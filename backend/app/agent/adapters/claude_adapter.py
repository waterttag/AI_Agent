"""
=============================================================================
Anthropic Claude LLM 适配器 (Claude Adapter for Anthropic Messages API)
=============================================================================

【核心适配点：system 参数的位置差异】

这是本项目中最重要的 API 适配差异，值得深入理解。

  Anthropic Messages API:
    请求体结构如下：
    {
      "model": "claude-sonnet-4-20250514",
      "max_tokens": 16000,
      "temperature": 0.7,
      "system": "You are an expert game developer...",    <-- 顶层参数，不在 messages 数组中
      "messages": [
        {"role": "user", "content": "Make a snake game..."}
      ]
    }
    system 是一个独立的顶层字段，与 messages 数组平级。
    这意味着 system prompt 在 API 层面被特殊处理 —— Anthropic 为它
    预留了专门的注意力机制，不会被用户输入"淹没"。

  OpenAI Chat Completions API:
    请求体结构如下：
    {
      "model": "gpt-4o",
      "max_tokens": 16000,
      "temperature": 0.7,
      "messages": [
        {"role": "system", "content": "You are an expert game developer..."},
        {"role": "user", "content": "Make a snake game..."}
      ]
    }
    system prompt 是 messages 数组中的一个普通元素，只是 role 字段为 "system"。
    在 Transformer 架构中，它和其他消息走同样的注意力通道。

  【差异的实际影响】
    1. API 语义不同：
       Anthropic 将 system 视为"顶层指令"，优先级高于 messages 中的所有内容。
       OpenAI 将 system 视为"对话中的第一条消息"，理论上可以被后续消息覆盖。

    2. 缓存策略不同：
       Anthropic 的 system prompt 可以单独缓存（prompt caching），
       因为它是独立参数，不受 messages 变化影响。
       OpenAI 的自动缓存需要整个 messages 前缀不变。

    3. token 计费：
       在 Anthropic API 中，system prompt 不计入 messages 的 token 数限制。
       在 OpenAI API 中，system 消息和 user 消息一样计入上下文窗口。

  【本适配器的处理】
    本文件在 generate() 和 generate_stream() 中使用：
      system=system_prompt           (Anthropic 风格)
    而 openai_adapter.py 中使用：
      messages=[{"role":"system",...}] (OpenAI 风格)
    上层调用者（harness.py）不需要关心这个差异 —— 这就是适配器模式的价值。

【Anthropic 官方 Python SDK】
  使用 `anthropic` 包中的 AsyncAnthropic 客户端：
    - 同步版本 Anthropic() 会阻塞事件循环，FastAPI 项目中一律用 AsyncAnthropic
    - SDK 内部使用 httpx 做异步 HTTP 请求
    - 流式响应通过 async context manager + async generator 实现

【Claude 模型命名约定】
  "claude-sonnet-4-20250514" 中：
    - claude:        品牌名
    - sonnet:        型号层级 (haiku < sonnet < opus)
    - 4:             大版本号
    - 20250514:     快照日期 (YYYYMMDD)，说明这是一个固定版本，行为可复现
"""

from typing import AsyncIterator

from anthropic import AsyncAnthropic

from app.agent.adapters.base import LLMAdapter


