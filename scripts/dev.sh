#!/bin/bash
# ============================================
# AI Game Forge — Development Quick Start
# ============================================
set -e

echo "=== AI Game Forge — Starting Development Environment ==="

# 1. Check prerequisites
echo "[1/5] Checking prerequisites..."
command -v docker >/dev/null 2>&1 || { echo "ERROR: Docker is required. Install Docker Desktop."; exit 1; }
command -v python >/dev/null 2>&1 || { echo "ERROR: Python 3.11+ is required."; exit 1; }
command -v node >/dev/null 2>&1 || { echo "ERROR: Node.js 20+ is required."; exit 1; }
echo "  Docker, Python, Node.js — OK"

# 2. Start infrastructure
echo "[2/5] Starting Docker services (MinIO + Redis)..."
docker compose up -d
echo "  MinIO: http://localhost:9000 (API), http://localhost:9001 (Console)"
echo "  Redis: localhost:6380"

# 3. Install dependencies
echo "[3/5] Installing dependencies..."
cd backend
pip install -r requirements.txt -q
cd ../frontend
npm install --silent 2>/dev/null
cd ..
echo "  Backend + Frontend deps — OK"

# 4. Seed data
echo "[4/5] Seeding example games..."
python seed/seed.py
echo "  Login: demo@aigame.dev / demo123"

# 5. Launch
echo "[5/5] Starting servers..."
echo ""
echo "  Backend:  cd backend && uvicorn app.main:app --reload --port 8000"
echo "  Workers:  cd backend && celery -A app.celery_app worker --loglevel=info --pool=solo"
echo "  Frontend: cd frontend && npm run dev"
echo ""
echo "  Open http://localhost:5173 in your browser."
echo ""
echo "=== Ready! ==="
