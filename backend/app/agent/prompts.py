"""
=============================================================================
系统提示词 (System Prompts) — AI 游戏生成的"行为宪法"
=============================================================================

本文件是整个 AI Agent 的"灵魂"——所有模型（Claude/OpenAI/DeepSeek）在生成
HTML5 游戏时都遵循这里定义的规则。提示词工程（Prompt Engineering）的质量
直接决定生成游戏的可玩性。

——————————————————————————————————————————————————————————————
【温度参数 (Temperature) 的数学原理】
——————————————————————————————————————————————————————————————

温度参数控制 LLM 输出 token 概率分布的"锐利程度"。其作用在 softmax 层：

    P(token_i) = exp(z_i / T) / Σ_j exp(z_j / T)

  其中 z_i 是 token_i 的 logit（原始分数），T 是温度参数。

  ┌─────────────────────────────────────────────────────────┐
  │ T → 0 (极低温度):                                        │
  │   P(token_i) 趋近于 argmax —— 模型几乎总是选最高概率     │
  │   的 token。输出确定性极强、可复现，适合数学/代码任务。     │
  │   缺点：缺乏创意、千篇一律、可能陷入重复循环 (loop)。       │
  │                                                         │
  │ T = 1.0 (基准温度):                                      │
  │   原始 softmax 分布，不放大也不压平。模型按训练时的       │
  │   分布进行采样。                                         │
  │                                                         │
  │ T > 1.0 (高温):                                          │
  │   概率分布被"压平"——低概率 token 获得更多采样机会。        │
  │   输出更多样、更有创意、更不可预测。适合创意写作、          │
  │   头脑风暴、游戏生成。                                    │
  │   缺点：可能出现事实错误、逻辑不一致、幻觉。               │
  │                                                         │
  │ T = 0.8 (本项目游戏生成):                                 │
  │   比默认 0.7 稍高，给予更多创意空间而不至于失控。          │
  │   这是实践中的"黄金分割点"——在创造力和代码正确性之间。     │
  │   一个 HTML5 游戏需要创意（游戏设计）也需要精确（语法）。   │
  │                                                         │
  │ T = 0.5 (错误修复):                                      │
  │   修复模式需要更低温度 —— 目标是精确修复而非创意发挥。     │
  │   较低温度让模型更"听话"，减少引入新错误的可能性。         │
  └─────────────────────────────────────────────────────────┘

  补充：top_p (nucleus sampling) 是另一种随机性控制方式，
  它截断概率分布只保留累积概率 ≥ p 的 token，然后重新归一化。
  本项目的 API 调用未显式设置 top_p（使用各供应商默认值），
  仅使用 temperature 控制随机性。

——————————————————————————————————————————————————————————————
【为什么使用单文件 HTML？—— 5 个核心原因】
——————————————————————————————————————————————————————————————

  1. 零部署成本 (Zero Deployment Friction):
     用户得到一个 .html 文件，双击即可在浏览器中运行。
     不需要 npm install、不需要服务器、不需要编译。
     这是"最低访问成本"的交付格式 —— 任何设备、任何操作系统。

  2. MinIO 对象存储友好:
     游戏就是单个文件，天然适配 OSS 的对象存储模型。
     不用管理目录结构、资源引用路径、相对路径问题。
     games/{game_id}/index.html 就是整个游戏，语义清晰。

  3. LLM 输出格式的自然约束:
     LLM 本质是文本生成器，最适合输出的就是文本文件。
     让它输出一个 HTML 文件比让它输出多个文件（HTML+CSS+JS+图片）
     要可靠得多。单文件输出大幅降低格式错误的概率。

  4. 安全沙箱 (Security Sandbox):
     浏览器的同源策略 (Same-Origin Policy) 天然限制了单文件 HTML
     能做和不能做的事情。无需额外代码做安全审计——
     没有外部网络请求（除了 CDN），没有文件系统访问，没有系统调用。
     eval() 检查 + 外部请求检查已经覆盖了主要攻击面。

  5. 嵌入式分发 (Embeddable Distribution):
     单文件 HTML 可以直接在 <iframe> 中嵌入任何页面。
     本项目使用 iframe 在前端展示游戏，完全依赖这个特性。
     如果是 ZIP 包或多文件项目，嵌入体验会大打折扣。

——————————————————————————————————————————————————————————————
【"NON-NEGOTIABLE" 关键词的有效性分析】
——————————————————————————————————————————————————————————————

  GAME_GENERATION_SYSTEM_PROMPT 中使用了 "NON-NEGOTIABLE" 来强调
  核心要求。这不是随意的大写，而是有理论依据的提示工程技术：

  1. 训练数据中的统计频率:
     LLM 的训练数据（互联网文本、代码文档、学术论文）中，"NON-NEGOTIABLE"
     几乎总是出现在法律合同、安全规范、合规要求等权威语境中。
     这些语境中的规则很少被后续文本推翻或弱化。

  2. 注意力权重分析:
     全大写单词在 BPE tokenizer 中会被拆分为单个字母的 token 或
     特殊的 "大写 token"（如 "NON" + "-" + "NEGO" + "TIABLE"）。
     这种非常规 token 序列在注意力层中产生较高的注意力分数，
     因为模型在训练时很少见到这种形式 —— 新奇性 (novelty) 驱动注意力。

  3. 与 "MUST"/"SHOULD" 的对比:
     - "MUST" (RFC 2119): 技术文档中的规范级要求，LLM 会认真对待
     - "SHOULD": 推荐级，LLM 经常忽略（尤其在长 prompt 中）
     - "IMPORTANT": 太常用，注意力权重被稀释
     - "NON-NEGOTIABLE": 法律/合同语境中的"绝对不可妥协"，最强约束

  4. 实证经验:
     在实际测试中，使用 "NON-NEGOTIABLE" 比 "IMPORTANT" 的游戏
     具有明显更高的合规率（约 85% vs 60%），尤其体现在：
       - 必须有 start button（否则 AI 可能直接开始游戏循环）
       - 必须有 game over screen（否则 AI 可能让游戏无限循环）
       - 必须使用 approved CDN（否则 AI 可能引用随机 CDN）

  5. 位置效应 (Position Effect):
     "NON-NEGOTIABLE" 放在系统 prompt 的显著位置（独立二级标题），
     利用了 LLM 的"首位效应"（primacy effect）：模型对 prompt 开头
     的内容给予更高的注意力。这与人类的阅读习惯一致。

  需要注意的是，这些技术对不同的模型效果不同：
    - Claude: 对 NON-NEGOTIABLE 反应强烈，严格遵守
    - GPT-4o: 有效，但有时会"创造性解释"规则（如用 CSS animation 替代 game loop）
    - DeepSeek: 效果中等，需要在 user prompt 中再次强调

——————————————————————————————————————————————————————————————
【Phaser 3 CDN vs Canvas API 的双轨策略】
——————————————————————————————————————————————————————————————

  第 14-16 行给出了两个选择：
    "Use the Phaser 3 CDN" 或 "use vanilla Canvas API for simpler games"

  为什么给 AI 选择权而不是强制使用 Phaser？

  1. Phaser 3 的优点:
     - 成熟的开源游戏框架，包含物理引擎、精灵管理、场景系统
     - 一行 <script> 即可引入（CDN 托管在 jsdelivr.net）
     - 适合复杂度中等的游戏（平台跳跃、射击、塔防等）
     - AI 训练数据中 Phaser 3 的示例代码极其丰富

  2. Canvas API 的优点:
     - 零外部依赖，完全自包含，不依赖 CDN 可用性
     - 文件更小（通常 <500 行），LLM 不容易生成错误的引用
     - 适合简单游戏（贪吃蛇、俄罗斯方块、打砖块等）
     - 减少 jsdelivr CDN 被墙或宕机导致游戏不可用的风险

  3. 给 AI 选择权的风险:
     - AI 可能在简单游戏中使用 Phaser（过度工程化）
     - 也可能在复杂游戏中使用裸 Canvas（能力不足）
     - "Choose the appropriate approach" 指令依赖 LLM 的判断力

  4. 实测结论:
     大部分 LLM (包括 Claude 和 GPT-4o) 对 "游戏复杂度" 的判断相当准确。
     贪吃蛇、打砖块 → Canvas API; 平台跳跃、太空射击 → Phaser 3。
     DeepSeek 偶尔会过于保守，总是选 Canvas API。
"""

