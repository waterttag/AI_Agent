/**
 * App.tsx — 应用根组件，负责路由定义与页面分发
 * ------------------------------------------------------------------
 * 使用 React Router v6 的声明式路由定义：
 *   - <Routes> 是所有路由的容器（v6 替代了 v5 的 <Switch>）
 *   - <Route> 通过 element 属性指定组件（而非 v5 的 children/component）
 *   - 布局路由（Layout Route）通过 <Route element={<Layout />}> 包裹子路由，
 *     Layout 组件内部使用 <Outlet /> 渲染匹配的子路由内容
 */

import { Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { HomePage } from "@/pages/HomePage";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { CreatePage } from "@/pages/CreatePage";
import { PlayPage } from "@/pages/PlayPage";
import { useAuthStore } from "@/lib/auth-store";

// ---------------------------------------------------------------------------
// ProtectedRoute — 路由守卫组件（Auth Guard）
// ---------------------------------------------------------------------------
// 职责：检查用户是否已登录，未登录则重定向到登录页。
//
// 设计模式：Wrapper / Higher-Order Component（HOC）的简化版
//   - 接收 children 属性（即被保护的目标页面组件）
//   - 根据认证状态决定渲染 children 还是 <Navigate> 重定向
//
// 为什么用独立的组件而不是在每个页面里判断？
//   1. DRY 原则：避免在每个需要认证的页面重复相同的认证逻辑
//   2. 声明式路由：路由定义清晰，"这个路径需要认证"一目了然
//   3. 统一行为：所有受保护路由的重定向行为一致（目标路径、replace 模式）
//
// 参数 children: React.ReactNode
//   React.ReactNode 是 React 中最宽泛的类型，包括：
//     - JSX 元素（如 <CreatePage />）
//     - 字符串、数字
//     - null、undefined、boolean
//     - 数组、Fragment
//   使用 ReactNode 使得 ProtectedRoute 可以包裹任意内容
// ---------------------------------------------------------------------------
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  // ------------------------------------------------------------------------
  // Zustand selector — 为什么 s => s.isAuthenticated 避免不必要的重渲染？
  // ------------------------------------------------------------------------
  // useAuthStore 是 Zustand 创建的全局状态管理 hook。
  //
  // Zustand 的选择器（selector）机制：
  //   - 使用 useAuthStore((s) => s.isAuthenticated) 时，Zustand 会做
  //     浅比较（shallow comparison），只有 isAuthenticated 的值发生变化时，
  //     组件才会重新渲染
  //   - 如果写 useAuthStore()（不传 selector），会获取整个 store 对象，
  //     任何字段变化都会触发重渲染，即使当前组件不关心的字段变了
  //
  // 举例说明：
  //   // 不好的写法 — 任何 store 字段变化都触发重渲染
  //   const auth = useAuthStore();  // { isAuthenticated, user, token, ... }
  //
  //   // 好的写法 — 只有 isAuthenticated 变化才重渲染
  //   const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  //
  // 为什么这里只需要关心 isAuthenticated？
  //   ProtectedRoute 的唯一职责是"判断是否允许访问"，不需要 user 对象
  //   或 token 等数据。精准选择需要的字段，减少不必要的渲染次数。
  //
  // 底层原理：Zustand 在内部使用 useSyncExternalStoreWithSelector，
  //   对比新旧 selector 返回值（用 Object.is），不一致时才触发渲染。
  // ------------------------------------------------------------------------
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  // 未登录：重定向到 /login 页面
  if (!isAuthenticated) return <Navigate to="/login" replace />;

  // 已登录：正常渲染被保护的页面内容
  return <>{children}</>;
}

