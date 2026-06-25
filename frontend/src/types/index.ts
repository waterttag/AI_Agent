/**
 * types/index.ts — 前端 TypeScript 类型定义（API 契约层）
 * ==========================================================================
 * 本文件定义了前端与后端 API 之间的数据结构契约。
 *
 * 为什么要把类型集中放在一个文件？
 *   1. 单一数据源（Single Source of Truth）：前后端类型定义一致，减少不匹配 bug
 *   2. 自动补全与类型检查：TypeScript 编译器可以在编辑时发现字段名拼写错误、
 *      类型不匹配等问题，而不是等到运行时才发现
 *   3. 文档作用：接口定义本身就是最好的 API 文档，直观展示数据结构
 *
 * 类型设计原则：
 *   - interface 而非 type：interface 可以 extends，更适合描述数据对象
 *   - 字段名使用 snake_case：与后端返回的 JSON 字段名一致，
 *     避免前端需要做字段映射（camelCase ↔ snake_case）
 *   - 可空字段使用 T | null：明确表示"这个字段可能不存在"
 *   - 字符串字面量联合类型：status、asset_type 等限定合法值，
 *     编译器会对非法值报错
 */

// ===========================================================================
// 用户认证相关类型（Auth Contracts）
// ===========================================================================

// --- User ---
/**
 * User — 用户实体
 *
 * 表示系统中一个已注册用户的基本信息。
 *
 * 字段说明：
 *   - id:       用户唯一标识符（UUID），由后端数据库生成
 *   - username: 用户名，用于登录和展示
 *   - email:    电子邮箱地址，用于注册和通知
 *   - role:     用户角色（如 "user" / "admin"），用于权限控制
 *               当前阶段为预留字段，后续可扩展 RBAC 系统
 *   - created_at: 注册时间（ISO 8601 格式字符串，如 "2025-06-01T12:00:00Z"）
 *
 * 为什么没有 password 字段？
 *   后端绝不会在 API 响应中返回密码（哪怕是哈希值），这是基本的安全原则。
 *   前端只关心"当前用户是谁"，不关心"密码是什么"。
 */
export interface User {
  id: string;
  username: string;
  email: string;
  role: string;
  created_at: string;
}

/**
 * TokenResponse — JWT 认证响应
 *
 * 用户登录或注册成功后，后端返回的完整认证凭据。
 *
 * JWT（JSON Web Token）认证流程：
 *   1. 前端发送 POST /api/auth/login（username + password）
 *   2. 后端验证凭据，用密钥签发 JWT token
 *   3. 前端将 access_token 存储在内存或 localStorage
 *   4. 后续请求在 Authorization header 中携带 token：
 *        Authorization: Bearer <access_token>
 *   5. 后端验证 token 签名和有效期，决定是否授权
 *
 * 字段说明：
 *   - access_token: JWT 字符串（三段 Base64 编码，以 . 分隔）
 *                   格式：header.payload.signature
 *   - token_type:   token 类型，标准值为 "bearer"（OAuth 2.0 规范）
 *                   大写 "Bearer" 也常见，取决于后端实现
 *   - user:         嵌套的用户对象，省去前端再请求 /api/users/me 的步骤
 *
 * 安全注意事项：
 *   - JWT token 有过期时间（exp 声明），过期后需重新登录或刷新
 *   - 本项目将 token 放在内存中（Zustand），页面刷新后即丢失，
 *     比 localStorage 更安全（XSS 攻击无法窃取）
 */
export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

// ===========================================================================
// 游戏相关类型（Game Contracts）
// ===========================================================================

// --- Game ---

/**
 * GameAsset — 游戏素材文件
 *
 * 每个游戏可以包含多种类型的素材资源，存储在阿里云 OSS（对象存储）上。
 *
 * 字段说明：
 *   - id:                素材唯一标识符
 *   - game_id:           所属游戏的 ID（关联 Game.id）
 *   - asset_type:        素材类型（字符串字面量联合类型）
 *                          - "image"     : 图片素材（如角色、背景、物品图标）
 *                          - "audio"     : 音频素材（如背景音乐、音效）
 *                          - "reference" : 参考素材（如美术参考图、设计稿）
 *                        使用联合类型限制，确保传入非法值（如 "video"）时
 *                        TypeScript 编译器会报错，防止运行时 bug
 *   - original_filename: 原始文件名（用户上传时的文件名，用于展示）
 *   - oss_url:           阿里云 OSS 上的完整访问 URL
 *                        客户端可直接用此 URL 加载/下载资源
 *   - file_size:         文件大小（字节），可为 null（部分旧数据或上传中）
 *   - created_at:        上传时间（ISO 8601 格式）
 */
export interface GameAsset {
  id: string;
  game_id: string;
  asset_type: "image" | "audio" | "reference";
  original_filename: string;
  oss_url: string;
  file_size: number | null;
  created_at: string;
}

