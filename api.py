import os
import uuid
import logging
import subprocess
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import livekit
from livekit import RoomServiceClient

# Configurer le logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("eloquence-api")

# Charger les variables d'environnement
load_dotenv(dotenv_path=".env.local")

# Configuration LiveKit
LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")

# Créer l'application FastAPI
app = FastAPI(title="Eloquence API", version="1.0.0")

# Configurer CORS pour permettre les requêtes depuis le frontend Flutter
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # À remplacer par les origines spécifiques en production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Client LiveKit API
livekit_client = RoomServiceClient(
    LIVEKIT_URL,
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET
)

# Modèles de données
class SessionRequest(BaseModel):
    user_id: str
    scenario_id: Optional[str] = None
    language: str = "fr"
    goal: Optional[str] = None
    agent_profile_id: Optional[str] = None
    is_multi_agent: bool = False

class SessionResponse(BaseModel):
    session_id: str
    room_name: str
    token: str
    url: str

# Fonction de vérification d'API key
async def verify_api_key(api_key: str = Header(..., alias="X-API-Key")):
    expected_key = os.environ.get("API_KEY", "default-key")
    if api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key

# Routes
@app.get("/")
async def root():
    return {"message": "Eloquence API", "version": "1.0.0"}

@app.post("/api/sessions", response_model=SessionResponse)
async def create_session(request: SessionRequest, api_key: str = Depends(verify_api_key)):
    """Crée une nouvelle session LiveKit pour l'application Eloquence."""
    try:
        # Générer un ID de session unique
        session_id = str(uuid.uuid4())
        
        # Créer un nom de room unique basé sur l'ID de session
        room_name = f"eloquence-{session_id}"
        
        # Créer la room LiveKit
        await livekit_client.create_room(room_name)
        logger.info(f"Room LiveKit créée: {room_name}")
        
        # Créer un token pour l'utilisateur
        token = livekit.tokens.AccessToken(
            LIVEKIT_API_KEY,
            LIVEKIT_API_SECRET,
            identity=request.user_id,
            name=f"User {request.user_id}"
        )
        token.add_grant(
            livekit.tokens.VideoGrant(
                room=room_name,
                room_join=True,
                can_publish=True,
                can_subscribe=True
            )
        )
        
        # Démarrer l'agent en arrière-plan
        # Note: Dans un environnement de production, cela serait géré par systemd
        agent_cmd = [
            "python", "-m", "livekit.agents.cli", "run",
            "--agent-path", "agent.py:EloquenceAgent",
            "--url", LIVEKIT_URL,
            "--api-key", LIVEKIT_API_KEY,
            "--api-secret", LIVEKIT_API_SECRET,
            "--room", room_name
        ]
        
        # Lancer le processus en arrière-plan
        subprocess.Popen(agent_cmd)
        logger.info(f"Agent Eloquence démarré pour la room: {room_name}")
        
        return SessionResponse(
            session_id=session_id,
            room_name=room_name,
            token=token.to_jwt(),
            url=LIVEKIT_URL
        )
    
    except Exception as e:
        logger.error(f"Erreur lors de la création de la session: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la création de la session: {str(e)}")

@app.delete("/api/sessions/{session_id}")
async def end_session(session_id: str, api_key: str = Depends(verify_api_key)):
    """Termine une session LiveKit."""
    try:
        # Construire le nom de la room à partir de l'ID de session
        room_name = f"eloquence-{session_id}"
        
        # Supprimer la room LiveKit
        await livekit_client.delete_room(room_name)
        logger.info(f"Room LiveKit supprimée: {room_name}")
        
        return {"status": "success", "message": f"Session {session_id} terminée avec succès"}
    
    except Exception as e:
        logger.error(f"Erreur lors de la terminaison de la session: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la terminaison de la session: {str(e)}")

# Démarrer le serveur si exécuté directement
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8083)