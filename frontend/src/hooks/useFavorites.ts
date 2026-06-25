/**
 * useFavorites.ts — 收藏功能相关 hooks
 *
 * 【功能说明】
 * 提供三个 hook 覆盖收藏功能的完整流程：
 * 1. useFavoriteGameIds — 获取当前用户收藏的游戏 ID 列表（个人数据）
 * 2. useFavoriteStatus — 获取单个游戏的收藏状态和收藏数（公开数据）
 * 3. useToggleFavorite — 切换收藏状态（添加/取消收藏）
 *
 * 【"收藏"的后端设计】
 * - 使用"toggle"模式：同一端点 POST /games/:id/favorite 同时处理添加和取消
 *   —— 优点：前端无需判断当前状态来选择 API，只需调用同一接口
 *   —— 服务端根据当前用户是否已收藏来决定：已收藏→取消，未收藏→添加
 *   —— 这种设计简化了前端逻辑，由服务端保证数据一致性
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
// useQueryClient: 用于 invalidateQueries，确保收藏操作后相关数据自动刷新

import apiClient from "@/lib/api-client";

/**
 * useFavoriteGameIds — 获取当前用户的收藏游戏 ID 列表
 *
 * 【用途】
 * - 在游戏列表页标记哪些游戏已被收藏（显示实心/空心爱心图标）
 * - 在"我的收藏"页面展示已收藏的游戏列表
 *
 * 【返回数据】
 * string[] —— 收藏的游戏 ID 数组
 * 例如：["game-001", "game-003", "game-007"]
 * 组件可以快速判断：ids.includes(gameId) → 已收藏
 *
 * 【认证相关】
 * GET /auth/me/favorites
 * —— 这个端点需要认证（/auth/me 前缀表示当前登录用户）
 * —— Axios 拦截器会自动附加 Authorization: Bearer <token>
 * —— 未登录用户调用此接口会收到 401 响应
 *
 * 【为什么不分页？】
 * 收藏列表通常数据量较小（用户收藏的游戏数量有限），
 * 一次性返回所有 ID 数组足够高效。如果将来收藏数量很大，
 * 可以改为分页返回。
 */
export function useFavoriteGameIds() {
  return useQuery({
    // queryKey: ["favorites"] —— 全局唯一的收藏缓存
    // —— 此查询不依赖任何参数（因为总是获取"当前用户"的收藏）
    queryKey: ["favorites"],

    // queryFn: 获取当前用户的收藏游戏 ID 列表
    queryFn: async () => {
      // GET /auth/me/favorites
      // —— 返回 string[] 类型的游戏 ID 数组
      const res = await apiClient.get<string[]>("/auth/me/favorites");
      return res.data;
    },

    // 注意：这里没有 enabled 条件
    // —— 意味着此查询在组件挂载时自动执行
    // —— 如果用户未登录，useQuery 会收到 401 错误，组件可以据此展示登录提示
    // —— 如果需要在未登录时不请求，可以添加 enabled 条件或使用 retry 配置
  });
}

/**
 * useFavoriteStatus — 获取单个游戏的收藏状态与收藏总数
 *
 * 【返回数据】
 * { favorited: boolean; count: number }
 * - favorited: 当前登录用户是否已收藏该游戏
 *   —— 未登录用户此值为 false
 * - count: 该游戏的总收藏数（公开信息，所有用户可见）
 *   —— 用于显示"已有 N 人收藏"
 *
 * 【与 useFavoriteGameIds 的区别】
 * - useFavoriteGameIds: 获取当前用户收藏的所有游戏 ID（个人数据）
 * - useFavoriteStatus: 获取单个游戏的收藏详情（含公开的收藏计数）
 * —— 两者配合使用：
 *   列表页用 useFavoriteGameIds 批量判断哪些已收藏
 *   详情页用 useFavoriteStatus 获取单个游戏的收藏数和状态
 *
 * 【为什么 count 是公开的？】
 * 收藏计数是社交功能的一部分——展示游戏的热度。
 * 类似于"点赞数"，不需要登录即可查看。
 * 而 favorited 字段对未登录用户返回 false（或根据需求返回 null）。
 */
