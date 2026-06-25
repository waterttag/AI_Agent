/**
 * useAuth.ts — 认证相关 hooks（登录 / 注册）
 *
 * 【架构说明】
 * - 使用 TanStack Query（原名 React Query）的 useMutation 处理登录和注册请求
 * - 登录/注册成功后，将服务端返回的 access_token 和 user 存入 Zustand 全局状态，
 *   并通过 React Router 的 useNavigate 跳转到首页 "/"
 */

import { useMutation } from "@tanstack/react-query";
// useMutation: TanStack Query 提供的 mutation hook
// —— 为什么用 mutation 而不是 query？
//    登录/注册是 POST 请求，会在服务端创建或修改状态（生成 token、创建用户记录），
//    属于"副作用"操作。TanStack Query 的设计哲学中：
//    - useQuery: 用于 GET 类"读取"操作，关注数据获取与缓存
//    - useMutation: 用于 POST/PUT/DELETE 等"写入"操作，关注副作用与缓存失效
//    两者分离可以让框架自动管理不同的生命周期（query 自动重取、mutation 手动触发）

import { useNavigate } from "react-router-dom";
// useNavigate: React Router v6 的编程式导航 hook
// —— 为什么在 hook 内部使用 useNavigate？
//    将"登录成功后跳转"这个副作用封装在 hook 内部，组件只需调用 mutate() 并传入表单数据，
//    无需关心跳转逻辑。这符合"关注点分离"原则——组件负责 UI 交互，hook 负责业务流程编排。

import apiClient from "@/lib/api-client";
// apiClient: 项目封装的 Axios 实例，预配置了 baseURL、拦截器等

import { useAuthStore } from "@/lib/auth-store";
// useAuthStore: Zustand store，管理全局认证状态（token、user、login/logout 方法）
// —— Zustand 是一个轻量级状态管理库，通过 selector 模式 (s) => s.login 按需订阅，
//    避免不必要的重渲染。与 Redux 不同，Zustand 无需 Provider 包裹组件树。

import type { TokenResponse } from "@/types";
// TokenResponse: 服务端返回的登录/注册响应类型
//    通常包含 { access_token: string; token_type: string; user: User }

/**
 * useLogin — 用户登录 hook
 *
 * 【数据流】
 * 1. 组件调用 mutate({ email, password }) 触发 mutation
 * 2. mutationFn 发送 POST /auth/login，携带 email + password
 * 3. 服务端验证凭证，返回 TokenResponse（含 access_token + user）
 * 4. onSuccess 回调：
 *    a. 调用 Zustand 的 login() 将 token 和 user 存入全局 store
 *       —— 全局 store 使得 Header 等组件可以响应式地显示用户信息
 *    b. 调用 navigate("/") 跳转到首页
 *       —— 登录成功后自动跳转是常见的 UX 惯例
 *
 * 【错误处理】
 * useMutation 返回值包含 isError、error 字段，组件可以直接使用：
 * - isError: boolean —— 是否发生了错误
 * - error: Error —— 错误对象，包含服务端返回的错误信息（如 "密码错误"）
 * - 组件通过这些字段显示错误提示，无需额外的 try/catch
 */
export function useLogin() {
  // 从 Zustand store 中提取 login 方法（使用 selector 避免不必要的重渲染）
  const login = useAuthStore((s) => s.login);
  // 获取 React Router 的 navigate 函数，用于登录成功后跳转
  const navigate = useNavigate();

  // 返回 useMutation 对象，调用方可以解构出 mutate、isPending、isError、error 等
  return useMutation({
    /**
     * mutationFn: 执行 mutation 的异步函数
     * —— async 模式：TanStack Query 内部会 catch 这个函数的异常，
     *    并自动设置 isError=true，将异常对象存入 error 字段
     * —— 参数 data 来自调用 mutate(data) 时传入的表单数据
     * —— 泛型 TokenResponse 指定了 API 返回的 data 类型
     */
    mutationFn: async (data: { email: string; password: string }) => {
      // POST 请求：将 email 和 password 作为请求体发送
      // axios.post<T>(url, body) 中，泛型 T 指定 response.data 的类型
      const res = await apiClient.post<TokenResponse>("/auth/login", data);
      return res.data; // 返回 TokenResponse，供 onSuccess 使用
    },
    /**
     * onSuccess: mutation 成功后的回调
     * —— 参数 data 就是 mutationFn 的返回值（TokenResponse）
     * —— 为什么在这里处理副作用而不是在组件中？
     *    onSuccess 在 mutation 生命周期的"正确时刻"触发，
     *    确保 login() 和 navigate() 只在请求确实成功后才执行，
     *    避免了在组件中手动管理 Promise 链的繁琐
     */
    onSuccess: (data) => {
      // 将 token 和 user 存入 Zustand 全局 store
      // —— access_token: JWT token，后续请求通过 Axios 拦截器自动附加到 Authorization header
      // —— user: 用户信息对象，供 UI 展示（用户名、头像等）
      login(data.access_token, data.user);
      // 跳转到首页 "/"
      // —— navigate("/") 会触发 React Router 的路由匹配，渲染首页组件
      navigate("/");
    },
  });
}

/**
 * useRegister — 用户注册 hook
 *
 * 【与 useLogin 的区别】
 * - API 端点不同：/auth/register vs /auth/login
 * - 请求体多一个字段：username（登录只需要 email + password）
 * - 其余逻辑完全一致：成功后同样存 token、跳转首页
 *
 * 【为什么注册后也自动登录？】
 * 服务端 /auth/register 接口直接返回 TokenResponse（而非仅返回"注册成功"），
 * 这意味着注册即登录——用户体验更好，无需注册后再跳转到登录页。
 */
export function useRegister() {
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  return useMutation({
    mutationFn: async (data: { username: string; email: string; password: string }) => {
      const res = await apiClient.post<TokenResponse>("/auth/register", data);
      return res.data;
    },
    onSuccess: (data) => {
      // 注册成功后自动登录：存入 token 和 user 信息
      login(data.access_token, data.user);
      // 跳转到首页
      navigate("/");
    },
  });
}
