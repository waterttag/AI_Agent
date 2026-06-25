/**
 * Card 卡片组件（复合组件模式 / Compound Component Pattern）
 *
 * 功能：一套语义化的卡片 UI 组件，包含容器、头部、标题、描述、内容区、底部操作区。
 *       采用"复合组件"模式：Card.Title, Card.Description, Card.Content 等子组件
 *       既可以独立使用，也可以组合在一起形成完整的卡片。
 *
 * 复合组件模式 vs Context 模式：
 *   这里的子组件不需要共享状态（如 isOpen、selectedItem），
 *   它们只是视觉上的搭配，各自独立渲染，因此**不需要 React Context**。
 *   简单组合（Composition）就足够了 — 相比 Context 模式更轻量、更直观。
 *
 * 每个子组件都使用 React.forwardRef 以支持父组件获取底层 DOM 元素的引用。
 */

import * as React from "react";
// React.forwardRef 和 React.HTMLAttributes 需要 React 命名空间

import { cn } from "@/lib/utils";
// cn(): clsx + tailwind-merge — 智能合并类名，自动解决 Tailwind 工具类冲突。

// =========================================================================
// Card — 卡片容器
// =========================================================================
// 泛型：forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>
//   - 第一个泛型 HTMLDivElement: ref 指向 <div> DOM 元素。
//   - 第二个泛型 React.HTMLAttributes<HTMLDivElement>:
//     接收所有标准 div 属性（className, style, id, children, on*, aria-* 等）。
//
// 样式解析：
//   - rounded-lg: border-radius 0.5rem (8px) — 大圆角，现代卡片风格。
//   - border border-border: 1px 实线边框，颜色使用 CSS 变量 --border（主题色）。
//   - bg-card text-card-foreground: 背景色和文字色使用 Shadcn/ui 约定的语义化 CSS 变量名。
//     --card 和 --card-foreground 由全局主题定义。
//   - shadow-sm: 微小阴影（0 1px 2px 0 rgb(0 0 0 / 0.05)）— 轻微浮起效果。
const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("rounded-lg border border-border bg-card text-card-foreground shadow-sm", className)} {...props} />
  )
);
// displayName: React DevTools 中显示为 <Card> 而非 "ForwardRef"。
Card.displayName = "Card";

// =========================================================================
// CardHeader — 卡片头部
// =========================================================================
// 布局：flex flex-col（纵向排列），内部元素通过 space-y-1.5 获得垂直间距。
//
// space-y-1.5:
//   CSS 等价于：.card-header > * + * { margin-top: 0.375rem; }
//   仅在**相邻兄弟元素之间**添加间距（第一个元素上方无 margin），这是 CSS 的
//   "相邻兄弟选择器"（adjacent sibling combinator, `+`）模式。
//   比给每个元素加 margin-bottom 更优雅 — 不会在最后一个元素下方产生多余间距。
//
// p-6: 内边距 1.5rem (24px) — 给卡片内容足够的呼吸空间。
const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col space-y-1.5 p-6", className)} {...props} />
  )
);
CardHeader.displayName = "CardHeader";

// =========================================================================
// CardTitle — 卡片标题
// =========================================================================
// 渲染为 <h3> 语义标签（标题层级第三级），利于 SEO 和无障碍访问。
// 屏幕阅读器会根据标题层级（h1→h2→h3→...）构建页面大纲。
//
// 样式解析：
//   - text-2xl: 字号 1.5rem (24px) — 卡片标题需要比正文明显大。
//   - font-semibold: 字重 600 — 半粗体，比正常粗但不如 bold (700) 重。
//   - leading-none: line-height: 1 — 多行标题时行间距紧凑。
//     （注意：单行标题时使用 leading-none 可精确控制卡片高度）
//   - tracking-tight: letter-spacing: -0.025em — 轻微收紧字间距，
//     大字号文字收紧字间距更显精致（Apple 设计哲学）。
const CardTitle = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3 ref={ref} className={cn("text-2xl font-semibold leading-none tracking-tight", className)} {...props} />
  )
);
CardTitle.displayName = "CardTitle";

// =========================================================================
// CardDescription — 卡片描述文字
// =========================================================================
// 渲染为 <p> 段落标签，用于标题下方的说明文字。
//
// text-sm: 字号 0.875rem (14px) — 比正文小，表达辅助信息。
// text-muted-foreground: 低对比度颜色 — "muted"（柔和的），
//   告诉用户这是次要信息，不需要第一时间阅读。
const CardDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p ref={ref} className={cn("text-sm text-muted-foreground", className)} {...props} />
  )
);
CardDescription.displayName = "CardDescription";

// =========================================================================
// CardContent — 卡片主体内容区
// =========================================================================
// p-6 pt-0: 四周内边距 1.5rem，但**顶部内边距为 0**。
//
// 为什么 pt-0（移除顶部内边距）？
//   因为 CardContent 通常紧跟在 CardHeader 后面，
//   CardHeader 的底部内边距 (p-6) 已经提供了足够的间距，
//   如果 CardContent 也有顶部内边距，会导致间距加倍，视觉上不协调。
//   这是 Shadcn/ui 卡片系统的约定：Header → Content → Footer 无缝衔接。
//
//   如果 CardContent 是卡片的第一个子元素（没有 CardHeader），
//   那么"缺少顶部内边距"需要调用者自行通过 className 补充：
//     <CardContent className="pt-6">...</CardContent>
const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
  )
);
CardContent.displayName = "CardContent";

// =========================================================================
// CardFooter — 卡片底部操作区
// =========================================================================
// flex items-center: 弹性布局，子元素垂直居中。
//   这使按钮、链接等在底部水平排列并对齐。
//
// p-6 pt-0: 与 CardContent 同理 — 移除顶部内边距以避免与上方内容的间距加倍。
//
// 典型用法：
//   <CardFooter>
//     <Button variant="outline">Cancel</Button>
//     <Button>Submit</Button>
//   </CardFooter>
const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex items-center p-6 pt-0", className)} {...props} />
  )
);
CardFooter.displayName = "CardFooter";

// =========================================================================
// 复合组件模式的导出和使用
// =========================================================================
// 所有子组件作为独立命名导出（named exports），使用者可以按需导入：
//   import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
//
// 使用时通过 . 语法组合（因为它们是同一模块的导出，而非 Card 的静态属性）：
//   <Card>
//     <CardHeader>
//       <CardTitle>标题</CardTitle>
//       <CardDescription>描述文字</CardDescription>
//     </CardHeader>
//     <CardContent>内容</CardContent>
//     <CardFooter>
//       <Button>操作</Button>
//     </CardFooter>
//   </Card>
//
// 注意：这里的导出方式是扁平的 named exports，而非 Card.Header = CardHeader。
// 两种方式都是复合组件模式的有效实现，扁平导出更利于 tree-shaking
// （未使用的子组件不会被打包）。
export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent };
