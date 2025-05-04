"""
Configuration pour les tests pytest.
"""
import os
import sys
import pytest
import pytest_asyncio # <--- Importer pytest_asyncio
import logging
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock # Importer AsyncMock
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Assurez-vous que le chemin vers les modules de l'application est correct
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.models import Base # Importer la base déclarative
from app.main import app # Importer l'application FastAPI
from core import database as database_module # Importer database_module
from core.database import get_db # Importer la dépendance get_db originale
from core.auth import get_current_user_id # Importer la dépendance à surcharger
from services.kaldi_service import KaldiService # Importer KaldiService
from services.asr_service import AsrService # Importer AsrService
from services.llm_service import LlmService # Importer LlmService
from services.tts_service import TtsService # Importer TtsService
from services.vad_service import VadService # Importer VadService
from core.orchestrator import Orchestrator # Importer Orchestrator
from core.config import settings # Importer settings

# Patch le module logging pour éviter d'écrire dans des fichiers pendant les tests
@pytest.fixture(scope="session", autouse=True)
def mock_logging():
    original_file_handler = logging.FileHandler
    
    class MockFileHandler(logging.Handler):
        def __init__(self, filename, mode='a', encoding=None, delay=False):
            super().__init__()
            self.filename = filename
            self.mode = mode
            self.encoding = encoding
            self.delay = delay
            
        def emit(self, record):
            pass  # Ne rien faire
    
    # Remplacer FileHandler par notre mock
    logging.FileHandler = MockFileHandler
    
    yield
    
    # Restaurer le FileHandler original après les tests
    logging.FileHandler = original_file_handler

# Patch os.makedirs pour éviter les erreurs de permission
@pytest.fixture(scope="session", autouse=True)
def mock_makedirs():
    original_makedirs = os.makedirs
    
    def mock_makedirs_func(path, exist_ok=False, *args, **kwargs):
        # Ne rien faire si le chemin contient 'logs'
        # Convertir le chemin en chaîne si c'est un objet Path
        path_str = str(path)
        if 'logs' in path_str:
            return
        return original_makedirs(path, exist_ok=exist_ok, *args, **kwargs)
    
    os.makedirs = mock_makedirs_func
    
    yield
    
    # Restaurer la fonction originale
    os.makedirs = original_makedirs

# --- Nouvelle structure des fixtures DB et Client ---

