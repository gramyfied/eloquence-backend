#!/usr/bin/env python3
"""
API minimaliste pour Eloquence avec support des anciens endpoints.
Cette API est compatible avec l'application Flutter existante.
"""

import os
import uuid
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Depends, HTTPException, Header, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import jwt
import time
import requests

# Configurer le logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("eloquence-api")

# Charger les variables d'environnement
load_dotenv(".env.local")

# Configuration LiveKit
LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")

# Configuration API
API_KEY = os.environ.get("API_KEY", "default-key")
API_PORT = int(os.environ.get("API_PORT", "9090"))  # Utiliser le port 9090 par défaut

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

# Stockage en mémoire des sessions actives
active_sessions = {}

# Modèles de données
class SessionStartRequest(BaseModel):
    user_id: str
    language: str = "fr"
    scenario_id: str
    is_multi_agent: bool = False

class LiveKitTokenRequest(BaseModel):
    room_name: str
    participant_identity: str

class ScenarioModel(BaseModel):
    id: str
    name: str
    description: str
    type: str = "inconnu"
    difficulty: Optional[int] = None
    language: str = "fr"
    tags: List[str] = []
    preview_image: Optional[str] = None

# Scénarios disponibles
scenarios = [
    {
        "id": "coaching_adaptatif",
        "name": "Coaching adaptatif et interactif",
        "description": "Un scénario de coaching qui s'adapte automatiquement aux réponses de l'utilisateur, analysant le ton, le contenu et le niveau de confiance pour fournir un feedback personnalisé.",
        "type": "inconnu",
        "difficulty": None,
        "language": "fr",
        "tags": [],
        "preview_image": None
    },
    {
        "id": "scenario_test_scenario_start",
        "name": "Test Scenario for Start",
        "description": "A test scenario specifically for the start session endpoint.",
        "type": "inconnu",
        "difficulty": None,
        "language": "fr",
        "tags": [],
        "preview_image": None
    },
    {
        "id": "entretien_embauche",
        "name": "Simulation d'entretien d'embauche",
        "description": "Un scénario pour s'entraîner à un entretien d'embauche en français. L'IA joue le rôle du recruteur et pose des questions typiques d'un entretien.",
        "type": "inconnu",
        "difficulty": None,
        "language": "fr",
        "tags": [],
        "preview_image": None
    }
]

# Fonction de vérification d'API key
async def verify_api_key(api_key: str = Header(None, alias="X-API-Key")):
    if api_key != API_KEY and API_KEY != "default-key":
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key

# Routes
@app.get("/")
async def root():
    return {"message": "Bienvenue sur l'API Eloquence Backend"}

@app.get("/api/scenarios/")
async def get_scenarios(language: str = "fr"):
    """Récupère la liste des scénarios disponibles."""
    filtered_scenarios = [s for s in scenarios if s["language"] == language]
    return filtered_scenarios

@app.post("/livekit/token")
async def get_livekit_token(request: LiveKitTokenRequest):
    """Génère un token LiveKit pour une room et un participant."""
    try:
        # Créer un token JWT pour LiveKit
        now = int(time.time())
        token_data = {
            "name": request.participant_identity,
            "video": {
                "roomCreate": False,
                "roomJoin": True,
                "room": request.room_name,
                "canPublish": True,
                "canSubscribe": True,
                "canPublishData": True,
                "hidden": False
            },
            "sub": request.participant_identity,
            "iss": "eloquence_secure_api_key_for_livekit_server",
            "nbf": now,
            "exp": now + 21600  # 6 heures
        }
        
        token = jwt.encode(token_data, LIVEKIT_API_SECRET, algorithm="HS256")
        
        return {"access_token": token}
    except Exception as e:
        logger.error(f"Erreur lors de la génération du token LiveKit: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la génération du token LiveKit: {str(e)}")

