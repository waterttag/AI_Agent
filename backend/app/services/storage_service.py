"""
对象存储服务层 (Object Storage Service — S3-Compatible)
========================================================
WHAT: 封装文件上传/删除/URL 生成逻辑，支持阿里云 OSS、AWS S3、MinIO、Cloudflare R2。
WHY:  将存储操作与业务逻辑分离，方便切换存储提供商。
      使用 S3 兼容协议（de facto 标准），几乎所有对象存储服务都支持。

S3 兼容存储术语:
    - Bucket (桶):    存储的最顶层容器，类似于"根目录"
    - Key (键):       对象在 bucket 中的路径，如 "games/123/assets/abc.png"
    - Object (对象):  具体的文件，由 bucket + key 唯一标识
    - Endpoint (端点): S3 API 的访问地址，如 "oss-cn-hangzhou.aliyuncs.com"
    - ACL:            访问控制列表，"public-read" 表示公开可读

URL 风格 (Addressing Style):
    1. Virtual-Hosted Style (虚拟主机风格):
       格式: https://{bucket}.{endpoint}/{key}
       示例: https://my-bucket.oss-cn-hangzhou.aliyuncs.com/games/123/thumb.png
       使用方: 阿里云 OSS、AWS S3（推荐方式）
       原理: bucket 名称作为 DNS 子域名，需 SSL 证书支持通配符

    2. Path Style (路径风格):
       格式: https://{endpoint}/{bucket}/{key}
       示例: https://localhost:9000/my-bucket/games/123/thumb.png
       使用方: MinIO、本地开发环境
       原理: bucket 信息在 URL 路径中，不需要 DNS 配置

    本项目自动检测 endpoint 域名来判断使用哪种风格（见 s3_client.py）
"""

import uuid
from io import BytesIO     # 内存中的二进制流，用于将文件内容传给 boto3

from fastapi import UploadFile

from app.config import settings
from app.utils.s3_client import get_s3_client


# ============================================================================
# _build_public_url — 构建公网访问 URL
# ============================================================================
def _build_public_url(oss_key: str) -> str:
    """
    根据对象存储的配置生成公开访问 URL。

    内部逻辑（与 s3_client.py 的 addressing_style 检测保持一致）:
        1. 检测 endpoint 是否包含 "aliyuncs.com"（阿里云 OSS）或 "amazonaws.com"（AWS S3）
           → 使用 Virtual-Hosted Style: https://{bucket}.{endpoint}/{key}
        2. 否则（MinIO / 本地 / Cloudflare R2 等）
           → 使用 Path Style: https://{endpoint}/{bucket}/{key}

    scheme 选择:
        - minio_secure=true  → https（生产环境）
        - minio_secure=false → http（本地开发，MinIO 默认 9000 端口）

    为什么不直接用 boto3 的 generate_presigned_url？
        - presigned URL 有过期时间，不适合作为持久化的"游戏封面 URL"
        - 我们文件的 ACL 是 public-read，直接拼接公网 URL 即可
        - 省去每次请求都生成签名 URL 的计算开销
    """
    bucket = settings.minio_bucket
    endpoint = settings.minio_endpoint
    scheme = "https" if settings.minio_secure else "http"

    # 阿里云 OSS / AWS S3: virtual-hosted style
    # URL 格式: https://{bucket}.{endpoint}/{oss_key}
    if "aliyuncs.com" in endpoint or "amazonaws.com" in endpoint:
        return f"{scheme}://{bucket}.{endpoint}/{oss_key}"

    # MinIO / 本地 / 其他: path style
    # URL 格式: https://{endpoint}/{bucket}/{oss_key}
    return f"{scheme}://{endpoint}/{bucket}/{oss_key}"


