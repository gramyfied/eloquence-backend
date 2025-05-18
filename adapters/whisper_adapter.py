import os
import requests
import logging
import numpy as np
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class WhisperAdapter:
    """Adaptateur pour utiliser le service Whisper existant avec LiveKit Agents."""
    
    def __init__(self, url: Optional[str] = None):
        """Initialise l'adaptateur Whisper.
        
        Args:
            url: URL du service Whisper. Si None, utilise la variable d'environnement.
        """
        self.url = url or os.environ.get("WHISPER_URL", "http://localhost:8081")
        logger.info(f"Initialisation de l'adaptateur Whisper avec URL: {self.url}")
    
    async def transcribe(self, audio_data: np.ndarray, sample_rate: int = 16000) -> Dict[str, Any]:
        """Transcrit l'audio en texte.
        
        Args:
            audio_data: Données audio sous forme de tableau numpy
            sample_rate: Taux d'échantillonnage de l'audio
            
        Returns:
            Dictionnaire contenant la transcription et les métadonnées
        """
        try:
            # Vérifier que l'audio n'est pas vide ou silencieux
            if len(audio_data) == 0 or np.max(np.abs(audio_data)) < 0.01:
                logger.warning("Audio vide ou silencieux détecté")
                return {"text": "", "language": "fr", "segments": []}
            
            # Convertir l'audio en PCM 16-bit
            audio_int16 = (audio_data * 32767).astype(np.int16)
            audio_bytes = audio_int16.tobytes()
            
            # Préparer les données pour l'API Whisper existante
            files = {'audio': ('audio.wav', audio_bytes, 'audio/wav')}
            
            # Appeler l'API Whisper
            logger.info(f"Envoi de {len(audio_bytes)} bytes au service Whisper")
            response = requests.post(f"{self.url}/transcribe", files=files)
            response.raise_for_status()
            
            # Traiter la réponse
            result = response.json()
            logger.info(f"Transcription reçue: {result.get('text', '')[:50]}...")
            
            return {
                "text": result.get('text', ''),
                "language": result.get('language', 'fr'),
                "segments": result.get('segments', [])
            }
        except Exception as e:
            logger.error(f"Erreur lors de la transcription avec Whisper: {e}")
            return {"text": "", "language": "fr", "segments": []}