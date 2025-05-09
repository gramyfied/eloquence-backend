"""
Routes REST pour la gestion des sessions de coaching vocal.
"""

import logging
import os # Ajout de l'import manquant
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
    db: AsyncSession = Depends(get_db), # Réactivé
    current_user_id: str = Depends(get_current_user_id) # Réactivé
    # background_tasks: BackgroundTasks, # Gardé commenté
    # orchestrator: Orchestrator = Depends(get_orchestrator), # Gardé commenté
):
    """
    Démarre une nouvelle session de coaching vocal.
    Valide le scenario_id (DB puis fichier), génère un ID de session,
    crée une CoachingSession en DB, et retourne l'URL WebSocket et le message initial.
    V4 - Logique DB pour ScenarioTemplate et création CoachingSession.
    """
    logger.warning("<<<<< DANS start_session - V4 - Logique DB et création CoachingSession >>>>>")
    logger.info(f"Requête reçue pour user_id: {current_user_id} (authentifié) et scenario_id: {request.scenario_id}")

    if not request.scenario_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le champ 'scenario_id' est obligatoire."
        )

    scenario_template_db = None
    initial_prompt_text = None
    scenario_source = None

    # 1. Essayer de charger le ScenarioTemplate depuis la DB
    try:
        stmt = select(ScenarioTemplate).where(ScenarioTemplate.id == request.scenario_id)
        result = await db.execute(stmt)
        scenario_template_db = result.scalar_one_or_none()
        if scenario_template_db and scenario_template_db.initial_prompt:
            initial_prompt_text = scenario_template_db.initial_prompt
            scenario_source = "database"
            logger.info(f"Scénario '{request.scenario_id}' trouvé dans la base de données.")
    except Exception as e_db:
        logger.error(f"Erreur lors de la recherche du scénario '{request.scenario_id}' en DB: {e_db}", exc_info=True)
        # Ne pas lever d'exception ici, on va essayer de charger depuis un fichier

    # 2. Si non trouvé en DB, essayer de charger depuis un fichier JSON
    if not scenario_template_db:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        scenario_filename = f"scenario_{request.scenario_id}.json"
        scenario_path = os.path.join(base_dir, "examples", scenario_filename)
        logger.info(f"Scénario non trouvé en DB. Tentative de chargement depuis fichier: {scenario_path}")

        if os.path.exists(scenario_path):
            try:
                with open(scenario_path, "r", encoding="utf-8") as f:
                    scenario_data_file = json.load(f)
                    initial_prompt_text = scenario_data_file.get("initial_prompt")
                    scenario_source = "file"
                    logger.info(f"Scénario '{request.scenario_id}' trouvé dans le fichier JSON.")
            except json.JSONDecodeError:
                logger.error(f"Erreur de décodage JSON pour le scénario fichier: {scenario_path}")
            except Exception as e_file:
                logger.error(f"Erreur inattendue lors du chargement du scénario fichier {scenario_path}: {e_file}", exc_info=True)
        else:
            logger.warning(f"Scénario '{request.scenario_id}' non trouvé en DB ni en fichier ({scenario_path}).")

    # 3. Valider que initial_prompt_text a été trouvé
    if not initial_prompt_text or not isinstance(initial_prompt_text, str):
        logger.error(f"Impossible de déterminer initial_prompt pour scenario_id '{request.scenario_id}' (source: {scenario_source})")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, # Ou 500 si on considère que le scénario devrait exister
            detail=f"Données de scénario invalides ou scénario non trouvé pour '{request.scenario_id}'."
        )
    
    initial_message = {
        "text": initial_prompt_text,
        "audio_url": "" # TODO: Gérer initial_audio_url si présent dans scenario_template_db ou scenario_data_file
    }

    # 4. Générer un ID de session et l'URL WebSocket
    session_id_uuid = uuid.uuid4()
    session_id_str = str(session_id_uuid)
    websocket_url = f"/ws/{session_id_str}"

    # 5. Créer l'enregistrement CoachingSession en base de données
    try:
        new_session_db = CoachingSession(
            id=session_id_uuid,
            user_id=current_user_id, # Utilise l'ID de l'utilisateur authentifié
            scenario_template_id=request.scenario_id,
            language=request.language or "fr",
            goal=request.goal,
            status="started", # ou "active"
            created_at=datetime.utcnow(),
            current_scenario_state={} # État initial vide ou défini
        )
        db.add(new_session_db)
        await db.commit()
        await db.refresh(new_session_db)
        logger.info(f"CoachingSession créée en DB avec ID: {session_id_str} pour scenario: {request.scenario_id}")
    except Exception as e_create_session:
        logger.error(f"Erreur lors de la création de CoachingSession en DB pour scenario '{request.scenario_id}': {e_create_session}", exc_info=True)
        # Annuler la transaction si quelque chose s'est mal passé
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors de la création de la session."
        )

    logger.info(f"Session démarrée avec succès : id={session_id_str}, scenario={request.scenario_id}, source={scenario_source}")

    return SessionStartResponse(
        session_id=session_id_str,
        websocket_url=websocket_url,
        initial_message=initial_message
    )

