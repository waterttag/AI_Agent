# 🎮 AI Game Forge — AI Native Interactive Game Platform

An AI-powered web platform where **creators describe games in natural language** and **players discover & play** community-generated interactive games. Built as a full-stack MVP with an extensible **AI Agent Harness** architecture.

## ✨ Features

- **Tag Filtering** — Filter games by tag on the Home page
- **Preview → Publish** — AI-generated games enter preview mode first; creators review and publish when ready
- **Auto-Seed** — Fresh deploys automatically populate with 3 example games
- **Fullscreen Play** — Click fullscreen or press Escape to exit
- **Multi-LLM Support** — Claude / OpenAI / DeepSeek (adapter pattern, swap via env var)
- **No-MinIO Fallback** — Serves game HTML directly from the database when object storage is unavailable

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER BROWSER                             │
│  React+Vite (Port 5173)                                         │
│  Pages: Home / Login / Register / Create / Play                 │
└──────────────┬──────────────────────────────────────────────────┘
               │ HTTP/REST
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend (Port 8000)                  │
│  ┌──────────┬──────────┬───────────┬─────────────────────────┐ │
│  │ Auth API │ Game API │ Asset API │ Task API (Generation)   │ │
│  └──────────┴──────────┴───────────┴─────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              AI Agent Harness (Core Differentiator)      │  │
│  │  Preprocess → Generate → Validate → Package → Upload      │  │
│  │  ┌─────────┐  ┌─────────────┐  ┌────────────────────┐   │  │
│  │  │ Claude  │  │   OpenAI    │  │  (Extensible)      │   │  │
│  │  │ Adapter │  │   Adapter   │  │  LLMAdapter ABC    │   │  │
│  │  └─────────┘  └─────────────┘  └────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────┬──────────────┬──────────────────┬────────────────────────┘
       │              │                  │
       ▼              ▼                  ▼
┌──────────┐  ┌──────────┐     ┌──────────────┐
│ SQLite   │  │  Redis   │     │    MinIO      │
│ (Dev)    │  │ (Celery  │     │  (S3 Object   │
│ → PG     │  │  Broker) │     │   Storage)    │
└──────────┘  └──────────┘     └──────────────┘
```

### Key Technical Decisions
| Decision | Rationale |
|----------|-----------|
| **Celery + Redis** (not FastAPI BackgroundTasks) | LLM calls take 30-120s; Celery runs in separate process, never blocks API |
| **Single HTML bundle** per game | One file in MinIO = one HTTP request. Inlines CDN scripts, assets as data URIs |
| **MinIO** (not local files) | S3-compatible Docker container; swap endpoint to migrate to AWS S3 in production |
| **SQLite → PostgreSQL** | Same SQLAlchemy ORM; change `DATABASE_URL` to switch |
| **Adapter pattern** for LLMs | `LLM_PROVIDER=claude\|openai` env var switches the AI backend; add new models by implementing `LLMAdapter` ABC |
| **Polling** (not WebSocket) for task progress | TanStack Query `refetchInterval: 2000` = one line; upgrade to WebSocket is a single route change |

---

## 🚀 Quick Start

### Prerequisites
- **Docker Desktop** (for MinIO + Redis)
- **Python 3.11+**
- **Node.js 20+**

### 1. Clone & Setup
```bash
git clone <repo-url>
cd ai-game-platform

# Copy environment config
cp .env.example .env
# Edit .env to add LLM_API_KEY if you want AI generation
```

### 2. Start Infrastructure
```bash
docker compose up -d
# Starts: MinIO (port 9000,9001) + Redis (port 6380)
```

### 3. Install Dependencies
```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### 4. Seed Example Games
```bash
cd ..
python seed/seed.py
# Creates test user + 3 playable example games
```

### 5. Start Development Servers
```bash
# Terminal 1 — Backend
cd backend
uvicorn app.main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm run dev
```

### 6. Open the App
- **Frontend**: http://localhost:5173
- **Backend API Docs**: http://localhost:8000/docs
- **MinIO Console**: http://localhost:9001 (minioadmin / minioadmin)

