import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock, call
import uuid
import json
import aiohttp
from typing import Optional, Dict, Any, AsyncGenerator, Generator
import redis.asyncio as redis # Pour le cache optionnel

# Importer la classe à tester et les dépendances
from services.tts_service import TtsService
from core.config import settings

# --- Fixtures --- 

# Mock pour la connexion Redis
@pytest_asyncio.fixture
async def mock_redis_conn() -> AsyncMock:
    conn = AsyncMock(spec=redis.Redis)
    conn.get = AsyncMock(return_value=None) # Cache miss par défaut
    conn.set = AsyncMock(return_value=True)
    conn.close = MagicMock() # close n'est pas async
    conn.ping = AsyncMock(return_value=True)
    return conn

# Fixture pour le service TTS avec dépendances mockées
@pytest_asyncio.fixture
async def tts_service(mocker: MagicMock, mock_redis_conn: AsyncMock) -> Generator[TtsService, None, None]:
    # Mocker les settings TTS si nécessaire pour les tests
    mocker.patch("core.config.settings.TTS_API_URL", "http://test-tts-api.com/api/tts")
    mocker.patch("core.config.settings.TTS_SPEAKER_ID_NEUTRAL", "speaker_default")
    mocker.patch("core.config.settings.TTS_SPEAKER_ID_ENCOURAGEMENT", "speaker_encourage")
    mocker.patch("core.config.settings.TTS_CACHE_ENABLED", True) # Activer le cache pour les tests
    
    # Patcher _get_redis_connection pour retourner notre mock
    # Note: Si TtsService utilise un pool, il faudrait mocker le pool
    mocker.patch.object(TtsService, "_get_redis_connection", return_value=mock_redis_conn)
    
    service = TtsService()
    # Assurer que la map emotion->speaker est initialisée avec les settings mockés
    service._initialize_emotion_map()
    # Nettoyer les générations actives pour l'isolation
    service.active_generations.clear()
    yield service
    # Cleanup si nécessaire

# Mock amélioré pour simuler la réponse aiohttp avec streaming
class MockAiohttpStreamResponse:
    def __init__(self, status: int, chunks: list[bytes], headers: Optional[Dict[str, str]] = None):
        self.status = status
        self.headers = headers or {"Content-Type": "audio/mpeg"}
        self.content = AsyncMock(spec=aiohttp.StreamReader)
        # Configurer iter_any pour retourner les chunks fournis
        async def chunk_generator() -> AsyncGenerator[bytes, None]:
            for chunk in chunks:
                yield chunk
        self.content.iter_any.return_value = chunk_generator()
        # Simuler le context manager
        self._session = None # Pour raise_for_status

    async def __aenter__(self) -> "MockAiohttpStreamResponse":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        pass
        
    def raise_for_status(self) -> None:
        if self.status >= 400:
            request_info = MagicMock(spec=aiohttp.RequestInfo)
            request_info.url = "mock_url"
            request_info.method = "POST"
            request_info.headers = {}
            raise aiohttp.ClientResponseError(request_info, (), status=self.status)

# --- Tests --- 

@pytest.mark.asyncio
async def test_tts_get_speaker_id(tts_service: TtsService):
    # Les settings sont mockés dans la fixture tts_service
    assert tts_service._get_speaker_id("encouragement") == "speaker_encourage"
    assert tts_service._get_speaker_id("emotion_inconnue") == "speaker_default"
    assert tts_service._get_speaker_id(None) == "speaker_default"

@pytest.mark.asyncio
async def test_tts_stop_generation_success(tts_service: TtsService, mocker: MagicMock):
    session_id = "test_session_stop_success"
    # Simuler une tâche active
    mock_task = asyncio.create_task(asyncio.sleep(0.1)) # Utiliser une vraie tâche
    tts_service.active_generations[session_id] = mock_task

    # Mock aiohttp.ClientSession
    mock_session_instance = AsyncMock(spec=aiohttp.ClientSession)
    mock_response = MockAiohttpStreamResponse(status=200, chunks=[]) # Réponse OK pour stop
    mock_session_instance.post.return_value = mock_response
    
    with patch("aiohttp.ClientSession", return_value=mock_session_instance) as mock_session_class:
        success = await tts_service.stop_generation(session_id)

    assert success is True
    assert mock_task.cancelled() # Vérifier que la tâche a été annulée
    assert session_id not in tts_service.active_generations
    mock_session_instance.post.assert_awaited_once_with(
        "http://test-tts-api.com/api/stop", # URL basée sur settings mockés
        json={"session_id": session_id, "immediate_stop": True},
        headers={"Content-Type": "application/json"}
    )

@pytest.mark.asyncio
async def test_tts_stop_generation_api_fail(tts_service: TtsService, mocker: MagicMock):
    session_id = "test_session_stop_fail"
    mock_task = asyncio.create_task(asyncio.sleep(0.1))
    tts_service.active_generations[session_id] = mock_task

    # Mock aiohttp.ClientSession pour retourner une erreur 500
    mock_session_instance = AsyncMock(spec=aiohttp.ClientSession)
    mock_response = MockAiohttpStreamResponse(status=500, chunks=[])
    mock_session_instance.post.return_value = mock_response
    
    with patch("aiohttp.ClientSession", return_value=mock_session_instance) as mock_session_class:
        success = await tts_service.stop_generation(session_id)

    assert success is False # L'arrêt a échoué côté API
    assert mock_task.cancelled() # La tâche locale doit quand même être annulée
    assert session_id not in tts_service.active_generations
    mock_session_instance.post.assert_awaited_once()

