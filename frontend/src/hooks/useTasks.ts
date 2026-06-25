/**
 * useTasks.ts — 游戏关联任务列表查询 hook
 *
 * 【功能说明】
 * 获取指定游戏的所有 GenerationTask 记录（一个游戏可能有多次生成任务）。
 * 主要用于 PlayPage 的"版本历史"面板——展示该游戏历次 AI 生成的版本。
 *
 * 【使用场景】
 * - PlayPage > VersionHistoryPanel：列出所有历史生成版本
 * - 用户可以选择查看/回退到某个历史版本
 * - 每个版本对应一个 GenerationTask 记录
 */

import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { GenerationTask } from "@/types";
// GenerationTask: AI 生成任务的数据结构
// —— 每次用户触发 AI 生成都会创建一条 GenerationTask 记录
// —— 包含 task_id、status（completed/failed/processing）、
//    result（生成结果）、created_at（创建时间）等字段

/**
 * useTasks — 获取游戏的所有生成任务记录
 *
 * @param gameId - 游戏 ID，为 null 时不发起请求
 * @returns GenerationTask[] 数组，按创建时间排序（通常最新的在前）
 *
 * 【懒查询设计】
 * enabled: !!gameId
 * —— 与 useGame 一样，只有 gameId 存在时才获取数据
 * —— 在 PlayPage 中，gameId 来自路由参数，加载后自动触发查询
 *
 * 【queryKey 设计】
 * ["tasks", gameId]
 * —— 每个游戏的任务列表独立缓存
 * —— 注意与以下 queryKey 的区别：
 *    - ["task", taskId]    → useTaskPolling：单个任务的实时状态
 *    - ["task-log", gameId] → useTaskLog：任务的执行日志
 *    - ["tasks", gameId]   → useTasks：游戏的所有任务列表（本 hook）
 *    三者的缓存互不干扰
 *
 * 【API 端点】
 * GET /tasks/games/:gameId
 * —— 返回该游戏关联的所有 GenerationTask 记录
 * —— 返回类型是 GenerationTask[]（数组）
 * —— 这个端点与 useTaskLog 的 /tasks/games/:id/log 不同：
 *    useTaskLog 返回的是单个日志详情（包含 agent_steps），
 *    useTasks 返回的是任务列表摘要（不含详细日志步骤）
 *
 * 【数据关系】
 * 一个 Game 可以有多个 GenerationTask：
 * - 每次用户在 CreatePage 点击"生成"，就会产生一个新的 GenerationTask
 * - 所有任务都与 gameId 关联
 * - PlayPage 中展示这些任务作为"版本历史"
 *
 * 【为什么不在 useQuery 中添加 refetchInterval？】
 * —— 任务列表是"历史记录"，不需要实时更新
 * —— 只有在以下情况才需要刷新：
 *    1. 用户触发了新的生成（useGenerateGame 的 onSuccess 会 invalidate）
 *    2. 用户手动刷新页面
 * —— 相比之下，useTaskPolling 需要实时跟踪单个任务状态，所以有轮询
 */
export function useTasks(gameId: string | null) {
  return useQuery({
    // queryKey: 以 gameId 为键缓存任务列表
    queryKey: ["tasks", gameId],

    // queryFn: 获取游戏的所有 GenerationTask 记录
    queryFn: async () => {
      // GET /tasks/games/:gameId
      // —— 泛型 GenerationTask[] 表示返回的是任务数组
      const res = await apiClient.get<GenerationTask[]>(`/tasks/games/${gameId}`);
      return res.data;
    },

    // enabled: 仅当 gameId 存在时才执行查询
    // —— null 时查询处于 idle 状态，不发出请求
    enabled: !!gameId,
  });
}
