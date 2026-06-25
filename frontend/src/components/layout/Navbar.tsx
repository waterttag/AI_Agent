/**
 * Navbar 导航栏组件
 *
 * 功能：顶部固定导航栏，包含品牌标识、Browse/Create 导航链接、
 *       以及根据登录状态动态显示的 Login/Sign Up 或 用户名/Logout 区域。
 *
 * 设计要点：
 *   - 粘性定位 (sticky)：随页面滚动时固定在视口顶部，避免使用 fixed 造成脱离文档流的问题。
 *   - 毛玻璃效果 (backdrop-blur)：半透明背景 + 模糊，增强视觉层次感。
 *   - 条件渲染：根据 isAuthenticated 切换登录前/后的 UI，逻辑简单，直接内联三元表达式即可。
 */

import { Link, useNavigate } from "react-router-dom";
// react-router-dom:
//   - Link: 声明式导航组件，渲染为 <a> 标签，支持无障碍访问（键盘焦点、屏幕阅读器）。
//   - useNavigate: 命令式导航 hook，返回一个 navigate 函数，用于在事件处理中跳转。

import { useAuthStore } from "@/lib/auth-store";
// Zustand 认证状态管理 store

import { Button } from "@/components/ui/button";
// 项目统一的 Button 组件（基于 CVA 的变体系统，支持 variant/size props）

import { Gamepad2 } from "lucide-react";
// lucide-react 图标库中的游戏手柄图标

