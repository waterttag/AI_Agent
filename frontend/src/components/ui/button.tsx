/**
 * Button 按钮组件
 *
 * 功能：基于 CVA (class-variance-authority) 构建的类型安全、变体驱动的按钮组件。
 *       支持 6 种视觉变体（default, destructive, outline, secondary, ghost, link）
 *       和 4 种尺寸（default, sm, lg, icon），并提供完整的 TypeScript 类型推导。
 *
 * 技术核心：
 *   1. CVA (class-variance-authority) — 变体样式的"真理之源"
 *   2. React.forwardRef — 透传 DOM ref 给底层 <button> 元素
 *   3. cn() (clsx + twMerge) — 智能合并 Tailwind 类名，解决样式冲突
 */

import * as React from "react";
// React.forwardRef 需要 React 命名空间

import { cva, type VariantProps } from "class-variance-authority";
// class-variance-authority (CVA) 是什么？
// ============================================================
// CVA 是一个专门为"变体驱动组件"设计的样式管理库。
// 它的核心思想：你定义**一个**基础样式 + 若干变体（variants）+ 默认值（defaultVariants），
// CVA 返回一个函数，调用该函数传入变体名即可得到合并后的 class 字符串。
//
// 概念模型：
//   cva(baseClasses, {
//     variants: { variant: { ... }, size: { ... } },
//     defaultVariants: { variant: "...", size: "..." }
//   })
//
// 返回的函数使用方式：
//   buttonVariants()                          → 只有 baseClasses + 默认变体的类
//   buttonVariants({ variant: "outline" })    → baseClasses + outline 变体类 + 默认 size
//   buttonVariants({ variant: "ghost", size: "sm" }) → baseClasses + ghost + sm
//
// 为什么用 CVA 而不是手动拼接 className？
// ============================================================
// 1. 避免巨大的条件类名字符串 — 不用写：
//      className={`base ${variant === "outline" ? "border..." : variant === "ghost" ? "..." : "..."}`}
//    这种代码难以维护、容易出错、没有类型检查。
// 2. TypeScript 自动补全 — VariantProps<typeof buttonVariants> 会从 CVA 配置中
//    自动推导出 variant?: "default" | "destructive" | "outline" | ...，
//    不需要手动维护类型定义。修改 variants 配置后，类型自动更新。
// 3. 单一真理之源 — 所有按钮样式集中在一个 cva() 调用中，
//    新增或修改变体只需改动一处，不会出现某个文件的按钮样式漏改的情况。
// 4. 消除 Tailwind 类名重复 — 同一个 baseClasses 不会在多个地方复制粘贴。

import { cn } from "@/lib/utils";
// cn() 是 clsx + tailwind-merge 的组合：
//   - clsx: 条件拼接类名（如 cn("a", false && "b", "c") → "a c"）
//   - tailwind-merge (twMerge): 解决 Tailwind 类名冲突
//     （如 cn("px-2 py-1", "p-4") → "p-4" — 后面的 p-4 覆盖前面的 px-2 py-1）

