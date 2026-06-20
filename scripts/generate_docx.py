"""Generate the final delivery docx — professional, consistent styling."""

from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import os

FONT = "微软雅黑"
H1_COLOR = RGBColor(0x1E, 0x3A, 0x5F)
H2_COLOR = RGBColor(0x25, 0x63, 0xEB)
HEADER_BG = "1E3A5F"
ALT_ROW_BG = "F0F4FF"
MUTED = RGBColor(0x88, 0x88, 0x88)

# ── helpers ──────────────────────────────────────────────────────────

def _rf(run, size=Pt(10), bold=False, color=None):
    run.font.size = size
    run.font.name = FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    run.font.bold = bold
    if color: run.font.color.rgb = color

def _shade(cell, color):
    s = OxmlElement("w:shd"); s.set(qn("w:fill"), color); s.set(qn("w:val"), "clear")
    cell._tc.get_or_add_tcPr().append(s)

def _cell(cell, text, size=Pt(8.5), bold=False, color=None, center=False):
    cell.text = ""; p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run(str(text)); _rf(r, size, bold, color)

def _table(doc, hdrs, rows, widths=None):
    t = doc.add_table(rows=1+len(rows), cols=len(hdrs)); t.alignment = WD_TABLE_ALIGNMENT.CENTER; t.style = "Table Grid"
    for i,h in enumerate(hdrs): c=t.rows[0].cells[i]; _cell(c,h,Pt(9),True,RGBColor(0xFF,0xFF,0xFF),True); _shade(c,HEADER_BG)
    for ri,row in enumerate(rows):
        for ci,val in enumerate(row):
            c=t.rows[ri+1].cells[ci]; _cell(c,val,Pt(8.5))
            if ri%2==1: _shade(c,ALT_ROW_BG)
    if widths:
        for i,w in enumerate(widths):
            for row in t.rows: row.cells[i].width=Cm(w)
    doc.add_paragraph(""); return t

def _h(doc, text, level=1):
    h=doc.add_heading(text,level=level)
    for r in h.runs:
        r.font.name=FONT; r._element.rPr.rFonts.set(qn("w:eastAsia"),FONT)
        r.font.color.rgb=H1_COLOR if level==1 else H2_COLOR
    return h

def _p(doc, text, size=Pt(8.5), bold=False, color=None, center=False):
    p=doc.add_paragraph(); r=p.add_run(text)
    _rf(r,size,bold,color)
    if center: p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    return p

# ── document body ────────────────────────────────────────────────────

