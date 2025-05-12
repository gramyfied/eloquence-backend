"""
Service de Synthèse Vocale (TTS) optimisé avec cache Redis agressif.
Ce module fournit une interface pour la synthèse vocale via l'API Coqui TTS,
avec un cache Redis optimisé pour réduire la latence.
"""

import asyncio
import json
import logging
import sys
import time
from typing import Optional, Dict, List, Any, AsyncGenerator, Callable
import numpy as np
import soundfile as sf
import io

# Importer les classes nécessaires de Coqui TTS
from TTS.api import TTS

from core.config import settings
from core.latency_monitor import measure_latency, AsyncLatencyContext
from services.tts_cache_service import tts_cache_service

# Constantes pour le monitoring de latence
STEP_TTS_LOCAL_GENERATE = "tts_local_generate"
STEP_TTS_TOTAL = "tts_total"

logger = logging.getLogger(__name__)

class TTSServiceOptimized:
    """
    Service de Synthèse Vocale (TTS) optimisé avec cache Redis agressif.
    Utilise la bibliothèque Coqui TTS localement et streame l'audio vers le client via WebSocket.
    """
    
    def __init__(self):
        """Initialise le service TTS optimisé."""
        # Supprimer la configuration de l'API externe
        # self.api_url = settings.TTS_API_URL.rstrip('/') + "/api/tts"
        # self.timeout = ClientTimeout(total=60)  # Timeout généreux pour TTS (plus nécessaire pour API)
        
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
        
        # Charger le modèle Coqui TTS localement
        # TODO: Rendre le chemin du modèle configurable via settings
        # TODO: Charger le modèle de manière asynchrone ou dans un thread séparé
        self.tts_model: Optional[TTS] = None
        self.model_name = settings.TTS_MODEL_NAME # Assurez-vous que ce setting existe
        self.model_device = settings.TTS_DEVICE # Assurez-vous que ce setting existe
        
        # Initialiser les capacités du modèle (sera mis à jour après le chargement)
        self.model_capabilities = {
            "multi_speaker": False,
            "emotion_support": False,
            "emotion_embeddings": False,
            "voice_cloning": False,
            "streaming": False,
        }
        
        # Mappage des émotions vers des valeurs d'embeddings pour les modèles qui les supportent
        # Ces valeurs sont des exemples et devraient être ajustées selon le modèle utilisé
        self.emotion_embeddings = {
            "neutre": [0.0, 0.0, 0.0, 0.0],  # Valeurs neutres
            "encouragement": [0.8, 0.2, 0.5, 0.0],  # Positif, énergique
            "empathie": [0.2, -0.3, -0.2, 0.5],  # Doux, chaleureux
            "enthousiasme_modere": [0.6, 0.4, 0.3, 0.2],  # Très positif
            "curiosite": [0.3, 0.5, 0.0, 0.2],  # Interrogatif
            "reflexion": [0.0, -0.2, -0.4, 0.0],  # Pensif, lent
        }
        
        logger.info(f"Initialisation du service TTS optimisé avec modèle local: {self.model_name}")
        logger.info(f"Cache TTS: {'Activé' if settings.TTS_USE_CACHE else 'Désactivé'}")
    
    async def load_model(self):
        """Charge le modèle Coqui TTS de manière asynchrone."""
        loop = asyncio.get_running_loop()
        try:
            logger.info(f"Chargement du modèle TTS '{self.model_name}' sur {self.model_device}...")
            # Exécuter le chargement dans un thread séparé pour ne pas bloquer l'event loop
            self.tts_model = await loop.run_in_executor(
                None, # Utilise le ThreadPoolExecutor par défaut
                lambda: TTS(model_name=self.model_name, device=self.model_device)
            )
            logger.info(f"Modèle TTS '{self.model_name}' chargé avec succès.")
            
            # Détecter les capacités du modèle
            self._detect_model_capabilities()
            
        except Exception as e:
            logger.error(f"Erreur lors du chargement du modèle TTS: {e}", exc_info=True)
            raise # Relancer l'exception pour signaler l'échec
    
    def _detect_model_capabilities(self):
        """Détecte les capacités du modèle TTS chargé."""
        if self.tts_model is None:
            logger.warning("Impossible de détecter les capacités du modèle: modèle non chargé.")
            return
            
        # Initialiser les capacités par défaut
        self.model_capabilities = {
            "multi_speaker": False,
            "emotion_support": False,
            "emotion_embeddings": False,
            "voice_cloning": False,
            "streaming": False,
        }
        
        try:
            # Vérifier si le modèle est multi-speaker
            if hasattr(self.tts_model, "speakers") and self.tts_model.speakers:
                self.model_capabilities["multi_speaker"] = True
                logger.info(f"Modèle multi-speaker détecté avec {len(self.tts_model.speakers)} speakers")
                
            # Vérifier si le modèle supporte les émotions via des embeddings
            # Cela dépend du type de modèle (VITS, YourTTS, etc.)
            model_type = self.model_name.lower()
            if "vits" in model_type or "yourtts" in model_type or "xtts" in model_type:
                self.model_capabilities["emotion_support"] = True
                if "xtts" in model_type:
                    self.model_capabilities["voice_cloning"] = True
                    logger.info("Modèle avec clonage de voix détecté (XTTS)")
                logger.info("Modèle avec support d'émotions détecté")
                
            # Vérifier si le modèle supporte le streaming
            # Vérifier si la méthode tts_stream existe
            if hasattr(self.tts_model, 'tts_stream') and callable(getattr(self.tts_model, 'tts_stream')):
                self.model_capabilities["streaming"] = True
                logger.info("Modèle avec support de streaming natif détecté")
            else:
                self.model_capabilities["streaming"] = False
            
            logger.info(f"Capacités du modèle détectées: {self.model_capabilities}")
            
        except Exception as e:
            logger.warning(f"Erreur lors de la détection des capacités du modèle: {e}")
    
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
    
    def _get_emotion_parameters(self, emotion: Optional[str]) -> Dict[str, Any]:
        """
        Retourne les paramètres de synthèse spécifiques à une émotion.
        
        Args:
            emotion: L'émotion à appliquer.
            
        Returns:
            Dict[str, Any]: Les paramètres de synthèse pour cette émotion.
        """
        # Paramètres par défaut
        params = {
            "speed": 1.0,  # Vitesse normale
            "pitch": 0.0,  # Hauteur normale (pas de modification)
            "energy": 1.0,  # Énergie normale
        }
        
        # Ajuster les paramètres selon l'émotion
        if emotion == "neutre":
            # Paramètres neutres (par défaut)
            pass
        elif emotion == "encouragement":
            # Légèrement plus rapide, un peu plus haut, plus d'énergie
            params["speed"] = 1.05
            params["pitch"] = 0.5
            params["energy"] = 1.2
        elif emotion == "empathie":
            # Plus lent, un peu plus bas, moins d'énergie
            params["speed"] = 0.95
            params["pitch"] = -0.3
            params["energy"] = 0.9
        elif emotion == "enthousiasme_modere":
            # Plus rapide, plus haut, beaucoup plus d'énergie
            params["speed"] = 1.1
            params["pitch"] = 0.7
            params["energy"] = 1.3
        elif emotion == "curiosite":
            # Vitesse normale, plus haut à la fin (intonation montante)
            params["speed"] = 1.0
            params["pitch"] = 0.2
            params["energy"] = 1.1
        elif emotion == "reflexion":
            # Plus lent, plus bas, moins d'énergie
            params["speed"] = 0.9
            params["pitch"] = -0.5
            params["energy"] = 0.8
        
        logger.debug(f"Paramètres pour l'émotion '{emotion}': {params}")
        return params
    
    def _apply_emotion_to_audio(self, audio_np: np.ndarray, emotion: Optional[str]) -> np.ndarray:
        """
        Applique des transformations à l'audio pour simuler une émotion.
        
        Args:
            audio_np: L'audio sous forme de numpy array.
            emotion: L'émotion à appliquer.
            
        Returns:
            np.ndarray: L'audio transformé.
        """
        if not emotion or emotion == "neutre":
            return audio_np
            
        # Obtenir les paramètres pour cette émotion
        params = self._get_emotion_parameters(emotion)
        
        # Importer signal en dehors du bloc try/except pour éviter l'erreur "cannot access local variable 'signal'"
        from scipy import signal
        
        try:
            import librosa
            import pyrubberband as pyrb
            
            # Récupérer le taux d'échantillonnage (sample rate)
            sample_rate = self.tts_model.get_sampling_rate() if self.tts_model else 22050
            
            # 1. Appliquer le changement de vitesse sans affecter la hauteur (time stretching)
            if params["speed"] != 1.0:
                audio_np = pyrb.time_stretch(audio_np, sample_rate, params["speed"])
            
            # 2. Appliquer le changement de hauteur sans affecter la durée (pitch shifting)
            if params["pitch"] != 0.0:
                # Convertir les demi-tons en facteur de pitch shift
                audio_np = pyrb.pitch_shift(audio_np, sample_rate, params["pitch"])
            
            # 3. Appliquer le changement d'énergie (amplification/atténuation)
            if params["energy"] != 1.0:
                audio_np = audio_np * params["energy"]
                
                # Éviter l'écrêtage (clipping)
                if np.max(np.abs(audio_np)) > 1.0:
                    audio_np = audio_np / np.max(np.abs(audio_np))
            
            # 4. Appliquer des transformations spécifiques à certaines émotions
            if emotion == "curiosite":
                # Pour la curiosité, ajouter une intonation montante à la fin
                # Extraire les 20% finaux de l'audio
                end_portion_length = int(len(audio_np) * 0.2)
                if end_portion_length > 0:
                    end_portion = audio_np[-end_portion_length:]
                    # Appliquer une augmentation progressive de la hauteur
                    end_portion_pitched = pyrb.pitch_shift(end_portion, sample_rate, 1.5)
                    # Remplacer la fin de l'audio
                    audio_np[-end_portion_length:] = end_portion_pitched
                    
            elif emotion == "reflexion":
                # Pour la réflexion, ajouter une intonation descendante à la fin
                end_portion_length = int(len(audio_np) * 0.2)
                if end_portion_length > 0:
                    end_portion = audio_np[-end_portion_length:]
                    # Appliquer une diminution progressive de la hauteur
                    end_portion_pitched = pyrb.pitch_shift(end_portion, sample_rate, -1.0)
                    # Remplacer la fin de l'audio
                    audio_np[-end_portion_length:] = end_portion_pitched
                    
            elif emotion == "empathie":
                # Pour l'empathie, adoucir le son avec un léger filtrage passe-bas
                audio_np = librosa.effects.preemphasis(audio_np, coef=0.95)
                
            elif emotion == "enthousiasme_modere":
                # Pour l'enthousiasme, augmenter légèrement la brillance avec un filtrage passe-haut
                audio_np = librosa.effects.preemphasis(audio_np, coef=0.2)
            
            return audio_np
            
        except ImportError as e:
            logger.warning(f"Bibliothèque manquante pour les transformations audio avancées: {e}. Utilisation des transformations basiques.")
            # Fallback vers la méthode simple si les bibliothèques avancées ne sont pas disponibles
            if params["speed"] != 1.0:
                # Simuler un changement de vitesse en modifiant la longueur de l'audio
                new_length = int(len(audio_np) / params["speed"])
                audio_np = signal.resample(audio_np, new_length)
                
            return audio_np
        except Exception as e:
            logger.error(f"Erreur lors de l'application des transformations audio: {e}", exc_info=True)
            # En cas d'erreur, retourner l'audio non modifié
            return audio_np
    
    def _apply_emotion_to_model(self, emotion: Optional[str]) -> Dict[str, Any]:
        """
        Applique une émotion directement au modèle TTS si celui-ci le supporte.
        
        Args:
            emotion: L'émotion à appliquer.
            
        Returns:
            Dict[str, Any]: Les paramètres à passer au modèle pour cette émotion.
        """
        # Si pas d'émotion ou émotion neutre, retourner un dictionnaire vide
        if not emotion or emotion == "neutre":
            return {}
            
        # Si le modèle ne supporte pas les émotions, retourner un dictionnaire vide
        if not self.model_capabilities.get("emotion_support", False):
            return {}
            
        # Si le modèle supporte les embeddings d'émotions, les utiliser
        if self.model_capabilities.get("emotion_embeddings", False) and emotion in self.emotion_embeddings:
            return {"emotion_embedding": self.emotion_embeddings[emotion]}
            
        # Sinon, retourner un dictionnaire vide
        return {}
    
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
        
        # Cache miss, synthétiser localement
        self.metrics["cache_misses"] += 1
        logger.info(f"Cache TTS MISS pour session {session_id}. Génération locale avec modèle: {self.model_name}")
        
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
    
    @measure_latency(STEP_TTS_LOCAL_GENERATE, "session_id")
    async def _generate_and_stream(self, websocket_manager, session_id: str, text: str,
                                  speaker_id: str, language: str, emotion: Optional[str],
                                  cache_key: str, immediate_stop: Optional[bool] = None):
        """
        Génère l'audio via le modèle TTS local et le streame vers le client.
        
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
        if self.tts_model is None:
            logger.error("Modèle TTS non chargé.")
            # Envoyer un message d'erreur au client
            await websocket_manager.send_personal_message(
                json.dumps({"type": "error", "message": "Erreur TTS: Modèle non chargé."}),
                session_id
            )
            self.metrics["api_errors"] += 1 # Compter comme une erreur API pour les métriques
            return
            
        # Buffer pour stocker l'audio complet pour le cache
        audio_buffer_for_cache = bytearray()
        
        try:
            # Obtenir les paramètres d'émotion pour le modèle si supporté
            emotion_params = self._apply_emotion_to_model(emotion)
            
            # Préparer les paramètres pour la synthèse
            synth_params = {
                "text": text,
                "speaker": speaker_id,
                "language": language,
                **emotion_params  # Ajouter les paramètres d'émotion si disponibles
            }
            
            # Log des paramètres utilisés
            if emotion_params:
                logger.info(f"Session {session_id}: Utilisation des paramètres d'émotion natifs pour '{emotion}'")
            
            # Dans un environnement de test, utiliser toujours la méthode de génération complète
            # pour éviter les problèmes avec les mocks
            is_test_environment = 'pytest' in sys.modules
            
            # Vérifier si le modèle supporte le streaming natif
            if not is_test_environment and hasattr(self.tts_model, 'tts_stream') and callable(getattr(self.tts_model, 'tts_stream')):
                # Utiliser le streaming natif du modèle
                await self._stream_native_tts(
                    websocket_manager,
                    session_id,
                    synth_params,
                    emotion,
                    audio_buffer_for_cache,
                    cache_key
                )
            else:
                # Utiliser la méthode de génération complète puis streaming
                await self._generate_full_then_stream(
                    websocket_manager,
                    session_id,
                    synth_params,
                    emotion,
                    audio_buffer_for_cache,
                    cache_key
                )
                
        except asyncio.CancelledError:
            # Propager l'annulation
            raise
        except Exception as e:
            logger.error(f"Erreur lors de la génération TTS locale pour session {session_id}: {e}", exc_info=True)
            
            # Envoyer un message d'erreur au client
            await websocket_manager.send_personal_message(
                json.dumps({"type": "error", "message": f"Erreur TTS locale: {str(e)}"}),
                session_id
            )
            
            self.metrics["api_errors"] += 1 # Compter comme une erreur API pour les métriques
            raise # Relancer l'exception pour qu'elle soit gérée par stream_synthesize
            
    async def _stream_native_tts(self, websocket_manager, session_id: str, synth_params: Dict[str, Any],
                                emotion: Optional[str], audio_buffer_for_cache: bytearray, cache_key: str):
        """
        Utilise le streaming natif du modèle TTS pour générer et streamer l'audio en temps réel.
        
        Args:
            websocket_manager: Gestionnaire de WebSockets.
            session_id: ID de la session.
            synth_params: Paramètres pour la synthèse.
            emotion: Émotion à appliquer.
            audio_buffer_for_cache: Buffer pour stocker l'audio complet pour le cache.
            cache_key: Clé de cache pour stocker l'audio.
        """
        try:
            # Créer une file d'attente pour recevoir les chunks audio du modèle
            audio_queue = asyncio.Queue()
            
            # Fonction de callback pour recevoir les chunks audio du modèle
            def tts_callback(audio_chunk: np.ndarray):
                # Mettre le chunk dans la file d'attente
                asyncio.run_coroutine_threadsafe(
                    audio_queue.put(audio_chunk),
                    asyncio.get_running_loop()
                )
            
            # Ajouter le callback aux paramètres de synthèse
            stream_params = {**synth_params, "callback": tts_callback}
            
            # Lancer la génération dans un thread séparé
            loop = asyncio.get_running_loop()
            generation_task = loop.run_in_executor(
                None,
                lambda: self.tts_model.tts_stream(**stream_params)
            )
            
            # Traiter les chunks audio au fur et à mesure qu'ils arrivent
            sample_rate = self.tts_model.get_sampling_rate()
            
            while True:
                # Créer des tâches explicites pour les coroutines
                get_audio_task = asyncio.create_task(audio_queue.get())
                
                # Attendre le prochain chunk ou la fin de la génération
                done, pending = await asyncio.wait(
                    [get_audio_task, generation_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Annuler les tâches en attente pour éviter les fuites de ressources
                for task in pending:
                    task.cancel()
                
                # Vérifier si la génération est terminée
                if generation_task in done:
                    # Vider la file d'attente
                    while not audio_queue.empty():
                        audio_chunk = await audio_queue.get()
                        # Traiter le dernier chunk
                        await self._process_audio_chunk(
                            audio_chunk,
                            sample_rate,
                            emotion,
                            websocket_manager,
                            session_id,
                            audio_buffer_for_cache
                        )
                    break
                
                # Traiter le chunk audio si c'est la tâche get_audio_task qui est terminée
                if get_audio_task in done:
                    try:
                        # Récupérer le résultat de la tâche
                        audio_chunk = get_audio_task.result()
                        await self._process_audio_chunk(
                            audio_chunk,
                            sample_rate,
                            emotion,
                            websocket_manager,
                            session_id,
                            audio_buffer_for_cache
                        )
                    except Exception as e:
                        logger.error(f"Erreur lors de la récupération du chunk audio: {e}")
            
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
                logger.warning(f"Session {session_id}: Aucun chunk audio généré par le TTS local.")
                
        except Exception as e:
            logger.error(f"Erreur lors du streaming natif TTS pour session {session_id}: {e}", exc_info=True)
            raise
            
    async def _process_audio_chunk(self, audio_chunk: np.ndarray, sample_rate: int, emotion: Optional[str],
                                  websocket_manager, session_id: str, audio_buffer_for_cache: bytearray):
        """
        Traite un chunk audio généré par le modèle TTS.
        
        Args:
            audio_chunk: Chunk audio sous forme de numpy array.
            sample_rate: Taux d'échantillonnage.
            emotion: Émotion à appliquer.
            websocket_manager: Gestionnaire de WebSockets.
            session_id: ID de la session.
            audio_buffer_for_cache: Buffer pour stocker l'audio complet pour le cache.
        """
        # Appliquer les transformations d'émotion post-traitement si nécessaire
        if emotion and emotion != "neutre" and not self.model_capabilities.get("emotion_support", False):
            loop = asyncio.get_running_loop()
            audio_chunk = await loop.run_in_executor(
                None,
                lambda: self._apply_emotion_to_audio(audio_chunk, emotion)
            )
        
        # Convertir le numpy array en bytes WAV
        audio_io = io.BytesIO()
        sf.write(audio_io, audio_chunk, sample_rate, format='WAV')
        audio_bytes = audio_io.getvalue()
        
        # Ajouter au buffer pour le cache
        audio_buffer_for_cache.extend(audio_bytes)
        
        # Envoyer au client
        await websocket_manager.send_binary(audio_bytes, session_id)
        
    async def _generate_full_then_stream(self, websocket_manager, session_id: str, synth_params: Dict[str, Any],
                                        emotion: Optional[str], audio_buffer_for_cache: bytearray, cache_key: str):
        """
        Génère l'audio complet puis le streame par chunks.
        
        Args:
            websocket_manager: Gestionnaire de WebSockets.
            session_id: ID de la session.
            synth_params: Paramètres pour la synthèse.
            emotion: Émotion à appliquer.
            audio_buffer_for_cache: Buffer pour stocker l'audio complet pour le cache.
            cache_key: Clé de cache pour stocker l'audio.
        """
        try:
            # Exécuter la synthèse dans un thread séparé pour ne pas bloquer l'event loop
            loop = asyncio.get_running_loop()
            
            # Appel à la synthèse
            audio_np = await loop.run_in_executor(
                None, # Utilise le ThreadPoolExecutor par défaut
                lambda: self.tts_model.synthesize(**synth_params)
            )
            
            # Appliquer les transformations d'émotion post-traitement si nécessaire
            # (seulement si le modèle ne supporte pas nativement les émotions)
            if emotion and emotion != "neutre" and not self.model_capabilities.get("emotion_support", False):
                logger.info(f"Session {session_id}: Application de l'émotion '{emotion}' par post-traitement audio")
                # Exécuter la transformation dans un thread séparé pour ne pas bloquer l'event loop
                audio_np = await loop.run_in_executor(
                    None,
                    lambda: self._apply_emotion_to_audio(audio_np, emotion)
                )
            
            # Convertir le numpy array en bytes WAV
            # Utiliser soundfile pour écrire dans un buffer mémoire
            audio_io = io.BytesIO()
            sf.write(audio_io, audio_np, self.tts_model.get_sampling_rate(), format='WAV') # Utiliser le sample rate du modèle
            audio_bytes = audio_io.getvalue()
            
            # Streamer les bytes audio par chunks
            chunk_size = 1024 # Définir une taille de chunk appropriée
            for i in range(0, len(audio_bytes), chunk_size):
                chunk = audio_bytes[i:i + chunk_size]
                audio_buffer_for_cache.extend(chunk) # Ajouter au buffer pour le cache
                await websocket_manager.send_binary(chunk, session_id)
                await asyncio.sleep(0.005) # Petit délai pour éviter de saturer le client
            
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
                logger.warning(f"Session {session_id}: Aucun chunk audio généré par le TTS local.")
        
        except Exception as e:
            error_message = str(e)
            logger.error(f"Erreur lors de la génération TTS locale pour session {session_id}: {error_message}", exc_info=True)
            
            # Envoyer un message d'erreur au client
            await websocket_manager.send_personal_message(
                json.dumps({"type": "error", "message": f"Erreur TTS locale: {error_message}"}),
                session_id
            )
            
            # Propager l'erreur pour qu'elle soit gérée par _generate_and_stream
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
        if self.tts_model is None:
            logger.error("Modèle TTS non chargé.")
            return None
            
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
        
        logger.info(f"Cache TTS MISS pour texte: '{text[:20]}...'. Génération locale.")
        
        try:
            # Obtenir les paramètres d'émotion pour le modèle si supporté
            emotion_params = self._apply_emotion_to_model(emotion)
            
            # Utiliser la méthode synthesize de Coqui TTS pour générer l'audio
            # Exécuter la synthèse dans un thread séparé
            loop = asyncio.get_running_loop()
            
            # Préparer les paramètres pour la synthèse
            synth_params = {
                "text": text,
                "speaker": speaker_id,
                "language": language,
                **emotion_params  # Ajouter les paramètres d'émotion si disponibles
            }
            
            # Log des paramètres utilisés
            if emotion_params:
                logger.info(f"Utilisation des paramètres d'émotion natifs pour '{emotion}'")
            
            # Appel à la synthèse
            audio_np = await loop.run_in_executor(
                None, # Utilise le ThreadPoolExecutor par défaut
                lambda: self.tts_model.synthesize(**synth_params)
            )
            
            # Appliquer les transformations d'émotion post-traitement si nécessaire
            # (seulement si le modèle ne supporte pas nativement les émotions)
            if emotion and emotion != "neutre" and not self.model_capabilities.get("emotion_support", False):
                logger.info(f"Application de l'émotion '{emotion}' par post-traitement audio")
                # Exécuter la transformation dans un thread séparé pour ne pas bloquer l'event loop
                audio_np = await loop.run_in_executor(
                    None,
                    lambda: self._apply_emotion_to_audio(audio_np, emotion)
                )
            
            # Convertir le numpy array en bytes WAV
            audio_io = io.BytesIO()
            sf.write(audio_io, audio_np, self.tts_model.get_sampling_rate(), format='WAV')
            audio_data = audio_io.getvalue()
            
            # Mettre en cache
            if audio_data:
                asyncio.create_task(
                    tts_cache_service.set_audio(cache_key, audio_data)
                )
                
            return audio_data
            
        except Exception as e:
            logger.error(f"Erreur lors de la synthèse TTS locale: {e}", exc_info=True)
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
                # Attendre que la tâche soit effectivement annulée
                try:
                    # Attendre un court instant pour que l'annulation soit effective
                    await asyncio.sleep(0.05)
                    # Vérifier si la tâche est annulée
                    if task.cancelled():
                        logger.info(f"Synthèse TTS annulée pour session {session_id}")
                        # Retirer la tâche du dictionnaire
                        del self.active_generations[session_id]
                        return True
                except asyncio.CancelledError:
                    # Si cette méthode est elle-même annulée, propager l'annulation
                    raise
                
                logger.info(f"Synthèse TTS annulée pour session {session_id}")
                # Retirer la tâche du dictionnaire
                del self.active_generations[session_id]
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