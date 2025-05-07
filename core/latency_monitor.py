import time
import logging
import statistics
from typing import Dict, List, Optional, Tuple, Any
import threading
import json
import os
from datetime import datetime, timedelta
import asyncio
from functools import wraps
import inspect

from core.config import settings

# Configuration du logger spécifique pour les métriques de latence
latency_logger = logging.getLogger("eloquence.latency")
latency_logger.setLevel(logging.INFO)

# Formatter pour les logs de latence
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Handler pour les logs de latence dans un fichier séparé
os.makedirs("./logs", exist_ok=True)
latency_file_handler = logging.FileHandler("./logs/latency.log")
latency_file_handler.setFormatter(formatter)
latency_logger.addHandler(latency_file_handler)

# Constantes pour les étapes du pipeline
STEP_VAD_PROCESS = "vad_process"
STEP_ASR_TRANSCRIBE = "asr_transcribe"
STEP_LLM_GENERATE = "llm_generate"
STEP_TTS_SYNTHESIZE = "tts_synthesize"
STEP_TOTAL_TURN = "total_turn"
STEP_AUDIO_SAVE = "audio_save"
STEP_DB_OPERATION = "db_operation"
STEP_KALDI_SCHEDULE = "kaldi_schedule"

# Seuils d'alerte (en secondes)
DEFAULT_THRESHOLDS = {
    STEP_VAD_PROCESS: 0.05,      # 50ms pour le VAD
    STEP_ASR_TRANSCRIBE: 2.0,    # 2s pour l'ASR
    STEP_LLM_GENERATE: 3.0,      # 3s pour le LLM
    STEP_TTS_SYNTHESIZE: 1.0,    # 1s pour le TTS
    STEP_TOTAL_TURN: 5.0,        # 5s pour un tour complet
    STEP_AUDIO_SAVE: 0.2,        # 200ms pour sauvegarder l'audio
    STEP_DB_OPERATION: 0.1,      # 100ms pour les opérations DB
    STEP_KALDI_SCHEDULE: 0.1     # 100ms pour planifier l'analyse Kaldi
}

class LatencyStats:
    """Classe pour stocker et analyser les statistiques de latence."""
    
    def __init__(self):
        self.measurements: Dict[str, List[float]] = {}
        self.lock = threading.Lock()
        self.session_measurements: Dict[str, Dict[str, List[float]]] = {}
        
    def add_measurement(self, step: str, duration: float, session_id: Optional[str] = None):
        """Ajoute une mesure de latence pour une étape donnée."""
        with self.lock:
            # Ajouter à la liste globale
            if step not in self.measurements:
                self.measurements[step] = []
            self.measurements[step].append(duration)
            
            # Limiter la taille de l'historique pour éviter une consommation mémoire excessive
            if len(self.measurements[step]) > 1000:
                self.measurements[step] = self.measurements[step][-1000:]
            
            # Si un session_id est fourni, ajouter aux mesures spécifiques à la session
            if session_id:
                if session_id not in self.session_measurements:
                    self.session_measurements[session_id] = {}
                if step not in self.session_measurements[session_id]:
                    self.session_measurements[session_id][step] = []
                self.session_measurements[session_id][step].append(duration)
    
    def get_stats(self, step: str) -> Dict[str, float]:
        """Retourne les statistiques pour une étape donnée."""
        with self.lock:
            if step not in self.measurements or not self.measurements[step]:
                return {"count": 0, "min": 0, "max": 0, "mean": 0, "median": 0, "p95": 0, "p99": 0}
            
            values = self.measurements[step]
            return {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "mean": statistics.mean(values),
                "median": statistics.median(values),
                "p95": statistics.quantiles(values, n=20)[18] if len(values) >= 20 else max(values),
                "p99": statistics.quantiles(values, n=100)[98] if len(values) >= 100 else max(values)
            }
    
    def get_session_stats(self, session_id: str) -> Dict[str, Dict[str, float]]:
        """Retourne les statistiques pour une session donnée."""
        with self.lock:
            if session_id not in self.session_measurements:
                return {}
            
            result = {}
            for step, values in self.session_measurements[session_id].items():
                if not values:
                    result[step] = {"count": 0, "min": 0, "max": 0, "mean": 0, "median": 0}
                    continue
                
                result[step] = {
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "mean": statistics.mean(values),
                    "median": statistics.median(values)
                }
            
            return result
    
    def clear_session(self, session_id: str):
        """Supprime les mesures pour une session donnée."""
        with self.lock:
            if session_id in self.session_measurements:
                del self.session_measurements[session_id]
    
    def export_stats(self) -> Dict[str, Any]:
        """Exporte toutes les statistiques au format JSON."""
        result = {
            "global": {},
            "sessions": {}
        }
        
        # Copier les données sous le verrou pour minimiser le temps de blocage
        with self.lock:
            steps = list(self.measurements.keys())
            session_ids = list(self.session_measurements.keys())
        
        # Calculer les statistiques globales sans bloquer
        for step in steps:
            with self.lock:
                # Prendre un snapshot des mesures pour ce step
                values = self.measurements.get(step, [])[:]
            
            # Calculer les statistiques sur le snapshot
            if not values:
                result["global"][step] = {"count": 0, "min": 0, "max": 0, "mean": 0, "median": 0, "p95": 0, "p99": 0}
                continue
                
            result["global"][step] = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "mean": statistics.mean(values),
                "median": statistics.median(values),
                "p95": statistics.quantiles(values, n=20)[18] if len(values) >= 20 else max(values),
                "p99": statistics.quantiles(values, n=100)[98] if len(values) >= 100 else max(values)
            }
        
        # Limiter le nombre de sessions pour éviter un timeout
        max_sessions = 10
        if len(session_ids) > max_sessions:
            session_ids = session_ids[:max_sessions]
            
        # Calculer les statistiques par session
        for session_id in session_ids:
            result["sessions"][session_id] = self.get_session_stats(session_id)
        
        return result
    
    def save_stats_to_file(self, filepath: str = "./logs/latency_stats.json"):
        """Sauvegarde les statistiques dans un fichier JSON."""
        stats = self.export_stats()
        with open(filepath, 'w') as f:
            json.dump(stats, f, indent=2)


