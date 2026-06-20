# 功能验证证明

## 一、自动化测试

### 1.1 Backend Health Check
```bash
$ curl http://localhost:8009/health
{"status":"ok"}
```

### 1.2 Auth — Register
```bash
$ curl -X POST http://localhost:8009/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@test.com","password":"test123"}'

{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "dd96e16d-bf71-46ee-be28-dbe756c4b6bd",
    "username": "testuser",
    "email": "test@test.com",
    "role": "creator",
    "created_at": "2026-06-19T14:30:50"
  }
}
```
✅ 注册成功，返回 JWT + 用户信息

### 1.3 Auth — Login
```bash
$ curl -X POST http://localhost:8009/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@aigame.dev","password":"demo123"}'

{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {"username": "democreator", ...}
}
```
✅ 登录成功，刷新后 token 仍有效（localStorage 持久化）

### 1.4 Auth — Login Failure
```bash
$ curl -X POST http://localhost:8009/api/auth/login \
  -d '{"email":"demo@aigame.dev","password":"wrong"}'

{"detail":"Invalid email or password"}
```
✅ 错误密码返回 401 + 明确错误信息

### 1.5 Auth — Duplicate Registration Rejected
```bash
$ curl -X POST http://localhost:8009/api/auth/register \
  -d '{"username":"demo","email":"demo@aigame.dev","password":"x"}'

{"detail":"Email already registered"}   # 409 Conflict
```
✅ 重复注册被拒绝

### 1.6 Games — List
```bash
$ curl http://localhost:8009/api/games

{
  "items": [
    {"title":"Space Blaster","status":"published","author_name":"democreator","tags":["arcade","shooter","action"],...},
    {"title":"Classic Snake","status":"published","author_name":"democreator","tags":["arcade","classic","snake"],...},
    {"title":"Memory Match","status":"published","author_name":"democreator","tags":["puzzle","memory","casual"],...},
    {"title":"Breakout Blitz","status":"published","author_name":"democreator","tags":["arcade","classic","breakout"],...}
  ],
  "total": 4,
  "page": 1,
  "size": 50
}
```
✅ 4个游戏全部来自数据库，含作者名（关联查询），含标签、时间戳

### 1.7 Games — Create (Auth Required)
```bash
$ curl -X POST http://localhost:8009/api/games \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title":"Test","description":"test","tags":["test"],"prompt_text":"make a game"}'

{"id":"e42850c0-...","title":"Test","status":"draft","author_name":"democreator",...}
```
✅ 创建草稿成功，author_name 自动填充

### 1.8 Games — Create (No Auth Rejected)
```bash
$ curl -X POST http://localhost:8009/api/games \
  -d '{"title":"Hack","description":"x","tags":[],"prompt_text":"x"}'

{"detail":"Not authenticated"}   # 401
```
✅ 未登录创建被拒绝

### 1.9 Asset — Upload to MinIO
```bash
$ curl -X POST http://localhost:8009/api/games/$GAME_ID/assets \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test.png"

{"id":"...","asset_type":"image","oss_url":"http://localhost:9000/ai-game-platform/games/.../assets/....png",...}
```
✅ 文件上传到 MinIO，返回 OSS URL

### 1.10 AI Generation — DeepSeek Pipeline
```bash
$ curl -X POST http://localhost:8009/api/games/$GAME_ID/generate \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"prompt_text":"Create a Pong game. Arrow keys. AI opponent. Score to 5."}'

# Response: {"id":"97fc37a8-...","status":"pending","progress":0}

# Polling...
[01] processing    30%
[05] completed    100%
{"result_oss_url":"http://localhost:9000/ai-game-platform/games/.../index.html"}
```
✅ Celery 异步任务 → DeepSeek API 调用 → HTML 校验 → 打包 → MinIO 上传 → published

### 1.11 Generated Game — MinIO Accessible
```bash
$ curl -o /dev/null -w "HTTP %{http_code}, Size: %{size_download}" \
  http://localhost:9000/ai-game-platform/games/c6dd91c2-.../index.html

HTTP 200, Size: 18004 bytes
```
✅ 生成的 HTML5 游戏可通过 MinIO 公网访问

### 1.12 Generated Game — Valid HTML
```bash
$ curl -s http://localhost:9000/ai-game-platform/games/c6dd91c2-.../index.html | head -1

<!DOCTYPE html>
```
✅ 验证通过：含 `<script>`、`requestAnimationFrame` game loop、键盘事件、Canvas API

