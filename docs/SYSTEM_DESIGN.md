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
4. **Package & Deploy**: 单文件打包→上传MinIO→更新状态为published

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
- **访问方式**: MinIO public-read bucket，HTTP直接获取

### Play 页加载流程
1. 前端 GET `/api/games/{id}` → 获取 `game_url` (MinIO HTTP地址)
2. `<iframe sandbox="allow-scripts allow-same-origin" src={game_url}>` 
3. MinIO 配置 CORS + public-read bucket policy

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
