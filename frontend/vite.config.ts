// ============================================================
// Vite 构建工具配置文件
// ============================================================
// Vite 是下一代前端构建工具（由 Vue.js 作者 Evan You 开发）
// 特点：基于 ESBuild 的极速 HMR、原生 ESM、开箱即用 TypeScript
//
// 本文件配置三个核心方面：
//   1. React 插件（JSX 转换 + Fast Refresh）
//   2. 路径别名（@ → src/）
//   3. 开发代理（Vite proxy：/api → 后端服务器）
//
// 为什么选择 Vite 而不是 Create React App (CRA) / Webpack？
//   - CRA 已停止维护，Vite 是社区推荐替代方案
//   - Webpack 配置复杂，Vite 零配置即可使用
//   - Vite 开发服务器启动 < 1s（ESBuild），CRA/Webpack > 10s
// ============================================================

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  // ---- 插件 ----
  plugins: [react()],
  // @vitejs/plugin-react:
  //   - 使用 esbuild 进行 JSX 转换（比 Babel 快 10-100 倍）
  //   - 支持 React Fast Refresh（保留组件状态的 HMR 热更新）

  // ---- 模块解析 ----
  resolve: {
    alias: {
      // 【路径别名：@ → src/】
      // 好处：
      //   import { Button } from "@/components/ui/button"
      //   代替：
      //   import { Button } from "../../../components/ui/button"
      //
      //   - 消除深层相对路径导入（../../.. 噩梦）
      //   - 重构时无需修改每个文件的导入路径
      //   - IDE 自动补全和 Ctrl+Click 跳转仍然正常工作
      //     （因为 TypeScript tsconfig.json 中也有对应的 paths 配置）
      //   - 约定俗成：@ 代表 src/（Vue 社区习惯，React 项目也广泛使用）
      //
      // 注意：需要在 tsconfig.json 中同步配置：
      //   "compilerOptions": {
      //     "paths": { "@/*": ["./src/*"] }
      //   }
      // 否则 TypeScript 编译器无法解析 @ 别名
      "@": path.resolve(__dirname, "./src"),
    },
  },

  // ---- 开发服务器 ----
  server: {
    port: 5173,
    // Vite 默认端口，如果被占用会自动尝试 5174、5175...

    proxy: {
      // 【Vite Proxy（开发代理）详解】
      // 作用：将特定路径的请求转发到另一个服务器
      //
      // 为什么需要 Proxy？
      //   开发环境下，前端运行在 localhost:5173（Vite dev server）
      //   后端运行在 localhost:8000（uvicorn），这是跨域访问
      //
      //   CORS（跨域资源共享）问题：
      //   浏览器会阻止 http://localhost:5173 向 http://localhost:8000
      //   发送请求（不同端口 = 不同源）
      //
      //   解决方案有两种：
      //     方案 A（后端 CORS 头）：FastAPI 设置 allow_origins
      //        优点：简单直接，生产环境也需要
      //        缺点：开发和生产配置可能不一致
      //     方案 B（前端 Proxy）：Vite 开发服务器代为转发（本项目同时使用 A+B）
      //        优点：开发时 API 请求与静态资源同源，无 CORS 问题
      //        缺点：仅开发环境有效，生产环境需 nginx 或后端服务静态文件
      //
      //   工作流程：
      //     浏览器 → GET /api/games → localhost:5173 (Vite)
      //       → Vite 识别到 /api 前缀
      //       → Vite 转发到 http://localhost:8000/api/games
      //       → FastAPI 处理 → 返回 JSON
      //       → Vite 将响应传回浏览器
      //
      //   浏览器视角：请求发到了 localhost:5173/api/games
      //   实际后端：请求到了 localhost:8000/api/games
      //
      //   配置项说明：
      //     target:       代理目标地址（后端 API 服务器）
      //     changeOrigin: true 修改请求头中的 Origin/Host 为目标地址
      //                   后端看到的 Host 是 localhost:8000 而非 localhost:5173
      //                   避免后端某些框架根据 Host 做路由判断时出错
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        //                  环境变量 ↑           默认值 ↑
        // VITE_API_TARGET 可在 .env 文件中设置（如指向远程 API）
        // 例如：VITE_API_TARGET=https://staging.example.com
        changeOrigin: true,
      },
    },
  },
});