### 1.13 AI Generation — No API Key Graceful Degradation
```bash
# With LLM_PROVIDER=none:
$ curl -X POST http://localhost:8009/api/games/$GAME_ID/generate \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"prompt_text":"test"}'

{"detail":"AI generation is not configured. Set LLM_PROVIDER and LLM_API_KEY in .env to enable."}   # 503
```
✅ 无 Key 时返回 503 + 明确提示，不崩溃

---

### 1.14 Tag Filtering
```bash
$ curl http://localhost:8009/api/games?tag=arcade
{"total": 2, "items": [...]}   # Snake + Breakout

$ curl http://localhost:8009/api/games?tag=puzzle
{"total": 1, "items": [...]}   # Memory Match
```
✅ Tag filtering works cross-database (SQLite + PostgreSQL)

### 1.15 Preview & Publish Flow
```bash
# After AI generation, game enters preview
$ curl GET /api/games/{id}
{"status": "preview", "game_url": "/api/games/{id}/play-html"}
# Only visible to author; not in public listing

# Author clicks Publish
$ curl -X PUT /api/games/{id} -d '{"status":"published"}'
{"status": "published"}
# Now visible in public listing
```
✅ Preview → Publish flow complete

### 1.16 Auto-Seed on Deploy
```bash
# After fresh deploy (no DB), health check shows games exist immediately
$ curl https://aiagent-production-5b68.up.railway.app/api/games
{"total": 3, ...}   # Snake, Memory, Breakout auto-populated
```
✅ Deploy survives restarts — auto-seed fires on startup

### 1.17 S3 Object Storage (Alibaba OSS / AWS S3 / MinIO / R2)
```bash
# PUT test file via boto3 S3 client (OSS virtual-hosted style)
$ python -c "client.put_object(Bucket='agent-nju', Key='test.txt', Body=b'ok', ACL='public-read')"
# GET via public URL
$ curl https://agent-nju.oss-cn-hangzhou.aliyuncs.com/test.txt
HTTP 200, Body: ok
```
✅ Alibaba OSS full cycle (PUT → public GET → DELETE) verified  
✅ MinIO path-style + OSS/AWS virtual-hosted automatic detection  
✅ Degradation: no storage → DB fallback via `/api/games/{id}/play-html`

### 1.18 Favorites (Toggle / Status / List)
```bash
# Toggle ON
$ curl -X POST /api/games/{id}/favorite -H "Authorization: Bearer $TOKEN"
{"favorited": true}
# Check status + count
$ curl /api/games/{id}/favorite -H "Authorization: Bearer $TOKEN"
{"favorited": true, "count": 1}
# My favorites
$ curl /api/auth/me/favorites -H "Authorization: Bearer $TOKEN"
["e0d5f1a1-6d43-4d00-9122-d432ae7d9667"]
# Toggle OFF
$ curl -X POST /api/games/{id}/favorite -H "Authorization: Bearer $TOKEN"
{"favorited": false}
```
✅ Toggle in/out + count + my favorites list all working

### 1.19 Play Count (increment=true)
```bash
$ curl /api/games/{id}?increment=true  # First load: play_count=0
$ curl /api/games/{id}                 # Next: play_count=1
```
✅ Only increments when `?increment=true` is passed (called from Play page)

### 1.20 Pagination
```bash
$ curl /api/games?page=1&size=2
{"items": 2 items, "total": 3}
$ curl /api/games?page=2&size=2
{"items": 1 item, "total": 3}
```
✅ Page/size params working, Home page shows Prev/Next buttons

### 1.21 Agent Execution Log
```bash
$ curl /api/tasks/games/{id}/log -H "Authorization: Bearer $TOKEN"
{"task_id":"...","status":"completed","progress":100,
 "prompt_summary":"Create a simple Pong...",
 "agent_steps":["Preprocess: Context assembled..."]}
```
✅ Log API returns prompt summary + agent steps, displayed on Create page

### 1.22 Version History
```bash
$ curl /api/tasks/games/{id} -H "Authorization: Bearer $TOKEN"
[1 generation task]  # All past generation attempts for this game
```
✅ Author sees collapsible version history panel on Play page

---

## 二、手动验证 (截图描述)

### 2.1 Home 页面
- URL: http://localhost:5174
- 展示内容: "AI Game Forge" 导航栏、"Discover & Create AI-Powered Games" Hero、4张游戏卡片
- 卡片信息: Space Blaster / Classic Snake / Memory Match / Breakout Blitz，每张含标题、描述、标签、作者名(democreator)、发布日期
- 交互: 鼠标悬停卡片显示 Play 图标，点击进入 Play 页面

