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
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    HOST: str = os.getenv("API_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("API_PORT", "8000"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")
    LOG_DIR: str = os.getenv("LOG_DIR", "./logs")  # Chemin relatif pour Docker
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
        if SUPABASE_PROJECT_REF and SUPABASE_DB_PASSWORD:
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
        else:
            # Fallback to local Docker PostgreSQL
            POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
            POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "changethis")
            POSTGRES_DB: str = os.getenv("POSTGRES_DB", "eloquence")
            DB_HOST: str = os.getenv("DB_HOST", "db") # 'db' is the service name in docker-compose
            DB_PORT: str = os.getenv("DB_PORT", "5432")
            DATABASE_URL: str = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{DB_HOST}:{DB_PORT}/{POSTGRES_DB}"
    
    # Redis configuration - utiliser les variables d'environnement
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")  # Nom du service dans docker-compose
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_URL: str = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

    # Celery configuration - utiliser les variables d'environnement
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/1")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", f"redis://{REDIS_HOST}:{REDIS_PORT}/2")

    # Service URLs - utiliser les variables d'environnement
    ASR_API_URL: str = os.getenv("ASR_API_URL", "http://asr-service:8000/transcribe")
    LLM_API_URL: str = os.getenv("LLM_API_URL", "https://api.scaleway.ai/18f6cc9d-07fc-49c3-a142-67be9b59ac63/v1/chat/completions")
    TTS_API_URL: str = os.getenv("TTS_API_URL", "http://tts-service:5002/api/tts")
    
    # Kaldi configuration - utiliser les variables d'environnement
    KALDI_DOCKER_IMAGE: str = os.getenv("KALDI_DOCKER_IMAGE", "kaldiasr/kaldi:latest")
    KALDI_CONTAINER_NAME: str = os.getenv("KALDI_CONTAINER_NAME", "kaldi_eloquence")  # Nom dans docker-compose
    KALDI_RECIPE_DIR: str = os.getenv("KALDI_RECIPE_DIR", "/kaldi/egs/librispeech")
    KALDI_LANG_DIR: str = os.getenv("KALDI_LANG_DIR", "data/lang")
    KALDI_MODEL_DIR: str = os.getenv("KALDI_MODEL_DIR", "exp/chain/tdnn_1d_sp")
    KALDI_ALIGN_SCRIPT: str = os.getenv("KALDI_ALIGN_SCRIPT", "steps/nnet3/align.sh")
    KALDI_GOP_SCRIPT: str = os.getenv("KALDI_GOP_SCRIPT", "steps/compute_gop.sh")

    # VAD configuration
    VAD_THRESHOLD: float = float(os.getenv("VAD_THRESHOLD", "0.40"))
    VAD_MIN_SILENCE_DURATION_MS: int = int(os.getenv("VAD_MIN_SILENCE_DURATION_MS", "1800"))
    VAD_GENTLE_PROMPT_SILENCE_MS: int = int(os.getenv("VAD_GENTLE_PROMPT_SILENCE_MS", "1200"))
    VAD_WAIT_SILENCE_MS: int = int(os.getenv("VAD_WAIT_SILENCE_MS", "600"))
    VAD_SPEECH_PAD_MS: int = int(os.getenv("VAD_SPEECH_PAD_MS", "400"))
    VAD_CONSECUTIVE_SPEECH_FRAMES: int = 2
    VAD_CONSECUTIVE_SILENCE_FRAMES: int = 3
    VAD_WINDOW_SIZE_SAMPLES: int = 512

    # Storage paths - utiliser des chemins relatifs pour Docker
    AUDIO_STORAGE_PATH: str = os.getenv("AUDIO_STORAGE_PATH", "./data/audio")
    FEEDBACK_STORAGE_PATH: str = os.getenv("FEEDBACK_STORAGE_PATH", "./data/feedback")
    MODEL_STORAGE_PATH: str = os.getenv("MODEL_STORAGE_PATH", "./data/models")

    # ASR configuration
    ASR_MODEL_NAME: str = os.getenv("ASR_MODEL_NAME", "large-v2")
    ASR_DEVICE: str = os.getenv("ASR_DEVICE", "cpu")
    ASR_COMPUTE_TYPE: str = os.getenv("ASR_COMPUTE_TYPE", "int8")
    ASR_BEAM_SIZE: int = int(os.getenv("ASR_BEAM_SIZE", "5"))
    ASR_LANGUAGE: str = os.getenv("ASR_LANGUAGE", "fr")

    # LLM Configuration
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "scaleway")
    
    # Azure OpenAI/Compatible Settings
    AZURE_LLM_API_KEY: Optional[str] = os.getenv("AZURE_LLM_API_KEY")

    # Scaleway Mistral Settings
    SCW_LLM_API_URL: Optional[str] = os.getenv("SCW_LLM_API_URL", "https://api.scaleway.ai/18f6cc9d-07fc-49c3-a142-67be9b59ac63/v1/chat/completions")
    SCW_LLM_API_KEY: Optional[str] = os.getenv("SCW_LLM_API_KEY")
    
    # Common LLM Settings
    LLM_API_KEY: Optional[str] = os.getenv("LLM_API_KEY", os.getenv("SCW_LLM_API_KEY"))
    LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "mistral-nemo-instruct-2407")
    LLM_BACKEND: str = os.getenv("LLM_BACKEND", "vllm")
    LLM_LOCAL_API_URL: str = os.getenv("LLM_LOCAL_API_URL", "http://llm-service:8000")  # Nom du service dans docker-compose
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "150"))
    LLM_MAX_MAX_TOKENS: int = int(os.getenv("LLM_MAX_MAX_TOKENS", "512"))
    LLM_TIMEOUT_S: int = int(os.getenv("LLM_TIMEOUT_S", "30"))

    # TTS configuration
    TTS_USE_CACHE: bool = os.getenv("TTS_USE_CACHE", "True").lower() == "true"
    TTS_CACHE_PREFIX: str = os.getenv("TTS_CACHE_PREFIX", "tts_cache:")
    TTS_CACHE_DIR: str = os.getenv("TTS_CACHE_DIR", "./data/tts_cache")  # Chemin relatif pour Docker
    TTS_CACHE_EXPIRATION_S: int = int(os.getenv("TTS_CACHE_EXPIRATION_S", str(3600 * 24)))
    TTS_PRELOAD_COMMON_PHRASES: bool = os.getenv("TTS_PRELOAD_COMMON_PHRASES", "True").lower() == "true"
    TTS_IMMEDIATE_STOP: bool = os.getenv("TTS_IMMEDIATE_STOP", "True").lower() == "true"
    
    TTS_MODEL_NAME: str = os.getenv("TTS_MODEL_NAME", "tts_models/multilingual/multi-dataset/bark")
    TTS_DEVICE: str = os.getenv("TTS_DEVICE", "cpu")

    TTS_SPEAKER_ID_NEUTRAL: Optional[str] = os.getenv("TTS_SPEAKER_ID_NEUTRAL", "p225")
    TTS_SPEAKER_ID_ENCOURAGEMENT: Optional[str] = os.getenv("TTS_SPEAKER_ID_ENCOURAGEMENT", "p226")
    TTS_SPEAKER_ID_EMPATHY: Optional[str] = os.getenv("TTS_SPEAKER_ID_EMPATHY", "p227")
    TTS_SPEAKER_ID_ENTHUSIASM: Optional[str] = os.getenv("TTS_SPEAKER_ID_ENTHUSIASM", "p228")
    TTS_SPEAKER_ID_CURIOSITY: Optional[str] = os.getenv("TTS_SPEAKER_ID_CURIOSITY", "p229")
    TTS_SPEAKER_ID_REFLECTION: Optional[str] = os.getenv("TTS_SPEAKER_ID_REFLECTION", "p230")

    TTS_XTTS_MODEL_PATH: Optional[str] = os.getenv("TTS_XTTS_MODEL_PATH")
    TTS_XTTS_CONFIG_PATH: Optional[str] = os.getenv("TTS_XTTS_CONFIG_PATH")
    TTS_XTTS_SPEAKER_WAV_ENCOURAGEMENT: Optional[str] = os.getenv("TTS_XTTS_SPEAKER_WAV_ENCOURAGEMENT")
    
    SESSION_TIMEOUT_S: int = int(os.getenv("SESSION_TIMEOUT_S", "3600"))
    
    ENABLE_METRICS: bool = os.getenv("ENABLE_METRICS", "True").lower() == "true"
    METRICS_ENDPOINT: str = os.getenv("METRICS_ENDPOINT", "/api/metrics")

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

# Créer les répertoires nécessaires
os.makedirs(settings.AUDIO_STORAGE_PATH, exist_ok=True)
os.makedirs(settings.FEEDBACK_STORAGE_PATH, exist_ok=True)
os.makedirs(settings.MODEL_STORAGE_PATH, exist_ok=True)
os.makedirs(settings.LOG_DIR, exist_ok=True)
os.makedirs(settings.TTS_CACHE_DIR, exist_ok=True)