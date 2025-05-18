"""
Routes pour le monitoring de l'application.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any, Optional

from core.auth import get_current_user_id
from core.latency_monitor import get_latency_stats

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/monitoring/latency")
async def monitoring_latency(
    session_id: Optional[str] = None,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Récupère les statistiques de latence.
    
    Args:
        session_id: Identifiant de la session pour filtrer les statistiques
        
    Returns:
        Dict[str, Any]: Statistiques de latence
    """
    try:
        # Récupérer les statistiques de latence
        stats = get_latency_stats(session_id)
        
        return stats
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des statistiques de latence: {e}")
        # Retourner des données simulées en cas d'erreur
        return {
            "status": "error",
            "message": f"Erreur lors de la récupération des statistiques de latence: {str(e)}",
            "fallback_data": {
                "tts": 150,
                "stt": 200,
                "llm": 300,
                "total": 650
            }
        }

@router.get("/monitoring/status")
async def monitoring_status(
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Récupère l'état des services.
    
    Returns:
        Dict[str, Any]: État des services
    """
    try:
        # Vérifier l'état des services
        # Dans une implémentation réelle, on vérifierait l'état de chaque service
        # Pour l'instant, on retourne des données simulées
        return {
            "services": {
                "tts": {
                    "status": "ok",
                    "latency": 150,
                    "uptime": 3600
                },
                "stt": {
                    "status": "ok",
                    "latency": 200,
                    "uptime": 3600
                },
                "llm": {
                    "status": "ok",
                    "latency": 300,
                    "uptime": 3600
                },
                "database": {
                    "status": "ok",
                    "latency": 50,
                    "uptime": 3600
                }
            },
            "system": {
                "cpu": 50,
                "memory": 60,
                "disk": 70
            }
        }
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de l'état des services: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération de l'état des services: {str(e)}"
        )