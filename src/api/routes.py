from fastapi import APIRouter
from src.api.routers import core, config_routes, balance, analysis, script

router = APIRouter(prefix="/api")

# Include sub-routers
router.include_router(core.router)
router.include_router(config_routes.router)
router.include_router(balance.router)
router.include_router(analysis.router)
router.include_router(script.router)
