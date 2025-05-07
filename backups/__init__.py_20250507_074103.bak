# Package routes pour l'application Eloquence
# Ce fichier permet d'importer les routes comme des modules Python

from fastapi import APIRouter

from app.routes.websocket import router as websocket_router
from app.routes.session import router as session_router
from app.routes.audio import router as audio_router
from app.routes.monitoring import router as monitoring_router
from app.routes.tts_cache import router as tts_cache_router

# Router principal qui regroupe tous les sous-routers
api_router = APIRouter()

# Inclure les différents routers avec leurs préfixes
api_router.include_router(session_router, prefix="/api", tags=["session"])
api_router.include_router(websocket_router, tags=["websocket"])
api_router.include_router(audio_router, prefix="/api", tags=["audio"])
api_router.include_router(monitoring_router, prefix="/api", tags=["monitoring"])
api_router.include_router(tts_cache_router, prefix="/api", tags=["tts-cache"])