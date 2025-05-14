import time
import logging
import functools
import os
from typing import Callable, Any, Dict, List, Tuple, Optional # Ajout de Optional

# Configuration du logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Constantes pour les étapes de latence
STEP_ASR_TRANSCRIPTION = "asr_transcription"
STEP_LLM_GENERATE = "llm_generate"
STEP_TTS_SYNTHESIS = "tts_synthesis"
STEP_TTS_CACHE_GET = "tts_cache_get"
STEP_TTS_CACHE_SET = "tts_cache_set"
STEP_WEBSOCKET_SEND = "websocket_send"
STEP_SESSION_START = "session_start"

# Créer le répertoire de logs si nécessaire
LOG_DIR = "/home/ubuntu/eloquence_logs" 
os.makedirs(LOG_DIR, exist_ok=True)

# Fichier de log pour les latences
LATENCY_LOG_FILE = os.path.join(LOG_DIR, "latency_log.tsv")

# Initialiser le fichier de log avec les en-têtes si nécessaire
if not os.path.exists(LATENCY_LOG_FILE):
    with open(LATENCY_LOG_FILE, "w") as f:
        f.write("timestamp\tsession_id\tstep_name\tduration_ms\tmetadata\n")

# Structure pour stocker les latences d'une session
class SessionLatencyContext:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.latencies: List[Tuple[str, float, Dict[str, Any]]] = []
        self.start_time = time.time()

    def add_latency(self, step_name: str, duration_ms: float, metadata: Optional[Dict[str, Any]] = None):
        self.latencies.append((step_name, duration_ms, metadata or {}))
        # Écrire immédiatement dans le fichier de log
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        metadata_str = ";".join([f"{k}={v}" for k, v in (metadata or {}).items()])
        log_entry = f"{timestamp}\t{self.session_id}\t{step_name}\t{duration_ms:.2f}\t{metadata_str}\n"
        try:
            with open(LATENCY_LOG_FILE, "a") as f:
                f.write(log_entry)
        except Exception as e:
            logger.error(f"Erreur lors de l'écriture dans le fichier de log de latence: {e}")


    def get_summary(self) -> Dict[str, Any]:
        total_duration_ms = (time.time() - self.start_time) * 1000
        return {
            "session_id": self.session_id,
            "total_duration_ms": total_duration_ms,
            "steps": [
                {"step": name, "duration_ms": dur, "metadata": meta}
                for name, dur, meta in self.latencies
            ]
        }

# Contexte asynchrone pour mesurer la latence
class AsyncLatencyContext:
    def __init__(self, session_context: SessionLatencyContext, step_name: str, metadata_keys: Optional[List[str]] = None):
        self.session_context = session_context
        self.step_name = step_name
        self.metadata_keys = metadata_keys or []
        self.start_time = 0
        self.metadata: Dict[str, Any] = {}

    async def __aenter__(self):
        self.start_time = time.perf_counter()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        self.session_context.add_latency(self.step_name, duration_ms, self.metadata)
        logger.info(f"Latence pour {self.step_name} (session {self.session_context.session_id}): {duration_ms:.2f} ms")

    def set_metadata(self, **kwargs):
        for key, value in kwargs.items():
            if key in self.metadata_keys:
                self.metadata[key] = value
            else:
                logger.warning(f"Clé de métadonnée '{key}' non autorisée pour l'étape '{self.step_name}'.")


# Décorateur pour mesurer la latence des fonctions asynchrones
def measure_latency(step_name: str, *metadata_keys: str):
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Essayer de trouver un SessionLatencyContext dans les arguments
            session_context = None
            for arg in args:
                if isinstance(arg, SessionLatencyContext):
                    session_context = arg
                    break
            
            # Si on ne trouve pas de contexte de session, on ne mesure pas la latence
            # Cela permet d'utiliser le décorateur sur des fonctions qui ne sont pas toujours
            # appelées dans un contexte de session (ex: fonctions utilitaires)
            if session_context is None:
                logger.debug(f"Aucun contexte de session trouvé pour {func.__name__}, latence non mesurée.")
                return await func(*args, **kwargs)

            async with AsyncLatencyContext(session_context, step_name, list(metadata_keys)) as latency_ctx:
                # Extraire les métadonnées des arguments de la fonction
                func_args = func.__code__.co_varnames[:func.__code__.co_argcount]
                metadata_values = {key: value for key, value in zip(func_args, args)}
                metadata_values.update(kwargs) # Ajouter les kwargs

                # Définir les métadonnées pour le contexte de latence
                meta_to_set = {key: metadata_values.get(key) for key in metadata_keys if key in metadata_values}
                latency_ctx.set_metadata(**meta_to_set)
                
                return await func(*args, **kwargs)
        return wrapper
    return decorator