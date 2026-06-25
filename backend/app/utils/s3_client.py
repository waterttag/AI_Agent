"""
S3 兼容对象存储客户端 (S3-Compatible Object Storage Client)
=============================================================
WHAT: 提供 boto3 S3 客户端的单例工厂和 addressing style 自动检测逻辑。
WHY:  集中管理 S3 客户端配置，避免在多个 service 中重复创建。
      支持阿里云 OSS、AWS S3、MinIO、Cloudflare R2 等所有 S3 兼容存储。

boto3 简介:
    boto3 是 AWS 官方的 Python SDK，用于和 AWS 服务交互。
    虽然名叫"AWS SDK"，但通过指定 endpoint_url 参数可以连接到任何 S3 兼容存储。
    S3 协议已成为对象存储的事实标准（类似于 Kubernetes 之于容器编排）。

addressing_style 检测逻辑详解:
    ============================================================
    问题: 不同 S3 兼容存储使用不同的 URL 风格来访问对象。

    Virtual-Hosted Style (虚拟主机风格):
        URL: https://{bucket}.{endpoint}/{key}
        工作原理: bucket 名称作为 DNS 子域名
        优点:     支持 SSL 证书、可做 CDN 加速
        使用方:   阿里云 OSS、AWS S3（2020 年后的默认）
        检测方法:  endpoint 包含 "aliyuncs.com" 或 "amazonaws.com"

    Path Style (路径风格):
        URL: https://{endpoint}/{bucket}/{key}
        工作原理: bucket 信息在 URL 路径中
        优点:     不需要 DNS 配置，任何 endpoint 都能工作
        使用方:   MinIO、本地开发 S3 模拟器
        检测方法:  其他所有 endpoint（非 OSS/非 AWS）

    boto3 配置中如何指定?
        boto3 的 addressing_style 参数在 botocore Config 中配置:
        s3={"addressing_style": "virtual"}  → 使用虚拟主机风格
        s3={"addressing_style": "path"}     → 使用路径风格
        如果设置错误:
          - MinIO 上使用 "virtual" → DNS 解析失败（MinIO 没有为 bucket 配置 DNS）
          - OSS 上使用 "path"     → 可能遇到兼容性问题（OSS 推荐 virtual）
    ============================================================

region_name 说明:
    - 阿里云 OSS: region 格式为 "oss-cn-hangzhou"（根据实际 region 填写）
    - AWS S3:     如 "us-east-1"、"ap-southeast-1"
    - MinIO:      任意值即可，MinIO 不依赖 region 路由（设为 "us-east-1" 作为默认）
    - 为什么需要 region 参数? boto3 使用 region 来构建签名和选择 API endpoint，
      即使我们指定了 endpoint_url，某些验证逻辑仍需要 region
"""

import boto3
from botocore.config import Config as BotoConfig  # 用于配置 S3 客户端的低级选项
from botocore.exceptions import ClientError       # boto3 客户端异常基类

from app.config import settings


# ============================================================================
# get_s3_endpoint_url — 构建完整的 S3 endpoint URL
# ============================================================================
def get_s3_endpoint_url() -> str:
    """
    从配置中构建完整的 S3 endpoint URL。

    为什么独立为函数?
        - 两处使用: get_s3_client() 和 _build_public_url()（在 storage_service.py 中）
        - 确保 URL 格式一致性（scheme + "://" + endpoint）
        - 单点维护: 如果 URL 格式需要调整，只改一处

    scheme 选择:
        - minio_secure=true  → https (443 端口)
        - minio_secure=false → http  (80 端口)
        MinIO 默认在 9000 端口（HTTP）和 9001 端口（Web Console），
        使用 HTTP 进行本地开发。
    """
    scheme = "https" if settings.minio_secure else "http"
    return f"{scheme}://{settings.minio_endpoint}"


