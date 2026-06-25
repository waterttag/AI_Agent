"""
Task-related Pydantic schemas.

AI 生成任务相关的 Pydantic Schema。

本模块为前端提供了两种粒度的任务视图：
1. TaskResponse：完整任务信息（用于任务详情页）
2. TaskLogResponse：简化的日志/进度摘要（用于轻量轮询）
"""
# =============================================================================
# 任务 Schema 模块
# =============================================================================
# 设计要点：
# - 响应中不返回 llm_response_raw（原始响应体积大，前端不需要）
# - 响应中不返回 config（内部配置，对外无意义）
# - progress 字段让前端无需解析状态字符串即可渲染进度条
# - agent_steps 以人类可读的字符串列表提供执行步骤，兼容不同 AI Agent 的实现

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# =============================================================================
# TaskResponse - 任务详情响应体
# =============================================================================
class TaskResponse(BaseModel):
    """
    完整的任务信息 API 响应 Schema。

    用于任务详情页展示，包含状态、进度和结果信息。
    不包括：
    - config：内部配置，用户不可见
    - llm_response_raw：原始 LLM 响应，体积极大（可达数万字符），
      前端不需要也不应暴露（可能含敏感生成指令细节）
    """
    id: str                  # 任务 UUID（前端轮询用）
    game_id: str             # 关联的游戏 ID（前端跳转到游戏详情）
    user_id: str             # 发起任务的用户 ID
    # ---- 任务状态 ----
    # pending / queued / processing / completed / failed / cancelled
    # 前端根据状态显示不同的 UI（加载动画、成功提示、错误信息）
    status: str
    # ---- 进度（0-100 整数） ----
    # 前端进度条的唯一数据源
    # 0 到 100 对应 0% 到 100% 的进度条宽度
    # 使用 int 而非 str（如 "45%"），因为数字可直接用于计算
    progress: int
    # ---- 结果 URL ----
    # 当 status=completed 时包含 AI 生成游戏的 OSS URL
    # 前端在 iframe 中加载此 URL 展示游戏
    result_oss_url: Optional[str] = None
    # ---- 错误信息 ----
    # 当 status=failed 时包含错误详情
    # 前端在错误提示对话框中展示给用户
    error_message: Optional[str] = None
    # ---- 提示词回溯 ----
    # system_prompt_used 和 user_prompt_used 用于：
    # 1. 用户查看"我输入了什么提示词"
    # 2. 开发者调试生成质量问题
    # 不返回 llm_response_raw（体积太大），有需要时单独查询
    system_prompt_used: Optional[str] = None
    user_prompt_used: Optional[str] = None
    # ---- 时间戳 ----
    # started_at：开始处理时间，用于显示"任务耗时"
    # completed_at：完成时间
    # created_at：创建时间，用于排序
    # 三个时间点的差值有业务意义：
    #   - created_at → started_at：队列等待时间
    #   - started_at → completed_at：实际执行时间
    #   - created_at → completed_at：端到端总耗时
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# TaskLogResponse - 任务日志摘要（轻量轮询用）
# =============================================================================
class TaskLogResponse(BaseModel):
    """
    任务日志/进度摘要 Schema。

    相比 TaskResponse，这是一个更轻量的视图，用于：
    1. 前端轮询进度更新（只传必要字段，减少带宽）
    2. 任务历史列表项（不展示完整提示词）
    3. Agent 执行步骤的可视化展示（模拟 IDE 的 agent log）

    轻量设计的好处：
    - 前端每 2-3 秒轮询一次，字段越少响应越小
    - prompt_summary 只取前 200 字符，避免传输数 KB 的完整提示词
    - agent_steps 给用户直观的进度感知："正在分析需求..."、"正在生成代码..."
    """
    # ---- 任务标识和状态 ----
    task_id: str   # 任务 ID
    status: str    # 当前状态
    progress: int  # 进度 0-100

    # ---- 提示词摘要 ----
    # 只取用户提示词的前 200 个字符，给用户一个快速预览
    # 例如："创建一个 2D 平台跳跃游戏，主角是猫，有 5 个关卡，包含..."
    # 为什么不返回完整提示词：
    #   - 轮询时每次传完整提示词浪费带宽
    #   - 详情页可以单独请求 TaskResponse 获取完整内容
    #   - 200 字符足够用户在列表中辨认哪条记录
    prompt_summary: Optional[str] = None

    # ---- Agent 执行步骤 ----
    # 一个人类可读的字符串列表，描述 AI Agent 的当前执行状态
    # 示例值：
    #   [
    #     "收到生成请求：'创建一个贪吃蛇游戏'",
    #     "正在分析游戏需求...",
    #     "生成游戏设计文档...",
    #     "编写 HTML/CSS/JS 代码...",
    #     "验证游戏可玩性...",
    #     "上传游戏文件到 OSS...",
    #     "生成完成！游戏已就绪"
    #   ]
    #
    # 设计为 list[str]（而非 JSON 对象）：
    #   - 顺序性好：前端直接 map 渲染为有序列表
    #   - 灵活性：Agent 可以追加任意文本步骤，无需预定义步骤模板
    #   - 调试友好：字符串列表便于日志记录和问题排查
    #
    # default_factory=list：没有步骤时返回空列表而非 None，
    #   前端无需处理 null 判断
    agent_steps: list[str] = Field(default_factory=list)

    # ---- 时间戳 ----
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
