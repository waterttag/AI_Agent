/**
 * ============================================================================
 * auth-store.ts — Zustand 认证状态管理 & persist 持久化
 * ============================================================================
 *
 * 【文件职责】
 * 使用 Zustand 管理前端全局认证状态（token / user / isAuthenticated），
 * 并通过 persist 中间件将状态持久化到 localStorage，支持页面刷新后保持登录。
 *
 * 【为什么不用别的方案？— Zustand vs Redux Toolkit vs React Context 深度对比】
 *
 * ┌──────────────────────────────────────────────────────────────────────────┐
 * │ 1. Zustand（本项目选择）                                                  │
 * ├──────────────────────────────────────────────────────────────────────────┤
 * │ 优点：                                                                   │
 * │ • 极简 API：create() 一个函数搞定，零样板代码（无 reducer/action/type）    │
 * │ • 无需 Provider 包裹组件树，直接在组件中 import useAuthStore 即可使用       │
 * │ • 基于选择器的订阅：useAuthStore(s => s.token)，只有 token 变化时重渲染   │
 * │   而非整个 store 变化都重渲染，天然细粒度更新（区别于 Context）              │
 * │ • 内置 persist 中间件：一行代码实现 localStorage/sessionStorage 持久化     │
 * │ • TypeScript 一等公民：类型自动推断，无需额外类型定义                       │
 * │ • 可在 React 外部使用：getState() / setState() 静态方法（本例在拦截器中用）  │
 * │ • 体积极小：gzip 后 ~1KB，零运行时依赖（Redux Toolkit ~11KB）              │
 * │ • 支持中间件：persist、immer、devtools 等，按需组合                         │
 * │                                                                          │
 * │ 缺点：                                                                   │
 * │ • 社区/生态规模不如 Redux（但正在快速增长）                                 │
 * │ • 极大型应用（百+共享状态）可能不如 Redux DevTools 的调试体验               │
 * │ • 团队熟悉度：部分开发者更熟悉 Redux 的 reducer 模式                        │
 * ├──────────────────────────────────────────────────────────────────────────┤
 * │ 2. Redux (Toolkit)                                                       │
 * ├──────────────────────────────────────────────────────────────────────────┤
 * │ 优点：                                                                   │
 * │ • 成熟生态：Redux DevTools 功能强大（时间旅行调试、状态快照、action 重放）  │
 * │ • 严格的单向数据流：action → reducer → store，状态变更有据可查              │
 * │ • 中间件生态丰富：redux-saga、redux-observable、RTK Query 等               │
 * │ • 大规模团队熟悉度最高，社区资源最丰富                                      │
 * │                                                                          │
 * │ 缺点（相对于本项目需求）：                                                 │
 * │ • 样板代码多：需要 createSlice → configureStore → Provider 三步            │
 * │ • 必须用 <Provider> 包裹组件树根节点                                       │
 * │ • 在 React 外部访问 store 需要用 store.getState()，但 store 实例需要手动导出│
 * │ • 选择器订阅需要 useSelector + shallowEqual 配合才能避免不必要重渲染        │
 * │ • bundle 体积更大（~11KB gzipped），对本项目过度                            │
 * │ • 本项目只有 token + user 两个状态，Redux 的架构优势无法发挥                 │
 * ├──────────────────────────────────────────────────────────────────────────┤
 * │ 3. React Context                                                         │
 * ├──────────────────────────────────────────────────────────────────────────┤
 * │ 优点：                                                                   │
 * │ • React 内置，零依赖                                                      │
 * │ • 概念简单：createContext + Provider + useContext                         │
 * │                                                                          │
 * │ 缺点（致命）：                                                            │
 * │ • 重渲染级联问题（Re-render Cascade）：                                    │
 * │   当 Provider 的 value 对象中任意字段变化时，所有使用该 Context 的组件     │
 * │   都会重渲染，无论它们是否使用了变化的那一个字段。                             │
 * │   例如：AuthContext 包含 token、user、theme、language 四个字段，           │
 * │   如果 theme 变化，只读取 token 的组件也会无条件重渲染。                      │
 * │                                                                          │
 * │ • 缓解方案复杂度高：                                                      │
 * │   - useMemo 缓存 value 对象（避免每次渲染重新创建引用）                      │
 * │   - 拆分多个 Context（AuthTokenContext、AuthUserContext...）               │
 * │   - 或用 useReducer + memo 组合，但这已接近重新实现一个状态管理库            │
 * │   这些额外工作正是 Zustand/Redux 已经解决的问题                              │
 * │                                                                          │
 * │ • 无中间件：无法方便地持久化到 localStorage、无法做 devtools 调试            │
 * │ • 无法在 React 外部访问（如 api-client 拦截器），除非用 ref 或事件发射器     │
 * │ • 不适用于频繁更新的状态（每次更新都触发 Provider 子树全部重渲染）           │
 * │                                                                          │
 * │ 结论：Context 适合低频更新的静态数据（如主题、语言、权限标识），              │
 * │ 不适合频繁更新或多字段共享的状态。本项目 token 登录/登出时变化，              │
 * │ 且需要在 React 外部（拦截器）读取 token，Context 不适用。                     │
 * └──────────────────────────────────────────────────────────────────────────┘
 *
 * 【本项目选择 Zustand 的理由，总结】
 *  1. 状态规模小：仅 auth（token + user），不需要 Redux 级别的架构
 *  2. 需要 persist：Zustand 内置中间件，不额外安装库
 *  3. 需要 React 外部访问：getState() 在 api-client 拦截器中使用
 *  4. 选择器优化天然支持：无需 useMemo / shallowEqual / React.memo 配合
 *  5. TypeScript 体验好：类型自动推导
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User } from "@/types";

// ============================================================================
// 1. 接口定义 — AuthState
// ============================================================================

/**
 * 【WHAT】AuthState 接口描述认证 store 的完整类型结构。
 *
 * 【字段说明】
 * - token:      JWT 令牌字符串，未登录时为 null
 * - user:       当前登录用户对象（id, username, email 等），未登录时为 null
 * - isAuthenticated: 派生状态（由 login/logout 同步设置），方便 ProtectedRoute 等组件直接判断
 *               注意：这不是 computed/getter，而是在 login/logout 中手动同步赋值的
 * - login():    登录操作，接收 token 和 user 并一次性更新三个字段
 * - logout():   登出操作，将所有状态重置为初始值（null / null / false）
 */
interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
  login: (token: string, user: User) => void;
  logout: () => void;
}

// ============================================================================
// 2. Store 创建 — create + persist 中间件
// ============================================================================

/**
 * 【WHAT】使用 Zustand 的 create() 和 persist() 创建认证 store。
 *
 * 【语法说明 — create<AuthState>()(persist(...))】
 * - create<AuthState>() — 泛型参数指定 store 类型，注意双层括号：
 *   外层 create<AuthState>() 返回一个函数，内层 (persist(...)) 传入 store 定义。
 *   这种 "curried" 写法是为了让 TypeScript 类型推导与中间件组合同时工作。
 *
 * 【persist 中间件详解】
 *
 * WHAT: 自动将 store 状态序列化到 Web Storage（localStorage/sessionStorage），
 *       页面刷新/关闭后重新打开时自动恢复（rehydrate）。
 *
 * 配置项：
 * - name: "aigame-auth"
 *   存储键名（Storage key），实际存储在 localStorage 中的键名就是 "aigame-auth"。
 *   命名建议：加应用前缀避免多应用部署在同域名下时冲突。
 *
 * - storage（使用默认值 localStorage）：
 *   可通过 getStorage 传入自定义存储引擎（如 sessionStorage、AsyncStorage for RN）。
 *
 * - partialize（未在本文使用，但很重要）：
 *   相当于 blacklist/whitelist 机制，控制哪些字段被持久化。
 *   例: partialize: (state) => ({ token: state.token })
 *       → 只持久化 token，user 和 isAuthenticated 不存（页面刷新后手动从 token 解析 user）
 *   在本项目中未使用 partialize，意味着所有字段（token, user, isAuthenticated）都被持久化。
 *   这是安全的，因为 user 信息不包含密码等敏感数据。
 *
 * - version（未使用）：
 *   用于存储结构迁移：当存储结构变更时，可以写 migration 函数处理旧版本数据。
 *   例: version: 1, migrate: (persistedState, version) => { ... 转换为新结构 ... }
 *
 * - skipHydration（未使用）：
 *   默认为 false，即 store 创建时自动从 localStorage 恢复状态。
 *   设为 true 时需要手动调用 useAuthStore.persist.rehydrate()，用于 SSR（服务端渲染）
 *   场景（服务端没有 localStorage，会报错）或需要控制恢复时机。
 *
 * 【技术知识 — localStorage vs sessionStorage 安全权衡】
 *
 * localStorage（本项目使用）:
 *   + 浏览器关闭后仍保留，用户下次打开页面仍保持登录
 *   + 容量 ~5MB，足够存储 token + user 信息
 *   – XSS 风险：如果网站存在 XSS 漏洞，恶意脚本可读取 localStorage 中的 token
 *   – 同源策略：同一域名下的所有页面共享
 *
 * sessionStorage:
 *   + 浏览器标签关闭后自动清除，更安全（标签隔离）
 *   – 不持久，刷新标签页后仍需重新登录
 *   – 不同标签页不共享，无法实现多标签同步登录
 *
 * 【安全建议】
 * - Token 存储在 localStorage 中的 XSS 风险可以通过严格的 CSP（Content Security Policy）
 *   和输入消毒（sanitize）来缓解
 * - 更高安全需求的场景应使用 httpOnly cookie（JS 不可读，自动随请求发送）
 *   但这需要后端配合设置 Set-Cookie
 * - 定期轮换 Token（refresh token 机制）是更好的实践
 *
 * 【技术知识 — persist 对状态字段的序列化/反序列化】
 * - 写入：JSON.stringify(state) → localStorage.setItem(key, jsonStr)
 * - 读取：localStorage.getItem(key) → JSON.parse(jsonStr) → 恢复到 store
 * - 方法（如 login(), logout()）不会被序列化，只有数据字段被持久化
 * - 反序列化后 Zustand 会自动将数据字段合并到 store 中，方法保持不变
 * - 此过程对开发者完全透明，无需手动处理 JSON 转换
 */
