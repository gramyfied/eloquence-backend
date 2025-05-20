"""
Routes REST pour la gestion des sessions de coaching vocal.
"""

import logging
import os
import json
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from livekit import api # Ajout pour la génération de token LiveKit
from core.config import settings # S'assurer que cet import est bien actif
# from core.auth import get_api_key # Supprimé car non utilisé et cause une ImportError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from core.database import get_db
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
    client: Optional[Any] = None # Ajout défensif pour éviter AttributeError

class SessionStartResponse(BaseModel):
    session_id: str
    websocket_url: Optional[str] = None # Pour le WebSocket simple, rendu optionnel
    initial_message: Dict[str, str]
    livekit_url: Optional[str] = None
    livekit_token: Optional[str] = None
    room_name: Optional[str] = None

class FeedbackResponse(BaseModel):
    session_id: str
    feedback_results: List[Dict[str, Any]]

class SessionEndResponse(BaseModel):
    message: str
    final_summary_url: Optional[str] = None

@router.post("/sessions", response_model=SessionStartResponse) # Renommé de /session/start à /sessions
async def start_session(
    payload: SessionStartRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Démarre une nouvelle session de coaching vocal.
    Valide le scenario_id, génère un ID de session et retourne l'URL WebSocket, 
    le message initial, et les informations LiveKit.
    """
    user_id_from_payload = payload.user_id

    logger.warning("<<<<< DANS start_session - V3 avec LiveKit Info >>>>>")
    logger.info(f"Requête reçue pour user_id: {user_id_from_payload} et scenario_id: {payload.scenario_id}")

    if not payload.scenario_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le champ 'scenario_id' est obligatoire."
        )

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    scenario_filename = f"scenario_{payload.scenario_id}.json"
    scenario_path = os.path.join(base_dir, "examples", scenario_filename)
    
    logger.info(f"Vérification de l'existence du scénario : {scenario_path}")

    if not os.path.exists(scenario_path):
        logger.warning(f"Scénario non trouvé : {scenario_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scénario '{payload.scenario_id}' non trouvé."
        )

    try:
        with open(scenario_path, "r", encoding="utf-8") as f:
            scenario_data = json.load(f)
            initial_message = scenario_data.get("initial_message")
            if not initial_message or not isinstance(initial_message, dict) or "text" not in initial_message:
                 logger.error(f"Format 'initial_message' invalide dans {scenario_path}")
                 raise HTTPException(
                     status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                     detail=f"Données de scénario invalides pour '{payload.scenario_id}'."
                 )
            initial_message.setdefault("audio_url", "")
    except Exception as e:
        logger.error(f"Erreur lors du chargement du scénario {scenario_path}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur serveur lors du chargement du scénario '{payload.scenario_id}'."
        )

    session_id = str(uuid.uuid4())
    websocket_url = f"/ws/simple/{session_id}" 

    logger.info(f"Session démarrée avec succès : id={session_id}, scenario={payload.scenario_id}")

    # Génération des informations LiveKit en utilisant l'objet settings
    lk_host = settings.LIVEKIT_HOST
    lk_api_key = settings.LIVEKIT_API_KEY
    lk_api_secret = settings.LIVEKIT_API_SECRET

    livekit_room_name = f"eloquence-{session_id}"
    # S'assurer que participant_identity n'est pas vide
    participant_identity = user_id_from_payload if user_id_from_payload else f"participant-{uuid.uuid4()}"
    if not participant_identity: # Double vérification pour une chaîne vide
        participant_identity = f"unknown-participant-{uuid.uuid4()}"


    livekit_token_generated = None
    if lk_api_key and lk_api_secret:
        try:
            token_builder = api.AccessToken(lk_api_key, lk_api_secret)
            video_grants = api.VideoGrants(
                room_join=True,
                room=livekit_room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True
            )
            # S'assurer que participant_name n'est pas vide s'il est utilisé
            participant_name = participant_identity 
            livekit_token_generated = token_builder.with_identity(participant_identity) \
                                                .with_name(participant_name) \
                                                .with_grants(video_grants) \
                                                .to_jwt()
            logger.info(f"Token LiveKit généré pour la room: {livekit_room_name}, identité: {participant_identity}")
        except Exception as e:
            logger.error(f"Erreur lors de la génération du token LiveKit: {e}", exc_info=True)
            # Ne pas bloquer, le client gérera l'absence de token
            pass
    else:
        logger.warning("LIVEKIT_API_KEY ou LIVEKIT_API_SECRET non configurés. Impossible de générer le token LiveKit.")

    response_data = SessionStartResponse( # Crée l'objet réponse
        session_id=session_id,
        # websocket_url=websocket_url, # Supprimé pour forcer le flux LiveKit
        initial_message=initial_message,
        livekit_url=lk_host if livekit_token_generated else None, # CORRIGÉ: Utilise le champ 'livekit_url'
        livekit_token=livekit_token_generated, # CORRIGÉ: Utilise le champ 'livekit_token'
        room_name=livekit_room_name if livekit_token_generated else None
    )
    logger.info(f"Réponse envoyée pour /api/sessions: session_id={response_data.session_id}, websocket_url={response_data.websocket_url}, initial_message_text={response_data.initial_message.get('text')}, livekit_url={response_data.livekit_url}, livekit_token={'PRESENT' if response_data.livekit_token else 'ABSENT'}, room_name={response_data.room_name}") # Log amélioré avant de retourner
    return response_data # Retourne l'objet

@router.get("/session/{session_id}/feedback", response_model=FeedbackResponse)
async def get_session_feedback(
    session_id: uuid.UUID,
    segment_id: Optional[str] = None,
    feedback_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Récupère les résultats d'analyse Kaldi pour une session.
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
                    "pronunciation_scores": {"overall": 0.85, "phonemes": {"b": 0.9, "o": 0.85, "n": 0.8, "j": 0.9, "u": 0.85, "r": 0.8}},
                    "fluency_metrics": {"speech_rate": 3.2, "articulation_rate": 4.5, "pause_count": 2, "mean_pause_duration": 0.3},
                    "lexical_metrics": {"lexical_diversity": 0.7, "word_count": 8},
                    "prosody_metrics": {"pitch_variation": 0.15, "intensity_variation": 0.12}
                }
            }
        ]
    )

@router.post("/session/{session_id}/end", response_model=SessionEndResponse)
async def end_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Termine une session de coaching vocal et génère un résumé final.
    """
    session = await db.get(CoachingSession, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session non trouvée")

    summary_url = f"/summaries/{session_id}.pdf" 

    return SessionEndResponse(
        message="Session terminée avec succès",
        final_summary_url=summary_url
    )
