/**
 * main.tsx — 应用入口文件（Entry Point）
 * ------------------------------------------------------------------
 * 职责：初始化 React 应用，挂载全局 Provider 层，并注入根组件 <App />。
 *
 * 整个应用的启动流程：
 *   1. 创建 QueryClient（TanStack Query 的全局缓存管理器）
 *   2. 调用 ReactDOM.createRoot 挂载到 DOM 节点 #root
 *   3. 按"从外到内"的顺序包裹 Provider：
 *      StrictMode → QueryClientProvider → BrowserRouter → App
 *
 * Provider 包裹顺序说明：
 *   - StrictMode 在最外层，确保所有子组件在开发模式下都受严格检查
 *   - QueryClientProvider 必须在 BrowserRouter 外层，因为路由页面可能需要
 *     使用 react-query 的 hooks（如 useQuery），而这些 hooks 依赖
 *     QueryClient 上下文
 *   - BrowserRouter 包裹 App，使整个应用都能使用 React Router
 */

import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./index.css";

// ---------------------------------------------------------------------------
// QueryClient — TanStack Query 的全局配置
// ---------------------------------------------------------------------------
// QueryClient 是 TanStack Query（原 React Query v4+）的核心对象，负责：
//   - 缓存所有查询结果（内存缓存）
//   - 管理请求的 loading / error / success 状态
//   - 自动触发后台重新请求（stale-while-revalidate 策略）
//   - 垃圾回收（GC）：未使用的缓存会在 cacheTime 后自动清理
//
// 为什么放在模块顶层（组件外部）？
//   用 new QueryClient() 创建的实例是普通 JS 对象，不依赖 React 生命周期。
//   放在组件外部可避免每次渲染都重新创建实例（React 组件每次渲染都会
//   重新执行函数体）。如果用 useState 包一层也可以，但放模块顶层更简洁，
//   且 TanStack Query 官方文档也推荐这种方式。
// ---------------------------------------------------------------------------
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // ------------------------------------------------------------------
      // staleTime: 30_000（30 秒）— 数据"保鲜"时间
      // ------------------------------------------------------------------
      // 含义：在 30 秒内，TanStack Query 认为缓存数据仍然是"新鲜的"，
      //       不会触发后台重新请求。
      //
      // 流程（stale-while-revalidate 策略）：
      //   第 1 次访问：缓存为空 → 发起请求 → 数据返回，缓存此时的时间戳
      //   第 2 次访问（10 秒后）：还在 30s 内 → 直接返回缓存，不发请求
      //   第 3 次访问（40 秒后）：超过 30s → 先返回旧缓存（stale data），
      //                          同时后台静默发起新请求，新数据回来后再更新 UI
      //
      // 为什么设为 30 秒？
      //   - 游戏列表/详情数据不需要实时更新（不像股票/聊天）
      //   - 减少不必要的 API 调用，降低服务器压力
      //   - 30 秒是常见的折中值：用户体验不会感到数据陈旧，又不会频繁请求
      //
      // 补充知识：staleTime 默认值是 0
      //   - staleTime=0 意味着每次使用缓存都会立即后台请求最新数据
      //   - 适合对实时性要求极高的场景，但会产生大量请求
      // ------------------------------------------------------------------
      staleTime: 30_000,

      // ------------------------------------------------------------------
      // retry: 1 — 失败重试次数
      // ------------------------------------------------------------------
      // 含义：当查询请求失败（网络错误、5xx 服务器错误等）时，自动重试 1 次。
      //
      // 为什么是 1 而不是更大的数（默认是 3）？
      //   - 重试 3 次在弱网环境下可能导致用户等待过久（每次重试间隔递增）
      //   - 1 次重试可以覆盖瞬时网络抖动（如 WiFi 切换），而不会过度等待
      //   - 如果 2 次请求都失败（1 次原始 + 1 次重试），说明问题不是偶然的，
      //     应该向用户展示错误信息，让其决定下一步操作
      //
      // 重试策略细节（TanStack Query 默认行为）：
      //   - 采用指数退避（exponential backoff）：第 1 次重试延迟约 1s，
      //     第 2 次约 2s，以此类推
      //   - 不会重试 4xx 客户端错误（如 400/401/403/404），因为这表示
      //     请求本身有问题，重试不会改变结果
      //   - 可以通过 retryDelay 自定义退避算法，通过 retryOnMount 控制
      //     组件重新挂载时是否重试
      //
      // 扩展：也可以针对单个查询覆盖此配置
      //   useQuery({ queryKey: [...], queryFn: ..., retry: 3 })
      // ------------------------------------------------------------------
      retry: 1,
    },
  },
});

