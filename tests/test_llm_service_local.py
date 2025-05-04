import pytest
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch
from typing import List, Dict, Any, Tuple, Generator

import aiohttp

# Importer la classe à tester
from services.llm_service_local import LlmService, TARGET_EMOTIONS
# Importer les settings pour les valeurs par défaut
from core.config import settings

# Type hint pour le retour des fixtures
LLMFixtureReturnType = Tuple[LlmService, AsyncMock]

# Fixture pour initialiser le service LLM avec vLLM
@pytest.fixture
def llm_service_vllm(mocker: MagicMock) -> Generator[LLMFixtureReturnType, None, None]:
    # Mocker les settings pour utiliser vLLM
    mocker.patch("core.config.settings.LLM_BACKEND", "vllm")
    mocker.patch("core.config.settings.LLM_LOCAL_API_URL", "http://vllm-test:8000")

    # Mocker aiohttp.ClientSession et son instance
    mock_session_instance = AsyncMock(spec=aiohttp.ClientSession)
    # Configurer le mock pour qu'il se comporte comme un context manager
    mock_session_class = mocker.patch("aiohttp.ClientSession", return_value=mock_session_instance)
    # Simuler l'entrée/sortie du context manager
    mock_session_instance.__aenter__.return_value = mock_session_instance
    mock_session_instance.__aexit__.return_value = None 

    # Instancier le service LLM
    service = LlmService()
    
    # Retourner le service et l'instance mockée de la session
    yield service, mock_session_instance
    
    # Nettoyage (pas nécessaire avec mocker)

# Fixture pour initialiser le service LLM avec TGI
@pytest.fixture
def llm_service_tgi(mocker: MagicMock) -> Generator[LLMFixtureReturnType, None, None]:
    # Mocker les settings pour utiliser TGI
    mocker.patch("core.config.settings.LLM_BACKEND", "tgi")
    mocker.patch("core.config.settings.LLM_LOCAL_API_URL", "http://tgi-test:8080")

    # Mocker aiohttp.ClientSession et son instance
    mock_session_instance = AsyncMock(spec=aiohttp.ClientSession)
    mock_session_class = mocker.patch("aiohttp.ClientSession", return_value=mock_session_instance)
    mock_session_instance.__aenter__.return_value = mock_session_instance
    mock_session_instance.__aexit__.return_value = None

    # Instancier le service LLM
    service = LlmService()
    
    yield service, mock_session_instance

# Mock amélioré pour simuler la réponse de aiohttp
class MockAiohttpResponse:
    def __init__(self, status: int, json_data: Any = None, text_data: str = None, url: str = "http://mock-url.com"):
        self.status = status
        self._json_data = json_data
        self._text_data = text_data if text_data is not None else (json.dumps(json_data) if json_data is not None else "")
        # Attributs pour simuler ClientResponseError
        self.request_info = MagicMock(spec=aiohttp.RequestInfo)
        self.request_info.url = aiohttp.hdrs.URL(url)
        self.request_info.method = "POST"
        self.request_info.headers = {}
        self.history: Tuple[Any, ...] = ()
        self.headers = {}

    async def json(self) -> Any:
        if self._json_data is None:
            # Simuler l'erreur si on essaie de lire du JSON alors qu'il n'y en a pas
            raise aiohttp.ContentTypeError(self.request_info, self.history)
        return self._json_data

    async def text(self) -> str:
        return self._text_data

    async def __aenter__(self) -> "MockAiohttpResponse":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        pass
    
    def close(self) -> None:
        pass
        
    # Méthode pour simuler l'erreur ClientResponseError
    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                self.request_info,
                self.history,
                status=self.status,
                message=f"HTTP Error {self.status}",
                headers=self.headers,
            )

# --- Tests pour vLLM --- 

@pytest.mark.asyncio
async def test_vllm_generate_success(llm_service_vllm: LLMFixtureReturnType):
    service, mock_session = llm_service_vllm
    expected_text = "Ceci est la réponse du coach."
    expected_emotion = "encouragement"

    mock_response = MockAiohttpResponse(status=200, json_data={
        "choices": [{
            "message": {"content": f"{expected_text}\n[EMOTION: {expected_emotion}]"}
        }]
    })
    mock_session.post.return_value = mock_response
    
    history: List[Dict[str, str]] = [{"role": "user", "content": "Bonjour coach"}]
    result = await service.generate(history, is_interrupted=False)

    assert result == {"text_response": expected_text, "emotion_label": expected_emotion}
    mock_session.post.assert_awaited_once()
    call_args, call_kwargs = mock_session.post.call_args
    assert call_args[0] == "http://vllm-test:8000/v1/chat/completions"
    sent_payload = call_kwargs.get("json", {})
    assert "messages" in sent_payload
    assert len(sent_payload["messages"]) == 2 # System + User
    assert sent_payload["messages"][0]["role"] == "system"
    assert "coach vocal interactif" in sent_payload["messages"][0]["content"]
    assert f"[{', '.join(TARGET_EMOTIONS)}]" in sent_payload["messages"][0]["content"]
    assert sent_payload["messages"][1] == history[0]
    assert "timeout" in call_kwargs
    assert isinstance(call_kwargs["timeout"], aiohttp.ClientTimeout)
    assert call_kwargs["timeout"].total == settings.LLM_TIMEOUT_SECONDS