# ============================================================================
# upload_file — 上传文件到对象存储
# ============================================================================
async def upload_file(file: UploadFile, game_id: str, folder: str = "assets") -> tuple[str, str]:
    """
    上传文件到对象存储。返回 (oss_key, oss_url) 元组。

    参数:
        file:    FastAPI 的 UploadFile 对象（来自 multipart/form-data 请求）
        game_id: 游戏 ID，用于构建存储路径
        folder:  子目录名，默认为 "assets"

    存储路径结构:
        games/{game_id}/{folder}/{uuid}.{ext}
        例如: games/abc-123/assets/a1b2c3d4.png

    为什么不直接用原始文件名？
        1. 安全性: 原始文件名可能包含特殊字符、路径穿越（../ 等）
        2. 唯一性: 不同用户可能上传同名文件
        3. UUID 保证全局唯一: uuid4 的碰撞概率极低（2^122 空间）
        4. 保留扩展名: 便于识别文件类型和浏览器正确渲染

    ContentType 的重要性:
        - boto3 的 ContentType 参数告诉 S3 存储 Content-Type 元数据
        - 浏览器访问文件时，S3 返回此 Content-Type
        - 正确设置才能让浏览器:
          - 渲染图片（Content-Type: image/png）
          - 播放音频（Content-Type: audio/mpeg）
          - 下载文件（Content-Type: application/octet-stream）
        - 如果缺失或不正确，可能导致浏览器行为异常

    ACL="public-read":
        - 文件公开可读（任何人可访问 URL）
        - 适合 CDN 和前端直接引用
        - 不需要签名 URL
        - 安全考虑: 只有游戏资源（非用户隐私数据）才适合 public-read
    """
    client = get_s3_client()
    bucket = settings.minio_bucket

    # ---- 生成唯一文件名 ----
    # split(".")[-1]: 取最后一个点后面的内容作为扩展名
    # 例如: "screenshot.final.png" → ext = "png"
    # 如果文件名没有扩展名 → ext = "bin"（通用二进制）
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "bin"

    # uuid4(): 生成随机的 UUID（如 a1b2c3d4-e5f6-7890-abcd-ef1234567890）
    unique_name = f"{uuid.uuid4()}.{ext}"

    # OSS key = 对象存储中的完整路径
    oss_key = f"games/{game_id}/{folder}/{unique_name}"

    # ---- 读取文件内容 ----
    # UploadFile.read() 是异步方法，返回 bytes
    # 注意: 大文件应分片上传（multipart upload），这里假设文件较小（< 10MB）
    content = await file.read()

    # 如果客户端没传 Content-Type，用通用二进制类型
    content_type = file.content_type or "application/octet-stream"

    # ---- 执行上传 ----
    # BytesIO(content): 将 bytes 包装为类文件对象（file-like object）
    # boto3 put_object 接受类文件对象作为 Body 参数
    client.put_object(
        Bucket=bucket,
        Key=oss_key,
        Body=BytesIO(content),
        ContentType=content_type,
        ACL="public-read",
    )

    # ---- 生成访问 URL ----
    oss_url = _build_public_url(oss_key)

    return oss_key, oss_url


# ============================================================================
# upload_html — 上传生成的游戏 HTML
# ============================================================================
async def upload_html(game_id: str, html_content: str) -> str:
    """
    上传生成的游戏 HTML 文件到对象存储。返回公开访问 URL。

    特殊处理:
        - 固定文件名为 index.html（一个游戏一个 HTML）
        - ContentType 设为 "text/html"（浏览器直接渲染）
        - ContentDisposition="inline": 告诉浏览器"直接显示内容，不要弹下载框"

    ContentDisposition 详解:
        有两个值:
          - "inline": 浏览器在窗口中直接显示内容（如图片、HTML）
                      对应 HTTP 响应头: Content-Disposition: inline
          - "attachment": 浏览器弹出"保存为..."对话框
                          对应 HTTP 响应头: Content-Disposition: attachment; filename="xxx.html"

        为什么 HTML 用 inline？
          - 游戏需要在 iframe 中直接渲染
          - 如果用 attachment，浏览器会尝试下载文件而非显示
          - S3/MinIO 存储此元数据后，访问 URL 时会自动带上对应的 Content-Disposition 头

    注意: 本项目中 upload_html 可能不被主流程使用，
         因为 play-html 端点直接从数据库的 llm_response_raw 返回 HTML，
         不依赖 OSS。但保留此函数以备将来需要 OSS 托管 HTML 的场景。
    """
    client = get_s3_client()
    bucket = settings.minio_bucket

    # 固定路径: games/{game_id}/index.html
    oss_key = f"games/{game_id}/index.html"
    data = html_content.encode("utf-8")  # 字符串 → UTF-8 字节

    client.put_object(
        Bucket=bucket,
        Key=oss_key,
        Body=BytesIO(data),
        ContentType="text/html",
        ContentDisposition="inline",  # 浏览器直接渲染，不弹下载框
        ACL="public-read",
    )

    return _build_public_url(oss_key)


# ============================================================================
# delete_file — 删除文件
# ============================================================================
async def delete_file(oss_key: str) -> None:
    """
    从对象存储中删除指定 key 的文件。

    注意: S3 的删除是幂等的 — 删除不存在的 key 不会报错。
         目前主流程（games.py 的 delete_asset）没有调用此函数，
         意味着删除资源时 OSS 上会留下"孤儿文件"。
         这是有意为之还是未实现取决于具体需求:
         - 保留文件更安全（防止误删后无法恢复）
         - 删除文件更节省存储空间
    """
    client = get_s3_client()
    client.delete_object(Bucket=settings.minio_bucket, Key=oss_key)
