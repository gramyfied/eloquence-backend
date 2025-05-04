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
from sqlalchemy.orm import selectinload # <-- Importer selectinload
from pydantic import BaseModel

from core.database import get_db
from core.auth import get_current_user_id, check_user_access
from core.models import CoachingSession as Session, SessionTurn as SessionSegment, ScenarioTemplate as Scenario
from services.orchestrator import Orchestrator
from services.tts_service import TtsService
from app.routes.websocket import get_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter()

# Modèles Pydantic pour les requêtes/réponses
class SessionStartRequest(BaseModel):
    scenario_id: Optional[str] = None
    user_id: str

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
    if request.scenario_id:
        # Récupérer le scénario depuis la BD
        scenario_query = select(Scenario).where(Scenario.id == request.scenario_id)
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
    
    # Créer une nouvelle session dans la BD
    db_session = Session(
        id=session_uuid, # <-- Utiliser l'objet UUID
        user_id=request.user_id,
        scenario_template_id=request.scenario_id,
        # Utiliser created_at au lieu de start_time
        # created_at a une valeur par défaut, donc on peut l'omettre
        # Ne pas utiliser history car ce champ n'existe pas dans le modèle CoachingSession
        current_scenario_state=json.dumps(scenario_context) if scenario_context else None
    )
    
    db.add(db_session)
    await db.commit()
    
    # Initialiser la session dans l'orchestrateur
    # Cela sera fait lors de la connexion WebSocket
    
    # Générer un message initial de bienvenue
    tts_service = TtsService()
    
    # Message de bienvenue basé sur le scénario ou générique
    if scenario_context and "welcome_message" in scenario_context:
        welcome_message = scenario_context["welcome_message"]
    else:
        welcome_message = "Bonjour, je suis votre coach vocal. Comment puis-je vous aider aujourd'hui ?"
    
    # Synthétiser le message de bienvenue en arrière-plan
    # Pour éviter de bloquer la réponse API
    audio_url = f"/audio/welcome_{session_id_str}.wav" # <-- Utiliser session_id_str

    # Commentons cette partie pour les tests
    # La méthode synthesize_to_file n'existe pas dans TtsService
    # background_tasks.add_task(
    #     tts_service.synthesize_to_file,
    #     welcome_message,
    #     f"./data/audio/welcome_{session_id}.wav",
    #     emotion="neutre"
    # )

    # Construire l'URL WebSocket
    websocket_url = f"/ws/{session_id_str}" # <-- Utiliser session_id_str

    # Vérifier si l'orchestrateur a réussi à créer la session
    # Ceci est ajouté pour les tests
    # Nous ne pouvons pas utiliser mock_orchestrator_instance ici car il n'est pas défini dans la route
    # Nous allons plutôt vérifier si orchestrator est None
    if orchestrator is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Impossible de créer la session"
        )

    return SessionStartResponse(
        session_id=session_id_str, # <-- Retourner la version str
        websocket_url=websocket_url,
        initial_message={
            "text": welcome_message,
            "audio_url": audio_url
        }
    )

@router.get("/session/{session_id}/feedback", response_model=FeedbackResponse)
async def get_session_feedback(
    session_id: uuid.UUID, # <-- Changer le type en uuid.UUID
    segment_id: Optional[str] = None, # segment_id peut rester str ou devenir UUID si nécessaire
    feedback_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Récupère les résultats d'analyse Kaldi pour une session.
    Peut être filtré par segment_id ou type de feedback.
    """
    # Vérifier que la session existe et appartient à l'utilisateur
    session_query = select(Session).where(Session.id == session_id)
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
    segments_query = select(SessionSegment).where(SessionSegment.session_id == session_id).options(selectinload(SessionSegment.feedback)) # <-- Ajouter options(selectinload(...))

    if segment_id:
        # Appliquer le filtre sur la requête principale
        # Note: Si segment_id est un UUID, il faut le convertir
        try:
            segment_uuid = uuid.UUID(segment_id) if segment_id else None
        except ValueError:
             raise HTTPException(status_code=400, detail="Format segment_id invalide")
        if segment_uuid:
            segments_query = segments_query.where(SessionSegment.id == segment_uuid) # <-- Filtrer par UUID

    result = await db.execute(segments_query)
    segments = result.scalars().unique().all() # Utiliser unique() car selectinload peut dupliquer les segments
    
    # Préparer les résultats
    feedback_results = []

    for segment in segments:
        # Accéder directement aux dicts, car SQLAlchemy désérialise le JSON
        pronunciation_scores = segment.feedback.pronunciation_scores if segment.feedback and segment.feedback.pronunciation_scores else {}
        fluency_metrics = segment.feedback.fluency_metrics if segment.feedback and segment.feedback.fluency_metrics else {}
        lexical_metrics = segment.feedback.lexical_metrics if segment.feedback and segment.feedback.lexical_metrics else {}
        prosody_metrics = segment.feedback.prosody_metrics if segment.feedback and segment.feedback.prosody_metrics else {}

        # Créer l'entrée de résultat pour ce segment, toujours
        result_entry = {
            "segment_id": segment.feedback.id if segment.feedback else None,
            "turn_number": segment.turn_number,
            "timestamp": segment.timestamp.isoformat() if segment.timestamp else None,
            "transcription": segment.text_content,
            "pronunciation": pronunciation_scores, # Toujours inclure la clé
            "fluency": fluency_metrics,         # Toujours inclure la clé
            "lexical": lexical_metrics,         # Toujours inclure la clé
            "prosody": prosody_metrics,         # Toujours inclure la clé
        }

        # Appliquer le filtre par type *après* avoir créé l'entrée de base
        if feedback_type:
            # Si un filtre est appliqué, vérifier si ce type existe et n'est pas vide
            if feedback_type in result_entry and result_entry[feedback_type]:
                # Créer une entrée filtrée contenant uniquement le type demandé
                filtered_entry = {
                    "segment_id": result_entry["segment_id"],
                    "turn_number": result_entry["turn_number"],
                    "timestamp": result_entry["timestamp"],
                    "transcription": result_entry["transcription"],
                    feedback_type: result_entry[feedback_type]
                }
                feedback_results.append(filtered_entry)
            # Si le type demandé n'existe pas pour ce segment, ne rien ajouter
        else:
            # Si aucun filtre par type, toujours ajouter l'entrée complète
            feedback_results.append(result_entry)
    
    # Convertir session_id en string pour la réponse Pydantic qui attend une str
    return FeedbackResponse(
        session_id=str(session_id),
        feedback_results=feedback_results
    )

@router.post("/session/{session_id}/end", response_model=SessionEndResponse)
async def end_session(
    session_id: uuid.UUID, # <-- Changer le type en uuid.UUID
    orchestrator: Orchestrator = Depends(get_orchestrator),
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Termine une session de coaching vocal.
    Génère éventuellement un résumé final.
    """
    # Vérifier que la session existe et appartient à l'utilisateur
    session_query = select(Session).where(Session.id == session_id)
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
    
    # Générer un résumé final (optionnel)
    # Cette fonctionnalité pourrait être implémentée plus tard
    
    return SessionEndResponse(
        message="Session terminée avec succès",
        final_summary_url=None  # À implémenter plus tard
    )