@app.post("/api/session/start")
async def start_session(request: SessionStartRequest):
    """Démarre une nouvelle session (ancien endpoint)."""
    try:
        # Vérifier que le scénario existe
        scenario = next((s for s in scenarios if s["id"] == request.scenario_id), None)
        if not scenario:
            raise HTTPException(status_code=404, detail=f"Scénario '{request.scenario_id}' non trouvé.")
        
        # Générer un ID de session unique
        session_id = str(uuid.uuid4())
        
        # Créer une room LiveKit (simulation)
        room_name = f"eloquence-{session_id}"
        
        # Stocker les informations de session
        active_sessions[session_id] = {
            "user_id": request.user_id,
            "language": request.language,
            "scenario_id": request.scenario_id,
            "is_multi_agent": request.is_multi_agent,
            "room_name": room_name,
            "created_at": time.time()
        }
        
        # Générer un message initial basé sur le scénario
        initial_message = ""
        if request.scenario_id == "coaching_adaptatif":
            initial_message = "Bonjour et bienvenue à cette session de coaching vocal adaptatif. Je suis votre coach IA et je vais vous aider à améliorer votre expression orale. Pendant cette session, je vais analyser votre voix, votre ton, votre rythme et le contenu de vos réponses pour vous donner un feedback personnalisé. Commençons par une courte présentation. Pourriez-vous me dire quelques mots sur vous et ce que vous souhaitez améliorer dans votre expression orale ?"
        elif request.scenario_id == "entretien_embauche":
            initial_message = "Bonjour et bienvenue à cette simulation d'entretien d'embauche. Je suis le recruteur et je vais vous poser des questions typiques d'un entretien. Commençons. Pourriez-vous vous présenter et me parler de votre parcours professionnel ?"
        else:
            initial_message = f"Bienvenue à la session '{scenario['name']}'. Comment puis-je vous aider aujourd'hui ?"
        
        # Retourner les informations de session au format attendu par l'application Flutter
        return {
            "session_id": session_id,
            "websocket_url": f"/ws/simple/{session_id}",
            "initial_message": {
                "text": initial_message,
                "audio_url": ""
            }
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Erreur lors du démarrage de la session: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du démarrage de la session: {str(e)}")

@app.post("/api/session/{session_id}/end")
async def end_session(session_id: str):
    """Termine une session existante (ancien endpoint)."""
    try:
        # Vérifier que la session existe
        if session_id not in active_sessions:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' non trouvée.")
        
        # Récupérer les informations de session
        session_info = active_sessions[session_id]
        
        # Supprimer la session
        del active_sessions[session_id]
        
        # Retourner un message de succès
        return {"status": "success", "message": f"Session {session_id} terminée avec succès"}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Erreur lors de la terminaison de la session: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la terminaison de la session: {str(e)}")

@app.websocket("/ws/simple/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """Endpoint WebSocket pour la communication en temps réel (ancien endpoint)."""
    try:
        # Vérifier que la session existe
        if session_id not in active_sessions:
            await websocket.close(code=1008, reason=f"Session '{session_id}' non trouvée.")
            return
        
        # Accepter la connexion WebSocket
        await websocket.accept()
        
        # Envoyer un message de bienvenue
        await websocket.send_json({
            "type": "connected",
            "message": f"Connecté à la session {session_id}"
        })
        
        # Boucle de communication
        while True:
            # Recevoir un message du client
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                
                # Traiter le message
                if message.get("type") == "text":
                    # Simuler une réponse de l'agent
                    response = {
                        "type": "text",
                        "text": f"Réponse à: {message.get('text')}",
                        "audio_url": ""
                    }
                    await websocket.send_json(response)
                elif message.get("type") == "audio":
                    # Simuler une réponse de l'agent
                    response = {
                        "type": "text",
                        "text": "J'ai bien reçu votre message audio.",
                        "audio_url": ""
                    }
                    await websocket.send_json(response)
            except json.JSONDecodeError:
                # Envoyer un message d'erreur
                await websocket.send_json({
                    "type": "error",
                    "message": "Format de message invalide"
                })
    
    except WebSocketDisconnect:
        logger.info(f"Client déconnecté de la session {session_id}")
    except Exception as e:
        logger.error(f"Erreur WebSocket pour la session {session_id}: {e}")
        try:
            await websocket.close(code=1011, reason=f"Erreur interne: {str(e)}")
        except:
            pass

# Nouveaux endpoints (compatibles avec LiveKit)
@app.post("/api/sessions")
async def create_session(request: SessionStartRequest, api_key: str = Depends(verify_api_key)):
    """Crée une nouvelle session (nouvel endpoint)."""
    try:
        # Vérifier que le scénario existe
        scenario = next((s for s in scenarios if s["id"] == request.scenario_id), None)
        if not scenario:
            raise HTTPException(status_code=404, detail=f"Scénario '{request.scenario_id}' non trouvé.")
        
        # Générer un ID de session unique
        session_id = str(uuid.uuid4())
        
        # Créer une room LiveKit
        room_name = f"eloquence-{session_id}"
        
        # Stocker les informations de session
        active_sessions[session_id] = {
            "user_id": request.user_id,
            "language": request.language,
            "scenario_id": request.scenario_id,
            "is_multi_agent": request.is_multi_agent,
            "room_name": room_name,
            "created_at": time.time()
        }
        
        # Générer un token LiveKit
        now = int(time.time())
        token_data = {
            "name": request.user_id,
            "video": {
                "roomCreate": False,
                "roomJoin": True,
                "room": room_name,
                "canPublish": True,
                "canSubscribe": True,
                "canPublishData": True,
                "hidden": False
            },
            "sub": request.user_id,
            "iss": "eloquence_secure_api_key_for_livekit_server",
            "nbf": now,
            "exp": now + 21600  # 6 heures
        }
        
        token = jwt.encode(token_data, LIVEKIT_API_SECRET, algorithm="HS256")
        
        # Retourner les informations de session au format LiveKit
        return {
            "session_id": session_id,
            "room_name": room_name,
            "token": token,
            "url": LIVEKIT_URL
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Erreur lors de la création de la session: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la création de la session: {str(e)}")

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, api_key: str = Depends(verify_api_key)):
    """Supprime une session existante (nouvel endpoint)."""
    try:
        # Vérifier que la session existe
        if session_id not in active_sessions:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' non trouvée.")
        
        # Récupérer les informations de session
        session_info = active_sessions[session_id]
        
        # Supprimer la session
        del active_sessions[session_id]
        
        # Retourner un message de succès
        return {"status": "success", "message": f"Session {session_id} supprimée avec succès"}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Erreur lors de la suppression de la session: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression de la session: {str(e)}")

# Démarrer le serveur si exécuté directement
if __name__ == "__main__":
    import uvicorn
    logger.info(f"Démarrage de l'API sur le port {API_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)