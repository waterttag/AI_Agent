"""
API 路由聚合模块 (API Router Aggregation Module)
================================================
WHAT: 将所有 API 子路由（auth、games、tasks、admin）集中注册到一个统一的 api_router 上。
WHY:  单一入口点方便 main.py 只需一行 `app.include_router(api_router)` 即可挂载所有路由，
      避免在应用工厂中逐个注册，降低遗漏风险，符合 FastAPI 大型应用的最佳实践。
技术知识: FastAPI 的 APIRouter 支持嵌套 — 每个子模块定义自己的 prefix/tags，
        然后在顶层通过 include_router 聚合，最终所有路由都会出现在 OpenAPI 文档中。
"""

# FastAPI 的 APIRouter 类，用于创建可复用的路由组。
# 不同于直接使用 app=FastAPI() 上的装饰器，APIRouter 允许将路由逻辑拆分到不同模块中，
# 实现"关注点分离"(Separation of Concerns)，每个模块只管自己那部分 API。
from fastapi import APIRouter

# ---- 导入各子模块的 router 实例 ----
# 每个子模块内部已经定义好了 prefix（如 /auth、/games）和 tags，
# 这里只是把它们的 router 对象拿过来，不必重复设置。

# 认证相关路由：注册、登录、获取当前用户信息、收藏列表
from app.api.auth import router as auth_router

# 游戏 CRUD 路由：创建、列表、详情、更新、删除、资源上传、AI 生成、游玩 HTML、收藏切换
from app.api.games import router as games_router

# 任务路由：生成任务状态轮询、任务列表、Agent 执行日志
from app.api.tasks import router as tasks_router

# 管理路由：种子数据注入（inject-game）等内部运维接口
from app.api.admin import router as admin_router

# 创建顶层 API 路由，所有子路由都会挂载在 /api 前缀下。
# 最终 URL 形如：/api/auth/login、/api/games、/api/tasks/{id}、/api/admin/inject-game
api_router = APIRouter(prefix="/api")

# ---- 将子路由注册到顶层路由 ----
# include_router 会把子路由的所有端点（endpoint）"合并"进来，
# 子路由自身的 prefix 会追加到父路由的 prefix 后面。
# FastAPI 内部用路由表（radix tree）匹配 URL，合并后的路由和直接定义的性能一致。

api_router.include_router(auth_router)    # → /api/auth/*
api_router.include_router(games_router)   # → /api/games/*
api_router.include_router(tasks_router)   # → /api/tasks/*
api_router.include_router(admin_router)   # → /api/admin/*