/**
 * Game — 游戏实体（持久化对象）
 *
 * 表示一个完整的 AI 生成游戏项目，包括元数据、状态和关联素材。
 * Game 是数据库中的持久化实体——创建后一直存在，状态随时间变化。
 *
 * 字段说明：
 *   - id:              游戏唯一标识符
 *   - title:           游戏标题（用户输入或 AI 生成）
 *   - description:     游戏描述文本（可选，用于列表展示和 SEO）
 *   - cover_image_url: 封面图片 URL，可为 null（未生成或未设置）
 *   - game_url:        可玩游戏 URL（HTML 文件地址），
 *                      生成完成前为 null，完成后指向 OSS 上的 index.html
 *   - author_id:       作者（创建者）的用户 ID
 *   - author_name:     作者的用户名（冗余字段，避免额外的 JOIN 查询）
 *   - tags:            标签数组（如 ["动作", "冒险", "像素风"]），用于分类和搜索
 *   - status:          游戏状态（字符串字面量联合类型）
 *                       状态机流转路径：
 *                         draft      → 用户创建了游戏描述，尚未提交生成
 *                         generating → 提交了生成任务，AI 正在生成中（轮询中）
 *                         preview    → 生成完成，可预览但未公开发布
 *                         published  → 已公开发布，所有用户可访问
 *                         failed     → 生成失败（可能是 AI 服务异常或超时）
 *                       状态是一个"单向"流转的有向图，不是每个状态都能随意切换
 *   - prompt_text:     用户的生成提示词（prompt），如 "创建一个太空射击游戏"
 *                       可为 null（创建时未填写）
 *   - play_count:      游玩次数计数器（每次打开游戏时递增）
 *   - created_at:      创建时间
 *   - updated_at:      最后更新时间
 *   - assets:          关联的素材资源数组（一对多关系）
 *                      使用 GameAsset[] 而非单独的 API 查询，减少请求次数
 */
export interface Game {
  id: string;
  title: string;
  description: string;
  cover_image_url: string | null;
  game_url: string | null;
  author_id: string;
  author_name?: string | null;
  tags: string[];
  status: "draft" | "generating" | "preview" | "published" | "failed";
  prompt_text: string | null;
  play_count: number;
  created_at: string;
  updated_at: string;
  assets: GameAsset[];
}

/**
 * GameListResponse — 分页游戏列表响应
 *
 * 标准的分页 API 响应格式，用于游戏列表页（首页、搜索页等）。
 *
 * 分页模式：基于偏移量的分页（Offset-based Pagination）
 *   请求：GET /api/games?page=1&size=10
 *   响应：{ items: [...], total: 45, page: 1, size: 10 }
 *
 * 与其他分页模式的比较：
 *   - 偏移量分页（当前使用）：简单直观，适合小数据集
 *     缺点：数据变化时可能出现"跳过"或"重复"的问题
 *   - 游标分页（Cursor-based）：
 *     GET /api/games?cursor=xxx&size=10
 *     优点：数据一致性高，适合大数据集
 *     缺点：无法跳页（只能"上一页/下一页"）
 *
 * 字段说明：
 *   - items: 当前页的游戏列表数据
 *   - total: 符合条件的总记录数（用于计算总页数 = Math.ceil(total / size)）
 *   - page:  当前页码（从 1 开始，而非 0）
 *   - size:  每页记录数
 */
export interface GameListResponse {
  items: Game[];
  total: number;
  page: number;
  size: number;
}

// ===========================================================================
// 生成任务相关类型（Generation Task Contracts）
// ===========================================================================

// --- Task ---

/**
 * GenerationTask — 游戏生成任务（异步作业对象）
 *
 * ------------------------------------------------------------------
 * 为什么要把 Game 和 GenerationTask 分成两个独立的实体？
 * ------------------------------------------------------------------
 * 这是"关注点分离"（Separation of Concerns）原则的典型应用：
 *
 *   Game（持久化实体）：
 *     - 代表"一个游戏"，是一个业务概念
 *     - 生命周期长：从用户创建 → 生成 → 发布 → 持续被游玩
 *     - 状态是游戏的"业务状态"（草稿、已发布等）
 *     - 存储在数据库的游戏表中
 *
 *   GenerationTask（异步任务）：
 *     - 代表"一次生成作业"，是一个技术概念
 *     - 生命周期短：提交 → 处理中 → 完成/失败（通常几分钟内）
 *     - 状态是任务的"执行状态"（排队中、处理中、已完成）
 *     - 存储在任务队列或任务表中
 *
 * 为什么分离？
 *   1. 单一职责：一个游戏可能被多次生成（修改 prompt 后重新生成），
 *      每次生成产生一个新的 Task，但 Game 还是同一个
 *   2. 轮询效率：前端只需要轮询 GenerationTask 的状态（轻量），
 *      不需要每次都拉取 Game 的所有关联数据（素材列表等重数据）
 *   3. 数据隔离：Task 的 error_message, started_at 等技术字段
 *      与 Game 的业务字段完全无关，分开后两个接口都更清晰
 *   4. 扩展性：后续如果要加入"任务队列优先级""重试次数""生成日志"等
 *      功能，只需要修改 Task 结构，不影响 Game
 *
 * 字段说明：
 *   - id:            任务唯一标识符
 *   - game_id:       关联的游戏 ID（Game.id）
 *                     通过 task.game_id 找到对应的游戏
 *   - user_id:       提交任务的用户 ID
 *   - status:        任务执行状态（字符串字面量联合类型）
 *                      - "pending"    : 任务已提交，排队等待处理
 *                      - "processing" : 正在生成中，进度见 progress 字段
 *                      - "completed"  : 生成成功，result_oss_url 有值
 *                      - "failed"     : 生成失败，error_message 说明原因
 *   - progress:      生成进度（0 - 100 的整数）
 *                     前端用此字段展示进度条；progress=100 不意味着完成，
 *                     只有 status="completed" 才算最终完成
 *   - result_oss_url: 生成结果的 OSS URL（HTML 游戏链接）
 *                     任务完成后有值，否则为 null
 *   - error_message:  失败原因描述，正常时为 null
 *   - started_at:     任务开始处理的时间，pending 状态时为 null
 *   - completed_at:   任务完成/失败的时间，未完成时为 null
 *                     通过 started_at 和 completed_at 可计算生成耗时
 *   - created_at:     任务提交时间
 */
export interface GenerationTask {
  id: string;
  game_id: string;
  user_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  progress: number;
  result_oss_url: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}