export const useAuthStore = create<AuthState>()(
  persist(
    /**
     * 【store 定义回调】
     * Zustand 的 create() 接收 (set, get, api) => initialState 形式的回调。
     * 这里仅使用了 set（状态更新函数），不需要 get（读取状态）和 api（store 实例方法）。
     *
     * 【Zustand 的 set() 函数】
     * - set({ key: value }) 执行浅合并（shallow merge），只更新传入的字段，其余字段保留
     * - 支持函数式更新：set(state => ({ count: state.count + 1 }))
     * - 更新触发所有订阅了变化字段的选择器的组件重渲染（未订阅的字段不会触发）
     * - 在 persist 中间件下，每次 set() 调用后自动触发 localStorage 写入
     *   （实际上是 set 之后 debounce 写入，避免频繁 IO）
     */
    (set) => ({
      // -------- 初始状态 --------
      /** 未登录时所有认证相关字段为 null/false */
      token: null,
      user: null,
      isAuthenticated: false,

      // -------- Actions --------

      /**
       * 【login — 登录操作】
       * WHAT: 接收登录成功返回的 token 和 user，一次性更新三个状态字段。
       * WHY: 保证 token、user、isAuthenticated 三者同步更新，避免中间态不一致。
       *       如果分三次 set 调用，可能在某个瞬间 token 有值但 isAuthenticated 仍为 false，
       *       导致组件逻辑判断错误。
       * 触发效果：
       *   1) api-client 的下次请求自动携带新 token
       *   2) ProtectedRoute 检测到 isAuthenticated=true，放行受保护页面
       *   3) UI 组件（如 UserProfile）自动展示 user 信息
       *   4) persist 中间件自动写入 localStorage
       */
      login: (token: string, user: User) =>
        set({ token, user, isAuthenticated: true }),

      /**
       * 【logout — 登出操作】
       * WHAT: 清除所有认证状态，回退到未登录的初始状态。
       * WHY: 必须同时清空 token 和 user，仅清空 token 会导致 UI 仍展示旧用户信息。
       * 调用场景：
       *   1) 用户主动点击"退出登录"按钮
       *   2) api-client 响应拦截器收到 401 时自动调用（Token 过期或无效）
       *   3) 管理员强制下线（如有此功能）
       * 触发效果：
       *   1) persist 中间件自动清除 localStorage 中的持久化数据
       *   2) ProtectedRoute 检测到 isAuthenticated=false，重定向到 /login
       *   3) 其他订阅了 token/user 的组件自动更新 UI
       */
      logout: () =>
        set({ token: null, user: null, isAuthenticated: false }),
    }),
    {
      /**
       * persist 中间件配置
       * name: localStorage 中的键名，需全局唯一
       *
       * 其他常用但未在此启用的配置项：
       * - storage: createJSONStorage(() => sessionStorage)  — 改用 sessionStorage
       * - partialize: (state) => ({ token: state.token })     — 只持久化部分字段
       * - version: 1                                           — 数据迁移版本号
       * - migrate: (persistedState, version) => { ... }        — 数据迁移函数
       * - skipHydration: true                                  — 跳过自动恢复（SSR 场景）
       * - onRehydrateStorage: (state) => { ... }               — 恢复完成后的回调
       */
      name: "aigame-auth",
    }
  )
);
