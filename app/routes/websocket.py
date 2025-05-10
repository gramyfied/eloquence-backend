"""
Routes WebSocket pour l'application Eloquence.
Gère les connexions WebSocket pour le streaming audio bidirectionnel.
"""

import logging
import asyncio
import time
from datetime import datetime

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
    logger.info(f"[WS] Nouvelle connexion WebSocket entrante pour session {session_id}")
    
    # Statistiques de connexion
    connection_stats = {
        "connected_at": datetime.now(),
        "last_activity": time.time(),
        "message_count": 0,
        "reconnect_count": 0
    }
    
    try:
        # Vérifier que la session existe
        # Note: Dans une implémentation réelle, il faudrait vérifier que l'utilisateur
        # a le droit d'accéder à cette session
        
        # Accepter la connexion WebSocket
        await orchestrator.connect_client(websocket, session_id)
        logger.info(f"[WS] Connexion WebSocket acceptée pour session {session_id}")
        
        # Boucle de traitement des messages
        while True:
            # Mise à jour des statistiques
            connection_stats["last_activity"] = time.time()
            connection_stats["message_count"] += 1
            
            # Log périodique des statistiques (tous les 10 messages)
            if connection_stats["message_count"] % 10 == 0:
                duration = time.time() - connection_stats["connected_at"].timestamp()
                logger.info(f"[WS] Statistiques session {session_id}: "
                           f"durée={duration:.1f}s, "
                           f"messages={connection_stats['message_count']}, "
                           f"reconnexions={connection_stats['reconnect_count']}")
            
            logger.info(f"[WS] En attente de message WebSocket pour session {session_id}...")
            await orchestrator.process_websocket_message(websocket, session_id)
            logger.info(f"[WS] Message WebSocket traité pour session {session_id}.")
    
    except WebSocketDisconnect:
        logger.info(f"[WS] Client déconnecté de la session {session_id}")
        await orchestrator.disconnect_client(session_id)
    
    except Exception as e:
        logger.error(f"[WS] Erreur WebSocket: {e}", exc_info=True)
        # Tenter de fermer proprement
        try:
            await orchestrator.disconnect_client(session_id)
        except:
            pass

@router.websocket("/ws/resilient/{session_id}")
async def resilient_websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    db: AsyncSession = Depends(get_db)
):
    """
    Point d'entrée WebSocket avec reconnexion automatique.
    
    Cette route gère automatiquement les reconnexions en cas de déconnexion temporaire.
    Elle maintient l'état de la session même en cas de déconnexion.
    """
    # Statistiques de connexion
    connection_stats = {
        "connected_at": datetime.now(),
        "last_activity": time.time(),
        "message_count": 0,
        "reconnect_count": 0,
        "last_error": None,
        "is_active": True
    }
    
    logger.info(f"[WS-RESILIENT] Nouvelle connexion WebSocket résiliente pour session {session_id}")
    
    # Accepter la connexion initiale
    try:
        await orchestrator.connect_client(websocket, session_id)
        logger.info(f"[WS-RESILIENT] Connexion WebSocket résiliente acceptée pour session {session_id}")
        
        # Boucle principale avec gestion de reconnexion
        while connection_stats["is_active"]:
            try:
                # Mise à jour des statistiques
                connection_stats["last_activity"] = time.time()
                connection_stats["message_count"] += 1
                
                # Log périodique des statistiques
                if connection_stats["message_count"] % 10 == 0:
                    duration = time.time() - connection_stats["connected_at"].timestamp()
                    logger.info(f"[WS-RESILIENT] Statistiques session {session_id}: "
                               f"durée={duration:.1f}s, "
                               f"messages={connection_stats['message_count']}, "
                               f"reconnexions={connection_stats['reconnect_count']}")
                
                # Traitement du message
                logger.info(f"[WS-RESILIENT] En attente de message pour session {session_id}...")
                await orchestrator.process_websocket_message(websocket, session_id)
                logger.info(f"[WS-RESILIENT] Message traité pour session {session_id}")
                
                # Réinitialiser le compteur d'erreurs si tout va bien
                connection_stats["last_error"] = None
                
            except WebSocketDisconnect:
                # Le client s'est déconnecté, mais nous gardons la session active
                logger.warning(f"[WS-RESILIENT] Déconnexion détectée pour session {session_id}, "
                              f"attente de reconnexion...")
                
                # Notifier l'orchestrateur de la déconnexion mais ne pas fermer la session
                # Cela permet de conserver l'état de la session
                await orchestrator.client_disconnected(session_id, keep_session=True)
                
                # Attendre une reconnexion
                try:
                    # Attendre que le client se reconnecte (timeout de 30 secondes)
                    reconnect_timeout = 30
                    reconnect_start = time.time()
                    
                    while time.time() - reconnect_start < reconnect_timeout:
                        # Vérifier si le client s'est reconnecté
                        if session_id in orchestrator.connected_clients:
                            websocket = orchestrator.connected_clients[session_id]
                            connection_stats["reconnect_count"] += 1
                            logger.info(f"[WS-RESILIENT] Client reconnecté pour session {session_id} "
                                       f"(reconnexion #{connection_stats['reconnect_count']})")
                            break
                        
                        # Attendre un peu avant de vérifier à nouveau
                        await asyncio.sleep(1)
                    
                    # Si le timeout est dépassé, terminer la session
                    if time.time() - reconnect_start >= reconnect_timeout:
                        logger.warning(f"[WS-RESILIENT] Timeout de reconnexion pour session {session_id}, "
                                      f"fermeture de la session")
                        connection_stats["is_active"] = False
                        await orchestrator.disconnect_client(session_id)
                        break
                    
                except Exception as reconnect_error:
                    logger.error(f"[WS-RESILIENT] Erreur lors de l'attente de reconnexion: {reconnect_error}",
                                exc_info=True)
                    connection_stats["is_active"] = False
                    await orchestrator.disconnect_client(session_id)
                    break
            
            except Exception as e:
                # Autre erreur, logger et continuer
                logger.error(f"[WS-RESILIENT] Erreur lors du traitement du message: {e}", exc_info=True)
                connection_stats["last_error"] = str(e)
                
                # Attendre un peu avant de réessayer pour éviter une boucle d'erreurs trop rapide
                await asyncio.sleep(1)
    
    except Exception as init_error:
        # Erreur lors de l'initialisation
        logger.error(f"[WS-RESILIENT] Erreur lors de l'initialisation de la connexion: {init_error}",
                    exc_info=True)
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
        # Accepter la connexion WebSocket
        await orchestrator.connect_client(websocket, session_id)
        logger.info(f"Connexion WebSocket de débogage acceptée pour session {session_id}")
        
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
