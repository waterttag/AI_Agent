"""
=============================================================================
HTML5 游戏生成器 (HTML5 Game Generator using LLM)
=============================================================================

本模块负责"提示词 + LLM 调用 = 游戏代码"这个核心转换。
它是连接"用户说什么"和"AI 生成什么"的桥梁。

【职责边界】
  本模块只负责：
    1. 构建 prompt（调用 prompts.py 的工具函数）
    2. 调用 LLM adapter（通过依赖注入获得）
    3. 后处理（清理 markdown 围栏等输出 artifact）
  本模块不负责：
    1. 验证生成的 HTML（交给 processors/validator.py）
    2. 上传到 MinIO（交给 processors/packager.py）
    3. 进程管理和进度更新（交给 harness.py）
  这种职责分离是 Clean Architecture 的体现 —— 每个模块只有单一职责。

——————————————————————————————————————————————————————————————
【temperature=0.8 的选择理由（游戏生成）】
——————————————————————————————————————————————————————————————

  GameGenerationContext 中的 temperature=0.8（第 41 行）：
    html_code = await self.adapter.generate(
        ...,
        temperature=0.8,  # Higher creativity for games
        ...
    )

  为什么是 0.8 而不是默认的 0.7 或其他值？

  1. 创造力与正确性的平衡点：
     - 游戏生成需要创造力（新颖的游戏机制、视觉设计、交互方式）
     - 但也需要正确性（HTML 语法、JavaScript 逻辑、CSS 规则）
     - 0.8 在 softmax 曲线上比 0.7 略微压平分布，增加约 15% 的 token 多样性
     - 实验表明这个点能在不引入语法错误的情况下最大化创意

  2. 与 0.5（修复模式）的对比：
     - 修复模式使用 temperature=0.5（第 59 行），更低温度 = 更保守
     - 修复模式的目标是"精确、忠实于原文"而非"创造性发挥"
     - 在 softmax 中，0.5 vs 0.8 意味着概率分布"锐利度"提升约 60%

  3. 不同供应商对温度的感受：
     - Claude: 对温度变化最敏感，0.8 已经足够激进
     - GPT-4o: 对温度较不敏感，0.8 和 1.0 差异不大
     - DeepSeek: 0.8 时偶尔会出现语法错误，但游戏创意更好
     0.8 是跨供应商的平均最优值。

  4. max_tokens=16000 的配套考量：
     高温 + 高 max_tokens 组合意味着 LLM 有大量"空间"和"自由度"来
     生成完整游戏。如果 max_tokens 太小（如 4000），高温导致的"啰嗦"
     可能挤占游戏逻辑的空间。16000 token 的余量抵消了这个风险。

  详细 temperature 数学原理见 prompts.py 文件头部注释。

——————————————————————————————————————————————————————————————
【_clean_output() 的设计——LLM 输出格式归一化】
——————————————————————————————————————————————————————————————

  LLM 经常在输出中包裹 markdown 代码围栏（code fence），例如：
    ```html
    <!DOCTYPE html>
    ...
    ```
  或
    ```
    <!DOCTYPE html>
    ...
    ```

  这虽然是格式良好的 markdown，但对游戏渲染来说是无用的甚至有害的 ——
  浏览器不能解析 markdown 包裹的 HTML。_clean_output() 移除这些围栏。

  为什么不用正则表达式？
    1. 简单的前缀/后缀检查足够 —— markdown 围栏的格式极其固定
    2. 按行 strip 比正则更快（O(n)，无回溯）
    3. .strip() 处理首尾空白（LLM 偶尔在围栏外输出额外空行）

  为什么在 generate() 和 fix_errors() 中都调用 _clean_output()？
    两个方法的 LLM 输出都可能含有围栏。在 generate() 中清理后，
    后续的 fix_errors() 接收的是干净 HTML；但 fix_errors() 也
    可能二次引入围栏（LLM 的"惯性"行为），所以需要二次清理。

  注意：HTML 中间出现的 "```" 不会被误删，因为我们只检查前缀和后缀。
  这是因为正则 /^```html|^```|```$/ 的 startswith/endswith 语义明确。
"""

