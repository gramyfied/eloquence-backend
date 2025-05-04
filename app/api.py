import uuid
import logging
import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any, cast

# Importer les dépendances, modèles et schémas
from core.database import get_db
from core.models import CoachingSession, SessionTurn, KaldiFeedback
from app.schemas import (
    FeedbackResponse, FeedbackResultItem, PronunciationFeedback, FluencyFeedback,
    LexicalFeedback, ProsodyFeedback, SessionStartRequest, SessionStartResponse,
    InitialMessage, SessionEndResponse
)
from core.orchestrator import orchestrator
from app.routes.monitoring import router as monitoring_router
from app.routes.audio import router as audio_router
from app.routes.coaching import router as coaching_router
from app.routes.chat import router as chat_router
from app.routes.scenario import router as scenario_router

logger = logging.getLogger(__name__)
router = APIRouter()

# Inclure les routeurs
router.include_router(monitoring_router, prefix="/monitoring", tags=["Monitoring"])
router.include_router(audio_router, prefix="/audio", tags=["Audio"])
router.include_router(coaching_router, prefix="/coaching", tags=["Coaching"])
router.include_router(chat_router, prefix="/chat", tags=["Chat"])
router.include_router(scenario_router, tags=["Scenarios"])

# Routes de compatibilité au niveau racine
router.include_router(audio_router, tags=["Compatibility"])

# Endpoint pour démarrer une session
@router.post(
    "/session/start",
    response_model=SessionStartResponse,
    tags=["Session"],
    summary="Démarre une nouvelle session de coaching"
)
async def start_session(
    request: SessionStartRequest,
    db: AsyncSession = Depends(get_db)
) -> SessionStartResponse:
    """
    Démarre une nouvelle session de coaching.
    
    - **scenario_id**: ID du scénario à utiliser (optionnel)
    - **user_id**: ID de l'utilisateur (défaut: "anonymous")
    - **language**: Langue de la session (défaut: "fr")
    - **goal**: Objectif spécifique de la session (optionnel)
    
    Retourne l'ID de la session, l'URL WebSocket et un message initial.
    """
    try:
        # Créer une nouvelle session dans la base de données
        session_id_str = str(uuid.uuid4())
        
        # Initialiser la session avec l'orchestrateur
        session_state = await orchestrator.get_or_create_session(
            session_id_str,
            db,
            scenario_id=request.scenario_id,
            user_id=request.user_id,
            language=request.language,
            goal=request.goal
        )
        
        if not session_state:
            raise HTTPException(status_code=500, detail="Impossible de créer la session")
        
        # Générer un message initial
        initial_prompt = f"Tu es un coach de prononciation français. L'utilisateur souhaite améliorer sa prononciation en {request.language}. Son objectif est: {request.goal or 'améliorer sa prononciation générale'}. Commence la session en te présentant brièvement et propose un premier exercice."
        
        # Générer la réponse initiale
        # Supposons que generate_text_response retourne Dict[str, Any]
        response: Dict[str, Any] = await orchestrator.generate_text_response(session_id_str, initial_prompt, db)
        
        # Utiliser .get() pour un accès plus sûr au dictionnaire
        initial_text = response.get("text_response", "Bonjour ! Prêt à commencer ?")
        
        return SessionStartResponse(
            session_id=uuid.UUID(session_id_str),
            websocket_url=f"/ws/{session_id_str}",
            initial_message=InitialMessage(
                text=initial_text,
                audio_url=None  # À implémenter si nécessaire
            )
        )
    except Exception as e:
        logger.exception(f"Erreur lors du démarrage de la session: {e}") # Utiliser logger.exception pour inclure la traceback
        raise HTTPException(status_code=500, detail=f"Erreur interne lors du démarrage de la session.")

