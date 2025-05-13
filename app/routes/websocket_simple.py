"""
Routes WebSocket simplifiées pour l'application Eloquence.
Gère les connexions WebSocket pour le streaming audio bidirectionnel.
"""

import logging
import json
from typing import Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.orchestrator import Orchestrator
from app.routes.websocket import get_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter()

# Stockage des connexions WebSocket actives
active_connections = {}

@router.websocket("/ws/simple/{session_id}")
async def websocket_simple_endpoint(
    websocket: WebSocket,
    session_id: str,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    db: AsyncSession = Depends(get_db)
):
    """
    Point d'entrée WebSocket simplifié pour le streaming audio bidirectionnel.
    
    Le client envoie des chunks audio et reçoit des chunks audio en retour.
    Le client peut également envoyer des messages de contrôle JSON.
    """
    logger.info(f"Nouvelle connexion WebSocket simplifiée entrante pour session {session_id}")
    
    # Accepter explicitement la connexion WebSocket
    await websocket.accept()
    logger.info(f"Connexion WebSocket simplifiée acceptée pour session {session_id}")
    
    # Stocker la connexion
    active_connections[session_id] = websocket
    
    try:
        # Envoyer un message de bienvenue
        await websocket.send_json({
            "type": "welcome",
            "message": f"Bienvenue dans la session {session_id}!"
        })
        
        # Connecter le client à l'orchestrateur
        await orchestrator.connect_client(websocket, session_id)
        logger.info(f"Client connecté à l'orchestrateur pour session {session_id}")
        
        # Boucle de traitement des messages
        while True:
            logger.info(f"En attente de message WebSocket pour session {session_id}...")
            await orchestrator.process_websocket_message(websocket, session_id)
            logger.info(f"Message WebSocket traité pour session {session_id}.")
    
    except WebSocketDisconnect:
        logger.info(f"Client déconnecté de la session {session_id}")
        if session_id in active_connections:
            del active_connections[session_id]
        # Déconnecter le client de l'orchestrateur
        await orchestrator.disconnect_client(session_id)
    
    except Exception as e:
        logger.error(f"Erreur WebSocket: {e}", exc_info=True)
        if session_id in active_connections:
            del active_connections[session_id]
        # Tenter de déconnecter le client de l'orchestrateur
        try:
            await orchestrator.disconnect_client(session_id)
        except:
            pass