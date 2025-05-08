"""
Point d'entrée principal de l'application Eloquence Backend.
"""

import logging
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routes.chat import router as chat_router
from app.routes.coaching import router as coaching_router
from app.routes.session import router as session_router
from app.routes.audio import router as audio_router
from app.routes.monitoring import router as monitoring_router
from app.routes.scenarios import router as scenarios_router
from core.database import init_db
from core.config import settings

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

logger = logging.getLogger(__name__)

# AJOUT POUR DÉBOGAGE DE VERSION DE FICHIER
try:
    # Utiliser un chemin relatif correct depuis l'emplacement de main.py
    scenarios_file_path = os.path.join(os.path.dirname(__file__), "routes", "scenarios.py")
    if not os.path.exists(scenarios_file_path):
        # Fallback si la structure est app/main.py et app/routes/scenarios.py (courant)
        scenarios_file_path = "app/routes/scenarios.py"
        if not os.path.exists(scenarios_file_path): # Dernier fallback si exécuté depuis la racine du projet
             scenarios_file_path = "eloquence_backend_py/app/routes/scenarios.py"


    if os.path.exists(scenarios_file_path):
        with open(scenarios_file_path, "r", encoding="utf-8") as f_scenarios_check:
            first_line_scenarios = f_scenarios_check.readline().strip()
            logger.warning(f">>>>> CHECK VERSION SCENARIOS.PY AU DÉMARRAGE (depuis {scenarios_file_path}): '{first_line_scenarios}' <<<<<")
    else:
        logger.error(f">>>>> ERREUR CHECK VERSION: Fichier scenarios.py non trouvé aux emplacements testés. Testé: {scenarios_file_path} <<<<<")
except Exception as e_check:
    logger.error(f">>>>> ERREUR LECTURE scenarios.py POUR CHECK VERSION: {e_check} <<<<<")
# FIN AJOUT DÉBOGAGE

# Création de l'application FastAPI
app = FastAPI(
    title="Eloquence Backend",
    description="Backend pour l'application Eloquence de coaching vocal",
    version="1.0.0",
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En production, spécifier les origines autorisées
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Événement de démarrage
@app.on_event("startup")
async def startup_event():
    """
    Événement exécuté au démarrage de l'application.
    """
    logger.info(f"Démarrage de l'application Eloquence Backend en mode DEBUG: {settings.DEBUG}") # Remplacé settings.MODE par settings.DEBUG
    
    # Initialisation de la base de données
    await init_db()
    logger.info("Base de données initialisée avec succès")

# Événement d'arrêt
@app.on_event("shutdown")
async def shutdown_event():
    """
    Événement exécuté à l'arrêt de l'application.
    """
    logger.info("Arrêt de l'application Eloquence Backend")

# Gestionnaire d'exceptions global
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Gestionnaire d'exceptions global pour capturer toutes les exceptions non gérées.
    """
    logger.error(f"Exception non gérée: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Une erreur interne est survenue"},
    )

# Route de base
@app.get("/")
async def root():
    """
    Route de base pour vérifier que l'application fonctionne.
    """
    return {"message": "Bienvenue sur l'API Eloquence Backend"}

# Route de santé
@app.get("/health")
async def health():
    """
    Route de santé pour vérifier que l'application fonctionne correctement.
    """
    return {
        "status": "ok",
        "version": "1.0.0",
        "mode": settings.MODE
    }

# Inclusion des routers
app.include_router(chat_router, prefix="/chat", tags=["chat"])
app.include_router(coaching_router, prefix="/coaching", tags=["coaching"])
app.include_router(session_router, prefix="/api", tags=["session"]) # Rétablir le préfixe /api
# app.include_router(session_router, tags=["session"]) # Supprimer l'inclusion sans préfixe
app.include_router(audio_router, prefix="/api", tags=["audio"])
app.include_router(monitoring_router, prefix="/api", tags=["monitoring"])
app.include_router(scenarios_router, prefix="/api", tags=["scenarios"])
