/**
 * useCreateGame.ts — 游戏创建与 AI 生成相关 hooks
 *
 * 【架构说明】
 * - 三个 mutation hook：创建游戏、上传素材、触发 AI 生成
 * - 使用 TanStack Query 的 useMutation + useQueryClient 实现缓存失效
 * - onSuccess 中调用 invalidateQueries 确保相关数据在变更后自动刷新
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
// useMutation: 处理 POST/PUT/DELETE 等"写入"操作
// useQueryClient: 获取 QueryClient 实例，用于手动控制缓存（如 invalidateQueries）
// —— invalidateQueries 会将指定的 query 标记为"过时"（stale），
//    活动页面上的 useQuery 会自动 refetch，非活动页面的缓存会等到下次访问时重新获取

import apiClient from "@/lib/api-client";
import type { Game, GameAsset, GenerationTask } from "@/types";

/**
 * useCreateGame — 创建游戏草稿
 *
 * 【mutation 流程】
 * 1. 用户在创建页面填写标题、描述、标签、创作提示词
 * 2. 点击"创建" → mutate({ title, description, tags, prompt_text })
 * 3. mutationFn 发送 POST /games，服务端创建游戏记录（状态为 draft）
 * 4. onSuccess 调用 invalidateQueries(["games"]) 使游戏列表缓存失效
 *    —— 这样游戏列表页会自动重新获取，新创建的游戏出现在列表中
 *
 * 【为什么在 onSuccess 中 invalidate？】
 * —— 缓存一致性：POST 创建了新游戏后，["games"] 缓存是"脏"的（缺少新游戏）
 * —— invalidateQueries 后，所有使用该 queryKey 的活跃 useQuery 会自动 refetch
 * —— 这比手动更新缓存更简单、更可靠：服务端是唯一的数据源，
 *    客户端只需标记缓存"过期"即可，无需本地推算服务端状态
 *
 * 【注意】
 * prompt_text 字段：用户的创作意图描述，不是 AI 生成的实际 prompt
 * —— AI 生成管线会基于这个 prompt_text 构建更复杂的 system prompt
 * —— 这个字段用于初始化 GenerationTask
 */
export function useCreateGame() {
  // useQueryClient: 获取全局 QueryClient 实例
  // —— QueryClient 由 QueryClientProvider 提供，管理整个应用的查询缓存
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: {
      title: string;
      description: string;
      tags: string[];
      prompt_text: string;
    }) => {
      // POST /games —— 创建新游戏（初始状态为 draft）
      // —— 泛型 <Game> 指定返回类型为 Game 对象
      const res = await apiClient.post<Game>("/games", data);
      return res.data; // 返回创建后的 Game 对象
    },
    onSuccess: () => {
      // 创建成功后，使游戏列表查询缓存失效
      // —— queryKey: ["games"] 匹配 useGames() 中定义的查询
      // —— 失效后，活跃的列表页 useGame 会自动 refetch，新游戏随之出现
      // —— TanStack Query 的"模糊匹配"：["games"] 会匹配所有以 "games" 开头的 queryKey
      //    例如 ["games", 1, "射击", 12] 和 ["games", 2, undefined, 12] 都会被失效
      queryClient.invalidateQueries({ queryKey: ["games"] });
    },
  });
}

/**
 * useUploadAsset — 上传游戏素材文件
 *
 * 【为什么必须使用 multipart/form-data】
 * —— 文件上传需要将二进制数据和文本字段混合传输
 * —— Content-Type 必须设为 multipart/form-data，因为：
 *    1. application/json 只能传输文本，无法携带二进制文件
 *    2. multipart/form-data 是 HTTP 标准中唯一支持文件上传的编码格式
 *    3. 浏览器会自动设置 boundary 分隔符（通过 FormData API）
 *       —— 每个字段（文本或文件）由 boundary 字符串分隔
 *       —— 文件字段还会包含 filename 和 Content-Type 头
 *
 * 【FormData 构建流程】
 * 1. new FormData() 创建空的表单数据容器
 * 2. form.append("file", file) 将 File 对象添加到容器
 *    —— "file" 是服务端期望的字段名
 *    —— file 是浏览器 File API 的对象（来自 <input type="file">）
 * 3. Axios 自动将 FormData 序列化为 multipart 请求体
 *
 * 【与 useCreateGame 的关系】
 * 通常是先创建游戏（获得 gameId），再上传素材到该游戏
 * —— POST /games/:id/assets 中的 :id 就是 gameId
 */
export function useUploadAsset() {
  return useMutation({
    mutationFn: async ({ gameId, file }: { gameId: string; file: File }) => {
      // 创建 FormData 实例：浏览器原生的表单数据 API
      // —— FormData 会自动设置正确的 Content-Type 和多部分边界
      const form = new FormData();
      // append(key, value): 添加表单字段
      // —— key "file" 必须与服务端 Multer/Formidable 等中间件的字段名一致
      // —— value 是 File 对象（浏览器原生的文件接口）
      form.append("file", file);
      // POST 请求，第三个参数显式设置 headers
      // —— 虽然浏览器+Axios 通常能自动推断 Content-Type，
      //    但显式设置 multipart/form-data 可以避免某些环境下的推断错误
      const res = await apiClient.post<GameAsset>(
        `/games/${gameId}/assets`,
        form,
        {
          headers: { "Content-Type": "multipart/form-data" },
        }
      );
      return res.data; // 返回上传后的 GameAsset 对象（含 URL）
    },
  });
}

/**
 * useGenerateGame — 触发 AI 生成管线
 *
 * 【AI 生成流程】
 * 1. 用户创建游戏草稿并（可选）上传参考素材
 * 2. 用户调用 useGenerateGame，传入 gameId 和 promptText
 * 3. POST /games/:id/generate 触发服务端 AI 生成管线
 * 4. 服务端返回 GenerationTask 对象（含 task_id + 初始状态 "queued"）
 * 5. 前端拿到 task_id 后，通过 useTaskPolling 轮询任务进度
 *
 * 【GenerationTask 是什么】
 * —— 表示一次 AI 生成任务的完整生命周期
 * —— 包含 task_id（唯一标识）、status（queued/processing/completed/failed）、progress 等
 * —— 前端通过轮询 /tasks/:id 接口来追踪任务进展
 *
 * 【onSuccess 中的 invalidateQueries】
 * —— 触发生成后，游戏的状态可能会变（如从 draft 变为 generating），
 *    需要失效 ["games"] 缓存以获取最新状态
 * —— 注意：这里只失效了列表，生成结果的详情页（代码、素材等）
 *    由 useTaskPolling 实时轮询获取
 */
export function useGenerateGame() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      gameId,
      promptText,
    }: {
      gameId: string;
      promptText: string;
    }) => {
      // POST /games/:id/generate —— 启动 AI 生成
      // —— 请求体包含 prompt_text：用户的核心创作意图描述
      // —— 返回 GenerationTask 对象，用于后续轮询
      const res = await apiClient.post<GenerationTask>(
        `/games/${gameId}/generate`,
        {
          prompt_text: promptText,
        }
      );
      return res.data;
    },
    onSuccess: () => {
      // 生成任务启动后，游戏状态可能变化，失效列表缓存
      // —— 例如游戏状态从 "draft" 变为 "generating"
      queryClient.invalidateQueries({ queryKey: ["games"] });
    },
  });
}
