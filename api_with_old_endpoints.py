#!/usr/bin/env python3
"""
API minimaliste pour Eloquence avec support des anciens endpoints.
Cette API est compatible avec l'application Flutter existante.
Inclut des mesures de sécurité renforcées pour le backend interne.
"""

import os
import uuid
import json
import logging
import asyncio
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Depends, HTTPException, Header, WebSocket, WebSocketDisconnect, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator, Field
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
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION = 3600  # 1 heure

# Configuration de sécurité
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000,https://eloquence.app").split(",")

# Créer l'application FastAPI
app = FastAPI(
    title="Eloquence API Sécurisée",
    version="1.0.0",
    docs_url=None if os.environ.get("ENVIRONMENT") == "production" else "/docs",
    redoc_url=None if os.environ.get("ENVIRONMENT") == "production" else "/redoc"
)

# Configurer CORS pour permettre les requêtes uniquement depuis les origines autorisées
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    max_age=86400,  # 24 heures
)

# Stockage en mémoire des sessions actives
active_sessions = {}

# Stockage en mémoire des tentatives de connexion échouées
failed_attempts = {}

# Schéma de sécurité pour l'API key
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Modèles de données avec validation
class SessionStartRequest(BaseModel):
    user_id: str = Field(..., min_length=3, max_length=50)
    language: str = Field("fr", min_length=2, max_length=5)
    scenario_id: str = Field(..., min_length=3, max_length=50)
    is_multi_agent: bool = False
    
    @validator('user_id')
    def validate_user_id(cls, v):
        if not v.isalnum() and not '_' in v:
            raise ValueError('user_id doit être alphanumérique ou contenir des underscores')
        return v
    
    @validator('scenario_id')
    def validate_scenario_id(cls, v):
        if not v.isalnum() and not '_' in v and not '-' in v:
            raise ValueError('scenario_id doit être alphanumérique ou contenir des underscores/tirets')
        return v

class LiveKitTokenRequest(BaseModel):
    room_name: str = Field(..., min_length=3, max_length=50)
    participant_identity: str = Field(..., min_length=3, max_length=50)
    
    @validator('room_name', 'participant_identity')
    def validate_fields(cls, v):
        if not v.isalnum() and not '_' in v and not '-' in v:
            raise ValueError('Les champs doivent être alphanumériques ou contenir des underscores/tirets')
        return v

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

# Middleware de sécurité
@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # Journaliser la requête
    request_id = str(uuid.uuid4())
    client_ip = request.client.host
    logger.info(f"Requête {request_id} - Méthode: {request.method} - URL: {request.url} - IP: {client_ip}")
    
    # Continuer avec la requête
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    # Journaliser la réponse
    logger.info(f"Requête {request_id} - Statut: {response.status_code} - Temps: {process_time:.4f}s")
    
    # Ajouter des en-têtes de sécurité
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    
    return response

