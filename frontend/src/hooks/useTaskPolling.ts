/**
 * useTaskPolling.ts — AI 生成任务自适应轮询 hook
 *
 * 【核心概念：自适应轮询（Adaptive Polling）】
 * 使用 TanStack Query 的 refetchInterval 回调形式实现"智能轮询"——
 * 不是固定间隔一直请求，而是根据任务状态动态调整：
 * - 无数据（首次加载）→ 每 2000ms 轮询（快速获取初始状态）
 * - 任务进行中（pending/processing）→ 每 2000ms 轮询（跟踪进度）
 * - 任务完成/失败 → 停止轮询（节省带宽和服务器资源）
 *
 * 【为什么用 refetchInterval 回调函数而非常量数值？】
 * TanStack Query 的 refetchInterval 支持两种形式：
 *
 *   1. refetchInterval: 3000  （常量数字）
 *      —— 永远每隔 3000ms 请求一次，永不停止
 *      —— 问题：任务完成后仍在无效轮询，浪费带宽和服务器资源
 *      —— 适用场景：需要持续刷新的实时数据（如股票行情）
 *
 *   2. refetchInterval: (query) => number | false  （回调函数）
 *      —— 每次 refetch 后调用此函数，根据返回值决定下次间隔
 *      —— 返回 number：表示 N 毫秒后再轮询
 *      —— 返回 false：停止轮询，不再自动 refetch
 *      —— 这就是"自适应轮询"的基础——根据 query 的当前状态决定是否继续
 *
 * 【回调函数的参数 query】
 * query 对象包含以下关键信息：
 * - query.state.data: 当前查询的返回数据（GenerationTask 或 undefined）
 * - query.state.status: TanStack Query 内部状态（loading/error/success）
 * - query.state.dataUpdatedAt: 数据最后更新时间戳
 * 回调中可以访问这些信息来做决策。
 *
 * 【轮询逻辑详解】
 * ```
 * const data = query.state.data;
 * if (!data) return 2000;          // 首次：无数据 => 2秒后重试
 * if (data.status === "completed" || data.status === "failed")
 *   return false;                   // 终态：停止轮询（不消耗资源）
 * return 2000;                      // 进行中：2秒后继续轮询
 * ```
 * - 首次加载阶段（data 为 undefined）：2000ms 间隔快速获取初始响应
 * - 进行中阶段（status 为 "queued" / "processing" / 任何非终态）：2000ms 间隔跟踪进度
 * - 终态阶段（status 为 "completed" / "failed"）：返回 false 停止轮询
 *
 * 【为什么这是"响应式轮询"？】
 * 区别于传统的 setTimeout/setInterval 手动轮询：
 * - 传统方式：组件中手动 setInterval → 需要管理 componentWillUnmount 清理
 * - TanStack Query 方式：声明式定义轮询规则 → 框架自动管理生命周期
 *   - 组件卸载时自动停止轮询
 *   - 窗口失焦时自动暂停（refetchOnWindowFocus 默认行为）
 *   - 支持 staleTime 和 gcTime 控制缓存策略
 *
 * 【enabled 条件】
 * enabled: !!taskId
 * —— taskId 为 null/undefined/"" 时不启动查询（也不启动轮询）
 * —— 典型流程：
 *    1. useGenerateGame 返回 GenerationTask（包含 task_id）
 *    2. 组件将 taskId 传给 useTaskPolling(taskId)
 *    3. taskId 从 null 变为有效值 → enabled 变为 true → 查询+轮询自动启动
 *
 * 【queryKey 设计】
 * queryKey: ["task", taskId]
 * —— 当 navigate 到不同的任务时，taskId 变化 → queryKey 变化 → 停止旧轮询，启动新轮询
 * —— TanStack Query 为每个 taskId 维护独立的缓存：
 *    - ["task", "task-123"] → 缓存任务 123 的数据
 *    - ["task", "task-456"] → 缓存任务 456 的数据
 * —— 切换回之前的 taskId 时，可以直接使用缓存（如果未过期）
 */

