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
    # Remplacer le pool Redis par un mock pour les tests unitaires
    # Le service lui-même gère la connexion/fermeture dans _get_redis_connection
    service.redis_pool = None # Ou un mock si on veut tester l'interaction avec le pool
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
    mock_prev_feedback.pronunciation_scores = mock_prev_feedback_data
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
    assert history_item["feedback"]["pronunciation_scores"] == mock_prev_feedback_data

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
    cache_key = f"kaldi_eval:{session_id}:{turn_id}"

    # Mock Redis via patch direct car _get_redis_connection est interne
    mock_redis_conn = AsyncMock()
    mock_redis_conn.get.return_value = json.dumps(cached_result).encode("utf-8")
    mocker.patch.object(kaldi_service, "_get_redis_connection", return_value=mock_redis_conn)

    audio_path = os.path.join(TEST_AUDIO_STORAGE_PATH, "test_audio_hit.wav")
    sf.write(audio_path, np.zeros(16000, dtype=np.int16), 16000)

    # Mock subprocess pour s'assurer qu'il n'est pas appelé
    mock_subprocess_run = mocker.patch("subprocess.run")

    # Exécuter la méthode
    evaluation_data = await kaldi_service.evaluate(audio_path, "transcription hit", session_id, turn_id)

    # Vérifications
    assert evaluation_data["score"] == 0.9
    assert evaluation_data["feedback"]["feedback_text"] == "Cache hit feedback"
    mock_redis_conn.get.assert_awaited_once_with(cache_key)
    mock_redis_conn.close.assert_awaited_once() # Vérifier la fermeture
    mock_subprocess_run.assert_not_called()

@pytest.mark.asyncio
async def test_kaldi_evaluate_cache_miss(kaldi_service: KaldiService, mock_get_sync_db: MagicMock, mock_feedback_generator: MagicMock, mocker: MagicMock):
    session_id = "test_session_cache_miss"
    turn_id = uuid.uuid4()
    cache_key = f"kaldi_eval:{session_id}:{turn_id}"
    transcription = "test transcription miss"

    # Mock Redis (miss au GET, succès au SET)
    mock_redis_conn_get = AsyncMock()
    mock_redis_conn_get.get.return_value = None
    mock_redis_conn_set = AsyncMock()
    # Simuler la séquence d'appels à _get_redis_connection
    mocker.patch.object(kaldi_service, "_get_redis_connection", side_effect=[mock_redis_conn_get, mock_redis_conn_set])

    audio_path = os.path.join(TEST_AUDIO_STORAGE_PATH, "test_audio_miss.wav")
    sf.write(audio_path, np.zeros(16000, dtype=np.int16), 16000)

    # Mock subprocess.run pour simuler la sortie Kaldi
    mock_subprocess_run = mocker.patch("subprocess.run")
    mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="Kaldi output", stderr="")
    
    # Mock l'analyse des fichiers de sortie Kaldi (simplifié)
    mock_parse_gop = mocker.patch("services.kaldi_service.parse_gop_output", return_value={"overall_gop_score": 0.6})
    mock_parse_ctm = mocker.patch("services.kaldi_service.parse_ctm_output", return_value={"speech_rate_wpm": 110})
    # Assurer que les répertoires semblent exister pour le parsing
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("builtins.open", MagicMock()) # Mock open pour éviter les erreurs

    # Exécuter la méthode
    evaluation_data = await kaldi_service.evaluate(audio_path, transcription, session_id, turn_id)

    # Vérifications
    mock_redis_conn_get.get.assert_awaited_once_with(cache_key)
    mock_redis_conn_get.close.assert_awaited_once()
    mock_subprocess_run.assert_called_once() # Vérifier que Kaldi a été appelé
    mock_parse_gop.assert_called_once()
    mock_parse_ctm.assert_called_once()
    mock_feedback_generator.generate_feedback.assert_called_once() # Vérifier que le feedback a été généré
    
    assert evaluation_data["score"] == 0.6 # Basé sur le mock de parse_gop
    assert evaluation_data["feedback"]["feedback_text"] == "Feedback généré par mock"
    
    # Vérifier la mise en cache
    mock_redis_conn_set.set.assert_awaited_once()
    args_set, kwargs_set = mock_redis_conn_set.set.call_args
    assert args_set[0] == cache_key
    cached_data = json.loads(args_set[1].decode("utf-8"))
    assert cached_data["pronunciation_scores"]["overall_gop_score"] == 0.6
    assert cached_data["fluency_metrics"]["speech_rate_wpm"] == 110
    assert cached_data["personalized_feedback"]["feedback_text"] == "Feedback généré par mock"
    assert kwargs_set.get("ex") == settings.KALDI_CACHE_TTL
    mock_redis_conn_set.close.assert_awaited_once()

