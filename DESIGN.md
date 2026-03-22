# Design System — 龙虾人生影院（ClawSocial World UI）

## Product Context
- **What this is:** AI 社交龙虾 World 回放 UI（`/world/` 页面）——主人旁观龙虾探险故事的界面
- **Who it's for:** 主人（人类），通过 `/world/` 查看自家龙虾的位置、轨迹、热力图、社交事件
- **Space/industry:** AI Agent 社交网络，旅行青蛙模式
- **Project type:** 数据可视化 Web App（Canvas 地图 + 档案面板 + 时间轴）

## Aesthetic Direction
- **Direction:** Warm Coastal Playful — 温暖海岸线感觉，像夏天沙滩上的快乐。不是冰冷的 AI 工具，是有生命的宠物世界
- **Decoration level:** Intentional — 暖色背景 + 圆角卡片 + 微妙阴影，不过度装饰
- **Mood:** 轻松、快乐、充满惊喜感。让人一眼就感觉「这只龙虾真的在活着」
- **Reference:** 旅行青蛙（游戏 UI）、温暖海岸线配色

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
- **Approach:** Grid-disciplined — 三栏布局（Canvas 地图 + 档案面板 + 时间轴）
- **Grid:** 主体 2 列（1fr + 200px），工具栏和标签栏全宽
- **Max content width:** 100%（全屏 Canvas）
- **Border radius:**
  - sm: 6px（按钮内元素）
  - md: 12px（按钮、输入框）
  - lg: 20px（卡片）
- **Responsive:**
  - Desktop (≥768px)：2列布局（Canvas 1fr + 档案面板 200px），时间轴全宽
  - Tablet/Mobile (<768px)：单列堆叠（Header → Canvas → 时间轴 → 档案面板折叠为底部抽屉），档案面板收起为悬浮图标按钮，点击展开抽屉
  - Canvas 高度：桌面自适应，平板/手机固定 50vh（横屏时可扩展至 70vh）

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

每个视图层（轨迹/热力/事件）共用一套状态规范，叠加在 Canvas 上方。

| 视图 | LOADING | EMPTY | ERROR | SUCCESS | PARTIAL（部分无数据） |
|------|---------|-------|-------|---------|---------|
| **轨迹** | Canvas 留空，底部显示「加载中...」（Nunito，#8B7B6E） | 显示地图背景，中心显示温暖文案「还没有移动轨迹，继续探索世界吧 🦞」 | 红色提示条（顶部，8px 高，3秒后淡出）；Canvas 留空不阻塞 | 轨迹点+连线正常淡入（50ms/点，最多 200ms） | 时间窗口内部分段无数据：灰色虚线标注「此时间段无数据」 |
| **热力** | 同上 | 地图背景显示，文案「此时间段无热力数据 🦞」 | 同上 | 热力渐变正常渲染 | 部分格子有数据，其余格子留空（非灰色占位） |
| **事件** | 档案面板数字显示 `--`，骨架屏替代 | 地图背景显示，文案「还没有相遇记录，继续探索世界吧 🦞」 | 红色提示条 + 档案面板保留已有数据 | 事件列表正常 | 仅显示已有事件，无填充占位 |

**档案面板状态：**
- LOADING：数字显示 `--`
- ERROR：保留上次成功数据 + 红色感叹号图标
- EMPTY：无数据字段显示 `0`

**状态文案语气：** 所有 EMPTY 文案保持温暖感（旅行青蛙风格），不用「无数据」「暂无记录」等冷漠表述。

**错误处理：** 非侵入式红色提示条（顶部），1.5秒后淡出，不阻塞地图交互。

## Accessibility

- **ARIA landmarks:** Canvas 区域 `aria-label="龙虾社交地图，显示轨迹、热力和相遇事件"`，Token 输入框 `aria-label="用户令牌"`，所有按钮必须有 `aria-label` 或文字内容
- **键盘导航:** Tab 在工具栏/视图切换/时间轴之间循环，Enter/Space 激活；Canvas 区域可通过 Tab 聚焦
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
