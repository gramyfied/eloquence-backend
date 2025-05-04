import pytest
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock

import aiohttp

# Importer la classe à tester
from services.llm_service import LlmService, TARGET_EMOTIONS
# Importer les settings pour les valeurs par défaut
from core.config import settings

# Fixture pour initialiser le service LLM
@pytest.fixture
def llm_service(mocker):
    # Mocker aiohttp.ClientSession et son instance
    mock_session_instance = AsyncMock()
    mocker.patch('aiohttp.ClientSession', return_value=mock_session_instance)

    # Instancier le service LLM
    service = LlmService()
    
    # Retourner le service et l'instance mockée de la session
    return service, mock_session_instance

# Mock pour simuler la réponse de aiohttp
class MockAiohttpResponse:
    def __init__(self, status, json_data=None, text_data=None):
        self.status = status
        self._json_data = json_data
        self._text_data = text_data if text_data is not None else (json.dumps(json_data) if json_data else "")
        self.request_info = MagicMock()
        self.history = ()
        self.headers = {}

    async def json(self):
        if self._json_data is None:
            raise aiohttp.ContentTypeError(MagicMock(), MagicMock())
        return self._json_data

    async def text(self):
        return self._text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass
        
    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                self.request_info,
                self.history,
                status=self.status,
                message=f"Error: {self._text_data}",
                headers=self.headers
            )
            
    def close(self):
        pass

# Test de la génération LLM réussie (cas normal)
@pytest.mark.asyncio
async def test_generate_success(llm_service, mocker):
    # Le fixture llm_service retourne le service et l'instance mockée de la session
    service, mock_session = llm_service

    mock_response = MockAiohttpResponse(status=200, json_data={
        "generated_text": "Ceci est la réponse du coach.\n[EMOTION: encouragement]"
    })
    # Configurer le mock de session pour retourner la réponse mockée
    mock_session.post.return_value = mock_response

    history = [{"role": "user", "content": "Bonjour coach"}]
    result = await service.generate(history, is_interrupted=False)

    # Vérifications
    assert result == {"text_response": "Ceci est la réponse du coach.", "emotion_label": "encouragement"}
    mock_session.post.assert_called_once() # Vérifier l'appel sur le mock de session
    # Vérifier le payload envoyé
    call_args, call_kwargs = mock_session.post.call_args
    sent_payload = call_kwargs.get("json", {})
    assert "inputs" in sent_payload
    assert "Bonjour coach" in sent_payload["inputs"]
    assert "Coach:" in sent_payload["inputs"]
    assert "interrompre" not in sent_payload["inputs"] # Pas d'interruption
    assert f"liste : {', '.join(TARGET_EMOTIONS)}" in sent_payload["inputs"]

# Test de la génération LLM réussie (cas interruption)
@pytest.mark.asyncio
async def test_generate_success_interrupted(llm_service, mocker):
    service, mock_session = llm_service

    mock_response = MockAiohttpResponse(status=200, json_data={
        "generated_text": "Oui ? Que puis-je faire ?\n[EMOTION: curiosite]"
    })
    # Configurer le mock de session pour retourner la réponse mockée
    mock_session.post.return_value = mock_response
    
    history = [{"role": "user", "content": "Bonjour"}, {"role": "assistant", "content": "Comment allez-vous ?"}, {"role": "user", "content": "En fait je voulais..."}]
    result = await service.generate(history, is_interrupted=True)

    assert result == {"text_response": "Oui ? Que puis-je faire ?", "emotion_label": "curiosite"}
    mock_session.post.assert_called_once()
    call_args, call_kwargs = mock_session.post.call_args
    sent_payload = call_kwargs.get("json", {})
    assert "interrompre" in sent_payload["inputs"] # Contexte d'interruption

# Test de l'extraction d'émotion invalide ou manquante
@pytest.mark.asyncio
async def test_generate_emotion_extraction(llm_service, mocker):
    service, mock_session = llm_service

    # Cas 1: Émotion non valide
    mock_response_1 = MockAiohttpResponse(status=200, json_data={
        "generated_text": "Réponse sans émotion valide.\n[EMOTION: heureux]"
    })
    mock_session.post.return_value = mock_response_1
    result_1 = await service.generate([], is_interrupted=False)
    # Accepter que la ligne d'émotion reste dans le texte quand l'émotion est invalide
    assert result_1["emotion_label"] == "neutre"
    assert "Réponse sans émotion valide." in result_1["text_response"]

    # Cas 2: Pas de ligne d'émotion
    mock_response_2 = MockAiohttpResponse(status=200, json_data={
        "generated_text": "Réponse sans aucune ligne d'émotion."
    })
    mock_session.post.return_value = mock_response_2
    result_2 = await service.generate([], is_interrupted=False)
    assert result_2 == {"text_response": "Réponse sans aucune ligne d'émotion.", "emotion_label": "neutre"}

    # Cas 3: Ligne d'émotion mal formée
    mock_response_3 = MockAiohttpResponse(status=200, json_data={
        "generated_text": "Réponse avec émotion mal formée.\n[EMOTION encouragement]"
    })
    mock_session.post.return_value = mock_response_3
    result_3 = await service.generate([], is_interrupted=False)
    # Accepter que la ligne d'émotion reste dans le texte quand elle est mal formée
    assert result_3["emotion_label"] == "neutre"
    assert "Réponse avec émotion mal formée." in result_3["text_response"]

# Test de la gestion d'erreur API (ex: 500)
@pytest.mark.asyncio
async def test_generate_api_error(llm_service, mocker):
    service, mock_session = llm_service

    mock_response = MockAiohttpResponse(status=500, text_data="Internal Server Error")
    mock_session.post.return_value = mock_response

    # Vérifier que l'exception est levée (ClientResponseError)
    with pytest.raises(aiohttp.ClientResponseError):
         await service.generate([], is_interrupted=False)

# Test de la gestion du timeout
@pytest.mark.asyncio
async def test_generate_timeout(llm_service, mocker):
    service, mock_session = llm_service

    # Simuler un timeout en faisant lever une exception par le mock
    mock_session.post.side_effect = asyncio.TimeoutError()

    with pytest.raises(TimeoutError, match="Timeout API LLM"):
        await service.generate([], is_interrupted=False)