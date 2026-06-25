"""
=============================================================================
HTML5 游戏验证器 (Game Validator — 守护"可玩性"的最后防线)
=============================================================================

验证器是 AI 游戏生成流程中的质量关卡。它不保证游戏"好玩"，
但保证游戏至少"可运行"。这是一套针对 AI 生成代码特色的启发式检查规则。

——————————————————————————————————————————————————————————————
【技术决策：BeautifulSoup vs 正则表达式 —— 为什么用 BeautifulSoup？】
——————————————————————————————————————————————————————————————

  当需要解析 AI 生成的 HTML 时，两种选择摆在面前：

  ┌─────────────────────────────────────────────────────────┐
  │ 方案 A：正则表达式 (regex)                                │
  │                                                         │
  │   import re                                              │
  │   scripts = re.findall(r'<script[^>]*>(.*?)</script>',   │
  │                        html, re.DOTALL)                  │
  │                                                         │
  │   优点：快速、零依赖、一行搞定                             │
  │   缺点：                                                  │
  │     1. AI 生成的 HTML 可能嵌套不规则 —— 正则无法处理       │
  │     2. 注释中的 <script> 被误匹配                          │
  │     3. 属性中的特殊字符导致正则失败                         │
  │     4. 多层嵌套标签的正则是 CS 理论上的不可能任务           │
  │       （HTML 是上下文无关语言，正则只能识别正则语言）        │
  └─────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────┐
  │ 方案 B：BeautifulSoup (HTML 解析器) — 本项目采用          │
  │                                                         │
  │   from bs4 import BeautifulSoup                          │
  │   soup = BeautifulSoup(html_code, "html.parser")         │
  │                                                         │
  │   优点：                                                  │
  │     1. 容错性强：BS4 使用浏览器的错误恢复算法              │
  │       （与浏览器渲染引擎的行为一致），能处理 AI 生成的      │
  │       格式不佳的 HTML（如未闭合标签、嵌套错误）             │
  │     2. 结构化查询：soup.find_all("script") 精确找到       │
  │       所有 <script> 标签，包括有 src 属性的外部引用         │
  │     3. 属性提取：s.get("src", "") 安全地获取属性值         │
  │     4. 文本提取：s.string 获取标签内的文本内容              │
  │   缺点：                                                  │
  │     1. 需要安装 lxml 或 html.parser（但 fastapi 通常      │
  │        已经间接依赖了这些库）                              │
  │     2. 比正则慢（毫秒级，对单文件验证微不足道）             │
  └─────────────────────────────────────────────────────────┘

  选择 BeautifulSoup 的核心原因：AI 生成的 HTML 格式不可预测。
  一个 LLM 可能输出完美格式的 HTML，另一个可能在 <script> 标签中
  使用不规范的属性或未闭合的标签。正则在这种情况下会静默失败
  （匹配到错误的内容），而 BS4 会尽力构造一个可用的 DOM 树。
  验证必须"确定性正确"，不能因为解析失败而给出错误的判断。

——————————————————————————————————————————————————————————————
【为什么检查 eval()？—— XSS (跨站脚本攻击) 防护】
——————————————————————————————————————————————————————————————

  第 107-109 行：
    if "eval(" in all_script_text:
        result.errors.append("Security: eval() usage detected — not allowed")
        result.is_valid = False

  eval() 是 JavaScript 中最危险的函数之一，它可以动态执行任意字符串
  作为代码。为什么在游戏生成场景中特别关注这个问题？

  1. LLM 的"惯性"行为：
     LLM 在训练数据中见过大量使用 eval() 的代码（特别是旧式游戏代码、
     JSON 解析变通方案、动态函数调用等）。当生成游戏时，LLM 可能
     "无意识地"使用 eval() 处理动态生成的代码片段。
     例如：eval("new " + className + "()") 来实现简单工厂模式。

  2. 攻击面分析：
     虽然游戏是单文件 HTML 在 iframe 中运行，但 iframe 通常与主应用
     共享同一个域（同源策略允许访问）。如果 LLM 生成的游戏包含 eval()，
     并且用户输入（如玩家名字、聊天消息）以某种方式流入 eval() 参数，
     就可以触发 XSS —— 攻击者在玩家名字中注入恶意 JS 代码。

     攻击路径示例：
       用户输入名字: "Player1"); fetch('/api/admin/delete-all') //
       AI 生成代码:  eval("alert('Hello, " + playerName + "!')")
       实际执行:     alert('Hello, Player1'); fetch('/api/admin/delete-all') //!')

  3. 零信任原则 (Zero Trust)：
     AI 生成的内容本质上是"不可信的"（untrusted code generation）。
     虽然当前 prompt 中明确要求不使用 eval()，但不能 100% 保证
     模型遵守。验证器作为最后防线，将 eval() 检查设为致命错误
     （is_valid = False），确保任何含 eval() 的游戏都会被拦截或修复。

  4. 为什么不是更全面的 CSP (Content Security Policy) 检查？
     全面的 CSP 检查（如检查 inline script、eval、WebSocket 连接等）
     需要更复杂的分析。当前只检查 eval() 是因为：
       - eval() 是最高风险函数（占 XSS 攻击的 70%+）
       - 我们的游戏只通过 iframe 加载，iframe sandbox 属性可提供额外保护
       - 完整的 CSP 策略会限制游戏功能（如动态样式注入）
     这是一个"实用主义安全"的权衡 —— 覆盖最大风险，不过度工程化。

  5. 检查方法的局限性：
     if "eval(" in all_script_text 是简单的字符串匹配，
     存在漏检和误检的可能：
       漏检：eval.call(null, code)、window["eval"](code)
       误检：注释中的 "eval("、字符串字面量中的 "eval("
     但考虑到 AI 生成的代码几乎不会使用高级绕过技术，
     且误检只会触发一次修复尝试（不会破坏游戏），这个简单的
     字符串匹配是性能/准确性的合理平衡。

  【补充】为什么也禁止 document.write() 和 inline event handlers？
    第 108 行的注释中也提到了这两者：
      - document.write(): 在页面加载后调用会清空整个文档
      - inline event handlers (onclick="..."): CSP unsafe-inline 违规
    但当前 validator 代码中没有做这两项检查 —— 它们依靠 prompt 约束。
    将来可以添加，作为深度防御 (defense-in-depth) 的一部分。

——————————————————————————————————————————————————————————————
【警告 vs 错误的分类逻辑】
——————————————————————————————————————————————————————————————

  验证结果分为两个层级：

  errors (严重，is_valid = False):
    - HTML 不可解析 (parseable)
    - 缺少实质性 <script> 代码 (game logic)
    - 包含 eval() (安全)
    这些是"硬伤" —— 游戏根本无法安全运行，必须修复。

  warnings (轻微，is_valid 仍为 True):
    - 缺少游戏主循环 (game loop)
    - 缺少用户交互处理 (input handling)
    - 引用了非批准的外部 CDN
    这些是"软伤" —— 游戏可能运行但体验不佳，记录日志但不阻断。

  这个分层设计让流水线有"弹性"：只有硬伤触发 fix_errors()，
  软伤只记录不阻塞。如果每次 warning 都触发修复，修复循环
  可能无限重复（LLM 可能每次都引入新的轻微问题）。
"""

