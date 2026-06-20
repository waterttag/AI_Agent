# 部署指南 — AI Game Forge

## 当前生产部署: Railway

**Demo**: https://aiagent-production-5b68.up.railway.app  
**对象存储**: 阿里云 OSS（`oss-cn-hangzhou.aliyuncs.com`，bucket: `agent-nju`）

---

## 对象存储配置

系统使用 boto3 S3 客户端，兼容以下存储服务：

| 服务 | Endpoint 格式 | 推荐 |
|------|--------------|:---:|
| **阿里云 OSS** | `oss-cn-hangzhou.aliyuncs.com` | ✅ 当前使用 |
| **AWS S3** | `s3.amazonaws.com` | ✅ |
| **Cloudflare R2** | `<id>.r2.cloudflarestorage.com` | ✅ 免费 |
| **MinIO** | `localhost:9000` | ✅ 本地开发 |

### 配置环境变量

无论用哪个服务，只需改 5 个变量（系统自动适配 virtual-hosted / path 风格）：

| Key | Value 示例 |
|-----|-----------|
| `MINIO_ENDPOINT` | `oss-cn-hangzhou.aliyuncs.com` |
| `MINIO_ACCESS_KEY` | `LTAI5t7xxxxxx` |
| `MINIO_SECRET_KEY` | `xxxxxx` |
| `MINIO_BUCKET` | `agent-nju` |
| `MINIO_SECURE` | `true`（HTTPS）或 `false`（HTTP） |

### 创建 OSS Bucket (阿里云)

1. 打开 https://oss.console.aliyun.com
2. **Bucket 列表** → **创建 Bucket**
3. Bucket 名称 + 地域选择 + **读写权限：公共读**
4. 右上角头像 → **AccessKey 管理** → 获取 Key

### 创建 R2 Bucket (Cloudflare，免费)

1. 打开 https://dash.cloudflare.com → R2 → Create bucket
2. Bucket name: `ai-game-platform`
3. Settings → Public Access → 开启
4. R2 API Tokens → Object Read & Write → 获取 Key

### 创建 S3 Bucket (AWS)

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

## 第五步：种子数据（自动）

后端启动时自动检测——如果数据库中没有游戏，会自动创建 demo 账号并注入 3 款种子游戏。**无需手动操作。**

如需重新种子数据，调用 API：
```bash
# 注册 demo 用户
curl -X POST https://YOUR_URL/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"democreator","email":"demo@aigame.dev","password":"demo123"}'

# 注入种子游戏
curl -X POST https://YOUR_URL/api/admin/inject-game \
  -H "Content-Type: application/json" \
  -d '{"title":"Classic Snake","description":"...","tags":["arcade","classic","snake"],"html_content":"<!DOCTYPE html>...","author_username":"democreator"}'
```

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
