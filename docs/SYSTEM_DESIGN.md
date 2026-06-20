# 系统设计文档 — AI Game Forge

## 1. 系统架构

```
┌─ Browser ──────────────────────────────────────────────────────┐
│  React 18 + Vite + TypeScript                                  │
│  Pages: Home / Login / Register / Create / Play                │
│  State: TanStack Query (server) + Zustand (auth)               │
└────────────────────┬───────────────────────────────────────────┘
                     │ HTTP REST /api/*
                     ▼
┌─ FastAPI ──────────────────────────────────────────────────────┐
│  Routes: Auth / Games / Assets / Tasks                         │
│  Auth: JWT (HS256, 24h), bcrypt password hashing                │
│  CORS: localhost:5173, localhost:3000                          │
└────┬──────────────┬────────────────────┬───────────────────────┘
     │              │                    │
     ▼              ▼                    ▼
┌─────────┐  ┌──────────┐  ┌────────────────────────────────┐
│ SQLite  │  │  Redis   │  │  MinIO (S3-compatible)         │
│ (async  │  │  (Celery │  │  games/{id}/index.html         │
│  ORM)   │  │   Broker)│  │  games/{id}/assets/*           │
└─────────┘  └────┬─────┘  └────────────────────────────────┘
                  │
                  ▼
┌─ Celery Worker ────────────────────────────────────────────────┐
│  generate_game_task(task_id, game_id, prompt, asset_ids)        │
│                                                                 │
│  ┌─ Phase 1: PREPROCESS ──────────────────────────────────┐   │
│  │  • Load assets from MinIO                               │   │
│  │  • Describe images via LLM Vision API (Claude/GPT only) │   │
│  │  • Build structured GameGenerationContext                │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─ Phase 2: GENERATE ────────────────────────────────────┐   │
│  │  • Select adapter: ClaudeAdapter | OpenAIAdapter |      │   │
│  │                     DeepSeekAdapter (inherits OpenAI)   │   │
│  │  • Assemble system prompt + user prompt                 │   │
│  │  • Call LLM API → generate complete HTML5 game          │   │
│  │  • Temperature: 0.8 (creative), max_tokens: 16000       │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─ Phase 3: VALIDATE ────────────────────────────────────┐   │
│  │  • Parse HTML (BeautifulSoup)                           │   │
│  │  • Check game loop (requestAnimationFrame/Phaser/       │   │
│  │    setInterval)                                         │   │
│  │  • Check input handling (keyboard/mouse/touch)          │   │
│  │  • Security: block eval()                               │   │
│  │  • Auto-fix: send errors back to LLM for repair         │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─ Phase 4: PACKAGE & DEPLOY ────────────────────────────┐   │
│  │  • Package as single .html file                         │   │
│  │  • Upload to MinIO: games/{game_id}/index.html          │   │
│  │  • Update game.status = "published"                     │   │
│  │  • Update task.status = "completed"                     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 2. 数据模型

```
users
├── id (UUID PK)
├── username (VARCHAR 50 UNIQUE)
├── email (VARCHAR 255 UNIQUE)
├── password_hash (VARCHAR 255, bcrypt)
├── role (VARCHAR 20: player | creator)
└── created_at, updated_at

games
├── id (UUID PK)
├── title (VARCHAR 200)
├── description (TEXT)
├── cover_image_url (VARCHAR 500, OSS URL)
├── game_url (VARCHAR 500, OSS URL → playable HTML)
├── author_id (FK → users)
├── tags (JSONB: ["puzzle","arcade"])
├── status (VARCHAR 20: draft | generating | preview | published | failed)
├── prompt_text (TEXT)
├── play_count (INTEGER)
└── created_at, updated_at

game_assets
├── id (UUID PK)
├── game_id (FK → games, CASCADE)
├── asset_type (VARCHAR 50: image | audio | reference)
├── original_filename, oss_key, oss_url, file_size
└── created_at

game_favorites
├── user_id (FK → users, composite PK)
├── game_id (FK → games, composite PK)
└── created_at

generation_tasks
├── id (UUID PK)
├── game_id (FK → games), user_id (FK → users)
├── status (VARCHAR 30: pending | processing | completed | failed)
├── progress (INTEGER 0-100)
├── system_prompt_used, user_prompt_used, llm_response_raw
├── result_oss_url, error_message
├── started_at, completed_at
└── created_at
```

## 3. API 接口

全部18个端点，详见 `http://localhost:8000/docs` (OpenAPI 自动生成)：