@pytest.mark.asyncio
async def test_vllm_generate_success_interrupted(llm_service_vllm: LLMFixtureReturnType):
    service, mock_session = llm_service_vllm
    expected_text = "Oui ? Que puis-je faire ?"
    expected_emotion = "curiosite"

    mock_response = MockAiohttpResponse(status=200, json_data={
        "choices": [{
            "message": {"content": f"{expected_text}\n[EMOTION: {expected_emotion}]"}
        }]
    })
    mock_session.post.return_value = mock_response
    
    history: List[Dict[str, str]] = [
        {"role": "user", "content": "Bonjour"}, 
        {"role": "assistant", "content": "Comment allez-vous ?"}, 
        {"role": "user", "content": "En fait je voulais..."}
    ]
    result = await service.generate(history, is_interrupted=True)

    assert result == {"text_response": expected_text, "emotion_label": expected_emotion}
    mock_session.post.assert_awaited_once()
    call_args, call_kwargs = mock_session.post.call_args
    sent_payload = call_kwargs.get("json", {})
    assert "messages" in sent_payload
    # Vérifier que le prompt système contient le contexte d'interruption
    assert "L'utilisateur vient de t'interrompre" in sent_payload["messages"][0]["content"]
    # Vérifier que l'historique complet est envoyé
    assert len(sent_payload["messages"]) == len(history) + 1 # System + history
    assert sent_payload["messages"][1:] == history

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response_content, expected_text, expected_emotion",
    [
        ("Réponse sans émotion valide.\n[EMOTION: heureux]", "Réponse sans émotion valide.", "neutre"),
        ("Réponse sans aucune ligne d'émotion.", "Réponse sans aucune ligne d'émotion.", "neutre"),
        ("Réponse avec émotion mal formée.\n[EMOTION encouragement]", "Réponse avec émotion mal formée.", "neutre"),
        ("Réponse valide.\n[EMOTION: surprise]", "Réponse valide.", "surprise"),
        ("[EMOTION: tristesse]\nRéponse valide.", "Réponse valide.", "tristesse"), # Emotion en début
    ]
)
async def test_vllm_generate_emotion_extraction(
    llm_service_vllm: LLMFixtureReturnType, 
    response_content: str, 
    expected_text: str, 
    expected_emotion: str
):
    service, mock_session = llm_service_vllm
    mock_response = MockAiohttpResponse(status=200, json_data={
        "choices": [{
            "message": {"content": response_content}
        }]
    })
    mock_session.post.return_value = mock_response
    result = await service.generate([], is_interrupted=False)
    assert result["text_response"] == expected_text
    assert result["emotion_label"] == expected_emotion

@pytest.mark.asyncio
async def test_vllm_generate_api_error(llm_service_vllm: LLMFixtureReturnType):
    service, mock_session = llm_service_vllm
    mock_response = MockAiohttpResponse(status=500, text_data="Internal Server Error")
    # Configurer le mock pour lever l'erreur lors de l'appel à raise_for_status
    mock_response.raise_for_status = MagicMock(side_effect=aiohttp.ClientResponseError(mock_response.request_info, mock_response.history, status=500))
    mock_session.post.return_value = mock_response

    with pytest.raises(aiohttp.ClientResponseError):
        await service.generate([], is_interrupted=False)
    # Vérifier que raise_for_status a été appelé (implicitement par la gestion d'erreur dans le service)
    # mock_response.raise_for_status.assert_called_once() # Difficile à vérifier sans mocker explicitement l'appel

@pytest.mark.asyncio
async def test_vllm_generate_timeout(llm_service_vllm: LLMFixtureReturnType):
    service, mock_session = llm_service_vllm
    mock_session.post.side_effect = asyncio.TimeoutError()

    with pytest.raises(TimeoutError, match="Timeout API vLLM"):
        await service.generate([], is_interrupted=False)
    mock_session.post.assert_awaited_once()

# --- Tests pour TGI --- 

@pytest.mark.asyncio
async def test_tgi_generate_success(llm_service_tgi: LLMFixtureReturnType):
    service, mock_session = llm_service_tgi
    expected_text = "Ceci est la réponse du coach."
    expected_emotion = "encouragement"

    mock_response = MockAiohttpResponse(status=200, json_data=[{
        "generated_text": f"{expected_text}\n[EMOTION: {expected_emotion}]"
    }])
    mock_session.post.return_value = mock_response
    
    history: List[Dict[str, str]] = [{"role": "user", "content": "Bonjour coach"}]
    result = await service.generate(history, is_interrupted=False)

    assert result == {"text_response": expected_text, "emotion_label": expected_emotion}
    mock_session.post.assert_awaited_once()
    call_args, call_kwargs = mock_session.post.call_args
    assert call_args[0] == "http://tgi-test:8080/generate"
    sent_payload = call_kwargs.get("json", {})
    assert "inputs" in sent_payload
    assert "parameters" in sent_payload
    assert "<|system|>\nTu es un coach vocal interactif" in sent_payload["inputs"]
    assert "<|user|>\nBonjour coach" in sent_payload["inputs"]
    assert "<|assistant|>\n" in sent_payload["inputs"] # Vérifier le prompt final
    assert "timeout" in call_kwargs
    assert isinstance(call_kwargs["timeout"], aiohttp.ClientTimeout)
    assert call_kwargs["timeout"].total == settings.LLM_TIMEOUT_SECONDS

