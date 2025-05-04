# Package services pour l'application Eloquence
# Ce fichier permet d'importer les services comme des modules Python

import logging
from core.config import settings

logger = logging.getLogger(__name__)

# Importer les services
from .vad_service import VadService
from .asr_service import AsrService
from .tts_service import TtsService
from .kaldi_service import kaldi_service

# Importer le service LLM approprié en fonction de la configuration
if settings.LLM_BACKEND.lower() in ['vllm', 'tgi']:
    logger.info(f"Utilisation du service LLM local avec backend {settings.LLM_BACKEND}")
    from .llm_service_local import LlmService
else:
    logger.info("Utilisation du service LLM distant (API Azure)")
    from .llm_service import LlmService

# Exporter les classes et instances
__all__ = [
    'VadService',
    'AsrService',
    'LlmService',
    'TtsService',
    'kaldi_service'
]