### Test Account
```
Email:    demo@aigame.dev
Password: demo123
```

---

## 🔌 Enabling AI Game Generation

### Supported LLM Providers

| Provider | Setup | Vision | Best for |
|----------|-------|--------|----------|
| **DeepSeek** | `LLM_PROVIDER=deepseek` | ❌ text-only | 性价比最高，中文友好，生成质量好 |
| **Claude** | `LLM_PROVIDER=claude` | ✅ | 代码生成质量最佳，支持图片素材描述 |
| **OpenAI** | `LLM_PROVIDER=openai` | ✅ (GPT-4o) | 通用能力强，生态完善 |
| **自定义** | `LLM_PROVIDER=openai` + `LLM_API_BASE_URL` | 取决于模型 | 任何 OpenAI 兼容 API |

### Quick Setup — DeepSeek (推荐)
```bash
# 1. 获取 API Key: https://platform.deepseek.com
# 2. 编辑 .env:
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-your-deepseek-key
LLM_MODEL=deepseek-chat       # 或 deepseek-reasoner
```

### Quick Setup — Claude / OpenAI
```bash
LLM_PROVIDER=claude            # 或 "openai"
LLM_API_KEY=sk-ant-...         # 你的 API key
LLM_MODEL=claude-sonnet-4-20250514
```

### Quick Setup — Custom OpenAI-Compatible API
```bash
LLM_PROVIDER=openai
LLM_API_KEY=your-key
LLM_MODEL=your-model-name
LLM_API_BASE_URL=https://your-custom-endpoint.com/v1
```

### Start Generation Worker
```bash
# Terminal 3 — Celery Worker
cd backend
celery -A app.celery_app worker --loglevel=info --pool=solo
```

4. Go to **Create** page, write a prompt like:
> "Create a space shooter where the player controls a ship at the bottom of the screen, shooting asteroids that fall from above. Include power-ups, a score system, and increasing difficulty."

5. Click **Generate Game with AI** — the Agent Harness will:
   - Process any uploaded assets through Vision API
   - Build a system prompt with game constraints
   - Call the LLM to generate a complete HTML5 game
   - Validate the output (parseable HTML, game loop present, no `eval()`)
   - Auto-fix on validation failure
   - Package & upload to MinIO
   - Set game status to "published"

---

## 📁 Project Structure

```
ai-game-platform/
├── README.md
├── docker-compose.yml          # MinIO + Redis
├── .env / .env.example         # Configuration
│
├── backend/                    # FastAPI (Python)
│   ├── app/
│   │   ├── main.py             # App entry, CORS, lifespan
│   │   ├── config.py           # Pydantic Settings (env vars)
│   │   ├── database.py         # Async SQLAlchemy
│   │   ├── models/             # User, Game, GameAsset, GenerationTask
│   │   ├── schemas/            # Pydantic request/response models
│   │   ├── api/                # Auth, Games, Tasks routes
│   │   ├── services/           # Business logic layer
│   │   ├── agent/              # *** AI Agent Harness ***
│   │   │   ├── harness.py      # Pipeline orchestrator
│   │   │   ├── prompts.py      # Game generation system prompts
│   │   │   ├── adapters/       # LLM provider adapters
│   │   │   ├── generators/     # Game code generators
│   │   │   └── processors/     # Validator + Packager
│   │   ├── tasks/              # Celery task definitions
│   │   └── utils/              # Security, MinIO client
│   └── requirements.txt
│
├── frontend/                   # React + Vite (TypeScript)
│   ├── src/
│   │   ├── App.tsx             # Routes
│   │   ├── pages/              # Home, Login, Register, Create, Play
│   │   ├── components/         # UI primitives + feature components
│   │   ├── hooks/              # useAuth, useGames, useTaskPolling
│   │   ├── lib/                # api-client, auth-store, utils
│   │   └── types/              # TypeScript interfaces
│   └── package.json
│
└── seed/                       # Seed data
    ├── seed.py                 # Populates DB + MinIO
    └── games/                  # Pre-built HTML5 games
        ├── snake.html
        ├── memory.html
        └── breakout.html
```

