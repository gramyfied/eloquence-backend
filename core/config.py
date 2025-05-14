import os
from dotenv import load_dotenv
import yaml
from pydantic_settings import BaseSettings
from typing import Optional, List, ClassVar
from pydantic import Field

# Charger les variables d'environnement depuis .env s'il existe
load_dotenv()

class Settings(BaseSettings):
    # Paramètres de l'application
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8083
    LOG_LEVEL: str = "info"
    LOG_DIR: str = "/home/ubuntu/eloquence_logs" # Modifié pour utiliser un chemin absolu
    SECRET_KEY: str = "eloquence_secret_key_change_in_production"
    
    # CORS
    CORS_ORIGINS: List[str] = ["*"]
    
    IS_TESTING: bool = "PYTEST_CURRENT_TEST" in os.environ or os.environ.get("TESTING") == "True"
    
    SUPABASE_PROJECT_REF: ClassVar[Optional[str]] = os.getenv("SUPABASE_PROJECT_REF")
    SUPABASE_DB_PASSWORD: ClassVar[Optional[str]] = os.getenv("SUPABASE_DB_PASSWORD")
    SUPABASE_REGION: ClassVar[str] = os.getenv("SUPABASE_REGION", "eu-west-3")

    if IS_TESTING:
        DATABASE_URL: str = "sqlite+aiosqlite:///:memory:"
    else:
        if not SUPABASE_PROJECT_REF or not SUPABASE_DB_PASSWORD:
            raise ValueError("SUPABASE_PROJECT_REF and SUPABASE_DB_PASSWORD must be set in .env or environment variables")
        
        DATABASE_URL: str = (
            f"postgresql+asyncpg://postgres.{SUPABASE_PROJECT_REF}:{SUPABASE_DB_PASSWORD}@"
            f"aws-0-{SUPABASE_REGION}.pooler.supabase.com:6543/postgres"
            f"?prepared_statement_cache_size=0"
            f"&statement_cache_size=0"
            f"&pool_pre_ping=true"
            f"&pool_recycle=300"
            f"&pool_timeout=30"
            f"&pool_size=5"
            f"&max_overflow=10"
        )
    
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: str = "redis://localhost:6379/0"

    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    ASR_API_URL: str = "http://localhost:8001/asr"
    LLM_API_URL: str = "http://localhost:8002/generate"
    TTS_API_URL: str = "http://localhost:5002/api/tts"
    
    KALDI_DOCKER_IMAGE: str = "kaldiasr/kaldi:latest"
    KALDI_CONTAINER_NAME: str = "kaldi_container"
    KALDI_RECIPE_DIR: str = "/kaldi/egs/librispeech"
    KALDI_LANG_DIR: str = "data/lang"
    KALDI_MODEL_DIR: str = "exp/chain/tdnn_1d_sp"
    KALDI_ALIGN_SCRIPT: str = "steps/nnet3/align.sh"
    KALDI_GOP_SCRIPT: str = "steps/compute_gop.sh"

    VAD_THRESHOLD: float = 0.40
    VAD_MIN_SILENCE_DURATION_MS: int = 1800
    VAD_GENTLE_PROMPT_SILENCE_MS: int = 1200
    VAD_WAIT_SILENCE_MS: int = 600
    VAD_SPEECH_PAD_MS: int = 400
    VAD_CONSECUTIVE_SPEECH_FRAMES: int = 2
    VAD_CONSECUTIVE_SILENCE_FRAMES: int = 3
    VAD_WINDOW_SIZE_SAMPLES: int = 512

    AUDIO_STORAGE_PATH: str = "/home/ubuntu/eloquence_data/audio" # Modifié pour utiliser un chemin absolu
    FEEDBACK_STORAGE_PATH: str = "/home/ubuntu/eloquence_data/feedback" # Modifié pour utiliser un chemin absolu
    MODEL_STORAGE_PATH: str = "/home/ubuntu/eloquence_data/models" # Modifié pour utiliser un chemin absolu

    ASR_MODEL_NAME: str = "large-v2"
    ASR_DEVICE: str = "cpu"
    ASR_COMPUTE_TYPE: str = "int8"
    ASR_BEAM_SIZE: int = 5
    ASR_LANGUAGE: str = "fr"

    LLM_BACKEND: str = "vllm"
    LLM_LOCAL_API_URL: str = "http://localhost:8000"
    LLM_API_URL: str = "https://ai-ousmanesissoko-8429.services.ai.azure.com/models/chat/completions?api-version=2024-05-01-preview"
    SCW_LLM_API_KEY: Optional[str] = Field(None, description="Clé API Scaleway pour le LLM")
    LLM_MODEL_NAME: str = "mistral-nemo-instruct-2407"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 150
    LLM_MAX_MAX_TOKENS: int = 512
    LLM_TIMEOUT_S: int = 10

    TTS_USE_CACHE: bool = True
    TTS_CACHE_PREFIX: str = "tts_cache:"
    TTS_CACHE_EXPIRATION_S: int = 3600 * 24
    TTS_PRELOAD_COMMON_PHRASES: bool = True
    TTS_IMMEDIATE_STOP: bool = True
    
    TTS_MODEL_NAME: str = "tts_models/fr/mai/tacotron2-DDC"
    TTS_DEVICE: str = "cpu"

    TTS_SPEAKER_ID_NEUTRAL: Optional[str] = "p225"
    TTS_SPEAKER_ID_ENCOURAGEMENT: Optional[str] = "p226"
    TTS_SPEAKER_ID_EMPATHY: Optional[str] = "p227"
    TTS_SPEAKER_ID_ENTHUSIASM: Optional[str] = "p228"
    TTS_SPEAKER_ID_CURIOSITY: Optional[str] = "p229"
    TTS_SPEAKER_ID_REFLECTION: Optional[str] = "p230"

    TTS_XTTS_MODEL_PATH: Optional[str] = None
    TTS_XTTS_CONFIG_PATH: Optional[str] = None
    TTS_XTTS_SPEAKER_WAV_ENCOURAGEMENT: Optional[str] = None
    
    SESSION_TIMEOUT_S: int = 3600
    
    ENABLE_METRICS: bool = True
    METRICS_ENDPOINT: str = "/api/metrics"

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        extra = 'ignore'

settings = Settings()

try:
    config_path = os.environ.get("CONFIG_PATH", "config/settings.yaml")
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            yaml_config = yaml.safe_load(f)
            for key, value in yaml_config.items():
                if hasattr(settings, key):
                    setattr(settings, key, value)
except Exception as e:
    print(f"Erreur lors du chargement de la configuration YAML: {e}")

os.makedirs(settings.AUDIO_STORAGE_PATH, exist_ok=True)
os.makedirs(settings.FEEDBACK_STORAGE_PATH, exist_ok=True)
os.makedirs(settings.MODEL_STORAGE_PATH, exist_ok=True)
os.makedirs(settings.LOG_DIR, exist_ok=True)
