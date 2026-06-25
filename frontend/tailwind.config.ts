// ============================================================
// Tailwind CSS v4 配置文件（TypeScript 格式）
// ============================================================
// Tailwind CSS 是一个 Utility-First（工具优先）的 CSS 框架
// 核心理念：不写 CSS，直接使用原子化 class 组合样式
//
// 例如：
//   <div className="bg-primary text-primary-foreground rounded-lg p-4">
//   等价于传统 CSS：
//     background: hsl(var(--primary)); color: hsl(var(--primary-foreground));
//     border-radius: var(--radius); padding: 1rem;
//
// 优势：
//   - 零上下文切换：样式写在 HTML 中，无需切换 .css 文件
//   - 内置设计系统：颜色、间距、圆角等全部统一约束
//   - 生产构建 Tree-shaking：只保留实际使用的 class
//   - CSS 变量驱动：通过 CSS 变量实现暗色模式、主题切换
//
// 本文件配置 extends（扩展）部分，使用 shadcn/ui 的 CSS 变量体系
// ============================================================

import type { Config } from "tailwindcss";

export default {
  // ---- 内容扫描 ----
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    //           |    |    |
    //           |    |    └─ TypeScript React 组件
    //           |    └────── TypeScript 文件（可能有 className）
    //           └─────────── JavaScript React 组件
  ],
  // content 数组告诉 Tailwind 扫描哪些文件中的 className
  // 只有被扫描到的 class 才会生成对应的 CSS 规则
  // ! 注意：动态拼接的 class 名不会被扫描到！
  //   例如：className={`bg-${color}-500}` → 不会生成 bg-red-500
  //   正确做法：使用完整类名或 class 映射对象

  // ---- 主题扩展 ----
  theme: {
    extend: {
      // 【CSS 变量驱动的颜色系统】
      // 此处定义的颜色都引用 CSS 变量（hsl(var(--xxx))）
      // 这样的设计使得可以通过修改 CSS 变量值来切换主题：
      //   - 明暗模式切换：只需改变 :root 和 .dark 的 CSS 变量
      //   - 品牌色调整：修改 --primary 的 HSL 值即可全局生效
      //
      // HSL 颜色模型：Hue（色相）/ Saturation（饱和度）/ Lightness（亮度）
      // 优势：通过调整 L 值轻松实现 hover/focus 状态
      //
      // 这是 shadcn/ui 的标准颜色体系，语义化命名：
      //   primary:    主色（按钮、链接、品牌色）
      //   secondary:  辅色（次要元素）
      //   destructive: 破坏性操作（删除按钮、错误提示）
      //   muted:      弱化内容（描述文字、占位符）
      //   accent:     强调色（选中状态、高亮）
      //   background / foreground: 背景 / 前景文本
      //   card:       卡片组件专用
      //   border / input / ring: 边框 / 输入框 / 聚焦环
      //
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
          // 每个颜色 Token 有两个变体：
          //   DEFAULT:      背景色（bg-primary）
          //   foreground:   前景色/文字色（text-primary-foreground）
          // 这样保证文字在背景上始终可读（WCAG 无障碍对比度）
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },

      // 【圆角系统】
      // 使用 CSS 变量使圆角值可配置
      // 通过修改 --radius 可以全局调整组件的圆角大小
      //   lg: 组件外边框（Card、Dialog）— 直接使用 --radius
      //   md: 中圆角（Button、Input）     — --radius - 2px
      //   sm: 小圆角（Badge、Tag）        — --radius - 4px
      // 阶梯递减保持视觉层次感
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },

  // ---- 插件 ----
  plugins: [require("tailwindcss-animate")],
  // tailwindcss-animate:
  //   提供动画相关的 utility class
  //   如 animate-in、animate-out、fade-in、slide-in-from-top 等
  //   用于 shadcn/ui 组件的过渡动画（Dialog 进出场、Toast 滑入等）

} satisfies Config;
// ^^^^^^^^ satisfies 操作符（TypeScript 4.9+）
//   作用：验证对象是否符合 Config 类型，但不改变其类型推断
//   与 as Config 的区别：
//     - satisfies Config: 类型检查 + 保留原始类型推断
//       → 调用方看到的是完整的主题配置类型，而非宽泛的 Config
//     - as Config:       类型断言（强制转换），压制类型错误
//       → 调用方看到的是 Config 类型，丢失了具体配置信息
//   推荐使用 satisfies 获取更好的类型提示