@pytest.mark.asyncio
async def test_tts_stream_synthesize_cache_hit(
    tts_service: TtsService, 
    mock_redis_conn: AsyncMock, 
    mocker: MagicMock
):
    websocket_manager = AsyncMock()
    session_id = "test_session_cache_hit_stream"
    text = "Bonjour de cache"
    emotion = "neutre"
    language = "fr"
    cached_audio = b"cached_audio_data_stream"
    cache_key = tts_service.cache_service.generate_cache_key(text, language, tts_service._get_speaker_id(emotion), emotion)

    # Mock cache hit
    # Utiliser le mock injecté dans la fixture tts_service
    tts_service.cache_service.stream_from_cache = AsyncMock(return_value=True)
    
    # Mock aiohttp pour vérifier qu'il n'est PAS appelé
    mock_session_class = mocker.patch("aiohttp.ClientSession")

    await tts_service.stream_synthesize(websocket_manager, session_id, text, emotion, language)

    # Vérifier les appels
    websocket_manager.send_personal_message.assert_has_awaits([
        call(json.dumps({"type": "audio_control", "event": "ia_speech_start"}), session_id),
        call(json.dumps({"type": "audio_control", "event": "ia_speech_end"}), session_id)
    ])
    # Vérifier que stream_from_cache a été appelé
    tts_service.cache_service.stream_from_cache.assert_awaited_once_with(cache_key, ANY) # ANY pour le callback
    # Vérifier que l'API TTS n'a pas été appelée
    mock_session_class.assert_not_called()
    # Vérifier que la tâche a été enregistrée puis retirée
    assert session_id not in tts_service.active_generations

@pytest.mark.asyncio
async def test_tts_stream_synthesize_cache_miss(
    tts_service: TtsService, 
    mock_redis_conn: AsyncMock, 
    mocker: MagicMock
):
    websocket_manager = AsyncMock()
    session_id = "test_session_cache_miss_stream"
    text = "Au revoir API"
    emotion = "encouragement"
    language = "fr"
    api_audio_chunk1 = b"api_chunk_1"
    api_audio_chunk2 = b"api_chunk_2"
    speaker_id = tts_service._get_speaker_id(emotion)
    cache_key = tts_service.cache_service.generate_cache_key(text, language, speaker_id, emotion)

    # Mock cache miss
    tts_service.cache_service.stream_from_cache = AsyncMock(return_value=False)
    # Mock cache set
    tts_service.cache_service.set_audio = AsyncMock(return_value=True)

    # Mock aiohttp.ClientSession et la réponse streamée
    mock_session_instance = AsyncMock(spec=aiohttp.ClientSession)
    mock_response = MockAiohttpStreamResponse(status=200, chunks=[api_audio_chunk1, api_audio_chunk2])
    mock_session_instance.post.return_value = mock_response
    mock_session_class = mocker.patch("aiohttp.ClientSession", return_value=mock_session_instance)

    await tts_service.stream_synthesize(websocket_manager, session_id, text, emotion, language)

    # Vérifier les appels
    websocket_manager.send_personal_message.assert_has_awaits([
        call(json.dumps({"type": "audio_control", "event": "ia_speech_start"}), session_id),
        call(json.dumps({"type": "audio_control", "event": "ia_speech_end"}), session_id)
    ])
    # Vérifier les chunks envoyés
    websocket_manager.send_binary.assert_has_awaits([
        call(api_audio_chunk1, session_id),
        call(api_audio_chunk2, session_id)
    ])
    # Vérifier l'appel API
    mock_session_instance.post.assert_awaited_once()
    call_args, call_kwargs = mock_session_instance.post.call_args
    assert call_args[0] == "http://test-tts-api.com/api/tts"
    sent_payload = call_kwargs.get("json", {})
    assert sent_payload["text"] == text
    assert sent_payload["language"] == language
    assert sent_payload["speaker_id"] == speaker_id
    assert sent_payload["stream"] is True
    
    # Vérifier les appels au cache
    tts_service.cache_service.stream_from_cache.assert_awaited_once_with(cache_key, ANY)
    tts_service.cache_service.set_audio.assert_awaited_once_with(cache_key, api_audio_chunk1 + api_audio_chunk2)
    # Vérifier que la tâche a été enregistrée puis retirée
    assert session_id not in tts_service.active_generations

@pytest.mark.asyncio
async def test_tts_stream_synthesize_api_error(
    tts_service: TtsService, 
    mock_redis_conn: AsyncMock, 
    mocker: MagicMock
):
    websocket_manager = AsyncMock()
    session_id = "test_session_api_error_stream"
    text = "Erreur API"
    emotion = "neutre"
    language = "fr"
    cache_key = tts_service.cache_service.generate_cache_key(text, language, tts_service._get_speaker_id(emotion), emotion)

    # Mock cache miss
    tts_service.cache_service.stream_from_cache = AsyncMock(return_value=False)

    # Mock aiohttp pour retourner une erreur 500
    mock_session_instance = AsyncMock(spec=aiohttp.ClientSession)
    mock_response = MockAiohttpStreamResponse(status=500, chunks=[])
    mock_session_instance.post.return_value = mock_response
    mock_session_class = mocker.patch("aiohttp.ClientSession", return_value=mock_session_instance)

    # Utiliser pytest.raises pour vérifier l'exception
    with pytest.raises(aiohttp.ClientResponseError):
        await tts_service.stream_synthesize(websocket_manager, session_id, text, emotion, language)

    # Vérifier que le message de début a été envoyé mais pas celui de fin
    websocket_manager.send_personal_message.assert_awaited_once_with(
        json.dumps({"type": "audio_control", "event": "ia_speech_start"}), session_id
    )
    websocket_manager.send_binary.assert_not_awaited()
    # Vérifier que la tâche a été retirée même en cas d'erreur
    assert session_id not in tts_service.active_generations
    # Vérifier que set_audio n'a pas été appelé
    tts_service.cache_service.set_audio.assert_not_awaited()

