from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from typing import Dict
import json # Importer json

# Importer get_db
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {} # session_id: websocket

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket connecté pour session: {session_id}")

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"WebSocket déconnecté pour session: {session_id}")

    async def send_personal_message(self, message: str, session_id: str):
        if session_id in self.active_connections:
            websocket = self.active_connections[session_id]
            await websocket.send_text(message)

    async def send_binary(self, data: bytes, session_id: str):
         if session_id in self.active_connections:
            websocket = self.active_connections[session_id]
            await websocket.send_bytes(data)

    # Potentiellement d'autres méthodes pour envoyer des JSON structurés, etc.

manager = ConnectionManager()

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    db: AsyncSession = Depends(get_db) # Injecter la session DB
):
    # Importer l'orchestrateur localement pour éviter les importations circulaires
    from core.orchestrator import orchestrator
    
    # Créer/Récupérer la session dans l'orchestrateur ET la DB
    session_state = await orchestrator.get_or_create_session(session_id, db)
    if not session_state:
        # Si la création échoue (ex: erreur DB), fermer la connexion
        logger.error(f"Impossible de créer ou récupérer la session {session_id} dans la DB.")
        await websocket.close(code=1011) # Internal Error
        return

    await manager.connect(websocket, session_id)
    try:
        while True:
            # Recevoir les données (peut être binaire pour l'audio ou texte/JSON pour contrôle)
            data = await websocket.receive()

            if "bytes" in data:
                audio_chunk = data["bytes"]
                # logger.debug(f"Session {session_id}: Reçu chunk audio de {len(audio_chunk)} bytes")
                # Passer la session DB à process_audio_chunk si nécessaire (pas pour l'instant)
                # Importer l'orchestrateur localement si nécessaire
                await orchestrator.process_audio_chunk(session_id, audio_chunk, db)

            elif "text" in data:
                message_text = data["text"]
                logger.info(f"Session {session_id}: Reçu message texte/JSON: {message_text}")
                try:
                    message_json = json.loads(message_text)
                    if message_json.get("type") == "control":
                        event = message_json.get("event")
                        if event == "user_interrupt_start":
                             # Importer l'orchestrateur localement si nécessaire
                             await orchestrator.handle_interruption(session_id)
                        elif event == "user_speech_end":
                             # Optionnel: l'utilisateur signale explicitement la fin
                             logger.info(f"Session {session_id}: Signal user_speech_end reçu.")
                             # On pourrait forcer handle_end_of_speech ici si le VAD ne l'a pas déjà fait
                             # await orchestrator.handle_end_of_speech(session_id, db)
                        else:
                             logger.warning(f"Session {session_id}: Événement de contrôle inconnu: {event}")
                except json.JSONDecodeError:
                    logger.warning(f"Session {session_id}: Message texte reçu n'est pas un JSON valide: {message_text}")
                # Traiter d'autres types de messages texte si nécessaire

    except WebSocketDisconnect:
        logger.info(f"WebSocket déconnecté pour session {session_id}.")
        manager.disconnect(session_id)
        # Importer l'orchestrateur localement si nécessaire
        await orchestrator.cleanup_session(session_id, db) # Passer la session DB
    except Exception as e:
        logger.error(f"Erreur WebSocket pour session {session_id}: {e}", exc_info=True)
        manager.disconnect(session_id)
        # Importer l'orchestrateur localement si nécessaire
        await orchestrator.cleanup_session(session_id, db) # Passer la session DB même en cas d'erreur
