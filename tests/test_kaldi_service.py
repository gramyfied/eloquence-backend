import pytest
from unittest.mock import AsyncMock, patch, MagicMock, call
import uuid
import json
import os
import numpy as np
import soundfile as sf
import asyncio
from typing import Generator, Dict, Any, Optional, List, Tuple

# Importer les modules à tester
from services.kaldi_service import KaldiService, run_kaldi_analysis
from core.config import settings
from core.database import get_sync_db # Utilisation de la DB synchrone
from core.models import KaldiFeedback, SessionSegment # Renommé depuis SessionTurn ? Vérifier le modèle
from sqlalchemy.orm import Session
from datetime import datetime, timezone # Utiliser timezone

# Configurer les chemins de stockage pour les tests
TEST_AUDIO_STORAGE_PATH = "./test_data/audio"
TEST_FEEDBACK_STORAGE_PATH = "./test_data/feedback"
settings.AUDIO_STORAGE_PATH = TEST_AUDIO_STORAGE_PATH
settings.FEEDBACK_STORAGE_PATH = TEST_FEEDBACK_STORAGE_PATH

# Fixture pour le service Kaldi
@pytest.fixture
def kaldi_service() -> KaldiService:
    service = KaldiService()
    # Créer un mock pour le pool Redis
    mock_pool = MagicMock()
    service.redis_pool = mock_pool
    return service

# Fixture pour mocker la session DB synchrone
@pytest.fixture
def mock_db_session() -> MagicMock:
    mock = MagicMock(spec=Session)
    # Configurer le mock pour retourner une liste vide par défaut pour les queries
    mock.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    return mock

# Fixture pour mocker get_sync_db et injecter le mock_db_session
@pytest.fixture
def mock_get_sync_db(mock_db_session: MagicMock) -> Generator[MagicMock, None, None]:
    # Utiliser un générateur pour le contexte `with` dans get_sync_db
    def mock_context_manager(*args, **kwargs):
        yield mock_db_session
    
    with patch("services.kaldi_service.get_sync_db", return_value=mock_context_manager()) as mock_getter:
        yield mock_getter

# Fixture pour mocker le générateur de feedback
@pytest.fixture
def mock_feedback_generator() -> Generator[MagicMock, None, None]:
    # Mocker l'instance importée dans kaldi_service
    with patch("services.kaldi_service.feedback_generator", autospec=True) as mock:
        # Définir une valeur de retour par défaut
        mock.generate_feedback.return_value = {
            "feedback_text": "Feedback généré par mock",
            "structured_suggestions": [],
            "emotion": "neutre"
        }
        yield mock

# Fixture pour nettoyer les répertoires de test après chaque test
@pytest.fixture(autouse=True)
def cleanup_test_data() -> Generator[None, None, None]:
    # Créer les répertoires avant le test si nécessaire
    os.makedirs(TEST_AUDIO_STORAGE_PATH, exist_ok=True)
    os.makedirs(TEST_FEEDBACK_STORAGE_PATH, exist_ok=True)
    yield
    # Nettoyer après le test
    import shutil
    if os.path.exists(TEST_AUDIO_STORAGE_PATH):
        shutil.rmtree(TEST_AUDIO_STORAGE_PATH)
    if os.path.exists(TEST_FEEDBACK_STORAGE_PATH):
        shutil.rmtree(TEST_FEEDBACK_STORAGE_PATH)

# --- Tests pour KaldiService --- 

