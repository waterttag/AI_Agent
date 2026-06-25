/**
 * Input 输入框组件
 *
 * 功能：基于原生 <input> 的封装组件，提供统一的项目样式，
 *       同时完全兼容原生 input 的所有属性和行为。
 *       使用 React.forwardRef 透传 DOM ref，支持文件上传样式、
 *       placeholder 样式、键盘焦点指示器、禁用状态等。
 *
 * 设计原则：
 *   不像 Button/Badge 使用 CVA（没有多样式变体需求），
 *   只有一个统一的样式定义，通过 cn() 允许用户扩展（传入 className）。
 */

import * as React from "react";
// React.forwardRef 和 React.InputHTMLAttributes 需要

import { cn } from "@/lib/utils";
// cn() = clsx + tailwind-merge — 智能合并类名

// =========================================================================
// InputProps: 类型定义
// =========================================================================
// React.InputHTMLAttributes<HTMLInputElement>:
//   继承原生 <input> 的所有 HTML 属性，包括但不限于：
//     - 通用属性: className, style, id, hidden, tabIndex, autoFocus, etc.
//     - 输入属性: type, value, defaultValue, placeholder, onChange, onInput,
//                onFocus, onBlur, readOnly, disabled, required, name, etc.
//     - 验证属性: min, max, maxLength, minLength, pattern, step, etc.
//     - 表单属性: form, formAction, formMethod, etc.
//     - 文件属性: accept, multiple (用于 type="file")
//     - 无障碍: aria-*, role
//
//   通过 extends（而非重新声明需要的属性），保证 Input 组件完全兼容原生 input —
//   开发者可以像使用 <input> 一样使用 <Input>，无需查阅文档确认"这个 prop 支持吗？"。
//
// 注意：接口体是空的 {} — 因为我们只是"声明"组件使用这个类型，
//       不需要添加额外属性。如果需要添加自定义 prop（如 error, label 等），
//       在 {} 中添加即可。
export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

