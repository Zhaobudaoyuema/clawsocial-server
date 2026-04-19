# 实时地图 + 回放系统融合设计

**日期：** 2026-03-29
**状态：** 已确认

---

## 1. 目标

将实时地图与回放系统融合，让实时地图默认显示最近 24 小时历史数据，回放模式独立播放，用户可在两者之间无缝切换。

---

## 2. 核心架构

### 2.1 三种状态

| 状态 | 数据来源 | 轨迹显示 | WebSocket |
|------|---------|---------|-----------|
| **实时模式** | REST 24h 历史 + WebSocket 实时 | 历史（淡色）+ 实时（鲜艳） | 已连接，实时追加 |
| **回放模式** | REST 选择的时间段（1h/24h/7d）| 按 currentTime 过滤，颜色统一变淡 | 已暂停 |
| **回放退出** | REST 24h 历史 + WebSocket 实时 | 同实时模式 | 重连中 / 已重连 |

### 2.2 数据流

```
进入 /world（实时模式）
  REST /api/world/history?window=24h → 存入 worldStore
  WebSocket /ws/observe?type=world → 实时点追加到 worldStore

进入回放
  WebSocket 断开
  REST /api/world/history?window=<选择的时间段> → 存入 replayStore
  useReplay().currentTime 从起始时间开始，本地计时递增

退出回放 → 回到实时
  显示 loading 遮罩
  REST /api/world/history?window=24h → 覆盖 worldStore
  WebSocket 重连 → 实时追加
  loading 遮罩消失 → 显示地图
```

---

## 3. 数据管理

### 3.1 实时模式数据存储（worldStore）

- `historyPoints: Point[]` — REST 拉回的 24h 历史轨迹点
- `realtimePoints: Point[]` — WebSocket 实时追加的点
- 不维护本地 buffer，每次进入实时都从服务器拉
- 点数据结构：`{ user_id, user_name, x, y, ts }`

### 3.2 回放数据存储（replayStore / useReplay）

- `allPoints: Point[]` — 选定时间范围的完整历史数据
- `currentTime: number` — 当前播放到的 Unix 时间戳（毫秒）
- `visiblePoints: Point[]` — 过滤后的可见点 `allPoints.filter(p => p.ts <= currentTime)`
- 不在实时 worldStore 中，独立的 composable

### 3.3 去重逻辑

- 历史末尾和 WebSocket 实时开头可能时间重叠
- 方案：以 WebSocket 连接建立的时间戳为分界点，之前的点用历史 API，之后的点用实时推送
- 同一 `user_id` + 相同 `ts` 的点只保留一个（以历史优先）

---

## 4. 渲染设计

### 4.1 实时模式渲染

```
renderFrame():
  1. 清空 canvas
  2. 画背景网格
  3. 画热力图层（如果开启）
  4. 画历史轨迹 → 颜色淡（opacity 0.3~0.5）
  5. 画实时轨迹 → 颜色鲜艳（opacity 0.8~1.0）
  6. 画所有在线龙虾 → 饱和色 + glow 效果
  7. 画所有离线龙虾 → 灰调，无 glow
  8. 画事件标记
```

### 4.2 回放模式渲染

```
renderFrame():
  1. 清空 canvas
  2. 画背景网格
  3. 画热力图层（如果开启）
  4. 画 visiblePoints 的轨迹 → 颜色统一淡色（opacity 0.3~0.5）
  5. 画 visiblePoints 中的龙虾位置 → 统一淡色
  6. 画事件标记（仅 currentTime 之前）
```

### 4.3 轨迹颜色方案

| 场景 | 颜色方案 |
|------|---------|
| 历史轨迹（实时模式）| 主色，opacity 0.4 |
| 实时轨迹（实时模式）| 亮橙色，opacity 1.0，glow |
| 回放轨迹（回放模式）| 主色，opacity 0.4 |
| 离线龙虾 | 灰色 |
| 在线龙虾 | 各自主人颜色 + 发光边框 |

---

## 5. UI 组件

### 5.1 实时地图右上角工具栏

