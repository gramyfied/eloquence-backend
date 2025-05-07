"""
Service pour interagir avec les modèles de langage (LLM).
"""

import logging
import json
from typing import Dict, List, Optional, Any
import aiohttp

from core.config import settings
from core.latency_monitor import measure_latency, STEP_LLM_GENERATE

logger = logging.getLogger(__name__)

class LlmService:
    """
    Service pour interagir avec les modèles de langage (LLM).
    """
    def __init__(self):
        self.api_url = settings.LLM_API_URL
        # Utiliser LLM_API_KEY s'il existe, sinon None
        self.api_key = getattr(settings, 'LLM_API_KEY', None)
        self.model = settings.LLM_MODEL_NAME  # Utiliser LLM_MODEL_NAME au lieu de LLM_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
        self.timeout = aiohttp.ClientTimeout(total=settings.LLM_TIMEOUT_S)
        logger.info(f"Initialisation du service LLM avec API URL: {self.api_url}")

    @measure_latency(STEP_LLM_GENERATE)
    async def generate(self, prompt: str = None, context: Dict = None, history: List[Dict[str, str]] = None, is_interrupted: bool = False, scenario_context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Génère une réponse du LLM de manière asynchrone.
        Supporte deux interfaces:
        1. Avec prompt et context (interface utilisée par les routes)
        2. Avec history, is_interrupted et scenario_context (interface alternative)
        
        Retourne un dictionnaire avec 'text' et 'emotion'.
        """
        # Préparer les messages pour l'API
        messages = []
        
        # Ajouter un message système
        system_message = "Tu es un coach vocal interactif pour l'application Eloquence. Ton objectif est d'aider l'utilisateur à améliorer son expression orale en français."
        messages.append({"role": "system", "content": system_message})
        
        # Si history est fourni, l'utiliser
        if history:
            for msg in history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        # Sinon, utiliser prompt
        elif prompt:
            messages.append({"role": "user", "content": prompt})
        
        # Préparer les headers et le payload
        headers = {
            "Content-Type": "application/json"
        }
        
        # Ajouter l'en-tête d'autorisation si une clé API est disponible
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
        
        try:
            # Créer une session HTTP asynchrone
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                # Faire la requête POST
                async with session.post(self.api_url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Erreur LLM {response.status}: {error_text}")
                        return {"text": f"Erreur du service LLM: {response.status}", "emotion": "neutre"}
                    
                    # Traiter la réponse
                    response_json = await response.json()
                    
                    # Extraire le texte de la réponse
                    content = response_json.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if not content:
                        logger.error(f"Format de réponse LLM inattendu: {response_json}")
                        return {"text": "Erreur: format de réponse inattendu", "emotion": "neutre"}
                    
                    # Extraire l'émotion du texte (si présente)
                    emotion = "neutre"  # Valeur par défaut
                    emotion_markers = ["[EMOTION:", "[ÉMOTION:"]
                    for marker in emotion_markers:
                        if marker in content:
                            start_idx = content.find(marker)
                            end_idx = content.find("]", start_idx)
                            if end_idx > start_idx:
                                emotion_text = content[start_idx + len(marker):end_idx].strip()
                                emotion = emotion_text
                                # Supprimer le tag d'émotion du texte
                                content = content[:start_idx].strip() + content[end_idx + 1:].strip()
                                break
                    
                    return {"text": content, "emotion": emotion}
        except aiohttp.ClientError as e:
            logger.error(f"Erreur de connexion au service LLM: {e}")
            return {"text": f"Erreur de connexion au service LLM: {str(e)}", "emotion": "neutre"}
        except Exception as e:
            logger.error(f"Erreur lors de la génération LLM: {e}")
            return {"text": f"Erreur du service LLM: {str(e)}", "emotion": "neutre"}