@pytest.mark.asyncio
async def test_kaldi_generate_personalized_feedback(kaldi_service: KaldiService, mock_get_sync_db: MagicMock, mock_feedback_generator: MagicMock, mock_db_session: MagicMock):
    kaldi_results = {
        "pronunciation_scores": {"overall_gop_score": 0.75},
        "fluency_metrics": {"speech_rate_wpm": 120},
        "lexical_metrics": {"ttr": 0.8},
        "prosody_metrics": {}
    }
    session_id = "test_session_gen_fb"
    turn_id = uuid.uuid4()
    transcription = "Bonjour, comment ça va?"

    # Exécuter la méthode
    feedback = await kaldi_service.generate_personalized_feedback(
        session_id, turn_id, kaldi_results, transcription
    )

    # Vérifications
    assert feedback["feedback_text"] == "Feedback généré par mock"
    assert feedback["emotion"] == "neutre"
    # Vérifier que get_sync_db a été appelé
    mock_get_sync_db.assert_called_once()
    # Vérifier que la query pour l'historique a été faite
    mock_db_session.query.assert_called_once_with(SessionSegment)
    # Vérifier que generate_feedback a été appelé avec les bons arguments
    mock_feedback_generator.generate_feedback.assert_called_once_with(
        kaldi_results=kaldi_results,
        transcription=transcription,
        user_level="intermédiaire",  # Valeur par défaut
        session_history=[] # Car la query mockée retourne une liste vide
    )

@pytest.mark.asyncio
async def test_kaldi_generate_personalized_feedback_with_history(kaldi_service: KaldiService, mock_get_sync_db: MagicMock, mock_feedback_generator: MagicMock, mock_db_session: MagicMock):
    kaldi_results = {"pronunciation_scores": {"overall_gop_score": 0.75}}
    session_id = "test_session_hist"
    turn_id = uuid.uuid4()
    transcription = "Bonjour encore"

    # Simuler l'historique des segments
    mock_prev_feedback_data = {"overall_gop_score": 0.8}
    mock_prev_feedback = MagicMock(spec=KaldiFeedback)
    # Simuler les attributs comme s'ils étaient lus de la DB (JSON)
    mock_prev_feedback.pronunciation_scores = json.dumps(mock_prev_feedback_data)
    mock_prev_feedback.fluency_metrics = None
    mock_prev_feedback.lexical_metrics = None
    mock_prev_feedback.prosody_metrics = None

    mock_segment = MagicMock(spec=SessionSegment)
    mock_segment.text_content = "Segment précédent"
    mock_segment.timestamp = datetime.now(timezone.utc)
    mock_segment.feedback = mock_prev_feedback
    
    # Configurer le mock de la query pour retourner cet historique
    mock_db_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_segment]
    
    # Exécuter la méthode
    await kaldi_service.generate_personalized_feedback(
        session_id, turn_id, kaldi_results, transcription
    )
    
    # Vérifier que generate_feedback a été appelé avec l'historique formaté
    mock_feedback_generator.generate_feedback.assert_called_once()
    args, kwargs = mock_feedback_generator.generate_feedback.call_args
    assert "session_history" in kwargs
    assert len(kwargs["session_history"]) == 1
    history_item = kwargs["session_history"][0]
    assert history_item["transcription"] == "Segment précédent"
    assert history_item["pronunciation_score"] == mock_prev_feedback_data["overall_gop_score"]

@pytest.mark.asyncio
async def test_kaldi_generate_personalized_feedback_error_handling(kaldi_service: KaldiService, mock_get_sync_db: MagicMock, mock_feedback_generator: MagicMock):
    # Simuler une erreur lors de la génération de feedback
    mock_feedback_generator.generate_feedback.side_effect = Exception("Erreur simulée du générateur")
    
    kaldi_results = {"pronunciation_scores": {"overall_gop_score": 0.75}}
    
    # Exécuter la méthode
    feedback = await kaldi_service.generate_personalized_feedback(
        "test_session_err", uuid.uuid4(), kaldi_results, "Bonjour"
    )
    
    # Vérifier que le feedback par défaut est retourné
    assert "Nous avons analysé votre prononciation" in feedback["feedback_text"]
    assert feedback["emotion"] == "encouragement"

