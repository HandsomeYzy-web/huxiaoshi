import io
from minio import Minio
from datetime import timedelta
from core.config import settings
from core.logger import logger

class MinioRepo:
    """MinIO 对象存储访问层封装"""

    def __init__(self):
        self.client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE
        )
        self.bucket_name = settings.MINIO_BUCKET_NAME
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"✅ MinIO Bucket '{self.bucket_name}' 创建成功")
        except Exception as e:
            logger.error(f"❌ 连接 MinIO 失败: {e}")

    def upload_file_bytes(self, object_name: str, file_data: bytes, content_type: str = "application/octet-stream") -> str:
        """上传字节流到 MinIO"""
        data_stream = io.BytesIO(file_data)
        file_size = len(file_data)
        self.client.put_object(
            bucket_name=self.bucket_name,
            object_name=object_name,
            data=data_stream,
            length=file_size,
            content_type=content_type
        )
        logger.debug(f"文件上传 MinIO 成功: {object_name}")
        return object_name

    def get_file_stream(self, object_name: str):
        """获取文件流，用于后台解析"""
        return self.client.get_object(self.bucket_name, object_name)

    def get_presigned_url(self, object_name: str, expires_hours: int = 2) -> str:
        """生成预签名 URL（主要用于让大模型或前端能够临时访问存在 MinIO 里的图片）"""
        return self.client.get_presigned_url(
            "GET",
            self.bucket_name,
            object_name,
            expires=timedelta(hours=expires_hours)
        )

minio_repo = MinioRepo() # 实例化单例