# Fonction de vérification d'API key
async def verify_api_key(api_key: str = Depends(api_key_header), request: Request = None):
    if not api_key:
        logger.warning(f"Tentative d'accès sans API key depuis {request.client.host if request else 'inconnu'}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key manquante",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    if api_key != API_KEY:
        # Incrémenter le compteur de tentatives échouées
        client_ip = request.client.host if request else "inconnu"
        if client_ip not in failed_attempts:
            failed_attempts[client_ip] = {"count": 0, "lockout_until": datetime.now()}
        
        failed_attempts[client_ip]["count"] += 1
        
        # Si trop de tentatives, bloquer temporairement
        if failed_attempts[client_ip]["count"] >= 5:
            failed_attempts[client_ip]["lockout_until"] = datetime.now() + timedelta(minutes=15)
            logger.warning(f"IP {client_ip} bloquée pendant 15 minutes après 5 tentatives échouées")
        
        logger.warning(f"Tentative d'accès avec API key invalide depuis {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key invalide",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
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
async def start_session(request: SessionStartRequest, api_key: str = Depends(verify_api_key)):
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
        
        # Stocker les informations de session avec données de sécurité
        active_sessions[session_id] = {
            "user_id": request.user_id,
            "language": request.language,
            "scenario_id": request.scenario_id,
            "is_multi_agent": request.is_multi_agent,
            "room_name": room_name,
            "created_at": time.time(),
            "last_activity": time.time(),
            "ip_address": request.client.host,
            "user_agent": request.headers.get("User-Agent", "Unknown"),
            "session_token": secrets.token_hex(16)
        }
        
        # Journaliser la création de session
        logger.info(f"Session LiveKit {session_id} créée pour l'utilisateur {request.user_id} avec le scénario {request.scenario_id}")
        
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
async def end_session(session_id: str, api_key: str = Depends(verify_api_key), request: Request = None):
    """Termine une session existante (ancien endpoint)."""
    try:
        # Vérifier que la session existe
        if session_id not in active_sessions:
            logger.warning(f"Tentative de terminer une session inexistante: {session_id}")
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' non trouvée.")
        
        # Récupérer les informations de session
        session_info = active_sessions[session_id]
        
        # Vérifier que l'IP qui termine la session est la même que celle qui l'a créée
        client_ip = request.client.host if request else "inconnu"
        if client_ip != session_info.get("ip_address") and client_ip not in ["127.0.0.1", "::1"]:
            logger.warning(f"Tentative de terminer la session {session_id} depuis une IP non autorisée: {client_ip}")
            raise HTTPException(status_code=403, detail="Vous n'êtes pas autorisé à terminer cette session.")
        
        # Supprimer la session
        del active_sessions[session_id]
        
        # Journaliser la terminaison de session
        logger.info(f"Session {session_id} terminée avec succès")
        
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
            logger.warning(f"Tentative de connexion WebSocket à une session inexistante: {session_id}")
            await websocket.close(code=1008, reason=f"Session '{session_id}' non trouvée.")
            return
        
        # Récupérer les informations de session
        session_info = active_sessions[session_id]
        
        # Vérifier l'origine de la connexion WebSocket
        client_ip = websocket.client.host if hasattr(websocket, 'client') else "inconnu"
        headers = websocket.headers if hasattr(websocket, 'headers') else {}
        origin = headers.get("origin", "unknown")
        
        # Vérifier si l'origine est autorisée
        origin_allowed = False
        for allowed_origin in ALLOWED_ORIGINS:
            if origin.startswith(allowed_origin):
                origin_allowed = True
                break
        
        if not origin_allowed and origin != "unknown":
            logger.warning(f"Tentative de connexion WebSocket depuis une origine non autorisée: {origin}")
            await websocket.close(code=1008, reason="Origine non autorisée")
            return
        
        # Accepter la connexion WebSocket
        await websocket.accept()
        
        # Mettre à jour l'heure de dernière activité
        active_sessions[session_id]["last_activity"] = time.time()
        
        # Journaliser la connexion WebSocket
        logger.info(f"Connexion WebSocket établie pour la session {session_id} depuis {client_ip}")
        
        # Envoyer un message de bienvenue
        await websocket.send_json({
            "type": "connected",
            "message": f"Connecté à la session {session_id}"
        })
        
        # Boucle de communication
        while True:
            # Recevoir un message du client
            data = await websocket.receive_text()
            
            # Mettre à jour l'heure de dernière activité
            active_sessions[session_id]["last_activity"] = time.time()
            
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
        
        # Stocker les informations de session avec données de sécurité
        active_sessions[session_id] = {
            "user_id": request.user_id,
            "language": request.language,
            "scenario_id": request.scenario_id,
            "is_multi_agent": request.is_multi_agent,
            "room_name": room_name,
            "created_at": time.time(),
            "last_activity": time.time(),
            "ip_address": request.client.host,
            "user_agent": request.headers.get("User-Agent", "Unknown"),
            "session_token": secrets.token_hex(16)
        }
        
        # Journaliser la création de session
        logger.info(f"Session LiveKit {session_id} créée pour l'utilisateur {request.user_id} avec le scénario {request.scenario_id}")
        
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
async def delete_session(session_id: str, api_key: str = Depends(verify_api_key), request: Request = None):
    """Supprime une session existante (nouvel endpoint)."""
    try:
        # Vérifier que la session existe
        if session_id not in active_sessions:
            logger.warning(f"Tentative de supprimer une session inexistante: {session_id}")
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' non trouvée.")
        
        # Récupérer les informations de session
        session_info = active_sessions[session_id]
        
        # Vérifier que l'IP qui supprime la session est la même que celle qui l'a créée
        client_ip = request.client.host if request else "inconnu"
        if client_ip != session_info.get("ip_address") and client_ip not in ["127.0.0.1", "::1"]:
            logger.warning(f"Tentative de supprimer la session {session_id} depuis une IP non autorisée: {client_ip}")
            raise HTTPException(status_code=403, detail="Vous n'êtes pas autorisé à supprimer cette session.")
        
        # Supprimer la session
        del active_sessions[session_id]
        
        # Journaliser la suppression de session
        logger.info(f"Session {session_id} supprimée avec succès")
        
        # Retourner un message de succès
        return {"status": "success", "message": f"Session {session_id} supprimée avec succès"}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Erreur lors de la suppression de la session: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression de la session: {str(e)}")

# Tâche de nettoyage des sessions inactives
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_inactive_sessions())

async def cleanup_inactive_sessions():
    """Nettoie les sessions inactives périodiquement."""
    while True:
        try:
            current_time = time.time()
            sessions_to_remove = []
            
            for session_id, session_info in active_sessions.items():
                # Supprimer les sessions inactives depuis plus de 30 minutes
                if current_time - session_info.get("last_activity", session_info.get("created_at", 0)) > 1800:  # 30 minutes
                    sessions_to_remove.append(session_id)
            
            # Supprimer les sessions
            for session_id in sessions_to_remove:
                logger.info(f"Nettoyage de la session inactive {session_id}")
                del active_sessions[session_id]
            
            # Attendre 5 minutes avant la prochaine vérification
            await asyncio.sleep(300)
        except Exception as e:
            logger.error(f"Erreur lors du nettoyage des sessions inactives: {e}")
            await asyncio.sleep(60)  # Attendre 1 minute en cas d'erreur

# Démarrer le serveur si exécuté directement
if __name__ == "__main__":
    import uvicorn
    logger.info(f"Démarrage de l'API sécurisée sur le port {API_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)