// =========================================================================
// React.forwardRef 详解
// =========================================================================
// 为什么需要 forwardRef？
//   父组件可能需要直接操作 input DOM 元素，例如：
//     1. 调用 inputRef.current.focus() — 自动聚焦输入框（如搜索框弹出时）。
//     2. 调用 inputRef.current.select() — 全选输入内容。
//     3. 调用 formRef.current.reset() — 表单重置（需要原生 input 参与）。
//     4. 集成第三方库（如 react-hook-form, react-input-mask）— 这些库需要直接访问 DOM。
//     5. 测量 input 的尺寸或位置（getBoundingClientRect）。
//
//   不使用 forwardRef 的后果：
//     <Input ref={myRef} /> — myRef.current 指向的是 React 组件实例（Input），
//     而不是 <input> DOM 元素，无法调用 .focus() / .select() 等方法。
//
// 泛型参数：
//   React.forwardRef<HTMLInputElement, InputProps>
//     - HTMLInputElement: ref 类型，forwardRef 返回的 ref 为 RefObject<HTMLInputElement>
//     - InputProps: 组件 props 类型
const Input = React.forwardRef<HTMLInputElement, InputProps>(
  // 解构 props:
  //   - className: 用户自定义类名 → 与基础样式合并
  //   - type: input 类型（text, email, password, file, number 等）→ 显式解构以便透传
  //   - ...props: 其余所有原生属性 → 展开到 <input>
  //
  // 注意：type 被显式解构出来是因为它需要透传给 <input type={type}>，
  //       而不是通过 {...props} 间接传递。这样做的原因是：
  //       如果用户同时传了 type 和 {...props} 中的 type，
  //       显式的 type={type} 会覆盖展开的 type（因为它在 {...props} 之后）。
  //       实际上这与直接让 {...props} 传递 type 效果相同，
  //       但显式解构让代码意图更清晰 — "这个组件关心 type 属性"。
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        // type={type}: 透传 type 属性 — 支持 text, email, password, file, number 等。

        // ===================================================================
        // 样式详解
        // ===================================================================
        className={cn(
          // flex:
          //   将 input 设为弹性容器 — 为什么 input 需要 flex？
          //   主要是为了 file 类型：在 Chrome 中，input[type=file] 内部有一个
          //   "Choose File" 按钮，将其设为 flex 可以更好地控制内部布局。
          //   对于普通 text input，flex 不会产生负面影响（单行文本自然就一行）。
          //
          // h-10:
          //   高度 2.5rem (40px) — 与 Button 的 default size 一致，
          //   保证 input 与相邻 button 同一高度（input-group 模式）。
          //
          // w-full:
          //   宽度 100% — 填充父容器，这是表单输入的默认预期行为。
          //
          // rounded-md:
          //   border-radius 0.375rem (6px) — 与 Button 的圆角一致。
          //
          // border border-input:
          //   1px 实线边框，颜色使用 CSS 变量 --input（主题输入框边框色）。
          //
          // bg-background:
          //   背景色使用 --background — 与页面背景一致（不透明输入框）。
          //
          // px-3 py-2:
          //   水平内边距 0.75rem (12px)，垂直内边距 0.5rem (8px)。
          //   水平内边距确保文字不会紧贴边框。
          //
          // text-sm:
          //   字号 0.875rem (14px) — 与 Button 文字大小一致。
          //
          // ring-offset-background:
          //   设置 focus ring 的偏移区域颜色为背景色 —
          //   配合 focus-visible:ring-offset-2 在 ring 与 input 之间留出 2px 间隙。

          "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background " +

          // ===================================================================
          // file: 伪类 — 文件上传按钮样式
          // ===================================================================
          // Tailwind 的 file: 前缀对应 CSS 的 ::file-selector-button 伪元素 —
          // 即 input[type=file] 中的"选择文件"按钮。
          //
          // file:border-0:
          //   移除文件上传按钮的默认边框（浏览器会给它一个系统样式的边框）。
          //
          // file:bg-transparent:
          //   移除文件上传按钮的默认背景色（浏览器通常给灰色背景），
          //   让它融入输入框的整体设计中。
          //
          // file:text-sm file:font-medium:
          //   文件上传按钮的文字大小和字重与输入框主体一致。
          "file:border-0 file:bg-transparent file:text-sm file:font-medium " +

          // ===================================================================
          // placeholder: 伪类 — 占位符文字样式
          // ===================================================================
          // Tailwind 的 placeholder: 前缀对应 CSS 的 ::placeholder 伪元素。
          //
          // placeholder:text-muted-foreground:
          //   占位符文字使用"柔和的"前景色（低对比度）—
          //   视觉上明确区分"占位符提示"和"用户输入的内容"。
          //   这是一种 UX 惯例：占位符不应与真实内容有相同的视觉权重。
          "placeholder:text-muted-foreground " +

          // ===================================================================
          // focus-visible: 键盘焦点指示器
          // ===================================================================
          // 为什么使用 focus-visible: 而非 focus:？
          // ============================================================
          // focus: 在任何获取焦点的方式下都触发 —
          //   包括鼠标点击输入框。如果使用 focus:ring-2，
          //   用户每次点击输入框都会看到蓝色光环，这很干扰。
          //
          // focus-visible: 只在**键盘导航**时触发（如按 Tab 键切换到输入框）—
          //   鼠标点击不显示焦点环。这是更好的 UX：
          //     - 鼠标用户：不需要焦点环（他们知道自己点了哪里）。
          //     - 键盘用户：需要焦点环来知道当前聚焦在哪个元素。
          //
          // 浏览器判断"键盘导航"的依据：
          //   用户最近一次交互是通过键盘（Tab/Shift+Tab）而非鼠标。
          //   :focus-visible 伪类是 CSS Selectors Level 4 规范。
          //
          // focus-visible:outline-none:
          //   移除浏览器默认的 outline（通常是蓝色或黑色的粗边框），
          //   用下面自定义的 ring 替代（更美观、与设计系统一致）。
          //
          // focus-visible:ring-2:
          //   显示 2px 的 box-shadow ring —
          //   ring 相比 outline 的优势：
          //     - ring 使用 box-shadow 实现，不占据额外空间（不影响布局）。
          //     - ring 可以设置 offset（离元素边缘的距离）。
          //
          // focus-visible:ring-ring:
          //   ring 颜色使用 CSS 变量 --ring（由主题定义，通常为主色）。
          //
          // focus-visible:ring-offset-2:
          //   ring 与元素边缘之间留 2px 空白间隙 —
          //   让焦点环不紧贴输入框，视觉上更清晰。
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 " +

          // ===================================================================
          // disabled: 禁用状态样式
          // ===================================================================
          // disabled:cursor-not-allowed:
          //   鼠标悬停时显示"禁止"光标（圆圈+斜杠）—
          //   视觉反馈告诉用户"这个输入框不可用"。
          //
          // disabled:opacity-50:
          //   50% 透明度 — 让禁用的输入框"变灰"，
          //   这是一种通用的"不可用"视觉约定（与 Button 的 disabled 样式一致）。
          "disabled:cursor-not-allowed disabled:opacity-50",

          // 用户传入的自定义类名 — cn() 的 twMerge 功能会处理与基础样式的冲突
          className
        )}
        ref={ref}
        // ref={ref}: 将 forwardRef 接收的 ref 附加到 <input> DOM 元素上 —
        //   父组件可以通过 ref.current 直接访问原生 input，
        //   调用 .focus(), .select(), .value 等。

        {...props}
        // {...props}: 展开其余所有原生属性 —
        //   placeholder, value, onChange, disabled, required, name, id,
        //   aria-label, data-*, onKeyDown, onPaste, ... 全部透传给 <input>。
        //   这样 Input 组件就是原生 input 的"完全替代品"（drop-in replacement）。
      />
    );
  }
);

// displayName: React DevTools 中显示为 "Input" 而非 "ForwardRef" —
// forwardRef 内部使用箭头函数，React 无法自动推断组件名。
Input.displayName = "Input";

export { Input };
