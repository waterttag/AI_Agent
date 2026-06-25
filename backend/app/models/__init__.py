"""
模型层模块初始化文件。

本文件是整个 app.models 包的入口，负责：
1. 集中导出所有 ORM 模型类，方便其他模块统一导入
2. 通过 __all__ 声明公开 API，控制模块的外部可见性
3. 利用 Python 的 import 副作用机制：导入本模块时自动注册所有模型，
   使 Alembic 的自动迁移（autogenerate）能发现所有表
"""
# =============================================================================
# 模型导出 (Model Exports)
# =============================================================================

# ---- 用户模型 ----
# User：用户表，存储注册用户信息和认证凭据
from app.models.user import User

# ---- 游戏模型组 ----
# Game：游戏主表，核心业务实体
# GameAsset：游戏资源文件元数据表（存储在 OSS）
# GameFavorite：用户-游戏收藏关联表（复合主键）
from app.models.game import Game, GameAsset, GameFavorite

# ---- 生成任务模型 ----
# GenerationTask：AI 游戏生成任务表，追踪异步生成生命周期
from app.models.task import GenerationTask

# ---- 公开 API 声明 ----
# __all__ 的作用：
# 1. 限制 `from app.models import *` 的导入范围
#    （虽然项目中使用显式导入，但设置 __all__ 是良好实践）
# 2. 文档化本包对外提供哪些模型
# 3. IDE 智能提示：工具可以据此判断哪些符号是"公开"的
#
# 注意：Alembic 的自动迁移依赖 SQLAlchemy Base.metadata，
# 因此所有模型必须在应用启动前被 import（通常由 FastAPI 的
# app 初始化流程触发，或通过 alembic/env.py 中的 target_metadata 导入）
__all__ = ["User", "Game", "GameAsset", "GameFavorite", "GenerationTask"]
