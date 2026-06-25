/**
 * usePublishGame.ts — 游戏发布 hook
 *
 * 【功能说明】
 * 将游戏从 preview（预览）状态变更为 published（已发布）状态。
 * 只有发布后的游戏才会出现在首页游戏列表中。
 *
 * 【发布状态机】
 * draft → preview → published
 *   - draft: 草稿状态，仅创建者可见，尚未生成
 *   - preview: 预览状态，已生成可预览，但未公开发布
 *   - published: 已发布状态，出现在首页列表，所有用户可见
 *
 * 【为什么用 PUT 而不是 PATCH？】
 * PUT /games/:id 是完整替换资源
 * —— 语义上，我们用 { status: "published" } 作为请求体，
 *    明确表示"将此游戏的状态字段更新为 published"
 * —— PUT vs PATCH 的区别：
 *    PUT: 替换整个资源（需要发送完整数据或指定字段的替换语义）
 *    PATCH: 部分更新资源（仅发送需要修改的字段）
 * —— 在这个场景中，PUT 发送一个包含 status 字段的对象，
 *    服务端将其理解为"更新 status 为 published"，也算合理
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
// useMutation: 处理 PUT 请求（修改服务器状态）
// useQueryClient: 用于在发布成功后失效相关缓存

import apiClient from "@/lib/api-client";
import type { Game } from "@/types";

/**
 * usePublishGame — 发布游戏
 *
 * 【mutation 流程】
 * 1. 创建者在预览页面确认发布
 * 2. 调用 mutate(gameId) 触发 mutation
 * 3. mutationFn 发送 PUT /games/:id { status: "published" }
 * 4. 服务端将游戏状态从 preview 改为 published
 * 5. onSuccess 中失效相关缓存：
 *    - ["game"]: 游戏详情缓存（详情页需要展示新状态）
 *    - ["games"]: 游戏列表缓存（列表页需要包含新发布的游戏）
 *
 * 【onSuccess 中为什么要 invalidate 两个 queryKey？】
 *
 * invalidateQueries({ queryKey: ["game"] })
 * —— 失效所有以 "game" 开头的查询（TanStack Query 模糊匹配）
 * —— 这会匹配 ["game", gameId] 等详情查询
 * —— 确保详情页显示"已发布"状态而非"预览"状态
 *
 * invalidateQueries({ queryKey: ["games"] })
 * —— 失效游戏列表查询
 * —— 确保首页列表包含新发布的游戏
 * —— 因为 useGames 中 status 固定为 "published"，
 *    之前请求时该游戏还是 preview 状态（不在结果中），
 *    现在发布了，需要重新获取才能出现在列表中
 *
 * 【为什么发布后 game 详情页也有影响？】
 * —— 发布前的详情页可能显示"预览模式"提示或编辑按钮
 * —— 发布后这些 UI 应该变化（如隐藏编辑按钮，显示分享按钮）
 * —— 缓存失效后重新获取的 Game 对象 status 变为 "published"，
 *    UI 随之自动更新
 */
export function usePublishGame() {
  // 获取全局 QueryClient 实例，用于缓存操作
  const queryClient = useQueryClient();

  return useMutation({
    // mutationFn: 执行发布操作
    mutationFn: async (gameId: string) => {
      // PUT /games/:id —— 更新游戏信息
      // —— 请求体 { status: "published" } 将游戏状态改为已发布
      // —— 泛型 <Game> 指定返回类型为更新后的 Game 对象
      const res = await apiClient.put<Game>(`/games/${gameId}`, {
        status: "published",
      });
      return res.data; // 返回发布后的 Game 对象
    },

    // onSuccess: 发布成功后刷新相关缓存
    onSuccess: () => {
      // 失效游戏详情缓存
      // —— ["game"] 模糊匹配 ["game", "xxx"] 等所有详情查询
      // —— 确保详情页获取到 status="published" 的最新数据
      queryClient.invalidateQueries({ queryKey: ["game"] });

      // 失效游戏列表缓存
      // —— ["games"] 模糊匹配 ["games", 1, undefined, 12] 等所有列表查询
      // —— 确保首页列表包含新发布的游戏
      queryClient.invalidateQueries({ queryKey: ["games"] });
    },
  });
}
