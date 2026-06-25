"""
=============================================================================
游戏打包器 (Game Packager — 将生成的 HTML 上传到 MinIO OSS)
=============================================================================

打包器是游戏生成流水线的最后一步，负责持久化存储和生成可访问的 URL。

【职责边界】
  打包器只关心"存储"—— 它不验证 HTML 是否有效（validator 已做），
  不关心游戏逻辑是否正确。这种职责分离让流水线各阶段独立可测。

——————————————————————————————————————————————————————————————
【Content-Disposition: inline vs attachment 的关键决策】
——————————————————————————————————————————————————————————————

  一个看似微小的 HTTP 响应头决定直接影响用户体验：

  ┌───────────────────────────────────────────────────────────┐
  │ Content-Disposition: inline                               │
  │                                                           │
  │   浏览器行为：直接在浏览器中打开/渲染文件                    │
  │   对 HTML 文件：浏览器加载并渲染页面                        │
  │   优点：用户无需下载即可游玩，iframe 嵌入零配置              │
  │   缺点：无（对于游戏 HTML 文件而言）                        │
  │   使用场景：本项目的游戏 HTML —— 需要直接在 iframe 中      │
  │            渲染并运行                                      │
  └───────────────────────────────────────────────────────────┘

  ┌───────────────────────────────────────────────────────────┐
  │ Content-Disposition: attachment                           │
  │                                                           │
  │   浏览器行为：触发下载对话框，保存到本地磁盘                 │
  │   对 HTML 文件：下载为 .html 文件而非渲染                   │
  │   优点：用户获得文件的控制权（保存、分享、离线使用）          │
  │   缺点：iframe 加载时也会触发下载而非渲染 —— 游戏无法运行   │
  │   使用场景：文件分享/下载服务，不适合需要即时渲染的内容       │
  └───────────────────────────────────────────────────────────┘

  【本项目的问题与解决方案】

    MinIO 默认使用 attachment 作为文件上传的 Content-Disposition。
    这意味着通过 MinIO 直链访问 games/{id}/index.html 时，
    浏览器会下载文件而不是渲染它。游戏的 iframe 嵌入体验彻底崩溃。

    解决方案（在 harness.py 的 _finalize() 中实现）：
      不直接使用 MinIO URL 作为游戏访问地址，而是将其存储为备用，
      同时设置 game.game_url = "/api/games/{game_id}/play-html"。
      这个 API 端点通过 FastAPI 直接返回 HTML 内容，可以显式设置
      Content-Disposition: inline 响应头，确保 iframe 正常渲染。

    这解释了 packager.py 中看似简单的逻辑 —— 上传本身很简单，
    但"如何提供 URL"的策略是在 harness.py 层面决定的。
    打包器的职责是"把文件放到 MinIO"；harness 的职责是"决定用哪个 URL"。

  【扩展：为什么不在 MinIO 端设置 inline？】
    MinIO 支持通过 x-amz-meta-* 自定义元数据和 Content-Type 设置，
    但 Content-Disposition 的预设需要在 bucket policy 或
    预签名 URL 中配置。对于按需设置不同 disposition 的场景，
    通过 API 端点代理是更灵活的方案。

    MinIO 上传时的元数据设置：
      extra_args={"ContentType": "text/html", "ContentDisposition": "inline"}
    但并非所有 MinIO 部署都支持完整的元数据覆盖，
    使用 API 端点代理是最可靠的跨部署方案。

——————————————————————————————————————————————————————————————
【为何打包器如此精简？—— YAGNI 的实践】
——————————————————————————————————————————————————————————————

  当前打包器只有 35 行代码（包括注释），只有一个方法。
  这看起来似乎"太简单了"—— 但这是刻意的。

  打包器的原始设计包含以下功能（后被移除）：
    1. CDN 脚本内联化（下载 Phaser CDN 的 JS 并 base64 嵌入）
       → 移除原因：Phaser 3 CDN 极其稳定（jsdelivr + Cloudflare），
          内联化增加文件大小 3 倍（base64 膨胀），且使代码更难调试。

    2. 资源 Data URI 注入（将图片/音频转为 base64 data URI）
       → 移除原因：本项目使用程序化美术（Canvas 绘制），不需要外部资源。
          如果将来集成 AI 图片生成，此功能可以重新加入。

    3. ZIP 打包（HTML + assets 整体打包下载）
       → 移除原因：单文件 HTML 已经自包含，ZIP 打包增加了复杂度
          但几乎没有增加价值。用户可以 Ctrl+S 保存 HTML。

    4. 版本管理（保留每次生成的多个版本）
       → 移除原因：数据库层的 Game.revisions 字段已经覆盖了版本历史需求，
          不需要在 OSS 层再维护文件版本。

  这些被移除的功能都有各自的使用场景，但在当前的产品需求下都是
  "可能将来需要"的功能。YAGNI (You Aren't Gonna Need It) 原则告诉我们，
  只实现当前确定需要的功能。简洁的代码更容易理解、测试和维护。
"""

