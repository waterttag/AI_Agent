"""
Celery 应用实例 (Celery Application Instance)
===============================================
WHAT: 创建并配置 Celery 异步任务队列的 app 实例。
WHY:  Celery 是 Python 生态中最成熟的分布式任务队列，用于将 AI 游戏生成（耗时 30s-2min）
      从 API 进程中解耦出来，实现异步处理。

Celery 核心概念:
    ============================================================
    Producer (生产者):
        - FastAPI 路由调用 task.delay() 发送任务消息到 Broker
        - 例如: generate_game_task.delay(task_id="...", game_id="...")

    Broker (消息中间件):
        - 存储待执行的任务消息
        - 本项目使用 Redis（通过 redis_url 配置）
        - 其他选择: RabbitMQ、Amazon SQS

    Worker (消费者/执行者):
        - 独立的进程，从 Broker 取消息并执行任务
        - 启动命令: celery -A app.celery_app worker -l info -P solo
        - -P solo: 使用 solo 进程池（单进程，适合 Windows 开发）

    Result Backend (结果存储):
        - Worker 执行完任务后把结果存到这里
        - 本项目也使用 Redis（和 Broker 同一个）
        - Producer 可以通过 AsyncResult(task_id).get() 获取结果
        - 本项目通过数据库轮询获取结果（而非 Celery result backend）
    ============================================================

为什么 Celery prefork 进程池在 Windows 上不工作?
    ============================================================
    根本原因: Windows 没有 fork() 系统调用。

    fork() 是 POSIX 标准的一部分（Unix/Linux/macOS），用于创建子进程。
    工作原理:
        1. 父进程调用 fork() → 操作系统复制整个进程的内存空间
        2. 子进程从 fork() 返回点继续执行
        3. 子进程继承了父进程的所有状态（变量、文件描述符、数据库连接等）
        4. 写时复制 (Copy-on-Write): 父子进程共享内存页直到某个进程修改它

    Celery 的 prefork 池利用 fork() 来:
        - 预创建多个 worker 子进程（避免每次任务都创建新进程的开销）
        - 子进程自动继承父进程加载的模块（不需要重新 import）
        - 父进程管理子进程的生命周期

    Windows 的替代方案:
        - spawn: 从零开始启动新 Python 解释器（Windows 默认）
          → 慢（需要重新 import 所有模块）
          → 需要 if __name__ == "__main__" 保护（避免无限递归 spawn）
        - solo: 单进程执行（开发环境推荐）
          → 简单可靠，但一次只能执行一个任务
        - threads: 线程池（轻量但注意 GIL）
          → 对 I/O 密集型任务有效，CPU 密集型任务受 GIL 限制

    本项目的回退方案（在 games.py 的 generate 端点中）:
        当 Celery 不可用时（Redis 未启动或 Windows 环境），
        使用 threading.Thread + asyncio.run() 在进程内执行任务。
        详见 games.py 中 POST /generate 端点的注释。
    ============================================================

关键配置项说明:
    task_serializer="json":
        - 任务消息使用 JSON 序列化
        - 优点: 跨语言兼容、人类可读
        - 缺点: 不能序列化复杂 Python 对象（如 datetime 需转字符串）

    task_acks_late=True:
        - 延迟确认: Worker 执行完任务后才发送 ACK
        - 默认是"提前确认"（任务被 Worker 接收后立即 ACK）
        - 延迟确认的好处: 如果 Worker 在执行过程中崩溃，任务会被重新分发给其他 Worker
        - 代价: 可能导致任务重复执行（需要任务本身是幂等的）

    worker_prefetch_multiplier=1:
        - 每个 Worker 预取多少任务
        - 默认是 4（预取 4 个任务）
        - 设为 1: 一次只取一个任务，处理完再取下一个
        - 适合长任务: 避免某个 Worker 囤积多个耗时任务导致负载不均

    task_track_started=True:
        - 跟踪任务"已开始"状态
        - 开启后任务状态有: PENDING → STARTED → SUCCESS/FAILURE
        - 关闭后只有: PENDING → SUCCESS/FAILURE
"""

from celery import Celery

from app.config import settings


# ============================================================================
# Celery 应用实例创建
# ============================================================================
celery_app = Celery(
    # 应用名称: 用于标识（在监控、日志中可见）
    "ai_game_platform",

    # broker: 消息中间件 URL
    # 格式: redis://host:port/db_number
    # 例如: redis://localhost:6379/0
    # Celery 将任务消息写入 Redis 的 list 数据结构
    broker=settings.redis_url,

    # backend: 结果存储 URL（和 broker 可以相同）
    # 任务执行结果也存在 Redis 中
    # 本项目主要通过数据库轮询获取结果，但保留 backend 配置以备将来使用
    backend=settings.redis_url,

    # include: 任务模块列表
    # Celery worker 启动时会 import 这些模块来发现被 @celery_app.task 装饰的函数
    # 如果不 include，Worker 不知道有哪些任务可以执行
    include=["app.tasks.game_gen"],
)


# ============================================================================
# Celery 配置更新
# ============================================================================
celery_app.conf.update(
    # ---- 序列化配置 ----
    # JSON 序列化: 任务参数和返回值都用 JSON 格式
    # 限制: 不能传 Python 对象，参数必须是 JSON 可序列化的类型（str, int, list, dict, None）
    task_serializer="json",
    accept_content=["json"],     # 只接受 JSON 格式的消息（安全: 拒绝 pickle）
    result_serializer="json",

    # ---- 时区配置 ----
    # UTC: 统一使用 UTC 时间，避免夏令时和时区问题
    timezone="UTC",
    enable_utc=True,

    # ---- 任务行为配置 ----
    # task_track_started: 跟踪"已开始"状态
    # 开启后前端可以区分"排队中"和"执行中"两种状态
    task_track_started=True,

    # task_acks_late: 延迟确认
    # True:  执行完后确认 → Worker 崩溃时任务不丢失
    # False: 接收后确认 → Worker 崩溃时任务丢失（但不会重复执行）
    # 对于 AI 生成长任务，选择 True 更安全
    task_acks_late=True,

    # worker_prefetch_multiplier: 预取倍数
    # 1: 一次只取一个任务
    # 为什么设为 1? AI 生成任务是 CPU/IO 密集型长任务，
    # 让每个 worker 一次只处理一个任务可以均匀分配负载
    worker_prefetch_multiplier=1,
)
