"""
Point d'entrée principal de l'application Eloquence Backend.
"""

import logging
import os
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse

# Importer les routeurs
from app.routes.session import router as session_router
from app.routes.audio import router as audio_router
from app.routes.chat import router as chat_router
from app.routes.coaching import router as coaching_router
from app.routes.monitoring import router as monitoring_router

from core.config import settings
from core.database import init_db

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)

logger = logging.getLogger(__name__)

# Initialisation de l'application
app = FastAPI(
    title="Eloquence Backend API",
    description="API pour le système de coaching vocal Eloquence",
    version="1.0.0",
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclure les routeurs
app.include_router(session_router, prefix="/api")
app.include_router(audio_router, prefix="/api")
app.include_router(chat_router, prefix="/chat")
app.include_router(coaching_router, prefix="/coaching")
app.include_router(monitoring_router, prefix="/api")

# Servir les fichiers statiques
app.mount("/audio", StaticFiles(directory=settings.AUDIO_STORAGE_PATH), name="audio")

# Événements de démarrage et d'arrêt
@app.on_event("startup")
async def startup_event():
    """
    Événement exécuté au démarrage de l'application.
    """
    if settings.IS_TESTING:
        logger.info("Démarrage de l'application Eloquence Backend en mode test")
    else:
        logger.info("Démarrage de l'application Eloquence Backend en mode production")
    
    # Créer les répertoires de stockage s'ils n'existent pas
    os.makedirs(settings.AUDIO_STORAGE_PATH, exist_ok=True)
    os.makedirs(settings.FEEDBACK_STORAGE_PATH, exist_ok=True)
    os.makedirs(settings.MODEL_STORAGE_PATH, exist_ok=True)
    os.makedirs(settings.LOG_DIR, exist_ok=True)
    
    # Initialiser la base de données
    try:
        await init_db()
        logger.info("Base de données initialisée avec succès")
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation de la base de données: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """
    Événement exécuté à l'arrêt de l'application.
    """
    logger.info("Arrêt de l'application Eloquence Backend")

# Route de santé
@app.get("/health")
async def health_check():
    """
    Vérifie l'état de santé de l'application.
    """
    return {
        "status": "ok",
        "version": "1.0.0",
        "mode": "test" if settings.IS_TESTING else "production"
    }

# Route racine
@app.get("/")
async def root():
    """
    Route racine de l'API.
    """
    html_content = """
    <html>
        <head>
            <title>Eloquence Backend API</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    line-height: 1.6;
                }
                h1 {
                    color: #4CAF50;
                }
                .info {
                    background-color: #e7f3fe;
                    color: #0c5460;
                    padding: 10px;
                    border-radius: 5px;
                    margin: 20px 0;
                }
                .endpoints {
                    background-color: #f8f9fa;
                    padding: 15px;
                    border-radius: 5px;
                }
            </style>
        </head>
        <body>
            <h1>Eloquence Backend API</h1>
            <p>Bienvenue sur l'API Eloquence pour le coaching vocal.</p>
            
            <div class="info">
                <strong>Mode:</strong> """ + ("Test (SQLite)" if settings.IS_TESTING else "Production (Supabase)") + """
            </div>
            
            <div class="endpoints">
                <h3>Endpoints disponibles:</h3>
                <ul>
                    <li><a href="/health">/health</a> - Vérification de l'état du serveur</li>
                    <li><a href="/docs">/docs</a> - Documentation API</li>
                    <li><a href="/api/session/start">/api/session/start</a> - Démarrer une session</li>
                    <li><a href="/api/session/{session_id}/feedback">/api/session/{session_id}/feedback</a> - Obtenir le feedback d'une session</li>
                    <li><a href="/api/tts">/api/tts</a> - Synthèse vocale</li>
                    <li><a href="/api/stt">/api/stt</a> - Reconnaissance vocale</li>
                    <li><a href="/chat/">/chat/</a> - Chat avec l'assistant</li>
                    <li><a href="/coaching/exercise/generate">/coaching/exercise/generate</a> - Générer un exercice</li>
                </ul>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

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
        reload=True
    )