export function useFavoriteStatus(gameId: string) {
  return useQuery({
    // queryKey: ["favorite", gameId] —— 每个游戏独立缓存
    queryKey: ["favorite", gameId],

    // queryFn: 获取指定游戏的收藏状态
    queryFn: async () => {
      // GET /games/:id/favorite
      // —— 返回 { favorited: boolean; count: number }
      const res = await apiClient.get<{ favorited: boolean; count: number }>(
        `/games/${gameId}/favorite`
      );
      return res.data;
    },
  });
}

/**
 * useToggleFavorite — 切换收藏状态（toggle 模式）
 *
 * 【为什么使用 toggle 设计？】
 * POST /games/:id/favorite 是 toggle 端点：
 * —— 已收藏 → 调用 → 取消收藏（返回 { favorited: false }）
 * —— 未收藏 → 调用 → 添加收藏（返回 { favorited: true }）
 * —— 前端不需要先 GET 确认状态再决定调用什么 API，
 *    只需调用这一个端点，服务端自动判断并翻转状态
 *
 * 【onSuccess 中的缓存失效策略】
 * 同时 invalidate 两个 queryKey：
 *   1. ["favorites"]  → useFavoriteGameIds 的缓存
 *      —— 收藏/取消收藏后，用户的收藏 ID 列表发生变化
 *
 *   2. ["favorite"]   → useFavoriteStatus 的缓存
 *      —— TanStack Query 的模糊匹配会失效所有以 "favorite" 开头的 queryKey
 *      —— 例如 ["favorite", "game-001"]、["favorite", "game-002"] 等全部失效
 *      —— 这意味着任何页面上的收藏状态和计数都会自动更新
 *
 * 【为什么 invalidateQueries 而不是手动更新缓存？】
 * 两种方式对比：
 *
 *   方式 A — invalidateQueries（本项目采用）：
 *     - 标记缓存过时 → 下次渲染时自动 refetch
 *     - 优点：实现简单，100% 确保数据一致性（数据来自服务端）
 *     - 缺点：多一次网络请求
 *
 *   方式 B — setQueryData 手动更新：
 *     - 直接在本地修改缓存中的数据
 *     - 优点：零网络延迟，即时响应
 *     - 缺点：需要在客户端复制服务端的业务逻辑（如 count 的加减计算）
 *            如果服务端逻辑变更（如增加去重、限流），客户端逻辑也要同步修改
 *            容易产生不一致的"乐观更新"bug
 *
 * —— 对于收藏来说，一次网络请求的代价很小（毫秒级），
 *    选择 invalidateQueries 更简单、更可靠。
 */
export function useToggleFavorite() {
  // 获取全局 QueryClient 实例
  const queryClient = useQueryClient();

  return useMutation({
    // mutationFn: 发送 toggle 请求
    mutationFn: async (gameId: string) => {
      // POST /games/:id/favorite
      // —— Toggle 端点：根据当前状态自动反转收藏状态
      // —— 不需要额外的请求体，gameId 从 URL 路径中提取
      // —— 返回 { favorited: boolean } 表示操作后的状态
      const res = await apiClient.post<{ favorited: boolean }>(
        `/games/${gameId}/favorite`
      );
      return res.data;
    },

    // onSuccess: 收藏操作成功后刷新相关缓存
    onSuccess: () => {
      // 失效 ["favorites"] —— 用户的收藏 ID 列表
      // —— 确保列表页的收藏图标正确反映最新状态
      queryClient.invalidateQueries({ queryKey: ["favorites"] });

      // 失效 ["favorite"] —— 所有游戏的收藏状态查询
      // —— TanStack Query 的 partial matching：
      //   传入 ["favorite"] 会匹配所有以 "favorite" 开头的 queryKey
      //   如 ["favorite", "game-001"]、["favorite", "game-002"] 等
      // —— 这确保了：
      //    1. 详情页的收藏状态立即更新
      //    2. 收藏计数自动同步
      //    3. 不需要知道当前页面具体是哪个 gameId
      queryClient.invalidateQueries({ queryKey: ["favorite"] });
    },
  });
}