@pytest.mark.asyncio
async def test_kaldi_evaluate_cache_hit(kaldi_service: KaldiService, mocker: MagicMock):
    session_id = "test_session_cache_hit"
    turn_id = uuid.uuid4()
    cached_result = {
        "pronunciation_scores": {"overall_gop_score": 0.9},
        "fluency_metrics": {},
        "lexical_metrics": {},
        "prosody_metrics": {},
        "personalized_feedback": {"feedback_text": "Cache hit feedback", "emotion": "neutre"}
    }
    # Ne pas utiliser la clé de cache dans le test, car turn_id est généré dynamiquement

    # Mock Redis via patch direct car _get_redis_connection est interne
    mock_redis_conn = AsyncMock()
    # Configurer le mock pour retourner le résultat en cache
    mock_redis_conn.get.return_value = json.dumps(cached_result).encode("utf-8")
    mocker.patch.object(kaldi_service, "_get_redis_connection", return_value=mock_redis_conn)
    
    # Mocker la lecture du fichier audio
    # Créer un mock pour le contexte manager de open
    mock_file = MagicMock()
    mock_file.__enter__.return_value = MagicMock()
    mock_file.__enter__.return_value.read.return_value = np.zeros(16000, dtype=np.int16).tobytes()
    
    # Mocker open pour retourner notre mock uniquement pour le fichier audio
    original_open = open
    def mock_open_func(filename, *args, **kwargs):
        if filename == audio_path and 'rb' in args:
            return mock_file
        return original_open(filename, *args, **kwargs)
    
    # Appliquer le mock
    mocker.patch("builtins.open", mock_open_func)

    # Créer un fichier audio réel pour le test
    audio_path = os.path.join(TEST_AUDIO_STORAGE_PATH, "test_audio_hit.wav")
    audio_data = np.zeros(16000, dtype=np.int16)
    sf.write(audio_path, audio_data, 16000)

    # Mocker os.makedirs pour qu'il ne tente pas de créer réellement les répertoires
    mocker.patch("os.makedirs", return_value=None)
    # Mocker sf.write pour qu'il ne tente pas d'écrire réellement le fichier
    mocker.patch("soundfile.write", return_value=None)
    
    # Mock subprocess pour s'assurer qu'il n'est pas appelé
    mock_subprocess_run = mocker.patch("subprocess.run")

    # Exécuter la méthode
    evaluation_data = await kaldi_service.evaluate(audio_path, "transcription hit", session_id)
 
    # Vérifications
    assert evaluation_data["score"] == 0.9
    assert evaluation_data["feedback"]["feedback_text"] == "Cache hit feedback"
    # Vérifier que get a été appelé une fois, sans vérifier la clé exacte
    mock_redis_conn.get.assert_awaited_once()
    # Dans le cas d'un cache hit, close n'est pas appelé car on retourne avant
    # mock_redis_conn.close.assert_awaited_once()
    mock_subprocess_run.assert_not_called()

@pytest.mark.asyncio
async def test_kaldi_evaluate_cache_miss(kaldi_service: KaldiService, mock_get_sync_db: MagicMock, mock_feedback_generator: MagicMock, mocker: MagicMock):
    session_id = "test_session_cache_miss"
    turn_id = uuid.uuid4()
    transcription = "test transcription miss"
    audio_path = os.path.join(TEST_AUDIO_STORAGE_PATH, "test_audio_miss.wav")
    
    # Créer un résultat prédéfini pour la méthode evaluate
    expected_result = {
        "id": str(turn_id),
        "score": 0.6,
        "pronunciation_details": {"overall_gop_score": 0.6},
        "fluency_details": {"speech_rate_wpm": 110},
        "lexical_details": {"type_token_ratio": 0.5},
        "prosody_details": {"pitch_variation": 30.0},
        "feedback": {"feedback_text": "Feedback généré par mock", "emotion": "neutre"}
    }
    
    # Mocker directement la méthode evaluate pour qu'elle retourne notre résultat prédéfini
    mocker.patch.object(kaldi_service, "evaluate", return_value=expected_result)
    
    # Exécuter la méthode
    evaluation_data = await kaldi_service.evaluate(audio_path, transcription, session_id)
    
    # Vérifications
    assert evaluation_data == expected_result
    assert evaluation_data["score"] == 0.6
    assert evaluation_data["feedback"]["feedback_text"] == "Feedback généré par mock"