@pytest_asyncio.fixture(scope="function") # <--- Changer le décorateur
async def async_test_engine():
    """Crée un moteur de DB en mémoire et gère les tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine # Fournit le moteur au test

    # Nettoyage après le test
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.drop_all) # Optionnel pour in-memory
    await engine.dispose()

@pytest_asyncio.fixture(scope="function") # <--- Changer le décorateur
async def async_test_session(async_test_engine):
    """Fournit une session unique pour la configuration du test."""
    AsyncTestingSessionLocal = sessionmaker(
        async_test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with AsyncTestingSessionLocal() as session:
        yield session # Fournit la session au test

# Fixture pour le client de test FastAPI avec la dépendance get_db remplacée
import httpx # Importer httpx

# Fixture pour nettoyer les overrides de dépendances après chaque test
@pytest.fixture(scope="function", autouse=True)
def cleanup_dependency_overrides():
    yield
    # Nettoyer les overrides après chaque test
    app.dependency_overrides.clear()

@pytest_asyncio.fixture(scope="function")
async def client(async_test_engine): # Dépend du moteur
    """Crée le client de test et override les dépendances get_db et get_current_user_id."""
    AsyncTestingSessionLocal = sessionmaker(
        async_test_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    # Fonction de substitution pour get_db
    async def override_get_db():
        async with AsyncTestingSessionLocal() as session:
            yield session

    # Fonction de substitution pour get_current_user_id
    async def override_get_current_user_id():
        return "test-user" # Utiliser la valeur cohérente

    # Appliquer les overrides
    app.dependency_overrides[database_module.get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = override_get_current_user_id # <-- Override get_current_user_id
    
    # Créer et retourner le client httpx
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver"
    ) as c:
        yield c # Yield le client pour le test

    # Nettoyer l'override après le test (géré par cleanup_dependency_overrides)

# Fixture pour mocker l'orchestrateur
@pytest.fixture(scope="function")
def mock_orchestrator(mocker):
    # Mocker l'instance de l'orchestrateur
    mock_instance = mocker.patch('core.orchestrator.orchestrator', new_callable=AsyncMock)
    # Mocker les services dont l'orchestrateur dépend
    mock_instance.asr_service = AsyncMock()
    mock_instance.llm_service = AsyncMock()
    mock_instance.tts_service = AsyncMock()
    mock_instance.vad_service = AsyncMock()
    mock_instance.websocket_manager = AsyncMock()
    mock_instance.db_session_maker = AsyncMock() # Mock du sessionmaker
    mock_instance.db_session_maker.return_value = AsyncMock() # Mock de la session elle-même
    
    # Mock des méthodes spécifiques utilisées dans les tests
    mock_instance.get_or_create_session = AsyncMock()
    mock_instance.generate_text_response = AsyncMock()
    mock_instance.cleanup_session = AsyncMock()
    mock_instance.handle_interruption = MagicMock() # handle_interruption n'est pas async
    mock_instance.process_audio_chunk = MagicMock() # process_audio_chunk n'est pas async
    mock_instance.handle_end_of_speech = MagicMock() # handle_end_of_speech n'est pas async
    mock_instance.connect_client = AsyncMock()
    mock_instance.disconnect_client = AsyncMock()
    mock_instance.process_websocket_message = AsyncMock()

    return mock_instance

# Mock pour simuler une réponse aiohttp
class MockAiohttpResponse:
    def __init__(self, status, json_data=None, text_data=None):
        self.status = status
        self._json_data = json_data
        self._text_data = text_data
        self.headers = {} # Ajouter les headers si nécessaire
        self.request_info = MagicMock() # Ajouter request_info
        self.history = [] # Ajouter history
        self.content = AsyncMock() # Ajouter content pour le streaming

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    def close(self):
        pass # Mock la méthode close

# Mock pour simuler les segments de transcription faster_whisper
class MockSegment:
    def __init__(self, text):
        self.text = text

# Mock pour simuler l'info de transcription faster_whisper
class MockTranscriptionInfo:
    def __init__(self):
        self.language = "fr"
        self.language_probability = 1.0

# Mock pour simuler une session DB asynchrone
class MockAsyncSession(AsyncMock):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._results = {} # Dictionnaire pour stocker les résultats mockés
        self._execution_results = {} # Dictionnaire pour stocker les résultats d'exécution mockés

    def add_get_result(self, model, id, result):
        """Ajoute un résultat mocké pour session.get(model, id)."""
        self._results[(model, id)] = result

    def add_execution_result(self, statement_name, result_list):
        """Ajoute une liste de résultats pour session.execute(select(Model)).scalars().all()."""
        self._execution_results[statement_name] = result_list

    async def get(self, model, id):
        """Simule session.get()."""
        return self._results.get((model, id))

    async def execute(self, statement):
        """Simule session.execute()."""
        # Simplifié: cherche un nom de statement mocké
        # Dans un vrai mock, on analyserait le statement SQLAlchemy
        for name, results in self._execution_results.items():
             # Très basique: cherche si le nom du modèle est dans le statement stringifié
             if name in str(statement):
                 mock_result = MagicMock()
                 mock_result.scalars.return_value.all.return_value = results
                 mock_result.scalar_one_or_none.return_value = results[0] if results else None # Simule scalar_one_or_none
                 return mock_result
        
        # Si aucun résultat mocké n'est trouvé, retourner un mock vide
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one_or_none.return_value = None
        return mock_result

    async def commit(self):
        """Simule session.commit()."""
        pass # Ne rien faire

    async def refresh(self, instance):
        """Simule session.refresh()."""
        pass # Ne rien faire

    async def close(self):
        """Simule session.close()."""
        pass # Ne rien faire

# Fixture pour un mock de session DB asynchrone
@pytest.fixture(scope="function")
def mock_async_db_session(mocker):
    return MockAsyncSession()

# Fixture pour les tests d'API qui nécessitent un mock DB et orchestrator
@pytest.fixture(scope="function")
def mock_api_db(mocker, mock_async_db_session):
    # Mocker get_db pour retourner notre mock de session DB
    # Utiliser iter() car FastAPI attend un générateur pour les dépendances
    get_db_patch = patch("app.routes.session.get_db", return_value=iter([mock_async_db_session]))
    get_db_patch.start()

    # Mocker l'orchestrateur
    orchestrator_patch = patch('app.routes.session.orchestrator', new_callable=AsyncMock)
    orchestrator_instance = orchestrator_patch.start()

    # Mock des méthodes spécifiques de l'orchestrateur utilisées dans les routes API
    orchestrator_instance.get_or_create_session = AsyncMock()
    orchestrator_instance.generate_text_response = AsyncMock()
    orchestrator_instance.cleanup_session = AsyncMock()

    yield {
        "db_session": mock_async_db_session,
        "orchestrator_instance": orchestrator_instance,
        # Ajouter d'autres mocks si nécessaire pour les tests API
        # Utiliser la même valeur que dans les données de test ("test-user")
        "get_current_user_id": mocker.patch("core.auth.get_current_user_id", return_value="test-user") # <-- Valeur corrigée
    }

    # Nettoyer les patchs
    get_db_patch.stop()
    orchestrator_patch.stop()

# Fixture pour les tests WebSocket qui nécessitent un mock DB et orchestrator
@pytest.fixture(scope="function")
def mock_websocket_deps(mocker, mock_async_db_session):
    # Mocker get_db pour retourner notre mock de session DB
    # Note: Pour les WebSockets, la dépendance est souvent gérée différemment,
    # il faut s'assurer que le mock est bien injecté.
    # Ici, on patch directement dans le module de la route websocket.
    get_db_patch = patch("app.routes.websocket.get_db", return_value=mock_async_db_session)
    get_db_patch.start()

    # Mocker l'orchestrator
    orchestrator_patch = patch('app.routes.websocket.orchestrator', new_callable=AsyncMock)
    orchestrator_instance = orchestrator_patch.start()

    # Mock des méthodes spécifiques de l'orchestrator utilisées dans les routes WebSocket
    orchestrator_instance.connect_client = AsyncMock()
    orchestrator_instance.disconnect_client = AsyncMock()
    orchestrator_instance.process_websocket_message = AsyncMock()
    orchestrator_instance.handle_interruption = AsyncMock() # Assurez-vous que c'est async si utilisé dans websocket

    yield {
        "db_session": mock_async_db_session,
        "orchestrator_instance": orchestrator_instance,
        # Ajouter d'autres mocks si nécessaire pour les tests WebSocket
    }

    # Nettoyer les patchs
    get_db_patch.stop()
    orchestrator_patch.stop()

# Fixture pour les tests de service qui nécessitent un mock DB
@pytest.fixture(scope="function")
def mock_service_db(mocker, mock_async_db_session):
     # Mocker get_db pour retourner notre mock de session DB
    get_db_patch = patch("core.database.get_db", return_value=iter([mock_async_db_session]))
    get_db_patch.start()

    # Mocker get_sync_db si utilisé dans les services (pour Celery par exemple)
    # Cela dépend de l'implémentation exacte de get_sync_db
    # Si get_sync_db est juste une version synchrone de get_db, on peut la mocker aussi
    try:
        get_sync_db_patch = patch("core.database.get_sync_db", return_value=iter([MagicMock()])) # Mock synchrone
        get_sync_db_patch.start()
    except AttributeError:
        get_sync_db_patch = None # get_sync_db n'existe pas

    yield {
        "db_session": mock_async_db_session,
        "get_sync_db": get_sync_db_patch.new if get_sync_db_patch else None # Retourne le mock lui-même si patché
    }

    # Nettoyer les patchs
    get_db_patch.stop()
    if get_sync_db_patch:
        get_sync_db_patch.stop()

# Fixture pour les tests de service Kaldi qui nécessitent des mocks spécifiques
@pytest.fixture(scope="function")
def kaldi_service(mocker, mock_service_db):
    # Mock des dépendances de KaldiService
    mock_feedback_generator = mocker.patch('services.kaldi_service.FeedbackGenerator', new_callable=MagicMock)
    mock_feedback_generator_instance = mock_feedback_generator.return_value
    mock_feedback_generator_instance.generate_feedback = AsyncMock() # Assurez-vous que c'est AsyncMock si la méthode est async

    mock_redis_client = mocker.patch('redis.asyncio.Redis', new_callable=AsyncMock)
    mock_redis_client_instance = mock_redis_client.return_value

    # Créer une instance de KaldiService avec les mocks
    service = KaldiService(
        feedback_generator=mock_feedback_generator_instance,
        redis_client=mock_redis_client_instance # Passer l'instance mockée
    )

    # Mock des méthodes internes si nécessaire
    service._get_redis_connection = AsyncMock(return_value=mock_redis_client_instance) # Mock de la méthode interne

    yield service, mock_service_db["get_sync_db"], mock_feedback_generator_instance # Retourner le service et les mocks pertinents

# Fixture pour les tests de service ASR
@pytest.fixture(scope="function")
def asr_service(mocker):
    # Mock du modèle Whisper
    mock_whisper_model = mocker.patch('faster_whisper.WhisperModel.from_pretrained', new_callable=MagicMock).return_value
    mock_whisper_model.transcribe = MagicMock() # La méthode transcribe est synchrone dans faster_whisper

    # Créer une instance de AsrService avec le mock
    service = AsrService()
    service.model = mock_whisper_model # Assigner le mock au modèle

    yield service, mock_whisper_model

# Fixture pour les tests de service LLM (API externe)
@pytest.fixture(scope="function")
def llm_service(mocker):
    # Mock de la session aiohttp
    mock_session = mocker.patch('aiohttp.ClientSession', new_callable=AsyncMock).return_value
    mock_session.post = AsyncMock()

    # Créer une instance de LlmService avec le mock
    service = LlmService()
    service.api_url = "http://mock-llm-api.com" # URL factice

    yield service, mock_session

# Fixture pour les tests de service LLM (locale vLLM/TGI)
@pytest.fixture(scope="function")
def llm_service_local(mocker):
    # Mock de la session aiohttp
    mock_session = mocker.patch('aiohttp.ClientSession', new_callable=AsyncMock).return_value
    mock_session.post = AsyncMock()

    # Créer une instance de LlmService avec le mock
    # On peut tester les deux modes (vLLM et TGI) avec la même fixture en changeant le type
    service_vllm = LlmService(api_type="vllm")
    service_vllm.api_url = "http://mock-url.com" # URL factice
    service_tgi = LlmService(api_type="tgi")
    service_tgi.api_url = "http://mock-url.com" # URL factice


    yield {
        "vllm": (service_vllm, mock_session),
        "tgi": (service_tgi, mock_session)
    }

# Fixture pour les tests de service TTS
@pytest.fixture(scope="function")
def tts_service(mocker):
    # Mock de la session aiohttp
    mock_session = mocker.patch('aiohttp.ClientSession', new_callable=AsyncMock).return_value
    mock_session.post = AsyncMock()

    # Mock Redis connection
    mock_redis_conn = mocker.patch('redis.asyncio.Redis', new_callable=AsyncMock).return_value

    # Créer une instance de TtsService avec les mocks
    service = TtsService()
    service.api_url = "http://mock-tts-api.com" # URL factice
    service.redis_client = mock_redis_conn # Assigner le mock au client Redis

    # Mock des méthodes internes si nécessaire
    service._get_redis_connection = AsyncMock(return_value=mock_redis_conn) # Mock de la méthode interne

    yield service

# Fixture pour les tests de service VAD
@pytest.fixture(scope="function")
def vad_service(mocker):
    # Mock du modèle VAD
    mock_vad_model = mocker.patch('torch.hub.load', return_value=MagicMock()).return_value
    mock_vad_model.reset_state = MagicMock()
    mock_vad_model.forward = MagicMock() # La méthode forward est synchrone

    # Créer une instance de VadService avec le mock
    service = VadService()
    service.model = mock_vad_model # Assigner le mock au modèle

    yield service

# Fixture pour les tests de l'orchestrateur
@pytest.fixture(scope="function")
def orchestrator(mocker, mock_async_db_session):
    # Mock des services dont l'orchestrateur dépend
    mock_asr_service = AsyncMock()
    mock_llm_service = AsyncMock()
    mock_tts_service = AsyncMock()
    mock_vad_service = AsyncMock()
    mock_websocket_manager = AsyncMock()

    # Mock du sessionmaker pour retourner notre mock de session DB
    mock_db_session_maker = MagicMock()
    mock_db_session_maker.return_value = AsyncMock() # Retourne un mock de session asynchrone

    # Créer une instance de l'orchestrateur avec les mocks
    # On ne mocke PAS l'instance globale 'orchestrator' ici, on crée une nouvelle instance pour le test
    from core.orchestrator import Orchestrator # Importer la classe réelle
    instance = Orchestrator(
        asr_service=mock_asr_service,
        llm_service=mock_llm_service,
        tts_service=mock_tts_service,
        vad_service=mock_vad_service,
        websocket_manager=mock_websocket_manager,
        db_session_maker=mock_db_session_maker # Passer le mock du sessionmaker
    )

    # Remplacer l'instance globale par notre instance de test pour ce test
    orchestrator_patch = patch('core.orchestrator.orchestrator', new=instance)
    orchestrator_patch.start()

    yield instance # Retourner l'instance de l'orchestrateur mockée

    # Nettoyer le patch
    orchestrator_patch.stop()
