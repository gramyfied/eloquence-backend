import logging
import uuid
import datetime
import logging
import uuid
import datetime
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field # Ajout de BaseModel et Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional, Dict, Any, List

from core.database import get_db
from core.models import CoachingSession, SessionTurn, ScenarioTemplate
from core.orchestrator import orchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/coaching", tags=["Coaching"]) # Ajout d'un préfixe pour clarté

# --- Modèles Pydantic ---
class ExerciseRequest(BaseModel):
    exercise_type: str = Field(..., description="Type d'exercice (ex: diction, lecture, jeu_de_role_situation)")
    topic: Optional[str] = Field(None, description="Sujet ou thème de l'exercice")
    difficulty: Optional[str] = Field("moyen", description="Niveau de difficulté (ex: facile, moyen, difficile)")
    length: Optional[str] = Field("court", description="Longueur souhaitée (ex: très court, court, moyen, long)")

class ExerciseResponse(BaseModel):
    exercise_text: str

# --- Routes existantes ---
@router.post("/init")
async def init_session(
    user_id: str,
    language: Optional[str] = "français",
    goal: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Initialise une session de coaching.
    Équivalent à POST /coaching/init dans le backend Node.js.
    """
    try:
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id est requis")
        
        # Créer une nouvelle session dans la base de données
        session_id = str(uuid.uuid4())
        
        # Initialiser la session avec l'orchestrateur
        session_state = await orchestrator.get_or_create_session(session_id, db)
        
        # Générer un message initial
        initial_prompt = f"Tu es un coach de prononciation français. L'utilisateur souhaite améliorer sa prononciation en {language}. Son objectif est: {goal or 'améliorer sa prononciation générale'}. Commence la session en te présentant brièvement et propose un premier exercice."
        
        # Générer la réponse initiale
        response = await orchestrator.generate_text_response(session_id, initial_prompt, db)
        
        return {
            "status": "success",
            "message": "Session de coaching initialisée",
            "data": {
                "session_id": session_id,
                "coach_message": response["text_response"],
                "websocket_url": f"/ws/{session_id}"  # URL pour la connexion WebSocket
            }
        }
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation de la session: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'initialisation de la session: {str(e)}")

@router.post("/message", tags=["Coaching"])
async def process_message(
    session_id: str,
    message: str,
    audio_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Traite un message dans une session existante.
    Équivalent à POST /coaching/message dans le backend Node.js.
    """
    try:
        if not session_id or not message:
            raise HTTPException(status_code=400, detail="session_id et message sont requis")
        
        # Vérifier que la session existe
        session_result = await db.execute(select(CoachingSession).where(CoachingSession.id == session_id))
        session = session_result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Session non trouvée")
        
        # Ajouter le message de l'utilisateur à l'historique
        new_turn = SessionTurn(
            session_id=session_id,
            turn_number=len(session.turns) + 1,
            role="user",
            text_content=message,
            audio_path=audio_id
        )
        db.add(new_turn)
        await db.commit()
        await db.refresh(new_turn)
        
        # Construire le prompt pour Mistral
        # Récupérer les derniers messages
        turns_result = await db.execute(
            select(SessionTurn)
            .where(SessionTurn.session_id == session_id)
            .order_by(SessionTurn.turn_number.desc())
            .limit(6)  # Limiter le contexte aux 6 derniers messages
        )
        recent_turns = turns_result.scalars().all()
        recent_turns.reverse()  # Remettre dans l'ordre chronologique
        
        history_text = "\n".join([f"{'Utilisateur' if turn.role == 'user' else 'Coach'}: {turn.text_content}" for turn in recent_turns])
        
        prompt = f"Tu es un coach de prononciation français. Voici l'historique de la conversation:\n{history_text}\nRéponds à l'utilisateur de manière encourageante et constructive. Limite ta réponse à 3-4 phrases."
        
        # Générer la réponse
        response = await orchestrator.generate_text_response(session_id, prompt, db)
        
        # Ajouter la réponse à l'historique
        assistant_turn = SessionTurn(
            session_id=session_id,
            turn_number=len(session.turns) + 2,
            role="assistant",
            text_content=response["text_response"],
            emotion_label=response["emotion_label"]
        )
        db.add(assistant_turn)
        await db.commit()
        
        return {
            "status": "success",
            "message": "Message traité",
            "data": {
                "coach_message": response["text_response"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors du traitement du message: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du traitement du message: {str(e)}")

@router.post("/interrupt", tags=["Coaching"])
async def interrupt_session(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Interrompt une session de coaching.
    Équivalent à POST /coaching/interrupt dans le backend Node.js.
    """
    try:
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id est requis")
        
        # Vérifier que la session existe
        session_result = await db.execute(select(CoachingSession).where(CoachingSession.id == session_id))
        session = session_result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Session non trouvée")
        
        # Interrompre la session via l'orchestrateur
        await orchestrator.handle_interruption(session_id)
        
        return {
            "status": "success",
            "message": "Session interrompue",
            "data": {
                "session_id": session_id,
                "paused": True
            }
        }
    except Exception as e:
        logger.error(f"Erreur lors de l'interruption de la session: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'interruption de la session: {str(e)}")

@router.post("/end", tags=["Coaching"])
async def end_session(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Termine une session de coaching.
    Équivalent à POST /coaching/end dans le backend Node.js.
    """
    try:
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id est requis")
        
        # Vérifier que la session existe
        session_result = await db.execute(select(CoachingSession).where(CoachingSession.id == session_id))
        session = session_result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Session non trouvée")
        
        # Récupérer tous les tours de la session
        turns_result = await db.execute(
            select(SessionTurn)
            .where(SessionTurn.session_id == session_id)
            .order_by(SessionTurn.turn_number)
        )
        turns = turns_result.scalars().all()
        
        # Construire l'historique complet
        history_text = "\n".join([f"{'Utilisateur' if turn.role == 'user' else 'Coach'}: {turn.text_content}" for turn in turns])
        
        # Générer un résumé de la session
        prompt = f"Tu es un coach de prononciation français. Voici l'historique complet d'une session de coaching:\n{history_text}\n\nFais un résumé des points forts et des points à améliorer de l'utilisateur, ainsi que des recommandations pour continuer à progresser. Limite ta réponse à 5-6 phrases."
        
        # Générer le résumé
        response = await orchestrator.generate_text_response(session_id, prompt, db)
        
        # Marquer la session comme terminée
        session.status = "ended"
        session.ended_at = datetime.datetime.utcnow()
        await db.commit()
        
        # Nettoyer la session dans l'orchestrateur
        await orchestrator.cleanup_session(session_id, db)
        
        return {
            "status": "success",
            "message": "Session terminée",
            "data": {
                "summary": response["text_response"]
            }
        }
    except Exception as e:
        logger.error(f"Erreur lors de la fin de la session: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la fin de la session: {str(e)}")

# --- Nouvelle route pour la génération d'exercices ---
@router.post("/exercise/generate", response_model=ExerciseResponse)
async def generate_exercise_text_endpoint(
    request_data: ExerciseRequest
):
    """
    Génère le texte pour un exercice de coaching spécifique en utilisant l'IA.
    """
    try:
        logger.info(f"Requête API pour générer un exercice: {request_data.dict()}")
        
        # Appeler la méthode de l'orchestrateur
        exercise_text = await orchestrator.generate_exercise(
            exercise_type=request_data.exercise_type,
            topic=request_data.topic,
            difficulty=request_data.difficulty,
            length=request_data.length
        )
        
        return ExerciseResponse(exercise_text=exercise_text)
        
    except Exception as e:
        logger.error(f"Erreur API lors de la génération de l'exercice: {e}", exc_info=True)
        # Remonter une erreur HTTP 500
        raise HTTPException(status_code=500, detail=f"Erreur interne lors de la génération de l'exercice: {str(e)}")
