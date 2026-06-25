"""
=============================================================================
LLM 适配器工厂 (Adapter Factory — create_adapter)
=============================================================================

【架构决策：工厂函数 vs 依赖注入容器 — 为什么选择工厂函数？】

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
方案 A：工厂函数 (Factory Function) — 本项目采用
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  def create_adapter() -> LLMAdapter:
      provider = settings.llm_provider.lower()
      if provider == "claude":
          return ClaudeAdapter(...)
      elif provider == "openai":
          return OpenAIAdapter(...)
      ...

  优点：
    1. 零依赖：不需要 FastAPI、dependency_injector、punq 等框架
    2. 调用简单：在任意地方（后台任务、CLI 脚本、测试）直接 import 调用
    3. 显式控制流：if/elif/else 分支一目了然，调试时可以 step-through
    4. 类型安全：返回 LLMAdapter 基类类型，所有子类自动兼容
    5. 无魔法：没有隐式注入、装饰器扫描、自动绑定等"黑盒"行为
    6. 测试友好：在测试中直接 monkeypatch settings 或传递 mock adapter
    7. 启动快：不需要容器初始化、组件扫描、依赖图构建等开销

  缺点：
    1. 需要手动维护 if/elif 分支（新增供应商时需要修改本函数）
    2. 没有自动生命周期管理（如 Singleton 作用域、资源清理）
    3. 配置和创建耦合在同一个函数中

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
方案 B：依赖注入容器 (DI Container) — 未采用
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  以 FastAPI 的 Depends() 或 punq 为例：

    def get_adapter(provider: str = Depends(get_provider_from_config)) -> LLMAdapter:
        container = Container()
        container.register(LLMAdapter, ClaudeAdapter, provider="claude")
        container.register(LLMAdapter, OpenAIAdapter, provider="openai")
        return container.resolve(LLMAdapter, provider=provider)

  优点：
    1. 自动注入：路由处理函数签名中声明参数类型，框架自动解析
    2. 生命周期管理：Singleton/Scoped/Transient 作用域
    3. 解耦注册和使用：配置在容器初始化时完成，使用时无需关心实例化细节

  缺点（也是本项目的拒绝理由）：
    1. 引入框架依赖 —— 本项目希望在非 Web 上下文也能创建适配器
    2. 隐式行为 —— "这个参数从哪里来？"需要理解框架的注入机制
    3. 过度工程化 —— 当前只有 3 个适配器实现，DI 容器的复杂度超过了
       它带来的收益。YAGNI 原则：You Aren't Gonna Need It。
    4. 学习成本 —— 新手需要理解 Python DI 的概念后才能修改代码

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
方案 C：注册表模式 (Registry Pattern) — 中间方案
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  _adapters = {}
  def register(name, factory):
      _adapters[name] = factory
  def create(provider):
      return _adapters[provider]()

  这比 if/elif 更灵活（可以在外部注册新供应商），但当前项目中
  只有 3 个已知供应商，注册表模式增加了间接性而没有实际收益。
  如果未来适配器数量增长到 10+，可以考虑迁移到此模式。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
结论：工厂函数是当前规模和需求下的最优解
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  一个 30 行的工厂函数足以覆盖所有需求，不需要任何外部依赖。
  这与 Python 社区 "简单的解决方案优于聪明的解决方案" 的价值观一致。

【settings 对象的来源】
  from app.config import settings
  这是 Pydantic Settings (pydantic-settings) 管理的配置对象。
  它会自动从 .env 文件和环境变量加载配置，提供类型安全的属性访问。
  例如 settings.llm_provider 返回 str 类型，IDEName 能提供自动补全。

【provider 的 .lower() 处理】
  第 17 行：provider = settings.llm_provider.lower()
  这允许用户以任意大小写输入供应商名称：
    "CLAUDE"  -> "claude"
    "OpenAI"  -> "openai"
    "DeepSeek"-> "deepseek"
  这是防御性设计 —— 环境变量和 .env 文件中的大小写不可控。

【"none" 供应商的特殊处理】
  第 35-38 行：当 LLM_PROVIDER 为 "none" 时不创建任何适配器，
  而是抛出 ValueError 并附带清晰的操作指引。
  这不是错误状态，而是"有意未配置"的声明 —— 可能在开发环境中
  不需要 AI 功能，或者在生产环境中使用自定义的非标准适配器。

【__all__ 的作用】
  第 45 行：__all__ = ["LLMAdapter", "ClaudeAdapter", "OpenAIAdapter", "DeepSeekAdapter", "create_adapter"]
  这控制了 from app.agent.adapters import * 的行为。
  虽然没有代码使用 import *，但这是一个文档性声明，
  告诉阅读者"这些是本模块的公开 API"。
"""

