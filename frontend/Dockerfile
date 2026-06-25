# ============================================================
# 前端本地开发 Dockerfile
# ============================================================
# 用途：docker-compose.yml 中 frontend 服务的构建
# 运行 Vite 开发服务器（HMR 热更新），不构建生产产物
# 与根目录 Dockerfile 阶段 1（frontend-build）的区别：
#   - 开发模式：npm run dev，带 HMR 热更新
#   - 生产模式：npm run build，产出 dist/ 静态文件
#   - 此 Dockerfile 不设置 AS 别名（不作为多阶段构建的一部分）

FROM node:20-alpine
# 使用 node:20-alpine（基于 Alpine Linux + musl libc）
# 【为什么前端可以用 alpine？】
#   Node.js 官方 alpine 镜像工作良好，与 glibc 差异无关
#   npm 包是纯 JavaScript，不涉及 C 扩展编译
#   镜像仅约 130MB（node:20-slim 约 250MB）
#   体积优势明显，且不影响功能

WORKDIR /app

# 分层复制：先 package.json → npm ci → 再源码
# 原理与 backend Dockerfile 一致：利用 Docker 层缓存加速重建
COPY package.json package-lock.json ./
RUN npm ci
# 【为什么用 npm ci 而非 npm install？】
#   npm ci:
#     - 严格按 lock 文件安装，版本 100% 可控
#     - 自动删除旧 node_modules，保证洁净
#     - 跳过依赖树解析，速度更快
#     - 适用于所有自动化场景（CI/CD/Docker）
#   npm install:
#     - 可能修改 lock 文件（版本漂移）
#     - 不保证幂等性
#   结论：Dockerfile 中 npm ci 是唯一正确选择

COPY . .
# 复制所有源码（src/、vite.config.ts、tailwind.config.ts、tsconfig.json 等）

EXPOSE 5173
# Vite 开发服务器默认端口

# CMD exec 形式，启动 Vite 开发服务器
# --host 0.0.0.0: 监听所有网络接口，否则 Docker 端口映射无法访问
#   （Vite 默认只监听 localhost，容器外无法访问）
# 返回的命令行实际执行：npm run dev -- --host 0.0.0.0
#   -- 告诉 npm 后面的参数传给 dev 脚本而非 npm 本身
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
