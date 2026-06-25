"""
=============================================================================
AI Agent Harness —— 游戏生成流水线的总指挥 (Orchestrator)
=============================================================================

这是整个 AI Agent 系统的"大脑"，负责编排 Preprocess → Generate →
Validate → Fix → Package → Upload 的全流程。它不亲自做任何具体工作，
而是像乐队指挥一样协调各个专业组件。

【Harness 的命名由来】
  "Harness"（马具/线束）在软件架构中的含义：
  A test/utilization harness is a framework that provides the scaffolding,
  data, and control flow to exercise a system under controlled conditions.
  在这里，"被驱动的系统"是 LLM 适配器 + 生成器 + 验证器 + 打包器的组合。
  Harness 提供数据编排、进度追踪、错误恢复和优雅降级。

【依赖关系图】
  GameGenerationHarness
  ├── HTML5GameGenerator ──── LLMAdapter (依赖注入)
  │   ├── prompts.build_system_prompt()
  │   └── prompts.build_user_prompt()
  ├── GameValidator
  │   └── BeautifulSoup (BS4)
  └── GamePackager
      └── storage_service (MinIO)

  所有依赖通过构造函数注入，不使用全局变量或服务定位器。
  这使得每个组件都可以独立测试（单元测试时注入 mock）。

——————————————————————————————————————————————————————————————
【4 阶段流水线的进度比率设计 —— 非线性分布】
——————————————————————————————————————————————————————————————

  流水线被分为 4 个阶段，progress 值从 0 到 100：

  ┌─────────────┬──────────┬──────────┬────────────────────────────────┐
  │ 阶段         │ 进度区间  │ 增量     │ 详解                            │
  ├─────────────┼──────────┼──────────┼────────────────────────────────┤
  │ Phase 1      │  0 → 10  │  +10     │ 预处理（素材加载+Vision分析）     │
  │ Preprocess   │          │          │ 通常 1-3 秒，10% 合理             │
  ├─────────────┼──────────┼──────────┼────────────────────────────────┤
  │ Phase 2      │ 10 → 70  │  +60     │ LLM 生成（AI 思考+代码输出）      │
  │ Generate     │          │          │ 通常 10-30 秒，占绝对大头          │
  ├─────────────┼──────────┼──────────┼────────────────────────────────┤
  │ Phase 3      │ 70 → 85  │  +15     │ 验证+修复+打包上传                │
  │ Postprocess  │          │          │ 通常 2-5 秒                       │
  ├─────────────┼──────────┼──────────┼────────────────────────────────┤
  │ Phase 4      │ 85 → 100 │  +15     │ 最终化（写数据库+更新状态）        │
  │ Finalize     │          │          │ 通常 <1 秒                        │
  └─────────────┴──────────┴──────────┴────────────────────────────────┘

  为什么 LLM 生成占 60% (10→70) 而不是线性均分的 25%？

  理由 1: 时间占比 —— LLM 生成是整个流水线中耗时最长的阶段。
      在典型的生成任务中：
        Preprocess:   1-3 秒   ( ~5% 的时间)
        LLM Generate: 10-30 秒 ( ~75% 的时间)
        Validate+Pack: 2-5 秒  ( ~15% 的时间)
        Finalize:     <1 秒    ( ~3% 的时间)
      进度条的增量应该与实际耗时大致匹配，这样用户感知到的
      进度条移动速度才是均匀的。如果 LLM 生成只占 25% 但耗时 75%，
      用户会感觉进度条"卡住了"。

  理由 2: 用户体验心理学 —— 进度条是"感知进度"，不是"实际进度"。
      研究表明，用户对进度条的满意度取决于：
        a) 进度条是否持续移动（不管快慢）
        b) 进度条在接近完成时是否减速（"终点效应"）
        c) 进度条不应长时间停滞（>5 秒不动会引发焦虑）
      将 60% 分配给最慢的阶段，然后在验证/打包阶段分配 15%，
      最后 15% 作为"冲刺完成"阶段，创造了最佳的心理节奏。

  理由 3: 进度粒度 —— LLM 生成阶段内部只有一次进度更新（30→70）。
      如果生成耗时 20 秒，这 60% 的进度跳跃发生在两个时间点：
        - 生成开始：progress=10 → 30（立即，让用户知道"AI 开始工作了"）
        - 生成完成：progress=30 → 70（瞬时，让用户知道"AI 完成了"）
      中间 20 秒进度条停留在 40% 的区间内。这可以通过流式生成
      进一步细化（在每个 streaming token 到达时微调进度条），
      但当前实现选择了简单方案 —— 开始和结束两个跳点足够好。

  如果没有这个非线性设计会怎样？
    线性分配：Preprocess 25% → Generate 25% → Postprocess 25% → Finalize 25%
    结果：预处理很快完成 0→25%（2秒），然后生成阶段进度条在 25-50%
    之间停滞 20 秒。用户看到进度条"卡在 30%"很长时间，
    产生"AI 是不是挂了？"的焦虑，甚至刷新页面。

——————————————————————————————————————————————————————————————
【优雅降级 (Graceful Degradation) —— OSS 不可用时的数据库回退】
——————————————————————————————————————————————————————————————

  第 111-115 行：
    try:
        oss_url = await self.packager.package_and_upload(game_id, html_code)
    except Exception as e:
        logger.warning(f"[{task_id}] MinIO upload failed ({e}), storing in DB instead")
        oss_url = f"/api/games/{game_id}/play-html"

  这是系统中最重要的弹性设计 —— 当 MinIO 对象存储不可用时（宕机、
  网络故障、认证过期），系统不会崩溃，而是降级到备用方案。

  【降级策略的完整链路】

  ┌──────────────────────────────────────────────────────────────┐
  │ 正常路径 (Happy Path):                                        │
  │                                                              │
  │   HTML Code ──> packager.package_and_upload() ──> MinIO OSS  │
  │                        │                                     │
  │                        └──> oss_url = "https://oss.../..."   │
  │                                                              │
  │   游戏访问: 通过 MinIO 直链 + API 端点双通道                     │
  │   用户打开: /api/games/{id}/play-html (从 MinIO 302 或直读)    │
  └──────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────┐
  │ 降级路径 (Degraded Path):                                      │
  │                                                              │
  │   HTML Code ──> packager.package_and_upload() ──> ❌ 失败      │
  │                        │                                     │
  │                        └──> oss_url = "/api/games/{id}/..."  │
  │                                                              │
  │   游戏 HTML 存储在数据库的 llm_response_raw 字段中              │
  │   用户打开: /api/games/{id}/play-html (从数据库读取)            │
  └──────────────────────────────────────────────────────────────┘

  【降级路径的关键细节】

  1. oss_url 的值变化：
     正常：oss_url = "https://minio.example.com/games/{id}/index.html"
     降级：oss_url = "/api/games/{game_id}/play-html"
     这是一个相对路径 API 端点，前端可以直接 fetch/iframe 它。

  2. HTML 内容的存储位置：
     第 193 行：llm_response_raw=html_code[:50000]
     数据库表中有 llm_response_raw 字段（TEXT 类型），最大存储 50000 字符。
     50000 字符相当于约 12000-15000 行代码，足以容纳绝大多数游戏。
     如果超出（极少情况），内容被截断但游戏通常仍可运行（核心逻辑在前半部分）。

  3. 为什么不在降级时抛异常让用户看到错误？
     对用户来说，"游戏生成失败了" 是比 "游戏加载慢一点" 糟糕得多的体验。
     降级后的数据库读取可能比 OSS 慢几百毫秒，但在游戏加载场景中几乎不可感知。
     用轻微的性能损失换取零中断的用户体验，是最优的 trade-off。

  4. game.game_url 的值也使用 API 端点：
     第 201 行：game.game_url = f"/api/games/{game_id}/play-html"
     即使在正常路径中，game_url 也被设为 API 端点而非 MinIO 直链。
     这是为了解决 Content-Disposition 问题（详见 packager.py 头部注释）。
     实际上，API 端点在正常路径下可以通过 302 重定向到 MinIO URL，
     也可以直接从数据库读取（降级路径），两种模式对外接口一致。

  5. 降级触发后的恢复：
     当 MinIO 恢复后，已降级的游戏不会自动迁移到 OSS。
     这是一个可接受的设计 —— 数据库中的 HTML 完全可用，
     迁移存储不增加用户价值，增加系统复杂度。如果运营需要，
     可以通过管理脚本批量迁移。

  【其他优雅降级点】
    本系统中还有其他降级点：
      - DeepSeek 不支持 Vision: 返回文本占位描述（deepseek_adapter.py 第 37 行）
      - 验证失败: 尝试自动修复，修不好也继续（harness.py 第 85-102 行）
      - 自动修复异常: catch 后继续，使用原 HTML（harness.py 第 101 行）
      - 进度更新失败: 记录日志，不阻断流水线（harness.py 第 175 行）
      - 最终化失败: 记录日志，不阻断返回 URL（harness.py 第 205 行）

    这些降级点共同构成了"韧性架构"（Resilient Architecture）—— 系统在
    部分组件失败时仍能提供降级的但仍可用的服务，而不是完全崩溃。

——————————————————————————————————————————————————————————————
【自动修复循环的设计 —— 只修复一次】
——————————————————————————————————————————————————————————————

  第 85-102 行展示了验证失败后的自动修复逻辑。

  为什么只修复一次而不是循环修复直到通过？
    1. 避免无限循环：LLM 可能在修复时引入新错误，导致验证永远无法通过。
       一次修复是"尽力而为"（best-effort），如果修不好就交付当前版本。
    2. 成本控制：每次修复需要一次完整的 LLM API 调用（成本 + 延迟）。
       两次修复的成本是原生成的两倍，用户等待时间翻倍。
    3. 边际收益递减：第一次修复通常能解决 80% 的问题，
       第二次修复只能解决剩余 20% 中的 80%（即总量的 16%）。
       从性价比看，一次修复是最优停止点。

  这种设计哲学叫做 "Optimistic Delivery"（乐观交付）——
  如果游戏基本可玩（通过了致命检查），就交付给用户，
  即使存在一些 warning。完美主义在 AI 生成场景中是不切实际的。

——————————————————————————————————————————————————————————————
【_finalize() 的双存储策略】
——————————————————————————————————————————————————————————————

  第 178-206 行的 _finalize() 方法做了两件关键的事情：

  1. 任务记录 (task):
     - progress=100, status="completed"
     - result_oss_url: 保存 OSS URL（或降级的 API 端点路径）
     - llm_response_raw: 保存完整 HTML（截断到 50000 字符）
       这个字段的双重用途：
         a) 降级路径的 HTML 来源（MinIO 不可用时）
         b) 调试和审计（查看 AI 实际生成的原始代码）
         c) 版本历史（如果将来需要比较不同版本的游戏质量）

  2. 游戏记录 (game):
     - game_url = f"/api/games/{game_id}/play-html"
       使用 API 端点而非 MinIO 直链作为主 URL。原因：
         a) Content-Disposition 控制：API 端可设置 inline
         b) 降级路径兼容：API 端可以根据 OSS 可用性选择数据源
         c) 访问控制：将来可以在 API 端添加认证、限流、统计
     - status = "preview"
       游戏初始状态为 "preview"（可预览），将来可以发布为 "published"。

  这种"双记录"策略（任务 + 游戏）反映了系统的领域模型：
    - GenerationTask 是一次"生成行为"的记录
    - Game 是一个"游戏实体"的持久化状态
    - 一个游戏可能有多次生成任务（如用户要求重新生成），
      但只保留最新的生成结果作为游戏的当前状态。

——————————————————————————————————————————————————————————————
【_preprocess_assets() 的 Vision API 集成】
——————————————————————————————————————————————————————————————

  第 123-163 行的素材预处理展示了如何将 Vision API 集成到流水线中：

  1. 从数据库加载素材元数据（asset_type, oss_url, original_filename）
  2. 根据素材类型决定处理方式：
     - image 类型：调用 LLM Vision API 获取图片描述 → 注入 prompt
     - 其他类型：生成简单的文本描述包含类型和 URL
  3. 异常处理：Vision API 调用失败时返回占位描述
     （又一个优雅降级点 —— 不给图片描述也能生成游戏）

  这种设计让系统对不同的 LLM 供应商和素材类型都有适当的处理策略，
  体现了"容错优先"的设计哲学。
"""