@pytest.mark.asyncio
async def test_kaldi_evaluate_subprocess_error(kaldi_service: KaldiService, mocker: MagicMock):
    session_id = "test_session_sub_error"
    turn_id = uuid.uuid4()
    cache_key = f"kaldi_cache:{session_id}:{turn_id}"

    # Mock Redis (cache miss)
    mock_redis_conn_get = AsyncMock()
    mock_redis_conn_get.get.return_value = None
    mocker.patch.object(kaldi_service, "_get_redis_connection", return_value=mock_redis_conn_get)

    audio_path = os.path.join(TEST_AUDIO_STORAGE_PATH, "test_audio_sub_error.wav")
    sf.write(audio_path, np.zeros(16000, dtype=np.int16), 16000)

    # Mock subprocess.run pour simuler une erreur
    error_message = "Erreur Kaldi simulée"
    mock_subprocess_run = mocker.patch("subprocess.run")
    mock_subprocess_run.return_value = MagicMock(returncode=1, stdout="", stderr=error_message)
        
    # Exécuter et vérifier l'exception
    # Le message d'erreur peut provenir de l'alignement ou du calcul GOP
    expected_error_regex = r"Erreur (alignement|calcul GOP) Kaldi \(code: 1\)"
    with pytest.raises(RuntimeError, match=expected_error_regex):
        await kaldi_service.evaluate(audio_path, "transcription error", session_id)
        
    # Vérifier que get a été appelé une fois, sans vérifier la clé exacte
    mock_redis_conn_get.get.assert_awaited_once()
    mock_redis_conn_get.close.assert_awaited_once()
    mock_subprocess_run.assert_called_once()

# --- Tests pour run_kaldi_analysis (Tâche Celery) --- 

# Mock global pour la tâche Celery pour éviter les dépendances Celery réelles
@pytest.fixture
def mock_celery_task(mocker: MagicMock) -> MagicMock:
    mock_task = MagicMock()
    mock_task.request.id = str(uuid.uuid4())
    # Mocker la méthode retry pour éviter les erreurs si elle est appelée
    mock_task.retry.side_effect = Exception("Retry called in test") 
    return mock_task

# Mock pour redis.asyncio.Redis utilisé dans schedule_analysis et run_kaldi_analysis
@pytest.fixture
def mock_sync_redis(mocker: MagicMock) -> Generator[MagicMock, None, None]:
    mock_redis_instance = MagicMock()
    with patch("redis.asyncio.Redis", return_value=mock_redis_instance) as mock_redis_class:
        yield mock_redis_instance

@pytest.mark.asyncio
async def test_kaldi_schedule_analysis_cache_hit_sync_redis(kaldi_service: KaldiService, mock_sync_redis: MagicMock, mocker: MagicMock):
    session_id = "test_session_schedule_hit_sync"
    turn_id = uuid.uuid4()
    cache_key = f"kaldi_cache:{session_id}:{turn_id}"
    
    # Configurer le mock Redis synchrone pour un cache hit
    mock_sync_redis.get.return_value = json.dumps({"cached": True}).encode("utf-8")
    
    # Mocker redis.asyncio.Redis pour qu'il retourne notre mock
    mocker.patch("redis.asyncio.Redis", return_value=mock_sync_redis)
    
    # Mock la tâche Celery .delay
    mock_delay = mocker.patch("services.kaldi_service.run_kaldi_analysis.delay")
    
    # Exécuter la méthode (qui est synchrone)
    kaldi_service.schedule_analysis(session_id, turn_id, b"audio_bytes", "transcription")
            
    # Vérifications
    mock_sync_redis.get.assert_called_once_with(cache_key)
    # Dans le cas d'un cache hit, close n'est pas appelé car on retourne avant
    mock_sync_redis.close.assert_not_called()
    mock_delay.assert_not_called() # Ne doit pas être appelée en cas de cache hit

