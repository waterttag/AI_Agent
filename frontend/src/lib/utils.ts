/**
 * ============================================================================
 * utils.ts — 通用工具函数集合
 * ============================================================================
 *
 * 【文件职责】
 * 提供项目级通用工具函数：CSS 类名合并（cn）、日期格式化（formatDate）、
 * MinIO URL 透传（getMinioUrl）。
 *
 * 这些函数在项目中被广泛复用，集中管理避免重复实现，且便于未来统一修改。
 */

import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

// ============================================================================
// 1. cn() — CSS 类名智能合并（clsx + tailwind-merge）
// ============================================================================

/**
 * 【WHAT】cn() 函数将传入的任意多个 CSS 类名参数合并为一个字符串，
 *         并智能解决 Tailwind CSS 中同属性类的冲突问题。
 *
 * 【处理流程】
 *   cn("px-4", "py-2")          → 先 clsx 合并 → "px-4 py-2"
 *                                          → 再 twMerge 去冲突 → "px-4 py-2"
 *   cn("px-4", "p-6")           → "px-4 p-6"
 *                                          → twMerge 发现 p-6 是 px-4 的简写，输出 "p-6"
 *   cn("text-red-500", false && "hidden") → clsx 过滤 falsy → "text-red-500"
 *   cn("bg-red-500", { "bg-blue-500": true }) → clsx 处理对象 → "bg-red-500 bg-blue-500"
 *                                          → twMerge 解决冲突 → "bg-blue-500"
 *
 * 【WHY — 为什么要合并 clsx 和 tailwind-merge 两步？】
 *
 * 这是现代 shadcn/ui 项目中的标准模式（shadcn/ui 官方模板即使用 cn() 函数）：
 *
 * 第一步 — clsx（条件类名拼接）：
 *   clsx 是一个轻量工具（~300B），用于条件性地拼接 CSS 类名：
 *   - 自动过滤 falsy 值（null, undefined, false, 0, ""）→ 无需写三元表达式
 *   - 支持字符串、对象 { key: boolean }、数组嵌套组合
 *   - 示例: clsx("btn", isActive && "active", { "disabled": !enabled })
 *           → isActive=true, enabled=false → "btn active disabled"
 *   - 相比手写模板字符串 `${...} ${...}`，clsx 更简洁且不会留下多余空格
 *
 * 第二步 — tailwind-merge (twMerge)（类名冲突解决）：
 *   WHY 需要它 — Tailwind 的"实用优先"（Utility-First）理念带来的问题：
 *     Tailwind 鼓励每个类名只负责一个 CSS 属性，开发中常出现这样的场景：
 *     - 基础组件定义：<Button className="px-4 py-2 bg-blue-500" />
 *     - 使用时覆盖：  <Button className="px-6 bg-red-500" />
 *     - 最终类名：    "px-4 py-2 bg-blue-500 px-6 bg-red-500"
 *     - CSS 中的优先级：后出现的类不一定覆盖先出现的（取决于 CSS 优先级规则，
 *       而不仅是出现顺序！px-4 和 px-6 的 CSS 选择器优先级相同，后面的确实覆盖前面的
 *       ——但在某些情况下，base 层和 utilities 层的优先级会不同）
 *
 *     更关键的问题：当 className 字符串中存在 "px-4 p-6" 时，
 *     p-6 设置了 padding（四边），px-4 设置了 padding-left + padding-right，
 *     由于 CSS 中两个类选择器优先级相同，后面的会覆盖前面的，
 *     所以最终 padding-left/right 的值取决于 px-4 和 p-6 在 HTML class 属性中的顺序。
 *     这种不确定性会导致难以调试的样式 bug。
 *
 *     twMerge 的作用：它真正理解 Tailwind 的设计令牌（design token）体系：
 *     - 知道 p-6 是 px-4 + py-6，当两者同时出现时保留 p-6（或后面出现的那个）
 *     - 知道 text-red-500 和 text-blue-500 是同一属性，取后者
 *     - 知道 w-1/2 和 w-full 是同一属性，取后者
 *     - 能够处理任意顺序的输入，输出确定性的结果
 *
 *   twMerge 的工作原理（非简单字符串去重）：
 *     1) 内置 Tailwind 所有 utility class 的知识图谱（通过 tailwind-merge 库维护）
 *     2) 将每个类名归入其 CSS 属性组（如 "padding" / "text-color" / "width"）
 *     3) 同一组内按出现顺序，后面的覆盖前面的
 *     4) 不同的组之间保留所有值
 *     5) 最终输出只保留每组中最后一个出现的类名
 *
 *   举例：
 *     输入: "px-2 py-3 px-4 pt-2 p-6 text-sm text-lg"
 *     twMerge 内部分组:
 *       padding 组:    px-2, py-3, px-4, pt-2, p-6 → 最终保留 p-6（最后出现）
 *       font-size 组:  text-sm, text-lg → 最终保留 text-lg
 *     输出: "p-6 text-lg"
 *
 * 【WHERE — 使用场景】
 *   在组件中接收外部 className prop 并需要与内部默认类名合并时：
 *
 *   interface ButtonProps {
 *     className?: string;  // 外部传入的覆盖样式
 *   }
 *
 *   function Button({ className }: ButtonProps) {
 *     return (
 *       <button
 *         className={cn(
 *           "px-4 py-2 rounded bg-blue-500 text-white",  // 默认样式
 *           className                                       // 外部覆盖样式
 *         )}
 *       >
 *         Click me
 *       </button>
 *     );
 *   }
 *
 *   // 使用：
 *   <Button className="bg-red-500 px-6" />
 *   // 最终渲染: className="px-6 py-2 rounded bg-red-500 text-white"
 *   // px-6 覆盖了 px-4（padding 组），bg-red-500 覆盖了 bg-blue-500（bg 组）
 */