# ============================================================================
# get_s3_client — 获取 boto3 S3 客户端（单例模式）
# ============================================================================
def get_s3_client():
    """
    创建并返回一个配置好的 boto3 S3 客户端。

    设计决策:
        - 每次调用都创建新客户端（而非全局单例）的原因:
          1. boto3 client 是轻量级的（连接池是 session 级别管理的）
          2. 避免全局状态：模块加载时配置可能还没就绪
          3. 线程安全：每个线程/请求使用独立的 client 实例
          4. 如果配置变化（极少见但可能），不需要重启应用

        如果追求极致性能，可以用 session 级别管理:
          session = boto3.Session()
          client = session.client("s3", ...)
          但当前场景下差异可忽略。

    addressing_style 自动检测逻辑:
        1. 检查 settings.minio_endpoint 是否包含 "aliyuncs.com"
           → 是: 阿里云 OSS，使用 virtual-hosted style
           → 否: 继续检查
        2. Amazon S3 默认使用 virtual-hosted style
           → 但本项目的检测逻辑基于域名关键词匹配
           → 非 OSS 非 AWS 的 endpoint 使用 path style（MinIO 等）

    签名版本:
        signature_version="s3v4": 使用 AWS Signature Version 4
        - v4 是当前最新版本（2014 年推出）
        - 几乎所有 S3 兼容存储都支持 v4（包括 MinIO、OSS、R2）
        - v2 已过时，不支持某些新 region
    """
    endpoint_url = get_s3_endpoint_url()

    # ---- addressing_style 自动检测 ----
    # 判断是否为阿里云 OSS（域名包含 aliyuncs.com）
    # 阿里云 OSS 需要 virtual-hosted style:
    #   https://my-bucket.oss-cn-hangzhou.aliyuncs.com/object-key
    # 注意: 这里只判断了 OSS，AWS S3 的判断逻辑类似（通过 amazonaws.com），
    #       但在当前 config 检测中未显式处理 — 如果将来用 AWS S3，
    #       需要在 is_oss 判断中加入 "amazonaws.com" 或在 config 中加 s3_addressing_style 配置项
    is_oss = "aliyuncs.com" in settings.minio_endpoint

    return boto3.client(
        "s3",                                     # 服务名: s3 (Simple Storage Service)
        endpoint_url=endpoint_url,                # 自定义 endpoint（非 AWS 时必须指定）
        aws_access_key_id=settings.minio_access_key,      # Access Key
        aws_secret_access_key=settings.minio_secret_key,   # Secret Key

        config=BotoConfig(
            # 签名版本: s3v4（AWS Signature Version 4）
            # v4 vs v2: v4 使用 HMAC-SHA256，安全性更高，支持新 region
            signature_version="s3v4",

            # addressing_style 决定 URL 格式:
            # "virtual" = https://{bucket}.{endpoint}/{key}  （OSS/S3）
            # "path"    = https://{endpoint}/{bucket}/{key}   （MinIO/其他）
            s3={"addressing_style": "virtual" if is_oss else "path"},
        ),

        # region_name: OSS 使用 "oss-cn-hangzhou"，其他使用 "us-east-1"
        # "us-east-1" 是 AWS 的默认 region，MinIO 不检查此值，所以填任意合法 region 即可
        region_name="oss-cn-hangzhou" if is_oss else "us-east-1",
    )


# ============================================================================
# ensure_bucket — 确保 bucket 存在（应用启动时调用）
# ============================================================================
def ensure_bucket() -> None:
    """
    检查配置的 bucket 是否存在，不存在则创建并设置公开读策略。

    调用时机: 应用启动时（main.py 或 lifespan handler）

    策略说明:
        head_bucket: 检查 bucket 是否存在（HEAD 请求，轻量级）
        create_bucket: 创建 bucket（MinIO 不需要指定 region，OSS/S3 可能需要）
        put_bucket_policy: 设置 bucket 策略为公开读
          - 只对 games/* 路径公开读（而非整个 bucket）
          - Effect: Allow — 允许操作
          - Principal: * — 任何人
          - Action: s3:GetObject — 只读（不能写入、删除、列目录）
          - Resource: arn:aws:s3:::{bucket}/games/* — 只针对 games 目录
          - 这是一个最小权限的公开读策略

    为什么不直接用 ACL="public-read" 在每个 put_object 调用中？
        - put_object 的 ACL 是针对单个对象的
        - bucket policy 是全局的，新对象自动继承
        - 双重保障: 有 bucket policy + put_object ACL 更安全
    """
    client = get_s3_client()
    bucket = settings.minio_bucket

    try:
        # 检查 bucket 是否存在
        client.head_bucket(Bucket=bucket)
    except ClientError:
        # bucket 不存在 → 创建
        client.create_bucket(Bucket=bucket)

        # 设置公开读策略 — 允许任何人读取 games/ 下的文件
        # 策略格式: IAM Policy JSON (AWS 风格的访问控制声明)
        client.put_bucket_policy(
            Bucket=bucket,
            Policy=(
                '{"Version":"2012-10-17",'
                '"Statement":[{'
                '"Effect":"Allow",'
                '"Principal":"*",'
                '"Action":["s3:GetObject"],'
                '"Resource":["arn:aws:s3:::' + bucket + '/games/*"]'
                '}]}'
            ),
        )