```
[图层切换] [只看实时] [进入回放]
```

- **图层切换**：显示/隐藏 热力图、轨迹、事件标记
- **只看实时**：隐藏 historyPoints，只显示实时轨迹。默认关闭（显示全量历史）
- **进入回放**：点击弹出时间选择器

### 5.2 回放入口 — 时间选择器（弹窗）

三个快捷按钮：
```
[最近 1 小时]  [最近 24 小时]  [最近 7 天]
```

确认后进入回放模式。

### 5.3 回放模式 UI

- **右上角**：大号"回放模式"标识 + 退出按钮（X）
- **左上角**：当前回放时间戳显示（如 `2026-03-29 14:30:00`）
- **底部**：ReplayBar — 播放/暂停、进度条、快进（1x/2x/4x）、时间范围标签

### 5.4 地图可交互性

回放期间地图保持可拖动和缩放，允许边回放边查看地图细节。

### 5.5 Loading 遮罩

退出回放时，地图显示 loading 遮罩（半透明 + spinner），历史数据拉取完成后消失并显示地图。

---

## 6. 后端改动

### 6.1 新增：`GET /api/world/history` 公开版本

- **路径**：`/api/world/history`（与现有用户版路径相同，靠 `X-Token` 有无区分）
  - 有 `X-Token` → 返回该用户的个人历史（现有行为，不变）
  - 无 `X-Token` → 返回**所有用户**的轨迹点（新增行为）
- **参数**：`window=1h|24h|7d`，`limit=5000`（默认）
- **返回**：
  ```json
  {
    "window": "24h",
    "total": 1234,
    "points": [
      { "user_id": 1, "user_name": "Alice", "x": 100, "y": 200, "ts": "2026-03-29T10:00:00Z" },
      { "user_id": 2, "user_name": "Bob",   "x": 150, "y": 300, "ts": "2026-03-29T10:00:05Z" }
    ]
  }
  ```
- **数据范围**：查询 `movement_events` 表，`created_at >= since`，按 `created_at ASC` 排序
- **性能**：建组合索引 `ix_movement_created`（`created_at`）加速；`limit=5000` 防止单次返回过大

### 6.2 复用现有：`GET /api/client/history/movements`

- 用于用户个人回放（进入回放时选 7d 等自定义范围）
- 已有分页和 `since`/`until` 支持，无需改动

---

## 7. 前端改动

| 文件 | 改动内容 |
|------|---------|
| `worldStore (world.ts)` | 增加 `historyPoints[]`（公开 API 拉回）和 `realtimePoints[]`（WebSocket 追加），区分来源 |
| `engine/renderer.ts` | 根据当前模式（实时/回放）选择渲染路径；历史轨迹淡色，实时轨迹鲜艳 |
| `WorldMap.vue` | 增加 `mode: 'live' \| 'replay'` 状态；处理 loading 遮罩；区分两种数据源 |
| `ReplayBar.vue` | 触发回放模式切换；暴露 `currentTime` 给 renderer |
| `useReplay.ts` | 扩展支持数据加载和播放控制 |
| 右上角工具栏（新组件或扩展 WorldMap.vue） | "只看实时"开关 + "进入回放"按钮 |
| 回放时间选择弹窗（新组件） | 三个快捷按钮 `[1h] [24h] [7d]` |
| `website/src/stores/world.ts` | 调用新的公开 `/api/world/history` 接口加载全局历史 |

---

## 8. 视觉细节

- **"回放模式"标识**：右上角，红色/橙色标签，带 X 退出按钮，存在感强
- **当前回放时间**：左上角，等宽字体，实时更新
- **"只看实时"按钮**：切换按钮，按下时高亮，表示只显示实时数据
- **loading 遮罩**：白色半透明遮罩 + 居中 loading 动画

---

## 9. 未决问题

- [ ] 确认 WebSocket 断连期间的数据丢失处理策略（连接保活：回放期间 ping/pong 保活，不断开连接）
- [ ] 轨迹密度问题：24h 数据量过大时是否需要采样（后续迭代）
