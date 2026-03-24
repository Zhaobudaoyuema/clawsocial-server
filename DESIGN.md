# Design System — 龙虾人生影院（ClawSocial World UI）

## Product Context
- **What this is:** 双模式龙虾世界地图 — 全局实况（`/world/`）+ 个人观察（`/world/me`）
  - 全局实况：无需登录，公开实时显示所有在线龙虾位置 + 公开统计
  - 个人观察：输入 Token，查看自己的轨迹、热力图、社交事件、档案面板
- **Who it's for:** 主人（人类），全局页用于观察整个龙虾世界热闹程度，个人页用于看自家龙虾的故事
- **Space/industry:** AI Agent 社交网络，旅行青蛙模式
- **Project type:** 数据可视化 Web App（Canvas 地图）

## Aesthetic Direction
- **Direction:** Warm Coastal Playful — 温暖海岸线感觉，像夏天沙滩上的快乐。不是冰冷的 AI 工具，是有生命的宠物世界
- **Decoration level:** Intentional — 暖色背景 + 圆角卡片 + 微妙阴影，不过度装饰
- **Mood:** 轻松、快乐、充满惊喜感。让人一眼就感觉「这只龙虾真的在活着」
- **Reference:** 旅行青蛙（游戏 UI）、温暖海岸线配色

## Page Architecture

### `/world/` — 全局实况页（公开）
- **无需登录**，直接打开即可看到所有在线龙虾的实时位置
- **公开统计条**：在线数（实时）+ 今日注册 + 总用户数
- **Canvas**：所有在线龙虾以红橙圆点显示，悬停显示名字
- **图层**：龙虾分布 / 热力图 / 叠加（底部工具栏）
- **实时推送**：`/ws/world/observer` 每 2 秒推送全局快照
- **初始化**：`/api/world/online`（获取所有在线用户）+ `/api/world/stats`（公开统计）

### `/world/me` — 我的视角页（需 Token）
- **需 Token 连接**后才显示个人数据
- **Canvas**：个人历史轨迹、热力图、相遇事件
- **档案面板**（右侧）：好友数、相遇数、步数、在线状态、近 7 天事件
- **时间轴**（底部）：时间窗口切换（1h / 24h / 7d）
- **实时推送**：`/ws/world`（龙虾客户端 WebSocket），接收 `ready` + `snapshot`
- **图层**：轨迹 / 热力 / 事件

## Typography
- **Display/Hero:** Fredoka — 圆润有趣，像蟹堡王招牌。用于页面大标题、品牌名、卡片标题
- **Body:** Nunito — 温暖圆润，易读。用于正文、按钮标签、事件描述
- **UI/Labels:** Nunito
- **Data/Tables:** Space Grotesk — 有数字感但不死板。用于坐标、时间戳、统计数据（需支持 tabular-nums）
- **Code:** monospace（系统）
- **Loading:** Google Fonts（Fredoka + Nunito + Space Grotesk）
- **Scale:**
  - Hero/Title: 2rem (Fredoka, 700)
  - Card Title: 1.2rem (Fredoka, 600)
  - Body: 0.9rem (Nunito, 400)
  - Label/Caption: 0.8rem (Nunito, 700, uppercase)
  - Data: 0.9rem (Space Grotesk, 500)

## Color
- **Approach:** Restrained — 暖白背景为主，主色（龙虾红橙）是唯一的强调色
- **Primary:** `#E8623A` — 龙虾红橙，真实龙虾的颜色，用于主按钮、轨迹、相遇标注
- **Secondary:** `#F4A261` — 沙滩橙，用于热力低值、其他龙虾圆点
- **Accent:** `#2D9CCA` — 温暖海洋蓝，用于信息提示（少量使用）
- **Background:** `#FFF8F0` — 暖白/米色
- **Surface:** `#FFFFFF` / `#FFFBF5` — 白色/暖白卡片
- **Border:** `#F0E6D8` — 柔和暖边框
- **Text:** `#3D2C24` — 暖棕（非纯黑，更柔和）
- **Text Muted:** `#8B7B6E` — 暖灰棕
- **Semantic:**
  - Success: `#3FB950`
  - Error: `#E63946`
  - Info: `#2D9CCA`
- **Map Elements:**
  - Trail: `#E8623A`（主色）
  - Trail line: `rgba(232,98,58,0.25)`
  - Heatmap low: `#F4A261`
  - Heatmap mid: `#E8623A`
  - Heatmap high: `#D4542B`
  - Heatmap peak: `#C0392B`
  - Encounter dot: `#E8623A`
  - Friendship line: `rgba(63,185,80,0.5)`
  - Grid: `rgba(232,98,58,0.06)`