export function cn(...inputs: ClassValue[]) {
  /**
   * 1. clsx(inputs) — 将展开的 inputs 数组合并为一个去除了 falsy 值的字符串
   * 2. twMerge(...) — 对合并后的类名字符串进行 Tailwind 冲突消解
   * 3. 返回最终确定性的、无冲突的类名字符串
   */
  return twMerge(clsx(inputs));
}

// ============================================================================
// 2. formatDate() — 日期格式化
// ============================================================================

/**
 * 【WHAT】将 ISO 日期字符串格式化为人类可读的美式英文短日期格式。
 *
 * 【示例】
 *   formatDate("2026-06-25T10:30:00Z") → "Jun 25, 2026"
 *   formatDate("2026-01-03T00:00:00Z") → "Jan 3, 2026"
 *
 * 【WHY — 为何使用 Intl.DateTimeFormat 而非手动字符串拼接】
 * - 国际化内置：Intl.DateTimeFormat 是 ECMAScript 国际化 API（ECMA-402）的一部分，
 *   所有现代浏览器和 Node.js 原生支持，无需引入 moment.js/dayjs 等第三方库。
 * - 本地化感知（locale-aware）：虽然这里固定 en-US，但将来可轻松切换为 "zh-CN"
 *   以输出 "2026年6月25日"，只需改一个参数。
 * - 月份名称为标准缩写：Jan, Feb, Mar... 无需维护月份映射表。
 * - 自动处理时区：默认使用用户本地时区显示日期（也可显式指定 timeZone）。
 *
 * 【技术知识 — toLocaleDateString vs toLocaleString vs Intl.DateTimeFormat】
 * - toLocaleDateString(locale, options): 仅日期部分，快捷但每次调用创建 Intl 实例
 * - toLocaleString(locale, options): 日期 + 时间
 * - new Intl.DateTimeFormat(locale, options).format(date): 底层 API，
 *   可复用 formatter 实例（批量格式化时性能更好）
 * - 这里每次只格式化一个日期，直接使用 toLocaleDateString 即可
 *
 * @param dateStr ISO 8601 格式的日期字符串（如 "2026-06-25T10:30:00Z"）
 * @returns 格式化后的日期字符串（如 "Jun 25, 2026"）
 */
export function formatDate(dateStr: string): string {
  /**
   * 使用 en-US locale 和美式日期格式：
   * - year: "numeric"  → 完整年份（2026，非 "26"）
   * - month: "short"   → 三字母英文缩写月份（Jan/Feb/Mar...）
   * - day: "numeric"   → 不带前导零的日期（3，非 "03"）
   *
   * 不包含的时间部分：hour/min/second，因为只展示日期即可满足项目需求
   * （游戏列表发布时间、评论日期等）。
   */
  return new Date(dateStr).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// ============================================================================
// 3. getMinioUrl() — MinIO 资源 URL 透传
// ============================================================================

/**
 * 【WHAT】直接返回后端传来的 game_url 字符串，不做任何处理。
 *
 * 【WHY — 为何保留一个看似"什么都不做"的函数】
 *
 * 这是一个有意的抽象层（Abstraction Layer）设计决策：
 *
 * 1. 当前状态（直接透传）：
 *    后端返回的 game_url 已经是完整的 MinIO 预签名 URL（presigned URL），
 *    格式如: http://localhost:9000/aigame/game-files/uuid/index.html?X-Amz-...
 *    前端可以直接使用，无需拼接 base path 或添加 query 参数。
 *
 * 2. 未来可能的变更（保留此函数的意义）：
 *    假设将来发生以下任一变化：
 *    - MinIO 从 localhost:9000 迁移到 CDN 域名（cdn.example.com/games/...）
 *    - 后端改为只返回文件 key（如 "game-files/uuid/index.html"），前端需要拼接
 *    - URL 格式从预签名 URL 变为普通公开 URL
 *    - 需要添加缓存破坏参数（cache-busting）：`${gameUrl}?v=${version}`
 *    - 需要统一添加 CORS 代理前缀
 *    - 需要替换 URL 中的域名（开发环境 vs 生产环境）
 *
 *    如果业务代码中直接使用 game_url 字符串（没有此函数），上述任何变更都需要
 *    修改所有引用 game_url 的地方，可能达数十处，极易遗漏导致线上 Bug。
 *
 *    而有了 getMinioUrl() 抽象层，所有修改只需在此一处完成 ——
 *    这就是软件工程中"封装变化"（Encapsulate what varies）原则的具体实践。
 *
 * 3. 语义清晰：
 *    调用 getMinioUrl(game.url) 比直接写 game.url 更明确地表达意图：
 *    "获取这个游戏的 MinIO 资源 URL"，而非"取这个对象的 url 字段"。
 *    代码可读性和自解释性（self-documenting）更强。
 *
 * 【技术知识 — MinIO 预签名 URL】
 * - MinIO 是兼容 AWS S3 API 的开源对象存储服务
 * - 预签名 URL（Presigned URL）是带有临时签名的访问链接，在有效期内无需额外认证
 *   即可访问私有 Bucket 中的对象
 * - 适用于本项目的游戏文件（HTML/JS/CSS 等静态资源）分发场景
 * - 后端生成签名 URL 后返回给前端，前端直接嵌入 iframe 或作为链接使用
 *
 * @param gameUrl 后端返回的完整 MinIO 资源 URL（通常是预签名 URL）
 * @returns 直接透传的 URL 字符串
 */
export function getMinioUrl(gameUrl: string): string {
  // game_url from backend is already a full MinIO URL（后端已经返回完整 MinIO URL）
  return gameUrl;
}
