/**
 * useTaskLog.ts — 游戏 AI 生成任务日志查询 hook
 *
 * 【功能说明】
 * 获取指定游戏的 AI 生成任务执行日志，展示在创建页面的"完成"阶段。
 * 当 AI 生成完成后（GenerationTask status === "completed"），
 * 通过此 hook 获取 Agent 的详细执行过程日志。
 *
 * 【使用场景】
 * - CreatePage 的"done"状态：显示 Agent 的执行步骤和最终结果
 * - 让用户了解 AI 在生成游戏过程中做了哪些工作
 * - 提供透明度——用户可以看到 Agent 的思考过程和操作日志
 */

import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";

/**
 * TaskLog 接口 — 任务日志的本地数据结构
 *
 * 【为什么在 hook 文件中定义接口而非 types/ 中？】
 * - 这个接口仅在此 hook 中使用（组件通过 hook 返回值推断类型）
 * - 如果将来其他地方也需要，可以提取到 types/index.ts 中
 * - 保持 types/ 目录整洁，只放跨模块共享的类型
 *
 * 【字段说明】
 * - task_id: 任务唯一标识（对应 useTaskPolling 中的 taskId）
 * - status: 任务当前状态（completed / failed / processing 等）
 * - progress: 进度百分比（0-100），用于进度条展示
 * - prompt_summary: 缩写的提示词摘要
 *   —— 完整提示词可能非常长（数百字），日志中只展示缩略版本
 *   —— 用于让用户快速回忆起自己的创作意图
 *   —— 可能为 null（如果任务尚未开始或日志未生成）
 * - agent_steps: Agent 执行步骤的日志消息数组
 *   —— 来自 AI Agent harness（AI 代理执行框架）
 *   —— 每一步是一条文本消息，描述 Agent 某个具体操作
 *   —— 例如：["分析用户需求...", "设计游戏架构...", "生成 HTML 代码...", ...]
 * - started_at: 任务开始时间（ISO 8601 格式字符串）
 *   —— 可能为 null（任务尚未开始）
 * - completed_at: 任务完成时间
 *   —— 可能为 null（任务尚未完成）
 */
interface TaskLog {
  task_id: string;
  status: string;
  progress: number;
  prompt_summary: string | null;
  agent_steps: string[];
  started_at: string | null;
  completed_at: string | null;
}

/**
 * useTaskLog — 获取游戏生成任务日志
 *
 * @param gameId - 游戏 ID，为 null 时不发起请求
 *
 * 【懒查询】
 * enabled: !!gameId
 * —— 仅在 gameId 有效时获取日志
 * —— 典型流程：
 *    1. 用户创建游戏 → 获得 gameId
 *    2. 用户触发 AI 生成 → 获得 taskId → useTaskPolling 轮询
 *    3. 生成完成后 → 组件切换到 "done" 状态
 *    4. 此时 gameId 已存在 → useTaskLog 自动 fetch 日志
 *    5. UI 展示 agent_steps 中的执行日志
 *
 * 【queryKey 说明】
 * ["task-log", gameId]
 * —— 每个游戏的日志独立缓存
 * —— 与 ["task", taskId]（useTaskPolling）不同：
 *    useTaskPolling 按 taskId 缓存，useTaskLog 按 gameId 缓存
 *    因为一个游戏可能有多个任务，但日志是游戏级别的汇总
 *
 * 【与 useTaskPolling 的区别】
 * - useTaskPolling: 轮询获取 GenerationTask 状态（轻量，高频轮询）
 * - useTaskLog: 一次性获取 Agent 执行日志（重量，仅完成时获取一次）
 * - 两者服务于不同的 UI 状态：
 *   - 生成中（processing）→ 用 useTaskPolling 显示进度
 *   - 完成后（completed）→ 用 useTaskLog 显示详细日志
 */
export function useTaskLog(gameId: string | null) {
  return useQuery({
    // queryKey: 以 gameId 为维度缓存任务日志
    // —— 不同游戏的任务日志完全独立
    queryKey: ["task-log", gameId],

    // queryFn: 获取指定游戏的任务执行日志
    queryFn: async () => {
      // GET /tasks/games/:gameId/log
      // —— 返回 TaskLog 对象，包含任务执行的全量日志
      const res = await apiClient.get<TaskLog>(`/tasks/games/${gameId}/log`);
      return res.data;
    },

    // enabled: 仅在 gameId 有效时执行查询
    // —— 在用户创建游戏之前，gameId 为 null，不会发出无效请求
    enabled: !!gameId,
  });
}
