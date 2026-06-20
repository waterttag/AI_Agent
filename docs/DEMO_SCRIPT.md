# Demo 视频脚本 — AI Game Forge

时长：约 5 分钟
录制工具推荐：OBS Studio、Loom 或 Windows 自带录屏（Win+Alt+R）

---

## 场景 1：首页浏览（30秒）

```
打开 https://aiagent-production-5b68.up.railway.app

"这是 AI Game Forge，一个 AI Native 互动游戏平台。
首页展示了平台上的游戏，每张卡片有标题、描述、标签、作者和发布时间。
顶部可以按标签筛选——比如点 arcade，只看动作类游戏。"

操作：
- 展示标签筛选栏，点 "arcade"，过滤出 2 款游戏 ✅
- 点 "All" 恢复
- 鼠标悬停卡片，展示 Play 图标浮出效果
- 点右上角 "Create" 或 Hero 的 "Create a Game" 按钮
```

---

## 场景 2：登录 & 注册（30秒）

```
"创作游戏需要先登录。输入邮箱和密码直接登录。"

操作：
- 跳转到 /login
- 输入 demo@aigame.dev / demo123
- 点 "Sign In"
- 导航栏变为显示用户名 + Create 链接 ✅

"这是注册页面，新用户可以在这里创建账户。"

操作：
- 点导航栏 "Logout" 退出
- 导航栏恢复 Login / Sign Up
- 点 "Sign Up" 到 /register
- 展示注册表单
- 不填，直接回到登录，重新登录
```

---

## 场景 3：创作 & AI 生成（90秒）

```
"现在进入核心功能——用自然语言创作游戏。
我描述一个太空射击游戏：arrow keys 移动，space 射击，
destroy enemies to earn points，3条命，game over 有重启按钮。"

操作：
- 点 Create 进入 /create

"填写游戏信息——"
- Title: "Space Blaster"
- Description: "A fast-paced space shooter. Dodge asteroids, blast enemy ships..."
- Tags: 输入 arcade 回车，输入 shooter 回车，输入 action 回车
- 展示 Tags 的添加和删除

"在 Prompt 区用自然语言描述游戏——"
- 粘贴 Prompt：
  Create a space shooter game. The player controls a spaceship at the bottom.
  Left/right arrows to move, spacebar to shoot. Asteroids and enemy ships fall
  from above. Kill enemies = 10 points. Get hit = lose a life. 3 lives total.
  Show score and lives. Game Over screen with final score and restart button.
  Use Canvas API with colorful graphics on a dark space background.

"也可以拖拽图片上传素材，DeepSeek 会用它做参考——"
- 展示拖拽上传区

"点击 Generate Game with AI。"
- 点 Generate 按钮
- 进度条开始推进
- 4 阶段 Pipeline 高亮：
  Preprocess (10%) → Generate (70%) → Validate & Fix (85%) → Deploy (100%)
- 约 30-60 秒后完成

"生成完成！现在进入 Preview 模式，只有我自己能看到。"
- 展示 "Game Ready for Preview" 成功界面
- 点 "Preview & Publish"
```

---

## 场景 4：预览 & 发布（30秒）

```
"Play 页面顶部有黄色 Preview Mode 横幅，
提醒我游戏还未发布。我可以先试玩，确认没问题再发布。"

操作：
- 跳转到 /play/{gameId}
- 展示黄色 "Preview Mode" 横幅 ✅
- 点 "Fullscreen"，iframe 全屏展示游戏
- 按 Escape 退出全屏
-  展示右上角 Exit Fullscreen 按钮 ✅

"确认没问题后，点 Publish Now。"
- 点 "Publish Now" 按钮
- Banner 消失，游戏状态变为 published

"回到首页——Space Blaster 已经出现在列表中。"
- 点 "Back to Browse" 回首页
- 展示新增的 Space Blaster 卡片 ✅
```

---

## 场景 5：游玩（30秒）

```
"回到首页，挑一款游戏玩——比如 Classic Snake。"
- 点 Snake 卡片

"游戏从远端动态加载，运行在 iframe sandbox 内。Arrow keys 控制蛇的方向，吃苹果变长，撞到自己 Game Over。"
- 玩 10-15 秒 Snake
- 故意撞墙/撞自己
- 展示 "Play Again" 按钮

"再看一款 Memory Match——翻牌匹配 emoji。"
- 回到首页，点 Memory Match 卡片
- 翻几张牌展示

"Breakout Blitz——弹球打砖块。"
- 回到首页，点 Breakout 卡片
- 玩 5 秒
```

---

## 场景 6：技术架构（30秒）

```
"最后快速介绍一下系统架构。

后端是 FastAPI + SQLAlchemy async ORM，
AI Agent Harness 采用 4 阶段流水线——Preprocess / Generate / Validate / Deploy。
通过适配器工厂支持 Claude、OpenAI、DeepSeek 三种 LLM，环境变量一键切换。

前端 React + Vite + Tailwind + TanStack Query，
对象存储用 MinIO 或 Cloudflare R2，生产换 endpoint 即可迁移。

整个项目 80+ 源文件，10 次 Git commit，
通过 Railway 全栈部署，Docker Compose 一键本地启动。"
```

---

## 📝 口播要点速查

| 时间 | 说什么 | 做什么 |
|------|--------|--------|
| 0:00-0:30 | Home 介绍 + 标签筛选 | 展示首页，点标签过滤 |
| 0:30-1:00 | 登录流程 | 登录、登出、注册 |
| 1:00-1:30 | 创建表单填写 | Title/Desc/Tags/Prompt |
| 1:30-2:30 | AI 生成过程 | Generate → Pipeline |
| 2:30-3:00 | Preview & Publish | Banner + Publish按钮 |
| 3:00-3:30 | 游玩 3 款种子游戏 | Snake/Memory/Breakout |
| 3:30-4:00 | 游玩 AI 生成游戏 | Space Blaster |
| 4:00-4:30 | 架构介绍 | FastAPI/Agent/React/MinIO |
| 4:30-5:00 | 总结 + GitHub 地址 | 展示 GitHub README |
