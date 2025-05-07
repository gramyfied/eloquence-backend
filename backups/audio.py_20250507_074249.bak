import os
import logging
import uuid
import asyncio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any
import shutil

from core.database import get_db
from core.config import settings
from services.asr_service import AsrService
from services.tts_service import TtsService
from services.kaldi_service import kaldi_service
from core.orchestrator import orchestrator

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialiser les services
asr_service = AsrService()
tts_service = TtsService()

# Assurer que les répertoires de stockage existent
os.makedirs(settings.AUDIO_STORAGE_PATH, exist_ok=True)

@router.post("/upload", tags=["Audio"])
async def upload_audio(
    audio: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload d'un fichier audio.
    Équivalent à POST /audio/upload dans le backend Node.js.
    """
    try:
        # Générer un nom de fichier unique
        filename = f"audio-{uuid.uuid4()}.{audio.filename.split('.')[-1]}"
        file_path = os.path.join(settings.AUDIO_STORAGE_PATH, filename)
        
        # Sauvegarder le fichier
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)
        
        return {
            "status": "success",
            "message": "Fichier audio uploadé avec succès",
            "data": {
                "audio_id": file_path,
                "filename": filename,
                "size": os.path.getsize(file_path)
            }
        }
    except Exception as e:
        logger.error(f"Erreur lors de l'upload du fichier audio: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'upload du fichier audio: {str(e)}")

@router.post("/tts", tags=["Audio"])
async def synthesize_speech(
    text: str,
    voice: Optional[str] = None,
    speed: Optional[float] = 1.0,
    db: AsyncSession = Depends(get_db)
):
    """
    Synthèse vocale (TTS).
    Équivalent à POST /audio/tts dans le backend Node.js.
    """
    try:
        if not text:
            raise HTTPException(status_code=400, detail="Le texte est requis")
        
        # Limiter la longueur du texte pour éviter les timeouts
        if len(text) > 2000:
            logger.warning(f"Texte trop long ({len(text)} caractères), tronqué à 2000 caractères")
            text = text[:2000] + "..."
        
        # Utiliser le service TTS pour synthétiser
        result = await tts_service.synthesize(text, voice=voice, speed=speed)
        
        return {
            "status": "success",
            "message": "Synthèse vocale réussie",
            "data": {
                "audio_id": result["file_path"],
                "filename": os.path.basename(result["file_path"])
            }
        }
    except Exception as e:
        logger.error(f"Erreur lors de la synthèse vocale: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la synthèse vocale: {str(e)}")

@router.post("/stt", tags=["Audio"])
async def transcribe_audio(
    audio_id: str,
    language: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Transcription audio (STT).
    Équivalent à POST /audio/stt dans le backend Node.js.
    """
    try:
        if not audio_id:
            raise HTTPException(status_code=400, detail="audio_id est requis")
        
        # Vérifier que le fichier existe
        if not os.path.exists(audio_id):
            raise HTTPException(status_code=404, detail=f"Fichier audio non trouvé: {audio_id}")
        
        # Vérifier la taille du fichier
        file_size_mb = os.path.getsize(audio_id) / (1024 * 1024)
        if file_size_mb > 25:
            raise HTTPException(status_code=413, detail=f"Fichier audio trop volumineux: {file_size_mb:.2f} MB")
        
        # Utiliser le service ASR pour transcrire
        transcription = await asr_service.transcribe(audio_id, language=language)
        
        return {
            "status": "success",
            "message": "Transcription réussie",
            "data": transcription
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la transcription audio: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la transcription audio: {str(e)}")

@router.post("/evaluate", tags=["Audio"])
async def evaluate_pronunciation(
    audio_id: str,
    reference_text: str,
    session_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Évaluation de la prononciation.
    Équivalent à POST /audio/evaluate dans le backend Node.js.
    
    Args:
        audio_id: Chemin vers le fichier audio à évaluer
        reference_text: Texte de référence pour l'évaluation
        session_id: ID de la session (optionnel, pour la personnalisation du feedback)
    """
    try:
        if not audio_id or not reference_text:
            raise HTTPException(status_code=400, detail="audio_id et reference_text sont requis")
        
        # Vérifier que le fichier existe
        if not os.path.exists(audio_id):
            raise HTTPException(status_code=404, detail=f"Fichier audio non trouvé: {audio_id}")
        
        # Utiliser le service Kaldi pour évaluer avec personnalisation si session_id est fourni
        evaluation_data = await kaldi_service.evaluate(audio_id, reference_text, session_id)
        
        return {
            "status": "success",
            "message": "Évaluation de la prononciation réussie",
            "data": evaluation_data
        }
    except Exception as e:
        logger.error(f"Erreur lors de l'évaluation de la prononciation: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'évaluation de la prononciation: {str(e)}")

@router.post("/full-process", tags=["Audio"])
async def full_process(
    audio: UploadFile = File(...),
    reference_text: str = Form(...),
    language: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db)
):
    """
    Processus complet (upload, transcription, évaluation, feedback).
    Équivalent à POST /audio/full-process dans le backend Node.js.
    
    Args:
        audio: Fichier audio à analyser
        reference_text: Texte de référence pour l'évaluation
        language: Langue de l'audio (optionnel)
        session_id: ID de la session (optionnel, pour la personnalisation du feedback)
    """
    try:
        # 1. Upload du fichier audio
        filename = f"audio-{uuid.uuid4()}.{audio.filename.split('.')[-1]}"
        audio_path = os.path.join(settings.AUDIO_STORAGE_PATH, filename)
        
        with open(audio_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)
        
        # 2. Transcription et évaluation en parallèle
        transcription_task = asr_service.transcribe(audio_path, language=language)
        evaluation_task = kaldi_service.evaluate(audio_path, reference_text, session_id)
        
        transcription_result, evaluation_data = await asyncio.gather(
            transcription_task,
            evaluation_task
        )
        
        # Utiliser le feedback personnalisé généré par Kaldi si disponible
        feedback_text = ""
        if evaluation_data and "feedback" in evaluation_data and evaluation_data["feedback"]:
            # Utiliser le feedback personnalisé généré par la méthode evaluate
            feedback_text = evaluation_data["feedback"].get("feedback_text", "")
        
        # Si aucun feedback personnalisé n'est disponible, générer un feedback avec l'orchestrateur
        if not feedback_text:
            feedback_prompt = f"""
                Texte de référence: "{reference_text}"
                Transcription de l'utilisateur: "{transcription_result['transcription']}"
                Score de prononciation: {evaluation_data.get('score', 'N/A')}
                
                Donne un feedback constructif et encourageant sur la prononciation de l'utilisateur.
                Identifie les forces et les points à améliorer. Limite ta réponse à 3-4 phrases.
            """
            
            # Utiliser l'orchestrateur pour générer le feedback
            feedback_result = await orchestrator.generate_feedback(feedback_prompt, db)
            feedback_text = feedback_result["text_response"]
        
        return {
            "status": "success",
            "message": "Traitement complet réussi",
            "data": {
                "audio_id": audio_path,
                "reference_text": reference_text,
                "transcription": transcription_result["transcription"],
                "evaluation": evaluation_data,
                "feedback": feedback_text
            }
        }
    except Exception as e:
        logger.error(f"Erreur lors du traitement complet: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du traitement complet: {str(e)}")

# Routes de compatibilité
@router.post("/transcribe", tags=["Compatibility"])
async def transcribe_compat(
    audio: Optional[UploadFile] = File(None),
    audio_id: Optional[str] = None,
    language: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Route de compatibilité pour la transcription.
    Équivalent à POST /transcribe dans le backend Node.js.
    """
    try:
        # Si un fichier est fourni, l'uploader d'abord
        if audio:
            filename = f"audio-{uuid.uuid4()}.{audio.filename.split('.')[-1]}"
            file_path = os.path.join(settings.AUDIO_STORAGE_PATH, filename)
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(audio.file, buffer)
            
            audio_id = file_path
        
        # Vérifier qu'on a bien un audio_id
        if not audio_id:
            raise HTTPException(status_code=400, detail="audio_id est requis ou un fichier audio doit être fourni")
        
        # Utiliser la route /stt
        return await transcribe_audio(audio_id, language, db)
    except Exception as e:
        logger.error(f"Erreur lors de la transcription audio (compat): {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la transcription audio: {str(e)}")

@router.post("/synthesize", tags=["Compatibility"])
async def synthesize_compat(
    text: str,
    voice: Optional[str] = None,
    speed: Optional[float] = 1.0,
    db: AsyncSession = Depends(get_db)
):
    """
    Route de compatibilité pour la synthèse vocale.
    Équivalent à POST /synthesize dans le backend Node.js.
    """
    return await synthesize_speech(text, voice, speed, db)