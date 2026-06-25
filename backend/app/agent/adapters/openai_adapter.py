"""
=============================================================================
OpenAI GPT LLM 适配器 (OpenAI Adapter for Chat Completions API)
=============================================================================

【核心适配点：base_url 参数的设计意图】

本适配器接受一个可选的 base_url 参数（第 13 行）：
  def __init__(self, api_key: str, model: str = "gpt-4o", base_url: str | None = None)

这不是一个简单的配置项，而是一个具备深远架构意义的参数。理解其价值：

  1. OpenAI 兼容协议 (OpenAI-Compatible Protocol)：
     OpenAI 的 Chat Completions API（POST /v1/chat/completions）已成为事实上的
     行业标准协议。以下供应商都实现了此协议：
       - DeepSeek        (https://api.deepseek.com)
       - Groq            (https://api.groq.com/openai)
       - Together AI     (https://api.together.xyz)
       - Fireworks       (https://api.fireworks.ai/inference)
       - 本地 Ollama      (http://localhost:11434/v1)
       - 本地 vLLM       (http://localhost:8000/v1)
       - Azure OpenAI    (https://{resource}.openai.azure.com)
       - 阿里百炼         (https://dashscope.aliyuncs.com/compatible-mode)
       - 硅基流动         (https://api.siliconflow.cn)

     只需改变 base_url + model，同一个 OpenAIAdapter 类可以对接 10+ 个供应商。
     这就是 "兼容层" 策略的力量 —— 一次编写，到处运行。

  2. 与 DeepSeek 适配器的关系（继承与复用的精妙设计）：
     DeepSeekAdapter 继承 OpenAIAdapter，唯一的变化是：
       - 默认 base_url 硬编码为 "https://api.deepseek.com"
       - 默认 model 为 "deepseek-chat"
     DeepSeekAdapter 不需要重写 generate()、generate_stream() 等方法，
     因为 DeepSeek 的 API 与 OpenAI 完全兼容。详见 deepseek_adapter.py 的
     "继承 vs 组合" 注释。

  3. 代理/网关场景：
     base_url 可以指向自定义代理服务器（如 LiteLLM、one-api），
     实现统一的 token 计费、速率限制和审计日志。生产环境常用。

  4. None 默认值的含义：
     base_url=None 时，openai 库使用默认的 "https://api.openai.com/v1"。
     显式传 None 和完全不传参数效果一致，但 None 作为默认值比字符串硬编码
     更灵活 —— 允许 openai 库未来改变默认端点而不破坏兼容性。

【OpenAI Chat Completions API 响应结构】

非流式响应：
  {
    "choices": [
      {
        "index": 0,
        "message": {
          "role": "assistant",
          "content": "<!DOCTYPE html>..."   <-- 实际生成的文本
        },
        "finish_reason": "stop"
      }
    ],
    "usage": {
      "prompt_tokens": 500,
      "completion_tokens": 8000,
      "total_tokens": 8500
    }
  }

流式响应（每个 chunk）：
  {
    "choices": [
      {
        "index": 0,
        "delta": {
          "content": "游戏"  <-- 增量文本，可能为 None（首/尾 chunk）
        },
        "finish_reason": null  <-- 最后一个 chunk 才会是 "stop"
      }
    ]
  }

【关键差异：OpenAI vs Anthropic vision API】

  OpenAI:  直接传图片 URL
    {"type": "image_url", "image_url": {"url": "https://..."}}

  Anthropic: 需要 base64 编码
    {"type": "image", "source": {"type": "base64", "media_type": "...", "data": "..."}}

  OpenAI 的方式更简单（不需要下载+编码），但如果图片在私有 MinIO 中，
  需要确保 API 服务器能访问该 URL。Anthropic 的方式虽然多一步，
  但对访问控制更友好（认证在客户端完成，不依赖服务器间网络）。
"""

from typing import AsyncIterator

from openai import AsyncOpenAI

from app.agent.adapters.base import LLMAdapter


