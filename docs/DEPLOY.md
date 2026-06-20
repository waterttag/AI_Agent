# 部署指南 — AI Game Forge

## 推荐方案：Render (后端) + Vercel (前端) + Cloudflare R2 (对象存储)

全免费额度，无需信用卡即可开始。

---

## 第一步：准备对象存储 (Cloudflare R2)

1. 打开 https://dash.cloudflare.com → 注册/登录
2. 左侧菜单 → **R2** → **Create bucket**
   - Bucket name: `ai-game-platform`
3. 进入 bucket → **Settings** → **Public access** → 允许 `public read`
4. 创建 API Token：右侧 **Manage R2 API Tokens** → **Create API Token**
   - Permission: `Object Read & Write`
   - 记下: **Access Key ID** 和 **Secret Access Key**
   - Endpoint: `https://<account-id>.r2.cloudflarestorage.com`

---

## 第二步：部署后端 (Render)

1. 打开 https://render.com → 注册/登录 (用 GitHub)
2. **New** → **Web Service** → 连接你的 GitHub 仓库
3. 配置：
   ```
   Name: aigame-backend
   Root Directory: backend
   Runtime: Python 3
   Build Command: pip install -r requirements.txt
   Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
4. 添加以下环境变量：

| Key | Value |
|-----|-------|
| `DATABASE_URL` | (Render 会自动生成——创建 PostgreSQL 后填入) |
| `REDIS_URL` | (Render 会自动生成——创建 Redis 后填入) |
| `MINIO_ENDPOINT` | `<account-id>.r2.cloudflarestorage.com` |
| `MINIO_ACCESS_KEY` | R2 Access Key ID |
| `MINIO_SECRET_KEY` | R2 Secret Access Key |
| `MINIO_BUCKET` | `ai-game-platform` |
| `MINIO_SECURE` | `true` |
| `JWT_SECRET` | 随机生成 64 字符 |
| `JWT_ALGORITHM` | `HS256` |
| `LLM_PROVIDER` | `deepseek` |
| `LLM_API_KEY` | `sk-d9210e9d...` (你的 Key) |
| `LLM_MODEL` | `deepseek-chat` |
| `CORS_ORIGINS` | `["http://localhost:5173","https://YOUR_VERCEL_APP.vercel.app"]` |

5. 创建关联服务：
   - **New** → **PostgreSQL** → `aigame-db` (会生成 `DATABASE_URL`)
   - **New** → **Redis** → `aigame-redis` (会生成 `REDIS_URL`)
   - 把生成的两个 URL 填入上面的环境变量

6. **New** → **Background Worker** (同样的代码，单独的 Worker 进程)
   ```
   Name: aigame-worker
   Root Directory: backend
   Build Command: pip install -r requirements.txt
   Start Command: celery -A app.celery_app worker --loglevel=info --pool=solo
   ```
   环境变量与 Web Service 完全相同。

7. **Create Web Service** → Render 自动构建+部署
   - 部署完成后，记下 URL: `https://aigame-backend.onrender.com`

---

## 第三步：部署前端 (Vercel)

1. 打开 https://vercel.com → 注册/登录 (用 GitHub)
2. **Add New** → **Project** → 导入你的 GitHub 仓库
3. 配置：
   ```
   Root Directory: frontend
   Build Command: npm run build
   Output Directory: dist
   Framework Preset: Vite
   ```
4. 环境变量：

| Key | Value |
|-----|-------|
| `VITE_API_URL` | `https://aigame-backend.onrender.com` |

5. **Deploy** → 等待完成
   - 记下 URL: `https://your-app.vercel.app`

---

## 第四步：更新 CORS 和 Worker

1. 回到 Render → aigame-backend → Environment
   - 更新 `CORS_ORIGINS` 加上你的 Vercel 域名：
     ```
     ["http://localhost:5173","https://YOUR_VERCEL_APP.vercel.app"]
     ```
   - 点 **Save** → Render 自动重启

2. 回到 Render → aigame-worker → Environment
   - 确保 `LLM_PROVIDER`、`LLM_API_KEY` 已设置
   - 确保 `MINIO_*` 变量与 backend 一致

---

## 第五步：运行种子数据

在 Render 的 aigame-backend 服务中：
1. 点击 **Shell** 标签
2. 运行：
   ```bash
   cd /opt/render/project/src/backend
   export DATABASE_URL=<你的PostgreSQL URL>
   export MINIO_ENDPOINT=<你的R2 endpoint>
   export MINIO_ACCESS_KEY=<...>
   export MINIO_SECRET_KEY=<...>
   export MINIO_BUCKET=ai-game-platform
   export MINIO_SECURE=true
   python /opt/render/project/src/seed/seed.py
   ```

**但是** seed 脚本依赖 `backend/app/` 路径，在 Render 上路径不同。更好的办法是：

在 Render Shell 中：
```bash
python -c "
import sys; sys.path.insert(0, '/opt/render/project/src/backend')
sys.path.insert(0, '/opt/render/project/src')
import asyncio
from seed.seed import main
asyncio.run(main())
"
```

或者更简单——直接在 Render 上通过 API 注册+创建游戏。

---

## 第六步：验证

1. 打开 `https://YOUR_VERCEL_APP.vercel.app`
2. 能看到种子游戏卡片
3. 注册账号 → Create → 输入 Prompt → DeepSeek 生成 → Play

---

## 本地开发 vs 生产对照

| 组件 | 本地开发 | 生产 (Render + Vercel) |
|------|---------|----------------------|
| 前端 | `localhost:5173` (Vite dev) | Vercel (CDN全球边缘) |
| 后端 | `localhost:8000` (Uvicorn) | Render Web Service |
| Worker | `localhost` (Celery) | Render Background Worker |
| 数据库 | SQLite (本地文件) | PostgreSQL (Render managed) |
| 缓存 | Redis Docker | Redis (Render managed) |
| 对象存储 | MinIO Docker | Cloudflare R2 (S3兼容) |
| 密钥管理 | `.env` 文件 | Render Environment Variables |

---

## 一键 Docker Compose 部署 (备选)

如果你有一台 Linux VPS (AWS EC2 / 阿里云 ECS / 腾讯云 CVM)：

```bash
# 在 VPS 上:
git clone <your-repo>
cd ai-game-platform

# 创建 .env 填入真实值
cp .env.example .env
nano .env   # 编辑 LLM_API_KEY 等

# 启动全部服务
docker compose up -d

# 运行种子数据
docker compose run seed
```

访问 `http://<VPS-IP>:5173`
