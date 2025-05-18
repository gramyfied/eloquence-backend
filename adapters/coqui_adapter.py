import os
import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class CoquiAdapter:
    """Adaptateur pour utiliser le service Coqui TTS existant avec LiveKit Agents."""
    
    def __init__(self, url: Optional[str] = None):
        """Initialise l'adaptateur Coqui TTS.
        
        Args:
            url: URL du service Coqui TTS. Si None, utilise la variable d'environnement.
        """
        self.url = url or os.environ.get("COQUI_URL", "http://localhost:8084")
        logger.info(f"Initialisation de l'adaptateur Coqui TTS avec URL: {self.url}")
        
        # Mapping des émotions vers les voix ou styles
        self.emotion_to_voice = {
            "happy": "happy",
            "sad": "sad",
            "angry": "angry",
            "excited": "excited",
            "serious": "serious",
            "thoughtful": "thoughtful",
            "neutral": "neutral"
        }
    
    async def synthesize(self, text: str, emotion: Optional[str] = None) -> Dict[str, Any]:
        """Synthétise du texte en audio.
        
        Args:
            text: Texte à synthétiser
            emotion: Émotion à exprimer
            
        Returns:
            Dictionnaire contenant l'audio synthétisé et les métadonnées
        """
        try:
            # Déterminer la voix/style en fonction de l'émotion
            voice = self.emotion_to_voice.get(emotion, "neutral") if emotion else "neutral"
            
            # Préparer les données pour l'API Coqui TTS existante
            data = {
                'text': text,
                'voice': voice,
                'emotion': emotion
            }
            
            # Appeler l'API Coqui TTS
            logger.info(f"Envoi du texte au service Coqui TTS: {text[:50]}... (émotion: {emotion})")
            response = requests.post(f"{self.url}/synthesize", json=data)
            response.raise_for_status()
            
            # Récupérer l'audio
            audio_data = response.content
            
            # Déterminer le sample rate (par défaut 22050 Hz)
            sample_rate = 22050
            if 'X-Sample-Rate' in response.headers:
                sample_rate = int(response.headers['X-Sample-Rate'])
            
            logger.info(f"Audio synthétisé reçu: {len(audio_data)} bytes, sample rate: {sample_rate} Hz")
            
            return {
                "audio": audio_data,
                "sample_rate": sample_rate,
                "emotion": emotion
            }
        except Exception as e:
            logger.error(f"Erreur lors de la synthèse avec Coqui TTS: {e}")
            # Retourner un audio vide en cas d'erreur
            return {
                "audio": b"",
                "sample_rate": 22050,
                "emotion": emotion
            }