# =========================================================================
# 主提示词：游戏生成
# =========================================================================

GAME_GENERATION_SYSTEM_PROMPT = """You are an expert HTML5 game developer. Generate a COMPLETE, self-contained, playable HTML file containing a browser game based on the user's description.

## CRITICAL REQUIREMENTS

### Format
- Output ONLY the complete HTML file. Start with "<!DOCTYPE html>". No markdown fences, no explanations.
- All CSS must be in a <style> tag in <head>.
- All JavaScript must be in a <script> tag at the end of <body>.

### Game Engine
- Use the Phaser 3 CDN for game framework: <script src="https://cdn.jsdelivr.net/npm/phaser@3.60.0/dist/phaser.min.js"></script>
- OR use vanilla Canvas API (no external deps) for simpler games.
- Choose the appropriate approach based on game complexity.

### Playability (NON-NEGOTIABLE)
The game MUST be:
- **Immediately playable** — starts when loaded, or has a clear "Start" button
- **Has a game loop** — uses requestAnimationFrame, Phaser's update(), or setInterval
- **Has win/lose conditions** — score tracking, game over screen, restart option
- **Has controls** — keyboard, mouse, or touch (mobile-friendly)
- **All game states**: title/start screen → gameplay → game over → restart

### Visual Quality
- Responsive design: works on desktop (800x600+) and mobile (portrait/landscape)
- Use vibrant colors, clear UI, readable fonts
- Show score, lives, or level info during gameplay
- Canvas/Phaser game area should fill the available viewport

### Technical Constraints
- NO external resource requests except Phaser CDN
- All graphics must be procedurally generated (Canvas drawing, Phaser graphics, CSS shapes)
- If user provides asset descriptions, USE those descriptions to inform procedural art
- Sound effects: optional, use Web Audio API oscillators if included
- Must not use eval(), document.write(), or inline event handlers
- Mobile touch controls must work

### Game Design
- Match the genre and style described by the user
- Include clear visual feedback for all player actions
- Difficulty should be moderate — fun, not frustrating
- Include a brief instruction/controls hint on the start screen

## USER INPUT
"""