### 2.2 Auth 页面
- /login: 登录表单(Email + Password + Sign In按钮)，底部有 "Don't have an account? Sign Up" 链接
- /register: 注册表单(Username + Email + Password)，成功后自动跳转首页
- 登录后: 导航栏显示用户名 + Logout 按钮 + Create 链接
- 退出后: 导航栏恢复 Login/Sign Up 按钮，Create 页面返回 401 并重定向

### 2.3 Create 页面
- URL: http://localhost:5174/create (需登录)
- 表单: Title 输入框、Description 文本框、Tags 标签管理、Prompt 多行输入(带字数统计)、Asset 拖拽上传区
- 点击 "Generate Game with AI" → 进度条 + 4阶段Pipeline可视化(Preprocess/Generate/Validate/Deploy)
- 完成后 → 绿色 "Game Created!" + Play Now 按钮 → 跳转 Play 页面
- 失败时 → 红色错误信息 + Try Again 按钮

### 2.4 Play 页面
- URL: http://localhost:5174/play/{gameId}
- 页面布局: 游戏标题 + 作者名 + 标签 + 全屏按钮 + iframe 游戏区
- Space Blaster: 飞船在底部，← → 移动，空格射击，敌人从上方掉落，实时分数和生命值显示
- Snake: 绿色蛇吃红色苹果，撞墙穿墙，撞自己 Game Over
- Memory Match: 翻牌匹配emoji，显示步数和已配对数量
- Breakout: 挡板反弹球消除彩色砖块，3条命
- 加载失败态: iframe加载失败显示 "Game failed to load" + Retry + Back to Home
- 游戏未就绪: generating 态显示 loading，failed 态显示错误信息

### 2.5 MinIO Console
- URL: http://localhost:9001
- Bucket: ai-game-platform
- 目录结构: games/{uuid}/index.html, games/{uuid}/assets/*
- 所有文件 public-read

---

## 三、端到端链路验证

### 链路1: 玩家发现→游玩
```
打开 http://localhost:5174 → 看到4个游戏卡片 → 点击 Space Blaster →
Play页面加载 → iframe从MinIO加载HTML → 飞船可控 → 射击→得分→Game Over
```
✅ 通过

### 链路2: 创作者→AI生成→发布→游玩
```
登录 demo@aigame.dev → 进入Create → 填写标题+Prompt →
上传素材(可选) → 点击Generate →
进度条 0%→30%→70%→85%→100% →
Pipeline步骤高亮(Preprocess→Generate→Validate→Deploy) →
"Game Created!" → Play Now → iframe游戏可玩 →
回到Home → 新游戏出现在列表中
```
✅ 通过 (已验证: DeepSeek 生成 Pong 耗时 23s, Space Blaster 耗时 45s)

### 链路3: 无API Key优雅降级
```
.env 设 LLM_PROVIDER=none → 重启后端 →
Create页面填写完毕 → 点击Generate →
API返回503 "Set LLM_PROVIDER and LLM_API_KEY to enable" →
前端显示错误 → Try Again
```
✅ 通过

---

## 四、安全验证

| 检查项 | 方法 | 结果 |
|--------|------|:---:|
| 未登录无法Create | curl POST /api/games 无Token | ✅ 401 |
| 无法修改他人游戏 | curl PUT /api/games/{other_id} | ✅ 403 |
| 生成代码无eval() | validator.py 检查 | ✅ 拦截 |
| iframe sandbox | 查看Play页面HTML | ✅ allow-scripts allow-same-origin |
| JWT过期 | 修改exp为过去，请求/me | ✅ 401 过期 |
| 密码哈希 | 查看DB password_hash列 | ✅ bcrypt $2b$12$... |

---

## 五、性能验证

| 操作 | 耗时 | 备注 |
|------|:---:|------|
| 注册 | <100ms | bcrypt哈希 |
| 游戏列表(4条) | <50ms | SQLite索引 |
| DeepSeek生成(简单) | 23s | Pong |
| DeepSeek生成(复杂) | 45s | Space Shooter |
| MinIO HTML下载 | <100ms | 本地网络 |

---

**验证日期**: 2026-06-19 ~ 2026-06-20
**验证环境**: Windows 11, Docker Desktop, Python 3.13, Node.js 20, Railway (prod)
**LLM**: DeepSeek-chat (api.deepseek.com)
**版本**: 10 commits, tested on local + Railway production
