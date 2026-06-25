"""
=============================================================================
DeepSeek LLM 适配器 (DeepSeek Adapter — 继承 OpenAI 适配器)
=============================================================================

【架构决策：为什么 DeepSeekAdapter 继承 OpenAIAdapter？】

这是一个值得深入讨论的设计选择。下面是完整的 trade-off 分析。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
方案 A：继承 (Inheritance) — 本项目采用
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  class DeepSeekAdapter(OpenAIAdapter):
      def __init__(self, api_key, model="deepseek-chat"):
          super().__init__(api_key, model, base_url="https://api.deepseek.com")

  优点：
    1. 零重复代码：generate()、generate_stream() 完全复用，一行都不需要重写
    2. 语义正确：DeepSeek "是一个" OpenAI 兼容的 API，IS-A 关系成立
    3. LSP（里氏替换原则）兼容：DeepSeekAdapter 可以用在任何期望 OpenAIAdapter 的地方
    4. 自动继承改进：如果 OpenAIAdapter 后来修复了 bug，DeepSeekAdapter 自动受益
    5. describe_image() 的重写（override）语义清晰：子类覆盖了父类的行为

  缺点：
    1. 耦合度较高 —— 对 OpenAIAdapter 的修改可能影响 DeepSeekAdapter
    2. DeepSeekAdapter "太像" OpenAIAdapter，不够独立（但这正是我们需要的）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
方案 B：组合 (Composition) — 未采用
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  class DeepSeekAdapter(LLMAdapter):
      def __init__(self, api_key, model="deepseek-chat"):
          super().__init__(api_key, model)
          self._openai = OpenAIAdapter(api_key, model, base_url="https://api.deepseek.com")

      async def generate(self, ...) -> str:
          return await self._openai.generate(...)  # 委托给内部对象

      # 需要为每个方法写委托代码 —— 重复且容易遗漏

  优点：
    1. 松耦合 —— DeepSeekAdapter 不依赖 OpenAIAdapter 的内部实现细节
    2. 更灵活 —— 可以在委托前后添加额外逻辑（如日志、重试）
    3. "优先使用组合而非继承" 是 GoF 设计模式的经典建议

  缺点：
    1. 大量样板委托代码（boilerplate delegation）：3 个方法 × 2 行 = 6 行重复
    2. LLMAdapter 接口变化时，需要同时修改两个类
    3. 没有表达 "DeepSeek 就是 OpenAI 兼容" 的语义
    4. isinstance(deepseek, OpenAIAdapter) 返回 False，破坏了多态性

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
结论：当 IS-A 关系成立且 API 完全兼容时，继承优于组合
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  DeepSeek API 不仅在 HTTP 层面兼容 OpenAI，在行为语义上也完全一致。
  这不是"恰好使用相似的协议"（那应该用组合），而是"故意实现了完全相同的协议"。
  因此继承是正确的选择。

  相反的例子：如果未来对接一个 "类似但不完全兼容" 的 API（如 Gemini 的
  generateContent 接口），就应该用组合模式在 LLMAdapter 抽象层之下封装，
  而不是继承 OpenAIAdapter。

【DeepSeek API 概述】
  - 官网: https://platform.deepseek.com
  - API 端点: https://api.deepseek.com/v1/chat/completions
  - 授权头: Authorization: Bearer {api_key}
  - 模型:
      deepseek-chat     — 通用对话模型，速度快，成本低（约 $0.14/1M tokens）
      deepseek-reasoner — 推理增强模型，支持 chain-of-thought，质量更高但更慢
  - 上下文窗口: 128K tokens (deepseek-chat)
  - 关键限制: deepseek-chat 不支持多模态（无 vision），仅文本

【describe_image() 的优雅降级 (Graceful Degradation)】
  DeepSeek 不支持图片分析，但我们不能直接抛异常或返回错误字符串，
  因为这样会破坏 harvester.py 的流水线。以下是设计考量：

    返回内容（第 37-41 行）：
      "An uploaded asset file ({filename}). DeepSeek does not support image analysis;
       the game should be generated based on the user's text description."

    这个字符串的设计意图：
      1. 不返回空字符串 —— 空字符串会让下游以为"图片无内容"，误导 prompt 构建
      2. 包含文件名 —— 让 LLM 知道"有这么个文件"，但不依赖其视觉内容
      3. 明确告知限制 —— "should be generated based on user's text description"
         是指令性的，引导 LLM 使用用户的文字描述而非假设图片细节
      4. 这不是 bug 而是 feature —— 体现了系统对不同供应商能力的自适应

    与直接抛异常的对比：
      如果抛异常，harness.py 的异常处理逻辑需要区分 "网络错误" vs "不支持此功能"。
      返回占位描述字符串更简单：流水线正常运行，只是少了一些视觉分析信息。
"""

from typing import AsyncIterator

from app.agent.adapters.openai_adapter import OpenAIAdapter