---

## 🔧 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///...` | SQLite dev / PostgreSQL prod |
| `REDIS_URL` | `redis://localhost:6380/0` | Celery broker |
| `MINIO_ENDPOINT` | `localhost:9000` | S3-compatible storage |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO credential |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO credential |
| `MINIO_BUCKET` | `ai-game-platform` | Bucket name |
| `JWT_SECRET` | (change in production) | JWT signing key |
| `LLM_PROVIDER` | `none` | `claude` \| `openai` \| `none` |
| `LLM_API_KEY` | — | Your LLM API key |
| `LLM_MODEL` | `claude-sonnet-4-20250514` | Model to use |

---

## 📊 Database Schema

| Table | Key Columns |
|-------|------------|
| **users** | id, username, email, password_hash, role |
| **games** | id, title, description, cover_image_url, game_url, author_id, tags, status, prompt_text, play_count |
| **game_assets** | id, game_id, asset_type, oss_key, oss_url |
| **generation_tasks** | id, game_id, user_id, status, progress, llm_response_raw, result_oss_url |

---

## 🔄 API Overview

Full interactive docs at `http://localhost:8000/docs` (auto-generated OpenAPI).

### Auth
- `POST /api/auth/register` — Create account
- `POST /api/auth/login` — Sign in
- `GET /api/auth/me` — Current user

### Games
- `GET /api/games` — List published games (paginated, filterable)
- `GET /api/games/{id}` — Game detail with assets
- `POST /api/games` — Create draft `[Auth]`
- `PUT /api/games/{id}` — Update metadata `[Auth]`
- `DELETE /api/games/{id}` — Delete game `[Auth]`

### Assets
- `POST /api/games/{id}/assets` — Upload to MinIO `[Auth]`
- `GET /api/games/{id}/assets` — List assets
- `DELETE /api/games/{id}/assets/{id}` — Remove asset `[Auth]`

### Generation
- `POST /api/games/{id}/generate` — Start AI generation `[Auth]`
- `GET /api/tasks/{id}` — Poll generation status
- `GET /api/tasks/games/{id}` — Task history

---

## 🧠 AI Agent Harness — Extensibility

The agent system uses an **adapter pattern** for pluggable LLM backends:

```python
# To add a new LLM provider:
# 1. Implement LLMAdapter in agent/adapters/
class MyAdapter(LLMAdapter):
    async def generate(self, system_prompt, user_prompt, **kwargs) -> str: ...
    async def generate_stream(self, ...) -> AsyncIterator[str]: ...
    async def describe_image(self, image_url) -> str: ...

# 2. Register in agent/adapters/__init__.py factory
# 3. Set LLM_PROVIDER=myprovider in .env
```

The pipeline (`harness.py`) is LLM-agnostic:
```
User Prompt → Preprocess Assets → Build Context → LLM Generate →
→ Validate (HTML parse, game loop, security) → Auto-fix → Package → Upload MinIO
```

---

## 🛡️ Security Considerations

- Generated games run in `<iframe sandbox="allow-scripts allow-same-origin">`
- Validator blocks `eval()` usage in generated code
- External script sources restricted to approved CDNs
- JWT-based authentication with bcrypt password hashing
- MinIO bucket policy: public-read on `games/*`, write requires server credential

---

## 🚧 Production Migration Path

1. **Database**: Change `DATABASE_URL` to `postgresql+asyncpg://...`
2. **Storage**: Change `MINIO_ENDPOINT` to AWS S3 endpoint
3. **Secrets**: Set `JWT_SECRET` to a random 64-char string
4. **LLM**: Set `LLM_PROVIDER` + `LLM_API_KEY` to production keys
5. **Deployment**: Frontend → Vercel/Cloudflare Pages; Backend → Fly.io/Railway; Celery Worker → separate instance
