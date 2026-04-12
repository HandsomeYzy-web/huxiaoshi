"""模型配置仓储层：提供 ModelConfig（模型配置）的数据库增删改查操作，支持同类型模型的激活/停用切换。"""

from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.logger import logger
from models.entities.model_config import ModelConfig


class ModelConfigRepo:
    """ModelConfig 持久化操作。"""

    def __init__(self, db: Session):
        self.db = db

    def create(self, config: ModelConfig) -> ModelConfig:
        self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        return config

    def get_by_id(self, config_id: int) -> Optional[ModelConfig]:
        return self.db.get(ModelConfig, config_id)

    def list_all(self) -> list[ModelConfig]:
        stmt = select(ModelConfig).order_by(ModelConfig.model_type, ModelConfig.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def list_by_type(self, model_type: str) -> list[ModelConfig]:
        stmt = (
            select(ModelConfig)
            .where(ModelConfig.model_type == model_type)
            .order_by(ModelConfig.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_active(self, model_type: str) -> Optional[ModelConfig]:
        """获取某类型当前激活的模型配置。"""
        stmt = select(ModelConfig).where(
            ModelConfig.model_type == model_type,
            ModelConfig.is_active.is_(True),
        )
        return self.db.scalars(stmt).first()

    def update(self, config_id: int, update_data: dict) -> Optional[ModelConfig]:
        config = self.get_by_id(config_id)
        if not config:
            return None
        for field, value in update_data.items():
            if hasattr(config, field) and value is not None:
                setattr(config, field, value)
        self.db.commit()
        self.db.refresh(config)
        return config

    def activate(self, config_id: int) -> Optional[ModelConfig]:
        """激活指定模型，同时关闭同类型的其他模型。"""
        config = self.get_by_id(config_id)
        if not config:
            return None
        # 先关闭同类型的所有激活
        stmt = (
            update(ModelConfig)
            .where(ModelConfig.model_type == config.model_type, ModelConfig.is_active.is_(True))
            .values(is_active=False)
        )
        self.db.execute(stmt)
        # 激活目标
        config.is_active = True
        self.db.commit()
        self.db.refresh(config)
        logger.info(f"Activated model config: id={config_id}, type={config.model_type}, name={config.name}")
        return config

    def delete(self, config_id: int) -> bool:
        config = self.get_by_id(config_id)
        if not config:
            return False
        self.db.delete(config)
        self.db.commit()
        return True
