"""
Module pour surveiller et mesurer les latences des différentes étapes du traitement.
"""

import logging
import time
import functools
from typing import Callable, Any, Dict, Optional

logger = logging.getLogger(__name__)

# Constantes pour les étapes de traitement
STEP_VAD_PROCESS = "vad_process"
STEP_ASR_TRANSCRIBE = "asr_transcribe"
STEP_LLM_GENERATE = "llm_generate"
STEP_TTS_SYNTHESIZE = "tts_synthesize"
STEP_KALDI_ANALYZE = "kaldi_analyze"
STEP_TTS_CACHE_GET = "tts_cache_get"
STEP_TTS_CACHE_SET = "tts_cache_set"

# Dictionnaire global pour stocker les métriques de latence
latency_metrics: Dict[str, Dict[str, float]] = {
    STEP_VAD_PROCESS: {"count": 0, "total_time": 0, "max_time": 0},
    STEP_ASR_TRANSCRIBE: {"count": 0, "total_time": 0, "max_time": 0},
    STEP_LLM_GENERATE: {"count": 0, "total_time": 0, "max_time": 0},
    STEP_TTS_SYNTHESIZE: {"count": 0, "total_time": 0, "max_time": 0},
    STEP_KALDI_ANALYZE: {"count": 0, "total_time": 0, "max_time": 0},
}

def measure_latency(step_name: str, param_name: Optional[str] = None):
    """
    Décorateur pour mesurer la latence d'une fonction.
    
    Args:
        step_name: Nom de l'étape de traitement
        param_name: Nom du paramètre à inclure dans les logs (optionnel)
        
    Returns:
        Fonction décorée
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            
            # Extraire la valeur du paramètre si spécifié
            param_value = None
            if param_name and param_name in kwargs:
                param_value = kwargs[param_name]
            
            try:
                # Exécuter la fonction
                result = await func(*args, **kwargs)
                return result
            finally:
                # Mesurer le temps écoulé
                elapsed_time = time.time() - start_time
                
                # Mettre à jour les métriques
                if step_name in latency_metrics:
                    latency_metrics[step_name]["count"] += 1
                    latency_metrics[step_name]["total_time"] += elapsed_time
                    latency_metrics[step_name]["max_time"] = max(
                        latency_metrics[step_name]["max_time"], elapsed_time
                    )
                
                # Journaliser la latence
                log_message = f"Latence {step_name}: {elapsed_time:.3f}s"
                if param_value:
                    log_message += f" ({param_name}: {param_value})"
                logger.debug(log_message)
        
        return wrapper
    
    return decorator

class AsyncLatencyContext:
    """
    Contexte de mesure de latence pour les opérations asynchrones.
    Permet de mesurer la latence d'un bloc de code asynchrone.
    
    Exemple d'utilisation:
    ```
    async with AsyncLatencyContext("step_name", "operation_id") as ctx:
        # Code asynchrone à mesurer
        result = await some_async_function()
        ctx.set_metadata({"key": "value"})
        return result
    ```
    """
    
    def __init__(self, step_name: str, operation_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        """
        Initialise le contexte de mesure de latence.
        
        Args:
            step_name: Nom de l'étape de traitement
            operation_id: Identifiant de l'opération (optionnel)
            metadata: Métadonnées supplémentaires (optionnel)
        """
        self.step_name = step_name
        self.operation_id = operation_id
        self.metadata = metadata or {}
        self.start_time = 0.0
        self.end_time = 0.0
        
    async def __aenter__(self):
        """Début du bloc de code à mesurer."""
        self.start_time = time.time()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Fin du bloc de code à mesurer."""
        self.end_time = time.time()
        elapsed_time = self.end_time - self.start_time
        
        # Mettre à jour les métriques
        if self.step_name in latency_metrics:
            latency_metrics[self.step_name]["count"] += 1
            latency_metrics[self.step_name]["total_time"] += elapsed_time
            latency_metrics[self.step_name]["max_time"] = max(
                latency_metrics[self.step_name]["max_time"], elapsed_time
            )
        
        # Journaliser la latence
        log_message = f"Latence {self.step_name}: {elapsed_time:.3f}s"
        if self.operation_id:
            log_message += f" (op: {self.operation_id})"
        if self.metadata:
            log_message += f" {self.metadata}"
        logger.debug(log_message)
        
    def set_metadata(self, metadata: Dict[str, Any]):
        """
        Ajoute des métadonnées au contexte.
        
        Args:
            metadata: Métadonnées à ajouter
        """
        self.metadata.update(metadata)

