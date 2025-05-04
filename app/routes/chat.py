import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from core.database import get_db
from core.orchestrator import orchestrator

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/", tags=["Chat"])
async def process_message(
    message: str,
    context: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Traite un message de chat.
    Équivalent à POST /chat dans le backend Node.js.
    """
    try:
        if not message:
            raise HTTPException(status_code=400, detail="Le message est requis")
        
        # Construire le prompt
        prompt = f"Tu es un assistant spécialisé dans l'apprentissage des langues et l'amélioration de la prononciation. {f'Contexte: {context}' if context else ''}\nQuestion de l'utilisateur: {message}\n\nRéponds de manière claire, précise et utile."
        
        # Générer la réponse
        # Utiliser une session temporaire pour le chat (pas besoin de persister)
        temp_session_id = f"chat_{message[:10]}"
        response = await orchestrator.generate_text_response(temp_session_id, prompt, db)
        
        return {
            "status": "success",
            "message": "Message traité",
            "data": {
                "response": response["text_response"]
            }
        }
    except Exception as e:
        logger.error(f"Erreur lors du traitement du message chat: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du traitement du message: {str(e)}")