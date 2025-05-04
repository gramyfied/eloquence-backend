import asyncio
import logging
import json
import aiohttp
from typing import Optional, Dict
import redis.asyncio as redis # Pour le cache optionnel

from core.config import settings
# Ne plus importer websocket_manager ici
# from app.websocket import manager as websocket_manager

logger = logging.getLogger(__name__)

class TtsService:
    """
    Service de Synthèse Vocale (TTS) interagissant avec l'API Coqui TTS
    et streamant l'audio vers le client via WebSocket.
    """
    def __init__(self):
        self.api_url = settings.TTS_API_URL.rstrip('/') + "/api/tts" # Assurer le bon endpoint
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
        # Dictionnaire pour stocker les tâches asyncio en cours
        self.active_generations: Dict[str, asyncio.Task] = {}
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

    async def stream_synthesize(self, websocket_manager, session_id: str, text: str, emotion: Optional[str], language: str):
        """
        Synthétise le texte et streame l'audio vers le WebSocket de la session.
        Accepte websocket_manager comme argument.
        """
        speaker_id = self._get_speaker_id(emotion)
        cache_key = f"{settings.TTS_CACHE_PREFIX}{language}:{speaker_id}:{text}"
        redis_conn = await self._get_redis_connection()

        # 1. Vérifier le cache Redis
        if redis_conn:
            try:
                cached_audio = await redis_conn.get(cache_key)
                if cached_audio:
                    logger.info(f"Cache TTS HIT pour session {session_id}")
                    await websocket_manager.send_personal_message(json.dumps({"type": "audio_control", "event": "ia_speech_start"}), session_id)
                    # Streamer depuis le cache
                    chunk_size = 2048 # Taille des chunks à envoyer
                    for i in range(0, len(cached_audio), chunk_size):
                        await websocket_manager.send_binary(cached_audio[i:i+chunk_size], session_id)
                        await asyncio.sleep(0.01) # Petit délai pour éviter de saturer le client
                    await websocket_manager.send_personal_message(json.dumps({"type": "audio_control", "event": "ia_speech_end"}), session_id)
                    await redis_conn.close()
                    return # Terminé si trouvé dans le cache
            except Exception as e:
                logger.error(f"Erreur lors de la lecture du cache TTS Redis: {e}")
            finally:
                 if redis_conn: await redis_conn.close() # Assurer la fermeture

        logger.info(f"Cache TTS MISS pour session {session_id}. Appel API: {self.api_url}")

        # 2. Appel API Coqui TTS si pas dans le cache
        payload = {
            "text": text,
            "speaker_id": speaker_id,
            "language_id": language, # Coqui TTS utilise souvent language_id
            "response_format": "wav", # Ou autre format supporté
            "stream": True # Demander explicitement le streaming si l'API le supporte
                           # Note: L'API Coqui standard ne supporte pas forcément "stream": True
                           # Elle streame par défaut si responseType='stream' est utilisé avec aiohttp
        }

        stream_started = False
        audio_buffer_for_cache = b"" # Pour stocker l'audio à mettre en cache

        try:
            # Créer une session HTTP asynchrone
            session = aiohttp.ClientSession(timeout=self.timeout)
            try:
                # Faire la requête POST
                response = await session.post(self.api_url, json=payload)
                try:
                    if response.status == 200:
                        # Envoyer le signal de début de parole dès réception des premières données
                        async for chunk in response.content.iter_any(): # iter_any pour obtenir des chunks dès qu'ils arrivent
                            if chunk:
                                if not stream_started:
                                    await websocket_manager.send_personal_message(json.dumps({"type": "audio_control", "event": "ia_speech_start"}), session_id)
                                    stream_started = True
                                    logger.debug(f"Session {session_id}: Début streaming TTS.")

                                # Envoyer le chunk audio via WebSocket
                                await websocket_manager.send_binary(chunk, session_id)
                                if self.redis_pool: # Stocker pour le cache si activé
                                    audio_buffer_for_cache += chunk

                                # Important: permettre à d'autres tâches de s'exécuter
                                await asyncio.sleep(0.001) # Très court délai pour céder le contrôle

                        if stream_started:
                            await websocket_manager.send_personal_message(json.dumps({"type": "audio_control", "event": "ia_speech_end"}), session_id)
                            logger.info(f"Session {session_id}: Fin streaming TTS.")

                            # 3. Mettre en cache si réussi et cache activé
                            if self.redis_pool and audio_buffer_for_cache:
                                redis_conn_write = await self._get_redis_connection()
                                if redis_conn_write:
                                    try:
                                        logger.debug(f"Tentative de mise en cache TTS: Clé={cache_key}, Taille={len(audio_buffer_for_cache)}") # Log ajouté
                                        await redis_conn_write.set(cache_key, audio_buffer_for_cache, ex=settings.TTS_CACHE_EXPIRATION_S)
                                        logger.info(f"Audio TTS mis en cache pour session {session_id} (clé: {cache_key})")
                                    except Exception as e:
                                        logger.error(f"Erreur lors de l'écriture du cache TTS Redis: {e}")
                                    finally:
                                        await redis_conn_write.close()
                        else:
                             logger.warning(f"Session {session_id}: Aucun chunk audio reçu du TTS.")


                    else:
                        error_text = await response.text()
                        logger.error(f"Erreur API TTS ({response.status}): {error_text}")
                        await websocket_manager.send_personal_message(json.dumps({"type": "error", "message": f"Erreur TTS ({response.status})"}), session_id)
                finally:
                    # Fermer la réponse
                    response.close()
            finally:
                # Fermer la session
                await session.close()

        except asyncio.CancelledError:
             logger.info(f"Session {session_id}: Tâche de streaming TTS annulée (probablement par interruption).")
             # Pas besoin d'envoyer ia_speech_end si annulé
        except aiohttp.ClientError as e:
            logger.error(f"Erreur client HTTP lors de l'appel TTS: {e}", exc_info=True)
            await websocket_manager.send_personal_message(json.dumps({"type": "error", "message": "Erreur de connexion TTS"}), session_id)
        except Exception as e:
            logger.error(f"Erreur inattendue lors du streaming TTS: {e}", exc_info=True)
            await websocket_manager.send_personal_message(json.dumps({"type": "error", "message": "Erreur interne TTS"}), session_id)
        finally:
            # Assurer que ia_speech_end est envoyé si le stream a commencé mais n'a pas été annulé et a échoué
            # Note: La logique ci-dessus l'envoie déjà en cas de succès. Gérer les cas d'erreur ici est complexe.
            # On pourrait ajouter un flag pour savoir si end a été envoyé.
            pass
            
    async def synthesize_stream(self, text: str, session_id: str, emotion: Optional[str] = None, language: str = "fr"):
        """
        Synthétise le texte en audio et retourne un générateur de chunks audio.
        Cette méthode est utilisée par l'orchestrateur pour streamer l'audio vers le client.
        
        Args:
            text: Le texte à synthétiser
            session_id: L'identifiant de la session pour pouvoir annuler la génération
            emotion: L'émotion à utiliser pour la synthèse (optionnel)
            language: La langue du texte (par défaut: "fr")
            
        Returns:
            Un générateur asynchrone de chunks audio
        """
        speaker_id = self._get_speaker_id(emotion)
        
        # Créer une tâche pour cette génération et l'enregistrer pour pouvoir l'annuler plus tard
        current_task = asyncio.current_task()
        if current_task:
            self.active_generations[session_id] = current_task
            logger.debug(f"Tâche TTS enregistrée pour la session {session_id}")
        
        cache_key = f"{settings.TTS_CACHE_PREFIX}{language}:{speaker_id}:{text}"
        redis_conn = await self._get_redis_connection()

        # 1. Vérifier le cache Redis
        if redis_conn:
            try:
                cached_audio = await redis_conn.get(cache_key)
                if cached_audio:
                    logger.info(f"Cache TTS HIT pour texte: '{text[:20]}...'")
                    # Streamer depuis le cache
                    chunk_size = 2048  # Taille des chunks à envoyer
                    for i in range(0, len(cached_audio), chunk_size):
                        yield cached_audio[i:i+chunk_size]
                        await asyncio.sleep(0.01)  # Petit délai pour éviter de saturer le client
                    await redis_conn.close()
                    return  # Terminé si trouvé dans le cache
            except Exception as e:
                logger.error(f"Erreur lors de la lecture du cache TTS Redis: {e}")
            finally:
                if redis_conn: await redis_conn.close()  # Assurer la fermeture

        logger.info(f"Cache TTS MISS pour texte: '{text[:20]}...'. Appel API: {self.api_url}")

        # 2. Appel API Coqui TTS si pas dans le cache
        payload = {
            "text": text,
            "speaker_id": speaker_id,
            "language_id": language,  # Coqui TTS utilise souvent language_id
            "response_format": "wav",  # Ou autre format supporté
            "stream": True  # Demander explicitement le streaming si l'API le supporte
        }

        audio_buffer_for_cache = b""  # Pour stocker l'audio à mettre en cache

        try:
            # Créer une session HTTP asynchrone
            session = aiohttp.ClientSession(timeout=self.timeout)
            try:
                # Faire la requête POST
                response = await session.post(self.api_url, json=payload)
                try:
                    if response.status == 200:
                        # Streamer les chunks audio
                        async for chunk in response.content.iter_any():
                            if chunk:
                                # Stocker pour le cache si activé
                                if self.redis_pool:
                                    audio_buffer_for_cache += chunk
                                
                                # Retourner le chunk audio
                                yield chunk
                                
                                # Important: permettre à d'autres tâches de s'exécuter
                                await asyncio.sleep(0.001)  # Très court délai pour céder le contrôle
                        
                        # 3. Mettre en cache si réussi et cache activé
                        if self.redis_pool and audio_buffer_for_cache:
                            redis_conn_write = await self._get_redis_connection()
                            if redis_conn_write:
                                try:
                                    logger.debug(f"Tentative de mise en cache TTS: Clé={cache_key}, Taille={len(audio_buffer_for_cache)}")
                                    await redis_conn_write.set(cache_key, audio_buffer_for_cache, ex=settings.TTS_CACHE_EXPIRATION_S)
                                    logger.info(f"Audio TTS mis en cache (clé: {cache_key})")
                                except Exception as e:
                                    logger.error(f"Erreur lors de l'écriture du cache TTS Redis: {e}")
                                finally:
                                    await redis_conn_write.close()
                    else:
                        error_text = await response.text()
                        logger.error(f"Erreur API TTS ({response.status}): {error_text}")
                        # Retourner un chunk vide ou lever une exception
                        raise RuntimeError(f"Erreur API TTS ({response.status}): {error_text}")
                finally:
                    # Fermer la réponse
                    response.close()
            finally:
                # Fermer la session
                await session.close()
        
        except asyncio.CancelledError:
            logger.info(f"Tâche de streaming TTS annulée (probablement par interruption) pour la session {session_id}")
            # Propager l'annulation
            raise
        except Exception as e:
            logger.error(f"Erreur lors de la synthèse TTS pour la session {session_id}: {e}", exc_info=True)
            # Propager l'erreur
            raise
        finally:
            # Nettoyer l'entrée dans active_generations
            if session_id in self.active_generations:
                del self.active_generations[session_id]
                logger.debug(f"Tâche TTS supprimée pour la session {session_id}")
            raise

    async def stop_generation(self, session_id: str):
        """
        Arrête proprement une génération TTS en cours pour une session donnée.
        Cette méthode envoie une requête à l'API Coqui TTS pour arrêter la génération
        si l'API le supporte. Elle annule également toute tâche asyncio associée à cette session.
        
        À appeler depuis l'orchestrateur lors d'une interruption utilisateur.
        """
        logger.info(f"Demande d'arrêt de la génération TTS pour la session {session_id}")
        
        # Annuler toute tâche asyncio associée à cette session
        if session_id in self.active_generations:
            task = self.active_generations[session_id]
            if not task.done():
                logger.info(f"Annulation de la tâche asyncio pour la session {session_id}")
                task.cancel()
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=0.2)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    logger.info(f"Tâche asyncio annulée pour la session {session_id}")
                except Exception as e:
                    logger.error(f"Erreur lors de l'annulation de la tâche asyncio: {e}")
                finally:
                    del self.active_generations[session_id]
        
        # Si l'API Coqui TTS supporte un endpoint pour arrêter la génération
        stop_endpoint = f"{self.api_url.replace('/api/tts', '/api/stop')}"
        
        try:
            # Créer une session HTTP asynchrone avec un timeout court
            session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=0.5))
            try:
                # Faire la requête POST pour arrêter la génération
                response = await session.post(
                    stop_endpoint,
                    json={"session_id": session_id, "immediate_stop": True},
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status == 200:
                    logger.info(f"Arrêt de la génération TTS réussi pour la session {session_id}")
                    return True
                else:
                    logger.warning(f"Échec de l'arrêt de la génération TTS pour la session {session_id}: {response.status}")
                    # L'annulation de la tâche asyncio a déjà été tentée ci-dessus
                    return False
            finally:
                # Fermer la session
                await session.close()
        except Exception as e:
            logger.error(f"Erreur lors de la tentative d'arrêt de la génération TTS pour la session {session_id}: {e}")
            # L'annulation de la tâche asyncio a déjà été tentée ci-dessus
            return False