def build():
    doc = Document()
    for s in doc.sections:
        s.top_margin=Cm(2.5); s.bottom_margin=Cm(2.5)
        s.left_margin=Cm(2.8); s.right_margin=Cm(2.8)

    sty=doc.styles["Normal"]
    sty.font.size=Pt(9.5); sty.font.name=FONT
    sty.element.rPr.rFonts.set(qn("w:eastAsia"),FONT)
    sty.paragraph_format.space_after=Pt(6); sty.paragraph_format.line_spacing=1.3

    # ── Cover ──
    for _ in range(5): doc.add_paragraph("")
    _p(doc,"AI Native 互动游戏 Web 平台",Pt(26),True,RGBColor(0x1E,0x3A,0x5F),True)
    _p(doc,"系统设计测试 — 交付文档",Pt(14),False,RGBColor(0x66,0x66,0x66),True)
    doc.add_paragraph("")
    for l in ["候选人：Niuyuhang","提交日期：2026-06-20",
              "GitHub：github.com/waterttag/AI_Agent",
              "Demo：https://aiagent-production-5b68.up.railway.app",
              "测试账号：demo@aigame.dev / demo123"]:
        _p(doc,l,Pt(10),False,MUTED,True)
    doc.add_page_break()

    # ── TOC ──
    _h(doc,"目录")
    for t in ["一、项目概述","二、技术栈","三、系统架构设计","四、数据模型设计",
              "五、API 接口设计","六、AI Agent 选型与编排","七、远程部署协议",
              "八、安全策略","九、失败恢复机制","十、可观测性","十一、详细交付物清单",
              "十二、功能验证总结","十三、完成度说明","十四、AI 协同记录"]:
        _p(doc,t,Pt(10))
    doc.add_page_break()

    # ── 1 ──
    _h(doc,"一、项目概述")
    _p(doc,"本项目是一个 AI Native 互动游戏 Web 平台 MVP（参考 Astrocade），用 2 天时间在 AI 编程工具的协同下从零搭建，打通了「注册/登录 → 创意生成 → 游戏发布 → 浏览游玩」的完整业务闭环。")
    _h(doc,"产品主旅程",2)
    _p(doc,"• 玩家旅程：发现 → 浏览 → 游玩（Home → Play）\n• 创作者旅程：创意 → AI 生成 → 预览 → 发布（Create → Generate → Preview → Publish）")
    _h(doc,"用户角色",2)
    _table(doc,["角色","核心活动","实现状态"],[
        ["玩家 (Player)","浏览平台游戏、点击游玩、查看游戏信息","Home + Play 页"],
        ["创作者 (Creator)","登录 → Create → 输入创意+上传素材 → DeepSeek 生成 → 预览 → 发布","完整闭环"],
        ["平台维护者 (Maintainer)","关注任务稳定性、管理 OSS 文件、处理不安全内容","Health + 自动种子"],
    ],[3,7,4])

    # ── 2 ──
    _h(doc,"二、技术栈")
    _table(doc,["层级","技术选型","选型理由"],[
        ["前端","React 18 + Vite + TypeScript + Tailwind CSS + TanStack Query + Zustand","Vite HMR 极速开发；Tailwind 零切换成本；TanStack Query 一行搞定缓存+轮询"],
        ["后端","FastAPI (Python) + SQLAlchemy 2.0 (async) + Celery + Redis","异步原生 + 自动 OpenAPI 文档；Python 是 AI SDK 首选；Celery 解耦 LLM 长耗时调用"],
        ["数据库","SQLite (dev) → PostgreSQL (prod)","ORM 抽象层隔离差异，改 DATABASE_URL 一行切换"],
        ["对象存储","boto3 S3 → 阿里云 OSS / AWS S3 / MinIO / R2","单客户端兼容多服务；自动检测 URL 风格；无存储时降级 DB"],
        ["AI / LLM","适配器工厂 (Claude | OpenAI | DeepSeek)","策略模式 env 切换；DeepSeek 继承 OpenAI 仅改 base_url"],
        ["部署","Railway (Dockerfile) + 阿里云 OSS","多阶段 Docker 构建；CMD shell 形式接受 $PORT"],
    ],[2.5,5,7])

    # ── 3 ──
    _h(doc,"三、系统架构设计")
    _h(doc,"3.1 协作流程",2)
    _p(doc,"浏览器 (React+Vite) ←→ FastAPI Backend ←→ Celery Worker (Redis) ←→ DeepSeek API\n                    ↕                       ↕\n              SQLite / PG          阿里云 OSS / MinIO / R2")
    _p(doc,"1. 用户通过 REST API 与 FastAPI 通信\n2. 生成请求到达后，FastAPI 创建 task 并入队 Celery（Redis 为代理）\n3. Celery Worker 独立进程执行 4 阶段 Pipeline：Preprocess → Generate → Validate → Package\n4. 游戏 HTML 上传到 OSS（或降级 DB），通过 play-html 端点由 iframe 加载\n5. 生成后进入 preview 状态，创作者确认后 Publish")
    _h(doc,"3.2 为什么 Celery + Redis？",2)
    _p(doc,"BackgroundTasks 在主进程中执行，LLM 调用 30-120s 会阻塞整个 worker。Celery 独立进程 + Redis 消息队列实现请求与生成功解耦，支持水平扩展。")
    _h(doc,"3.3 为什么 SQLite → PostgreSQL 双模式？",2)
    _p(doc,"SQLAlchemy async ORM 抽象隔离差异，改一个环境变量即可切换。SQLite 零配置开发，PostgreSQL 提供生产级并发。")

    # ── 4 ──
    _h(doc,"四、数据模型设计")
    _p(doc,"共 5 张表，拆分为独立实体，通过外键和 JSON 灵活关联：")
    _table(doc,["表名","核心字段","设计要点"],[
        ["users","id, username, email, password_hash (bcrypt), role","role 预留 OAuth 扩展；认证与业务分离"],
        ["games","id, title, description, game_url, author_id, tags (JSON),\nstatus (draft|generating|preview|published|failed), prompt_text, play_count","status 状态机驱动全生命周期；tags 用 JSON 灵活支持任意标签；preview 实现发布前审查"],
        ["game_assets","id, game_id (FK), asset_type, oss_key, oss_url","多对一关联 games；boto3 客户端上传到阿里云 OSS"],
        ["generation_tasks","id, game_id (FK), user_id (FK), status, progress,\nsystem_prompt_used, user_prompt_used, llm_response_raw,\nresult_oss_url, error_message","生成过程与游戏解耦，历史可追溯；完整保存 prompt+响应供调试和日志展示"],
        ["game_favorites","user_id+game_id (复合 PK), created_at","轻量收藏表，复合主键天然去重；支持 toggle 切换"],
    ],[2.5,5.5,6])
    _h(doc,"tags 为什么用 JSON 而非关联表？",2)
    _p(doc,"游戏标签数量少（≤10）且无需跨游戏聚合查询。JSON 列避免额外 join，SQLite 用 cast(Text).like()，PostgreSQL 可用 GIN 索引。")

    # ── 5 ──
    _h(doc,"五、API 接口设计")
    _p(doc,"共 20 个端点，完整 OpenAPI 文档（/docs）：")
    _table(doc,["分组","方法","路径","说明","Auth"],[
        ["Auth","POST","/auth/register","注册","—"],
        ["Auth","POST","/auth/login","登录","—"],
        ["Auth","GET","/auth/me","当前用户信息","✅"],
        ["Auth","GET","/auth/me/favorites","我的收藏 ID 列表","✅"],
        ["Games","GET","/games?status=&tag=&page=&size=","列表 (分页+筛选)","—"],
        ["Games","GET","/games/{id}?increment=","详情 (播放计数)","—"],
        ["Games","POST","/games","创建草稿","✅"],
        ["Games","PUT","/games/{id}","更新 (含发布)","✅"],
        ["Games","DELETE","/games/{id}","删除","✅"],
        ["Games","GET","/games/{id}/play-html","直接服务游戏 HTML","—"],
        ["Assets","POST","/games/{id}/assets","上传文件到 OSS","✅"],
        ["Assets","GET","/games/{id}/assets","素材列表","—"],
        ["Tasks","POST","/games/{id}/generate","触发 AI 生成","✅"],
        ["Tasks","GET","/tasks/{id}","轮询任务进度","✅"],
        ["Tasks","GET","/tasks/games/{id}","版本历史","✅"],
        ["Tasks","GET","/tasks/games/{id}/log","Agent 执行日志","✅"],
        ["Favorites","POST","/games/{id}/favorite","收藏/取消","✅"],
        ["Favorites","GET","/games/{id}/favorite","收藏状态+计数","✅"],
        ["Admin","POST","/admin/inject-game","注入预构建游戏","—"],
    ],[1.5,1.2,4.5,3.5,1])

    # ── 6 ──
    _h(doc,"六、AI Agent 选型与编排")
    _h(doc,"6.1 适配器工厂",2)
    _p(doc,"采用策略模式，LLM_PROVIDER 环境变量切换。新增模型只需实现 LLMAdapter 基类：\n  LLMAdapter (ABC)\n  ├── ClaudeAdapter  → api.anthropic.com (支持 Vision)\n  ├── OpenAIAdapter  → api.openai.com (支持 Vision + 自定义 base_url)\n  └── DeepSeekAdapter → api.deepseek.com (继承 OpenAIAdapter)")
    _h(doc,"6.2 为什么自建而非用 OpenClaw / Hermes / LangGraph？",2)
    _p(doc,"本项目的核心任务是「一段 prompt → 一个 HTML 文件」的单次生成，不需要多步推理和多工具编排。\n• OpenClaw/Hermes/Pi Agent：完整 Agent 框架，引入徒增认知负担\n• LangGraph：适合有状态多节点工作流，当前线性 Pipeline 用 status + Celery 即可表达\n• 扩展路径：若未来需要多 Agent 协作，Pipeline 中的每个 Phase 可无损映射为 LangGraph Node")
    _h(doc,"6.3 4-Phase Pipeline",2)
    _table(doc,["Phase","内容","进度"],[
        ["1. Preprocess","加载素材 → Vision API 描述 → 组装上下文","0-30%"],
        ["2. Generate","构建 System Prompt → 调用 LLM → 收集完整 HTML","30-70%"],
        ["3. Validate","BeautifulSoup 解析 → 检查 game loop → 禁止 eval() → CDN 白名单 → 失败自动修复","70-85%"],
        ["4. Package","Content-Disposition: inline → 上传 OSS 或降级 DB → 设置 preview 状态","85-100%"],
    ],[2,9.5,2.5])

    # ── 7 ──
    _h(doc,"七、远程部署协议")
    _h(doc,"7.1 为什么单文件 HTML？",2)
    _p(doc,"1. 存储简单：一个游戏一个文件，路径 games/{id}/index.html\n2. 传输高效：一次 HTTP GET 加载全部内容\n3. LLM 友好：模型天然擅长输出自包含单文件\n4. 沙箱安全：iframe 加载单文件无相对路径跨越问题\n5. 跨平台：移动端桌面端任何浏览器都能打开")
    _h(doc,"7.2 Play 页加载流程",2)
    _p(doc,"1. 前端 GET /api/games/{id}?increment=true → 获取 game_url + 累计播放\n2. <iframe sandbox=\"allow-scripts allow-same-origin\" src={game_url}>\n3. game_url 使用 play-html 端点，避免 OSS Content-Disposition 触发下载\n4. Bucket 配置 public-read ACL + CORS\n5. 无对象存储时自动降级：generation_tasks.llm_response_raw → 直接服务")

    # ── 8 ──
    _h(doc,"八、安全策略")
    _table(doc,["威胁层面","措施","技术实现"],[
        ["认证","JWT (HS256, 24h), bcrypt 哈希","python-jose + passlib"],
        ["上传安全","MIME 白名单 (image/*, audio/*), 限 10 文件","FastAPI UploadFile 校验"],
        ["生成代码执行","iframe sandbox 隔离, Validator 禁止 eval()","allow-scripts allow-same-origin"],
        ["Prompt Injection","用户输入仅作 User Message，不进入 System Prompt","后端构建 System Prompt"],
        ["密钥管理",".env + .gitignore，生产用 Railway Secret","不提交真实密钥"],
        ["资源控制","max_tokens: 16000, Worker pool=solo","防止并发过载和费用失控"],
    ],[2.5,5,5.5])

    # ── 9 ──
    _h(doc,"九、失败恢复机制")
    _table(doc,["故障场景","恢复策略","可观察性"],[
        ["LLM API 超时/500","Celery 自动重试 1 次（60s），仍失败写 error_message","task.status = failed + 前端错误"],
        ["HTML 校验失败","错误列表返回 LLM 二次修复（t=0.5），仍失败降级交付","Validator 日志 + llm_response_raw"],
        ["OSS 上传失败","降级 DB 存储，play-html 端点直接服务","日志：'storing in DB'"],
        ["素材描述失败","跳过该素材，其余正常注入","日志 + 任务继续"],
        ["部署重启丢数据","启动时自动 _auto_seed() 注入 3 款游戏 + demo 用户","/health 验证"],
        ["前端上传失败","跳过该文件，不阻断 AI 生成","console.warn + 继续"],
    ],[3.5,6,4.5])

    # ── 10 ──
    _h(doc,"十、可观测性")
    _table(doc,["观察维度","记录方式","证据路径"],[
        ["任务进度","Celery 状态机 + DB generation_tasks 实时 progress","GET /api/tasks/{id}"],
        ["Agent 日志","Python logging 每个 Phase 输出 [task_id] Phase N","Railway Deploy Logs"],
        ["LLM 调用记录","system_prompt_used + user_prompt_used + llm_response_raw","Agent Log API + DB 查询"],
        ["播放统计","GET ?increment=true 自动 +1，Home 卡片显示","Eye 图标"],
        ["前端 Pipeline 可视化","4 阶段进度条 + 步骤高亮","Create 页面"],
        ["版本历史","generation_tasks 按时间倒序","Play 页面可展开列表"],
        ["系统健康","/health + Readiness","curl /health → 200"],
        ["自动种子","启动检测空 DB → 注入 3 款游戏","首次访问即有数据"],
        ["验证证明","22 项 API 测试 + 安全 + 性能","docs/VERIFICATION.md"],
    ],[3,5.5,5.5])

    # ── 11 ──
    _h(doc,"十一、详细交付物清单")
    _p(doc,"对照测试文档 3.3 节：")
    _table(doc,["#","交付物","状态","说明"],[
        ["1","源代码仓库","✅","github.com/waterttag/AI_Agent — 15 次 commit"],
        ["2","Demo 地址","✅","aiagent-production-5b68.up.railway.app"],
        ["3","部署方式","✅","Docker Compose + Railway + 阿里云 OSS"],
        ["4","测试数据","✅","3 种子游戏 + Space Shooter (DeepSeek) + 自动种子"],
        ["5","环境变量","✅",".env.example 含全部 18 个环境变量"],
        ["6","系统设计文档","✅","docs/SYSTEM_DESIGN.md 含架构/数据/API/Agent/安全/恢复全维度"],
        ["7","技术栈","✅","README 完整列出选型及理由"],
        ["8","完成度说明","✅","docs/COMPLETION_REPORT.md 含已完成/未完成/改进计划"],
        ["9","功能验证证明","✅","docs/VERIFICATION.md — 22 项 API 测试全通过"],
        ["10","演示视频","⏸️","录制脚本已备好 (docs/DEMO_SCRIPT.md)"],
        ["11","AI 协同记录","✅","docs/AI_COLLAB_LOG.md 含工具/策略/占比/日志"],
    ],[0.8,2.5,1,9.5])

    # ── 12 ──
    _h(doc,"十二、功能验证总结")
    _p(doc,"以下全部项已通过线上实测（aiagent-production-5b68.up.railway.app）：")
    _table(doc,["#","功能","方式"],[
        ["1","用户注册 + JWT","curl POST → 201"],
        ["2","用户登录","curl POST → 200 + token"],
        ["3","登录失败提示","curl POST → 401"],
        ["4","重复注册拒绝","curl POST → 409"],
        ["5","退出登录","Zustand store 清除"],
        ["6","游戏列表 (3 款)","curl GET → published"],
        ["7","标签筛选","?tag=arcade → 2"],
        ["8","分页翻页","?page=1&size=2 → 2 items"],
        ["9","播放计数 +1","?increment=true → OK"],
        ["10","收藏切换","POST toggle → true/false"],
        ["11","未登录创建拒绝","curl POST → 401"],
        ["12","AI 生成 (DeepSeek)","POST → poll → completed"],
        ["13","Preview 非公开","公网列表不含 preview"],
        ["14","Publish 发布","PUT status=published → 公网可见"],
        ["15","Agent 执行日志","tasks/log → summary+steps"],
        ["16","版本历史","tasks/games/{id} → 数组"],
        ["17","OSS 上传 (阿里云)","boto3 PUT → GET 200"],
        ["18","OSS Content-Disposition 修复","inline + play-html"],
        ["19","无 API Key 降级","LLM_PROVIDER=none → 503"],
        ["20","自动种子数据","部署即 3 款游戏"],
        ["21","健康检查","/health → 200"],
        ["22","全屏 Escape","iframe 全屏 + 按钮退出"],
    ],[0.8,5,5])

    # ── 13 ──
    _h(doc,"十三、完成度说明")
    _h(doc,"核心功能",2)
    _table(doc,["模块","完成度","关键功能"],[
        ["Auth","100%","邮箱注册/登录/退出/JWT, OAuth 扩展预留"],
        ["Home","100%","卡片网格/标签筛选/分页/播放次数/收藏"],
        ["Play","100%","iframe 动态加载/全屏/失败重试/退出入口"],
        ["Create","100%","文本+素材/4 阶段 Pipeline/Agent 日志/Preview→Publish"],
        ["Agent Harness","100%","3 种 LLM 适配器/Validator/Auto-fix/OSS 降级"],
        ["对象存储","100%","boto3 多服务/自动检测 URL 风格/DB 降级"],
        ["部署","100%","Docker + Railway + OSS/自动种子/健康检查"],
    ],[3,1.5,9.5])
    _h(doc,"加分项 (已全部完成)",2)
    _table(doc,["加分项","状态","实现"],[
        ["标签筛选","✅","Home 页 Filter Bar + 卡片标签可点击"],
        ["分页翻页","✅","Prev/Next + 页码"],
        ["播放统计","✅","Eye 图标 + ?increment=true 精确计数"],
        ["收藏","✅","❤️ toggle + Favorites 筛选"],
        ["Preview → Publish","✅","预览横幅 → Publish Now"],
        ["Agent 日志","✅","生成完成页展示 Prompt + Pipeline 步骤"],
        ["版本历史","✅","Play 页可展开"],
        ["失败重试","✅","错误信息 + Try Again + Celery 重试"],
        ["安全沙箱","✅","iframe sandbox + Validator 禁止 eval()"],
        ["资源限额","✅","max_tokens + solo pool"],
    ],[3,1.5,9.5])
    _h(doc,"未完成",2)
    _p(doc,"• OAuth 第三方登录：文档注明 demo 阶段可不实现，role 字段已预留\n• 演示视频：录制脚本已备好\n• WebSocket 推送：当前轮询方案 MVP 够用，升级只需改一处")

    # ── 14 ──
    _h(doc,"十四、AI 协同记录")
    _table(doc,["项目","内容"],[
        ["主力 AI 工具","Claude Code (CLI) — 架构设计、代码生成、联调部署"],
        ["内容生成 AI","DeepSeek API (deepseek-chat) — HTML5 游戏代码生成"],
        ["关键 Prompt","系统架构设计：输入 .docx 全文 → 输出架构方案\nAgent Harness System Prompt：4 阶段约束 + 安全规则 + auto-fix 模板\n修复 Prompt：校验失败错误列表 → LLM 二次修复"],
        ["AI 辅助占比","项目结构约 80% / ORM+Schemas 约 85% / API 约 75% / Agent Harness 约 80%、前端组件约 60% / 文档约 70%、种子游戏约 10%（手写 HTML）"],
        ["人工修正","SQLAlchemy greenlet 错误（懒加载 assets）/ MinIO→boto3 迁移 / OSS Content-Disposition 修复、前端 TS 类型错误 / 数据库路径统一 / Railway Dockerfile 适配"],
        ["开发时间","Day 1：脚手架→后端→前端→Agent→Celery→种子→联调\nDay 2：部署→修复→自动种子→加分项（标签/预览/分页/收藏/日志/版本）"],
        ["Git 提交","16 次 commit，清晰的分阶段提交历史"],
    ],[3,11])

    doc.add_paragraph("")
    _p(doc,"— AI Native 互动游戏 Web 平台 · 系统设计测试交付文档 · 2026-06-20 —",Pt(8),False,MUTED,True)

    out = os.path.join(os.path.dirname(__file__),"..","AIAgent全栈工程师-交付文档-终版.docx")
    doc.save(out)
    print(f"Saved: {os.path.abspath(out)}")

if __name__=="__main__":
    build()