| 分组 | 方法 | 路径 | 说明 |
|------|------|------|------|
| Auth | POST | /api/auth/register | 注册 |
| Auth | POST | /api/auth/login | 登录 |
| Auth | GET | /api/auth/me | 当前用户 |
| Games | GET | /api/games | 列表(分页+筛选) |
| Games | GET | /api/games/{id} | 详情 |
| Games | POST | /api/games | 创建草稿 [Auth] |
| Games | PUT | /api/games/{id} | 更新 [Auth] |
| Games | DELETE | /api/games/{id} | 删除 [Auth] |
| Assets | POST | /api/games/{id}/assets | 上传到MinIO [Auth] |
| Assets | GET | /api/games/{id}/assets | 列表 |
| Assets | DELETE | /api/games/{id}/assets/{id} | 删除 [Auth] |
| Tasks | POST | /api/games/{id}/generate | 触发生成 [Auth] |
| Tasks | GET | /api/tasks/{id} | 轮询状态 |
| Tasks | GET | /api/tasks/games/{id} | 任务历史 |
| Tasks | GET | /api/tasks/games/{id}/log | Agent 执行日志 |
| Favorites | POST | /api/games/{id}/favorite | 收藏/取消 [Auth] |
| Favorites | GET | /api/games/{id}/favorite | 收藏状态+总数 [Auth] |
| Favorites | GET | /api/auth/me/favorites | 我的收藏 [Auth] |

## 4. Agent 编排

### 适配器工厂 (Adapter Factory)
采用策略模式，通过环境变量切换 LLM 提供方。新增模型只需实现 `LLMAdapter` 抽象基类：

```python
LLMAdapter (ABC)
├── ClaudeAdapter  → api.anthropic.com    (支持 Vision)
├── OpenAIAdapter  → api.openai.com       (支持 Vision + 自定义 base_url)
└── DeepSeekAdapter → api.deepseek.com    (继承 OpenAIAdapter)
```

### 生成流水线 (4-Phase Pipeline)
1. **Preprocess**: 加载素材→Vision API描述→组装上下文
2. **Generate**: 选择适配器→构建System Prompt→调用LLM→收集HTML
3. **Validate & Fix**: 解析HTML→检查game loop→安全检查→失败自动修复
4. **Package & Deploy**: 单文件打包→上传到 S3 兼容对象存储（阿里云 OSS / AWS S3 / MinIO / Cloudflare R2）→更新状态为 preview

### System Prompt 设计
- 要求输出自包含HTML5游戏(Phaser.js CDN 或 Canvas API)
- 强制约束：游戏性(必须有game loop)、交互性(键盘/鼠标/触摸)、视觉(响应式)
- 安全约束：禁止eval()、限制外部请求CDN白名单
- 素材注入：通过Vision API描述图片，文本化注入prompt上下文

## 5. 远端部署协议

### 游戏文件格式
- **Bundle**: 单文件 `.html` (CSS内联`<style>` + JS内联`<script>` + CDN引用)
- **存储路径**: `games/{game_uuid}/index.html`
- **素材路径**: `games/{game_uuid}/assets/{asset_uuid}.{ext}`
- **访问方式**: Bucket public-read ACL，HTTP 直接获取
- **URL 格式**: OSS/AWS S3 虚拟主机风格 `https://{bucket}.{endpoint}/{key}`；MinIO 路径风格 `http://{endpoint}/{bucket}/{key}`（自动检测）

### Play 页加载流程
1. 前端 GET `/api/games/{id}` → 获取 `game_url`（OSS/S3/MinIO HTTP 地址）
2. `<iframe sandbox="allow-scripts allow-same-origin" src={game_url}>` 
3. Bucket 配置 public-read ACL + CORS（OSS 控制台可配）
4. 无对象存储时自动降级：HTML 存入 `generation_tasks` 表，通过 `/api/games/{id}/play-html` 直接服务

## 6. 安全策略