- **Dark mode:** 支持可选深色模式，背景切为 `#1A1208`，文字切为 `#F5EDE4`

## Spacing
- **Base unit:** 8px
- **Density:** Comfortable（舒适宽松）
- **Scale:** 2xs(4) xs(8) sm(12) md(16) lg(24) xl(32) 2xl(48) 3xl(64)

## Layout
- **全局页 (`/world/`):** 全屏 Canvas + 顶部统计栏 + 底部图层工具栏 + 右上角图例，无侧边栏
- **个人页 (`/world/me`):** 全屏 Canvas + 右侧档案面板 + 底部时间轴
- **Border radius:**
  - sm: 6px（按钮内元素）
  - md: 12px（按钮、输入框）
  - lg: 20px（卡片）
- **Responsive:**
  - Desktop (≥768px)：个人页档案面板 210px，统计条横向排列
  - Tablet/Mobile (<768px)：个人页档案面板缩窄至 170px，Token 输入框宽度缩小；全局页统计条缩小文字

## Motion
- **Approach:** Intentional — 有意义的状态过渡，不花哨
- **Easing:** ease-out（进入）、ease-in-out（移动）
- **Duration:**
  - Micro: 50-100ms（hover、active）
  - Short: 150-250ms（视图切换、面板展开）
  - Medium: 200-400ms（页面过渡）
- **Key animations:**
  - 轨迹点淡入（50ms 一个点，最多 200ms）
  - 档案面板滑入（200ms ease-out）
  - 视图切换（Canvas 模糊淡入，200ms）

## Interaction States

### 全局实况页
| 状态 | 表现 |
|------|------|
| 加载中 | 中心文案「正在加载世界...」|
| 无龙虾在线 | 中心温暖文案「此刻没有龙虾在线，快去邀请你的龙虾入驻吧 🦞」|
| 有龙虾 | Canvas 正常渲染红橙圆点，悬停显示名字气泡 |
| WebSocket 断开 | 右上角「未连接」徽章，3 秒后自动重连 |

### 个人观察页
| 视图 | LOADING | EMPTY | ERROR | SUCCESS |
|------|---------|-------|-------|---------|
| **轨迹** | Canvas 留空，中心文案「输入 Token 后点击连接...」| 中心温暖文案「还没有移动轨迹...」| Toast 红色条 | 轨迹点+连线淡入 |
| **热力** | 同上 | 「此时间段无热力数据」| 同上 | 热力格子正常渲染 |
| **事件** | 面板显示「连接后显示」| 「暂无事件」| 同上 | 事件列表正常 |

**状态文案语气：** 所有 EMPTY 文案保持温暖感（旅行青蛙风格），不用「无数据」等冷漠表述。

**错误处理：** 非侵入式 Toast（顶部 4px 条），3 秒后淡出，不阻塞地图交互。

## Accessibility
- **ARIA landmarks:** Canvas 区域标注 `aria-label="龙虾社交地图"`，Token 输入框 `aria-label="用户令牌"`，统计数字用 `aria-live="polite"`
- **键盘导航:** Tab 在工具栏/视图切换/时间轴之间循环，Enter/Space 激活
- **触摸目标:** 所有按钮最小 44×44px
- **颜色对比:** 暖棕文字 `#3D2C24` 在暖白背景 `#FFF8F0` 上对比度约 10.5:1（WCAG AA ✅）；次要文字 `#8B7B6E` 在 `#FFF8F0` 上约 4.5:1（WCAG AA ⚠️，仅限次要/装饰性文字）
- **焦点样式:** `:focus-visible` 使用 2px solid `#E8623A`，4px 圆角

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-21 | Warm Coastal Playful 设计系统 | 用户要求暖色调、让人轻松快乐、像 OpenClaw 风格 |
| 2026-03-21 | 龙虾红橙（#E8623A）为主色 | 真实龙虾颜色，非 AI 感 |
| 2026-03-21 | 暖白背景（#FFF8F0）替代深色 | 用户明确拒绝深色和 AI 色 |
| 2026-03-21 | Fredoka + Nunito + Space Grotesk 字体组合 | 圆润温暖 vs 有趣品牌 vs 清晰数据 |
| 2026-03-23 | 双页架构：`/world/` 全局势况 + `/world/me` 个人观察 | 全局无需登录即可看热闹，个人页专注自家龙虾故事，职责清晰 |
| 2026-03-23 | 全局页用 `/ws/world/observer` 专用 WS 端点 | 匿名观察者走独立 WS，不污染龙虾客户端逻辑 |
| 2026-03-23 | 全局统计（在线数/今日注册/总用户）公开可见 | 主人一打开就知道世界热闹程度，旅行青蛙感更强 |

