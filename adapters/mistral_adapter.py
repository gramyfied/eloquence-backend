import os
import requests
import logging
import json
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class MistralAdapter:
    """Adaptateur pour utiliser le service Mistral existant avec LiveKit Agents."""
    
    def __init__(self, url: Optional[str] = None):
        """Initialise l'adaptateur Mistral.
        
        Args:
            url: URL du service Mistral. Si None, utilise la variable d'environnement.
        """
        self.url = url or os.environ.get("MISTRAL_URL", "http://localhost:8082")
        logger.info(f"Initialisation de l'adaptateur Mistral avec URL: {self.url}")
    
    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Génère une réponse à partir d'un prompt.
        
        Args:
            prompt: Texte d'entrée
            system_prompt: Prompt système optionnel
            
        Returns:
            Dictionnaire contenant la réponse générée et les métadonnées
        """
        try:
            # Préparer les données pour l'API Mistral existante
            data = {
                'prompt': prompt,
                'system_prompt': system_prompt,
                'max_tokens': 1000,
                'temperature': 0.7,
            }
            
            # Appeler l'API Mistral
            logger.info(f"Envoi du prompt au service Mistral: {prompt[:50]}...")
            response = requests.post(f"{self.url}/generate", json=data)
            response.raise_for_status()
            
            # Traiter la réponse
            result = response.json()
            response_text = result.get('text', '')
            logger.info(f"Réponse reçue de Mistral: {response_text[:50]}...")
            
            # Extraire l'émotion si présente dans la réponse
            emotion = "neutral"
            emotion_markers = ["[EMOTION:", "[ÉMOTION:"]
            
            for marker in emotion_markers:
                if marker in response_text:
                    start_idx = response_text.find(marker)
                    end_idx = response_text.find("]", start_idx)
                    if end_idx > start_idx:
                        emotion_text = response_text[start_idx + len(marker):end_idx].strip()
                        emotion = emotion_text
                        # Supprimer le tag d'émotion du texte
                        response_text = response_text[:start_idx].strip() + response_text[end_idx + 1:].strip()
                        break
            
            return {
                "text": response_text,
                "emotion": emotion,
                "tokens": result.get('tokens', 0)
            }
        except Exception as e:
            logger.error(f"Erreur lors de la génération avec Mistral: {e}")
            return {
                "text": "Je suis désolé, je n'ai pas pu générer de réponse.",
                "emotion": "neutral",
                "tokens": 0
            }