@router.get("/session/{session_id}/feedback", response_model=FeedbackResponse)
async def get_session_feedback(
    session_id: uuid.UUID,
    segment_id: Optional[uuid.UUID] = None, # segment_id est l'ID d'un SessionTurn (UUID)
    feedback_type: Optional[str] = None, # Ignoré pour l'instant
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Récupère les résultats d'analyse Kaldi pour une session.
    Peut être filtré par segment_id (ID du SessionTurn).
    V2 - Logique DB restaurée.
    """
    logger.info(f"<<<<< DANS get_session_feedback - V2 - Logique DB restaurée >>>>>")
    logger.info(f"Récupération feedback pour session_id: {session_id}, segment_id: {segment_id}, user: {current_user_id}")

    # 1. Vérifier l'existence de la session et l'accès utilisateur
    coaching_session = await db.get(CoachingSession, session_id)
    if not coaching_session:
        logger.warning(f"Session non trouvée: {session_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session non trouvée")

    # Note: La logique d'accès utilisateur (check_user_access) pourrait être plus complexe
    # Pour l'instant, on se base sur le user_id de la session si SKIP_AUTH_CHECK n'est pas True.
    # Notre get_current_user_id simplifié retourne "debug-user", donc cette vérification est pour l'exemple.
    if coaching_session.user_id != current_user_id and current_user_id != "debug-user": # Permettre à debug-user d'accéder
        logger.warning(f"Accès non autorisé à la session {session_id} pour l'utilisateur {current_user_id}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès non autorisé à cette session")

    # 2. Construire la requête pour les feedbacks
    stmt = (
        select(SessionTurn, KaldiFeedback, Participant)
        .join(KaldiFeedback, KaldiFeedback.turn_id == SessionTurn.id)
        .join(Participant, Participant.id == SessionTurn.participant_id)
        .where(SessionTurn.session_id == session_id)
        .order_by(SessionTurn.turn_number) # Ordonner par numéro de tour
    )

    if segment_id:
        logger.info(f"Filtrage par segment_id (turn_id): {segment_id}")
        stmt = stmt.where(SessionTurn.id == segment_id)
    
    results = await db.execute(stmt)
    turn_feedback_data = results.all() # Liste de tuples (SessionTurn, KaldiFeedback, Participant)

    if not turn_feedback_data:
        logger.info(f"Aucun feedback trouvé pour la session {session_id} (segment: {segment_id})")
        # Si segment_id est spécifié et rien n'est trouvé, c'est un 404 pour ce segment.
        # Si aucun segment_id n'est spécifié et la liste est vide, c'est OK, juste pas de feedback.
        if segment_id:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Aucun feedback trouvé pour le segment {segment_id} de cette session.")

    feedback_results_list: List[Dict[str, Any]] = []
    for turn, kaldi, participant in turn_feedback_data:
        feedback_item = {
            "segment_id": str(turn.id),
            # Simplification: user_text et coach_text basés sur le rôle du participant du tour
            "user_text": turn.text_content if participant.role == "user" else None,
            "coach_text": turn.text_content if participant.role != "user" else None, # ou "assistant", "system"
            "audio_url": turn.audio_path, # Assumer que audio_path est l'URL ou un identifiant pour la construire
            "feedback": {
                "pronunciation_scores": kaldi.pronunciation_scores,
                "fluency_metrics": kaldi.fluency_metrics,
                "lexical_metrics": kaldi.lexical_metrics,
                "prosody_metrics": kaldi.prosody_metrics,
                "personalized_feedback": kaldi.personalized_feedback # Si ce champ existe et est pertinent
            }
        }
        feedback_results_list.append(feedback_item)

    return FeedbackResponse(
        session_id=str(session_id),
        feedback_results=feedback_results_list
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