@pytest.mark.asyncio
async def test_kaldi_evaluate_subprocess_error(kaldi_service: KaldiService, mocker: MagicMock):
    session_id = "test_session_sub_error"
    turn_id = uuid.uuid4()
    cache_key = f"kaldi_eval:{session_id}:{turn_id}"

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
    with pytest.raises(RuntimeError, match=f"Erreur lors de l'évaluation Kaldi \(code 1\): {error_message}"):
        await kaldi_service.evaluate(audio_path, "transcription error", session_id, turn_id)
        
    mock_redis_conn_get.get.assert_awaited_once_with(cache_key)
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

# Mock pour redis.Redis synchrone utilisé dans schedule_analysis et run_kaldi_analysis
@pytest.fixture
def mock_sync_redis(mocker: MagicMock) -> Generator[MagicMock, None, None]:
    mock_redis_instance = MagicMock()
    with patch("redis.Redis", return_value=mock_redis_instance) as mock_redis_class:
        yield mock_redis_instance

@pytest.mark.asyncio
async def test_kaldi_schedule_analysis_cache_hit_sync_redis(kaldi_service: KaldiService, mock_sync_redis: MagicMock, mocker: MagicMock):
    session_id = "test_session_schedule_hit_sync"
    turn_id = uuid.uuid4()
    cache_key = f"kaldi_eval:{session_id}:{turn_id}"
    
    # Configurer le mock Redis synchrone pour un cache hit
    mock_sync_redis.get.return_value = json.dumps({"cached": True}).encode("utf-8")
    
    # Mock la tâche Celery .delay
    mock_delay = mocker.patch("services.kaldi_service.run_kaldi_analysis.delay")
    
    # Exécuter la méthode (qui est synchrone)
    kaldi_service.schedule_analysis(session_id, turn_id, b"audio_bytes", "transcription")
            
    # Vérifications
    mock_sync_redis.get.assert_called_once_with(cache_key)
    mock_sync_redis.close.assert_called_once()
    mock_delay.assert_not_called() # Ne doit pas être appelée en cas de cache hit

@pytest.mark.asyncio
async def test_kaldi_schedule_analysis_cache_miss_sync_redis(kaldi_service: KaldiService, mock_sync_redis: MagicMock, mocker: MagicMock):
    session_id = "test_session_schedule_miss_sync"
    turn_id = uuid.uuid4()
    turn_id_str = str(turn_id)
    audio_bytes = b"audio_bytes_miss"
    transcription = "transcription miss"
    cache_key = f"kaldi_eval:{session_id}:{turn_id}"
    
    # Configurer le mock Redis synchrone pour un cache miss
    mock_sync_redis.get.return_value = None
    
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
    cache_key = f"kaldi_eval:{session_id}:{turn_id}"
    
    # Configurer le mock Redis synchrone pour lever une erreur
    mock_sync_redis.get.side_effect = ConnectionError("Redis connection failed")
    
    # Mock la tâche Celery .delay
    mock_delay = mocker.patch("services.kaldi_service.run_kaldi_analysis.delay")
    
    # Exécuter la méthode (qui est synchrone)
    kaldi_service.schedule_analysis(session_id, turn_id, audio_bytes, transcription)
            
    # Vérifications
    mock_sync_redis.get.assert_called_once_with(cache_key)
    mock_sync_redis.close.assert_called_once() # Close doit être appelé même en cas d'erreur
    # Doit être appelée même si Redis échoue (comportement actuel)
    mock_delay.assert_called_once_with(session_id, turn_id_str, audio_bytes, transcription)

