/**
 * Badge 徽标组件
 *
 * 功能：基于 CVA (class-variance-authority) 的小型标签/徽标组件，
 *       用于展示状态、分类、计数等紧凑信息。
 *       支持 3 种变体：default（实心主色）、secondary（次要色）、outline（边框）。
 *
 * 使用场景：
 *   - 游戏标签：<Badge>RPG</Badge> <Badge variant="secondary">Puzzle</Badge>
 *   - 状态标识：<Badge variant="outline">Draft</Badge>
 *   - 版本号：<Badge variant="secondary">v1.0</Badge>
 */

import * as React from "react";

import { cva, type VariantProps } from "class-variance-authority";
// class-variance-authority (CVA):
//   专门为"变体驱动组件"设计的样式管理库。
//   核心 API：
//     cva(baseClasses, { variants: {...}, defaultVariants: {...} })
//   返回一个函数，调用时传入 variant 值即可得到合并后的 class 字符串。
//   VariantProps<typeof x> 自动从 CVA 配置推导 TypeScript 类型。
//
// 与 button.tsx 一样使用 CVA，但 Badge 没有 size 变体 —
//   因为徽标通常只有一种尺寸（text-xs + px-2.5 py-0.5），
//   保持一致的紧凑外观，不需要像按钮那样支持多种尺寸。

import { cn } from "@/lib/utils";
// cn() = clsx + tailwind-merge:
//   - clsx: 条件拼接类名
//   - twMerge: 解决 Tailwind 工具类冲突（后声明的覆盖先声明的同类）

// =========================================================================
// badgeVariants: CVA 配置
// =========================================================================
const badgeVariants = cva(
  // --- 基础样式 ---
  // inline-flex:
  //   行内弹性容器 — badge 是行内元素（inline），但又能用 flex 对齐内部的图标+文字。
  //   如果用 inline-block，内部的图标和文字无法用 flex 居中。
  //
  // items-center:
  //   交叉轴（垂直）居中 — 确保图标和文字在同一水平线上。
  //
  // rounded-full:
  //   border-radius: 9999px — 完全圆角，形成"药丸"（pill）形状。
  //   这是徽标最经典的外观 — 比 rounded-md（6px 圆角）更柔和、更"标签化"。
  //
  // border:
  //   1px 实线边框 — 所有变体都有边框（部分变体用 border-transparent 隐藏）。
  //   为什么要始终保留 border 而不是按变体条件添加？
  //   因为 border 为元素提供结构 — 即使透明，它也占用 box-sizing 的空间，
  //   保证不同变体之间的尺寸完全一致（不会因为有无边框导致大小差异）。
  //
  // px-2.5 py-0.5:
  //   水平内边距 0.625rem (10px)，垂直内边距 0.125rem (2px)。
  //   徽标应该紧贴内容 — 垂直内边距极小保证紧凑外观。
  //
  // text-xs font-semibold:
  //   字号 0.75rem (12px) — 徽标文字应该比正文小得多。
  //   字重 600 (semibold) — 小字号需要略粗才能保持可读性。
  //
  // transition-colors:
  //   颜色变化有 150ms 过渡 — hover 效果更平滑。
  //
  // focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2:
  //   注意这里用的是 focus: 而非 focus-visible: —
  //   与 Button 不同，Badge 的 intent 通常是不可交互的（纯展示），
  //   但使用 focus:（鼠标点击也显示焦点环）不会造成 UX 问题，
  //   因为 Badge 通常不接收点击事件（没有 onClick）。
  //   如果 Badge 用作可交互元素（如可点击的筛选标签），应改用 focus-visible:。
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",

  // --- 变体配置 ---
  {
    variants: {
      variant: {
        // default: 实心主色徽标 — 最突出的样式。
        //   border-transparent: 边框透明（但保留占位，保持尺寸一致）。
        //   bg-primary text-primary-foreground: 主色背景 + 主色上的文字色（通常为白色）。
        //   hover:bg-primary/80: hover 时背景变浅（80% 不透明度）。
        default:
          "border-transparent bg-primary text-primary-foreground hover:bg-primary/80",

        // secondary: 次要徽标 — 低对比度，不抢占视觉注意力。
        //   用于"不那么重要"的标签，如辅助分类、技术栈标签等。
        //   border-transparent: 同样透明边框保持尺寸一致。
        //   hover:bg-secondary/80: hover 时略微变浅。
        secondary:
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",

        // outline: 轮廓徽标 — 仅边框 + 透明背景。
        //   最轻量的样式，用于"中性"标签（如状态、类型标记）。
        //   text-foreground: 使用前景色（正常文字色），不像 default/secondary 有专属配色。
        //   没有 hover 效果 — outline 通常表示静态信息，不需要交互反馈。
        outline: "text-foreground",
      },
    },

    // 默认变体：使用者不传 variant prop 时使用 default 样式
    defaultVariants: { variant: "default" },
  }
);

// =========================================================================
// BadgeProps: 类型定义
// =========================================================================
// extends 两种类型的交集：
//   1. React.HTMLAttributes<HTMLDivElement>
//      → 所有 div 原生属性：className, style, id, children, on*, aria-* 等。
//        渲染为 <div> 而非 <span> —
//        因为 Badge 内部可能包含图标、文字等多个子元素，
//        <div> 作为块级容器的语义比 <span>（纯文本容器）更合适。
//
//   2. VariantProps<typeof badgeVariants>
//      → CVA 自动推导的变体类型，等价于：
//        { variant?: "default" | "secondary" | "outline" }
//      VariantProps 保证类型与 CVA 配置始终同步 —
//      新增或修改 variant 后无需手动更新接口定义。
export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

// =========================================================================
// Badge 组件
// =========================================================================
// 注意：这里没有使用 React.forwardRef —
// 为什么？Badge 通常作为纯展示组件使用，调用者很少需要获取其 DOM 引用。
// 如果未来需要 ref（如用于测量尺寸或动画），可以改为 forwardRef。
//
// 解构 props:
//   - className: 用户自定义类名 → 通过 cn() 与 CVA 生成的类合并。
//   - variant: CVA 变体 → 传给 badgeVariants()。
//   - ...props: 其余所有 HTML 属性 → 展开到 <div> 上。
function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div
      // cn() 合并逻辑：
      //   1. badgeVariants({ variant }) — CVA 生成基础样式 + 指定变体的样式。
      //      如果未传 variant，CVA 使用 defaultVariants: { variant: "default" }。
      //   2. className — 用户额外传入的类名。
      //   3. cn() 通过 twMerge 解决冲突 —
      //      例如用户传入 "bg-red-500"，twMerge 会用它覆盖 CVA 的 bg-primary。
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  );
}

// 导出 Badge 组件和 badgeVariants 函数
// badgeVariants 也导出，允许其他组件复用 Badge 的样式：
//   例如：<span className={badgeVariants({ variant: "secondary" })}>Custom</span>
export { Badge, badgeVariants };
