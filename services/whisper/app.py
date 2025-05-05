import os
import tempfile
import logging
from typing import Optional
import soundfile as sf
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from faster_whisper import WhisperModel

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whisper-service")

# Récupérer les variables d'environnement
MODEL_NAME = os.environ.get("ASR_MODEL_NAME", "large-v2") # Utiliser large-v2 par défaut
DEVICE = os.environ.get("ASR_DEVICE", "cpu")  # "cuda" ou "cpu" - Forcer CPU par défaut à cause de l'incompatibilité CUDA
COMPUTE_TYPE = os.environ.get("ASR_COMPUTE_TYPE", "int8")  # "int8", "float16", "float32"

app = FastAPI(title="Whisper ASR Service")

# Configurer CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Autoriser toutes les origines en développement
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Charger le modèle au démarrage
@app.on_event("startup")
async def startup_event():
    global model
    logger.info(f"Chargement du modèle Whisper {MODEL_NAME} sur {DEVICE} avec {COMPUTE_TYPE}")
    try:
        model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE)
        logger.info("Modèle Whisper chargé avec succès")
    except Exception as e:
        logger.error(f"Erreur lors du chargement du modèle Whisper: {e}")
        # Continuer quand même, le modèle sera rechargé à la première requête

# Route pour la transcription
@app.post("/asr")
async def transcribe_audio(
    file: Optional[UploadFile] = File(None),
    audio_bytes: Optional[bytes] = None,
    language: Optional[str] = Form(None),
):
    try:
        # Vérifier qu'on a bien reçu un fichier audio
        if file is None and audio_bytes is None:
            raise HTTPException(status_code=400, detail="Aucun fichier audio fourni")
        
        # Traiter le fichier uploadé
        if file:
            # Sauvegarder le fichier temporairement
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
                temp_file_path = temp_file.name
                temp_file.write(await file.read())
            
            # Charger l'audio avec soundfile
            audio_data, sample_rate = sf.read(temp_file_path)
            
            # Supprimer le fichier temporaire
            os.unlink(temp_file_path)
        
        # Traiter les bytes audio directement
        elif audio_bytes:
            # Convertir les bytes en numpy array
            import io
            audio_io = io.BytesIO(audio_bytes)
            audio_data, sample_rate = sf.read(audio_io)
        
        # Vérifier le sample rate
        if sample_rate != 16000:
            logger.warning(f"Sample rate inattendu: {sample_rate}. Whisper préfère 16kHz.")
        
        # Transcription avec Whisper
        segments, info = model.transcribe(audio_data, language=language, beam_size=5)
        
        # Récupérer le texte complet
        transcription = "".join(segment.text for segment in segments)
        
        # Retourner les résultats
        return {
            "transcription": transcription.strip(),
            "language": info.language,
            "language_probability": info.language_probability
        }
    
    except Exception as e:
        logger.error(f"Erreur lors de la transcription: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la transcription: {str(e)}")

# Route de vérification de santé
@app.get("/health")
async def health_check():
    return {"status": "ok", "model": MODEL_NAME, "device": DEVICE}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)