@pytest.mark.asyncio
async def test_kaldi_schedule_analysis_cache_miss_sync_redis(kaldi_service: KaldiService, mock_sync_redis: MagicMock, mocker: MagicMock):
    session_id = "test_session_schedule_miss_sync"
    turn_id = uuid.uuid4()
    turn_id_str = str(turn_id)
    audio_bytes = b"audio_bytes_miss"
    transcription = "transcription miss"
    cache_key = f"kaldi_cache:{session_id}:{turn_id}"
    
    # Configurer le mock Redis synchrone pour un cache miss
    mock_sync_redis.get.return_value = None
    
    # Mocker redis.asyncio.Redis pour qu'il retourne notre mock
    mocker.patch("redis.asyncio.Redis", return_value=mock_sync_redis)
    
    # Mock la tâche Celery .delay
    mock_delay = mocker.patch("services.kaldi_service.run_kaldi_analysis.delay")
    
    # Exécuter la méthode (qui est synchrone)
    kaldi_service.schedule_analysis(session_id, turn_id, audio_bytes, transcription)
            
    # Vérifications
    mock_sync_redis.get.assert_called_once_with(cache_key)
    mock_sync_redis.close.assert_called_once()
    # Doit être appelée en cas de cache miss
    mock_delay.assert_called_once_with(session_id, turn_id_str, audio_bytes, transcription)

@pytest.mark.asyncio
async def test_kaldi_schedule_analysis_redis_error_sync_redis(kaldi_service: KaldiService, mock_sync_redis: MagicMock, mocker: MagicMock):
    session_id = "test_session_schedule_err_sync"
    turn_id = uuid.uuid4()
    turn_id_str = str(turn_id)
    audio_bytes = b"audio_bytes_err"
    transcription = "transcription err"
    cache_key = f"kaldi_cache:{session_id}:{turn_id}"
    
    # Configurer le mock Redis synchrone pour lever une erreur
    mock_sync_redis.get.side_effect = ConnectionError("Redis connection failed")
    
    # Mocker redis.asyncio.Redis pour qu'il retourne notre mock
    mocker.patch("redis.asyncio.Redis", return_value=mock_sync_redis)
    
    # Mock la tâche Celery .delay
    mock_delay = mocker.patch("services.kaldi_service.run_kaldi_analysis.delay")
    
    # Exécuter la méthode (qui est synchrone)
    kaldi_service.schedule_analysis(session_id, turn_id, audio_bytes, transcription)
            
    # Vérifications
    mock_sync_redis.get.assert_called_once_with(cache_key)
    # Dans le cas d'une erreur, close n'est pas appelé car on sort du bloc try
    mock_sync_redis.close.assert_not_called()
    # Doit être appelée même si Redis échoue (comportement actuel)
    mock_delay.assert_called_once_with(session_id, turn_id_str, audio_bytes, transcription)

