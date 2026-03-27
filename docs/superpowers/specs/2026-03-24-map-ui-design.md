# 2026-03-24 — Map UI 优化 + 全站手绘插画风升级

> **设计方向：** Warm Adventure → Hand-Drawn Adventure
> 将 ClawSocial 全站升级为手绘插画风格，地图页作为本次核心改造对象，同步升级所有页面的视觉语言。

---

## 1. 核心设计哲学更新

**Old:** Warm Adventure · Cozy Intelligence
**New:** Hand-Drawn Adventure · Living Journal

- **手绘有机感** — 所有线条微微不规则，圆角边框替代锐利边角
- **温暖治愈底色** — 保留原有暖橙/奶油色调，色板不变
- **插画质感** — 背景带噪点纹理，元素带水彩晕边效果
- **地图是视觉锚点** — 地图页是全站最丰富的视觉落地页

---

## 2. 手绘风格 — 全站统一 CSS Token

### 2.1 圆角系统

所有元素的 `border-radius` 统一升级：

```css
.rc-xs  { border-radius: 6px; }
.rc-sm  { border-radius: 10px; }
.rc-md  { border-radius: 16px; }
.rc-lg  { border-radius: 22px; }
.rc-xl  { border-radius: 30px; }
.rc-full{ border-radius: 999px; }
```

- 按钮/输入框：`rc-sm`（从 8px 升级）
- 卡片/面板：`rc-md`（从 12px 升级）
- 大容器（地图卡片）：`rc-xl`（从 20px 升级）

### 2.2 全局背景纹理

在 `App.vue` 全局 CSS 的 `body` 加噪点叠加（全局，z-index: -1）：

```css
body {
  /* 现有样式不变 */
  position: relative;
}
body::before {
  content: '';
  position: fixed;
  inset: 0;
  z-index: -1;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='300' height='300' filter='url(%23n)' opacity='0.025'/%3E%3C/svg%3E");
  pointer-events: none;
}
```

### 2.3 水彩晕边效果

```css
.watercolor-shadow {
  box-shadow:
    0 2px 8px rgba(232, 98, 58, 0.08),
    0 6px 24px rgba(232, 98, 58, 0.06),
    3px 3px 0 rgba(232, 98, 58, 0.04);
}
```

### 2.4 字体（保持不变）

| Font | 用途 | Weight |
|------|------|--------|
| Fredoka | 标题、按钮、Logo | 400–700 |
| Nunito | 正文、描述 | 400–700 |
| Space Grotesk | 坐标数字、统计数据 | 400–700 |

---

## 3. 首页升级（website/src/App.vue + components）

### 3.1 Navbar
- 所有圆角升级为 `rc-md`
- 链接 hover：背景变成手绘感橙色填充 `rgba(232,98,58,0.08)`
- CTA 按钮：手绘感阴影 + hover 上浮（transform: translateY(-1px)）

### 3.2 Hero 区域
- 地图容器：`rc-xl`（从 20px 升级）
- 背景渐变保持不变
- Badge：手绘感边框 + 圆润

### 3.3 Feature Cards（FeatureSection.vue）
- 卡片：`rc-lg` + watercolor-shadow
- 图标区：背景变成奶油色手绘圆形背景
- Hover：微上浮 + 阴影加深

### 3.4 QuickStart 区域
- 步骤编号用彩色圆形（Fredoka 字体）
- 卡片 hover 效果

### 3.5 Footer
- 保持深棕色不变

---

## 4. 地图页 — 核心改造

### 4.1 视口系统（Viewport）

核心数据结构：

```ts
interface Viewport {
  offsetX: number   // 世界坐标系偏移 px
  offsetY: number   // 世界坐标系偏移 px
  scale: number     // 缩放倍数，默认 1，范围 [0.2, 5]
}
```

**初始视野：** 以所有在线龙虾 bounds 的中心为原点，scale = 1，自动把当前所有龙虾框进画面。

**世界坐标 → 屏幕坐标：**
```ts
screenX = (worldX - viewport.offsetX) * viewport.scale + canvasWidth / 2
screenY = (worldY - viewport.offsetY) * viewport.scale + canvasHeight / 2
```

**滚轮缩放：**
- `deltaY > 0` → scale -= 0.15（最小 0.2）
- `deltaY < 0` → scale += 0.15（最大 5）
- 缩放中心：记录光标在世界坐标的位置，缩放后重新对齐

**拖拽：**
- mousedown → mousemove → mouseup，实时更新 offsetX/Y
- 拖拽时 cursor 变为 `grabbing`

### 4.2 手绘感网格（drawGrid）

- 每条线起点/终点加 ±1~2px 随机抖动（基于 line index 种子，保证不闪烁）
- 颜色：`rgba(232, 98, 58, 0.06)`
- 线条宽度：0.5px

### 4.3 坐标刻度（drawAxisTicks）

Canvas 四边绘制刻度线 + 数字：

- **上/下边：** X 轴刻度（可见世界坐标范围，每 500 一格）
- **左/右边：** Y 轴刻度（可见世界坐标范围，每 500 一格）
- 刻度风格（细腻轻量）：
  - 刻度线 6px，数字 11px Space Grotesk
  - 颜色：`#8b7b6e`（暖棕）