class LatencyMonitor:
    """Classe principale pour le monitoring de latence."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LatencyMonitor, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.stats = LatencyStats()
        self.current_timers: Dict[Tuple[str, str], float] = {}  # (session_id, step) -> start_time
        self.lock = threading.Lock()
        self.thresholds = DEFAULT_THRESHOLDS.copy()
        self._initialized = True
        
        # Planifier l'export périodique des statistiques
        self._schedule_stats_export()
    
    def _schedule_stats_export(self):
        """Planifie l'export périodique des statistiques."""
        def _export_task():
            while True:
                time.sleep(3600)  # Export toutes les heures
                try:
                    self.stats.save_stats_to_file()
                    # Rotation des logs si nécessaire
                    self._rotate_logs()
                except Exception as e:
                    latency_logger.error(f"Erreur lors de l'export des statistiques: {e}")
        
        export_thread = threading.Thread(target=_export_task, daemon=True)
        export_thread.start()
    
    def _rotate_logs(self):
        """Effectue une rotation des logs si nécessaire."""
        log_file = "./logs/latency.log"
        try:
            # Si le fichier dépasse 10 Mo, faire une rotation
            if os.path.exists(log_file) and os.path.getsize(log_file) > 10 * 1024 * 1024:
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                os.rename(log_file, f"./logs/latency_{timestamp}.log")
                # Recréer le handler
                latency_logger.removeHandler(latency_file_handler)
                new_handler = logging.FileHandler(log_file)
                new_handler.setFormatter(formatter)
                latency_logger.addHandler(new_handler)
        except Exception as e:
            latency_logger.error(f"Erreur lors de la rotation des logs: {e}")
    
    def start_timer(self, step: str, session_id: Optional[str] = None) -> None:
        """Démarre un timer pour une étape donnée."""
        key = (session_id or "global", step)
        with self.lock:
            self.current_timers[key] = time.time()
    
    def stop_timer(self, step: str, session_id: Optional[str] = None) -> float:
        """Arrête un timer et retourne la durée en secondes."""
        key = (session_id or "global", step)
        with self.lock:
            if key not in self.current_timers:
                latency_logger.warning(f"Timer non démarré pour {step} (session: {session_id})")
                return 0
            
            start_time = self.current_timers.pop(key)
            duration = time.time() - start_time
            
            # Enregistrer la mesure
            self.stats.add_measurement(step, duration, session_id)
            
            # Vérifier si la durée dépasse le seuil
            threshold = self.thresholds.get(step)
            if threshold and duration > threshold:
                latency_logger.warning(
                    f"Latence élevée détectée: {step} = {duration:.3f}s (seuil: {threshold:.3f}s, "
                    f"session: {session_id})"
                )
            
            return duration
    
    def measure(self, step: str, session_id: Optional[str] = None):
        """Décorateur pour mesurer la latence d'une fonction."""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                self.start_timer(step, session_id)
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    self.stop_timer(step, session_id)
            
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                self.start_timer(step, session_id)
                try:
                    result = await func(*args, **kwargs)
                    return result
                finally:
                    self.stop_timer(step, session_id)
            
            if inspect.iscoroutinefunction(func):
                return async_wrapper
            return wrapper
        
        return decorator
    
    def set_threshold(self, step: str, threshold: float) -> None:
        """Définit un seuil d'alerte pour une étape donnée."""
        with self.lock:
            self.thresholds[step] = threshold
    
    def get_stats(self, step: Optional[str] = None) -> Dict:
        """Retourne les statistiques globales ou pour une étape spécifique."""
        if step:
            return self.stats.get_stats(step)
        
        result = {}
        for s in self.stats.measurements:
            result[s] = self.stats.get_stats(s)
        return result
    
    def get_session_stats(self, session_id: str) -> Dict:
        """Retourne les statistiques pour une session donnée."""
        return self.stats.get_session_stats(session_id)
    
    def clear_session(self, session_id: str) -> None:
        """Supprime les mesures pour une session donnée."""
        self.stats.clear_session(session_id)
    
    def export_stats(self) -> Dict:
        """Exporte toutes les statistiques."""
        return self.stats.export_stats()
    
    def save_stats_to_file(self, filepath: str = "./logs/latency_stats.json") -> None:
        """Sauvegarde les statistiques dans un fichier JSON."""
        self.stats.save_stats_to_file(filepath)
    
    def log_latency_report(self) -> None:
        """Génère un rapport de latence dans les logs."""
        stats = self.get_stats()
        latency_logger.info("=== Rapport de Latence ===")
        for step, step_stats in stats.items():
            latency_logger.info(
                f"{step}: count={step_stats['count']}, "
                f"min={step_stats['min']:.3f}s, "
                f"max={step_stats['max']:.3f}s, "
                f"mean={step_stats['mean']:.3f}s, "
                f"median={step_stats['median']:.3f}s, "
                f"p95={step_stats.get('p95', 0):.3f}s, "
                f"p99={step_stats.get('p99', 0):.3f}s"
            )
        latency_logger.info("========================")


