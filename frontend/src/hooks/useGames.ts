/**
 * useGames.ts — 游戏查询相关 hooks
 *
 * 【架构说明】
 * - 使用 TanStack Query 的 useQuery 进行数据获取
 * - 通过 queryKey 实现按参数维度缓存隔离
 * - 通过 enabled 选项实现懒加载（条件查询）
 */

import { useQuery } from "@tanstack/react-query";
// useQuery: TanStack Query 的核心查询 hook
// —— 负责数据获取、缓存、后台刷新、去重请求等
// —— 返回值包含 data, isLoading, isError, error 等状态字段

import apiClient from "@/lib/api-client";
import type { GameListResponse, Game, GameAsset } from "@/types";

/**
 * useGames — 分页+筛选获取游戏列表
 *
 * 【queryKey 设计】
 * queryKey: ["games", page, tag, size]
 * —— TanStack Query 将 queryKey 作为缓存的唯一标识
 * —— 当 page、tag、size 任一参数变化时，queryKey 随之变化，
 *    框架自动将其视为"新的查询"，触发 refetch（或从缓存读取）
 * —— 例如：
 *    ["games", 1, "射击", 12] → 缓存条目 A
 *    ["games", 2, "射击", 12] → 缓存条目 B（不同 key，独立缓存）
 *    ["games", 1, "RPG", 12]  → 缓存条目 C
 * —— 这种设计避免了手动管理"参数变了就要重新请求"的逻辑
 *
 * 【参数说明】
 * @param page   - 当前页码，默认 1（首页）
 * @param tag    - 标签筛选，undefined 表示不筛选（服务端返回全部）
 * @param size   - 每页数量，默认 12
 *
 * 【服务端筛选逻辑】
 * - status: 始终固定为 "published"
 *   —— 只展示已发布的游戏，draft 和 preview 状态对普通用户隐藏
 *   —— 这是安全边界的最后一道防线：前端虽不展示草稿游戏的入口，
 *      但 API 层的 status 过滤确保即使被直接调用也不会泄露未发布内容
 * - tag: 仅在有值时发送
 *   —— undefined 时 params 对象上没有 tag 键，Axios 不会发送该参数
 *   —— 服务端检测到没有 tag 参数时返回全部标签的游戏
 *   —— 这与发送 tag="" 或 tag=undefined 是不同的：有些后端会将空字符串
 *      视为"筛选为空标签"（返回空列表），所以条件添加是最安全的方式
 *
 * 【分页流程】
 * 1. React 组件维护 page 状态（useState）
 * 2. 用户点击"下一页" → setPage(page + 1)
 * 3. page 变化 → queryKey 变化 → TanStack Query 自动 refetch
 * 4. 服务端返回新的分页切片 → data 更新 → UI 自动重新渲染
 * —— 整个过程是声明式的：开发者只描述"什么参数"，框架负责"何时请求"
 */
export function useGames(page: number = 1, tag?: string, size: number = 12) {
  return useQuery({
    // queryKey: 缓存的唯一键，由所有影响查询结果的参数组成
    // —— 必须包含所有"查询依赖"，漏掉会导致不同参数共享同一缓存（数据错乱）
    queryKey: ["games", page, tag, size],
    queryFn: async () => {
      // params 对象：Axios 会将其序列化为 URL 查询字符串
      // 例如 { status: "published", page: "1", size: "12", tag: "射击" }
      // → GET /games?status=published&page=1&size=12&tag=射击
      const params: Record<string, string> = {
        status: "published", // 始终过滤：只拉取已发布的游戏
        page: String(page),  // 页码转为字符串（Axios 接受 string 更安全）
        size: String(size),  // 每页数量转为字符串
      };
      // tag 仅在非空时添加到 params
      // —— 利用 JavaScript 的 truthy 检查：undefined、""、null 都不会添加
      // —— 这比 if (tag !== undefined) 更简洁，且自动处理了空字符串的情况
      if (tag) params.tag = tag;
      // GET 请求，第二个参数 { params } 告诉 Axios 将这些键值对放到查询字符串
      const res = await apiClient.get<GameListResponse>("/games", { params });
      return res.data;
    },
  });
}

/**
 * useGame — 获取单个游戏详情
 *
 * 【懒查询（Lazy Query）】
 * enabled: !!gameId
 * —— 双重否定 !!gameId 将 gameId 转为布尔值：
 *    "" → false（空字符串时不会发起请求）
 *    "abc123" → true（有有效 ID 时自动发起请求）
 * —— 这是 TanStack Query 的条件查询模式：
 *    当 enabled 为 false 时，query 进入 "idle" 状态，queryFn 不会执行
 *    当 enabled 变为 true 时（gameId 从空变为有效值），自动执行 queryFn
 * —— 典型场景：游戏详情页路由 /games/:id，组件从 URL params 获取 gameId，
 *    初始渲染时 gameId 可能为空（路由还未解析），enabled: false 防止无效请求
 *
 * 【播放计数增量】
 * params: { increment: true }
 * —— 告诉服务端本次请求应将 play_count +1
 * —— 仅在游戏详情页（实际游玩场景）使用，列表页不传 increment，
 *    避免浏览列表时虚增播放次数
 * —— 为什么用查询参数而不是单独的 POST /games/:id/play？
 *    因为 GET 可以复用缓存，且前端只需一次网络请求即可获取数据+计次
 */
export function useGame(gameId: string) {
  return useQuery({
    // queryKey: ["game", gameId] —— 每个游戏的详情独立缓存
    queryKey: ["game", gameId],
    queryFn: async () => {
      // GET /games/:id?increment=true
      // —— increment=true 触发服务端 play_count++（播放计数）
      // —— 这是服务端驱动的计数逻辑，前端无需额外处理
      const res = await apiClient.get<Game>(`/games/${gameId}`, { params: { increment: true } });
      return res.data;
    },
    // enabled: 只有 gameId 存在时才执行查询
    // —— !! 双重否定将任意值转为布尔值：
    //    undefined → false, null → false, "" → false, "xxx" → true
    enabled: !!gameId,
  });
}

/**
 * useGameAssets — 获取游戏关联的素材文件列表
 *
 * 【与 useGame 的关系】
 * useGame 获取游戏元数据（标题、描述、标签等），
 * useGameAssets 获取游戏的素材文件（图片、音频、HTML 文件等）。
 * 两者是独立的 API 端点，分离获取可以：
 * - 使用不同的缓存策略（资产列表变化频率可能不同）
 * - 独立的加载状态（元数据先显示，资产列表后续加载）
 *
 * 【同样使用懒查询】
 * enabled: !!gameId —— gameId 无效时不会请求
 * 这防止了在 gameId 为空时发起 GET /games//assets 这样的无效请求
 */
export function useGameAssets(gameId: string) {
  return useQuery({
    // queryKey: ["game-assets", gameId] —— 资产的缓存键独立于游戏详情
    queryKey: ["game-assets", gameId],
    queryFn: async () => {
      // GET /games/:id/assets —— 返回 GameAsset[] 数组
      const res = await apiClient.get<GameAsset[]>(`/games/${gameId}/assets`);
      return res.data;
    },
    // 条件查询：gameId 无效时不发起请求
    enabled: !!gameId,
  });
}
