"""
Routes pour le service de chat.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.auth import get_current_user_id
from services.llm_service import LlmService
from services.llm_service_local import LlmServiceLocal

logger = logging.getLogger(__name__)

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = None
    session_id: Optional[str] = None
    history: Optional[list] = None

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
        # Utiliser le service local si disponible, sinon utiliser le service distant
        try:
            llm_service = LlmServiceLocal()
            logger.info("Utilisation du service LLM local")
        except Exception as e:
            logger.warning(f"Service LLM local non disponible: {e}. Utilisation du service distant.")
            llm_service = LlmService()
        
        # Préparer le contexte pour le LLM
        context = {
            "user_id": current_user_id,
            "session_id": request.session_id,
            "context_type": request.context or "general",
            "history": request.history or []
        }
        
        # Générer la réponse
        result = await llm_service.generate(
            prompt=request.message,
            context=context
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
