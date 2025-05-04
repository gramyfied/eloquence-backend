"""
Extension de l'orchestrateur pour supporter les appels REST API.
Ces méthodes sont utilisées par les routes REST pour interagir avec l'orchestrateur.
"""

import logging
import asyncio
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import datetime

from core.latency_monitor import measure_latency, STEP_LLM_GENERATE
from core.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

# Étendre la classe Orchestrator avec des méthodes pour l'API REST
async def generate_text_response(self, session_id: str, prompt: str, db: AsyncSession) -> Dict[str, Any]:
    """
    Génère une réponse textuelle à partir d'un prompt.
    Utilisé par les routes REST pour générer des réponses sans passer par WebSocket.
    """
    logger.info(f"Génération de réponse textuelle pour session {session_id}")
    
    # Vérifier si la session existe, sinon la créer temporairement
    session = self.sessions.get(session_id)
    if not session:
        logger.info(f"Session {session_id} non trouvée, création temporaire pour API REST")
        session = await self.get_or_create_session(session_id, db)
        if not session:
            logger.error(f"Impossible de créer une session temporaire pour {session_id}")
            return {"text_response": "Erreur: Impossible de créer une session", "emotion_label": "neutre"}
    
    # Générer la réponse avec le LLM
    try:
        with measure_latency(STEP_LLM_GENERATE, session_id):
            llm_response = await self.llm_service.generate(
                prompt=prompt,
                is_interrupted=False  # Pas d'interruption pour les appels REST
            )
        
        logger.info(f"Réponse générée pour session {session_id}: {llm_response['text_response'][:50]}...")
        return llm_response
    except Exception as e:
        logger.error(f"Erreur lors de la génération de réponse pour session {session_id}: {e}")
        return {"text_response": f"Erreur lors de la génération: {str(e)}", "emotion_label": "neutre"}

async def generate_feedback(self, prompt: str, db: AsyncSession) -> Dict[str, Any]:
    """
    Génère un feedback à partir d'un prompt.
    Utilisé par les routes REST pour générer des feedbacks sans passer par WebSocket.
    """
    # Créer un ID de session temporaire pour le feedback
    session_id = f"feedback_{datetime.datetime.now().timestamp()}"
    return await self.generate_text_response(session_id, prompt, db)

# Ajouter les méthodes à la classe Orchestrator
Orchestrator.generate_text_response = generate_text_response
Orchestrator.generate_feedback = generate_feedback