# Test direct de la fonction run_kaldi_analysis
def test_run_kaldi_analysis_success(mock_celery_task: MagicMock, mock_get_sync_db: MagicMock, mock_db_session: MagicMock, mock_sync_redis: MagicMock, mocker: MagicMock):
    session_id = "test_session_task_success"
    turn_id = uuid.uuid4()
    turn_id_str = str(turn_id)
    audio_bytes = np.zeros(16000, dtype=np.int16).tobytes()
    transcription = "Test transcription task"
    cache_key = f"kaldi_eval:{session_id}:{turn_id}"
    
    # Mock les appels système et dépendances
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
    
    # Exécuter la tâche (fonction synchrone)
    result = run_kaldi_analysis(mock_celery_task, session_id, turn_id_str, audio_bytes, transcription)
    
    # Vérifier le résultat
    assert result["status"] == "success"
    assert "feedback_id" in result
    feedback_id = result["feedback_id"]
    
    # Vérifier les appels mocks
    mock_makedirs.assert_called()
    mock_sf_write.assert_called_once()
    mock_subprocess_run.assert_called_once()
    mock_parse_gop.assert_called_once()
    mock_parse_ctm.assert_called_once()
    mock_feedback_gen.assert_called_once()
    
    # Vérifier l'interaction avec la DB
    mock_get_sync_db.assert_called_once()
    mock_db_session.add.assert_called_once()
    added_object = mock_db_session.add.call_args[0][0]
    assert isinstance(added_object, KaldiFeedback)
    assert added_object.id == feedback_id
    assert added_object.turn_id == turn_id
    assert added_object.pronunciation_scores["overall_gop_score"] == 0.85
    assert added_object.fluency_metrics["speech_rate_wpm"] == 125
    mock_db_session.commit.assert_called_once()
    mock_db_session.close.assert_called_once()
    
    # Vérifier l'interaction avec Redis (mise en cache)
    mock_sync_redis.set.assert_called_once()
    args_set, kwargs_set = mock_sync_redis.set.call_args
    assert args_set[0] == cache_key
    cached_data = json.loads(args_set[1].decode("utf-8"))
    assert cached_data["pronunciation_scores"]["overall_gop_score"] == 0.85
    assert cached_data["personalized_feedback"]["feedback_text"] == "Task feedback"
    assert kwargs_set.get("ex") == settings.KALDI_CACHE_TTL
    # Vérifier que close est appelé sur le mock redis utilisé pour le set
    # (Note: dépend de comment le mock est géré dans la fonction réelle)
    # mock_sync_redis.close.assert_called() # Peut être appelé plusieurs fois

def test_run_kaldi_analysis_subprocess_error(mock_celery_task: MagicMock, mock_get_sync_db: MagicMock, mock_db_session: MagicMock, mock_sync_redis: MagicMock, mocker: MagicMock):
    session_id = "test_session_task_error"
    turn_id = uuid.uuid4()
    turn_id_str = str(turn_id)
    audio_bytes = np.zeros(16000, dtype=np.int16).tobytes()
    transcription = "Test transcription task error"
    
    # Mock les appels système et dépendances
    mocker.patch("os.makedirs")
    mocker.patch("soundfile.write")
    mock_subprocess_run = mocker.patch("subprocess.run")
    # Simuler une erreur subprocess
    mock_subprocess_run.return_value = MagicMock(returncode=1, stdout="", stderr="Kaldi error")
    
    # Exécuter la tâche
    # Utiliser try/except car la fonction peut lever l'erreur avant de la catcher pour retry
    try:
        result = run_kaldi_analysis(mock_celery_task, session_id, turn_id_str, audio_bytes, transcription)
        # Si la fonction ne lève pas d'erreur et retourne, vérifier le retour
        assert result["status"] == "error"
        assert "Erreur lors de l'évaluation Kaldi" in result["message"]
    except Exception as e:
        # Si la fonction lève l'erreur (avant le retry mocké), c'est aussi un échec
        assert isinstance(e, RuntimeError)
        assert "Erreur lors de l'évaluation Kaldi" in str(e)

    # Vérifier les appels
    mock_subprocess_run.assert_called_once()
    # Vérifier que la DB n'a pas été modifiée
    mock_db_session.add.assert_not_called()
    mock_db_session.commit.assert_not_called()
    # Vérifier que Redis n'a pas été utilisé pour le set
    mock_sync_redis.set.assert_not_called()
    # Vérifier que la tâche a tenté de retry (si configuré)
    # mock_celery_task.retry.assert_called_once() # Dépend de la logique exacte de gestion d'erreur

