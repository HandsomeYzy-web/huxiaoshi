from fastapi import APIRouter

from api.routers.admin_kb_access_router import router as kb_access_router
from api.routers.admin_model_router import router as model_router
from api.routers.admin_permission_router import router as permission_router
from api.routers.admin_role_router import router as role_router
from api.routers.admin_user_router import router as user_router

router = APIRouter(prefix="/admin", tags=["Admin"])
router.include_router(permission_router)
router.include_router(role_router)
router.include_router(user_router)
router.include_router(kb_access_router)
router.include_router(model_router)