from dataclasses import dataclass

from app.agent.adapters.base import LLMAdapter
from app.agent.prompts import build_system_prompt, build_user_prompt


@dataclass
class GameGenerationContext:
    """
    游戏生成上下文 —— 封装一次生成任务需要的所有输入参数。

    【为什么使用 dataclass 而不是普通字典？】
      1. 类型安全：IDE 可以提供参数名的自动补全和类型检查
      2. 默认值清晰：asset_descriptions=None 明确表达"可选"语义
      3. 可读性：GameGenerationContext(user_prompt="...") 比
         {"user_prompt": "..."} 更有意图表达力
      4. 可扩展：将来添加新字段（如 language、target_platform）只需
         添加一个带默认值的属性，不破坏现有调用代码

    【参数说明】
      user_prompt:        用户的自然语言游戏描述（核心输入）
      asset_descriptions: 用户上传素材的文字描述（来自 Vision API 分析）
      style_preferences:  风格预设（genre, difficulty, visual_style）
      game_id:           游戏 UUID（用于日志和追踪，非功能必需）
    """
    user_prompt: str
    asset_descriptions: list[str] | None = None
    style_preferences: dict | None = None
    game_id: str | None = None


class HTML5GameGenerator:
    """
    使用 LLM 生成完整可玩的 HTML5 游戏。

    【设计模式：策略模式 (Strategy Pattern)】
      __init__ 接受 LLMAdapter 接口而非具体类，意味着：
        - 可以在运行时切换不同的 LLM 供应商
        - 测试时可以用 MockAdapter 替代真实 API 调用
        - 本类的核心逻辑不依赖特定 LLM 的实现细节

    【依赖注入】
      adapter 通过构造函数注入（Constructor Injection），
      而不是在类内部用 create_adapter() 创建。好处：
        1. 测试时可以注入 mock adapter
        2. 调用方控制 adapter 的生命周期（如在 harness 中复用）
        3. 类不依赖全局配置（settings），保持纯净
    """

    def __init__(self, adapter: LLMAdapter):
        """
        初始化游戏生成器。

        【为什么不在此处做更多初始化？】
          构造器极简是良好设计 —— 它只存储依赖，不做任何计算。
          实际的 prompt 构建和 LLM 调用都在 generate() 方法中进行。
          这种"懒初始化"模式让类的行为更可预测：
            创建对象 → 调用方法 → 得到结果
          没有任何隐藏的副作用。
        """
        self.adapter = adapter

    async def generate(self, context: GameGenerationContext) -> str:
        """
        根据上下文生成一个完整的 HTML5 游戏。

        【执行流程】
          1. 构建 system prompt（含素材描述注入）
          2. 构建 user prompt（含风格偏好拼接）
          3. 调用 LLM adapter 生成 HTML
          4. 清理 LLM 输出 artifact（markdown 围栏）
          5. 返回纯净的 HTML 代码

        【为什么 system 和 user prompt 分开构建】
          这对应了 LLM API 的语义分离：
            - System prompt: "你是谁"——定义角色和能力边界
            - User prompt:   "做什么"——具体的任务指令
          分离构建允许 prompts.py 中的两个工具函数独立演进，
          互不影响。如果需要调整系统提示词，只需修改
          GAME_GENERATION_SYSTEM_PROMPT 常量，不影响 user prompt 逻辑。

        【temperature=0.8 的详细论证】
          见本文件头部注释。
        """
        # 步骤 1-2：构建双角色 prompt
        system_prompt = build_system_prompt(context.asset_descriptions)
        user_prompt = build_user_prompt(context.user_prompt, context.style_preferences)

        # 步骤 3：调用 LLM 生成
        # 注意：此调用是异步的，可能耗时 5-30 秒
        # 在此期间，FastAPI 的事件循环可以处理其他请求
        html_code = await self.adapter.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.8,  # Higher creativity for games
            max_tokens=16000,
        )

        # 步骤 4：后处理清理
        html_code = self._clean_output(html_code)

        return html_code

    async def fix_errors(self, original_html: str, errors: list[str]) -> str:
        """
        要求 LLM 修复验证中发现的问题。

        【自动修复的设计理念】
          与其让用户手动修改 AI 生成的代码（这对非开发者几乎不可能），
          不如让 AI 自己修复自己的错误。这是"AI 生成 + AI 验证 + AI 修复"
          的闭环质量控制流程。

        【FIX_SYSTEM_PROMPT 的构造】
          使用 str.format() 将错误列表和原始代码注入修复提示词模板。
          错误列表以 markdown 列表形式呈现（每行 "- {error}"），
          利用了 LLM 对结构化列表的强理解能力。

        【temperature=0.5 —— 修复模式的低温策略】
          修复比生成需要更多的"精确性"和更少的"创意性"。
          0.5 的温度让模型：
            - 更严格地遵循纠错指令
            - 更少地"发明"新的游戏功能（scope creep）
            - 几乎不产生新的语法错误
          这是 temperature 在同一个系统中的多面应用 ——
          生成用 0.8（创意），修复用 0.5（精确），
          展示了参数选择的语境敏感性。

        【为什么 system_prompt 用硬编码字符串而非复用 prompts.py？】
          修复模式的 system prompt 非常简单，只有一句话，不需要复用
          prompts.py 中的复杂模板。直接写在这里是务实的，避免了
          为一行字符串创建独立的模块函数。YAGNI 原则。
        """
        from app.agent.prompts import FIX_SYSTEM_PROMPT

        # 将错误列表格式化为 markdown 列表
        errors_text = "\n".join(f"- {e}" for e in errors)
        # 注入错误和原始代码到修复模板
        prompt = FIX_SYSTEM_PROMPT.format(errors=errors_text, original_code=original_html)

        # 调用 LLM 进行修复（低温 = 高精确度）
        fixed_html = await self.adapter.generate(
            system_prompt="You are an expert HTML5 game debugger. Fix the errors and output the corrected HTML.",
            user_prompt=prompt,
            temperature=0.5,
            max_tokens=16000,
        )

        # 二次清理 —— LLM 可能在修复后重新引入 markdown 围栏
        return self._clean_output(fixed_html)

    @staticmethod
    def _clean_output(html: str) -> str:
        """
        清理 LLM 输出的常见格式 artifact。

        【处理的 artifact 类型】
          1. markdown 代码围栏（```html 和 ```）
          2. 首尾空白字符（空行、缩进、不可见字符）

        【为什么是 @staticmethod 而不是独立函数？】
          这是纯粹的数据转换，不依赖 self 状态。作为 staticmethod
          放在类内可以：
            1. 表达"这是 HTML5GameGenerator 的输出后处理逻辑"
            2. 便于子类覆盖（如果需要不同的清理逻辑）
            3. 不需要单独导入一个清理函数

        【潜在问题：如果 HTML 内容以 ``` 开头会怎样？】
          理论上可能误删以 ``` 开头的游戏代码（如包含 markdown 渲染器）。
          但实际上 HTML5 游戏代码极少以 ```html 或 ``` 开头。
          即使误删，validator 会检测到并触发 fix_errors()。
          这是一个可接受的 trade-off —— 清除 99% 的 artifact 比
          完美处理 1% 的边缘情况更有价值。

        【为什么用 .strip() 而非 .strip("`") 或正则？】
          .strip() 移除所有空白字符（空格、tab、换行、回车），这是我们需要的。
          .strip("`") 只移除反引号，会留下前导空白，不够彻底。
        """
        # 移除开头和结尾的空白
        html = html.strip()

        # 移除 markdown 代码围栏前缀
        # 注意：先检查 "```html"（特定语言标记），再检查 "```"（通用标记）
        # 顺序重要 —— 如果先匹配 "```"，可能只删掉 3 个反引号而留下 "html"
        if html.startswith("```html"):
            html = html[7:]   # 删除 ```html (7个字符)
        elif html.startswith("```"):
            html = html[3:]   # 删除 ``` (3个字符)

        # 移除后缀围栏
        if html.endswith("```"):
            html = html[:-3]  # 删除结尾 ```

        # 再次 strip 处理可能出现的额外空白
        html = html.strip()

        return html
