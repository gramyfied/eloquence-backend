"""
Routes WebSocket pour l'application Eloquence.
Gère les connexions WebSocket pour le streaming audio bidirectionnel.
"""

import logging

# Variable globale pour stocker l'orchestrateur en mode sans base de données
_orchestrator_instance = None

def set_orchestrator(orchestrator):
    # Définit l'instance globale de l'orchestrateur pour le mode sans base de données
    global _orchestrator_instance
    _orchestrator_instance = orchestrator
    return orchestrator

from typing import Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
# Suppression de l'importation problématique
# from core.auth import get_current_user_id
from services.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

router = APIRouter()

# Singleton Orchestrator
orchestrator: Optional[Orchestrator] = None

async def get_orchestrator(db: AsyncSession = Depends(get_db)) -> Orchestrator:
    """
    Récupère l'instance singleton de l'Orchestrateur.
    L'initialise si nécessaire.
    """
    global orchestrator
    if orchestrator is None:
        orchestrator = Orchestrator(db)
        await orchestrator.initialize()
    return orchestrator

# Fonction temporaire pour remplacer get_current_user_id
async def get_current_user_id(authorization: Optional[str] = None) -> str:
    """
    Implémentation temporaire pour remplacer l'importation manquante.
    """
    return "default-user-id"

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    db: AsyncSession = Depends(get_db)
):
    """
    Point d'entrée WebSocket pour le streaming audio bidirectionnel.
    
    Le client envoie des chunks audio et reçoit des chunks audio en retour.
    Le client peut également envoyer des messages de contrôle JSON.
    """
    logger.info(f"Nouvelle connexion WebSocket entrante pour session {session_id}")
    try:
        # Vérifier que la session existe
        # Note: Dans une implémentation réelle, il faudrait vérifier que l'utilisateur
        # a le droit d'accéder à cette session
        
        # Accepter explicitement la connexion WebSocket
        await websocket.accept()
        logger.info(f"Connexion WebSocket acceptée pour session {session_id}")
        
        # Connecter le client à l'orchestrateur
        await orchestrator.connect_client(websocket, session_id)
        
        # Boucle de traitement des messages
        while True:
            logger.info(f"En attente de message WebSocket pour session {session_id}...")
            await orchestrator.process_websocket_message(websocket, session_id)
            logger.info(f"Message WebSocket traité pour session {session_id}.")
    
    except WebSocketDisconnect:
        logger.info(f"Client déconnecté de la session {session_id}")
        await orchestrator.disconnect_client(session_id)
    
    except Exception as e:
        logger.error(f"Erreur WebSocket: {e}", exc_info=True)
        # Tenter de fermer proprement
        try:
            await orchestrator.disconnect_client(session_id)
        except:
            pass

@router.websocket("/ws/debug/{session_id}")
async def debug_websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    db: AsyncSession = Depends(get_db)
):
    """
    Point d'entrée WebSocket de débogage.
    Permet de tester le flux sans authentification.
    À utiliser uniquement en développement.
    """
    logger.info(f"Nouvelle connexion WebSocket de débogage entrante pour session {session_id}")
    if not session_id:
        session_id = "debug-session"
    
    try:
        # Accepter explicitement la connexion WebSocket
        await websocket.accept()
        logger.info(f"Connexion WebSocket de débogage acceptée pour session {session_id}")
        
        # Connecter le client à l'orchestrateur
        await orchestrator.connect_client(websocket, session_id)
        
        # Boucle de traitement des messages
        while True:
            logger.info(f"En attente de message WebSocket de débogage pour session {session_id}...")
            await orchestrator.process_websocket_message(websocket, session_id)
            logger.info(f"Message WebSocket de débogage traité pour session {session_id}.")
    
    except WebSocketDisconnect:
        logger.info(f"Client déconnecté de la session de débogage {session_id}")
        await orchestrator.disconnect_client(session_id)
    
    except Exception as e:
        logger.error(f"Erreur WebSocket de débogage: {e}", exc_info=True)
        # Tenter de fermer proprement
        try:
            await orchestrator.disconnect_client(session_id)
        except:
            pass

@router.websocket("/ws/simple/{session_id}")
async def simple_websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    db: AsyncSession = Depends(get_db)
):
    """
    Point d'entrée WebSocket simplifié pour l'application mobile.
    Accepte les connexions sans authentification.
    """
    logger.info(f"Nouvelle connexion WebSocket simple entrante pour session {session_id}")
    
    # Variable pour suivre l'état de la connexion
    connection_active = True
    
    try:
        # Accepter explicitement la connexion avant de la passer à l'orchestrateur
        await websocket.accept()
        logger.info(f"Connexion WebSocket acceptée pour session {session_id}")
        
        # Envoyer un message de confirmation de connexion
        await websocket.send_json({
            "type": "connection_status",
            "status": "connected",
            "session_id": session_id,
            "message": "Connexion WebSocket établie avec succès"
        })
        
        # Connecter le client à l'orchestrateur
        await orchestrator.connect_client(websocket, session_id)
        logger.info(f"Client connecté à l'orchestrateur pour session {session_id}")
        
        # Boucle de traitement des messages avec timeout
        while connection_active:
            try:
                # Utiliser wait_for pour éviter de bloquer indéfiniment
                logger.info(f"En attente de message WebSocket simple pour session {session_id}...")
                await orchestrator.process_websocket_message(websocket, session_id)
                logger.info(f"Message WebSocket simple traité pour session {session_id}.")
            except WebSocketDisconnect:
                logger.info(f"Client déconnecté de la session simple {session_id}")
                connection_active = False
                break
            except Exception as e:
                logger.error(f"Erreur lors du traitement du message: {e}")
                # Envoyer un message d'erreur au client si possible
                try:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Erreur lors du traitement du message: {str(e)}"
                    })
                except:
                    # Si l'envoi échoue, la connexion est probablement fermée
                    connection_active = False
                    break
    
    except WebSocketDisconnect:
        logger.info(f"Client déconnecté de la session simple {session_id}")
    
    except Exception as e:
        logger.error(f"Erreur WebSocket simple: {e}", exc_info=True)
    
    finally:
        # Toujours nettoyer la connexion, quelle que soit la raison de la sortie
        logger.info(f"Nettoyage de la connexion pour session {session_id}")
        try:
            await orchestrator.disconnect_client(session_id)
        except Exception as cleanup_error:
            logger.error(f"Erreur lors du nettoyage de la connexion: {cleanup_error}")