export function Navbar() {
  // =========================================================================
  // 1. useAuthStore 解构：一次调用获取三个值
  // =========================================================================
  // 为什么不用三次独立调用（如 const isAuthenticated = useAuthStore(s => s.isAuthenticated)）？
  // 理由：isAuthenticated、user、logout 这三个值在登录/登出时总是一起变化，
  //       不存在"isAuthenticated 变了但 user 没变"的场景，
  //       因此一次解构获取三个值不会导致不必要的重渲染。
  //       （如果某个值频繁独立变化，才需要用独立 selector 精确订阅）
  const { isAuthenticated, user, logout } = useAuthStore();

  // navigate 函数用于命令式跳转（logout 后跳转到首页、点击 Login 按钮跳转等）
  const navigate = useNavigate();

  return (
    // =========================================================================
    // 2. 粘性导航栏 (sticky navbar)
    // =========================================================================
    // sticky top-0 z-50:
    //   - sticky: 粘性定位 — 元素在正常文档流中占据空间，当页面滚动到其 top-0 位置时"粘住"不动。
    //     与 fixed 的区别：fixed 完全脱离文档流（不占空间，需要手动给下方内容加 padding-top），
    //     sticky 保留文档流占位（下方内容自动适配，无需额外 padding）。
    //   - top-0: 粘住时距离视口顶部的偏移为 0。
    //   - z-50: 确保导航栏在所有内容之上（不会被下方内容遮挡）。
    //
    // border-b border-border: 底部 1px 的分割线，与主题边框色一致。
    //
    // bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60:
    //   毛玻璃（frosted-glass）效果：
    //     - bg-background/95: 背景色 95% 不透明度（几乎不透明），作为不支持 backdrop-filter 浏览器
    //       的 fallback — 此时几乎看不到下方内容，保证文字可读性。
    //     - backdrop-blur: CSS backdrop-filter: blur() — 对导航栏**后方**的内容做模糊处理。
    //       产生毛玻璃效果：半透明背景 + 后方模糊 = 能看到下面内容但被虚化。
    //     - supports-[backdrop-filter]:bg-background/60: 使用 CSS @supports 特性查询 —
    //       如果浏览器支持 backdrop-filter，则改用 60% 不透明度的背景（更透明），
    //       配合模糊效果一起呈现真正的毛玻璃效果。
    //       如果不支持（如旧版浏览器），则保留 95% 的背景以确保可读性。
    <nav className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      {/*
        container mx-auto: 响应式容器，自动水平居中，最大宽度随断点变化。
        flex h-16 items-center justify-between: 弹性布局，固定高度 4rem，垂直居中，两端对齐。
        px-4: 水平内边距 1rem（小屏也不会贴边）。
      */}
      <div className="container mx-auto flex h-16 items-center justify-between px-4">
        {/*
          =======================================================================
          3. Link vs navigate：声明式 vs 命令式导航
          =======================================================================
          品牌 Logo 使用 <Link> 组件：
            - Link 渲染为标准 <a> 标签，天然支持右键"在新标签页打开"、中键点击、
              键盘 Tab 聚焦、屏幕阅读器朗读 "链接" 角色等无障碍特性。
            - 适合**导航菜单项** — 它们是页面的自然组成部分，语义上就是链接。
            - flex items-center gap-2: 图标与文字水平排列，间距 0.5rem。
          */}
        <Link to="/" className="flex items-center gap-2 text-xl font-bold text-primary">
          <Gamepad2 className="h-6 w-6" />
          <span>AI Game Forge</span>
        </Link>

        <div className="flex items-center gap-4">
          {/*
            Browse 链接：始终可见的导航项。
            text-muted-foreground hover:text-foreground: 默认灰色，hover 时变为主文字色。
            transition-colors: 颜色变化有过渡动画（150ms），视觉上更平滑。
          */}
          <Link to="/" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
            Browse
          </Link>

          {/*
            =======================================================================
            4. 条件渲染：isAuthenticated ? 登录后 UI : 登录前 UI
            =======================================================================
            为什么使用内联三元表达式而不是拆分成两个独立组件？
              理由：认证状态仅影响导航栏右侧的一小块区域（几个链接和按钮），
              逻辑足够简单，不需要抽象成单独组件来增加文件数量和心智负担。
              如果未来登录后/前的 UI 变得非常复杂（如各自有子菜单、下拉等），
              再抽成 <LoggedInMenu /> / <LoggedOutMenu /> 即可。
          */}
          {isAuthenticated ? (
            // ---------- 登录后：显示 Create 链接 + 用户名 + Logout 按钮 ----------
            <>
              <Link
                to="/create"
                className="text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                Create
              </Link>
              <div className="flex items-center gap-3">
                {/*
                  user?.username: 使用可选链 (?.) 防止 user 为 null/undefined 时报错。
                  Zustand store 的类型定义中 user 可能是 User | null。
                */}
                <span className="text-sm text-muted-foreground">
                  {user?.username}
                </span>
                {/*
                  =================================================================
                  5. Button 变体 (variants) 说明
                  =================================================================
                  variant="outline": 次要操作 — 边框 + 透明背景 + hover 背景色。
                    logout 不是用户的主要目标，视觉上不应抢占注意力。
                  size="sm": 小尺寸 (h-9)，与导航栏尺度匹配。

                  onClick 中使用 navigate("/") 而非 <Link>：
                    logout 是**副作用驱动的操作** — 先调用 logout() 清除认证状态，
                    再跳转到首页。如果用 <Link>，用户点击后页面立即跳转，
                    logout 可能来不及执行（或者需要复杂的 onClick + preventDefault）。
                    因此使用 Button + onClick 命令式处理更合适。
                */}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    logout();
                    navigate("/");
                  }}
                >
                  Logout
                </Button>
              </div>
            </>
          ) : (
            // ---------- 登录前：显示 Login + Sign Up 按钮 ----------
            <div className="flex items-center gap-2">
              {/*
                variant="ghost": 幽灵按钮 — 透明背景，hover 时才显示背景色。
                  适合 Login 这样的次级 CTA（Call To Action），不抢占 Sign Up 的视觉权重。
                navigate("/login"): 命令式跳转（点击按钮后跳转到登录页）。
                  Button 不是导航链接，语义上就是点击触发动作，用 navigate 更自然。
              */}
              <Button variant="ghost" size="sm" onClick={() => navigate("/login")}>
                Login
              </Button>
              {/*
                无 variant prop = 使用默认 variant="default"（由 CVA 的 defaultVariants 配置）。
                default variant = bg-primary 实心主色按钮，视觉上最突出。
                Sign Up 是主要的 CTA，应使用最醒目的按钮样式引导用户操作。
              */}
              <Button size="sm" onClick={() => navigate("/register")}>
                Sign Up
              </Button>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