# Instance singleton
latency_monitor = LatencyMonitor()


# Décorateurs pratiques pour les fonctions et méthodes
def measure_latency(step: str, session_id_arg: Optional[str] = None):
    """
    Décorateur pour mesurer la latence d'une fonction ou méthode.
    
    Args:
        step: Nom de l'étape à mesurer
        session_id_arg: Nom de l'argument contenant l'ID de session, ou None
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Déterminer l'ID de session
            session_id = None
            if session_id_arg:
                if session_id_arg in kwargs:
                    session_id = kwargs[session_id_arg]
                elif len(args) > 0 and isinstance(args[0], str):
                    # Premier argument positionnel pourrait être l'ID de session
                    session_id = args[0]
            
            latency_monitor.start_timer(step, session_id)
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                latency_monitor.stop_timer(step, session_id)
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Déterminer l'ID de session
            session_id = None
            if session_id_arg:
                if session_id_arg in kwargs:
                    session_id = kwargs[session_id_arg]
                elif len(args) > 0 and isinstance(args[0], str):
                    # Premier argument positionnel pourrait être l'ID de session
                    session_id = args[0]
            
            latency_monitor.start_timer(step, session_id)
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                latency_monitor.stop_timer(step, session_id)
        
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return wrapper
    
    return decorator


# Contexte pour mesurer la latence dans un bloc de code
class LatencyContext:
    """Contexte pour mesurer la latence d'un bloc de code."""
    
    def __init__(self, step: str, session_id: Optional[str] = None):
        self.step = step
        self.session_id = session_id
    
    def __enter__(self):
        latency_monitor.start_timer(self.step, self.session_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        latency_monitor.stop_timer(self.step, self.session_id)


# Contexte asynchrone pour mesurer la latence dans un bloc de code asynchrone
class AsyncLatencyContext:
    """Contexte asynchrone pour mesurer la latence d'un bloc de code."""
    
    def __init__(self, step: str, session_id: Optional[str] = None):
        self.step = step
        self.session_id = session_id
    
    async def __aenter__(self):
        latency_monitor.start_timer(self.step, self.session_id)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        latency_monitor.stop_timer(self.step, self.session_id)


# API pour les routes FastAPI
def get_latency_stats():
    """Retourne les statistiques de latence pour l'API."""
    return latency_monitor.export_stats()


def get_session_latency_stats(session_id: str):
    """Retourne les statistiques de latence pour une session donnée."""
    return latency_monitor.get_session_stats(session_id)


def get_latency_thresholds():
    """Retourne les seuils d'alerte actuels."""
    return latency_monitor.thresholds


def update_latency_threshold(step: str, threshold: float):
    """Met à jour un seuil d'alerte."""
    latency_monitor.set_threshold(step, threshold)
    return {"step": step, "threshold": threshold}