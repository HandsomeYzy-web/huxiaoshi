"""模型配置服务层：管理 LLM/Embedding/Rerank 模型配置的 CRUD、激活切换、缓存失效、知识库向量重建等。"""

from sqlalchemy.orm import Session

from core.connection_password_cipher import secret_cipher
from core.exceptions import ResourceNotFoundError, DuplicateResourceError, BusinessError
from core.logger import logger
from models.entities.model_config import ModelConfig
from models.schemas.model_schema import (
    ModelConfigCreate,
    ModelConfigResponse,
    ModelConfigUpdate,
    SUPPORTED_MODEL_TYPES,
    SUPPORTED_PROVIDERS,
)
from repositories.model_config_repo import ModelConfigRepo


def _mask_api_key(key: str) -> str:
    """脱敏 API Key，只显示前4位和后4位。"""
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


def _to_response(config: ModelConfig) -> ModelConfigResponse:
    return ModelConfigResponse(
        id=config.id,
        model_type=config.model_type,
        provider=config.provider,
        name=config.name,
        model_name=config.model_name,
        api_base_url=config.api_base_url,
        # 库里存的是密文，先解密再打码（兼容历史明文行：无前缀时原样返回）
        api_key_masked=_mask_api_key(secret_cipher.decrypt(config.api_key)),
        is_active=config.is_active,
        extra_params=config.extra_params,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


class ModelConfigService:
    """模型配置管理业务层"""

    def list_configs(self, db: Session, model_type: str | None = None) -> list[ModelConfigResponse]:
        repo = ModelConfigRepo(db)
        if model_type:
            configs = repo.list_by_type(model_type)
        else:
            configs = repo.list_all()
        return [_to_response(c) for c in configs]

    def get_config(self, db: Session, config_id: int) -> ModelConfigResponse:
        repo = ModelConfigRepo(db)
        config = repo.get_by_id(config_id)
        if not config:
            raise ResourceNotFoundError(f"模型配置 ID={config_id} 不存在")
        return _to_response(config)
    def create_config(self, db: Session, req: ModelConfigCreate) -> ModelConfigResponse:
        if req.model_type not in SUPPORTED_MODEL_TYPES:
            raise BusinessError(f"不支持的模型类型: {req.model_type}，支持: {SUPPORTED_MODEL_TYPES}")

        repo = ModelConfigRepo(db)
        config = ModelConfig(
            model_type=req.model_type,
            provider=req.provider,
            name=req.name,
            model_name=req.model_name,
            api_base_url=req.api_base_url,
            api_key=secret_cipher.encrypt(req.api_key),  # 密钥加密落库
            is_active=False,
            extra_params=req.extra_params,
        )

        created = repo.create(config)
        logger.info(f"Created model config: {created.name} ({created.model_type})")
        return _to_response(created)
    def update_config(self, db: Session, config_id: int, req: ModelConfigUpdate) -> ModelConfigResponse:
        repo = ModelConfigRepo(db)
        config = repo.get_by_id(config_id)
        if not config:
            raise ResourceNotFoundError(f"模型配置 ID={config_id} 不存在")

        update_data = req.model_dump(exclude_unset=True)
        # API Key 处理：前端只拿得到脱敏值（含 ****），回传脱敏占位或空值时视为「不修改」，
        # 仅当传入了真正的新明文 key 时才加密覆盖，避免把打码串当成新 key 写坏。
        if "api_key" in update_data:
            new_key = (update_data["api_key"] or "").strip()
            if not new_key or "****" in new_key:
                update_data.pop("api_key")
            else:
                update_data["api_key"] = secret_cipher.encrypt(new_key)

        updated = repo.update(config_id, update_data)

        if config.is_active:
            self._invalidate_service_cache(config.model_type)

        return _to_response(updated)

    def activate_config(self, db: Session, config_id: int) -> dict:
        """
        激活指定模型配置。
        返回 { config: ModelConfigResponse, warning: str|None, needs_rebuild: bool }
        """
        repo = ModelConfigRepo(db)

        # 记录旧的激活配置（用于判断 embedding 是否真正切换）
        target = repo.get_by_id(config_id)
        if not target:
            raise ResourceNotFoundError(f"模型配置 ID={config_id} 不存在")

        old_active = repo.get_active(target.model_type)
        embedding_changed = (
            target.model_type == "embedding"
            and (old_active is None or old_active.id != config_id)
        )

        activated = repo.activate(config_id)

        # 外部服务需要重建连接（清除缓存）
        self._invalidate_service_cache(activated.model_type)

        warning = None
        needs_rebuild = False
        if embedding_changed:
            warning = (
                "Embedding 模型已切换，所有知识库的向量数据需要重建才能正常使用。"
                "请前往管理面板执行「重建所有知识库」操作。"
            )
            needs_rebuild = True
            logger.warning(
                f"Embedding model changed: "
                f"{old_active.model_name if old_active else 'None'} → {activated.model_name}"
            )

        return {
            "config": _to_response(activated),
            "warning": warning,
            "needs_rebuild": needs_rebuild,
        }

    def delete_config(self, db: Session, config_id: int) -> None:
        repo = ModelConfigRepo(db)
        config = repo.get_by_id(config_id)
        if not config:
            raise ResourceNotFoundError(f"模型配置 ID={config_id} 不存在")
        if config.is_active:
            raise BusinessError("不能删除当前激活的模型配置，请先激活其他模型")
        repo.delete(config_id)
        logger.info(f"Deleted model config: {config.name} (ID={config_id})")

    def get_active_config(self, db: Session, model_type: str) -> ModelConfig | None:
        """获取当前激活的模型配置实体（供其他 service 调用）。"""
        return ModelConfigRepo(db).get_active(model_type)

    def get_providers_info(self) -> list[dict]:
        """返回支持的供应商信息。"""
        providers = [
            {"provider": "openai", "display_name": "OpenAI", "supported_types": ["llm", "embedding"]},
            {"provider": "dashscope", "display_name": "阿里云通义", "supported_types": ["llm", "embedding", "rerank"]},
            {"provider": "zhipu", "display_name": "智谱AI", "supported_types": ["llm", "embedding"]},
            {"provider": "baichuan", "display_name": "百川AI", "supported_types": ["llm", "embedding"]},
            {"provider": "moonshot", "display_name": "月之暗面 Kimi", "supported_types": ["llm"]},
            {"provider": "deepseek", "display_name": "DeepSeek", "supported_types": ["llm"]},
            {"provider": "ollama", "display_name": "Ollama 本地", "supported_types": ["llm", "embedding"]},
            {"provider": "azure_openai", "display_name": "Azure OpenAI", "supported_types": ["llm", "embedding"]},
            {"provider": "anthropic", "display_name": "Anthropic Claude", "supported_types": ["llm"]},
            {"provider": "cohere", "display_name": "Cohere", "supported_types": ["llm", "embedding", "rerank"]},
            {"provider": "jina", "display_name": "Jina AI", "supported_types": ["embedding", "rerank"]},
            {"provider": "local", "display_name": "本地部署", "supported_types": ["llm", "embedding", "rerank"]},
            {"provider": "custom", "display_name": "自定义 OpenAI 兼容", "supported_types": ["llm", "embedding", "rerank"]},
        ]
        return providers

    @staticmethod
    def _invalidate_service_cache(model_type: str):
        """清除对应服务的缓存实例，使其在下次调用时重新初始化（线程安全）。"""
        if model_type == "llm":
            from services.llm_service import llm_service
            with llm_service._lock:
                llm_service._model = None
                llm_service._streaming_model = None
                llm_service._resolved_model_name = None
            from services.text2sql_service import text2sql_service
            text2sql_service._model = None
        elif model_type == "embedding":
            from services.embeddings import reset_embeddings
            reset_embeddings()
        elif model_type == "rerank":
            pass  # Reranker 每次调用时重新解析配置
    
    # 保证操作的原子性
    @staticmethod
    def rebuild_all_knowledge_bases(db: Session) -> dict:
        """
        重建所有知识库的向量数据（Embedding 模型切换后调用）。
        流程：
        1. 删除每个 KB 的 Elasticsearch index
        2. 将所有已完成文件重置为「处理中」
        3. 为每个文件提交 reprocess 异步任务
        Returns: { total_kbs, total_files }
        """
        from repositories.kb_repo import KBRepo
        from repositories.file_repo import FileRepo
        from repositories.elasticsearch_repo import es_repo
        from tasks.document_tasks import reprocess_document_task

        kb_repo = KBRepo(db)
        file_repo = FileRepo(db)
        all_kbs = kb_repo.get_all_kbs()

        total_files = 0
        for kb in all_kbs:
            # Drop existing Elasticsearch index (will be recreated with new dim)
            try:
                es_repo.delete_chunks_by_kb_id(kb.id)
            except Exception as e:
                logger.warning(f"Failed to drop Elasticsearch index for kb_id={kb.id}: {e}")

            # Get all successfully processed files in this KB
            files = file_repo.get_files_by_kb(kb.id)
            for f in files:
                if f.status == 2:  # status=2 means completed
                    # Reset to pending
                    file_repo.update_file_status(f.id, status=0)
                    reprocess_document_task.delay(f.id)
                    total_files += 1

        logger.info(f"Rebuild triggered: {len(all_kbs)} KBs, {total_files} files queued")
        return {"total_kbs": len(all_kbs), "total_files": total_files}


model_config_service = ModelConfigService()