from app.config import settings
from app.agent.adapters.base import LLMAdapter
from app.agent.adapters.claude_adapter import ClaudeAdapter
from app.agent.adapters.openai_adapter import OpenAIAdapter
from app.agent.adapters.deepseek_adapter import DeepSeekAdapter


def create_adapter() -> LLMAdapter:
    """
    工厂函数：根据配置创建对应的 LLM 适配器实例。

    【调用时机】
      每次生成任务开始时调用一次。不在应用启动时创建全局实例，
      因为不同的并发任务可能使用不同的配置（虽然不常见）。
      如果未来需要实例复用，可以在这里添加 LRU 缓存。

    【返回类型 LLMAdapter 的设计】
      返回基类类型意味着调用方不需要知道具体是哪个供应商。
      harness.py 中只需要 adapter.generate(system, user) 即可工作。
      这是依赖倒置原则 (DIP: Dependency Inversion Principle) 的体现：
      高层模块（harness）依赖抽象（LLMAdapter），不依赖具体实现。

    【配置文件中的默认值处理】
      每个适配器的 model 参数使用 "or" 回退到默认值：
        settings.llm_model or "claude-sonnet-4-20250514"
      这意味着：
        - 如果用户在 .env 中设置了 LLM_MODEL，使用用户的设置
        - 如果用户没有设置（None 或空字符串），使用硬编码的默认值
      这是一个合理的"约定优于配置"策略。

    【支持的供应商】
      - claude:    Anthropic Claude 系列模型
      - openai:    OpenAI GPT 系列及所有 OpenAI 兼容 API
      - deepseek:  DeepSeek 模型（通过继承 OpenAI 适配器）
      - none:      禁用 AI 生成（开发/测试环境用）

    【扩展方式】
      要添加新供应商：
        1. 创建 myprovider_adapter.py，继承 LLMAdapter
        2. 在本函数中添加 elif provider == "myprovider" 分支
        3. 返回值类型保持 LLMAdapter（多态）

    Raises:
        ValueError: 当 LLM_PROVIDER 为 "none" 或不支持的供应商时抛出
    """
    provider = settings.llm_provider.lower()

    if provider == "claude":
        # Claude 适配器默认使用 "claude-sonnet-4-20250514"（固定快照版本）
        return ClaudeAdapter(
            api_key=settings.llm_api_key,
            model=settings.llm_model or "claude-sonnet-4-20250514",
        )
    elif provider == "openai":
        # OpenAI 适配器支持自定义 base_url，对接所有 OpenAI 兼容 API
        # settings.llm_api_base_url 可能为 None（使用 OpenAI 官方端点）
        return OpenAIAdapter(
            api_key=settings.llm_api_key,
            model=settings.llm_model or "gpt-4o",
            base_url=settings.llm_api_base_url or None,
        )
    elif provider == "deepseek":
        # DeepSeek 适配器继承 OpenAIAdapter，base_url 自动指向 api.deepseek.com
        # 默认模型 deepseek-chat（性价比最高的通用模型）
        return DeepSeekAdapter(
            api_key=settings.llm_api_key,
            model=settings.llm_model or "deepseek-chat",
        )
    elif provider == "none":
        # "none" 表示用户有意禁用 AI 功能，抛异常并附带配置引导
        raise ValueError(
            "LLM_PROVIDER is set to 'none'. Set LLM_PROVIDER and LLM_API_KEY in .env to enable AI generation."
        )
    else:
        # 未知供应商 —— 明确列出支持的选项，帮助用户快速修正配置
        raise ValueError(
            f"Unsupported LLM_PROVIDER: {provider}. Use 'claude', 'openai', or 'deepseek'."
        )


# 模块的公开 API 声明
# 这告诉 IDE 和 linter：这些是本模块的公开接口，其他的是内部实现
__all__ = ["LLMAdapter", "ClaudeAdapter", "OpenAIAdapter", "DeepSeekAdapter", "create_adapter"]
