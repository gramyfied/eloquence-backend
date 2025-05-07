
"""
Point d'entrée principal de l'application Eloquence Backend (mode sans base de données).
"""

import logging
import time
import os
import uuid
from fastapi import FastAPI, Query, HTTPException, status
from core.config import settings
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse

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
    title="Eloquence Backend API (Mode Sans Base de Données)",
    description="API pour le système de coaching vocal Eloquence - Mode de diagnostic sans base de données",
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

# Événements de démarrage et d'arrêt
@app.on_event("startup")
async def startup_event():
    """
    Événement exécuté au démarrage de l'application.
    """
    logger.info("Démarrage de l'application Eloquence Backend en mode sans base de données")
    logger.warning("⚠️ Mode sans base de données activé - Fonctionnalités limitées")

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
    return {"status": "ok", "version": "1.0.0", "mode": "sans base de données"}

# Route racine
@app.get("/")
async def root():
    """
    Route racine de l'API.
    """
    html_content = """
    <html>
        <head>
            <title>Backend Test Server</title>
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
                .warning {
                    background-color: #fff3cd;
                    color: #856404;
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
            <h1>Backend Test Server</h1>
            <p>If you can see this, your connection is working!</p>
            
            <div class="warning">
                <strong>Mode sans base de données activé</strong>
                <p>Le serveur fonctionne en mode diagnostic sans connexion à la base de données.</p>
                <p>Seules les routes de base sont disponibles.</p>
            </div>
            
            <div class="endpoints">
                <h3>Endpoints disponibles:</h3>
                <ul>
                    <li><a href="/health">/health</a> - Vérification de l'état du serveur</li>
                    <li><a href="/docs">/docs</a> - Documentation API</li>
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

# Ajouter quelques routes de test pour les services principaux
@app.get("/api/tts")
async def test_tts():
    return {"status": "mock", "message": "Service TTS simulé en mode sans base de données"}

@app.get("/api/stt")
async def test_stt():
    return {"status": "mock", "message": "Service STT simulé en mode sans base de données"}

@app.get("/coaching/init")
async def test_coaching_init():
    return {"status": "mock", "session_id": "test-session-123", "message": "Session de coaching simulée en mode sans base de données"}

@app.get("/api/session/start")
async def test_session_start():
    return {"status": "mock", "session_id": "test-session-123", "message": "Session simulée en mode sans base de données"}

# Endpoints de session ajoutés
@app.post("/api/session/start")
async def mock_session_start():
    # Endpoint simulé pour démarrer une session
    return {
        "status": "mock",
        "session_id": "mock-session-" + str(int(time.time())),
        "message": "Session simulée en mode sans base de données"
    }

@app.get("/api/session/{session_id}/feedback")
async def mock_session_feedback(session_id: str):
    # Endpoint simulé pour obtenir le feedback d'une session
    return {
        "status": "mock",
        "session_id": session_id,
        "feedback": {
            "fluency": 8,
            "pronunciation": 7,
            "grammar": 9,
            "vocabulary": 8,
            "overall": 8
        },
        "message": "Feedback simulé en mode sans base de données"
    }

# Endpoint de chat
@app.post("/chat/")
async def mock_chat():
    # Endpoint simulé pour le chat
    return {
        "status": "mock",
        "message": "Réponse de chat simulée en mode sans base de données",
        "response": "Bonjour, je suis un assistant virtuel simulé. Comment puis-je vous aider aujourd'hui?"
    }

# Endpoint d'exercice
@app.post("/coaching/exercise/generate")
async def mock_exercise_generate():
    # Endpoint simulé pour générer un exercice de coaching
    return {
        "status": "mock",
        "exercise_id": "mock-exercise-" + str(int(time.time())),
        "title": "Exercice de présentation",
        "description": "Présentez-vous en français pendant 1 minute",
        "message": "Exercice simulé en mode sans base de données"
    }

# Endpoints API TTS et STT avec paramètres
@app.post("/api/tts")
async def mock_tts_with_params(text: str = Query(...)):
    try:
        # Importer le service TTS optimisé
        from services.tts_service_optimized import tts_service_optimized
        
        # Utiliser le service TTS optimisé pour synthétiser
        audio_data = await tts_service_optimized.synthesize_text(text)
        
        # Générer un nom de fichier unique pour stocker l'audio
        filename = f"tts-{uuid.uuid4()}.wav"
        file_path = os.path.join(settings.AUDIO_STORAGE_PATH, filename)
        
        # Sauvegarder le fichier audio
        if audio_data:
            with open(file_path, "wb") as f:
                f.write(audio_data)
            
            return {
                "status": "success",
                "text": text,
                "audio_id": file_path,
                "message": "Synthèse vocale réussie"
            }
        else:
            return {
                "status": "error",
                "message": "Échec de la synthèse vocale"
            }
    except Exception as e:
        logger.error(f"Erreur lors de la synthèse vocale: {e}")
        return {
            "status": "error",
            "message": f"Erreur lors de la synthèse vocale: {str(e)}"
        }

@app.post("/api/stt")
async def mock_stt_with_params(audio_id: str = Query(...)):
    # Endpoint simulé pour la reconnaissance vocale
    return {
        "status": "mock",
        "audio_id": audio_id,
        "text": "Ceci est une transcription simulée pour le test.",
        "message": "Reconnaissance vocale simulée en mode sans base de données"
    }

# Endpoint de monitoring
@app.get("/api/monitoring/latency")
async def monitoring_latency():
    try:
        # Importer le module de monitoring de latence
        from core.latency_monitor import get_latency_stats
        
        # Récupérer les statistiques de latence réelles
        stats = get_latency_stats()
        
        return stats
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des statistiques de latence: {e}")
        # Retourner des données simulées en cas d'erreur
        return {
            "status": "error",
            "message": f"Erreur lors de la récupération des statistiques de latence: {str(e)}",
            "fallback_data": {
                "tts": 150,
                "stt": 200,
                "llm": 300,
                "total": 650
            }
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8082,
        reload=True
    )