def get_latency_metrics() -> Dict[str, Dict[str, float]]:
    """
    Récupère les métriques de latence actuelles.
    
    Returns:
        Dict[str, Dict[str, float]]: Métriques de latence
    """
    metrics = {}
    
    for step, data in latency_metrics.items():
        count = data["count"]
        avg_time = data["total_time"] / count if count > 0 else 0
        
        metrics[step] = {
            "count": count,
            "avg_time": avg_time,
            "max_time": data["max_time"]
        }
    
    return metrics

def get_latency_stats(session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Récupère les statistiques de latence pour le monitoring.
    
    Args:
        session_id: Identifiant de la session pour filtrer les statistiques (non utilisé actuellement)
        
    Returns:
        Dict[str, Any]: Statistiques de latence formatées pour l'API
    """
    # Récupérer les métriques brutes
    metrics = get_latency_metrics()
    
    # Convertir en millisecondes et formater pour l'API
    stats = {
        "status": "ok",
        "latency": {
            "tts": round(metrics.get(STEP_TTS_SYNTHESIZE, {}).get("avg_time", 0) * 1000),
            "stt": round(metrics.get(STEP_ASR_TRANSCRIBE, {}).get("avg_time", 0) * 1000),
            "llm": round(metrics.get(STEP_LLM_GENERATE, {}).get("avg_time", 0) * 1000),
            "vad": round(metrics.get(STEP_VAD_PROCESS, {}).get("avg_time", 0) * 1000),
            "kaldi": round(metrics.get(STEP_KALDI_ANALYZE, {}).get("avg_time", 0) * 1000)
        },
        "counts": {
            "tts": metrics.get(STEP_TTS_SYNTHESIZE, {}).get("count", 0),
            "stt": metrics.get(STEP_ASR_TRANSCRIBE, {}).get("count", 0),
            "llm": metrics.get(STEP_LLM_GENERATE, {}).get("count", 0),
            "vad": metrics.get(STEP_VAD_PROCESS, {}).get("count", 0),
            "kaldi": metrics.get(STEP_KALDI_ANALYZE, {}).get("count", 0)
        },
        "max_latency": {
            "tts": round(metrics.get(STEP_TTS_SYNTHESIZE, {}).get("max_time", 0) * 1000),
            "stt": round(metrics.get(STEP_ASR_TRANSCRIBE, {}).get("max_time", 0) * 1000),
            "llm": round(metrics.get(STEP_LLM_GENERATE, {}).get("max_time", 0) * 1000),
            "vad": round(metrics.get(STEP_VAD_PROCESS, {}).get("max_time", 0) * 1000),
            "kaldi": round(metrics.get(STEP_KALDI_ANALYZE, {}).get("max_time", 0) * 1000)
        }
    }
    
    # Calculer la latence totale moyenne
    total_latency = (
        stats["latency"]["tts"] +
        stats["latency"]["stt"] +
        stats["latency"]["llm"] +
        stats["latency"]["vad"] +
        stats["latency"]["kaldi"]
    )
    
    stats["latency"]["total"] = total_latency
    
    return stats

def reset_latency_metrics() -> None:
    """
    Réinitialise les métriques de latence.
    """
    for step in latency_metrics:
        latency_metrics[step] = {"count": 0, "total_time": 0, "max_time": 0}