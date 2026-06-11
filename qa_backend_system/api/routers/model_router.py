from typing import List

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from core.database import get_db
from core.response import UnifiedResponse, success
from models.schemas.model_schema import (
    ModelActivateResponse,
    ModelConfigCreate,
    ModelConfigResponse,
    ModelConfigUpdate,
    ModelProviderInfo,
)
from services.model_config_service import model_config_service

router = APIRouter(prefix="/models", tags=["Model Config"])


@router.get("", response_model=UnifiedResponse[List[ModelConfigResponse]])
async def list_model_configs(
    model_type: str | None = None,
    db: Session = Depends(get_db),
):
    return success(data=model_config_service.list_configs(db, model_type), message="Fetched model configs")


@router.get("/providers", response_model=UnifiedResponse[List[ModelProviderInfo]])
async def list_model_providers():
    return success(data=model_config_service.get_providers_info(), message="Fetched model providers")


@router.get("/{config_id}", response_model=UnifiedResponse[ModelConfigResponse])
async def get_model_config(
    config_id: int = Path(...),
    db: Session = Depends(get_db),
):
    return success(data=model_config_service.get_config(db, config_id), message="Fetched model config")


@router.post("", response_model=UnifiedResponse[ModelConfigResponse])
async def create_model_config(
    req: ModelConfigCreate,
    db: Session = Depends(get_db),
):
    return success(data=model_config_service.create_config(db, req), message="Model config created")


@router.put("/{config_id}", response_model=UnifiedResponse[ModelConfigResponse])
async def update_model_config(
    req: ModelConfigUpdate,
    config_id: int = Path(...),
    db: Session = Depends(get_db),
):
    return success(data=model_config_service.update_config(db, config_id, req), message="Model config updated")


@router.post("/{config_id}/activate", response_model=UnifiedResponse[ModelActivateResponse])
async def activate_model_config(
    config_id: int = Path(...),
    db: Session = Depends(get_db),
):
    result = model_config_service.activate_config(db, config_id)
    return success(data=result, message=result["warning"] or "Model activated")


@router.delete("/{config_id}", response_model=UnifiedResponse[None])
async def delete_model_config(
    config_id: int = Path(...),
    db: Session = Depends(get_db),
):
    model_config_service.delete_config(db, config_id)
    return success(data=None, message="Model config deleted")


@router.post("/rebuild-all-kbs", response_model=UnifiedResponse[dict])
async def rebuild_all_knowledge_bases(
    db: Session = Depends(get_db),
):
    result = model_config_service.rebuild_all_knowledge_bases(db)
    return success(data=result, message="Rebuild tasks submitted")
