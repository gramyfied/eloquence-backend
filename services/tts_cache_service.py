"""
Service de cache Redis optimisé pour le TTS.
Ce module fournit des fonctionnalités avancées de mise en cache pour le service TTS,
permettant de réduire la latence et d'améliorer les performances.
"""

import asyncio
import hashlib
import logging
import time
import zlib
from typing import Optional, Dict, Tuple, List, Any, Union

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool
from redis.asyncio.client import Redis

from core.config import settings
from core.latency_monitor import measure_latency, AsyncLatencyContext

logger = logging.getLogger(__name__)

# Constantes pour le monitoring de latence
STEP_TTS_CACHE_GET = "tts_cache_get"
STEP_TTS_CACHE_SET = "tts_cache_set"

class TTSCacheService:
    """
    Service de cache Redis optimisé pour le TTS.
    Fournit des fonctionnalités avancées de mise en cache pour réduire la latence.
    """
    
    def __init__(self):
        """Initialise le service de cache TTS."""
        self.redis_pool: Optional[ConnectionPool] = None
        self.cache_enabled = settings.TTS_USE_CACHE
        self.cache_prefix = settings.TTS_CACHE_PREFIX
        self.cache_expiration = settings.TTS_CACHE_EXPIRATION_S
        self.compression_enabled = True  # Activer la compression par défaut
        self.compression_level = 6  # Niveau de compression (1-9, 9 étant le plus élevé)
        self.compression_threshold = 1024  # Compresser seulement si > 1KB
        
        # Métriques
        self.metrics = {
            "hits": 0,
            "misses": 0,
            "set_success": 0,
            "set_error": 0,
            "get_latency_sum": 0,
            "get_latency_count": 0,
            "set_latency_sum": 0,
            "set_latency_count": 0,
            "last_reset_time": time.time()
        }
        
        # Initialiser la connexion Redis
        self._initialize_redis()
        
    def _initialize_redis(self):
        """Initialise la connexion Redis."""
        if not self.cache_enabled:
            logger.info("Cache TTS désactivé par configuration.")
            return
            
        try:
            self.redis_pool = redis.ConnectionPool.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                decode_responses=False,  # Important: stocker les bytes audio bruts
                max_connections=10,  # Limiter le nombre de connexions
                health_check_interval=30  # Vérifier la santé des connexions
            )
            logger.info("Pool de connexion Redis pour le cache TTS créé avec succès.")
        except Exception as e:
            logger.error(f"Impossible de créer le pool Redis pour le cache TTS: {e}. Cache désactivé.")
            self.cache_enabled = False
            self.redis_pool = None
    
    async def get_connection(self) -> Optional[Redis]:
        """
        Obtient une connexion Redis depuis le pool.
        
        Returns:
            Optional[Redis]: Une connexion Redis ou None si le cache est désactivé.
        """
        if not self.cache_enabled or not self.redis_pool:
            return None
            
        try:
            return redis.Redis(connection_pool=self.redis_pool)
        except Exception as e:
            logger.error(f"Impossible d'obtenir une connexion Redis: {e}")
            return None
    
    def generate_cache_key(self, text: str, language: str, speaker_id: str, 
                          emotion: Optional[str] = None, voice_id: Optional[str] = None) -> str:
        """
        Génère une clé de cache optimisée pour le TTS.
        
        Args:
            text: Le texte à synthétiser.
            language: La langue du texte.
            speaker_id: L'ID du speaker.
            emotion: L'émotion à appliquer (optionnel).
            voice_id: L'ID de la voix à utiliser (optionnel).
            
        Returns:
            str: La clé de cache générée.
        """
        # Utiliser un hachage pour les textes longs
        if len(text) > 100:
            text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
            text_prefix = text[:20].replace(" ", "_")
            text_part = f"{text_prefix}_{text_hash}"
        else:
            text_part = text.replace(" ", "_")
            
        # Construire la clé
        key_parts = [self.cache_prefix, language, speaker_id]
        
        # Ajouter les parties optionnelles
        if emotion:
            key_parts.append(f"emotion:{emotion}")
        if voice_id:
            key_parts.append(f"voice:{voice_id}")
            
        # Ajouter le texte à la fin
        key_parts.append(text_part)
        
        # Joindre toutes les parties
        return ":".join(key_parts)
    
    def _compress_data(self, data: bytes) -> Tuple[bytes, bool]:
        """
        Compresse les données si nécessaire.
        
        Args:
            data: Les données à compresser.
            
        Returns:
            Tuple[bytes, bool]: Les données (compressées ou non) et un booléen indiquant si elles ont été compressées.
        """
        if not self.compression_enabled or len(data) < self.compression_threshold:
            return data, False
            
        try:
            compressed_data = zlib.compress(data, level=self.compression_level)
            compression_ratio = len(compressed_data) / len(data)
            
            # Ne garder la version compressée que si elle est plus petite
            if compression_ratio < 0.9:  # Au moins 10% de réduction
                logger.debug(f"Données compressées: {len(data)} -> {len(compressed_data)} bytes "
                           f"(ratio: {compression_ratio:.2f})")
                return compressed_data, True
            else:
                logger.debug(f"Compression inefficace (ratio: {compression_ratio:.2f}), utilisation des données non compressées")
                return data, False
        except Exception as e:
            logger.warning(f"Erreur lors de la compression des données: {e}")
            return data, False
    
    def _decompress_data(self, data: bytes, is_compressed: bool) -> bytes:
        """
        Décompresse les données si nécessaire.
        
        Args:
            data: Les données à décompresser.
            is_compressed: Indique si les données sont compressées.
            
        Returns:
            bytes: Les données décompressées.
        """
        if not is_compressed:
            return data
            
        try:
            return zlib.decompress(data)
        except Exception as e:
            logger.error(f"Erreur lors de la décompression des données: {e}")
            return data  # Retourner les données originales en cas d'erreur
    
    @measure_latency(STEP_TTS_CACHE_GET, "cache_key")
    async def get_audio(self, cache_key: str) -> Optional[bytes]:
        """
        Récupère l'audio depuis le cache.
        
        Args:
            cache_key: La clé de cache.
            
        Returns:
            Optional[bytes]: Les données audio ou None si non trouvées.
        """
        start_time = time.time()
        
        if not self.cache_enabled:
            self.metrics["misses"] += 1
            return None
            
        redis_conn = await self.get_connection()
        if not redis_conn:
            self.metrics["misses"] += 1
            return None
            
        try:
            # Récupérer les données et les métadonnées
            pipeline = redis_conn.pipeline()
            await pipeline.get(cache_key)
            await pipeline.get(f"{cache_key}:meta")
            results = await pipeline.execute()
            
            cached_audio, meta_data = results
            
            if not cached_audio:
                logger.debug(f"Cache TTS MISS pour clé: {cache_key}")
                self.metrics["misses"] += 1
                return None
                
            # Traiter les métadonnées
            is_compressed = False
            if meta_data:
                try:
                    meta_dict = eval(meta_data.decode('utf-8'))
                    is_compressed = meta_dict.get('compressed', False)
                except Exception as e:
                    logger.warning(f"Erreur lors du décodage des métadonnées: {e}")
            
            # Décompresser si nécessaire
            audio_data = self._decompress_data(cached_audio, is_compressed)
            
            logger.info(f"Cache TTS HIT pour clé: {cache_key}")
            self.metrics["hits"] += 1
            
            # Mettre à jour les métriques de latence
            latency = time.time() - start_time
            self.metrics["get_latency_sum"] += latency
            self.metrics["get_latency_count"] += 1
            
            return audio_data
            
        except Exception as e:
            logger.error(f"Erreur lors de la lecture du cache TTS Redis: {e}")
            self.metrics["misses"] += 1
            return None
        finally:
            if redis_conn:
                await redis_conn.close()
    
    @measure_latency(STEP_TTS_CACHE_SET, "cache_key")
    async def set_audio(self, cache_key: str, audio_data: bytes, 
                       expiration: Optional[int] = None) -> bool:
        """
        Stocke l'audio dans le cache.
        
        Args:
            cache_key: La clé de cache.
            audio_data: Les données audio à stocker.
            expiration: Durée d'expiration en secondes (optionnel).
            
        Returns:
            bool: True si le stockage a réussi, False sinon.
        """
        start_time = time.time()
        
        if not self.cache_enabled or not audio_data:
            return False
            
        if not expiration:
            expiration = self.cache_expiration
            
        redis_conn = await self.get_connection()
        if not redis_conn:
            return False
            
        try:
            # Compresser les données si nécessaire
            compressed_data, is_compressed = self._compress_data(audio_data)
            
            # Préparer les métadonnées
            meta_data = {
                'size_original': len(audio_data),
                'size_stored': len(compressed_data),
                'compressed': is_compressed,
                'timestamp': time.time()
            }
            
            # Stocker les données et les métadonnées
            pipeline = redis_conn.pipeline()
            await pipeline.set(cache_key, compressed_data, ex=expiration)
            await pipeline.set(f"{cache_key}:meta", str(meta_data), ex=expiration)
            await pipeline.execute()
            
            logger.info(f"Audio TTS mis en cache (clé: {cache_key}, taille: {len(compressed_data)} bytes)")
            self.metrics["set_success"] += 1
            
            # Mettre à jour les métriques de latence
            latency = time.time() - start_time
            self.metrics["set_latency_sum"] += latency
            self.metrics["set_latency_count"] += 1
            
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de l'écriture du cache TTS Redis: {e}")
            self.metrics["set_error"] += 1
            return False
        finally:
            if redis_conn:
                await redis_conn.close()
    
    async def stream_from_cache(self, cache_key: str, chunk_callback) -> bool:
        """
        Streame l'audio depuis le cache vers un callback.
        
        Args:
            cache_key: La clé de cache.
            chunk_callback: Fonction de callback pour traiter chaque chunk.
            
        Returns:
            bool: True si le streaming a réussi, False sinon.
        """
        audio_data = await self.get_audio(cache_key)
        if not audio_data:
            return False
            
        # Streamer les données par chunks
        chunk_size = 2048  # Taille des chunks à envoyer
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i+chunk_size]
            await chunk_callback(chunk)
            await asyncio.sleep(0.01)  # Petit délai pour éviter de saturer le client
            
        return True
    
    async def get_metrics(self) -> Dict[str, Any]:
        """
        Récupère les métriques du cache.
        
        Returns:
            Dict[str, Any]: Les métriques du cache.
        """
        metrics = self.metrics.copy()
        
        # Calculer les métriques dérivées
        total_requests = metrics["hits"] + metrics["misses"]
        if total_requests > 0:
            metrics["hit_ratio"] = metrics["hits"] / total_requests
        else:
            metrics["hit_ratio"] = 0
            
        if metrics["get_latency_count"] > 0:
            metrics["avg_get_latency"] = metrics["get_latency_sum"] / metrics["get_latency_count"]
        else:
            metrics["avg_get_latency"] = 0
            
        if metrics["set_latency_count"] > 0:
            metrics["avg_set_latency"] = metrics["set_latency_sum"] / metrics["set_latency_count"]
        else:
            metrics["avg_set_latency"] = 0
            
        # Ajouter des informations sur le cache Redis
        if self.cache_enabled and self.redis_pool:
            redis_conn = await self.get_connection()
            if redis_conn:
                try:
                    # Obtenir des informations sur Redis
                    info = await redis_conn.info()
                    metrics["redis_used_memory"] = info.get("used_memory_human", "N/A")
                    metrics["redis_total_keys"] = await redis_conn.dbsize()
                    
                    # Obtenir le nombre de clés TTS
                    tts_keys_count = 0
                    cursor = b'0'
                    while cursor:
                        cursor, keys = await redis_conn.scan(cursor=cursor, match=f"{self.cache_prefix}*", count=1000)
                        tts_keys_count += len(keys)
                    
                    metrics["tts_cache_keys"] = tts_keys_count
                except Exception as e:
                    logger.error(f"Erreur lors de la récupération des métriques Redis: {e}")
                finally:
                    await redis_conn.close()
        
        return metrics
    
    async def reset_metrics(self) -> None:
        """Réinitialise les métriques du cache."""
        self.metrics = {
            "hits": 0,
            "misses": 0,
            "set_success": 0,
            "set_error": 0,
            "get_latency_sum": 0,
            "get_latency_count": 0,
            "set_latency_sum": 0,
            "set_latency_count": 0,
            "last_reset_time": time.time()
        }
        
    async def clear_cache(self, pattern: str = None) -> int:
        """
        Vide le cache Redis pour les clés TTS.
        
        Args:
            pattern: Motif de clé à supprimer (optionnel).
            
        Returns:
            int: Nombre de clés supprimées.
        """
        if not self.cache_enabled:
            return 0
            
        redis_conn = await self.get_connection()
        if not redis_conn:
            return 0
            
        try:
            # Définir le motif de recherche
            if not pattern:
                pattern = f"{self.cache_prefix}*"
                
            # Supprimer les clés correspondant au motif
            keys_deleted = 0
            cursor = b'0'
            while cursor:
                cursor, keys = await redis_conn.scan(cursor=cursor, match=pattern, count=1000)
                if keys:
                    keys_deleted += await redis_conn.delete(*keys)
                    
                    # Supprimer également les métadonnées
                    meta_keys = [f"{key.decode('utf-8')}:meta".encode('utf-8') for key in keys]
                    await redis_conn.delete(*meta_keys)
            
            logger.info(f"Cache TTS vidé: {keys_deleted} clés supprimées")
            return keys_deleted
            
        except Exception as e:
            logger.error(f"Erreur lors du vidage du cache TTS: {e}")
            return 0
        finally:
            if redis_conn:
                await redis_conn.close()
    
    async def preload_cache(self, texts: List[str], language: str, speaker_id: str,
                           emotion: Optional[str] = None, voice_id: Optional[str] = None,
                           tts_service = None) -> Dict[str, Any]:
        """
        Précharge le cache avec des textes fréquemment utilisés.
        
        Args:
            texts: Liste des textes à précharger.
            language: La langue des textes.
            speaker_id: L'ID du speaker.
            emotion: L'émotion à appliquer (optionnel).
            voice_id: L'ID de la voix à utiliser (optionnel).
            tts_service: Service TTS à utiliser pour la synthèse (optionnel).
            
        Returns:
            Dict[str, Any]: Statistiques sur le préchargement.
        """
        if not self.cache_enabled or not tts_service:
            return {"success": False, "reason": "Cache désactivé ou service TTS non fourni"}
            
        stats = {
            "total": len(texts),
            "already_cached": 0,
            "newly_cached": 0,
            "failed": 0
        }
        
        for text in texts:
            # Générer la clé de cache
            cache_key = self.generate_cache_key(text, language, speaker_id, emotion, voice_id)
            
            # Vérifier si déjà en cache
            existing_audio = await self.get_audio(cache_key)
            if existing_audio:
                stats["already_cached"] += 1
                continue
                
            try:
                # Synthétiser l'audio
                audio_data = await tts_service.synthesize_text(text, language, speaker_id, emotion, voice_id)
                
                if audio_data:
                    # Stocker dans le cache
                    success = await self.set_audio(cache_key, audio_data)
                    if success:
                        stats["newly_cached"] += 1
                    else:
                        stats["failed"] += 1
                else:
                    stats["failed"] += 1
                    
            except Exception as e:
                logger.error(f"Erreur lors du préchargement du cache pour '{text}': {e}")
                stats["failed"] += 1
                
        return stats

# Créer une instance singleton
tts_cache_service = TTSCacheService()