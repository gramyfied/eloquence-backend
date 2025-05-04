import asyncio
import logging
import io
import soundfile as sf
import numpy as np
from faster_whisper import WhisperModel

from core.config import settings

logger = logging.getLogger(__name__)

class AsrService:
    """
    Service de Reconnaissance Automatique de la Parole (ASR) utilisant faster-whisper.
    """
    def __init__(self):
        self.model_name = settings.ASR_MODEL_NAME
        self.device = settings.ASR_DEVICE
        self.compute_type = settings.ASR_COMPUTE_TYPE
        self.model = None
        logger.info(f"Initialisation du service ASR avec: model={self.model_name}, device={self.device}, compute_type={self.compute_type}")

    async def load_model(self):
        """Charge le modèle faster-whisper."""
        # Cette opération peut être longue, l'exécuter dans un thread séparé
        loop = asyncio.get_running_loop()
        try:
            logger.info(f"Chargement du modèle ASR '{self.model_name}'...")
            self.model = await loop.run_in_executor(
                None, # Utilise le ThreadPoolExecutor par défaut
                lambda: WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
            )
            logger.info(f"Modèle ASR '{self.model_name}' chargé avec succès sur {self.device} ({self.compute_type}).")
        except Exception as e:
            logger.error(f"Erreur lors du chargement du modèle ASR: {e}", exc_info=True)
            raise

    def _transcribe_sync(self, audio_float32: np.ndarray, language: str) -> str:
        """Méthode synchrone pour l'exécution dans le thread."""
        if self.model is None:
            raise RuntimeError("Le modèle ASR n'est pas chargé.")

        try:
            # Transcrire l'audio (numpy array float32)
            # beam_size=5 est une valeur par défaut courante
            segments, info = self.model.transcribe(audio_float32, language=language, beam_size=5)

            logger.info(f"Langue détectée: {info.language} avec probabilité {info.language_probability:.2f}")
            # TODO: Vérifier si info.language correspond à la langue attendue ?

            full_text = "".join(segment.text for segment in segments)
            logger.debug(f"Texte transcrit: '{full_text}'")
            return full_text.strip() # Enlever les espaces superflus au début/fin

        except Exception as e:
            logger.error(f"Erreur pendant la transcription synchrone: {e}", exc_info=True)
            raise # Relancer l'exception pour qu'elle soit capturée par l'appelant async

    async def transcribe(self, audio_bytes: bytes, language: str) -> str:
        """
        Transcrire un segment audio (bytes PCM 16-bit) de manière asynchrone.
        """
        if self.model is None:
            logger.error("Tentative de transcription alors que le modèle ASR n'est pas chargé.")
            raise RuntimeError("Le modèle ASR n'est pas chargé.")

        loop = asyncio.get_running_loop()
        try:
            # 1. Convertir les bytes PCM 16-bit en numpy array float32
            # Utiliser soundfile pour lire depuis la mémoire
            audio_io = io.BytesIO(audio_bytes)
            audio_data, sample_rate = sf.read(audio_io, dtype='float32')

            if sample_rate != 16000:
                # Ceci ne devrait pas arriver si le flux est bien en 16k, mais sécurité
                logger.warning(f"Sample rate ASR inattendu: {sample_rate}. Whisper préfère 16kHz.")
                # TODO: Ré-échantillonner si nécessaire, mais idéalement le flux est déjà correct.
                # Pour l'instant, on continue en espérant que Whisper gère.

            # 2. Exécuter la transcription synchrone dans un thread
            transcription = await loop.run_in_executor(
                None, # Utilise le ThreadPoolExecutor par défaut
                self._transcribe_sync,
                audio_data,
                language
            )
            return transcription

        except Exception as e:
            logger.error(f"Erreur lors de la transcription asynchrone: {e}", exc_info=True)
            # Retourner une chaîne vide ou relancer l'exception ? Relançons pour l'instant.
            raise RuntimeError(f"Erreur ASR: {e}")