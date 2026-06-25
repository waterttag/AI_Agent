"""
GenerationTask ORM model.

AI 游戏生成任务 ORM 模型。

这个模型是整个应用最关键的业务表之一——它追踪每一次
AI 生成游戏请求的完整生命周期：从用户提交提示词到最终交付 HTML 游戏。
"""
# =============================================================================
# AI 生成任务模型 (GenerationTask)
# =============================================================================
# 设计目标：
#   异步任务追踪：AI 游戏生成可能需要数十秒甚至数分钟，不能阻塞 HTTP 响应。
#   本模型允许前端通过轮询或 WebSocket 实时获取任务进度。
#
# 任务状态机语义：
#   pending ──入队──> queued ──开始处理──> processing ──成功──> completed
#                  │                       │                    │
#                  └──取消──> cancelled     └──失败──> failed    └──结果可被清理
#
# 核心数据存储：
# 1. config：任务配置 JSON（模型参数字典），灵活可扩展
# 2. system_prompt_used / user_prompt_used：实际使用的提示词文本，
#    用于事后分析（调试、质量审查、A/B 测试）
# 3. llm_response_raw：LLM 原始响应全文存储，Text 类型无长度限制
# 4. result_oss_url：AI 生成的 HTML 游戏部署到 OSS 后的 URL
# 5. progress：0-100 的整数进度，用于前端进度条渲染
# 6. error_message：失败时存储错误详情，用于用户提示和开发者调试

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GenerationTask(Base):
    """
    AI 游戏生成任务模型。

    每条记录代表一次完整的生成请求，从提交到完成（或失败）的全生命周期。
    """
    __tablename__ = "generation_tasks"

    # ---- 主键（任务 ID） ----
    # 每个生成任务有一个唯一 UUID，前端用此 ID 轮询任务状态
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # ---- 关联游戏 ID（外键） ----
    # 任务的目标游戏。一个游戏可能对应多次生成任务（如重新生成、迭代）
    # 任务创建时会先在 games 表创建一条 draft 记录，然后用此 FK 关联
    game_id: Mapped[str] = mapped_column(String(36), ForeignKey("games.id"), nullable=False)
    # ---- 发起用户 ID（外键） ----
    # 记录是哪个用户发起的生成请求，用于权限校验和用户历史查询
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    # ---- 任务状态（状态机核心字段） ----
    # 状态流转：
    #   pending    - 刚创建，等待后台 worker 拉取
    #   queued     - 已被 worker 接收，但在队列中等待处理
    #   processing - worker 正在调用 LLM 并生成游戏资源
    #   completed  - 生成成功，result_oss_url 存储了游戏 URL
    #   failed     - 生成失败，error_message 存储错误详情
    #   cancelled  - 用户取消了任务
    #
    # index=True：后台 worker 需要频繁查询 pending/queued 的任务来拉取执行
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", index=True
    )
    # ---- 任务配置（JSON 灵活结构） ----
    # 存储本次生成的参数配置，例如：
    #   {"model": "claude-sonnet-4-20250514", "temperature": 0.8, "max_tokens": 4096}
    # 使用 JSON 类型：
    #   - 不同模型/不同生成策略可能需要不同参数，JSON 无需 ALTER TABLE
    #   - PostgreSQL 可直接对 JSON 内部字段做查询（如 config->>'model'）
    #   - 相比于固定列，JSON 更灵活但无法享受列级别的类型检查
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # ---- 系统提示词（System Prompt） ----
    # 存储实际使用的 System Prompt 全文
    # 为什么要存储：
    #   - 事后审查：当生成质量不佳时，可以回溯 prompt 是否有问题
    #   - 调试：快速对比不同版本的 prompt 效果
    #   - A/B 测试：不同 prompt 策略的生成结果对比
    # 注意：Text 类型无长度限制，但过长的 prompt 会增加 db 存储成本
    system_prompt_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ---- 用户提示词（User Prompt） ----
    # 存储发送给 LLM 的最终用户提示词（可能经过模板渲染）
    # 与用户的原始输入 prompt_text 不同，此字段可能包含
    # 模板渲染后的完整内容（如附加的格式说明、约束条件）
    user_prompt_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ---- LLM 原始响应 ----
    # 存储大模型返回的完整原始响应文本
    # 为什么保留（而不是只保留解析后的结果）：
    #   - 解析失败时回溯：如果代码生成/结构化提取出错，可重新解析原始响应
    #   - 模型行为分析：分析 LLM 输出模式、Token 使用等
    #   - 质量审查：检查生成过程是否符合预期
    #   - 成本：Text 类型存储成本较低（典型的 Claude 响应 4K-32K tokens），
    #     而丢失信息后无法恢复的成本更高
    # 生产环境需要注意：如果响应非常大（如 100K+ tokens），
    #   考虑使用对象存储（OSS/S3）而非数据库存储
    llm_response_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ---- 生成结果 OSS URL ----
    # 存储 AI 生成的 HTML 游戏文件在 OSS 上的完整 URL
    # 当 status=completed 时，此字段应有值
    # 前端使用此 URL 在 iframe 中加载和展示生成的游戏
    result_oss_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # ---- 错误信息 ----
    # 当 status=failed 时，存储错误详情
    # 内容可能包括：LLM API 错误、超时、解析失败、OSS 上传失败等
    # 面向开发者调试，可能包含技术细节（栈跟踪、HTTP 状态码等）
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ---- 进度（0-100 整数） ----
    # 用于前端渲染进度条，轮询任务状态时同步展示
    # 进度映射（示意）：
    #   0-20：任务已入队
    #   20-40：正在调用 LLM
    #   40-70：正在解析生成结果
    #   70-90：上传资源到 OSS
    #   90-99：最终验证
    #   100：完成（此时 status 通常已是 completed）
    # 使用 Integer 而非 Float，因为百分比精度无需小数
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # ---- 开始处理时间 ----
    # worker 开始处理任务时设置（status 变为 processing 时）
    # 用于计算任务执行时长和超时判断
    # 可为 None：任务可能一直停留在 pending 状态
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # ---- 完成时间 ----
    # 任务完成（成功）或失败时设置
    # 用于计算总耗时、排序（最近完成的任务）
    # 注意：cancelled 状态的任务是否设置此字段取决于业务逻辑
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # ---- 创建时间 ----
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # =========================================================================
    # 关系定义 (Relationships)
    # =========================================================================
    # ---- 关联的游戏 ----
    # 通过 task.game 可访问此任务对应的 Game 对象
    # 例如：task.game.title 获取游戏标题
    game: Mapped["Game"] = relationship("Game", foreign_keys=[game_id])
    # ---- 关联的用户 ----
    # 通过 task.user 可访问发起任务的 User 对象
    # 例如：task.user.username 获取发起者用户名
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        """
        开发者友好的字符串表示。
        显示 id（任务标识）和 status（当前状态），轻量且信息充足。
        """
        return f"<GenerationTask(id={self.id}, status={self.status})>"
