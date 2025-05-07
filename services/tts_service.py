import asyncio
import logging
import json
import aiohttp
from typing import Optional, Dict, Union, List, Any
import redis.asyncio as redis # Pour le cache optionnel

from core.config import settings

logger = logging.getLogger(__name__)

class TtsService:
    """
    Service de Synthèse Vocale (TTS) interagissant avec l'API Coqui TTS.
    """
    def __init__(self):
        # Corriger l'URL de l'API TTS pour éviter la duplication de /api/tts
        if settings.TTS_API_URL.endswith('/api/tts'):
            self.api_url = settings.TTS_API_URL
        else:
            self.api_url = settings.TTS_API_URL.rstrip('/') + "/api/tts"
            
        self.timeout = aiohttp.ClientTimeout(total=60) # Timeout généreux pour TTS
        self.emotion_to_speaker_id: Dict[str, Optional[str]] = {
            "neutre": settings.TTS_SPEAKER_ID_NEUTRAL,
            "encouragement": settings.TTS_SPEAKER_ID_ENCOURAGEMENT,
            "empathie": settings.TTS_SPEAKER_ID_EMPATHY,
            "enthousiasme_modere": settings.TTS_SPEAKER_ID_ENTHUSIASM,
            "curiosite": settings.TTS_SPEAKER_ID_CURIOSITY,
            "reflexion": settings.TTS_SPEAKER_ID_REFLECTION,
            # Ajouter d'autres émotions si configurées
        }
        self.default_speaker_id = settings.TTS_SPEAKER_ID_NEUTRAL or "default" # Fallback
        self.redis_pool = None
        
        # Initialiser le cache Redis si configuré
        if settings.TTS_USE_CACHE:
            try:
                self.redis_pool = redis.ConnectionPool.from_url(
                    f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                    decode_responses=False # Important: stocker les bytes audio bruts
                )
                logger.info("Pool de connexion Redis pour le cache TTS créé.")
            except Exception as e:
                logger.error(f"Impossible de créer le pool Redis pour le cache TTS: {e}. Cache désactivé.")
                self.redis_pool = None

        logger.info(f"Initialisation du service TTS avec API URL: {self.api_url}")

    async def _get_redis_connection(self) -> Optional[redis.Redis]:
        """Obtient une connexion Redis depuis le pool."""
        if not self.redis_pool:
            return None
        try:
            return redis.Redis(connection_pool=self.redis_pool)
        except Exception as e:
            logger.error(f"Impossible d'obtenir une connexion Redis: {e}")
            return None

    def _get_speaker_id(self, emotion: Optional[str]) -> str:
        """Détermine le speaker_id basé sur l'émotion."""
        if emotion and emotion in self.emotion_to_speaker_id:
            speaker_id = self.emotion_to_speaker_id[emotion]
            if speaker_id:
                return speaker_id
        logger.warning(f"Speaker ID non trouvé pour l'émotion '{emotion}'. Utilisation du défaut: {self.default_speaker_id}")
        return self.default_speaker_id

    async def synthesize(self, text: str, speaker_id: str = None, emotion: Optional[str] = None, language: str = "fr") -> bytes:
        """
        Synthétise le texte en audio et retourne les données audio.
        Cette méthode est utilisée par les routes API.
        
        Args:
            text: Le texte à synthétiser
            speaker_id: L'ID du speaker à utiliser (optionnel)
            emotion: L'émotion à utiliser pour la synthèse (optionnel)
            language: La langue du texte (par défaut: "fr")
            
        Returns:
            Les données audio au format bytes
        """
        # Si speaker_id n'est pas fourni, utiliser l'émotion pour le déterminer
        if not speaker_id and emotion:
            speaker_id = self._get_speaker_id(emotion)
        elif not speaker_id:
            speaker_id = self.default_speaker_id
            
        cache_key = f"{settings.TTS_CACHE_PREFIX}{language}:{speaker_id}:{text}"
        redis_conn = await self._get_redis_connection()

        # 1. Vérifier le cache Redis
        if redis_conn:
            try:
                cached_audio = await redis_conn.get(cache_key)
                if cached_audio:
                    logger.info(f"Cache TTS HIT pour texte: {text[:20]}...")
                    await redis_conn.close()
                    return cached_audio
            except Exception as e:
                logger.error(f"Erreur lors de la lecture du cache TTS Redis: {e}")
            finally:
                if redis_conn: 
                    await redis_conn.close()

        logger.info(f"Cache TTS MISS pour texte: {text[:20]}... Appel API: {self.api_url}")

        # 2. Appel API Coqui TTS si pas dans le cache
        payload = {
            "text": text,
            "speaker_id": speaker_id,
            "language_id": language,
            "response_format": "wav"
        }

        audio_data = b""

        try:
            # Créer une session HTTP asynchrone
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                # Faire la requête POST
                async with session.post(self.api_url, json=payload) as response:
                    if response.status == 200:
                        # Lire toutes les données audio
                        audio_data = await response.read()
                        
                        # 3. Mettre en cache si réussi et cache activé
                        if self.redis_pool and audio_data:
                            redis_conn_write = await self._get_redis_connection()
                            if redis_conn_write:
                                try:
                                    logger.debug(f"Tentative de mise en cache TTS: Clé={cache_key}, Taille={len(audio_data)}")
                                    await redis_conn_write.set(cache_key, audio_data, ex=settings.TTS_CACHE_EXPIRATION_S)
                                    logger.info(f"Audio TTS mis en cache (clé: {cache_key})")
                                except Exception as e:
                                    logger.error(f"Erreur lors de l'écriture du cache TTS Redis: {e}")
                                finally:
                                    await redis_conn_write.close()
                    else:
                        error_text = await response.text()
                        logger.error(f"Erreur API TTS ({response.status}): {error_text}")
                        return b""
        except aiohttp.ClientError as e:
            logger.error(f"Erreur client HTTP lors de l'appel TTS: {e}")
            return b""
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la synthèse TTS: {e}")
            return b""

        return audio_data