// =========================================================================
// CVA 配置详解：buttonVariants
// =========================================================================
const buttonVariants = cva(
  // --- 基础样式（base classes）---
  // 无论什么 variant 和 size，这些类始终生效：
  //
  // inline-flex:
  //   将 button 设为行内弹性容器。为什么不用 block 或 inline-block？
  //   因为按钮通常包含图标 + 文字，需要用 flex 来对齐。
  //   inline-flex（而非 flex）确保按钮与其他行内元素（文字、其他按钮）在同一行时
  //   不会独占一行（flex 是块级，inline-flex 是行内块级）。
  //
  // items-center justify-center:
  //   flex 子元素在交叉轴（垂直）和主轴（水平）上都居中。
  //
  // whitespace-nowrap:
  //   禁止文字换行 — 按钮文字应该始终在单行显示，换行会破坏按钮的外观一致性。
  //
  // rounded-md:
  //   border-radius: 0.375rem（6px）— 中等圆角，视觉上友好但不幼稚。
  //
  // text-sm font-medium:
  //   字号 0.875rem（14px），字重 500 — 按钮文字需要比正文略重以突出可点击性。
  //
  // ring-offset-background:
  //   设置 focus ring 的偏移区域颜色为背景色 —
  //   配合 focus-visible:ring-offset-2 使用，在 ring 和元素之间留出 2px 的白色/背景色间隙。
  //
  // transition-colors:
  //   颜色属性（background-color, border-color, color, fill, stroke）变化时
  //   添加 150ms 的过渡动画，让 hover/focus 状态切换更平滑。
  //
  // focus-visible:outline-none:
  //   使用 focus-visible 而非 focus: — 关键区别！
  //     - focus: 任何方式获得焦点都触发（鼠标点击也会显示焦点环）。
  //     - focus-visible: 仅键盘导航（Tab 键）时触发，鼠标点击不显示。
  //     这是更好的 UX：鼠标用户不需要看到焦点环，键盘用户需要。
  //     移除浏览器默认的 outline 是为了用自定义的 ring 替代（下面两行）。
  //
  // focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2:
  //   自定义键盘焦点指示器：
  //     - ring-2: 2px 的 box-shadow ring（不像 outline 那样改变元素尺寸）。
  //     - ring-ring: ring 颜色使用 CSS 变量 --ring（由主题定义）。
  //     - ring-offset-2: ring 与元素边缘之间留 2px 间隙。
  //
  // disabled:pointer-events-none disabled:opacity-50:
  //   - pointer-events-none: 禁用状态时阻止所有鼠标/触摸事件（无法点击）。
  //   - opacity-50: 半透明表示不可用（50% 透明度），这是通用的"禁用"视觉约定。
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",

  // --- 变体配置（variants config）---
  {
    variants: {
      // ===================================================================
      // variant: 视觉风格变体（6 种）
      // 每个 key 的值是一组 Tailwind 类名字符串，
      // 会与 base 类合并，覆盖同名的 Tailwind 工具类（由 twMerge 处理）。
      // ===================================================================
      variant: {
        // default: 主按钮 — 实心背景 + 主色文字。
        //   用于页面最主要的 CTA（如"提交"、"保存"、"Sign Up"）。
        //   hover:bg-primary/90: hover 时背景变暗 10%（90% 不透明度），给用户点击反馈。
        default: "bg-primary text-primary-foreground hover:bg-primary/90",

        // destructive: 危险操作按钮 — 红色背景。
        //   用于删除、移除等不可逆操作，红色是最通用的"警告/危险"颜色。
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90",

        // outline: 轮廓按钮 — 边框 + 透明背景。
        //   用于次要操作（如"取消"、"Logout"），视觉权重低于 primary。
        //   hover:bg-accent hover:text-accent-foreground: hover 时出现浅色背景。
        outline:
          "border border-input bg-background hover:bg-accent hover:text-accent-foreground",

        // secondary: 次要按钮 — 低对比度背景。
        //   比 outline 更有"实体感"但不是主色，用于非主要的正向操作。
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",

        // ghost: 幽灵按钮 — 完全透明，hover 时才显示背景。
        //   用于最低优先级的操作（如导航栏中的 Login 链接按钮），
        //   不影响页面视觉层次，hover 时轻声出现。
        ghost: "hover:bg-accent hover:text-accent-foreground",

        // link: 链接风格按钮 — 看起来像超链接。
        //   underline-offset-4: 下划线与文字间距 4px。
        //   hover:underline: hover 时才显示下划线（避免视觉噪音）。
        link: "text-primary underline-offset-4 hover:underline",
      },

      // ===================================================================
      // size: 尺寸变体（4 种）
      // "default" 是基准尺寸，其他尺寸调整高度、内边距、圆角。
      // ===================================================================
      size: {
        // default: 标准尺寸 — 高度 2.5rem (40px)，标准内边距。
        default: "h-10 px-4 py-2",

        // sm: 小尺寸 — 高度 2.25rem (36px)，略小内边距。
        //   用于导航栏、表格行内、卡片 footer 等紧凑场景。
        sm: "h-9 rounded-md px-3",

        // lg: 大尺寸 — 高度 2.75rem (44px)，更大内边距。
        //   用于 Hero 区域的 CTA、登录页主按钮等强调场景。
        lg: "h-11 rounded-md px-8",

        // icon: 正方形图标按钮 — 宽高均为 2.5rem (40px)。
        //   用于仅包含图标的按钮（如关闭按钮、菜单切换）。
        //   无内边距（图标通过 flex + items-center + justify-center 自动居中）。
        icon: "h-10 w-10",
      },
    },

    // --- 默认变体值 ---
    // 当使用时未指定 variant 或 size 时，自动使用这些值。
    // 例如 <Button>Click</Button> 等于 <Button variant="default" size="default">Click</Button>
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

// =========================================================================
// ButtonProps 接口定义
// =========================================================================
// 通过 extends 组合两种类型：
//   1. React.ButtonHTMLAttributes<HTMLButtonElement>
//      → 继承原生 <button> 的所有 HTML 属性：
//        onClick, disabled, type (submit/button/reset), autoFocus, form, name, value 等。
//      这样使用者可以像原生 button 一样传递任何标准属性。
//
//   2. VariantProps<typeof buttonVariants>
//      → CVA 自动从 buttonVariants 的 variants 配置中推导出的类型。
//      实际上等价于：
//        { variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";
//          size?: "default" | "sm" | "lg" | "icon" }
//      修改 CVA 配置后，这个类型自动更新，不需要手动维护！
//      VariantProps 让 TypeScript 根据 cva() 的实际配置推导类型，
//      保证了"单一真理之源"——改 cva() 的 variants，类型自动同步。
export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

// =========================================================================
// React.forwardRef 深度解析
// =========================================================================
// forwardRef 是什么？
//   React 的一个高阶函数，允许父组件传递 ref 给子组件内部的 DOM 元素。
//
// 为什么需要 forwardRef？
//   在 React 中，ref 是一个特殊的 prop，不会被作为普通 prop 传递给子组件。
//   如果你这样写：
//     function Button(props) { return <button {...props} /> }
//     <Button ref={myRef} />  // myRef 不会附加到 <button> 上！
//   而 forwardRef 解决了这个问题 — 它接收 (props, ref) 两个参数，
//   第二个参数 ref 可以被手动附加到内部的 DOM 元素上。
//
// 实际使用场景：
//   - 焦点管理：父组件需要调用 buttonRef.current.focus() 来聚焦按钮。
//   - 滚动到视图：buttonRef.current.scrollIntoView()。
//   - 测量尺寸：buttonRef.current.getBoundingClientRect()。
//   - 与第三方库集成：如 react-aria、Framer Motion 等需要直接访问 DOM。
//
// 泛型参数说明：
//   React.forwardRef<HTMLButtonElement, ButtonProps>
//     - 第一个泛型 HTMLButtonElement: ref 指向的 DOM 元素类型。
//       forwardRef 返回的 ref 类型会是 RefObject<HTMLButtonElement>。
//     - 第二个泛型 ButtonProps: 组件接收的 props 类型。
//       决定了调用 <Button ...> 时有哪些可用的 prop。
const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  // 解构 props:
  //   - className: 用户传入的自定义类名（会通过 cn() 与 CVA 生成的类合并）
  //   - variant, size: CVA 变体 prop（传给 buttonVariants()）
  //   - ...props: 其余所有原生 button 属性（onClick, disabled, type, aria-*, 等）
  ({ className, variant, size, ...props }, ref) => {
    return (
      <button
        // cn() 合并逻辑：
        //   1. buttonVariants({ variant, size }) — CVA 生成基础 + 变体类名
        //   2. className — 用户额外传入的类名
        //   3. cn() 通过 twMerge 解决冲突（如 buttonVariants 给了 px-4，用户传了 px-8，
        //      twMerge 会让后者覆盖前者，而不是两个都保留造成不可预测的行为）
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        // ref={ref}: 将 forwardRef 接收的 ref 附加到 <button> DOM 元素 —
        //   这就是 forwardRef 的核心目的：把父组件的 ref 透传到真实的 DOM 节点。
        {...props}
        // {...props}: 展开其余所有原生属性（onClick, type, disabled, aria-label 等），
        // 确保组件完全兼容原生 button 的行为。
      />
    );
  }
);

// =========================================================================
// displayName：React DevTools 中的显示名称
// =========================================================================
// 为什么需要 displayName？
//   forwardRef 返回的是一个匿名组件（没有函数名），在 React DevTools 中会显示为
//   "ForwardRef" 而不是 "Button"，这会让调试变得困难。
//   设置 displayName = "Button" 后，DevTools 组件树中显示为 <Button>，
//   清晰表明这是什么组件。
//
// 注意：如果使用具名函数（function Button(...)），React DevTools 可以自动推断名称，
// 但 forwardRef 内部通常是箭头函数，因此需要手动设置 displayName。
Button.displayName = "Button";

// 导出 Button 组件和 buttonVariants 函数
// buttonVariants 也导出，以便其他组件需要复用按钮样式时直接调用。
// 例如：<Link className={buttonVariants({ variant: "ghost", size: "sm" })}>...</Link>
export { Button, buttonVariants };
