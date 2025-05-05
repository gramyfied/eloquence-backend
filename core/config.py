import os
from dotenv import load_dotenv
import yaml
from pydantic_settings import BaseSettings
from typing import Optional, List, ClassVar

# Charger les variables d'environnement depuis .env s'il existe
load_dotenv()

class Settings(BaseSettings):
    # Paramètres de l'application
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "info"
    LOG_DIR: str = "./logs"
    SECRET_KEY: str = "eloquence_secret_key_change_in_production"
    
    # CORS
    CORS_ORIGINS: List[str] = ["*"]  # En production, spécifier les origines autorisées
    
    # Base de données Supabase (chargée manuellement en raison de problèmes avec pydantic-settings)
    SUPABASE_PROJECT_REF: ClassVar[Optional[str]] = os.getenv("SUPABASE_PROJECT_REF")
    SUPABASE_DB_PASSWORD: ClassVar[Optional[str]] = os.getenv("SUPABASE_DB_PASSWORD")
    SUPABASE_REGION: ClassVar[str] = os.getenv("SUPABASE_REGION", "eu-west-3") # Région par défaut

    if not SUPABASE_PROJECT_REF or not SUPABASE_DB_PASSWORD:
        raise ValueError("SUPABASE_PROJECT_REF and SUPABASE_DB_PASSWORD must be set in .env or environment variables")

    DATABASE_URL: str = f"postgresql+asyncpg://postgres.{SUPABASE_PROJECT_REF}:{SUPABASE_DB_PASSWORD}@aws-0-{SUPABASE_REGION}.pooler.supabase.com:6543/postgres"
    
    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: str = "redis://localhost:6379/0"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # URLs des services
    ASR_API_URL: str = "http://localhost:8001/asr"
    LLM_API_URL: str = "http://localhost:8002/generate"
    TTS_API_URL: str = "http://localhost:8003/tts"
    
    # Kaldi
    KALDI_DOCKER_IMAGE: str = "kaldiasr/kaldi:latest"
    KALDI_CONTAINER_NAME: str = "kaldi_container"
    KALDI_RECIPE_DIR: str = "/kaldi/egs/librispeech" # Chemin vers la recette Kaldi dans le conteneur
    KALDI_LANG_DIR: str = "data/lang" # Chemin relatif au répertoire de recette
    KALDI_MODEL_DIR: str = "exp/chain/tdnn_1d_sp" # Chemin relatif au répertoire de recette
    KALDI_ALIGN_SCRIPT: str = "steps/nnet3/align.sh" # Chemin relatif au répertoire de recette
    KALDI_GOP_SCRIPT: str = "steps/compute_gop.sh" # Chemin relatif au répertoire de recette

    # VAD
    VAD_THRESHOLD: float = 0.40 # Seuil abaissé pour une meilleure détection de la parole
    VAD_MIN_SILENCE_DURATION_MS: int = 1800 # Seuil pour fin de tour (ASR) - légèrement réduit pour plus de réactivité
    VAD_GENTLE_PROMPT_SILENCE_MS: int = 1200 # Seuil pour relance douce (LLM) - légèrement réduit
    VAD_WAIT_SILENCE_MS: int = 600 # Seuil pour attente silencieuse - légèrement réduit
    VAD_SPEECH_PAD_MS: int = 400 # Padding ajouté avant/après la détection de parole
    VAD_CONSECUTIVE_SPEECH_FRAMES: int = 2 # Nombre de frames consécutives nécessaires pour confirmer la parole
    VAD_CONSECUTIVE_SILENCE_FRAMES: int = 3 # Nombre de frames consécutives nécessaires pour confirmer le silence

    # Chemins de stockage
    AUDIO_STORAGE_PATH: str = "./data/audio"
    FEEDBACK_STORAGE_PATH: str = "./data/feedback"
    MODEL_STORAGE_PATH: str = "./data/models"

    # ASR (Faster Whisper)
    ASR_MODEL_NAME: str = "large-v2" # Ou "medium", "small", "base", "tiny"
    ASR_DEVICE: str = "cpu" # "cuda" ou "cpu"
    ASR_COMPUTE_TYPE: str = "int8" # "int8", "float16", "float32"
    ASR_BEAM_SIZE: int = 5
    ASR_LANGUAGE: str = "fr"

    # LLM (Mistral en local via vLLM ou TGI)
    LLM_BACKEND: str = "vllm"  # "vllm" ou "tgi"
    LLM_LOCAL_API_URL: str = "http://localhost:8000"  # URL du serveur vLLM ou TGI
    LLM_API_URL: str = "https://ai-ousmanesissoko-8429.services.ai.azure.com/models/chat/completions?api-version=2024-05-01-preview"  # Fallback Azure
    SCW_LLM_API_KEY: str # Clé API Scaleway pour le LLM
    LLM_MODEL_NAME: str = "mistral-nemo-instruct-2407" # Modèle Scaleway par défaut
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 150 # Max tokens par défaut (peut être surchargé par LLM_MAX_MAX_TOKENS)
    LLM_MAX_MAX_TOKENS: int = 512 # Max tokens pour Scaleway (selon l'exemple utilisateur)
    LLM_TIMEOUT_S: int = 30  # Timeout en secondes

    # TTS (Coqui TTS API)
    TTS_API_URL: str = "http://localhost:5002/api/tts"
    TTS_USE_CACHE: bool = True
    TTS_CACHE_PREFIX: str = "tts_cache:"
    TTS_CACHE_EXPIRATION_S: int = 3600 * 24 # Cache pour 24h par défaut
    TTS_PRELOAD_COMMON_PHRASES: bool = True  # Précharger les phrases courantes au démarrage
    TTS_IMMEDIATE_STOP: bool = True  # Pour les interruptions

    # TTS Specific Voices/Emotions - à adapter selon la méthode (VITS/XTTS)
    # Exemple VITS (speaker_id par émotion)
    # IDs de speakers pour les différentes émotions
    # Ces IDs correspondent aux voix disponibles dans le modèle Coqui TTS
    # Pour VITS fine-tuné : utiliser les IDs spécifiques au modèle
    # Pour XTTS v2 : ces IDs peuvent être des chemins vers des fichiers audio de référence
    TTS_SPEAKER_ID_NEUTRAL: Optional[str] = "p225"  # Voix neutre
    TTS_SPEAKER_ID_ENCOURAGEMENT: Optional[str] = "p226"  # Voix encourageante
    TTS_SPEAKER_ID_EMPATHY: Optional[str] = "p227"  # Voix empathique
    TTS_SPEAKER_ID_ENTHUSIASM: Optional[str] = "p228"  # Voix enthousiaste
    TTS_SPEAKER_ID_CURIOSITY: Optional[str] = "p229"  # Voix curieuse
    TTS_SPEAKER_ID_REFLECTION: Optional[str] = "p230"  # Voix réfléchie

    TTS_XTTS_MODEL_PATH: Optional[str] = None
    TTS_XTTS_CONFIG_PATH: Optional[str] = None
    TTS_XTTS_SPEAKER_WAV_ENCOURAGEMENT: Optional[str] = None
    # ... autres chemins wav pour XTTS
    
    # Paramètres de session
    SESSION_TIMEOUT_S: int = 3600  # 1 heure
    
    # Paramètres de monitoring
    ENABLE_METRICS: bool = True
    METRICS_ENDPOINT: str = "/api/metrics"

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        extra = 'ignore' # Ignorer les variables d'env non définies dans le modèle

settings = Settings()

# Optionnel: Charger des configurations supplémentaires depuis YAML
try:
    config_path = os.environ.get("CONFIG_PATH", "config/settings.yaml")
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            yaml_config = yaml.safe_load(f)
            # Fusionner yaml_config avec settings
            for key, value in yaml_config.items():
                if hasattr(settings, key):
                    setattr(settings, key, value)
except Exception as e:
    print(f"Erreur lors du chargement de la configuration YAML: {e}")

# Créer les répertoires de stockage s'ils n'existent pas
os.makedirs(settings.AUDIO_STORAGE_PATH, exist_ok=True)
os.makedirs(settings.FEEDBACK_STORAGE_PATH, exist_ok=True)
os.makedirs(settings.MODEL_STORAGE_PATH, exist_ok=True)
os.makedirs(settings.LOG_DIR, exist_ok=True)
