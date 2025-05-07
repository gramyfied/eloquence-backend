"""
Routes pour les services audio (TTS et STT).
"""

import logging
import os
import uuid
from fastapi import APIRouter, Query, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import aiohttp
import aiofiles
from typing import Optional

from core.config import settings
from core.auth import get_current_user_id
from services.tts_service import TtsService
from services.asr_service import AsrService

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/tts")
async def synthesize_text(
    text: str = Query(..., description="Texte à synthétiser"),
    voice: Optional[str] = Query("default", description="Voix à utiliser"),
    emotion: Optional[str] = Query("neutre", description="Émotion à exprimer"),
    background_tasks: BackgroundTasks = None,
    current_user_id: str = None  # Optionnel pour permettre l'utilisation sans authentification
):
    """
    Synthétise du texte en audio.
    """
    try:
        # Initialiser le service TTS
        tts_service = TtsService()
        
        # Générer un nom de fichier unique
        filename = f"tts-{uuid.uuid4()}.wav"
        file_path = os.path.join(settings.AUDIO_STORAGE_PATH, filename)
        
        # Créer le répertoire de stockage s'il n'existe pas
        os.makedirs(settings.AUDIO_STORAGE_PATH, exist_ok=True)
        
        # Synthétiser le texte en audio
        audio_data = await tts_service.synthesize(text, speaker_id=voice, emotion=emotion)
        
        # Sauvegarder le fichier audio
        if audio_data:
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(audio_data)
            
            return {
                "status": "success",
                "text": text,
                "audio_id": file_path,
                "message": "Synthèse vocale réussie"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Échec de la synthèse vocale: aucune donnée audio générée"
            )
    except Exception as e:
        logger.error(f"Erreur lors de la synthèse vocale: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la synthèse vocale: {str(e)}"
        )

@router.post("/stt")
async def transcribe_audio(
    audio_file: UploadFile = File(..., description="Fichier audio à transcrire"),
    language: Optional[str] = Query("fr", description="Langue de l'audio"),
    current_user_id: str = None  # Optionnel pour permettre l'utilisation sans authentification
):
    """
    Transcrit un fichier audio en texte.
    """
    try:
        # Initialiser le service ASR
        asr_service = AsrService()
        
        # Sauvegarder temporairement le fichier audio
        temp_file_path = os.path.join(settings.AUDIO_STORAGE_PATH, f"temp-{uuid.uuid4()}.wav")
        os.makedirs(settings.AUDIO_STORAGE_PATH, exist_ok=True)
        
        # Lire le contenu du fichier
        audio_content = await audio_file.read()
        
        # Sauvegarder le fichier temporairement
        async with aiofiles.open(temp_file_path, "wb") as f:
            await f.write(audio_content)
        
        # Transcrire l'audio
        transcription_result = await asr_service.transcribe(temp_file_path, language=language)
        
        # Supprimer le fichier temporaire
        os.remove(temp_file_path)
        
        if transcription_result:
            return {
                "status": "success",
                "transcription": transcription_result["text"],
                "language": transcription_result.get("language", language),
                "segments": transcription_result.get("segments", []),
                "processing_time": transcription_result.get("processing_time", 0)
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Échec de la transcription: aucun résultat généré"
            )
    except Exception as e:
        logger.error(f"Erreur lors de la transcription: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la transcription: {str(e)}"
        )

@router.get("/audio/{filename}")
async def get_audio_file(filename: str):
    """
    Récupère un fichier audio par son nom.
    """
    file_path = os.path.join(settings.AUDIO_STORAGE_PATH, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="audio/wav")
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Fichier audio {filename} non trouvé"
        )