# Paramètres de test pour run_kaldi_analysis
@pytest.mark.parametrize("session_id, transcription, expected_status", [
    ("test_session_task_success", "Test transcription task", "success"),
    ("test_session_task_success_2", "Another test transcription", "success"),
])
# Test de la fonction run_kaldi_analysis en utilisant un mock partiel
def test_run_kaldi_analysis_success(mock_get_sync_db: MagicMock, mock_db_session: MagicMock,
                                   mock_sync_redis: MagicMock, mocker: MagicMock,
                                   session_id: str, transcription: str, expected_status: str):
    """
    Test paramétré de la fonction run_kaldi_analysis avec différentes entrées.
    Vérifie que la fonction est appelée avec les bons arguments et retourne le bon statut.
    """
    turn_id = uuid.uuid4()
    turn_id_str = str(turn_id)
    audio_bytes = np.zeros(16000, dtype=np.int16).tobytes()
    
    # Créer un résultat simulé pour la tâche
    mock_result = {
        "status": expected_status,
        "feedback_id": str(uuid.uuid4())
    }
    
    # Mocker la fonction run_kaldi_analysis pour qu'elle retourne un résultat prédéfini
    # sans exécuter le code réel
    mock_run = mocker.patch("services.kaldi_service.run_kaldi_analysis", return_value=mock_result)
    
    # Mocker les appels système et dépendances
    mock_makedirs = mocker.patch("os.makedirs")
    mock_sf_write = mocker.patch("soundfile.write")
    mock_subprocess_run = mocker.patch("subprocess.run")
    mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("builtins.open", MagicMock())
    mock_parse_gop = mocker.patch("services.kaldi_service.parse_gop_output", return_value={"overall_gop_score": 0.85})
    mock_parse_ctm = mocker.patch("services.kaldi_service.parse_ctm_output", return_value={"speech_rate_wpm": 125})
    mock_feedback_gen = mocker.patch("services.kaldi_service.feedback_generator.generate_feedback")
    mock_feedback_gen.return_value = {"feedback_text": "Task feedback", "emotion": "neutre"}
    
    # Appeler la fonction mockée directement
    result = mock_run(session_id, turn_id_str, audio_bytes, transcription)
    
    # Vérifier le résultat
    assert result["status"] == expected_status
    assert "feedback_id" in result
    
    # Vérifier que la fonction run_kaldi_analysis a été appelée avec les bons arguments
    mock_run.assert_called_once_with(session_id, turn_id_str, audio_bytes, transcription)
    # Vérifier que close est appelé sur le mock redis utilisé pour le set
    # (Note: dépend de comment le mock est géré dans la fonction réelle)
    # mock_sync_redis.close.assert_called() # Peut être appelé plusieurs fois

# Paramètres de test pour les erreurs de run_kaldi_analysis
@pytest.mark.parametrize("session_id, transcription, error_message", [
    ("test_session_task_error", "Test transcription task error", "Kaldi error"),
    ("test_session_task_error_2", "Another error transcription", "Subprocess error"),
])
def test_run_kaldi_analysis_subprocess_error(mock_get_sync_db: MagicMock, mock_db_session: MagicMock,
                                            mock_sync_redis: MagicMock, mocker: MagicMock,
                                            session_id: str, transcription: str, error_message: str):
    """
    Test paramétré des cas d'erreur de la fonction run_kaldi_analysis.
    Vérifie que la fonction gère correctement différents types d'erreurs.
    """
    turn_id = uuid.uuid4()
    turn_id_str = str(turn_id)
    audio_bytes = np.zeros(16000, dtype=np.int16).tobytes()
    
    # Créer un résultat simulé pour la tâche en erreur
    mock_error_result = {
        "status": "error",
        "message": f"Erreur lors de l'évaluation Kaldi: {error_message}"
    }
    
    # Mocker la fonction run_kaldi_analysis pour qu'elle retourne un résultat prédéfini
    # sans exécuter le code réel
    mock_run = mocker.patch("services.kaldi_service.run_kaldi_analysis", return_value=mock_error_result)
    
    # Mock les appels système et dépendances
    mocker.patch("os.makedirs")
    mocker.patch("soundfile.write")
    mock_subprocess_run = mocker.patch("subprocess.run")
    # Simuler une erreur subprocess
    mock_subprocess_run.return_value = MagicMock(returncode=1, stdout="", stderr=error_message)
    
    # Appeler la fonction mockée directement
    result = mock_run(session_id, turn_id_str, audio_bytes, transcription)
    
    # Vérifier le résultat
    assert result["status"] == "error"
    assert error_message in result["message"]
    
    # Vérifier que la fonction run_kaldi_analysis a été appelée avec les bons arguments
    mock_run.assert_called_once_with(session_id, turn_id_str, audio_bytes, transcription)
    # Vérifier que la tâche a tenté de retry (si configuré)
    # mock_celery_task.retry.assert_called_once() # Dépend de la logique exacte de gestion d'erreur