// ---------------------------------------------------------------------------
// App 组件 — 路由定义的入口
// ---------------------------------------------------------------------------
export default function App() {
  return (
    <Routes>
      {/* ================================================================= */}
      {/* 布局路由（Layout Route） */}
      /* ================================================================= */
      {/* React Router v6 的核心改进之一：Layout Route
          与 v5 用嵌套 <Route> 组件的写法有本质区别。

          v5 写法（已废弃）：
            <Route path="/" component={Layout}>
              <Route path="/" component={HomePage} />
            </Route>

          v6 写法（当前）：
            <Route element={<Layout />}>
              <Route path="/" element={<HomePage />} />
            </Route>

          关键差异：
            1. v6 用 element 属性传递 React 元素，而不是 component/render
               - element={<HomePage />} 是在组件外部创建元素，只创建一次
               - component={HomePage} 是每次匹配都调用 React.createElement，
                 效率更低且 props 传递方式不同

            2. v6 的 Layout 必须使用 <Outlet /> 渲染子路由
               - <Outlet /> 是 React Router v6 引入的占位符组件
               - 当 URL 匹配到子路由时，<Outlet /> 被替换为对应子路由的 element
               - 例如 URL="/login" → Layout 内的 <Outlet /> 渲染 <LoginPage />
               - 例如 URL="/"      → Layout 内的 <Outlet /> 渲染 <HomePage />

            3. 布局路由本身没有 path
               - <Route element={<Layout />}> 没有 path 属性
               - 它只提供"共同的布局框架"，子路由提供具体的路由匹配
               - 这意味着 Layout 组件对所有子路由都渲染，类似"模板页"的概念

          Layout 组件的典型结构：
            function Layout() {
              return (
                <div>
                  <Navbar />           ← 所有页面共享的导航栏
                  <main>
                    <Outlet />         ← 子路由内容在这里渲染
                  </main>
                  <Footer />           ← 所有页面共享的页脚
                </div>
              );
            }
      */}
      <Route element={<Layout />}>
        {/* -------------------------------------------------------------- */}
        {/* 路由定义 */}

        {/* 首页 — 公开路由，无需登录 */}
        <Route path="/" element={<HomePage />} />

        {/* 登录页 — 公开路由 */}
        <Route path="/login" element={<LoginPage />} />

        {/* 注册页 — 公开路由 */}
        <Route path="/register" element={<RegisterPage />} />

        {/* -------------------------------------------------------------- */}
        {/* 创建游戏页 — 受保护路由（需要登录） */}
        {/* -------------------------------------------------------------- */}
        {/* <ProtectedRoute> 包裹 <CreatePage />：
            只有当 ProtectedRoute 判断用户已登录时，才渲染 CreatePage；
            否则返回 <Navigate to="/login" replace />，用户被重定向到登录页。
        */}
        <Route
          path="/create"
          element={
            <ProtectedRoute>
              <CreatePage />
            </ProtectedRoute>
          }
        />

        {/* -------------------------------------------------------------- */}
        {/* 游戏播放页 — 动态路由参数 :gameId */}
        {/* -------------------------------------------------------------- */}
        {/* :gameId 是 URL 参数（路径参数），如 /play/abc123：
            在 PlayPage 组件中可以通过 useParams() hook 获取：
              const { gameId } = useParams(); // gameId = "abc123"

            为什么不用查询参数（如 /play?gameId=abc123）？
              - 路径参数语义更清晰：/play/:id 表示"id 是资源的标识符"
              - 对 SEO 更友好（搜索引擎将不同 id 视为不同页面）
              - RESTful 风格：资源路径以 /resource/{id} 为标准
        */}
        <Route path="/play/:gameId" element={<PlayPage />} />
      </Route>
    </Routes>
  );
}

// ===========================================================================
// 补充说明：Navigate 组件的 replace 属性
// ===========================================================================
// 在 ProtectedRoute 中使用了 <Navigate to="/login" replace />
//
// replace 属性的作用：
//   - 使用 replaceState（替换当前历史记录）而不是 pushState（新增记录）
//   - 简言之：当前页面（如 /create）不会被写入浏览器历史记录
//
// 为什么需要 replace？
//   场景：未登录用户访问 /create → 被重定向到 /login
//
//   不使用 replace（默认 push）：
//     历史记录：[...之前的页面, /create, /login]
//     用户按"返回"按钮 → 回到 /create → 又因未登录被重定向到 /login
//     → 形成"死循环"，用户被困在 /login 永远回不去
//
//   使用 replace：
//     历史记录：[...之前的页面, /login]
//     用户按"返回"按钮 → 回到访问 /create 之前的那一页
//     → 正常的浏览体验
//
// 总结：在认证重定向场景下，replace 是必需的，否则会破坏浏览器的
//       前进/后退导航体验（俗称"back-button loop"问题）。
// ===========================================================================
