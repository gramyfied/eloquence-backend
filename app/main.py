"""
Point d'entrée principal de l'application Eloquence Backend.
Configure FastAPI avec les routes, middleware et dépendances nécessaires.
"""

import asyncio
import logging
import os
import sys
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from core.config import settings
from core.database import engine, get_db, AsyncSessionLocal # Importer AsyncSessionLocal
from core.models import Base
from app.routes import api_router
from services.orchestrator import Orchestrator
from app.routes.websocket import get_orchestrator
from services.tts_service_optimized import tts_service_optimized
from services.tts_cache_service import tts_cache_service

# Configuration du logging
# Vérifier si nous sommes en mode test (présence de pytest)
is_test_mode = 'pytest' in sys.modules

# Configurer le logging différemment en mode test
if is_test_mode:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
        ]
    )
    print("Mode test détecté: logging configuré sans fichier")
else:
    # Créer le répertoire de logs si nécessaire
    os.makedirs(settings.LOG_DIR, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.join(settings.LOG_DIR, "eloquence.log"))
        ]
    )

logger = logging.getLogger(__name__)

# Création des tables dans la base de données
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Création des répertoires nécessaires
def create_directories():
    os.makedirs(settings.AUDIO_STORAGE_PATH, exist_ok=True)
    os.makedirs(settings.FEEDBACK_STORAGE_PATH, exist_ok=True)
    os.makedirs(settings.LOG_DIR, exist_ok=True)

# Initialisation de l'application FastAPI
app = FastAPI(
    title="Eloquence Backend API",
    description="API pour le système de coaching vocal Eloquence",
    version="1.0.0",
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montage des fichiers statiques
app.mount("/audio", StaticFiles(directory=settings.AUDIO_STORAGE_PATH), name="audio")

# Inclusion des routes API
app.include_router(api_router)

# Événements de démarrage et d'arrêt
@app.on_event("startup")
async def startup_event():
    """
    Événement exécuté au démarrage de l'application.
    Initialise la base de données, les répertoires et les services.
    """
    logger.info("Démarrage de l'application Eloquence Backend")
    
    # Créer les répertoires nécessaires
    create_directories()
    
    # Créer les tables dans la base de données
    await create_tables()
    
    # Initialiser l'orchestrateur (obtenir une session DB pour l'init)
    if AsyncSessionLocal:
        async with AsyncSessionLocal() as db:
            orchestrator = await get_orchestrator(db) # Passe la session à get_orchestrator
            logger.info("Orchestrateur initialisé")
    else:
        logger.error("Impossible d'initialiser l'Orchestrateur: Session DB non disponible.")
    
    # Initialiser le service TTS optimisé
    logger.info("Initialisation du service TTS optimisé...")
    if settings.TTS_USE_CACHE:
        logger.info(f"Cache TTS activé avec préfixe '{tts_cache_service.cache_prefix}' "
                   f"et expiration de {tts_cache_service.cache_expiration} secondes")
    else:
        logger.warning("Cache TTS désactivé. Activer le cache pour de meilleures performances.")
    
    # Précharger les phrases courantes si configuré
    if settings.TTS_PRELOAD_COMMON_PHRASES:
        logger.info("Préchargement des phrases courantes dans le cache TTS...")
        # Lancer le préchargement en arrière-plan
        asyncio.create_task(
            tts_service_optimized.preload_common_phrases(
                ["Bonjour et bienvenue à Eloquence."],
                "fr"
            )
        )

    logger.info("Application Eloquence Backend démarrée avec succès")

@app.on_event("shutdown")
async def shutdown_event():
    """
    Événement exécuté à l'arrêt de l'application.
    Nettoie les ressources et ferme les connexions.
    """
    logger.info("Arrêt de l'application Eloquence Backend")
    # Fermer les connexions à la base de données, etc.

# Route de santé
@app.get("/health")
async def health_check():
    """
    Vérifie l'état de santé de l'application.
    """
    return {"status": "ok", "version": "1.0.0"}

# Route racine
@app.get("/")
async def root():
    """
    Route racine de l'API.
    """
    return {
        "message": "Bienvenue sur l'API Eloquence",
        "documentation": "/docs",
        "health": "/health"
    }

# Gestionnaire d'exceptions global
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    Gestionnaire d'exceptions global pour l'application.
    """
    logger.error(f"Exception non gérée: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Une erreur interne est survenue"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