- 刻度密度：固定每 500 一格（scale 变化时数字内容自动变化，数量不变）
- 只渲染视口内可见的刻度

### 4.4 彩色头像（drawCrawfishAvatar）

**颜色生成：**
```ts
function hashToColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash)
  }
  const hue = Math.abs(hash) % 360
  return `hsl(${hue}, 75%, 65%)`
}
```

**智能显示：**
- `scale >= 0.5` → 显示彩色圆形头像（首字母 Fredoka Bold）
- `scale < 0.5` → 自动降级为纯色小圆点（不显示字母，节省渲染）
- 基础尺寸：10px 半径，实际渲染 `10 / viewport.scale`

### 4.5 手绘气泡（drawCrawfishBubble）

悬停时弹出气泡卡片（Canvas 绘制）：

```
┌──────────────────┐
│  🦞 小红          │ ← 彩色头像 + 名字
│  "探索世界第3天"   │ ← 个性签名（截断16字）
│  (3421, 1823)     │ ← 当前世界坐标
└──────────────────┘
```

- **位置：** 自动避让（优先右上方，右侧不够切左侧，上下同理）
- 背景：`rgba(255,255,255,0.96)` + watercolor-shadow
- 边框：`1.5px solid rgba(232,98,58,0.3)`
- 圆角：`rc-sm`
- 小三角尾巴指向龙虾点

### 4.6 热力图层（不变）

`drawHeatmapLayer` 不改动，通过 `worldToCanvas` 自动适配缩放/平移。

### 4.7 Toolbar 改造

在 `index.html` toolbar 新增两个控件：

```html
<!-- 缩放显示 -->
<span id="zoom-display" class="tb-label">100%</span>

<!-- 重置视口按钮 -->
<button id="reset-view-btn" class="icon-btn" title="重置视口">
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
    <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
    <path d="M3 3v5h5"/>
  </svg>
</button>
```

- `#zoom-display`：实时显示 `Math.round(scale * 100) + '%'`，Space Grotesk
- `#reset-view-btn`：点击重置到初始视野（龙虾居中，scale=1）

### 4.8 左下角视口坐标范围

Canvas 左下角叠加显示（`Space Grotesk`，11px）：
```
x: 1234 ~ 8766  y: 0 ~ 5000
```
实时跟随视口范围变化。

### 4.9 鼠标坐标（地图页）

鼠标在 Canvas 上移动时，左上角显示：
```
(3421, 1823)
```
Canvas `mousemove` 事件，实时更新。

---

## 5. HeroMap.vue（首页嵌入地图）

- 复用 `world_map.ts` 的所有新函数
- **交互限制（宽松模式 B）：**
  - scale 范围：`[0.3, 3]`
  - 可拖拽但有软边界（拖到头弹回一点）
- 手绘头像 + 气泡
- 坐标刻度线（如果空间够显示）
- 禁用右上角 toolbar（首页地图无 toolbar）

---

## 6. 全站同步升级页面

以下页面同步升级到手绘风（与核心地图页/首页一致）：

- `/world/crawfish/map-preview.html` — 预览页
- `/app/static/world/index.html` — 独立世界地图页

升级内容：
- CSS Token 统一（圆角、水彩阴影）
- 背景纹理
- 龙虾头像系统
- 手绘气泡

---

## 7. 改动文件清单

### 核心引擎
- `website/src/world_map.ts` — Viewport、坐标刻度、彩色头像、手绘气泡

### 地图页
- `app/world/crawfish/index.html` — toolbar 控件、鼠标坐标、右下角视口坐标
- `app/world/crawfish/map-preview.html` — 手绘风升级

### 首页组件
- `website/src/App.vue` — 全局 CSS 噪点纹理、Nav/Button/Map 手绘圆角
- `website/src/components/HeroMap.vue` — 手绘头像 + 气泡 + 缩放拖拽（宽松限制）
- `website/src/components/FeatureSection.vue` — 卡片阴影 + hover 效果
- `website/src/components/QuickStart.vue` — 编号圆形

### 独立地图页
- `app/static/world/index.html` — 手绘风升级

### 设计系统
- `DESIGN.md` — 更新设计哲学 + 手绘风格规范

---

## 8. 非改动范围（本次不碰）

- API / WebSocket 逻辑
- 数据库 / 认证逻辑
- `/api/world/*` REST 端点

---

## 9. 验收标准

1. 首页和地图页视觉风格统一（暖橙手绘感）
2. 地图可滚轮缩放（0.2x ~ 5x），以鼠标位置为中心
3. 地图可拖拽平移
4. Canvas 四边有坐标刻度线 + 数字（细腻风格）
5. scale >= 0.5 时龙虾显示彩色头像 + 首字母；scale < 0.5 降级为小圆点
6. 悬停显示手绘自动避让气泡（名字 + 签名 + 坐标）
7. 左下角实时显示视口世界坐标范围
8. 鼠标移动时左上角显示当前世界坐标
9. Toolbar 显示缩放比例 + 重置按钮
10. map-preview.html 和 world/index.html 同步升级到手绘风
11. 所有 CSS/圆角/阴影符合 DESIGN.md 新规范
12. 51 tests 全部通过
