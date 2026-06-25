/**
 * ============================================================================
 * api-client.ts — Axios 实例创建 & 拦截器详解
 * ============================================================================
 *
 * 【文件职责】
 * 创建并导出一个预配置的 Axios 实例，用于前端所有 HTTP 请求。
 * 通过请求拦截器自动附加 JWT 令牌，通过响应拦截器统一处理 401 未授权错误。
 *
 * 【技术栈】
 * Axios: 基于 Promise 的 HTTP 客户端，支持浏览器 & Node.js，自动 JSON 转换。
 * Zustand: 轻量级状态管理库，用于存储认证状态（token / user）。
 */

import axios from "axios";
import { useAuthStore } from "./auth-store";

// ============================================================================
// 1. Axios 实例创建 — axios.create()
// ============================================================================

/**
 * 【WHAT】使用 axios.create() 创建独立的 Axios 实例，而非修改全局 axios 对象。
 *
 * 【WHY — 隔离性】
 * - 全局 axios 默认值（axios.defaults）会影响所有通过 axios 直接发出的请求，
 *   包括第三方库内部发起的请求。在微服务/多网关场景下，不同后端服务可能需要不同
 *   的 baseURL、超时时间或认证策略，直接修改全局默认值会造成污染。
 * - axios.create() 返回的实例拥有独立的默认配置，互不干扰，便于：
 *   1) 同一前端对接多个 API 网关（如 /api/v1、/api/v2）时各建一个实例
 *   2) 不同模块（如用户模块、支付模块）使用不同的超时策略
 *   3) 测试时注入 mock 实例替代真实请求
 *
 * 【技术知识 — axios.create() vs axios 全局默认值】
 * - axios.defaults.baseURL = 'xxx'  → 全局污染，不推荐
 * - const instance = axios.create({ baseURL: 'xxx' }) → 隔离，推荐
 * - 实例创建后仍可通过 instance.defaults 继续覆盖默认值
 *
 * 【配置参数说明】
 * - baseURL: "/api"
 *   所有通过此实例发出的请求都会自动在此路径前拼接 baseURL。
 *   例如 apiClient.get("/games") 实际请求 → GET /api/games
 *   生产环境中通常由 Nginx/Vite proxy 将 /api/* 反向代理到后端服务，
 *   避免跨域问题（CORS）并隐藏后端真实地址。
 *
 * - timeout: 30000 (30秒)
 *   请求超时时间，单位毫秒。超过此时间未收到响应则自动取消请求，
 *   进入响应拦截器的 error 分支（error.code = 'ECONNABORTED'）。
 *   30s 是一个常见的中等超时值：太短可能导致慢查询/大文件上传误判为超时，
 *   太长则用户体验差（页面一直 loading）。
 *
 * - headers: { "Content-Type": "application/json" }
 *   默认请求头，告知后端请求体的 MIME 类型为 JSON。
 *   上传文件时需要覆盖为 "multipart/form-data"（Axios 会自动检测 FormData 并覆盖）。
 */