import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { GenerationTask } from "@/types";
// GenerationTask: AI 生成任务的数据结构
// —— 包含 task_id、status、progress、result 等字段
// —— status 的可能值：queued（排队中）、processing（处理中）、completed（已完成）、failed（失败）

/**
 * useTaskPolling — 自适应轮询 AI 生成任务状态
 *
 * @param taskId - 任务 ID，为 null 时不启动查询和轮询
 * @returns TanStack Query 对象，包含 data（GenerationTask）、isLoading、error 等
 *
 * 【使用示例】
 * ```
 * // 在 CreatePage 中
 * const task = useGenerateGame();   // 触发生成，返回 taskId
 * // ...
 * const { data: taskStatus } = useTaskPolling(taskId);
 * // taskStatus.status 变化时会自动反映到 UI
 * if (taskStatus?.status === "completed") { /* 显示结果 *\/ }
 * ```
 */
export function useTaskPolling(taskId: string | null) {
  return useQuery({
    // queryKey: 任务 ID 是缓存的唯一标识
    // —— 切换任务时自动创建新的独立缓存
    queryKey: ["task", taskId],

    // queryFn: 获取单个任务的当前状态
    queryFn: async () => {
      // GET /tasks/:id —— 返回 GenerationTask 对象
      // —— 服务端根据 task_id 查询后台任务队列，返回最新状态和进度
      const res = await apiClient.get<GenerationTask>(`/tasks/${taskId}`);
      return res.data;
    },

    // enabled: 只有 taskId 有效时才启动查询
    // —— !!taskId 将 null/undefined 转为 false，有效字符串转为 true
    // —— 当 taskId 仍为 null 时，查询处于 idle 状态，不会发出请求
    enabled: !!taskId,

    /**
     * refetchInterval: 自适应轮询间隔（核心功能）
     *
     * 【回调函数签名】
     * (query: Query) => number | false | undefined
     *
     * 【返回值含义】
     * - number: N 毫秒后再次执行 queryFn
     * - false: 停止自动 refetch（后续不再执行）
     * - undefined: 使用默认行为（相当于不设置 refetchInterval）
     *
     * 【与固定间隔的对比】
     * ```
     * // 固定间隔（不好）：任务完成后继续每 3 秒请求
     * refetchInterval: 3000
     *
     * // 回调形式（推荐）：任务完成后自动停止
     * refetchInterval: (query) => {
     *   if (query.state.data?.status === "completed") return false;
     *   return 3000;
     * }
     * ```
     *
     * 【为什么返回 false 能停止轮询？】
     * TanStack Query 内部实现：refetchInterval 回调返回 false 时，
     * 框架不会调用 setTimeout 注册下一次 refetch，从而自然停止。
     * 这是"声明式停止"——不需要手动调用 clearInterval。
     */
    refetchInterval: (query) => {
      // 获取当前查询返回的数据（GenerationTask 或 undefined）
      const data = query.state.data;

      // 情况 1: 还没有数据（首次加载或数据为空）
      // —— 2000ms 后重试，快速获取初始响应
      // —— 为什么是 2000ms 而不是更短？
      //    需要平衡响应速度和服务器负载：
      //    1000ms 可能过于频繁（服务器压力大），5000ms 可能响应太慢
      //    2000ms 是一个合理的折中值（适合 AI 生成任务的平均耗时）
      if (!data) return 2000;

      // 情况 2: 任务已到达终态（完成或失败）
      // —— 返回 false 停止轮询，节省带宽和服务器资源
      // —— GenerationTask.status 的可能值：
      //    "completed": 生成成功，结果可用
      //    "failed": 生成失败，错误信息可用
      // —— 两种终态都不需要继续轮询
      if (data.status === "completed" || data.status === "failed") return false;

      // 情况 3: 任务仍在进行中（queued / processing / 其他中间状态）
      // —— 2000ms 后再次轮询，跟踪进度更新
      // —— 注意：这里处理了所有非终态情况，包括
      //    "queued"（排队中）、"processing"（处理中）、
      //    以及未来可能新增的任何中间状态
      return 2000;
    },
  });
}
