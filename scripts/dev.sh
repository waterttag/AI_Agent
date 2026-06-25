#!/bin/bash
# ============================================================
# AI Game Forge — 开发环境一键启动脚本
# ============================================================
# 功能：从零搭建完整开发环境，分 5 步执行
#   1. 检查前置依赖（Docker、Python、Node.js）
#   2. 启动 Docker 基础设施（MinIO + Redis）
#   3. 安装前后端依赖
#   4. 运行种子数据脚本（注入示例游戏 + 测试用户）
#   5. 输出启动命令提示
#
# 使用方式：
#   chmod +x scripts/dev.sh
#   ./scripts/dev.sh
#
# 【为什么用 bash 脚本而不是 Makefile / Task？】
#   - 零依赖：bash 在任何 Unix 系统上预装
#   - 清晰可读：顺序执行，每步有输出，出错有提示
#   - 适合 AI 辅助：AI 可以轻松理解和修改此脚本
# ============================================================

# 【set -e 详解】
#   set -e: 任何命令返回非零退出码时立即终止脚本
#   例如：如果 docker compose up 失败，不会继续执行后续步骤
#   这避免了"在基础设施未就绪时安装依赖"等无意义操作
#   注意：管道中的最后一个命令决定退出码，中间命令失败可能被忽略
#         需要完整管道控制时使用 set -o pipefail
set -e

echo "=== AI Game Forge — Starting Development Environment ==="

# ════════════════════════════════════════════════════════════
# 步骤 1: 检查前置依赖
# ════════════════════════════════════════════════════════════
# command -v 比 which 更可移植（内建于 POSIX sh）
# >/dev/null 2>&1: 重定向 stdout 和 stderr 到 /dev/null（静默检查）
# || 短路求值：command 失败时才执行 echo 和 exit
echo "[1/5] Checking prerequisites..."
command -v docker >/dev/null 2>&1 || { echo "ERROR: Docker is required. Install Docker Desktop."; exit 1; }
command -v python >/dev/null 2>&1 || { echo "ERROR: Python 3.11+ is required."; exit 1; }
command -v node >/dev/null 2>&1 || { echo "ERROR: Node.js 20+ is required."; exit 1; }
echo "  Docker, Python, Node.js — OK"

# ════════════════════════════════════════════════════════════
# 步骤 2: 启动 Docker 基础设施
# ════════════════════════════════════════════════════════════
# docker compose up -d: 后台启动所有服务
#   - redis:    消息队列（Celery broker）
#   - minio:    对象存储（S3 兼容）
#   - backend:  FastAPI 服务器（但本地开发通常手动启动）
#   - frontend: Vite 开发服务器（但本地开发通常手动启动）
#   - worker:   Celery worker（但本地开发通常手动启动）
#   注意：seed 服务不在 docker compose up 中自动运行，
#         因为此时 MinIO 可能还未完全就绪
#         改为步骤 4 中本地显式执行
echo "[2/5] Starting Docker services (MinIO + Redis)..."
docker compose up -d
echo "  MinIO: http://localhost:9000 (API), http://localhost:9001 (Console)"
echo "  Redis: localhost:6380"

# ════════════════════════════════════════════════════════════
# 步骤 3: 安装前后端依赖
# ════════════════════════════════════════════════════════════
# pip install -q: 安静模式，减少输出噪音
# npm install --silent: 隐藏 npm 的 WARN 信息
#   注意：本地开发使用 npm install（非 npm ci）
#   因为 package-lock.json 可能需要在开发中更新
echo "[3/5] Installing dependencies..."
cd backend
pip install -r requirements.txt -q
cd ../frontend
npm install --silent 2>/dev/null
cd ..
echo "  Backend + Frontend deps — OK"

# ════════════════════════════════════════════════════════════
# 步骤 4: 种子数据
# ════════════════════════════════════════════════════════════
# 本地运行种子脚本（而非 Docker 容器内）
# 种子脚本自动检测路径（通过 /app/app 是否存在判断环境）
# 注入 3 款示例游戏（Snake、Memory Match、Breakout）+ 测试用户
echo "[4/5] Seeding example games..."
python seed/seed.py
echo "  Login: demo@aigame.dev / demo123"

# ════════════════════════════════════════════════════════════
# 步骤 5: 输出启动命令（手动启动）
# ════════════════════════════════════════════════════════════
# 本地开发推荐手动分别启动各服务，方便查看实时日志：
#   - 终端 1: cd backend && uvicorn app.main:app --reload --port 8000
#   - 终端 2: cd backend && celery -A app.celery_app worker --loglevel=info --pool=solo
#   - 终端 3: cd frontend && npm run dev
#
# 也可以使用 Docker 版本（docker compose up 已启动但建议停止用本地）：
#   docker compose stop backend worker frontend
echo "[5/5] Starting servers..."
echo ""
echo "  Backend:  cd backend && uvicorn app.main:app --reload --port 8000"
echo "  Workers:  cd backend && celery -A app.celery_app worker --loglevel=info --pool=solo"
echo "  Frontend: cd frontend && npm run dev"
echo ""
echo "  Open http://localhost:5173 in your browser."
echo ""
echo "=== Ready! ==="