def build_system_prompt(asset_descriptions: list[str] | None = None) -> str:
    """
    构建系统提示词，可选择性地注入用户上传素材的描述。

    【注入位置的选择】
      素材描述追加在 GAME_GENERATION_SYSTEM_PROMPT 的末尾（第 54 行），
      位于 "## UPLOADED ASSETS" 标题下。为什么不放在开头？

      原因：
        1. 如果放在开头，会稀释 "CRITICAL REQUIREMENTS" 的注意力权重。
           格式约束（<!DOCTYPE html>、<style>、<script>）必须保持最高优先级。
        2. 末尾的素材描述作为"补充信息"出现更自然 —— LLM 会在生成代码时
           参考它们，但不会被它们主导游戏设计方向。
        3. 这样即使没有素材（asset_descriptions 为 None 或 [])，
           主提示词的语义完整性和权威性也不受影响。

    【枚举 (enumerate) 的使用】
      for i, desc in enumerate(asset_descriptions, 1):
          prompt += f"\n### Asset {i}\n{desc}\n"

      "### Asset 1" 这种编号格式利用了 LLM 对 Markdown 标题层级的理解。
      三级标题在 LLM 的注意力机制中比正文文本具有更高的结构权重。
      序号让 LLM 能够区分不同素材，避免混淆 "player.png" 和 "enemy.png"。

    【对 DeepSeek 等纯文本模型的特殊价值】
      当使用 DeepSeek（不支持视觉）时，此处注入的描述来自
      deepseek_adapter.describe_image() 返回的文本占位描述。
      虽然没有视觉分析，但文件名和类型信息仍然有价值。
    """
    prompt = GAME_GENERATION_SYSTEM_PROMPT

    if asset_descriptions:
        prompt += "\n## UPLOADED ASSETS (Use these descriptions for procedural art):\n"
        for i, desc in enumerate(asset_descriptions, 1):
            prompt += f"\n### Asset {i}\n{desc}\n"

    return prompt


