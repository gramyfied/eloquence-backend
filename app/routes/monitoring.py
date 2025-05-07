from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional
from pydantic import BaseModel

from core.latency_monitor import (
    get_latency_stats, 
    get_session_latency_stats, 
    get_latency_thresholds,
    update_latency_threshold,
    latency_monitor,
    DEFAULT_THRESHOLDS
)

router = APIRouter(
    tags=["monitoring"],
    responses={404: {"description": "Not found"}},
)


class ThresholdUpdate(BaseModel):
    threshold: float


@router.get("/latency")
async def get_all_latency_stats() -> Dict[str, Any]:
    """
    Récupère toutes les statistiques de latence.
    """
    return get_latency_stats()


@router.get("/latency/session/{session_id}")
async def get_latency_stats_for_session(session_id: str) -> Dict[str, Any]:
    """
    Récupère les statistiques de latence pour une session spécifique.
    """
    stats = get_session_latency_stats(session_id)
    if not stats:
        raise HTTPException(status_code=404, detail=f"Aucune statistique trouvée pour la session {session_id}")
    return stats


@router.get("/latency/thresholds")
async def get_all_latency_thresholds() -> Dict[str, float]:
    """
    Récupère tous les seuils d'alerte de latence.
    """
    return get_latency_thresholds()


@router.put("/latency/thresholds/{step}")
async def update_threshold(step: str, update: ThresholdUpdate) -> Dict[str, Any]:
    """
    Met à jour le seuil d'alerte pour une étape spécifique.
    """
    if step not in DEFAULT_THRESHOLDS:
        raise HTTPException(status_code=404, detail=f"Étape inconnue: {step}")
    
    return update_latency_threshold(step, update.threshold)


@router.post("/latency/reset")
async def reset_latency_stats() -> Dict[str, str]:
    """
    Réinitialise toutes les statistiques de latence.
    """
    latency_monitor.stats = latency_monitor.__class__().stats
    return {"status": "success", "message": "Statistiques de latence réinitialisées"}


@router.post("/latency/export")
async def export_latency_stats(filepath: Optional[str] = Query(None)) -> Dict[str, str]:
    """
    Exporte les statistiques de latence dans un fichier JSON.
    """
    if filepath:
        latency_monitor.save_stats_to_file(filepath)
    else:
        latency_monitor.save_stats_to_file()
    
    return {"status": "success", "message": "Statistiques de latence exportées"}


@router.get("/latency/report")
async def generate_latency_report() -> Dict[str, Any]:
    """
    Génère un rapport détaillé des statistiques de latence.
    """
    stats = get_latency_stats()
    thresholds = get_latency_thresholds()
    
    report = {
        "stats": stats,
        "thresholds": thresholds,
        "alerts": [],
        "recommendations": []
    }
    
    # Générer des alertes pour les étapes qui dépassent les seuils
    for step, step_stats in stats["global"].items():
        if step in thresholds and step_stats["p95"] > thresholds[step]:
            report["alerts"].append({
                "step": step,
                "p95": step_stats["p95"],
                "threshold": thresholds[step],
                "severity": "high" if step_stats["p95"] > 2 * thresholds[step] else "medium"
            })
    
    # Générer des recommandations basées sur les statistiques
    if "asr_transcribe" in stats["global"] and stats["global"]["asr_transcribe"]["p95"] > thresholds.get("asr_transcribe", 2.0):
        report["recommendations"].append({
            "step": "asr_transcribe",
            "message": "Envisager d'utiliser un modèle ASR plus petit ou d'optimiser les paramètres de Whisper"
        })
    
    if "llm_generate" in stats["global"] and stats["global"]["llm_generate"]["p95"] > thresholds.get("llm_generate", 3.0):
        report["recommendations"].append({
            "step": "llm_generate",
            "message": "Envisager de réduire la taille du contexte ou d'optimiser les paramètres du LLM"
        })
    
    if "tts_synthesize" in stats["global"] and stats["global"]["tts_synthesize"]["p95"] > thresholds.get("tts_synthesize", 1.0):
        report["recommendations"].append({
            "step": "tts_synthesize",
            "message": "Vérifier que le cache TTS est activé et fonctionne correctement"
        })
    
    # Générer une recommandation globale
    if report["alerts"]:
        report["summary"] = "Des problèmes de latence ont été détectés. Voir les alertes et recommandations."
    else:
        report["summary"] = "Aucun problème de latence détecté."
    
    # Générer le rapport dans les logs
    latency_monitor.log_latency_report()
    
    return report