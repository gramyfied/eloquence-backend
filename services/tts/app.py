import os
import io
import uuid
import tempfile
import logging
from typing import Optional, Dict, List
import numpy as np
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import soundfile as sf
from pydub import AudioSegment
import time

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tts-service")

# Récupérer les variables d'environnement
MODELS_PATH = os.environ.get("TTS_MODELS_PATH", "/app/models")
SPEAKERS_PATH = os.environ.get("TTS_SPEAKERS_PATH", "/app/speakers")
USE_XTTS = os.environ.get("TTS_USE_XTTS", "true").lower() == "true"

# Mapping des émotions vers les fichiers de référence pour XTTS
EMOTION_TO_REFERENCE = {
    "neutre": os.path.join(SPEAKERS_PATH, "emotions/neutre.wav"),
    "encouragement": os.path.join(SPEAKERS_PATH, "emotions/encouragement.wav"),
    "empathie": os.path.join(SPEAKERS_PATH, "emotions/empathie.wav"),
    "enthousiasme_modere": os.path.join(SPEAKERS_PATH, "emotions/enthousiasme_modere.wav"),
    "curiosite": os.path.join(SPEAKERS_PATH, "emotions/curiosite.wav"),
    "reflexion": os.path.join(SPEAKERS_PATH, "emotions/reflexion.wav")
}

# Mapping des émotions vers les speaker_id pour VITS
EMOTION_TO_SPEAKER_ID = {
    "neutre": "nathalie",
    "encouragement": "nathalie_encouragement",
    "empathie": "nathalie_empathie",
    "enthousiasme_modere": "nathalie_enthousiasme",
    "curiosite": "nathalie_curiosite",
    "reflexion": "nathalie_reflexion"
}

# Modèles de données
class TTSRequest(BaseModel):
    text: str
    speaker_id: Optional[str] = "neutre"
    language_id: Optional[str] = "fr"
    response_format: Optional[str] = "wav"
    stream: Optional[bool] = True

# Dictionnaire pour stocker les tâches de synthèse en cours
active_tasks = {}

app = FastAPI(title="Coqui TTS Service")

# Configurer CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Charger les modèles au démarrage
@app.on_event("startup")
async def startup_event():
    global tts_model, xtts_model
    
    try:
        from TTS.api import TTS
        
        # Charger le modèle VITS pour le français
        logger.info("Chargement du modèle VITS pour le français...")
        tts_model = TTS(model_path=os.path.join(MODELS_PATH, "tts_models/fr/mai/vits-nathalie-hifigan"), 
                        config_path=None)
        
        # Charger le modèle XTTS v2 si activé
        if USE_XTTS:
            logger.info("Chargement du modèle XTTS v2...")
            xtts_model = TTS(model_path=os.path.join(MODELS_PATH, "tts_models/multilingual/multi-dataset/xtts_v2"), 
                            config_path=None)
        else:
            xtts_model = None
            
        logger.info("Modèles TTS chargés avec succès")
    except Exception as e:
        logger.error(f"Erreur lors du chargement des modèles TTS: {e}")
        # Continuer quand même, les modèles seront rechargés à la première requête

# Route pour la synthèse vocale
@app.post("/api/tts")
async def synthesize_speech(request: TTSRequest):
    try:
        # Générer un ID unique pour cette tâche
        task_id = str(uuid.uuid4())
        
        # Déterminer quel modèle utiliser
        use_xtts = USE_XTTS and request.speaker_id in EMOTION_TO_REFERENCE
        
        # Créer un fichier temporaire pour l'audio
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            output_path = temp_file.name
            
            # Enregistrer la tâche comme active
            active_tasks[task_id] = {
                "start_time": time.time(),
                "output_path": output_path,
                "completed": False
            }
            
            # Synthétiser l'audio
            if use_xtts:
                # Utiliser XTTS avec le fichier de référence pour l'émotion
                reference_file = EMOTION_TO_REFERENCE.get(request.speaker_id, EMOTION_TO_REFERENCE["neutre"])
                logger.info(f"Synthèse XTTS avec référence: {reference_file}")
                
                xtts_model.tts_to_file(
                    text=request.text,
                    file_path=output_path,
                    speaker_wav=reference_file,
                    language=request.language_id
                )
            else:
                # Utiliser VITS avec le speaker_id pour l'émotion
                speaker_id = EMOTION_TO_SPEAKER_ID.get(request.speaker_id, EMOTION_TO_SPEAKER_ID["neutre"])
                logger.info(f"Synthèse VITS avec speaker_id: {speaker_id}")
                
                tts_model.tts_to_file(
                    text=request.text,
                    file_path=output_path,
                    speaker=speaker_id
                )
            
            # Marquer la tâche comme terminée
            active_tasks[task_id]["completed"] = True
            
            # Lire le fichier audio
            def iterfile():
                with open(output_path, "rb") as f:
                    yield from f
                # Supprimer le fichier après l'envoi
                os.unlink(output_path)
                # Supprimer la tâche du dictionnaire
                if task_id in active_tasks:
                    del active_tasks[task_id]
            
            # Retourner l'audio en streaming
            if request.stream:
                return StreamingResponse(iterfile(), media_type="audio/wav")
            else:
                # Lire tout le fichier et le retourner
                with open(output_path, "rb") as f:
                    audio_data = f.read()
                # Supprimer le fichier
                os.unlink(output_path)
                # Supprimer la tâche du dictionnaire
                if task_id in active_tasks:
                    del active_tasks[task_id]
                return Response(content=audio_data, media_type="audio/wav")
    
    except Exception as e:
        logger.error(f"Erreur lors de la synthèse vocale: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la synthèse vocale: {str(e)}")

# Route pour arrêter une synthèse en cours
@app.post("/api/stop")
async def stop_synthesis(session_id: str):
    """
    Arrête une synthèse vocale en cours pour une session donnée.
    Cette fonctionnalité est utilisée lors des interruptions utilisateur.
    """
    # Trouver toutes les tâches actives pour cette session
    stopped_count = 0
    for task_id, task_info in list(active_tasks.items()):
        if not task_info["completed"]:
            # Marquer la tâche comme terminée
            active_tasks[task_id]["completed"] = True
            # Supprimer le fichier de sortie s'il existe
            if os.path.exists(task_info["output_path"]):
                try:
                    os.unlink(task_info["output_path"])
                except Exception as e:
                    logger.error(f"Erreur lors de la suppression du fichier temporaire: {e}")
            # Supprimer la tâche du dictionnaire
            del active_tasks[task_id]
            stopped_count += 1
    
    return {"status": "success", "stopped_tasks": stopped_count}

# Route de vérification de santé
@app.get("/health")
async def health_check():
    return {
        "status": "ok", 
        "models": {
            "vits": True,
            "xtts": USE_XTTS
        },
        "active_tasks": len(active_tasks)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5002)