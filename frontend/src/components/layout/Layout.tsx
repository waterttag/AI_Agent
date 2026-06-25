/**
 * Layout 布局组件
 *
 * 功能：作为 React Router v6 "布局路由"（Layout Route）的 element，
 *       提供全站统一的页面骨架：顶部导航栏 + 中间内容区 + 底部页脚。
 *
 * 技术核心：Outlet（React Router v6 的插槽机制）
 *   父路由使用 <Route element={<Layout />}> 包裹子路由，
 *   Layout 组件中的 <Outlet /> 会自动渲染当前匹配的子路由组件。
 *   这样 Navbar 和 Footer 只需定义一次，所有子页面共享。
 */

import { Outlet } from "react-router-dom";
// Outlet: React Router v6 的核心组件 —
//   它是父路由中为子路由预留的"插槽"（slot）。
//   当 URL 匹配到子路由时，对应的子组件会在 <Outlet /> 位置渲染。
//
// 路由配置示例（通常在 App.tsx 或 router.tsx 中）：
//   <Route element={<Layout />}>        {/* 父路由：无 path，仅提供布局 */}
//     <Route index element={<HomePage />} />   {/* 子路由：匹配 "/" */}
//     <Route path="login" element={<LoginPage />} />
//     <Route path="create" element={<CreatePage />} />
//   </Route>
//
// 当用户访问 "/login" 时，React Router 会渲染：
//   <Layout>
//     <Navbar />
//     <main>
//       <Outlet />  ← 这里渲染 <LoginPage />
//     </main>
//     <footer>...</footer>
//   </Layout>
//
// 这种模式的好处：
//   1. Navbar 和 Footer 只定义一次，不用在每个页面组件中重复引入。
//   2. 导航状态（如 Navbar 中的高亮项）可以随路由自动变化。
//   3. 布局层级的滚动、动画等可以在 Layout 中统一管理。

import { Navbar } from "./Navbar";

export function Layout() {
  return (
    // min-h-screen: 最小高度为视口高度（100vh）—
    //   即使内容很少，页面也会填满整个屏幕高度。
    //   这是"粘性页脚"（sticky footer）的基石。
    //
    // flex flex-col: 纵向弹性布局 —
    //   子元素沿垂直方向排列，配合 flex-1 实现 footer 推底。
    <div className="min-h-screen flex flex-col">
      {/* 顶部导航栏：始终在最上面 */}
      <Navbar />

      {/*
        =========================================================================
        flex-1：填充剩余空间，实现粘性页脚（sticky footer）
        =========================================================================
        flex-1 等价于 flex: 1 1 0%，即：
          - flex-grow: 1    → 有剩余空间时，main 会扩展占据全部剩余空间。
          - flex-shrink: 1  → 空间不足时可以缩小。
          - flex-basis: 0%  → 初始大小为 0（完全依赖 grow/shrink 分配空间）。

        配合父容器的 min-h-screen + flex flex-col：
          1) Navbar 占据其自然高度（h-16 = 4rem）。
          2) main 通过 flex-1 占据所有剩余的垂直空间。
          3) Footer 紧贴在 main 下方 → 内容少时 footer 在屏幕底部，内容多时自然下推。

        container mx-auto px-4 py-8:
          - container: Tailwind 响应式容器 — 根据断点自动调整最大宽度
            （sm:640px, md:768px, lg:1024px, xl:1280px, 2xl:1536px）。
          - mx-auto: 水平居中（margin-left: auto; margin-right: auto）。
          - px-4: 水平内边距 1rem — 小屏幕时内容不会贴边。
          - py-8: 垂直内边距 2rem — 内容与上下边缘有呼吸空间。
      */}
      <main className="flex-1 container mx-auto px-4 py-8">
        {/*
          <Outlet />: React Router v6 的"子路由插槽" —
          当前匹配的子路由组件将在此处渲染。
        */}
        <Outlet />
      </main>

      {/*
        底部页脚：始终在最下面
        border-t border-border: 顶部 1px 分割线。
        py-6: 垂直内边距 1.5rem。
        text-center: 文字居中。
        text-sm text-muted-foreground: 小号文字 + 低对比度颜色（次要信息）。
      */}
      <footer className="border-t border-border py-6 text-center text-sm text-muted-foreground">
        AI Game Forge — Built with AI Agent Collaboration
      </footer>
    </div>
  );
}
