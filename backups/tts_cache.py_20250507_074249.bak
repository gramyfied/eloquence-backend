"""
Routes API pour la gestion du cache TTS.
Ce module fournit des endpoints pour gérer le cache TTS, notamment pour obtenir des métriques,
vider le cache et précharger des phrases courantes.
"""

import logging
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from services.tts_service_optimized import tts_service_optimized
from services.tts_cache_service import tts_cache_service
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/tts-cache",
    tags=["TTS Cache"],
    responses={404: {"description": "Not found"}},
)

# Modèles de données pour les requêtes et réponses

class PreloadPhrasesRequest(BaseModel):
    """Modèle pour la requête de préchargement de phrases."""
    phrases: List[str] = Field(..., description="Liste des phrases à précharger")
    language: str = Field("fr", description="Langue des phrases")
    emotion: Optional[str] = Field(None, description="Émotion à appliquer")
    voice_id: Optional[str] = Field(None, description="ID de la voix à utiliser")

class PreloadPhrasesResponse(BaseModel):
    """Modèle pour la réponse de préchargement de phrases."""
    success: bool = Field(..., description="Indique si l'opération a réussi")
    total: int = Field(..., description="Nombre total de phrases")
    already_cached: int = Field(..., description="Nombre de phrases déjà en cache")
    newly_cached: int = Field(..., description="Nombre de phrases nouvellement mises en cache")
    failed: int = Field(..., description="Nombre de phrases dont la mise en cache a échoué")

class ClearCacheRequest(BaseModel):
    """Modèle pour la requête de vidage du cache."""
    pattern: Optional[str] = Field(None, description="Motif de clé à supprimer (optionnel)")

class ClearCacheResponse(BaseModel):
    """Modèle pour la réponse de vidage du cache."""
    success: bool = Field(..., description="Indique si l'opération a réussi")
    keys_deleted: int = Field(..., description="Nombre de clés supprimées")

class MetricsResponse(BaseModel):
    """Modèle pour la réponse de métriques."""
    tts_service: Dict[str, Any] = Field(..., description="Métriques du service TTS")
    cache_service: Dict[str, Any] = Field(..., description="Métriques du service de cache")

# Routes

@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """
    Récupère les métriques du cache TTS.
    
    Returns:
        MetricsResponse: Les métriques du cache TTS.
    """
    try:
        # Récupérer les métriques du service TTS
        tts_metrics = await tts_service_optimized.get_metrics()
        
        # Récupérer les métriques du service de cache
        cache_metrics = await tts_cache_service.get_metrics()
        
        return {
            "tts_service": tts_metrics,
            "cache_service": cache_metrics
        }
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des métriques: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des métriques: {str(e)}")

@router.post("/reset-metrics")
async def reset_metrics():
    """
    Réinitialise les métriques du cache TTS.
    
    Returns:
        Dict[str, bool]: Indique si l'opération a réussi.
    """
    try:
        # Réinitialiser les métriques du service TTS
        await tts_service_optimized.reset_metrics()
        
        # Réinitialiser les métriques du service de cache
        await tts_cache_service.reset_metrics()
        
        return {"success": True}
    except Exception as e:
        logger.error(f"Erreur lors de la réinitialisation des métriques: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la réinitialisation des métriques: {str(e)}")

@router.post("/clear", response_model=ClearCacheResponse)
async def clear_cache(request: ClearCacheRequest):
    """
    Vide le cache TTS.
    
    Args:
        request: Requête de vidage du cache.
        
    Returns:
        ClearCacheResponse: Réponse de vidage du cache.
    """
    try:
        # Vider le cache
        keys_deleted = await tts_cache_service.clear_cache(request.pattern)
        
        return {
            "success": True,
            "keys_deleted": keys_deleted
        }
    except Exception as e:
        logger.error(f"Erreur lors du vidage du cache: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du vidage du cache: {str(e)}")

@router.post("/preload", response_model=PreloadPhrasesResponse)
async def preload_phrases(request: PreloadPhrasesRequest, background_tasks: BackgroundTasks):
    """
    Précharge le cache avec des phrases courantes.
    
    Args:
        request: Requête de préchargement de phrases.
        background_tasks: Tâches en arrière-plan.
        
    Returns:
        PreloadPhrasesResponse: Réponse de préchargement de phrases.
    """
    try:
        # Vérifier si le cache est activé
        if not tts_cache_service.cache_enabled:
            raise HTTPException(status_code=400, detail="Le cache TTS est désactivé")
        
        # Vérifier si la liste de phrases est vide
        if not request.phrases:
            raise HTTPException(status_code=400, detail="La liste de phrases est vide")
        
        # Limiter le nombre de phrases
        if len(request.phrases) > 100:
            raise HTTPException(status_code=400, detail="Trop de phrases (max 100)")
        
        # Précharger le cache en arrière-plan si plus de 10 phrases
        if len(request.phrases) > 10:
            # Lancer le préchargement en arrière-plan
            background_tasks.add_task(
                tts_service_optimized.preload_common_phrases,
                request.phrases,
                request.language,
                request.emotion,
                request.voice_id
            )
            
            return {
                "success": True,
                "total": len(request.phrases),
                "already_cached": 0,
                "newly_cached": 0,
                "failed": 0,
                "message": "Préchargement lancé en arrière-plan"
            }
        else:
            # Précharger le cache de manière synchrone
            result = await tts_service_optimized.preload_common_phrases(
                request.phrases,
                request.language,
                request.emotion,
                request.voice_id
            )
            
            return {
                "success": True,
                "total": result["total"],
                "already_cached": result["already_cached"],
                "newly_cached": result["newly_cached"],
                "failed": result["failed"]
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors du préchargement du cache: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du préchargement du cache: {str(e)}")

@router.get("/status")
async def get_status():
    """
    Récupère l'état du cache TTS.
    
    Returns:
        Dict[str, Any]: L'état du cache TTS.
    """
    try:
        # Vérifier si le cache est activé
        cache_enabled = tts_cache_service.cache_enabled
        
        # Récupérer des informations sur Redis si le cache est activé
        redis_info = {}
        if cache_enabled:
            redis_conn = await tts_cache_service.get_connection()
            if redis_conn:
                try:
                    # Obtenir des informations sur Redis
                    info = await redis_conn.info()
                    redis_info = {
                        "version": info.get("redis_version", "N/A"),
                        "used_memory_human": info.get("used_memory_human", "N/A"),
                        "connected_clients": info.get("connected_clients", "N/A"),
                        "uptime_in_days": info.get("uptime_in_days", "N/A")
                    }
                except Exception as e:
                    logger.error(f"Erreur lors de la récupération des informations Redis: {e}")
                finally:
                    await redis_conn.close()
        
        return {
            "cache_enabled": cache_enabled,
            "cache_prefix": tts_cache_service.cache_prefix,
            "cache_expiration": tts_cache_service.cache_expiration,
            "compression_enabled": tts_cache_service.compression_enabled,
            "compression_level": tts_cache_service.compression_level,
            "redis_info": redis_info
        }
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de l'état du cache: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération de l'état du cache: {str(e)}")