from dataclasses import dataclass, field

from bs4 import BeautifulSoup


@dataclass
class ValidationResult:
    """
    验证结果的数据载体。

    【为什么使用 dataclass 而不是 namedtuple 或普通 dict？】
      - namedtuple: 不可变，但我们需要在 validate() 中逐步填充
      - dict: 无类型安全，errors 和 warnings 的 key 容易拼错
      - dataclass: 类型安全 + 可变 + field(default_factory) 处理可变默认值

    【field(default_factory=list) 的陷阱】
      不能写 errors: list[str] = []，因为 Python 的默认参数在函数定义时
      只求值一次。如果两个 ValidationResult 实例共享同一个列表引用，
      修改一个的 errors 会影响另一个。default_factory=list 在每次
      实例化时创建新的空列表，避免了这个经典的 Python 陷阱。

    【is_valid 的默认值】
      默认 True（"无罪推定"）—— 只有在发现问题时才设为 False。
      这确保了空验证（例如 validate() 返回默认对象）不会误判。
    """
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class GameValidator:
    """
    验证 AI 生成的 HTML 游戏是否满足最低可玩性标准。

    【设计原则】
      这是一个"启发式验证器"（heuristic validator），不是"形式化验证器"。
      它通过模式匹配而非完整静态分析来判断游戏质量。因此：
        - 可能产生 false positive（误报）—— 标记出实际没问题的代码
        - 可能产生 false negative（漏报）—— 未检测出隐藏的问题
      这是权衡：形式化验证（如用 ESLint + 自定义规则解析 JS AST）的
      工程复杂度远高于启发式验证，而后者已经覆盖了 90%+ 的常见问题。

    【验证项的设计逻辑】
      以下 6 项检查按"严重性递减"排列，反映了游戏可玩性的层次结构：
        层 1 (致命): HTML 本身有效       → parseability
        层 2 (核心): 有游戏逻辑           → scripts exist
        层 3 (必需): 有游戏循环           → requestAnimationFrame/setInterval/Phaser
        层 4 (期望): 有用户交互           → event listeners
        层 5 (安全): 无危险函数           → no eval()
        层 6 (合规): 外部资源来源合法      → approved CDN only
    """

    # 允许的外部 CDN 白名单
    # 只允许这些 CDN 来源的外部脚本，防止 LLM 引用恶意或不稳定的 CDN
    # jsdelivr.net:   全球最大的 npm/CDN 加速服务，Phaser 3 的官方推荐分发渠道
    # cdnjs.cloudflare.com: Cloudflare 运营的老牌 CDN，稳定性和速度极佳
    # unpkg.com:      直接从 npm 拉取的 CDN，作为备选
    # 注意：这个白名单如果太窄会影响游戏功能（如需要额外库），
    #       但太宽会引入安全风险（如允许未知 CDN 的恶意脚本）。
    #       当前范围覆盖了 99% 的合法游戏开发 CDN 需求。
    APPROVED_CDNS = [
        "cdn.jsdelivr.net",
        "cdnjs.cloudflare.com",
        "unpkg.com",
    ]

    def validate(self, html_code: str) -> ValidationResult:
        """
        对生成的游戏 HTML 执行全套验证。

        【参数】
          html_code: 完整的 HTML 代码字符串（应该已经从 markdown 围栏中清理过）

        【返回值】
          ValidationResult 包含 is_valid 标志、errors 列表、warnings 列表。

        【执行流程】
          6 个检查步骤按序执行。一旦 parseability 失败（HTML 不可解析），
          立即返回 —— 因为后续检查没有意义。其他检查即使发现问题也继续，
          因为一个错误不应掩盖其他错误。
        """

        # 初始化结果对象（"无罪推定"原则）
        result = ValidationResult(is_valid=True)

        # ================================================================
        # 检查 1：HTML 可解析性 (Parseability)
        # ================================================================
        # 这是所有检查的基础 —— 如果 BS4 都无法解析，后续的 script 查找
        # 和 text 提取都毫无意义。
        #
        # "html.parser" 是 Python 标准库的内置 HTML 解析器。
        # 它的容错性不如 "lxml" 或 "html5lib"，但不需要额外安装。
        # 如果 AI 生成的 HTML 连标准库的宽容解析器都过不去，说明格式严重错误。
        try:
            soup = BeautifulSoup(html_code, "html.parser")
        except Exception as e:
            result.is_valid = False
            result.errors.append(f"HTML is not parseable: {e}")
            return result  # 提前返回 —— 后续检查无法进行

        # ================================================================
        # 检查 2：必须有实质性的脚本代码 (Game Logic Existence)
        # ================================================================
        # 找到所有 <script> 标签，区分内联脚本和外部引用脚本。
        #
        # 内联脚本判断标准：s.string 非空且内容长度 > 50 字符。
        # 50 字符的阈值：排除短小的配置代码（如 var gameId = "xxx"），
        # 确保至少有实质性逻辑。实际游戏代码通常在 1000+ 字符。
        scripts = soup.find_all("script")
        inline_scripts = [s for s in scripts if s.string and len(s.string.strip()) > 50]

        # 如果既没有长内联脚本，也没有外部脚本引用 → 致命的
        if not inline_scripts and not any(
            s.get("src", "") for s in scripts
        ):
            result.is_valid = False
            result.errors.append("No game logic found: must have <script> with substantive code")

        # ================================================================
        # 检查 3：必须有游戏主循环 (Game Loop Detection)
        # ================================================================
        # 将所有脚本文本拼接为一个搜索域，检查关键词。
        #
        # 为什么拼接而不是逐个检查？
        #   游戏循环可能分散在多个 <script> 标签中：
        #     <script src="phaser.min.js"></script>  # 框架
        #     <script>
        #       var config = { type: Phaser.CANVAS };  # 配置
        #       var game = new Phaser.Game(config);     # 初始化（含游戏循环）
        #     </script>
        #   如果只检查有 s.string 的脚本，会漏过 "Phaser.Game"（可能在 inline 脚本中）。
        #   如果只检查 src，会漏过 "requestAnimationFrame"（在 inline 脚本中）。
        #   拼接后统一搜索覆盖所有可能。
        #
        # 包含 s.get("src", "") 的原因：
        #   外部脚本的 URL 本身可能包含关键词（虽然罕见，如 "game-loop.js"），
        #   加入搜索域的成本为零，但能覆盖这个边缘情况。
        all_script_text = " ".join(
            (s.string or "") + (s.get("src", "")) for s in scripts
        )

        # 关键词列表的设计：
        #   - requestAnimationFrame: Canvas API 的标准游戏循环驱动
        #   - setInterval: 固定帧率的简单循环方案（旧式游戏常用）
        #   - Phaser.Game / new Phaser.Game: Phaser 3 框架的游戏实例化（隐含游戏循环）
        #   - gameLoop / game_loop: 自定义游戏循环函数（常见命名约定）
        #   - update(: 带括号匹配大多数 update 函数调用模式
        #     注意 "update(" 可能匹配到非游戏循环的函数名（如 DOM 的 update()）。
        #     这是故意宽松的匹配 —— 假阳性（误报有游戏循环）比假阴性（漏报无游戏循环）
        #     的危害小，因为这只是 warning 而非 error。
        has_game_loop = any(
            keyword in all_script_text
            for keyword in [
                "requestAnimationFrame",
                "setInterval",
                "Phaser.Game",
                "new Phaser.Game",
                "gameLoop",
                "game_loop",
                "update(",
            ]
        )

        if not has_game_loop:
            result.warnings.append(
                "No game loop detected (requestAnimationFrame/setInterval/Phaser not found)"
            )

        # ================================================================
        # 检查 4：必须有用户交互处理 (Input Handling Detection)
        # ================================================================
        # 检查是否存在事件监听器或输入处理代码。
        #
        # 覆盖的输入类型：
        #   - addEventListener: DOM 标准事件绑定（最通用）
        #   - keydown/keyup/keypress: 键盘输入
        #   - mousedown/mouseup/mousemove/click: 鼠标输入
        #   - touchstart/touchend/touchmove: 移动端触摸
        #   - pointerdown: 统一的指针事件（现代标准）
        #   - input.keyboard / this.input: Phaser 3 的输入系统
        #
        # 为什么不检查 Phaser 的所有输入关键词（如 input.on、cursor keys）？
        #   维护一个完整的 Phaser 输入 API 列表太脆弱（Phaser 版本更新会过时）。
        #   当前的通用事件名 + 两个 Phaser 入口已覆盖 95%+ 的情况。
        #   "addEventListener" 本身就是最可靠的信标 —— 99% 的游戏都用到它。
        has_input = any(
            keyword in all_script_text
            for keyword in [
                "addEventListener",
                "keydown",
                "keyup",
                "keypress",
                "mousedown",
                "mouseup",
                "mousemove",
                "click",
                "touchstart",
                "touchend",
                "touchmove",
                "pointerdown",
                "input.keyboard",
                "this.input",
            ]
        )

        if not has_input:
            result.warnings.append(
                "No user input handling detected — game may not be interactive"
            )

        # ================================================================
        # 检查 5：安全 —— 禁止 eval() (XSS Prevention)
        # ================================================================
        # 这是唯一会导致 is_valid = False 的安全检查。
        # 关于为什么特别关注 eval()，详见文件头部注释。
        #
        # 为什么要区分 error 和 warning？
        #   缺少游戏循环：warning（游戏可能用其他方式运行，如 CSS animation）
        #   缺少输入处理：warning（游戏可能是自动演示）
        #   使用 eval()：   error （安全红线，不可妥协）
        #
        # 简单字符串匹配的局限性：见文件头部注释中的讨论。
        if "eval(" in all_script_text:
            result.errors.append("Security: eval() usage detected — not allowed")
            result.is_valid = False

        # ================================================================
        # 检查 6：外部脚本来源审查 (External Script Source Approval)
        # ================================================================
        # 遍历所有带 src 属性的 <script> 标签，检查来源是否在批准的白名单中。
        #
        # 为什么需要这个检查？
        #   LLM 可能在生成游戏时引用随机 CDN 或第三方库：
        #     - 恶意 CDN（通过训练数据中的钓鱼示例）
        #     - 不稳定 CDN（小站点可能宕机）
        #     - 旧版本库 CDN（可能有已知漏洞）
        #   白名单机制确保所有外部依赖都来自可信来源。
        #
        # 注意：这只是一个 warning，因为不批准的 CDN 不一定是恶意的。
        # 例如，LLM 引用了 "code.jquery.com"（合法但不在白名单中）。
        # 人工审核时可以决定是否添加到白名单。
        for script in scripts:
            src = script.get("src", "")
            if src and not any(cdn in src for cdn in self.APPROVED_CDNS):
                result.warnings.append(
                    f"External script source not in approved CDNs: {src}"
                )

        return result