# Endpoint pour terminer une session
@router.post(
    "/session/{session_id}/end",
    response_model=SessionEndResponse,
    tags=["Session"],
    summary="Termine une session de coaching"
)
async def end_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
) -> SessionEndResponse:
    """
    Termine une session de coaching existante.
    
    - **session_id**: ID de la session à terminer
    
    Retourne un message de confirmation et un résumé final.
    """
    try:
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
        turns: List[SessionTurn] = turns_result.scalars().all() # Ajouter l'annotation de type
        
        # Construire l'historique complet
        history_text = "\n".join([
            f"{'Utilisateur' if turn.role == 'user' else 'Coach'}: {turn.text_content or ''}" 
            for turn in turns
        ])
        
        # Générer un résumé de la session
        prompt = f"Tu es un coach de prononciation français. Voici l'historique complet d'une session de coaching:\n{history_text}\n\nFais un résumé des points forts et des points à améliorer de l'utilisateur, ainsi que des recommandations pour continuer à progresser. Limite ta réponse à 5-6 phrases."
        
        # Générer le résumé
        response: Dict[str, Any] = await orchestrator.generate_text_response(str(session_id), prompt, db)
        final_summary = response.get("text_response", "Session terminée. Bon travail !")
        
        # Marquer la session comme terminée
        session.status = "ended"
        # Utiliser timezone.utc pour la compatibilité
        session.ended_at = datetime.datetime.now(datetime.timezone.utc)
        await db.commit()
        
        # Nettoyer la session dans l'orchestrateur
        await orchestrator.cleanup_session(str(session_id), db)
        
        return SessionEndResponse(
            message="Session terminée avec succès",
            final_summary=final_summary,
            final_summary_url=None  # À implémenter si nécessaire
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erreur lors de la fin de la session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur interne lors de la fin de la session.")

@router.get(
    "/session/{session_id}/feedback",
    response_model=FeedbackResponse,
    tags=["Feedback"],
    summary="Récupère les résultats du feedback Kaldi pour une session"
)
async def get_session_feedback(
    session_id: uuid.UUID,
    segment_id: Optional[str] = Query(None, description="Filtrer par ID de segment spécifique (turn_id ou KaldiFeedback ID)"),
    db: AsyncSession = Depends(get_db)
) -> FeedbackResponse:
    """
    Récupère les résultats d'analyse Kaldi (prononciation, fluidité, etc.)
    pour tous les tours utilisateur d'une session de coaching donnée.
    """
    logger.info(f"Requête de feedback reçue pour session_id: {session_id}, segment_id: {segment_id}")

    try:
        # 1. Vérifier si la session existe
        session_result = await db.execute(select(CoachingSession).where(CoachingSession.id == session_id))
        session = session_result.scalar_one_or_none()
        if not session:
            logger.warning(f"Session non trouvée pour feedback: {session_id}")
            raise HTTPException(status_code=404, detail="Session non trouvée")

        # 2. Construire la requête pour récupérer les tours et leurs feedbacks
        stmt = (
            select(SessionTurn)
            .where(SessionTurn.session_id == session_id)
            .where(SessionTurn.role == 'user') # Ne récupérer que les tours utilisateur
            .options(selectinload(SessionTurn.feedback)) # Charger le feedback associé en une seule requête
            .order_by(SessionTurn.turn_number)
        )

        # Ajouter le filtre par segment_id si fourni
        if segment_id:
            try:
                segment_uuid = uuid.UUID(segment_id)
                # Filtrer sur l'ID du tour OU l'ID du feedback associé
                # Utilisation de outerjoin pour inclure les tours sans feedback si nécessaire
                stmt = stmt.outerjoin(SessionTurn.feedback).where(
                    (SessionTurn.id == segment_uuid) | (KaldiFeedback.id == segment_uuid)
                )
            except ValueError:
                logger.warning(f"segment_id '{segment_id}' n'est pas un UUID valide. Ignoré.")
                # Optionnel: lever une erreur 400 Bad Request
                # raise HTTPException(status_code=400, detail=f"segment_id '{segment_id}' n'est pas un UUID valide.")

        # 3. Exécuter la requête
        turns_result = await db.execute(stmt)
        # Utiliser unique() pour éviter les duplications dues à outerjoin
        user_turns_with_feedback: List[SessionTurn] = turns_result.scalars().unique().all()

        # 4. Formater la réponse
        feedback_results: List[FeedbackResultItem] = []
        for turn in user_turns_with_feedback:
            feedback_data: Optional[KaldiFeedback] = turn.feedback # Expliciter le type
            if feedback_data:
                # Vérifier que les scores/métriques sont bien des dictionnaires avant de les déballer
                pron_scores = feedback_data.pronunciation_scores if isinstance(feedback_data.pronunciation_scores, dict) else None
                flu_metrics = feedback_data.fluency_metrics if isinstance(feedback_data.fluency_metrics, dict) else None
                lex_metrics = feedback_data.lexical_metrics if isinstance(feedback_data.lexical_metrics, dict) else None
                pro_metrics = feedback_data.prosody_metrics if isinstance(feedback_data.prosody_metrics, dict) else None
                
                item = FeedbackResultItem(
                    segment_id=str(feedback_data.id), # Utiliser l'ID du feedback comme segment_id
                    turn_number=turn.turn_number,
                    # Utiliser les variables vérifiées
                    pronunciation=PronunciationFeedback(**pron_scores) if pron_scores else None,
                    fluency=FluencyFeedback(**flu_metrics) if flu_metrics else None,
                    lexical_diversity=LexicalFeedback(**lex_metrics) if lex_metrics else None,
                    prosody=ProsodyFeedback(**pro_metrics) if pro_metrics else None,
                )
                feedback_results.append(item)
            else:
                logger.debug(f"Aucun feedback trouvé pour le tour {turn.turn_number} (ID: {turn.id})")

        logger.info(f"Retour de {len(feedback_results)} résultats de feedback pour la session {session_id}")
        return FeedbackResponse(session_id=session_id, feedback_results=feedback_results)

    except HTTPException: # Re-lever les exceptions HTTP spécifiques
        raise
    except Exception as e:
        logger.exception(f"Erreur lors de la récupération du feedback pour la session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne lors de la récupération du feedback.")
