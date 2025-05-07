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

@router.post("/session/start", response_model=SessionStartResponse)
async def start_session(
    request: SessionStartRequest,
    background_tasks: BackgroundTasks,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Démarre une nouvelle session de coaching vocal.
    Retourne l'ID de session et l'URL WebSocket pour la connexion.
    """
    # Vérifier que l'utilisateur existe
    if not check_user_access(request.user_id, current_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'êtes pas autorisé à démarrer une session pour cet utilisateur"
        )

    # Générer un nouvel ID de session (objet UUID et sa version str)
    session_uuid = uuid.uuid4()
    session_id_str = str(session_uuid)

    # Charger le scénario si spécifié
    scenario_context = None
    welcome_message = "Bonjour, je suis votre coach vocal. Comment puis-je vous aider aujourd'hui ?"
    
    if request.scenario_id:
        # Récupérer le scénario depuis la BD
        scenario_query = select(ScenarioTemplate).where(ScenarioTemplate.id == request.scenario_id)
        result = await db.execute(scenario_query)
        scenario = result.scalar_one_or_none()
        
        if not scenario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scénario {request.scenario_id} non trouvé"
            )
        
        # Charger le contexte du scénario
        scenario_context = json.loads(scenario.structure) if scenario.structure else {}
        if scenario.initial_prompt:
            scenario_context["welcome_message"] = scenario.initial_prompt
            welcome_message = scenario.initial_prompt
    
    # Créer une nouvelle session dans la BD
    db_session = CoachingSession(
        id=session_uuid,
        user_id=request.user_id,
        scenario_template_id=request.scenario_id,
        language=request.language,
        goal=request.goal,
        current_scenario_state=json.dumps(scenario_context) if scenario_context else None
    )
    
    db.add(db_session)
    await db.commit()
    
    # Générer un message initial de bienvenue
    tts_service = TtsService()
    
    # Synthétiser le message de bienvenue en arrière-plan
    audio_url = f"/audio/welcome_{session_id_str}.wav"

    # Construire l'URL WebSocket
    websocket_url = f"/ws/{session_id_str}"

    return SessionStartResponse(
        session_id=session_id_str,
        websocket_url=websocket_url,
        initial_message={
            "text": welcome_message,
            "audio_url": audio_url
        }
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
    # Vérifier que la session existe et appartient à l'utilisateur
    session_query = select(CoachingSession).where(CoachingSession.id == session_id)
    result = await db.execute(session_query)
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} non trouvée"
        )
    
    if not check_user_access(session.user_id, current_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'êtes pas autorisé à accéder à cette session"
        )
    
    # Construire la requête pour les segments avec chargement eager de feedback
    segments_query = select(SessionTurn).where(SessionTurn.session_id == session_id).options(selectinload(SessionTurn.feedback))

    # Appliquer le filtre segment_id si fourni
    segment_uuid = None
    if segment_id:
        try:
            segment_uuid = uuid.UUID(segment_id)
            segments_query = segments_query.where(SessionTurn.id == segment_uuid)
        except ValueError:
            raise HTTPException(status_code=400, detail="Format segment_id invalide")
    
    result = await db.execute(segments_query)
    segments = result.scalars().unique().all()
    
    # Préparer les résultats
    feedback_results = []

    for segment in segments:
        # Accéder directement aux dicts, car SQLAlchemy désérialise le JSON
        pronunciation_scores = {}
        fluency_metrics = {}
        lexical_metrics = {}
        prosody_metrics = {}
        
        if segment.feedback:
            pronunciation_scores = segment.feedback.pronunciation_scores or {}
            fluency_metrics = segment.feedback.fluency_metrics or {}
            lexical_metrics = segment.feedback.lexical_metrics or {}
            prosody_metrics = segment.feedback.prosody_metrics or {}

        # Créer l'entrée de résultat pour ce segment
        result_entry = {
            "segment_id": str(segment.feedback.id) if segment.feedback else None,
            "turn_number": segment.turn_number,
            "timestamp": segment.timestamp.isoformat() if segment.timestamp else None,
            "transcription": segment.text_content,
            "pronunciation": pronunciation_scores,
            "fluency": fluency_metrics,
            "lexical": lexical_metrics,
            "prosody": prosody_metrics,
        }

        # Appliquer le filtre par type si fourni
        if feedback_type:
            if feedback_type in result_entry and result_entry[feedback_type]:
                filtered_entry = {
                    "segment_id": result_entry["segment_id"],
                    "turn_number": result_entry["turn_number"],
                    "timestamp": result_entry["timestamp"],
                    "transcription": result_entry["transcription"],
                    feedback_type: result_entry[feedback_type]
                }
                feedback_results.append(filtered_entry)
        else:
            feedback_results.append(result_entry)
    
    return FeedbackResponse(
        session_id=str(session_id),
        feedback_results=feedback_results
    )

@router.post("/session/{session_id}/end", response_model=SessionEndResponse)
async def end_session(
    session_id: uuid.UUID,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Termine une session de coaching vocal.
    Génère éventuellement un résumé final.
    """
    # Vérifier que la session existe et appartient à l'utilisateur
    session_query = select(CoachingSession).where(CoachingSession.id == session_id)
    result = await db.execute(session_query)
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} non trouvée"
        )
    
    if not check_user_access(session.user_id, current_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'êtes pas autorisé à terminer cette session"
        )
    
    # Terminer la session dans l'orchestrateur
    await orchestrator.end_session(session_id)
    
    # Mettre à jour la session dans la BD
    session.ended_at = datetime.now()
    await db.commit()
    
    return SessionEndResponse(
        message="Session terminée avec succès",
        final_summary_url=None
    )
