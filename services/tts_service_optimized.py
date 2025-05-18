"""
Service TTS optimisé avec gestion de cache.
Ce module fournit une interface optimisée pour la synthèse vocale avec mise en cache des résultats.
"""

import logging
import time
import asyncio
from typing import Dict, List, Any, Optional
import hashlib

from core.config import settings
from services.tts_service import TtsService
from services.tts_cache_service import tts_cache_service

logger = logging.getLogger(__name__)

class TtsServiceOptimized:
    """
    Service TTS optimisé avec gestion de cache.
    """
    
    def __init__(self):
        """
        Initialise le service TTS optimisé.
        """
        self.tts_service = TtsService()
        self.metrics = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_synthesis_time": 0,
            "total_audio_length": 0,
            "preloaded_phrases": 0,
            "failed_synthesis": 0
        }
        logger.info("Service TTS optimisé initialisé")
    
    async def get_metrics(self) -> Dict[str, Any]:
        """
        Récupère les métriques du service TTS.
        
        Returns:
            Dict[str, Any]: Les métriques du service TTS.
        """
        hit_rate = 0
        if self.metrics["total_requests"] > 0:
            hit_rate = self.metrics["cache_hits"] / self.metrics["total_requests"]
        
        avg_synthesis_time = 0
        if self.metrics["cache_misses"] > 0:
            avg_synthesis_time = self.metrics["total_synthesis_time"] / self.metrics["cache_misses"]
        
        return {
            "total_requests": self.metrics["total_requests"],
            "cache_hits": self.metrics["cache_hits"],
            "cache_misses": self.metrics["cache_misses"],
            "hit_rate": round(hit_rate, 2),
            "avg_synthesis_time": round(avg_synthesis_time, 3),
            "total_audio_length": round(self.metrics["total_audio_length"], 2),
            "preloaded_phrases": self.metrics["preloaded_phrases"],
            "failed_synthesis": self.metrics["failed_synthesis"]
        }
    
    async def reset_metrics(self) -> None:
        """
        Réinitialise les métriques du service TTS.
        """
        self.metrics = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_synthesis_time": 0,
            "total_audio_length": 0,
            "preloaded_phrases": 0,
            "failed_synthesis": 0
        }
        logger.info("Métriques du service TTS réinitialisées")
    
    def _generate_cache_key(self, text: str, language: str = "fr", emotion: str = "neutre", voice_id: Optional[str] = None) -> str:
        """
        Génère une clé de cache pour le texte et les paramètres donnés.
        
        Args:
            text: Texte à synthétiser
            language: Langue du texte
            emotion: Émotion à appliquer
            voice_id: ID de la voix à utiliser
            
        Returns:
            str: Clé de cache
        """
        # Normaliser le texte (supprimer les espaces superflus, etc.)
        normalized_text = " ".join(text.strip().split())
        
        # Créer une chaîne de caractères avec tous les paramètres
        params_str = f"{normalized_text}|{language}|{emotion}|{voice_id or 'default'}"
        
        # Générer un hash MD5 de la chaîne de caractères
        hash_obj = hashlib.md5(params_str.encode())
        hash_str = hash_obj.hexdigest()
        
        # Retourner la clé de cache avec un préfixe
        return f"tts:{hash_str}"
    
    async def synthesize(self, text: str, language: str = "fr", emotion: str = "neutre", voice_id: Optional[str] = None) -> bytes:
        """
        Synthétise le texte en audio, avec mise en cache.
        
        Args:
            text: Texte à synthétiser
            language: Langue du texte
            emotion: Émotion à appliquer
            voice_id: ID de la voix à utiliser
            
        Returns:
            bytes: Données audio
        """
        # Incrémenter le compteur de requêtes
        self.metrics["total_requests"] += 1
        
        # Générer la clé de cache
        cache_key = self._generate_cache_key(text, language, emotion, voice_id)
        
        # Vérifier si l'audio est déjà en cache
        if tts_cache_service.cache_enabled:
            cached_audio = await tts_cache_service.get(cache_key)
            if cached_audio:
                # Incrémenter le compteur de hits
                self.metrics["cache_hits"] += 1
                logger.debug(f"Cache hit pour '{text[:30]}...' (clé: {cache_key})")
                return cached_audio
        
        # Incrémenter le compteur de misses
        self.metrics["cache_misses"] += 1
        logger.debug(f"Cache miss pour '{text[:30]}...' (clé: {cache_key})")
        
        # Synthétiser l'audio
        start_time = time.time()
        try:
            audio_data = await self.tts_service.synthesize(text, language, emotion, voice_id)
            synthesis_time = time.time() - start_time
            
            # Mettre à jour les métriques
            self.metrics["total_synthesis_time"] += synthesis_time
            
            # Estimer la durée de l'audio (approximativement 1 seconde pour 15 caractères)
            estimated_audio_length = len(text) / 15
            self.metrics["total_audio_length"] += estimated_audio_length
            
            # Mettre en cache l'audio
            if tts_cache_service.cache_enabled:
                await tts_cache_service.set(cache_key, audio_data)
            
            return audio_data
        except Exception as e:
            # Incrémenter le compteur d'échecs
            self.metrics["failed_synthesis"] += 1
            logger.error(f"Erreur lors de la synthèse vocale: {e}")
            raise
    
    async def preload_common_phrases(self, phrases: List[str], language: str = "fr", emotion: str = "neutre", voice_id: Optional[str] = None) -> Dict[str, int]:
        """
        Précharge des phrases courantes dans le cache.
        
        Args:
            phrases: Liste des phrases à précharger
            language: Langue des phrases
            emotion: Émotion à appliquer
            voice_id: ID de la voix à utiliser
            
        Returns:
            Dict[str, int]: Statistiques de préchargement
        """
        if not tts_cache_service.cache_enabled:
            logger.warning("Préchargement ignoré: le cache est désactivé")
            return {
                "total": len(phrases),
                "already_cached": 0,
                "newly_cached": 0,
                "failed": len(phrases)
            }
        
        total = len(phrases)
        already_cached = 0
        newly_cached = 0
        failed = 0
        
        for phrase in phrases:
            try:
                # Générer la clé de cache
                cache_key = self._generate_cache_key(phrase, language, emotion, voice_id)
                
                # Vérifier si l'audio est déjà en cache
                cached_audio = await tts_cache_service.get(cache_key)
                if cached_audio:
                    already_cached += 1
                    continue
                
                # Synthétiser l'audio
                audio_data = await self.tts_service.synthesize(phrase, language, emotion, voice_id)
                
                # Mettre en cache l'audio
                await tts_cache_service.set(cache_key, audio_data)
                
                # Incrémenter le compteur de phrases préchargées
                self.metrics["preloaded_phrases"] += 1
                newly_cached += 1
                
                # Pause pour éviter de surcharger le service TTS
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Erreur lors du préchargement de '{phrase}': {e}")
                failed += 1
        
        logger.info(f"Préchargement terminé: {total} phrases, {already_cached} déjà en cache, {newly_cached} nouvellement mises en cache, {failed} échecs")
        
        return {
            "total": total,
            "already_cached": already_cached,
            "newly_cached": newly_cached,
            "failed": failed
        }

# Instance singleton du service TTS optimisé
tts_service_optimized = TtsServiceOptimized()