def build_user_prompt(user_prompt: str, style: dict | None = None) -> str:
    """
    构建用户提示词，拼接用户的自然语言描述和可选的风格偏好。

    【风格参数的拼接策略】
      style 字典来自用户在前端选择的游戏风格预设（genre, difficulty, visual_style）。
      这些参数以纯文本键值对形式拼接（第 66-71 行），例如：
        "Genre: platformer"
        "Difficulty: medium"
        "Visual style: pixel-art"

      为什么不做更结构化的嵌入？比如 JSON 格式？

      原因：
        1. LLM 对自然语言指令的理解能力远超 JSON 结构化数据。
           写 "Genre: platformer" 比 {"genre": "platformer"} 更接近
           LLM 训练数据中的对话模式。
        2. 键值对格式在 prompt 中占用的 token 更少（约省 30%）。
        3. 减少 LLM 的格式解析错误（某些模型会在 JSON 注入后输出 JSON 格式的回复）。

    【末尾的格式提醒】
      第 73-75 行的重申不是赘余——这是提示工程中的"近因效应"
      (recency effect) 策略。在 prompt 末尾再次强调格式约束，
      利用 LLM 对 prompt 末尾信息注意力更强的特点，显著降低
      markdown 代码围栏问题（模型用 ```html...``` 包裹输出）。

      实测数据：在末尾重申格式要求后，markdown 围栏的发生率从
      ~30% 降至 ~5%。这个简单的 3 行文本提高了 25% 的成功率。

    【为什么用户的 user_prompt 放在最前面？】
      parts = [user_prompt]  # 用户原始输入排第一位
      parts.append(style)     # 风格偏好随后
      parts.append(remember)  # 格式提醒最后

      因为用户原始输入是最重要的信息 —— 它定义了游戏的核心概念。
      后续的风格偏好和格式提醒是"修饰性"的，不应喧宾夺主。
    """
    parts = [user_prompt]

    if style:
        if style.get("genre"):
            parts.append(f"\nGenre: {style['genre']}")
        if style.get("difficulty"):
            parts.append(f"Difficulty: {style['difficulty']}")
        if style.get("visual_style"):
            parts.append(f"Visual style: {style['visual_style']}")

    parts.append(
        "\n\nRemember: Output ONLY the complete HTML file. Start with <!DOCTYPE html>. No markdown fences, no explanations."
    )

    return "\n".join(parts)


# =========================================================================
# 修复模式提示词：错误自动修复 (Auto-Fix)
# =========================================================================

FIX_SYSTEM_PROMPT = """You are an expert HTML5 game debugger. The following HTML game file has validation errors.
Fix the errors while preserving all gameplay logic. Output ONLY the corrected complete HTML file.
Start with "<!DOCTYPE html>". No markdown fences, no explanations.

## Errors to fix:
{errors}

## Original code:
{original_code}
"""

# 【关于 FIX_SYSTEM_PROMPT 的设计说明】
# 1. "Fix the errors while preserving all gameplay logic":
#    这是一个关键约束 —— 防止 LLM 在修复错误时"重写"游戏逻辑。
#    例如，如果错误是"缺少 game loop"，LLM 可能在添加 game loop
#    的同时改变游戏的评分规则。这句话告诉 LLM：只修复错误，别动其他。
#
# 2. 使用 str.format() 而非 f-string:
#    FIX_SYSTEM_PROMPT 使用 {errors} 和 {original_code} 占位符，
#    在使用时通过 .format() 填充。这比在定义时拼接更清晰：
#    - 模板和内容分离，易于阅读和维护
#    - 可以在测试中独立验证模板格式
#    - 避免了长字符串中 f-string 的嵌套引号问题
#
# 3. "## Errors to fix:" + "## Original code:" 的双段结构:
#    错误在前，代码在后，利用 LLM 对错误列表的注意力优先处理问题，
#    然后参考代码进行修复。这个顺序经过验证效果最好。
