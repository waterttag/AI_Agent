"""
=============================================================================
LLM 适配器抽象基类 (Abstract Base Class for LLM Adapters)
=============================================================================

【设计决策：ABC vs typing.Protocol】

Python 中有两种常见的接口定义方式：
  1. abc.ABC + @abstractmethod  —— 使用继承实现接口，运行时强制检查
  2. typing.Protocol              —— 结构化子类型，鸭子类型，静态检查

本文件选择 ABC（抽象基类）而非 Protocol，原因如下：

  a) 运行时安全性：
     ABC 在实例化时就会抛出 TypeError（如果子类未实现所有抽象方法），
     而不是等到调用缺失方法时才报 AttributeError。这对于多供应商适配器
     至关重要 —— 如果新增供应商（如 Gemini）时漏写了某个方法，立刻就能发现。

  b) 显式意图优于隐式约定：
     "class DeepSeekAdapter(LLMAdapter)" 比 "class DeepSeekAdapter(Protocol)"
     更清晰地表达了 "这是一个 LLM 适配器" 的设计意图。
     Python 之禅：Explicit is better than implicit.

  c) 继承复用：
     __init__ 方法中 api_key 和 model 的赋值逻辑（第 19-21 行）被子类通过
     super().__init__() 复用，避免了每个适配器重复相同的样板代码。
     Protocol 不支持这种实现继承 —— 它只定义结构，不提供行为。

  d) Protocol 的适用场景：
     Protocol 更适合 "我不关心你是什么类，只关心你有没有这个方法" 的场景，
     比如回调函数类型标注、第三方库交互。此处我们有明确的多态层次结构，
     ABC 是自然选择。

  e) isinstance 检查：
     ABC 允许在工厂函数中做 isinstance(adapter, LLMAdapter) 检查，
     这在调试和日志中很有用。

【实现说明】
  - generate()：非流式，返回完整文本，用于需要一次性处理的场景
  - generate_stream()：流式，返回 AsyncIterator[str]，用于 SSE 推送给前端
  - describe_image()：视觉能力，多模态模型特有，DeepSeek 等纯文本模型需要 fallback

【扩展指南】
  要新增 LLM 供应商（如 Gemini、Qwen）：
    1. 继承本类，实现全部三个抽象方法
    2. 在 __init__.py 的 create_adapter() 工厂函数中注册
    3. 在配置文件中添加对应的 provider 名称
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator


class LLMAdapter(ABC):
    """
    LLM 供应商抽象接口（Adapter Pattern — 适配器模式）。

    【什么是适配器模式？】
    适配器模式将一个接口转换成客户期望的另一个接口。
    在这里，Anthropic API *vs* OpenAI API *vs* DeepSeek API 各自有不同的
    请求/响应格式，但上层调用者（harness.py、html5_game.py）只需要统一的
    generate(system, user, temp, tokens) -> str 接口。
    本抽象类定义了那个"统一接口"，各具体适配器负责各自的转换。

    【已实现供应商】
      - ClaudeAdapter   (Anthropic)   — Messages API
      - OpenAIAdapter   (OpenAI)      — Chat Completions API
      - DeepSeekAdapter (继承 OpenAI) — OpenAI 兼容协议

    【为什么用异步 (async)？】
      LLM API 调用本质上是对远程 HTTP 端点的 I/O 操作，延迟通常在
      1-30 秒。如果使用同步调用，FastAPI 的事件循环会被阻塞，导致
      其他请求排队等待。使用 async/await 可以让事件循环在等待
      LLM 响应时处理其他请求，显著提高并发吞吐量。
    """

    def __init__(self, api_key: str, model: str):
        """
        初始化适配器基类。

        【参数说明】
          api_key: 供应商 API 密钥，存储在环境变量中，不在代码里硬编码
          model:   模型名称，如 "claude-sonnet-4-20250514"、"gpt-4o"
                   各子类有各自的默认值

        【设计要点】
          这里不使用依赖注入容器（如 FastAPI Depends），因为：
          1. 适配器通常在后台任务（BackgroundTasks）中创建
          2. 每个任务可能需要不同的 model 参数
          3. 保持了与 Web 框架的解耦 —— harness 不依赖 FastAPI
        """
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 16000,
    ) -> str:
        """
        非流式生成 —— 等待完整响应后一次性返回。

        【参数说明】
          system_prompt: 系统提示词，定义 AI 的角色和行为约束
                         不同 API 处理方式不同：
                           - Anthropic Messages API: 顶层 system 参数（不在 messages 数组中）
                           - OpenAI Chat Completions: messages 数组中的 {"role":"system"} 条目
                         这就是 claude_adapter.py 中需要适配的核心差异点
          user_prompt:   用户输入，包含游戏描述和格式要求
          temperature:   控制随机性，范围 [0, 2]
                         详见 prompts.py 中关于 softmax 温度参数的数学解释
          max_tokens:    最大输出 token 数，默认 16000 足够生成完整 HTML 游戏

        【返回值】
          生成的完整 HTML 代码字符串（可能包含 markdown 代码围栏，
          由 html5_game.py 的 _clean_output() 负责清理）

        【子类必须实现】
          各适配器需要调用各自 SDK 的非流式 API 并返回文本
        """
        ...

    @abstractmethod
    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 16000,
    ) -> AsyncIterator[str]:
        """
        流式生成 —— 逐 token 产出，用于 SSE (Server-Sent Events) 推送给前端。

        【为什么需要流式？】
          生成完整 HTML 游戏通常需要 5000-15000 个 token，非流式模式下
          用户需要等待 10-30 秒看到任何输出，体验极差。
          流式模式可以在第一个 token 生成后（通常 <1 秒）就开始向前端
          推送，配合打字机效果让用户感知到"AI 正在工作"。

        【AsyncIterator 的含义】
          这是一个异步生成器（async generator），调用方使用：
            async for chunk in adapter.generate_stream(...):
                yield f"data: {chunk}\n\n"  # SSE 格式

        【实现差异】
          - Claude: async with client.messages.stream(...) as stream
          - OpenAI: chat.completions.create(stream=True) + 异步迭代
          - DeepSeek: 与 OpenAI 相同（因为是兼容协议）
        """
        ...

    @abstractmethod
    async def describe_image(self, image_url: str) -> str:
        """
        使用视觉（Vision）能力描述图片。

        【用途】
          在游戏生成流程中，用户可能上传参考图片（角色设计、场景草图）。
          视觉 LLM 分析这些图片并将其转为文本描述，注入到 system prompt 中，
          这样即使模型本身不支持图片输入，也能根据描述生成匹配风格的
          程序化美术（procedural art）。

        【实现差异】
          - Claude:   支持 base64 编码的原生图片输入（image source block）
          - OpenAI:   使用 image_url 类型的内容块（直接传 URL）
          - DeepSeek: 纯文本模型，返回占位描述（优雅降级）

        【DeepSeek 的 fallback 策略】
          DeepSeek-chat 不支持图片输入，但 deepseek_adapter.py 返回一个
          通用描述字符串，确保流水线不会因为多模态能力缺失而崩溃。
          游戏代码中使用用户文本描述中的信息来生成程序化图形。
        """
        ...
