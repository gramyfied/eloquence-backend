"""
Service de streaming TTS pour l'application Eloquence.
Fournit des fonctionnalités de synthèse vocale en streaming.
"""

import asyncio
import logging
import aiohttp
from typing import Optional, AsyncGenerator, Dict, Any

from core.config import settings
from services.tts_service import TtsService
from services.tts_cache_service import tts_cache_service

logger = logging.getLogger(__name__)

class TtsStreamService(TtsService):
    """
    Extension du service TTS avec des fonctionnalités de streaming.
    Hérite du service TTS de base et ajoute des méthodes de streaming.
    """
    
    def __init__(self):
        super().__init__()
        self._active_generations = {}  # Dictionnaire pour suivre les tâches actives par session_id
    
    async def synthesize_stream(
        self, 
        text: str, 
        session_id: str = None, 
        emotion: Optional[str] = None, 
        language: str = "fr"
    ) -> AsyncGenerator[bytes, None]:
        """
        Synthétise le texte en audio et retourne un générateur asynchrone de chunks audio.
        
        Args:
            text: Le texte à synthétiser
            session_id: ID de session pour le suivi (optionnel)
            emotion: L'émotion à utiliser pour la synthèse (optionnel)
            language: La langue du texte (par défaut: "fr")
            
        Yields:
            Des chunks audio au format bytes
        """
        logger.info(f"Synthèse TTS streaming pour session {session_id}: {text[:50]}...")
        
        # Stocker la tâche courante si un session_id est fourni
        current_task = asyncio.current_task()
        if session_id:
            self._active_generations[session_id] = current_task
        
        try:
            # Si speaker_id n'est pas fourni, utiliser l'émotion pour le déterminer
            speaker_id = self._get_speaker_id(emotion)
            
            # Générer la clé de cache
            cache_key = tts_cache_service.generate_cache_key(
                text=text,
                language=language,
                speaker_id=speaker_id,
                emotion=emotion
            )
            
            # 1. Vérifier le cache
            cached_audio = await tts_cache_service.get_audio(cache_key)
            if cached_audio:
                logger.info(f"Cache TTS HIT pour session {session_id}, texte: {text[:20]}...")
                # Streamer depuis le cache
                chunk_size = 4096  # Taille des chunks à envoyer
                for i in range(0, len(cached_audio), chunk_size):
                    # Vérifier si la tâche a été annulée
                    if current_task.cancelled():
                        logger.info(f"Génération TTS interrompue pour session {session_id} (depuis cache)")
                        break
                    
                    yield cached_audio[i:i+chunk_size]
                    await asyncio.sleep(0.01)  # Délai réduit pour diminuer la latence
                
                return
            
            logger.info(f"Cache TTS MISS pour session {session_id}, texte: {text[:20]}...")
            
            # 2. Appel API TTS si pas dans le cache
            payload = {
                "text": text,
                "speaker_id": speaker_id,
                "language_id": language,
                "response_format": "wav"
            }
            
            # Créer une session HTTP asynchrone
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                # Faire la requête POST
                logger.info(f"Envoi de la requête TTS à {self.api_url} pour session {session_id}")
                async with session.post(self.api_url, json=payload) as response:
                    if response.status == 200:
                        # Lire toutes les données audio
                        audio_data = await response.read()
                        logger.info(f"Réponse TTS reçue: {len(audio_data)} bytes pour session {session_id}")
                        
                        # 3. Mettre en cache si réussi
                        if audio_data:
                            asyncio.create_task(
                                tts_cache_service.set_audio(
                                    cache_key, 
                                    audio_data, 
                                    settings.TTS_CACHE_EXPIRATION_S
                                )
                            )
                            logger.info(f"Mise en cache TTS programmée pour session {session_id}")
                        
                        # 4. Streamer l'audio
                        chunk_size = 4096  # Taille des chunks à envoyer
                        for i in range(0, len(audio_data), chunk_size):
                            # Vérifier si la tâche a été annulée
                            if current_task.cancelled():
                                logger.info(f"Génération TTS interrompue pour session {session_id} (depuis API)")
                                break
                                
                            yield audio_data[i:i+chunk_size]
                            await asyncio.sleep(0.01)  # Délai réduit pour diminuer la latence
                    else:
                        error_text = await response.text()
                        logger.error(f"Erreur API TTS ({response.status}) pour session {session_id}: {error_text}")
                        # Retourner un audio vide en cas d'erreur
                        yield b""
        except asyncio.CancelledError:
            logger.info(f"Tâche TTS annulée pour session {session_id}")
            raise
        except aiohttp.ClientError as e:
            logger.error(f"Erreur client HTTP lors de l'appel TTS pour session {session_id}: {e}")
            yield b""
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la synthèse TTS pour session {session_id}: {e}")
            yield b""
        finally:
            # Nettoyer la référence à la tâche
            if session_id and session_id in self._active_generations:
                del self._active_generations[session_id]
    
    async def stop_generation(self, session_id: str) -> bool:
        """
        Arrête la génération TTS en cours pour une session donnée.
        
        Args:
            session_id: ID de la session pour laquelle arrêter la génération
            
        Returns:
            bool: True si l'arrêt a réussi, False sinon
        """
        logger.info(f"Arrêt de la génération TTS pour la session {session_id}")
        
        if session_id in self._active_generations:
            task = self._active_generations[session_id]
            task.cancel()
            logger.info(f"Tâche TTS annulée pour session {session_id}")
            return True
        else:
            logger.warning(f"Aucune tâche TTS active trouvée pour session {session_id}")
            return False

# Créer une instance singleton
tts_stream_service = TtsStreamService()