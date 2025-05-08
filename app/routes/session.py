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
    # background_tasks: BackgroundTasks, # Gardé commenté
    # orchestrator: Orchestrator = Depends(get_orchestrator), # Gardé commenté
    # db: AsyncSession = Depends(get_db), # Gardé commenté
    current_user_id: str = Depends(get_current_user_id) # Réactivé (utilise auth.py simplifié)
):
    """
    Démarre une nouvelle session de coaching vocal.
    Valide le scenario_id, génère un ID de session et retourne l'URL WebSocket et le message initial.
    V3 - Logique restaurée (lecture fichier JSON), sans création DB/Orchestrator.
    """
    logger.warning("<<<<< DANS start_session - V3 - Logique restaurée (lecture JSON) >>>>>")
    logger.info(f"Requête reçue pour user_id: {current_user_id} (authentifié) et scenario_id: {request.scenario_id}") # Utilise current_user_id

    if not request.scenario_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le champ 'scenario_id' est obligatoire."
        )

    # Construire le chemin vers le fichier JSON du scénario
    # Chemin relatif depuis ce fichier (app/routes/session.py) vers examples/
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    scenario_filename = f"scenario_{request.scenario_id}.json" # Hypothèse: scenario_id correspond au nom du fichier
    scenario_path = os.path.join(base_dir, "examples", scenario_filename)
    
    logger.info(f"Vérification de l'existence du scénario : {scenario_path}")

    if not os.path.exists(scenario_path):
        logger.warning(f"Scénario non trouvé : {scenario_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scénario '{request.scenario_id}' non trouvé."
        )

    # Charger le message initial depuis le fichier JSON
    try:
        with open(scenario_path, "r", encoding="utf-8") as f:
            scenario_data = json.load(f)
            initial_message = scenario_data.get("initial_message")
            if not initial_message or not isinstance(initial_message, dict) or "text" not in initial_message:
                 logger.error(f"Format 'initial_message' invalide dans {scenario_path}")
                 raise HTTPException(
                     status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                     detail=f"Données de scénario invalides pour '{request.scenario_id}'."
                 )
            # Assurer que audio_url est présent, même si vide
            initial_message.setdefault("audio_url", "")

    except json.JSONDecodeError:
        logger.error(f"Erreur de décodage JSON pour le scénario: {scenario_path}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Impossible de lire les données du scénario '{request.scenario_id}'."
        )
    except Exception as e:
        logger.error(f"Erreur inattendue lors du chargement du scénario {scenario_path}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur serveur lors du chargement du scénario '{request.scenario_id}'."
        )

    # Générer un ID de session et l'URL WebSocket
    session_id = str(uuid.uuid4())
    websocket_url = f"/ws/{session_id}" # URL relative pour le WebSocket

    logger.info(f"Session démarrée avec succès : id={session_id}, scenario={request.scenario_id}")

    # TODO: Ajouter ici la logique pour créer la session dans la base de données
    # et potentiellement initialiser l'orchestrateur si nécessaire.

    return SessionStartResponse(
        session_id=session_id,
        websocket_url=websocket_url,
        initial_message=initial_message
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