// ---------------------------------------------------------------------------
// ReactDOM.createRoot — React 18 的 Concurrent Mode 挂载方式
// ---------------------------------------------------------------------------
// createRoot 是 React 18 引入的新 API，替代 React 17 的 ReactDOM.render。
//
// 区别：
//   - createRoot 启用并发特性（Concurrent Features）：自动批处理、Suspense、
//     useTransition、useDeferredValue 等
//   - 旧版 ReactDOM.render 运行在"同步传统模式"，不支持这些特性
//
// 参数 document.getElementById("root")!：
//   - 后面的 ! 是 TypeScript 非空断言操作符
//   - 告诉 TS 编译器："我确定这个元素一定存在，不会是 null"
//   - 因为在 index.html 中一定有 <div id="root"></div>，所以是安全的
// ---------------------------------------------------------------------------
ReactDOM.createRoot(document.getElementById("root")!).render(
  // ------------------------------------------------------------------------
  // <React.StrictMode> — 开发模式下的严格检查容器
  // ------------------------------------------------------------------------
  // StrictMode 是 React 提供的开发工具组件，不会渲染任何可见 UI，
  // 也不影响生产构建（生产环境下 StrictMode 不执行任何检查）。
  //
  // 主要功能：
  //   1. 双重渲染（Double Rendering）
  //      在开发模式下，StrictMode 会让组件渲染两次（仅函数体，不含 effect），
  //      目的是检测"非纯函数"副作用。纯函数要求相同的 props 和 state 必定
  //      得到相同的输出，但实践中可能有人在 render 中不小心写了副作用
  //      （如修改全局变量、直接调用 API），双重渲染会让这些 bug 暴露。
  //
  //      注意：useEffect 不会执行两次，只是组件的 render 函数体会。
  //      这也是为什么在开发时偶尔看到 console.log 打印了两次。
  //
  //   2. 检测过时的 API
  //      如已废弃的 componentWillMount、componentWillUpdate 等生命周期
  //
  //   3. 检测意外的副作用
  //      如 useEffect 没有正确清理（cleanup），导致内存泄漏
  //
  // 为什么生产环境不用关心？
  //   StrictMode 的所有检查都是纯开发时行为，打包后会被 tree-shaking 移除，
  //   对生产环境的性能和包体积没有任何影响。
  // ------------------------------------------------------------------------
  <React.StrictMode>
    {/* ------------------------------------------------------------------ */}
    {/* QueryClientProvider — 为整个 React 组件树注入 QueryClient */}
    {/* ------------------------------------------------------------------ */}
    {/* TanStack Query 使用 React Context 将 QueryClient 实例传递给所有
        子孙组件。任何组件在调用 useQuery / useMutation 等 hook 时，
        都会通过 useContext 获取到这个 QueryClient，从而共享同一份缓存。

        架构意义：
          - 全局共享数据缓存（如游戏列表），不同页面不会重复请求
          - 统一管理 loading/error 状态，无需手写 useState + useEffect
          - 支持自动后台刷新、乐观更新、无限滚动等高级模式
    */}
    <QueryClientProvider client={queryClient}>
      {/* ---------------------------------------------------------------- */}
      {/* BrowserRouter — 基于 HTML5 History API 的路由容器 */}
      {/* ---------------------------------------------------------------- */}
      {/* BrowserRouter 是 React Router 的两种主要路由策略之一：

          BrowserRouter（当前使用的）：
            - 底层使用 HTML5 History API（pushState / replaceState）
            - URL 看起来像普通 URL：/login, /play/123
            - 优点：URL 干净美观，对 SEO 友好
            - 缺点：需要服务器配合（配置 fallback 到 index.html），
                   否则刷新非根路径时会 404
            - 服务器配置示例（Nginx）：
               location / {
                 try_files $uri $uri/ /index.html;
               }

          HashRouter（未使用）：
            - 底层使用 URL hash（#）部分，如 /#/login, /#/play/123
            - hash 部分不会发送到服务器，所以不需要服务器配置
            - 优点：部署简单，不会 404
            - 缺点：URL 不美观，SEO 不友好（搜索引擎通常忽略 # 后面的内容）

          本项目选择 BrowserRouter 的原因：
            - 后端的 FastAPI 可以配置 SPA fallback（或前端用 Nginx）
            - URL 更专业，利于分享游戏链接
            - 现代 Web 应用的标准选择
      */}
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
