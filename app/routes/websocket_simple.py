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

logger = logging.getLogger(__name__)

router = APIRouter()

# Stockage des connexions WebSocket actives
active_connections = {}

@router.websocket("/ws/simple/{session_id}")
async def websocket_simple_endpoint(
    websocket: WebSocket,
    session_id: str,
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
        
        # Boucle de traitement des messages
        while True:
            # Attendre un message
            message = await websocket.receive()
            logger.info(f"Message reçu pour session {session_id}: {message}")
            
            # Message binaire (audio)
            if "bytes" in message:
                # Simplement renvoyer les données audio reçues
                await websocket.send_bytes(message["bytes"])
            
            # Message texte (contrôle)
            elif "text" in message:
                try:
                    data = json.loads(message["text"])
                    # Renvoyer le message reçu
                    await websocket.send_json({
                        "type": "echo",
                        "data": data
                    })
                except json.JSONDecodeError:
                    logger.error("Message JSON invalide")
                    await websocket.send_json({
                        "type": "error",
                        "message": "Message JSON invalide"
                    })
            
            else:
                logger.warning("Format de message WebSocket non pris en charge")
                await websocket.send_json({
                    "type": "error",
                    "message": "Format de message non pris en charge"
                })
    
    except WebSocketDisconnect:
        logger.info(f"Client déconnecté de la session {session_id}")
        if session_id in active_connections:
            del active_connections[session_id]
    
    except Exception as e:
        logger.error(f"Erreur WebSocket: {e}", exc_info=True)
        if session_id in active_connections:
            del active_connections[session_id]