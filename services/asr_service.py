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
            error_msg = "Le modèle ASR n'est pas chargé."
            print(f"ASR_ERROR: {error_msg}")
            logger.critical(f"ASR_ERROR: {error_msg}")
            raise RuntimeError(error_msg)

        try:
            # Transcrire l'audio (numpy array float32)
            # beam_size=5 est une valeur par défaut courante
            print(f"ASR_DEBUG: Appel de self.model.transcribe avec audio_float32 shape={audio_float32.shape}, dtype={audio_float32.dtype}, language={language}")
            logger.critical(f"ASR_DEBUG: Appel de self.model.transcribe avec audio_float32 shape={audio_float32.shape}, dtype={audio_float32.dtype}, language={language}")
            
            segments, info = self.model.transcribe(audio_float32, language=language, beam_size=5)
            
            print(f"ASR_DEBUG: Transcription terminée. Langue détectée: {info.language} avec probabilité {info.language_probability:.2f}")
            logger.critical(f"ASR_DEBUG: Transcription terminée. Langue détectée: {info.language} avec probabilité {info.language_probability:.2f}")
            logger.info(f"Langue détectée: {info.language} avec probabilité {info.language_probability:.2f}")
            
            # Construire le texte complet à partir des segments
            full_text = "".join(segment.text for segment in segments)
            print(f"ASR_DEBUG: Texte transcrit: '{full_text}'")
            logger.critical(f"ASR_DEBUG: Texte transcrit: '{full_text}'")
            logger.debug(f"Texte transcrit: '{full_text}'")
            
            return full_text.strip() # Enlever les espaces superflus au début/fin

        except Exception as e:
            error_msg = f"Erreur pendant la transcription synchrone: {e}"
            print(f"ASR_ERROR: {error_msg}")
            logger.critical(f"ASR_ERROR: {error_msg}")
            logger.error(error_msg, exc_info=True)
            raise # Relancer l'exception pour qu'elle soit capturée par l'appelant async

    async def transcribe(self, audio_bytes: bytes, language: str) -> str:
        """
        Transcrire un segment audio (bytes PCM 16-bit) de manière asynchrone.
        """
        if self.model is None:
            error_msg = "Tentative de transcription alors que le modèle ASR n'est pas chargé."
            print(f"ASR_ERROR: {error_msg}")
            logger.critical(f"ASR_ERROR: {error_msg}")
            logger.error(error_msg)
            raise RuntimeError("Le modèle ASR n'est pas chargé.")

        loop = asyncio.get_running_loop()
        try:
            print(f"ASR_DEBUG: Début de la transcription pour {len(audio_bytes)} bytes audio, langue: {language}")
            logger.critical(f"ASR_DEBUG: Début de la transcription pour {len(audio_bytes)} bytes audio, langue: {language}")
            logger.critical(f"ASR_DEBUG: Type des données audio: {type(audio_bytes)}")
            logger.critical(f"ASR_DEBUG: Premiers octets: {audio_bytes[:20] if len(audio_bytes) > 20 else audio_bytes}")
            
            # 1. Convertir les bytes PCM 16-bit en numpy array float32
            # Utiliser soundfile pour lire depuis la mémoire
            audio_io = io.BytesIO(audio_bytes)
            try:
                audio_data, sample_rate = sf.read(audio_io, dtype='float32')
                print(f"ASR_DEBUG: Audio lu par soundfile: shape={audio_data.shape}, dtype={audio_data.dtype}, sample_rate={sample_rate}")
                logger.critical(f"ASR_DEBUG: Audio lu par soundfile: shape={audio_data.shape}, dtype={audio_data.dtype}, sample_rate={sample_rate}")
            except Exception as sf_error:
                error_msg = f"Erreur lors de la lecture audio avec soundfile: {sf_error}"
                print(f"ASR_ERROR: {error_msg}")
                logger.critical(f"ASR_ERROR: {error_msg}")
                logger.error(error_msg, exc_info=True)
                raise RuntimeError(f"Erreur de lecture audio: {sf_error}")

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
            logger.info(f"Transcription synchrone terminée. Résultat: '{transcription}'")
            return transcription

        except Exception as e:
            logger.error(f"Erreur lors de la transcription asynchrone: {e}", exc_info=True)
            # Retourner une chaîne vide ou relancer l'exception ? Relançons pour l'instant.
            raise RuntimeError(f"Erreur ASR: {e}")
