# ============================================================
# 根目录 Dockerfile — 生产环境多阶段构建
# 目标：单容器运行 FastAPI + 内嵌前端静态文件
# 部署平台：Railway（通过 railway.json 指定 DOCKERFILE builder）
# ============================================================

# ════════════════════════════════════════════════════════════
# 阶段 1：前端构建（frontend-build）
# ════════════════════════════════════════════════════════════
# 【为什么用多阶段构建？为什么把前端构建放在阶段 1？】
#   传统做法：分别构建前后端镜像，用 nginx 反向代理
#   本项目做法：前端编译为纯静态文件（dist/），由 FastAPI 直接服务
#   优势：
#     1. 单容器部署 — 无需 nginx 容器或 CDN，减少服务数量和成本
#     2. 原子发布 — 前后端一次构建、一起发布，无版本不匹配风险
#     3. 最终镜像不含 Node.js — 阶段 1 的 node_modules 等构建依赖
#        不进入阶段 2，镜像体积大幅减小
#     4. COPY --from 仅提取构建产物（dist/），不携带源码和依赖
#
#   多阶段构建的生命周期：
#     阶段 1 (frontend-build): npm ci → npm run build → 产生 dist/
#     阶段 2 (最终镜像):      只 COPY --from=frontend-build dist/
#     阶段 1 的镜像层在构建完成后被丢弃，最终镜像只包含阶段 2
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend

# 先复制 package.json + lock 文件，利用 Docker 层缓存
# 原理：package.json 不变时，npm ci 层可复用缓存，加速重复构建
COPY frontend/package.json frontend/package-lock.json ./

# 【npm ci vs npm install 的区别】
#   npm ci (clean install):
#     - 严格依据 package-lock.json 安装，版本完全锁定
#     - 先删除 node_modules 再安装（如果有的话），保证洁净
#     - 速度更快（跳过依赖树解析，直接按 lock 文件安装）
#     - 适用于 CI/CD 和生产构建：可复现、可靠
#   npm install:
#     - 可能更新 package-lock.json（版本范围 ^1.0.0 可能装到 1.9.0）
#     - 不删除已有 node_modules，可能留下旧版本残留
#     - 适用于本地开发：灵活、交互式
#   总结：Dockerfile / CI 中必须使用 npm ci，确保构建幂等性
RUN npm ci

# 复制前端所有源码（package.json 变化后这层才会重建）
COPY frontend/ ./

# Vite build 生成 dist/ 目录，包含 index.html + 压缩后的 JS/CSS
RUN npm run build

# ════════════════════════════════════════════════════════════
# 阶段 2：最终运行镜像
# ════════════════════════════════════════════════════════════
# 【为什么用 python:3.11-slim 而不是 python:3.11-alpine？】
#   python:3.11-slim:
#     - 基于 Debian，使用 glibc（GNU C 库）
#     - 二进制兼容性好：pip 安装的预编译 wheel 直接可用
#     - 镜像约 150MB（含 Python）
#   python:3.11-alpine:
#     - 基于 Alpine Linux，使用 musl libc（轻量 C 库）
#     - 镜像更小（约 50MB），但 musl 与 glibc 不完全兼容
#     - 许多 Python 包的预编译 wheel 是针对 glibc 的，
#       在 Alpine 上需要从源码编译，增加构建时间和失败风险
#     - numpy、pandas 等科学计算包在 Alpine 上尤其容易出问题
#   结论：slim 版本在体积和兼容性之间取得最佳平衡，
#   本项目的依赖（boto3、SQLAlchemy、celery）在 slim 上开箱即用
FROM python:3.11-slim
WORKDIR /app

# 安装系统依赖 curl（用于 healthcheck 和 MinIO 健康检查）
# --no-install-recommends: 不安装推荐的额外包，减小镜像体积
# 清理 apt 缓存：rm -rf /var/lib/apt/lists/* 减少层大小
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# 先复制 requirements.txt（利用缓存层），再安装 Python 依赖
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY backend/ ./
# 复制种子脚本（用于容器启动时自动注入测试数据）
COPY seed/ ./seed/

# 【COPY --from 语法】
#   COPY --from=frontend-build /app/frontend/dist ./frontend/dist
#   从构建阶段 "frontend-build" 中提取文件，而不是从构建上下文
#   这样只有最终产物（编译后的 HTML/JS/CSS）进入阶段 2，
#   而阶段 1 中的所有构建依赖（node_modules、源码等）被丢弃
#   效果：最终镜像比分别构建前后端镜像合并节省了 ~500MB+
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

EXPOSE 8000

# 【CMD shell 形式 vs exec 形式】
#   Shell 形式 (当前使用):
#     CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
#     命令在 /bin/sh -c 中执行，支持 shell 特性：
#       - 变量替换：${PORT:-8000} 使用 shell 参数扩展
#       - 管道、重定向等 shell 语法
#     Railway 通过环境变量 $PORT 动态分配端口，
#     shell 形式可以在容器启动时展开该变量
#     如果写成 exec 形式 CMD ["uvicorn", ..., "--port", "${PORT:-8000}"]
#     则 ${PORT:-8000} 不会被 shell 展开，而是作为字面字符串传递
#
#   Exec 形式 (未使用):
#     CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
#     直接由内核 exec，不经过 shell
#     优势：PID 1 是 uvicorn 本身（信号处理正确），无 shell 进程
#     劣势：不支持 shell 变量展开
#     适合端口固定、不需要 shell 特性的场景
#
#   本项目用 shell 形式的原因：Railway 动态分配 $PORT 端口
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