from app.services import storage_service


class GamePackager:
    """
    将生成的 HTML 游戏打包并上传到 MinIO 对象存储。

    【单文件架构的优势】
      游戏是单个 index.html 文件，包含所有 CSS (内联 <style>) 和
      JavaScript (内联 <script>)。这种架构意味着：
        - OSS 路径简洁：games/{game_id}/index.html
        - 无需处理相对资源引用路径
        - 下载/加载只需一次 HTTP 请求（CDN 脚本除外）

    【MinIO 上传路径设计】
      games/{game_id}/index.html 的路径结构设计考量：
        - games/ 前缀：命名空间隔离，区分游戏文件、用户头像等
        - {game_id}/：每个游戏独立目录，未来可扩展（如添加 game.json 元数据文件）
        - index.html：约定优于配置，Web 服务器默认寻找的文件名
          如果用户直接访问 games/{game_id}/，服务器会自动提供 index.html

    【storage_service 的封装】
      storage_service.upload_html() 封装了：
        1. MinIO 客户端初始化（连接池、认证）
        2. 文件上传（Put Object API）
        3. Content-Type 设置（text/html; charset=utf-8）
        4. 公共 URL 生成（如果有配置过公共访问策略）
      这里不直接操作 MinIO SDK 是为了遵循"依赖倒置原则"——
      GamePackager 不关心底层存储是 MinIO、AWS S3、阿里云 OSS 还是本地文件系统。
    """

    async def package_and_upload(
        self,
        game_id: str,
        html_code: str,
    ) -> str:
        """
        上传游戏 HTML 到 MinIO 并返回公共访问 URL。

        【参数】
          game_id:   游戏的 UUID（用于构造 OSS 路径）
          html_code: 完整的 HTML 代码（已经过验证和清理）

        【返回值】
          MinIO OSS 的公共 URL，格式类似：
            https://oss.example.com/games/{game_id}/index.html

          注意：这个 URL 可能因为 MinIO 的 Content-Disposition 设置
          而触发下载而非渲染。harness.py 的 _finalize() 方法会处理这个问题，
          使用 API 端点作为主要访问入口。详见文件头部注释。

        【异步设计】
          upload_html 是 async 方法，因为 MinIO SDK 的 HTTP 操作
          使用异步客户端。在流水线中，这个上传通常耗时 0.5-2 秒。

        【错误处理】
          本方法不捕获异常 —— 异常传播到调用方 (harness.py)，
          由 harness.py 的 try/except 处理。这是一个有意的设计选择：
          本方法不知道如何处理 MinIO 不可用的情况（应该降级到数据库？
          应该重试？），只有更上层的编排者 (harness) 才有足够的上下文
          做正确的决策。详见 harness.py 中的"优雅降级 (OSS→DB fallback)"注释。
        """
        # 上传到 MinIO，路径为 games/{game_id}/index.html
        # storage_service 负责处理 MinIO SDK 的细节
        oss_url = await storage_service.upload_html(game_id, html_code)
        return oss_url
