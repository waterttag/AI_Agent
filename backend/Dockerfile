# ============================================================
# 后端本地开发 Dockerfile
# ============================================================
# 用途：docker-compose.yml 中 backend / worker / seed 服务的构建
# 与根目录 Dockerfile（生产构建）的区别：
#   - 不包含前端构建阶段（本地开发用 Vite 独立服务器）
#   - 不包含种子脚本（通过 volume 挂载，而非 COPY）
#   - 使用 exec 形式的 CMD（无 shell 变量展开，端口固定）
#   - 镜像体积更小，适合频繁重构

FROM python:3.11-slim
# 【为什么使用 slim 而非 alpine？】
#   slim (基于 Debian / glibc):
#     - 预编译 Python 包（wheel）直接安装，无需编译
#     - boto3、SQLAlchemy、celery 等依赖开箱即用
#     - 镜像约 150MB，可接受
#   alpine (基于 musl libc):
#     - 更小（约 50MB），但 musl 与 glibc 二进制不兼容
#     - 许多 Python 包需要从源码编译，增加构建时间和失败风险
#     - 对 AI/ML 相关包（numpy、pandas）兼容性尤其差
#   抉择：slim 多 100MB 但零编译风险，开发体验更好

WORKDIR /app

# 安装 curl（用于容器内健康检查和调试）
# 分层复制：先装系统依赖 → 再装 Python 依赖 → 再复制代码
# 这样修改代码时只需重建最后一层，pip install 层从缓存命中
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# 先复制依赖文件 → 安装依赖 → 再复制源码
# Docker 层缓存原理：requirements.txt 不变 → pip install 层复用缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
#  --no-cache-dir: 不缓存下载的 .whl 文件，减小镜像层大小

# 复制所有后端源码（.py 文件、migrations、app 目录等）
COPY . .

EXPOSE 8000

# 【CMD exec 形式 vs shell 形式】
#   本地开发使用 exec 形式（JSON 数组格式）:
#     CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
#   优点：
#     - uvicorn 作为 PID 1 运行，可以直接接收 SIGTERM 信号
#       （docker stop 发送的优雅关闭信号）
#     - 没有额外 sh 进程，进程树更简洁
#     - 参数明确，不会因空格/引号导致解析错误
#   不需要 shell 形式的原因：
#     - 端口固定为 8000，无需 ${PORT:-8000} 变量展开
#     - docker-compose.yml 中指定端口映射 8000:8000
#   对比：根目录生产 Dockerfile 用 shell 形式是为了
#   Railway 的 $PORT 动态端口展开
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