# DeepSeek 官方 API 端点 URL
# 注意：这是一个 OpenAI 兼容端点，路径结构与 OpenAI 完全一致（/v1/chat/completions）
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekAdapter(OpenAIAdapter):
    """
    DeepSeek 模型的 LLM 适配器（通过继承 OpenAI 适配器实现）。

    【继承了什么？】
      从 OpenAIAdapter 继承的方法（无需重写）：
        - generate()         — 完全相同，因为 DeepSeek API 接受 openai 库的标准参数
        - generate_stream()  — 完全相同，SSE 流格式与 OpenAI 一致
        - __init__() 的参数构造逻辑 — base_url 条件传入模式复用

    【重写了什么？】
      - __init__()：硬编码 base_url 指向 DeepSeek 端点，默认 model 设为 deepseek-chat
      - describe_image()：用文本占位描述替代视觉 API 调用（优雅降级）

    【为什么这两个 generate 方法"碰巧"能用？】
      因为 DeepSeek 在 API 层面刻意兼容了 OpenAI 的 Chat Completions 协议。
      当 openai 库初始化时 base_url 指向 https://api.deepseek.com，
      所有后续的 POST /v1/chat/completions 请求都会发送到 DeepSeek 服务器。
      DeepSeek 服务器接受与 OpenAI 相同的 JSON 结构和参数名。
      这是一种"协议兼容层"策略，也是中国 AI 厂商的常见做法，
      方便用户从 OpenAI 迁移而不需要改代码。

    【推荐模型的选型建议】
      - deepseek-chat:     游戏生成的主力，性价比高（约 1/10 的 GPT-4o 价格）
                           适合大量生成任务和初版迭代
      - deepseek-reasoner: 复杂游戏逻辑（如棋类 AI、物理模拟），
                           chain-of-thought 推理可以生成更合理的游戏规则
                           但速度慢 2-3 倍，且价格更高
    """

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        """
        初始化 DeepSeek 适配器。

        【为什么不需要覆盖其他初始化逻辑？】
          super().__init__(api_key, model, base_url=DEEPSEEK_BASE_URL) 做了所有事情：
            - api_key 传给父类 __init__（LLMAdapter.__init__）
            - model 传给父类，覆盖默认的 "gpt-4o"
            - base_url 传递给父类构造函数，父类将其注入 AsyncOpenAI 客户端

        【参数传递链路】
          DeepSeekAdapter.__init__(api_key="sk-xxx", model="deepseek-chat")
            -> OpenAIAdapter.__init__(api_key, model, base_url="https://api.deepseek.com")
              -> LLMAdapter.__init__(api_key, model)  # 存储基本属性
              -> AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                 # 创建 SDK 客户端，后续请求都发往 DeepSeek

          这条链路展示了多层继承中参数如何逐步传递和转换。
          每层只添加自己关心的参数（LLMAdapter 关心 api_key+model，
          OpenAIAdapter 关心 base_url，DeepSeekAdapter 关心默认值），
          职责分离清晰。
        """
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=DEEPSEEK_BASE_URL,
        )

    async def describe_image(self, image_url: str) -> str:
        """
        图片描述方法 —— 纯文本模型的优雅降级实现。

        【为什么需要重写此方法？】
          DeepSeek-chat 是纯文本模型，不支持多模态（vision）输入。
          如果直接使用父类（OpenAIAdapter）的 describe_image() 方法，
          它会构造一个包含 image_url 类型 content 的请求发送给 DeepSeek，
          DeepSeek 会返回 400 错误 "Unsupported content type: image_url"。
          这会导致 harvester.py 中 _preprocess_assets() 产生异常，
          需要 catch 后处理。

          与其让异常发生后再捕获，不如在适配器层面直接提供降级实现。
          这符合"防御性设计"原则 —— 在最接近问题源的地方解决问题。

        【提取文件名的逻辑】
          image_url.split("/")[-1] if "/" in image_url else image_url
          例如：
            "https://minio.example.com/games/abc/assets/player.png"  -> "player.png"
            "player.png"                                              -> "player.png"
          这是一个简单的文件名提取逻辑，用于在占位描述中告知 LLM 文件名。

        【返回值的设计哲学】
          这个返回值的核心思想是：承认限制，但不阻塞流程。
          "the game should be generated based on the user's text description"
          是一个清晰的分流指令 —— LLM 看到这句话后会侧重用户在对话中的文字描述，
          而不会去猜测图片中有什么（那会导致幻觉）。

          这也是"提示工程"在适配器层的应用 —— 不仅适配 API 调用格式，
          也适配下游 prompt 的质量。
        """
        # DeepSeek-chat 是纯文本模型，无法处理图片输入
        # 从 URL 中提取文件名作为上下文信息
        filename = image_url.split("/")[-1] if "/" in image_url else image_url
        return (
            f"An uploaded asset file ({filename}). "
            "DeepSeek does not support image analysis; "
            "the game should be generated based on the user's text description."
        )