import logging

from app.agent.adapters.base import LLMAdapter
from app.agent.generators.html5_game import HTML5GameGenerator, GameGenerationContext
from app.agent.processors.validator import GameValidator
from app.agent.processors.packager import GamePackager

# 日志记录器使用模块名 (app.agent.harness)，
# 在日志输出中可以清晰定位到 harness.py
logger = logging.getLogger(__name__)


class GameGenerationHarness:
    """
    游戏生成流水线的主编排器 (Orchestrator)。

    【职责】
      1. 初始化各子组件（生成器、验证器、打包器）
      2. 按阶段顺序执行流水线
      3. 管理进度报告（通过 _update_progress）
      4. 处理验证失败 → 自动修复 → 再验证的闭环
      5. 处理 MinIO 不可用时的优雅降级
      6. 最终化数据库记录

    【使用示例】
      adapter = create_adapter()  # 从工厂函数获取适配器
      harness = GameGenerationHarness(adapter)
      result_url = await harness.run(task_id, game_id, user_prompt, asset_ids)
      # result_url: "https://oss.example.com/games/{id}/index.html" (正常)
      #         或 "/api/games/{id}/play-html" (降级)

    【不使用 async context manager (__aenter__/__aexit__) 的原因】
      Harness 不管理需要清理的资源（如数据库连接、文件句柄）。
      LLM adapter 的连接池由 SDK 内部管理。如果将来添加了需要
      清理的资源，可以考虑实现 __aexit__ 方法。
    """

    def __init__(self, adapter: LLMAdapter):
        """
        初始化流水线编排器。

        【组件初始化】
          所有子组件在 __init__ 中创建（"急初始化"），而非在 run() 中
          按需创建。原因是：
            1. 子组件创建成本极低（只是存储引用，不做网络调用）
            2. 在 __init__ 中初始化可以在 run() 之前发现配置错误
            3. 构造函数明确表达了"这个 harness 需要这些组件"的依赖关系

        【组件之间的数据流】
          Generator 产生 HTML
            → Validator 检查 HTML
              → Generator (fix_errors) 修复 HTML（可选）
                → Packager 上传 HTML
                  → _finalize 保存元数据

          注意：Validator 和 Packager 不需要 adapter 依赖，
          它们是纯粹的本地处理逻辑（HTML 解析 + HTTP 上传）。
        """
        self.adapter = adapter
        self.generator = HTML5GameGenerator(adapter)
        self.validator = GameValidator()
        self.packager = GamePackager()

    async def run(
        self,
        task_id: str,
        game_id: str,
        user_prompt: str,
        asset_ids: list[str] | None = None,
    ) -> str:
        """
        执行完整的游戏生成流水线。

        【参数说明】
          task_id:    生成任务的 UUID（用于进度更新和日志追踪）
          game_id:    游戏实体的 UUID（用于数据库记录和 URL 构造）
          user_prompt:用户的自然语言游戏描述（核心输入）
          asset_ids:  用户上传素材的 UUID 列表（可选，用于 Vision 注入）

        【返回值】
          游戏的可访问 URL，可能是：
            - MinIO OSS 公共 URL（正常路径）
            - API 端点路径（降级路径，如 "/api/games/{id}/play-html"）

        【流水线设计哲学】
          这个 4 阶段流水线采用了"顺序管道"（Linear Pipeline）模式，
          而非更复杂的 DAG（有向无环图）或事件驱动架构。原因：
            - 阶段之间有严格的依赖顺序（必须先生成再验证）
            - 当前只有 4 个阶段，DAG 的复杂度超过收益
            - 顺序管道更容易理解和调试
          如果将来需要在某些阶段并行处理（如多个 LLM 同时生成并投票），
          DAG 可能是更好的选择，但那需要更复杂的结果合并逻辑。
        """

        # 日志记录使用 task_id 前缀，方便在日志中按任务追踪
        # 格式：[uuid-xxxx] 消息内容
        logger.info(f"[{task_id}] Starting generation pipeline for game {game_id}")

        # ================================================================
        # 阶段 1：预处理 (Preprocess) — 素材加载 + Vision 分析
        # ================================================================
        logger.info(f"[{task_id}] Phase 1: Preprocessing")
        # 进度更新到 10% —— 预处理完成
        # 预处理包括：从数据库加载素材、调用 Vision API 分析图片、
        # 构造素材描述列表。整个过程约 1-3 秒。
        await self._update_progress(task_id, 10, "processing")

        # 调用预处理逻辑获取素材描述
        # 即使没有素材（asset_ids 为 [] 或 None），返回空列表，
        # 流水线正常继续 —— 素材是可选的
        asset_descriptions = await self._preprocess_assets(asset_ids or [])

        # 构造生成上下文对象 —— 将所有输入打包为一个结构
        context = GameGenerationContext(
            user_prompt=user_prompt,
            asset_descriptions=asset_descriptions,
            game_id=game_id,
        )

        # ================================================================
        # 阶段 2：LLM 生成 (Generate) — AI 思考并输出 HTML 游戏代码
        # ================================================================
        logger.info(f"[{task_id}] Phase 2: Generating game via LLM")
        # 进度更新到 30% —— 告诉前端"AI 开始工作了"
        # 从 10% 到 30% 的 20% 增量用于覆盖 prompt 构建和 API 请求发起的时间
        await self._update_progress(task_id, 30, "processing")

        # 调用 LLM 生成 HTML 代码
        # 这是整个流水线中最关键也最耗时的步骤（10-30 秒）
        # 在生成期间，进度条停留在 30-70% 之间
        # 如果使用流式生成（generate_stream），可以在每个 token 到达时
        # 微调进度值，让进度条更平滑。当前使用非流式生成做实现简单性。
        html_code = await self.generator.generate(context)

        # 进度更新到 70% —— LLM 生成完成
        # 从 30% 到 70% 的 40% 增量（加上初始的 +20%，共 60%）描述了
        # LLM 生成阶段。详见文件头部关于非线性进度比率的讨论。
        await self._update_progress(task_id, 70, "processing")

        # ================================================================
        # 阶段 3：后处理 (Postprocess) — 验证 + 自动修复 + 打包上传
        # ================================================================
        logger.info(f"[{task_id}] Phase 3: Validating and packaging")

        # ---- 步骤 3a：验证 ----
        # 对生成的 HTML 执行 6 项启发式检查（详见 validator.py 注释）
        validation = self.validator.validate(html_code)

        if not validation.is_valid:
            # 验证未通过（存在致命错误，如 eval()、无实质性代码）
            logger.warning(
                f"[{task_id}] Validation failed: {validation.errors}. Attempting auto-fix."
            )

            # ---- 步骤 3b：自动修复 ----
            # 将错误列表和原始代码发送给 LLM，要求修复
            # 这是"AI 审查 AI"的自我修正流程
            try:
                html_code = await self.generator.fix_errors(
                    html_code, validation.errors
                )
                # 修复后重新验证 —— 确保修复没有引入新错误
                validation = self.validator.validate(html_code)
                if not validation.is_valid:
                    # 修复后仍然存在问题 —— 这是"尽力而为"的终点
                    logger.error(
                        f"[{task_id}] Auto-fix also failed: {validation.errors}"
                    )
                    # 关键决策：继续交付当前版本（不完美的游戏）
                    # 而非抛异常让任务失败。大多数情况下，这些错误
                    # 不致命 —— 游戏仍可运行（"Continue anyway"）。
            except Exception as e:
                # 修复过程本身崩溃（如 LLM API 错误）
                # 不阻断流水线 —— 使用原始 HTML 继续
                logger.error(f"[{task_id}] Auto-fix exception: {e}")

        # 记录警告（不影响 is_valid 的问题）
        if validation.warnings:
            logger.warning(f"[{task_id}] Validation warnings: {validation.warnings}")

        # 进度更新到 85% —— 验证和修复完成
        await self._update_progress(task_id, 85, "processing")

        # ---- 步骤 3c：打包上传 ----
        logger.info(f"[{task_id}] Phase 4: Packaging & uploading")

        try:
            # 正常路径：上传到 MinIO OSS
            oss_url = await self.packager.package_and_upload(game_id, html_code)
        except Exception as e:
            # 降级路径：MinIO 不可用，使用 API 端点作为 URL
            # 这是"优雅降级"的核心实现 —— 详见文件头部注释
            logger.warning(f"[{task_id}] MinIO upload failed ({e}), storing in DB instead")
            oss_url = f"/api/games/{game_id}/play-html"

        # ================================================================
        # 阶段 4：最终化 (Finalize) — 写数据库 + 更新状态
        # ================================================================
        await self._finalize(task_id, game_id, oss_url, html_code)

        # 流水线完成 —— 日志记录最终 URL 用于调试
        logger.info(f"[{task_id}] Generation complete: {oss_url}")
        return oss_url

    async def _preprocess_assets(self, asset_ids: list[str]) -> list[str]:
        """
        加载用户上传的素材并通过 Vision API 生成文字描述。

        【为什么作为独立方法而不是内联在 run() 中？】
          1. 单一职责：run() 负责编排，_preprocess_assets() 负责素材处理
          2. 可测试性：可以独立测试素材处理逻辑（mock Vision API）
          3. 可重用性：将来如果有"重新生成"功能，可以复用此方法

        【数据库会话的管理】
          使用 async_session() 上下文管理器，保证数据库连接在使用后
          正确归还到连接池。不使用全局 db session，因为流水线可能
          运行在 FastAPI 的 BackgroundTasks 中，请求级别的 session
          可能已经关闭。

        【Vision API 调用的顺序执行】
          如果用户上传了多个图片（如 3 张），本方法依次调用
          describe_image()（串行而非并行）。为什么不并行？

          原因：
            1. 大多数用户只上传 1 张图片（并行的需求不强烈）
            2. LLM 供应商通常有速率限制（RPM: Requests Per Minute），
               并行调用可能触发限流（429 Too Many Requests）
            3. 串行调用更简单、可预测、易于调试
            如果未来需要处理大量图片（如 10+ 张），可以用 asyncio.gather()
            并行调用，但需要加入信号量做并发控制。
        """
        if not asset_ids:
            return []

        # 延迟导入，避免循环依赖
        # async_session 和 GameAsset 只在需要访问数据库时才加载
        from app.database import async_session
        from app.services import game_service

        descriptions = []

        # 使用 async_session 上下文管理器管理数据库连接的生命周期
        async with async_session() as db:
            for asset_id in asset_ids:
                # 直接通过 SQLAlchemy select 查询素材记录
                # 使用 select + where 而非 game_service.get_asset_by_id()
                # 因为后者可能不存在（这是内部数据访问而非业务逻辑）
                from sqlalchemy import select
                from app.models.game import GameAsset

                result = await db.execute(
                    select(GameAsset).where(GameAsset.id == asset_id)
                )
                asset = result.scalar_one_or_none()

                # 如果素材不存在（可能已被删除），跳过
                if not asset:
                    continue

                # 根据素材类型选择不同的处理策略
                if asset.asset_type == "image":
                    try:
                        # 调用 LLM 的 Vision API 分析图片
                        # 这将返回图片的详细描述（颜色、形状、风格等）
                        desc = await self.adapter.describe_image(asset.oss_url)
                        descriptions.append(
                            f"Image '{asset.original_filename}': {desc}"
                        )
                    except Exception as e:
                        # Vision API 调用失败 —— 优雅降级
                        # 不抛异常，返回文件名信息作为最小上下文
                        # 游戏仍可根据用户的文字描述生成
                        logger.warning(f"Failed to describe image {asset.id}: {e}")
                        descriptions.append(
                            f"Image '{asset.original_filename}' (description unavailable)"
                        )
                else:
                    # 非图片素材（如音频、3D 模型等）
                    # 不同供应商处理方式不同，当前仅记录基本信息
                    # 将来可以扩展：视频分析、3D 模型解析等
                    descriptions.append(
                        f"Asset '{asset.original_filename}' (type: {asset.asset_type}, url: {asset.oss_url})"
                    )

        return descriptions

    async def _update_progress(self, task_id: str, progress: int, status: str):
        """
        更新生成任务的进度和状态（写入数据库）。

        【为什么把数据库更新包装在一个独立方法中？】
          1. 异常隔离：数据库更新失败不应阻断流水线
             （例如数据库暂时不可用，但游戏已经生成好了）
          2. 集中日志：所有进度更新相关的日志和错误处理集中管理
          3. 将来扩展：可以在这里添加 WebSocket 推送，
             实时通知前端进度变化

        【性能考量】
          每次 _update_progress 都会创建新的数据库连接（async_session）。
          这比保持长连接更安全（避免连接泄漏），但在高频调用时
          （如流式生成中每 100ms 更新一次）会有连接开销。
          对于当前的调用频率（每个阶段 1-2 次），这个开销可忽略。

        【延迟导入的复用说明】
          from app.database import async_session 在本文件中多次出现
          （_preprocess_assets 和 _update_progress 中各一次）。
          这是为了保持方法的独立性 —— 每个方法可以独立测试和重用，
          不需要依赖外部模块的 import 状态。如果觉得重复，
          可以移到文件顶部，但延迟导入避免了模块加载时的循环依赖风险。
        """
        try:
            from app.database import async_session
            from app.services import task_service

            async with async_session() as db:
                await task_service.update_task_progress(
                    db, task_id, progress=progress, status=status
                )
        except Exception as e:
            # 进度更新失败不阻断流水线 —— 游戏已经生成了
            # 最坏情况：用户在 UI 上看到旧的进度值，但游戏已经完成
            logger.error(f"Failed to update task progress: {e}")

    async def _finalize(
        self, task_id: str, game_id: str, oss_url: str, html_code: str
    ):
        """
        最终化流水线 —— 更新任务和游戏数据库记录。

        【双存储策略】
          1. Task 记录（操作日志）：
             - progress=100, status="completed"
             - result_oss_url: 存储最终的游戏 URL（OSS 直链或 API 端点）
             - llm_response_raw: 存储完整 HTML（用于降级路径和调试）
               截断到 50000 字符，防止超长 HTML 撑爆数据库字段

          2. Game 记录（游戏实体）：
             - game_url: 使用 API 端点而非 OSS 直链作为主 URL
               原因见 packager.py 中 Content-Disposition 问题的讨论
             - status: "preview"（预览状态，可被用户访问）
               将来可能的状态：preview → published → archived

        【为什么 game_url 使用 API 端点而非 OSS 直链？】
          这是解决 Content-Disposition 问题的关键设计决策：

          问题：MinIO 的 Content-Disposition 默认为 attachment，
               浏览器在 iframe 中加载时会触发下载而非渲染。

          方案 A：修改 MinIO 的 Content-Disposition 为 inline
            → 需要 MinIO bucket policy 配置，不是所有部署都支持

          方案 B：使用 API 端点代理
            → FastAPI 可以精确控制 Content-Disposition 响应头
            → 同时实现了 OSS→DB 的降级路径（统一入口）
            → /api/games/{id}/play-html 对外暴露一致的接口

          选择方案 B 是因为它同时解决了两个问题：
            - Content-Disposition 控制
            - 优雅降级（OSS 故障时的备用路径）

        【game 的提交时机】
          第 203 行：await db.commit()
          在 harvester 中直接操作 db 事务，而不是通过 game_service。
          这是因为 _finalize 需要在一个事务中同时更新 task 和 game，
          保证原子性。如果通过 game_service（它会创建自己的 session），
          两个更新可能不在同一个事务中。
        """
        try:
            from app.database import async_session
            from app.services import task_service, game_service

            async with async_session() as db:
                # ---- 更新任务记录 ----
                await task_service.update_task_progress(
                    db,
                    task_id,
                    progress=100,
                    status="completed",
                    result_oss_url=oss_url,
                    # 保存完整 HTML 用于降级路径和调试审计
                    # 50000 字符限制：平衡存储成本和功能完整性
                    # 大多游戏 HTML 在 10000-30000 字符范围内
                    llm_response_raw=html_code[:50000],
                )

                # ---- 更新游戏记录 ----
                game = await game_service.get_game(db, game_id)
                if game:
                    # 使用 API 端点作为主 URL（解决 Content-Disposition 问题）
                    # 不用 MinIO 直链：避免 iframe 加载时触发下载
                    game.game_url = f"/api/games/{game_id}/play-html"
                    # 设置为预览状态：游戏已可播放但未正式发布
                    game.status = "preview"
                    # 提交事务 —— task 和 game 更新在同一事务中
                    await db.commit()

        except Exception as e:
            # 最终化失败不阻断流水线 —— 核心价值（游戏 HTML）已经生成
            # 最坏情况：数据库状态不一致（进度显示未完成但游戏已生成）
            # 这种情况需要手动修复，但用户可以获得游戏 URL
            logger.error(f"Failed to finalize task/game: {e}")
