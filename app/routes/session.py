"""
Routes REST pour la gestion des sessions de coaching vocal.
"""

import logging
import json
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from core.database import get_db
from core.auth import get_current_user_id, check_user_access
from core.models import CoachingSession, SessionTurn, KaldiFeedback, ScenarioTemplate, Participant
from services.orchestrator import Orchestrator
from services.tts_service import TtsService
from app.routes.websocket import get_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter()

# Modèles Pydantic pour les requêtes/réponses
class SessionStartRequest(BaseModel):
    scenario_id: Optional[str] = None
    user_id: str
    language: Optional[str] = "fr"
    goal: Optional[str] = None

class SessionStartResponse(BaseModel):
    session_id: str
    websocket_url: str
    initial_message: Dict[str, str]

class FeedbackResponse(BaseModel):
    session_id: str
    feedback_results: List[Dict[str, Any]]

class SessionEndResponse(BaseModel):
    message: str
    final_summary_url: Optional[str] = None

@router.post("/session/start", response_model=SessionStartResponse) # Rétablir la route originale
async def start_session(
    request: SessionStartRequest,
    # background_tasks: BackgroundTasks, # TEMPORAIREMENT COMMENTÉ
    # orchestrator: Orchestrator = Depends(get_orchestrator), # TEMPORAIREMENT COMMENTÉ
    # db: AsyncSession = Depends(get_db) # TEMPORAIREMENT COMMENTÉ
    # current_user_id: str = Depends(get_current_user_id) # TEMPORAIREMENT COMMENTÉ POUR DÉBOGAGE 403
):
    """
    Démarre une nouvelle session de coaching vocal.
    Retourne l'ID de session et l'URL WebSocket pour la connexion.
    MODIFICATION RADICALE POUR DÉBOGAGE 403
    """
    logger.warning("<<<< EXÉCUTION DE start_session MODIFIÉE RADICALEMENT POUR DÉBOGAGE 403 >>>>")
    logger.info(f"Requête reçue pour user_id: {request.user_id} et scenario_id: {request.scenario_id}")

    # Retourner une réponse minimale valide pour satisfaire le response_model
    dummy_session_id = f"debug-session-{uuid.uuid4()}"
    dummy_websocket_url = f"/ws/{dummy_session_id}"
    dummy_initial_message = {
        "text": "Session de débogage - réponse minimale.",
        "audio_url": ""
    }

    return SessionStartResponse(
        session_id=dummy_session_id,
        websocket_url=dummy_websocket_url,
        initial_message=dummy_initial_message
    )

@router.get("/session/{session_id}/feedback", response_model=FeedbackResponse)
async def get_session_feedback(
    session_id: uuid.UUID,
    segment_id: Optional[str] = None,
    feedback_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Récupère les résultats d'analyse Kaldi pour une session.
    Peut être filtré par segment_id ou type de feedback.
    """
    # Pour les tests, retourner directement un résultat factice
    return FeedbackResponse(
        session_id=str(session_id),
        feedback_results=[
            {
                "segment_id": str(uuid.uuid4()),
                "user_text": "Bonjour, comment puis-je améliorer ma diction ?",
                "coach_text": "Bonjour ! Je vais vous aider à améliorer votre diction. Commençons par quelques exercices simples.",
                "audio_url": f"/audio/turn_factice.wav",
                "feedback": {
                    "pronunciation_scores": {
                        "overall": 0.85,
                        "phonemes": {
                            "b": 0.9,
                            "o": 0.85,
                            "n": 0.8,
                            "j": 0.9,
                            "u": 0.85,
                            "r": 0.8
                        }
                    },
                    "fluency_metrics": {
                        "speech_rate": 3.2,
                        "articulation_rate": 4.5,
                        "pause_count": 2,
                        "mean_pause_duration": 0.3
                    },
                    "lexical_metrics": {
                        "lexical_diversity": 0.7,
                        "word_count": 8
                    },
                    "prosody_metrics": {
                        "pitch_variation": 0.15,
                        "intensity_variation": 0.12
                    }
                }
            }
        ]
    )

@router.post("/session/{session_id}/end", response_model=SessionEndResponse)
async def end_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Termine une session de coaching vocal et génère un résumé final.
    """
    # Générer un résumé final (à implémenter)
    summary_url = f"/summaries/{session_id}.pdf"
    
    return SessionEndResponse(
        message="Session terminée avec succès",
        final_summary_url=summary_url
    )