| 层面 | 措施 |
|------|------|
| **认证** | JWT (HS256, 24h过期), bcrypt密码哈希 |
| **上传** | 文件类型白名单 (image/*, audio/*), 10文件上限 |
| **生成代码** | iframe sandbox隔离, Validator禁止eval(), CDN白名单 |
| **API** | CORS限制origin, Authorization Bearer Token |
| **密钥** | .env + .gitignore, 不提交真实密钥 |
| **依赖** | requirements.txt锁定版本, npm audit |

## 7. 失败恢复

| 场景 | 策略 |
|------|------|
| LLM API 调用失败 | Celery自动重试1次(延迟60s)，更新task.status=failed |
| HTML 校验失败 | 将错误列表反馈LLM，自动修复1次 |
| MinIO 上传失败 | 抛出异常，Celery重试 |
| 素材描述失败 | 跳过该素材，继续生成(降级) |
| Redis/Celery 断连 | Docker restart: unless-stopped |

## 8. 可观测性

- **Celery**: 任务状态 (pending→processing→completed/failed)，进度百分比
- **Agent 日志**: 每个 Phase 记录 logger.info/error
- **Task 记录**: 保存 system_prompt_used, user_prompt_used, llm_response_raw (截断至10KB)
- **前端**: Task 轮询 (TanStack Query, 2s间隔)，进度条 + Pipeline 步骤可视化
- **FastAPI**: 自动 OpenAPI docs + /health 健康检查端点

---

## 9. 设计决策 FAQ（工程交付参考）

### 9.1 系统架构

**Q: 前端、后端、异步任务 Agent Orchestrator、数据库、对象存储之间如何协作？**

前端 (React+Vite) 通过 REST API 与 FastAPI 后端通信。生成游戏时，FastAPI 不直接调用 LLM（耗时 30-120s 会阻塞整个请求），而是将任务入队到 Celery（Redis 为消息代理）。Celery Worker 独立进程异步执行 4 阶段 Pipeline。生成的游戏文件上传到 MinIO/S3 对象存储，前端通过 iframe 动态加载。

```
浏览器 → HTTP → FastAPI → Celery Queue → Worker → LLM API → MinIO → 浏览器 iframe
                 ↕        ↕
             SQLite/PG   Redis
```

**Q: 为什么用 Celery + Redis 而不是 FastAPI 的 BackgroundTasks？**

BackgroundTasks 在主进程中执行，LLM 调用 30-120s 会阻塞整个 API worker。Celery 独立进程 + Redis 消息队列，解耦请求和生成，支持水平扩展 Worker。

**Q: 为什么用 SQLite 开发 + PostgreSQL 生产？**

SQLAlchemy 2.0 async ORM 抽象层隔离差异，改 `DATABASE_URL` 一行切换。SQLite 零配置启动开发环境，PostgreSQL 提供生产级并发和 JSONB 索引。

### 9.2 数据模型

**Q: 用户、游戏、素材、生成任务、Agent日志、状态如何建模？**

4 表拆分为独立实体而非单表扁平化：

- `users` — 账号与认证分离，role 字段留 OAuth 扩展空间
- `games` — 游戏元信息 + `status` 状态机 (draft→generating→preview→published→failed)，tags 用 JSON 灵活支持任意标签
- `game_assets` — 多对一关联 games，独立存储 OSS key，方便增删
- `generation_tasks` — 生成过程与游戏结果解耦，历史可追溯。保存完整 prompt + LLM 响应用于调试

**Q: 为什么 tags 用 JSON 而非关联表？**

游戏标签数量少（≤10）且无需跨游戏聚合查询。JSON 列避免了额外 join 表，SQLite/PG 均支持 LIKE/JSONB 查询。引入 GIN 索引后 PG 性能可达到关联表级别。

### 9.3 Agent 选型

**Q: 为什么用自建适配器工厂，而不是 OpenClaw、Hermes、Pi Agent、LangGraph 等成熟框架？**

**核心原因：MVP 复杂度控制 + 隔离供应商依赖。**

- **OpenClaw / Hermes / Pi Agent**：这些是完整 Agent 框架，提供多步骤推理、工具调用、记忆管理。但本项目的核心任务是"一段 prompt → 一个 HTML 文件"的单次生成，不需要多步拆解和多工具编排。引入框架徒增认知负担和依赖耦合。
- **LangGraph**：适合有状态、多节点、条件分支的复杂 Agent 工作流。当前流水线是线性的（Preprocess→Generate→Validate→Upload），状态机用简单的 status 字段 + Celery 即可表达，LangGraph 在 MVP 阶段过度设计。
- **适配器工厂 (ABC + env switch)**：3 个文件实现多 LLM 切换。新增供应商只需实现 `LLMAdapter` 两个方法（`generate`, `describe_image`），无框架锁定。

**扩展路径**：若未来需要多 Agent 协作（如策划 Agent + 美术 Agent + 代码 Agent 分工），迁移到 LangGraph 成本低——已有 Pipeline 中的每个 Phase 可无损映射为 LangGraph Node。

### 9.4 远端部署协议

**Q: 可运行游戏用什么文件结构？为什么是单文件 HTML？**

**格式**: 单文件 `.html`，CSS 内联 `<style>` + JS 内联 `<script>` + CDN 引用。

**为什么不用 manifest / bundle / 多文件目录？**

1. **存储简单**：对象存储中每个游戏只有一个文件，路径 `games/{uuid}/index.html`
2. **传输高效**：一次 HTTP GET 即可加载全部游戏内容
3. **LLM 友好**：要求 LLM 输出单文件不依赖外部路径解析，模型天然擅长
4. **沙箱安全**：iframe sandbox 加载单文件，无相对路径跨越问题
5. **跨平台**：移动端、桌面端、任何浏览器都能打开自包含 HTML

### 9.5 安全策略

**Q: 如何处理上传素材、Prompt Injection、生成代码执行、密钥管理、资源控制？**

| 威胁 | 措施 |
|------|------|
| **上传素材安全** | MIME 白名单（image/*, audio/*），最大 10 文件，单文件限制 10MB（FastAPI Form 嵌套校验） |
| **Prompt Injection** | 用户 prompt 仅作为 User Message 传入（非 System Prompt），LLM 输出不包含执行权限 |
| **生成代码执行** | `<iframe sandbox="allow-scripts allow-same-origin">` 双层隔离：不允许 `allow-top-navigation`、`allow-popups`；Validator 静态检查 `eval()` |
| **密钥管理** | LLM_API_KEY、JWT_SECRET 仅存于 `.env`，`.gitignore` 排除。生产环境由 Railway/Render Secret Manager 注入 |
| **资源控制** | `max_tokens: 16000` 限制 LLM 成本上限，Worker `--pool=solo` 串行执行防止并发过载 |

### 9.6 失败恢复

**Q: 模型调用不稳定、上传失败、生成失败时如何定位恢复？**

| 故障场景 | 恢复策略 | 可观察性 |
|----------|---------|---------|
| LLM API 超时/500 | Celery 自动重试 1 次（60s delay），仍失败写入 error_message | task.status = failed，前端展示错误原因 |
| HTML 校验失败 | 将错误列表返回 LLM 二次修复（temperature 0.5），仍失败降级交付 | Validator 日志 + task.llm_response_raw 保存原始输出 |
| MinIO 上传失败 | Railway 环境无 MinIO 时自动降级——HTML 存入 generation_tasks.llm_response_raw，通过 `/api/games/{id}/play-html` 直接服务 | 日志：`MinIO upload failed, storing in DB` |
| 素材描述失败 | Vision API 不可用时跳过该素材，其余素材正常注入 Prompt | 日志：`Failed to describe image`，任务继续 |
| 部署重启丢数据 | 后端 startup 检测空 DB，自动调用 `_auto_seed()` 注入 3 款种子游戏 + demo 用户 | `/health` 即可验证 |

### 9.7 可观测性

**Q: 如何记录生成过程、Agent 执行动作、用户体验？提供证据。**

| 观察维度 | 记录方式 | 证据路径 |
|----------|---------|---------|
| **任务进度** | Celery 任务状态机（pending→processing→completed/failed），数据库 `generation_tasks` 表实时更新 progress | `GET /api/tasks/{id}` |
| **Agent 日志** | Python logging，每个 Phase 输出 `[task_id] Phase N: ...` | Docker logs / Railway Deploy Logs |
| **LLM 调用记录** | `generation_tasks` 保存 `system_prompt_used`、`user_prompt_used`、`llm_response_raw` 完整链路 | 数据库查询 |
| **用户操作** | 前端 TanStack Query devtools + 浏览器 Network 面板 | F12 截图 |
| **系统健康** | `/health` 端点 + Readiness 检查 | `curl /health` |
| **验证证明** | `docs/VERIFICATION.md` 包含 16 项自动化测试 + 安全验证 + 性能数据 | 交付文档 |

**提示：** 演示时可打开浏览器 F12 → Network 面板，展示 API 请求序列（register → login → create → generate → poll → play），作为可观测性证据。
