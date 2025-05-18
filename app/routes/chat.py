"""
Routes pour le service de chat.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.auth import get_current_user_id
from services.llm_service import LlmService

logger = logging.getLogger(__name__)

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = None
    session_id: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = None

class ChatResponse(BaseModel):
    response: str
    emotion: Optional[str] = None
    session_id: Optional[str] = None

@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Envoie un message au chatbot et reçoit une réponse.
    """
    try:
        # Initialiser le service LLM
        llm_service = LlmService()
        logger.info("Utilisation du service LLM")
        
        # Préparer l'historique pour le LLM
        history = request.history or []
        
        # Si l'historique est vide, créer un message utilisateur
        if not history:
            history = [{"role": "user", "content": request.message}]
        # Si le dernier message n'est pas celui de l'utilisateur, l'ajouter
        elif history[-1]["role"] != "user" or history[-1]["content"] != request.message:
            history.append({"role": "user", "content": request.message})
        
        # Préparer le contexte du scénario
        scenario_context = None
        if request.context:
            scenario_context = {
                "name": request.context,
                "goal": "conversation",
                "current_step": "dialogue"
            }
        
        # Générer la réponse
        result = await llm_service.generate(
            history=history,
            scenario_context=scenario_context
        )
        
        # Extraire la réponse et l'émotion
        response_text = result.get("text", "Je suis désolé, je n'ai pas pu générer de réponse.")
        emotion = result.get("emotion", "neutre")
        
        return ChatResponse(
            response=response_text,
            emotion=emotion,
            session_id=request.session_id
        )
    except Exception as e:
        logger.error(f"Erreur lors de la génération de la réponse: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la génération de la réponse: {str(e)}"
        )