class OpenAIAdapter(LLMAdapter):
    """
    OpenAI GPT 和所有 OpenAI 兼容 API 的通用适配器。

    【"OpenAI-compatible APIs" 意味着什么？】
      任何实现了以下接口的服务都可以使用本适配器：
        POST /v1/chat/completions
        请求体：{"model": "...", "messages": [...], "temperature": ..., "max_tokens": ...}
        响应体：{"choices": [{"message": {"content": "..."}}]}

      这行注释（第 11 行）不是装饰 —— 它是架构契约的声明，
      表明本类不仅服务于 api.openai.com，也服务于整个 OpenAI 兼容生态。

    【默认模型 "gpt-4o"】
      GPT-4o ("omni") 是 OpenAI 的多模态旗舰模型：
        - 原生支持图片输入，describe_image() 直接传 URL
        - 代码生成能力强，适合生成完整的 HTML5 游戏
        - 速度比 GPT-4 Turbo 快 2 倍
        - 128K token 上下文窗口
    """

    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: str | None = None):
        """
        初始化 OpenAI 兼容适配器。

        【kwargs 动态构造的设计模式】
          第 15-17 行使用了条件参数构造模式：
            kwargs = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self.client = AsyncOpenAI(**kwargs)

          为什么不用下面这种写法？
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)
          原因：openai 库在 base_url=None 和完全不传 base_url 时行为有细微差异。
          base_url=None 有时会覆盖默认 URL 为 "https://api.openai.com/v1/v1/"
          （路径拼接 bug）。条件传入可以保证只有用户显式指定时才设置 base_url，
          避免触发 SDK 内部的路径处理边缘情况。

        【为什么不把 client 设为单例？】
          单例模式意味着所有适配器共享同一个 httpx 连接池。但 base_url 不同时，
          连接池也应该是隔离的 —— api.deepseek.com 的连接不应该与 api.openai.com
          复用 HTTP/2 多路复用通道。每个适配器实例维护自己的 client 是更安全的设计。
          如果未来需要连接池共享，可以在工厂函数层管理。
        """
        super().__init__(api_key, model)
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = AsyncOpenAI(**kwargs)

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 16000,
    ) -> str:
        """
        使用 OpenAI Chat Completions API 生成完整响应。

        【system prompt 的处理方式】
          OpenAI 将 system prompt 作为 messages 数组中的一个元素：
            {"role": "system", "content": system_prompt}

          这与 Claude 的顶层 system 参数完全不同。详见 claude_adapter.py 头部注释
          中对两种设计哲学的对比分析。

        【max_tokens 参数】
          OpenAI 的 max_tokens 限制了 completion 部分（不包含 prompt）。
          16000 token 足够生成约 12000 行 HTML/CSS/JS 代码。
          注意：如果上下文窗口是 128K，16000 max_tokens 只占总窗口的一小部分，
          剩余的 112K 可以容纳非常长的 system prompt 和对话历史。

        【为什么用 response.choices[0].message.content or "" 而不是直接取？】
          - choices 数组理论上可能为空或 content 为 None
          - 使用 or "" 确保返回值始终是字符串类型
          - 即使 content 为 None（模型拒绝回答等边缘情况），也不会抛 TypeError
          - 空字符串会被上游的验证器捕获并报告为"无实质性内容"

        【finish_reason 说明】
          OpenAI 的 finish_reason 字段可能的值：
            - "stop": 正常结束，模型自行决定停止
            - "length": 达到 max_tokens 限制，内容被截断
            - "content_filter": 触发了内容安全过滤器
            - "tool_calls": 模型请求调用工具（本项目不使用）
          这里没有检查 finish_reason，因为即使截断，剩余代码通常也可用。
          如果需要严格检查，可以在 harness.py 层增加 finish_reason 验证逻辑。
        """
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""

    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 16000,
    ) -> AsyncIterator[str]:
        """
        使用 OpenAI Chat Completions API 流式生成。

        【stream=True 的工作原理】
          当设置 stream=True 时，API 返回 SSE 事件流而非单个 JSON 对象。
          每个事件对应一个 token 的增量（delta）。

        【chunk.choices[0].delta.content 的 None 值处理】
          第 58 行的 if 判断至关重要：
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

          原因：在流式响应的某些 chunk 中，delta.content 为 None。
          例如：
            - 第一个 chunk 可能只包含 role: "assistant" 信息，content 为 None
            - 包含 tool_calls 的 chunk 中 content 也为 None
          如果直接 yield None，上层调用者（如 SSE 端点）可能会崩溃或产生空数据帧。

        【async for + yield 的管道模式】
          这个函数本质上是"异步管道"：上游是 OpenAI 的 SSE 流，
          下游是前端 EventSource 的 onmessage 回调。
          本函数负责从 OpenAI 格式中提取纯文本 token 并转发。
          这种设计让上层（Web 端点）不需要知道 OpenAI 的响应格式细节。

        【与 Claude 流式适配器的对比】
          - Claude:  async with client.messages.stream(...) as stream:
                       async for text in stream.text_stream:
                         yield text
                     SDK 封装得更好，text_stream 已经是纯文本的 async generator

          - OpenAI:  stream = await client.chat.completions.create(stream=True)
                       async for chunk in stream:
                         if chunk.choices[0].delta.content:
                           yield chunk.choices[0].delta.content
                     需要手动处理 delta 的 None 值，更底层但也更灵活
        """
        stream = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
        )
        async for chunk in stream:
            # delta.content 可能为 None（首帧或工具调用帧）
            # 过滤掉 None 值确保 yield 出去的都是有效字符串
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def describe_image(self, image_url: str) -> str:
        """
        使用 GPT-4o 的视觉能力描述图片。

        【与 Claude 适配器的关键区别】
          OpenAI 直接传图片 URL（不需要下载+base64 编码）：
            {"type": "image_url", "image_url": {"url": image_url}}

          这意味着：
            1. 代码更简单（少了 httpx 下载 + base64 编码两个步骤）
            2. API 延迟更低（OpenAI 服务器直接从 URL 下载，可能比客户端下载再上传更快）
            3. 但要求 image_url 对公网可访问（OpenAI 服务器需要能访问该 URL）

        【MinIO OSS 的 URL 可访问性】
          本项目中图片存储在对公网开放的 MinIO，所以 image_url 可以直接传递。
          如果未来迁移到私有的、需认证的存储，需要改用 base64 方案。

        【max_tokens=500 的设计】
          图片描述用于注入 system prompt，作为程序化美术的参考。
          500 token（约 200-250 词）足以描述关键视觉元素：
            - 颜色方案、形状、角色特征、场景风格
          不需要更长的描述 —— 太长的描述可能稀释 system prompt 中
          更重要的游戏规则约束。

        【content 数组的结构】
          这是 OpenAI 的多模态内容格式：
            content: [
              {"type": "image_url", "image_url": {"url": "..."}},  // 图片
              {"type": "text", "text": "Describe this image..."},   // 文字指令
            ]
          注意：GPT-4o 的 image_url 支持可选的 "detail" 参数
          ("low", "high", "auto")，控制图片分析的分辨率。
          这里使用默认的 "auto"，让模型自行决定。
        """
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
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
        return response.choices[0].message.content or "No description available."