class ClaudeAdapter(LLMAdapter):
    """
    Anthropic Claude 模型的 LLM 适配器。

    【为什么选择 Claude 作为默认供应商？】
      1. 代码生成能力强：Claude 3.5 Sonnet/Claude 4 在 HTML/CSS/JS 生成评测中表现优异
      2. 长上下文窗口：200K token 上下文，足以容纳复杂的系统提示 + 完整的游戏代码
      3. 安全护栏适中：相比某些过度审查的模型，Claude 对游戏生成（包含射击/战斗元素）的拒绝率更低
      4. 原生 vision 能力：支持 base64 图片输入，用于分析用户上传的参考图
      5. Prompt caching：可缓存 system prompt 减少延迟和费用

    【默认模型 "claude-sonnet-4-20250514"】
      这是 Claude Sonnet 4 的一个固定快照。使用日期版本号而非 "claude-sonnet-4"
      这样的浮动标签，确保行为一致性 —— 不会因 Anthropic 更新模型而导致
      生成质量突变。
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        """
        初始化 Claude 适配器。

        【AsyncAnthropic 客户端创建】
          - 只需要 api_key（从环境变量/配置文件注入）
          - SDK 自动处理认证头的构建（x-api-key header）
          - 默认 base_url 指向 api.anthropic.com
          - 不使用 api_version 参数（使用 SDK 默认的最新稳定版本）

        【设计注记】
          客户端在 __init__ 中创建一次，而非每次调用 generate() 时新建。
          这是因为 httpx 的连接池复用可以显著减少 SSL 握手开销 ——
          对于高频调用的场景，这可以将延迟降低 50-200ms。
        """
        super().__init__(api_key, model)
        self.client = AsyncAnthropic(api_key=api_key)

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 16000,
    ) -> str:
        """
        使用 Claude Messages API 生成完整响应。

        【API 调用详解】
          self.client.messages.create() 映射到 POST /v1/messages

        【关键参数】
          system=system_prompt
            这是 Anthropic API 的独有顶层参数（见文件头部注释）。
            system prompt 不在 messages 数组中，API 会特殊处理它。

          messages=[{"role": "user", "content": user_prompt}]
            Messages API 的 messages 数组需要交替 user/assistant 角色。
            由于这是单轮生成（无对话历史），数组中只有一个 user 消息。
            如果有多轮对话，需要严格按照 user -> assistant -> user -> ... 的顺序。

          max_tokens=16000
            Anthropic API 要求 max_tokens 为必填参数（OpenAI 是可选的）。
            16000 token 足够 Claude 生成完整的 HTML5 游戏，
            包含 Canvas 绘制代码、游戏循环逻辑和 UI 元素。
            一个中等复杂的游戏 HTML 通常在 3000-8000 行之间，约 8000-15000 token。

        【响应解析】
          response.content 是一个 ContentBlock 列表，类型可以是：
            - "text": 文本内容块
            - "tool_use": 工具调用块（本项目未使用 Claude 的 tool use 功能）
          遍历列表找到第一个 text 类型的块并返回其内容。
          如果没有任何文本块（极端情况），返回空字符串。

        【与 OpenAI 适配器的对比】
          Claude:  response.content[0].text  （ContentBlock 对象）
          OpenAI:  response.choices[0].message.content  （ChatCompletion 对象）
        """
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt},
            ],
        )
        # 从 content 数组中提取第一个文本块的内容
        # response.content 的结构：[ContentBlock(type="text", text="..."), ...]
        # 注意：Claude 的流式和非流式响应结构完全不同，这里是非流式版本
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""

    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 16000,
    ) -> AsyncIterator[str]:
        """
        使用 Claude Messages API 流式生成。

        【流式机制详解】
          self.client.messages.stream() 返回一个 MessageStreamManager 上下文管理器。
          - 进入 async with 块时，SDK 发起 POST /v1/messages (stream: true)
          - stream.text_stream 是一个 async generator，逐 token yield
          - 底层是 SSE (Server-Sent Events) 协议：
              event: content_block_delta
              data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"游戏"}}

        【与 OpenAI 流式的关键区别】
          - Claude: 使用专门的 stream() 方法，返回上下文管理器
          - OpenAI: 在 create() 中传 stream=True 参数
          - Claude: text_stream 直接 yield 纯文本字符串
          - OpenAI: 需要手动检查 chunk.choices[0].delta.content 是否为 None

        【async for 的工作原理】
          "async for text in stream.text_stream" 等价于：
            iterator = stream.text_stream.__aiter__()
            while True:
                try:
                    text = await iterator.__anext__()
                    yield text
                except StopAsyncIteration:
                    break
          每次迭代中，事件循环会暂停此协程，等待 SDK 收到下一个 SSE 事件。
        """
        async with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt},
            ],
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def describe_image(self, image_url: str) -> str:
        """
        使用 Claude 的原生视觉能力描述图片。

        【工作流程】
          1. 通过 httpx 异步下载图片（不能直接用 URL，因为 Anthropic API 需要 base64）
          2. 将二进制数据 base64 编码
          3. 构造 vision 格式的 messages 请求
          4. 返回图片的文字描述（限制 200 词以内，专注游戏相关元素）

        【为什么下载图片而不是传 URL？】
          Anthropic Messages API 的图片输入要求 base64 编码（或 /v1/files 上传）。
          不支持直接传图片 URL。这与 OpenAI 不同——OpenAI 支持直接传 image_url。
          这是另一个需要适配器层处理的供应商差异。

        【media_type 检测】
          从 HTTP 响应头的 Content-Type 获取，默认回退到 "image/png"。
          支持的格式：image/png, image/jpeg, image/gif, image/webp。
          Claude 不支持 SVG 作为图片输入，需要使用 raster 格式。

        【max_tokens=500 的设计考量】
          图片描述不需要很长 —— 只需要提取游戏相关的视觉元素
          （颜色、形状、角色、风格）即可。500 token 约等于 200-250 个英文单词。
          限制 token 数既可以降低延迟（约 2-3 秒），也可以控制成本。

        【为什么使用延迟导入 (lazy import)？】
          httpx 和 base64 只在 describe_image() 中需要。如果用户不上传图片，
          这些导入完全不需要。延迟导入避免了不必要的模块加载开销，
          也有助于保持命名空间清洁。
        """
        # ---- 步骤 1：异步下载图片 ----
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
            image_data = resp.content

        # ---- 步骤 2：base64 编码 ----
        import base64

        b64_image = base64.b64encode(image_data).decode("utf-8")
        media_type = resp.headers.get("content-type", "image/png")

        # ---- 步骤 3：构造 vision 请求 ----
        # messages 数组中的 content 是一个列表（多模态内容块），而非简单字符串
        # 包含 image 块（base64 编码的图片）+ text 块（分析指令）
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Describe this image in detail, focusing on visual elements "
                                "relevant for a game: colors, shapes, characters, objects, "
                                "style, and any animation cues. Keep under 200 words."
                            ),
                        },
                    ],
                }
            ],
        )
        for block in response.content:
            if block.type == "text":
                return block.text
        return "No description available."
