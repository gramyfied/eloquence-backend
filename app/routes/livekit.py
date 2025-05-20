from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from livekit import api # Correction basée sur la documentation Context7 (nécessite livekit-api)
import os
import logging # Ajout pour le log
# from datetime import timedelta # Nécessaire si vous voulez spécifier un TTL personnalisé

# Configuration LiveKit (à externaliser dans core.config.py idéalement)
LIVEKIT_HOST = os.environ.get("LIVEKIT_HOST", "wss://livekit.xn--loquence-90a.com")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "eloquence_secure_api_key_for_livekit_server")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "eloquence_secure_secret_key_with_at_least_32_characters_for_security")

router = APIRouter()
logger = logging.getLogger(__name__) # Ajout pour le log

class TokenRequest(BaseModel):
    room_name: str
    participant_identity: str
    participant_name: str | None = None
    can_publish: bool = True
    can_subscribe: bool = True
    can_publish_data: bool = True
    is_hidden_participant: bool = False # Pour les agents IA

@router.post("/token", summary="Generate LiveKit Access Token")
async def generate_livekit_token(request_body: TokenRequest = Body(...)):
    """
    Génère un token d'accès pour qu'un participant rejoigne une salle LiveKit.
    """
    logger.info(f"Requête /livekit/token reçue avec body: {request_body.model_dump_json(indent=2)}") # Log du corps de la requête

    if not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        raise HTTPException(status_code=500, detail="LiveKit API key or secret is not configured.")

    # Définir les permissions pour le token
    video_grants = api.VideoGrants(
        room_join=True,
        room_create=False, # Généralement, les utilisateurs ne créent pas de salles via token
        room=request_body.room_name,
        can_publish=request_body.can_publish,
        can_subscribe=request_body.can_subscribe,
        can_publish_data=request_body.can_publish_data,
        hidden=request_body.is_hidden_participant
        # room_admin=False, # À utiliser avec prudence
        # recorder=False # Mettre à True si ce token est pour un enregistreur
    )

    access_token_builder = api.AccessToken(api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
    
    token = access_token_builder.with_identity(request_body.participant_identity) \
                                .with_name(request_body.participant_name or request_body.participant_identity) \
                                .with_grants(video_grants) \
                                .to_jwt()
                                # .with_ttl(timedelta(hours=1)) # Optionnel: définir la durée de validité

    return {"access_token": token}

# Vous pourriez ajouter d'autres routes ici, par exemple pour lister les salles,
# expulser des participants, etc., en utilisant LiveKitAPI.
# from livekit.api import LiveKitAPI
# lk_api_client = LiveKitAPI(host=LIVEKIT_HOST_FOR_API, api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
# Note: LIVEKIT_HOST_FOR_API serait l'URL HTTP/HTTPS du serveur, pas WSS, par ex. http://localhost:7880