@pytest.mark.asyncio
async def test_tgi_generate_success_interrupted(llm_service_tgi: LLMFixtureReturnType):
    service, mock_session = llm_service_tgi
    expected_text = "Oui ? Que puis-je faire ?"
    expected_emotion = "curiosite"

    mock_response = MockAiohttpResponse(status=200, json_data=[{
        "generated_text": f"{expected_text}\n[EMOTION: {expected_emotion}]"
    }])
    mock_session.post.return_value = mock_response
    
    history: List[Dict[str, str]] = [
        {"role": "user", "content": "Bonjour"}, 
        {"role": "assistant", "content": "Comment allez-vous ?"}, 
        {"role": "user", "content": "En fait je voulais..."}
    ]
    result = await service.generate(history, is_interrupted=True)

    assert result == {"text_response": expected_text, "emotion_label": expected_emotion}
    mock_session.post.assert_awaited_once()
    call_args, call_kwargs = mock_session.post.call_args
    sent_payload = call_kwargs.get("json", {})
    assert "inputs" in sent_payload
    # Vérifier que le prompt système contient le contexte d'interruption
    assert "L'utilisateur vient de t'interrompre" in sent_payload["inputs"]
    # Vérifier que l'historique est correctement formaté
    assert "<|user|>\nBonjour" in sent_payload["inputs"]
    assert "<|assistant|>\nComment allez-vous ?" in sent_payload["inputs"]
    assert "<|user|>\nEn fait je voulais..." in sent_payload["inputs"]

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response_content, expected_text, expected_emotion",
    [
        ("Réponse sans émotion valide.\n[EMOTION: heureux]", "Réponse sans émotion valide.", "neutre"),
        ("Réponse sans aucune ligne d'émotion.", "Réponse sans aucune ligne d'émotion.", "neutre"),
        ("Réponse avec émotion mal formée.\n[EMOTION encouragement]", "Réponse avec émotion mal formée.", "neutre"),
        ("Réponse valide.\n[EMOTION: surprise]", "Réponse valide.", "surprise"),
        ("[EMOTION: tristesse]\nRéponse valide.", "Réponse valide.", "tristesse"),
    ]
)
async def test_tgi_generate_emotion_extraction(
    llm_service_tgi: LLMFixtureReturnType, 
    response_content: str, 
    expected_text: str, 
    expected_emotion: str
):
    service, mock_session = llm_service_tgi
    mock_response = MockAiohttpResponse(status=200, json_data=[{
        "generated_text": response_content
    }])
    mock_session.post.return_value = mock_response
    result = await service.generate([], is_interrupted=False)
    assert result["text_response"] == expected_text
    assert result["emotion_label"] == expected_emotion

@pytest.mark.asyncio
async def test_tgi_generate_api_error(llm_service_tgi: LLMFixtureReturnType):
    service, mock_session = llm_service_tgi
    mock_response = MockAiohttpResponse(status=500, text_data="Internal Server Error")
    mock_response.raise_for_status = MagicMock(side_effect=aiohttp.ClientResponseError(mock_response.request_info, mock_response.history, status=500))
    mock_session.post.return_value = mock_response

    with pytest.raises(aiohttp.ClientResponseError):
        await service.generate([], is_interrupted=False)

@pytest.mark.asyncio
async def test_tgi_generate_timeout(llm_service_tgi: LLMFixtureReturnType):
    service, mock_session = llm_service_tgi
    mock_session.post.side_effect = asyncio.TimeoutError()

    with pytest.raises(TimeoutError, match="Timeout API TGI"):
        await service.generate([], is_interrupted=False)
    mock_session.post.assert_awaited_once()

# Test du format de réponse TGI alternatif (objet unique au lieu de liste)
@pytest.mark.asyncio
async def test_tgi_generate_alternative_response_format(llm_service_tgi: LLMFixtureReturnType):
    service, mock_session = llm_service_tgi
    expected_text = "Ceci est la réponse du coach."
    expected_emotion = "empathie"

    # Format de réponse alternatif (objet au lieu de liste)
    mock_response = MockAiohttpResponse(status=200, json_data={
        "generated_text": f"{expected_text}\n[EMOTION: {expected_emotion}]"
    })
    mock_session.post.return_value = mock_response
    
    history: List[Dict[str, str]] = [{"role": "user", "content": "Je me sens triste"}]
    result = await service.generate(history, is_interrupted=False)

    assert result == {"text_response": expected_text, "emotion_label": expected_emotion}
    mock_session.post.assert_awaited_once()

