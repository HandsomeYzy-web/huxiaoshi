import io
from minio import Minio
from datetime import timedelta
from core.config import settings
from core.exceptions import ExternalServiceError
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

    def init(self):
        """启动时显式初始化：确保 Bucket 存在。"""
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

    def delete_file(self, object_name: str):
        """从 MinIO 删除一个对象"""
        try:
            self.client.remove_object(self.bucket_name, object_name)
            logger.debug(f"MinIO 文件已删除: {object_name}")
        except Exception as e:
            logger.error(f"MinIO 删除文件失败 [{object_name}]: {e}")
            raise ExternalServiceError(f"对象存储删除失败: {object_name}")

    def delete_files_with_prefix(self, prefix: str):
        """删除指定前缀下的所有对象（用于删除整个知识库目录）"""
        try:
            objects = self.client.list_objects(self.bucket_name, prefix=prefix, recursive=True)
            for obj in objects:
                self.client.remove_object(self.bucket_name, obj.object_name)
            logger.info(f"MinIO 前缀 '{prefix}' 下所有文件已删除")
        except Exception as e:
            logger.error(f"MinIO 批量删除失败 [prefix={prefix}]: {e}")
            raise ExternalServiceError(f"对象存储批量删除失败: {prefix}")

minio_repo = MinioRepo() # 实例化单例