const apiClient = axios.create({
  baseURL: "/api",
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

// ============================================================================
// 2. 请求拦截器 — 自动附加 JWT Authorization 头
// ============================================================================

/**
 * 【WHAT】请求拦截器：在每次请求发出前自动从 Zustand store 读取 token 并塞入请求头。
 *
 * 【WHY — 关注点分离 & 安全性】
 * - 无需在每个 API 调用处手动拼接 Authorization 头，避免代码重复和遗漏。
 * - 统一管理认证逻辑：将来如果 Token 格式从 "Bearer xxx" 变更为其他方案
 *   （如 API Key、签名认证），只需修改此处一个地方。
 * - 安全考虑：Token 仅在前端内存中（Zustand store + localStorage 持久化），
 *   每次请求时动态注入，不会在页面 URL 或硬编码中出现。
 *
 * 【技术知识 — Axios 拦截器机制】
 * - 拦截器分为 request 和 response 两类，分别处理请求发出前和响应到达后。
 * - 使用 use() 注册拦截器，返回一个 ID，可通过 eject(id) 移除。
 *   本例无需移除（实例生命周期与页面一致），因此不保存 ID。
 * - 拦截器按注册顺序执行（FIFO），request 先注册的先执行，response 先注册的先执行。
 * - 每个 request 拦截器必须返回 config（或一个新的 config/Promise），
 *   否则请求不会发出（因为下一个拦截器或实际请求收不到 config）。
 *
 * 【技术知识 — useAuthStore.getState() 非响应式访问】
 * - useAuthStore 是一个 Zustand hook，在 React 组件中我们使用
 *   useAuthStore(state => state.token) 来订阅 token 的变化并自动重渲染。
 * - 但在这里（拦截器是非 React 环境），不能使用 hook（违反 React Hooks 规则），
 *   因此使用 useAuthStore.getState() 直接读取当前 store 快照。
 * - getState() 是 Zustand store 的静态方法，返回当前状态的不可变快照，
 *   不会建立订阅，不会触发 React 重渲染，是设计给 React 外部（中间件、拦截器、
 *   普通工具函数等）使用的标准 API。
 * - 对应的 setState() 用于在 React 外部更新状态。
 *
 * 【Bearer Token 认证机制】
 * - "Bearer" 是 OAuth 2.0 定义的 Token 类型标识，表示持有此 Token 者即授权主体。
 * - 格式：Authorization: Bearer <token>
 * - 后端从请求头中提取 Token，验证签名 & 有效期，确定用户身份。
 */
// 请求拦截器 — 每次请求前自动注入 JWT Token
apiClient.interceptors.request.use((config) => {
  /**
   * 从 Zustand store 获取当前 token。
   * 使用 getState() 而非 hook，因为拦截器不在 React 组件上下文中运行。
   * 每次请求都会动态读取最新 token（包括页面刷新后由 persist 中间件恢复的 token）。
   */
  const token = useAuthStore.getState().token;

  /**
   * 仅当 token 存在时才设置 Authorization 头。
   * 避免发送值为 "Bearer null" 或 "Bearer undefined" 的无意义请求头。
   * 未登录用户（token = null）直接放行，由后端决定是否拒绝未认证请求（401）。
   */
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  /**
   * 必须返回 config，否则请求链中断。
   * Axios 将返回值（或 resolve 的值）传递给下一个拦截器，最终通过适配器发出 HTTP 请求。
   * 也可返回 Promise<config> 用于异步操作（如刷新 Token），但本例无需。
   */
  return config;
});

// ============================================================================
// 3. 响应拦截器 — 统一处理 401 自动登出
// ============================================================================

/**
 * 【WHAT】响应拦截器：第一个回调处理成功响应（透传），第二个回调处理错误响应。
 *
 * 【WHY — 全局认证过期处理】
 * - 避免在每个 API 调用的 .catch() 中都写登出逻辑，减少代码重复和遗漏风险。
 * - 统一在拦截器中处理 401，保证无论哪个接口返回 401，用户都被登出并重定向
 *   到登录页（由 logout() 内部的 Zustand 状态变更触发 ProtectedRoute 重定向）。
 * - 用户无感知：Token 过期时无需手动刷新页面，自动跳转登录页。
 *
 * 【技术知识 — 响应拦截器的双回调模式】
 * axios.interceptors.response.use(onFulfilled, onRejected)
 * - onFulfilled: HTTP 状态码 2xx 时触发，接收 response 对象，返回什么下游就收到什么。
 * - onRejected: 所有非 2xx 状态码（或网络错误、超时）时触发，接收 error 对象。
 * - 如果 onFulfilled 抛出异常，也会进入 onRejected（但一般不在 onFulfilled 中抛异常）。
 *
 * 【技术知识 — error.response 结构】
 * - error.response 存在 → 服务器返回了非 2xx 响应（如 401, 403, 500）
 * - error.response 不存在 → 网络层面的错误（如断网、DNS 解析失败、CORS 被拦截、
 *   超时 ECONNABORTED），此时 error.request 包含 XMLHttpRequest 实例。
 * - 我们只处理 status === 401 的情况，其余错误全部透传。
 */
apiClient.interceptors.response.use(
  /**
   * 成功响应回调（2xx）：
   * 直接透传 response，让业务代码消费 response.data。
   * 不做额外处理，保持简洁。
   */
  (response) => response,

  /**
   * 错误响应回调（非 2xx 或网络错误）：
   * 在此集中处理认证失效场景。
   */
  (error) => {
    /**
     * 检查是否为 401 未授权错误。
     * 使用可选链 error.response?.status 安全地访问嵌套属性，
     * 避免在网络错误（response 为 undefined）时抛出 "Cannot read property 'status' of undefined"。
     */
    if (error.response?.status === 401) {
      /**
       * 401 表示 Token 无效或已过期。
       * 调用 Zustand store 的 logout() 方法：
       *   1) 清除内存中的 token / user / isAuthenticated
       *   2) persist 中间件自动同步清除 localStorage 中的持久化数据
       *   3) React 组件（如 ProtectedRoute）检测到 isAuthenticated=false，
       *      自动重定向到登录页面
       *
       * 同样使用 getState() 而非 hook（非 React 环境）。
       */
      useAuthStore.getState().logout();
    }

    /**
     * 【关键】返回 Promise.reject(error) 而非 return error：
     *
     * 【WHY — 错误传播链】
     * - 在 Axios 响应拦截器的 onRejected 回调中，如果您 return error（非 Promise），
     *   Axios 会将其视为 "错误已被处理"，将下游的 .catch() 转换为 .then()，
     *   即调用方收到的是 resolved Promise，无法通过 .catch() 捕获此错误。
     *
     * - 返回 Promise.reject(error) 确保错误继续沿着 Promise 链向下传播，
     *   让业务代码（调用 apiClient 的组件/模块）仍能通过 .catch() 捕获此错误，
     *   并进行额外的错误处理（如 toast 提示 "登录已过期"、记录错误日志、重试等）。
     *
     * - 如果不返回 Promise.reject，401 之外的错误也会被静默吞掉，
     *   调用方无法感知请求失败，导致 UI 逻辑错误。
     *
     * 【技术知识 — Promise.reject vs throw】
     * 在 Axios 拦截器中两者效果相同，都会导致返回的 Promise 被 reject。
     * 但 Promise.reject(error) 语义更明确（表示 "主动拒绝此 Promise"），
     * 且在所有 JS 环境中行为一致（throw 在某些异步上下文中可能表现不同）。
     */
    return Promise.reject(error);
  }
);

/**
 * 导出配置好的 Axios 实例，项目中所有 API 调用均使用此实例：
 *   import apiClient from "@/lib/api-client";
 *   const res = await apiClient.get("/games");
 */
export default apiClient;
