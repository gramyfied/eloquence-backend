"""
Service de Synthèse Vocale (TTS) optimisé avec cache Redis agressif.
Ce module fournit une interface pour la synthèse vocale via l'API Coqui TTS,
avec un cache Redis optimisé pour réduire la latence.
"""

import asyncio
import json
import logging
import time
from typing import Optional, Dict, List, Any, AsyncGenerator, Callable

import aiohttp
from aiohttp import ClientSession, ClientResponse, ClientTimeout

from core.config import settings
from core.latency_monitor import measure_latency, AsyncLatencyContext
from services.tts_cache_service import tts_cache_service

# Constantes pour le monitoring de latence
STEP_TTS_API_CALL = "tts_api_call"
STEP_TTS_TOTAL = "tts_total"

logger = logging.getLogger(__name__)

class TTSServiceOptimized:
    """
    Service de Synthèse Vocale (TTS) optimisé avec cache Redis agressif.
    Interagit avec l'API Coqui TTS et streame l'audio vers le client via WebSocket.
    """
    
    def __init__(self):
        """Initialise le service TTS optimisé."""
        # Éviter la duplication de /api/tts dans l'URL
        if settings.TTS_API_URL.endswith('/api/tts'):
            self.api_url = settings.TTS_API_URL
        else:
            self.api_url = settings.TTS_API_URL.rstrip('/') + "/api/tts"
        self.timeout = ClientTimeout(total=60)  # Timeout généreux pour TTS
        self.emotion_to_speaker_id: Dict[str, Optional[str]] = {
            "neutre": settings.TTS_SPEAKER_ID_NEUTRAL,
            "encouragement": settings.TTS_SPEAKER_ID_ENCOURAGEMENT,
            "empathie": settings.TTS_SPEAKER_ID_EMPATHY,
            "enthousiasme_modere": settings.TTS_SPEAKER_ID_ENTHUSIASM,
            "curiosite": settings.TTS_SPEAKER_ID_CURIOSITY,
            "reflexion": settings.TTS_SPEAKER_ID_REFLECTION,
            # Ajouter d'autres émotions si configurées
        }
        self.default_speaker_id = settings.TTS_SPEAKER_ID_NEUTRAL or "default"  # Fallback
        
        # Dictionnaire pour stocker les tâches asyncio en cours
        self.active_generations: Dict[str, asyncio.Task] = {}
        
        # Métriques
        self.metrics = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "api_errors": 0,
            "avg_latency": 0,
            "latency_sum": 0,
            "last_reset_time": time.time()
        }
        
        logger.info(f"Initialisation du service TTS optimisé avec API URL: {self.api_url}")
        logger.info(f"Cache TTS: {'Activé' if settings.TTS_USE_CACHE else 'Désactivé'}")
    
    def _get_speaker_id(self, emotion: Optional[str], voice_id: Optional[str] = None) -> str:
        """
        Détermine le speaker_id basé sur l'émotion ou l'ID de voix.
        
        Args:
            emotion: L'émotion à appliquer.
            voice_id: L'ID de la voix à utiliser (prioritaire sur l'émotion).
            
        Returns:
            str: L'ID du speaker à utiliser.
        """
        # Si un voice_id est fourni, l'utiliser en priorité
        if voice_id:
            return voice_id
            
        # Sinon, utiliser l'émotion pour déterminer le speaker_id
        if emotion and emotion in self.emotion_to_speaker_id:
            speaker_id = self.emotion_to_speaker_id[emotion]
            if speaker_id:
                return speaker_id
                
        logger.warning(f"Speaker ID non trouvé pour l'émotion '{emotion}'. "
                      f"Utilisation du défaut: {self.default_speaker_id}")
        return self.default_speaker_id
    
    @measure_latency(STEP_TTS_TOTAL, "session_id")
    async def stream_synthesize(self, websocket_manager, session_id: str, text: str, 
                               emotion: Optional[str] = None, language: str = "fr",
                               voice_id: Optional[str] = None, immediate_stop: bool = None):
        """
        Synthétise le texte en audio et le streame vers le client via WebSocket.
        Utilise le cache Redis si disponible.
        
        Args:
            websocket_manager: Gestionnaire de WebSockets pour envoyer l'audio.
            session_id: ID de la session.
            text: Texte à synthétiser.
            emotion: Émotion à appliquer (optionnel).
            language: Langue du texte (défaut: "fr").
            voice_id: ID de la voix à utiliser (optionnel).
            immediate_stop: Indique si l'arrêt doit être immédiat (optionnel).
        """
        start_time = time.time()
        self.metrics["total_requests"] += 1
        
        # Déterminer le speaker_id
        speaker_id = self._get_speaker_id(emotion, voice_id)
        
        # Générer la clé de cache
        cache_key = tts_cache_service.generate_cache_key(text, language, speaker_id, emotion, voice_id)
        
        # Définir le callback pour envoyer les chunks audio
        async def send_chunk(chunk):
            await websocket_manager.send_binary(chunk, session_id)
        
        # Envoyer le signal de début de parole
        await websocket_manager.send_personal_message(
            json.dumps({"type": "audio_control", "event": "ia_speech_start"}), 
            session_id
        )
        
        # Essayer de streamer depuis le cache
        cache_success = await tts_cache_service.stream_from_cache(cache_key, send_chunk)
        
        if cache_success:
            # Cache hit
            self.metrics["cache_hits"] += 1
            logger.info(f"Cache TTS HIT pour session {session_id}")
            
            # Envoyer le signal de fin de parole
            await websocket_manager.send_personal_message(
                json.dumps({"type": "audio_control", "event": "ia_speech_end"}), 
                session_id
            )
            
            # Mettre à jour les métriques
            latency = time.time() - start_time
            self.metrics["latency_sum"] += latency
            self.metrics["avg_latency"] = self.metrics["latency_sum"] / self.metrics["total_requests"]
            
            return
        
        # Cache miss, synthétiser via l'API
        self.metrics["cache_misses"] += 1
        logger.info(f"Cache TTS MISS pour session {session_id}. Appel API: {self.api_url}")
        
        # Créer une tâche pour la génération
        generation_task = asyncio.create_task(
            self._generate_and_stream(
                websocket_manager, session_id, text, speaker_id, language, 
                emotion, cache_key, immediate_stop
            )
        )
        
        # Stocker la tâche pour pouvoir l'annuler si nécessaire
        self.active_generations[session_id] = generation_task
        
        try:
            await generation_task
        except asyncio.CancelledError:
            logger.info(f"Génération TTS annulée pour session {session_id}")
        except Exception as e:
            logger.error(f"Erreur lors de la génération TTS pour session {session_id}: {e}")
            self.metrics["api_errors"] += 1
            
            # Envoyer un message d'erreur au client
            await websocket_manager.send_personal_message(
                json.dumps({"type": "error", "message": f"Erreur TTS: {str(e)}"}),
                session_id
            )
        finally:
            # Nettoyer la tâche
            if session_id in self.active_generations:
                del self.active_generations[session_id]
            
            # Mettre à jour les métriques
            latency = time.time() - start_time
            self.metrics["latency_sum"] += latency
            self.metrics["avg_latency"] = self.metrics["latency_sum"] / self.metrics["total_requests"]
    
    @measure_latency(STEP_TTS_API_CALL, "session_id")
    async def _generate_and_stream(self, websocket_manager, session_id: str, text: str, 
                                  speaker_id: str, language: str, emotion: Optional[str],
                                  cache_key: str, immediate_stop: Optional[bool] = None):
        """
        Génère l'audio via l'API TTS et le streame vers le client.
        
        Args:
            websocket_manager: Gestionnaire de WebSockets.
            session_id: ID de la session.
            text: Texte à synthétiser.
            speaker_id: ID du speaker.
            language: Langue du texte.
            emotion: Émotion à appliquer.
            cache_key: Clé de cache pour stocker l'audio.
            immediate_stop: Indique si l'arrêt doit être immédiat.
        """
        # Préparer les paramètres de la requête
        params = {
            "text": text,
            "speaker_id": speaker_id,
            "language_id": language
        }
        
        # Ajouter le paramètre immediate_stop si spécifié
        if immediate_stop is not None:
            params["immediate_stop"] = "true" if immediate_stop else "false"
        
        # Buffer pour stocker l'audio complet pour le cache
        audio_buffer_for_cache = bytearray()
        
        # Créer une session HTTP
        async with ClientSession(timeout=self.timeout) as session:
            try:
                # Faire la requête à l'API TTS
                async with session.post(self.api_url, json=params) as response:
                    if response.status == 200:
                        # Streamer la réponse chunk par chunk
                        async for chunk in response.content.iter_any():
                            if chunk:  # Ignorer les chunks vides
                                # Ajouter au buffer pour le cache
                                audio_buffer_for_cache.extend(chunk)
                                
                                # Envoyer au client
                                await websocket_manager.send_binary(chunk, session_id)
                                
                                # Petit délai pour éviter de saturer le client
                                await asyncio.sleep(0.01)
                        
                        # Envoyer le signal de fin de parole
                        await websocket_manager.send_personal_message(
                            json.dumps({"type": "audio_control", "event": "ia_speech_end"}),
                            session_id
                        )
                        
                        # Mettre en cache si on a reçu des données
                        if audio_buffer_for_cache:
                            # Mettre en cache de manière asynchrone
                            asyncio.create_task(
                                tts_cache_service.set_audio(
                                    cache_key, 
                                    bytes(audio_buffer_for_cache)
                                )
                            )
                        else:
                            logger.warning(f"Session {session_id}: Aucun chunk audio reçu du TTS.")
                    else:
                        # Gérer les erreurs
                        error_text = await response.text()
                        logger.error(f"Erreur API TTS ({response.status}): {error_text}")
                        
                        # Envoyer un message d'erreur au client
                        await websocket_manager.send_personal_message(
                            json.dumps({"type": "error", "message": f"Erreur TTS ({response.status})"}),
                            session_id
                        )
                        
                        self.metrics["api_errors"] += 1
            except asyncio.CancelledError:
                # Propager l'annulation
                raise
            except Exception as e:
                logger.error(f"Erreur lors de la génération TTS pour session {session_id}: {e}")
                
                # Envoyer un message d'erreur au client
                await websocket_manager.send_personal_message(
                    json.dumps({"type": "error", "message": f"Erreur TTS: {str(e)}"}),
                    session_id
                )
                
                self.metrics["api_errors"] += 1
                raise
    
    async def synthesize_text(self, text: str, language: str = "fr", 
                             speaker_id: Optional[str] = None, emotion: Optional[str] = None,
                             voice_id: Optional[str] = None) -> Optional[bytes]:
        """
        Synthétise le texte en audio et retourne les données audio.
        Utilise le cache Redis si disponible.
        
        Args:
            text: Texte à synthétiser.
            language: Langue du texte (défaut: "fr").
            speaker_id: ID du speaker (optionnel).
            emotion: Émotion à appliquer (optionnel).
            voice_id: ID de la voix à utiliser (optionnel).
            
        Returns:
            Optional[bytes]: Les données audio ou None en cas d'erreur.
        """
        # Déterminer le speaker_id si non fourni
        if not speaker_id:
            speaker_id = self._get_speaker_id(emotion, voice_id)
        
        # Générer la clé de cache
        cache_key = tts_cache_service.generate_cache_key(text, language, speaker_id, emotion, voice_id)
        
        # Vérifier le cache
        cached_audio = await tts_cache_service.get_audio(cache_key)
        if cached_audio:
            logger.info(f"Cache TTS HIT pour texte: '{text[:20]}...'")
            return cached_audio
        
        logger.info(f"Cache TTS MISS pour texte: '{text[:20]}...'. Appel API: {self.api_url}")
        
        # Préparer les paramètres de la requête
        params = {
            "text": text,
            "speaker_id": speaker_id,
            "language_id": language
        }
        
        # Créer une session HTTP
        async with ClientSession(timeout=self.timeout) as session:
            try:
                # Faire la requête à l'API TTS
                async with session.post(self.api_url, json=params) as response:
                    if response.status == 200:
                        # Lire toute la réponse
                        audio_data = await response.read()
                        
                        # Mettre en cache
                        if audio_data:
                            asyncio.create_task(
                                tts_cache_service.set_audio(cache_key, audio_data)
                            )
                            
                        return audio_data
                    else:
                        # Gérer les erreurs
                        error_text = await response.text()
                        logger.error(f"Erreur API TTS ({response.status}): {error_text}")
                        return None
            except Exception as e:
                logger.error(f"Erreur lors de la synthèse TTS: {e}")
                return None
    
    async def stop_synthesis(self, session_id: str) -> bool:
        """
        Arrête la synthèse en cours pour une session.
        
        Args:
            session_id: ID de la session.
            
        Returns:
            bool: True si la synthèse a été arrêtée, False sinon.
        """
        if session_id in self.active_generations:
            task = self.active_generations[session_id]
            if not task.done():
                task.cancel()
                logger.info(f"Synthèse TTS annulée pour session {session_id}")
                return True
        
        logger.warning(f"Aucune synthèse TTS active trouvée pour session {session_id}")
        return False
    
    async def get_metrics(self) -> Dict[str, Any]:
        """
        Récupère les métriques du service TTS.
        
        Returns:
            Dict[str, Any]: Les métriques du service TTS.
        """
        # Récupérer les métriques du cache
        cache_metrics = await tts_cache_service.get_metrics()
        
        # Combiner avec les métriques du service TTS
        metrics = self.metrics.copy()
        metrics["cache"] = cache_metrics
        
        # Calculer les métriques dérivées
        if metrics["total_requests"] > 0:
            metrics["cache_hit_ratio"] = metrics["cache_hits"] / metrics["total_requests"]
        else:
            metrics["cache_hit_ratio"] = 0
        
        return metrics
    
    async def reset_metrics(self) -> None:
        """Réinitialise les métriques du service TTS."""
        self.metrics = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "api_errors": 0,
            "avg_latency": 0,
            "latency_sum": 0,
            "last_reset_time": time.time()
        }
        
        # Réinitialiser les métriques du cache
        await tts_cache_service.reset_metrics()
    
    async def preload_common_phrases(self, phrases: List[str], language: str = "fr",
                                    emotion: Optional[str] = None, voice_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Précharge le cache avec des phrases couramment utilisées.
        
        Args:
            phrases: Liste des phrases à précharger.
            language: Langue des phrases (défaut: "fr").
            emotion: Émotion à appliquer (optionnel).
            voice_id: ID de la voix à utiliser (optionnel).
            
        Returns:
            Dict[str, Any]: Statistiques sur le préchargement.
        """
        # Déterminer le speaker_id
        speaker_id = self._get_speaker_id(emotion, voice_id)
        
        # Précharger le cache
        return await tts_cache_service.preload_cache(
            phrases, language, speaker_id, emotion, voice_id, self
        )

# Créer une instance singleton
tts_service_optimized = TTSServiceOptimized()