import pytest
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock

import aiohttp
from aioresponses import aioresponses # Importer aioresponses

# Importer la classe à tester
from services.llm_service import LlmService, TARGET_EMOTIONS
# Importer les settings pour les valeurs par défaut
from core.config import settings

# Mock pour simuler la réponse de aiohttp, y compris le contenu streamé
class MockAiohttpResponse:
    def __init__(self, status, json_data=None, text_data=None, content_chunks=None):
        self.status = status
        self._json_data = json_data
        self._text_data = text_data if text_data is not None else (json.dumps(json_data) if json_data else "")
        self.request_info = MagicMock()
        self.history = ()
        self.headers = {}
        # Créer un itérateur asynchrone mocké pour le contenu streamé
        self.content = AsyncMock()
        _content_chunks = content_chunks if content_chunks is not None else []

        # Définir explicitement __aiter__ pour retourner un itérateur asynchrone
        async def _aiter():
            for chunk in _content_chunks:
                yield chunk
        self.content.__aiter__ = _aiter

    async def json(self):
        if self._json_data is None:
            raise aiohttp.ContentTypeError(MagicMock(), MagicMock())
        return self._json_data

    async def text(self):
        return self._text_data

    async def __aenter__(self):
        # Nécessaire pour `async with response:`
        return self

    async def __aexit__(self, exc_type, exc, tb):
        # Nécessaire pour `async with response:`
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

# Fixture pour instancier le service LLM (plus besoin de mocker aiohttp ici)
@pytest.fixture
def llm_service_instance():
    # Note: Assurez-vous que les settings sont chargés correctement,
    # surtout SCW_LLM_API_KEY pour l'initialisation du service.
    # Si les tests échouent à cause de settings manquants,
    # il faudra peut-être mocker `settings` ou s'assurer que .env est lu.
    try:
        service = LlmService()
    except Exception as e:
        # Fournir un message d'erreur plus clair si l'initialisation échoue
        pytest.fail(f"Failed to initialize LlmService: {e}. Ensure SCW_LLM_API_KEY is set in .env or mocked.")
    return service

# Test de la génération LLM réussie (cas normal) avec aioresponses
@pytest.mark.asyncio
async def test_generate_success(llm_service_instance):
    service = llm_service_instance
    url = service.api_url

    # Définir les chunks de la réponse streamée
    stream_chunks = [
        bytes('data: {"choices": [{"delta": {"content": "Ceci est "}}]}\n', 'utf-8'),
        bytes('data: {"choices": [{"delta": {"content": "la réponse "}}]}\n', 'utf-8'),
        bytes('data: {"choices": [{"delta": {"content": "du coach."}}]}\n', 'utf-8'),
        bytes('data: \n', 'utf-8'), # Ligne vide
        bytes('data: [EMOTION: encouragement]\n', 'utf-8'),
        bytes('data: [DONE]\n', 'utf-8')
    ]

    with aioresponses() as m:
        # Mocker la requête POST vers l'URL de l'API avec body pour le stream
        m.post(url, body=b"".join(stream_chunks), status=200, content_type='text/event-stream') # Utiliser body

        history = [{"role": "user", "content": "Bonjour coach"}]
        result = await service.generate(history, is_interrupted=False)

        # Vérifications
        assert result == {"text_response": "Ceci est la réponse du coach.", "emotion_label": "encouragement"}

# Test de la génération LLM réussie (cas interruption) avec aioresponses
@pytest.mark.asyncio
async def test_generate_success_interrupted(llm_service_instance):
    service = llm_service_instance
    url = service.api_url

    stream_chunks = [
        bytes('data: {"choices": [{"delta": {"content": "Oui ? "}}]}\n', 'utf-8'),
        bytes('data: {"choices": [{"delta": {"content": "Que puis-je faire ?"}}]}\n', 'utf-8'),
        bytes('data: \n', 'utf-8'),
        bytes('data: [EMOTION: curiosite]\n', 'utf-8'),
        bytes('data: [DONE]\n', 'utf-8')
    ]

    with aioresponses() as m:
        m.post(url, body=b"".join(stream_chunks), status=200, content_type='text/event-stream') # Utiliser body

        history = [{"role": "user", "content": "Bonjour"}, {"role": "assistant", "content": "Comment allez-vous ?"}, {"role": "user", "content": "En fait je voulais..."}]
        result = await service.generate(history, is_interrupted=True)

        assert result == {"text_response": "Oui ? Que puis-je faire ?", "emotion_label": "curiosite"}

# Test de l'extraction d'émotion invalide ou manquante avec aioresponses
@pytest.mark.asyncio
async def test_generate_emotion_extraction(llm_service_instance):
    service = llm_service_instance
    url = service.api_url

    # Cas 1: Émotion non valide
    stream_chunks_1 = [
        bytes('data: {"choices": [{"delta": {"content": "Réponse sans émotion valide."}}]}\n', 'utf-8'),
        bytes('data: \n', 'utf-8'),
        bytes('data: [EMOTION: heureux]\n', 'utf-8'),
        bytes('data: [DONE]\n', 'utf-8')
    ]
    with aioresponses() as m:
        m.post(url, body=b"".join(stream_chunks_1), status=200, content_type='text/event-stream') # Utiliser body
        result_1 = await service.generate([], is_interrupted=False)
        assert result_1["emotion_label"] == "neutre"
        assert result_1["text_response"] == "Réponse sans émotion valide."
        assert "[EMOTION: heureux]" not in result_1["text_response"] # Vérifier que la ligne invalide est absente

    # Cas 2: Pas de ligne d'émotion
    stream_chunks_2 = [
        bytes('data: {"choices": [{"delta": {"content": "Réponse sans aucune ligne d\'émotion."}}]}\n', 'utf-8'),
        bytes('data: [DONE]\n', 'utf-8')
    ]
    with aioresponses() as m:
        m.post(url, body=b"".join(stream_chunks_2), status=200, content_type='text/event-stream') # Utiliser body
        result_2 = await service.generate([], is_interrupted=False)
        assert result_2 == {"text_response": "Réponse sans aucune ligne d'émotion.", "emotion_label": "neutre"}

    # Cas 3: Ligne d'émotion mal formée
    stream_chunks_3 = [
        bytes('data: {"choices": [{"delta": {"content": "Réponse avec émotion mal formée."}}]}\n', 'utf-8'),
        bytes('data: \n', 'utf-8'),
        bytes('data: [EMOTION encouragement]\n', 'utf-8'),
        bytes('data: [DONE]\n', 'utf-8')
    ]
    with aioresponses() as m:
        m.post(url, body=b"".join(stream_chunks_3), status=200, content_type='text/event-stream') # Utiliser body
        result_3 = await service.generate([], is_interrupted=False)
        assert result_3["emotion_label"] == "neutre"
        assert result_3["text_response"] == "Réponse avec émotion mal formée."
        assert "[EMOTION encouragement]" not in result_3["text_response"] # Vérifier que la ligne mal formée est absente

# Test de la gestion d'erreur API (ex: 500) avec aioresponses
@pytest.mark.asyncio
async def test_generate_api_error(llm_service_instance):
    service = llm_service_instance
    url = service.api_url

    with aioresponses() as m:
        m.post(url, status=500, body="Internal Server Error")
        with pytest.raises(aiohttp.ClientResponseError):
             await service.generate([], is_interrupted=False)

# Test de la gestion du timeout avec aioresponses (simulé par exception)
@pytest.mark.asyncio
async def test_generate_timeout(llm_service_instance):
    service = llm_service_instance
    url = service.api_url

    with aioresponses() as m:
        # Simuler un timeout en levant l'exception appropriée
        m.post(url, exception=asyncio.TimeoutError())
        with pytest.raises(TimeoutError, match="Timeout API LLM"):
            await service.generate([], is_interrupted=False)

# Test de la génération de texte d'exercice réussie (non-streaming) avec aioresponses
@pytest.mark.asyncio
async def test_generate_exercise_text_success(llm_service_instance):
    service = llm_service_instance
    url = service.api_url

    response_payload = {
        "choices": [{"message": {"content": "Voici un texte pour l'exercice."}}]
    }

    with aioresponses() as m:
        m.post(url, payload=response_payload, status=200)

        exercise_type = "diction"
        topic = "voyage"
        difficulty = "facile"
        length = "court"

        result = await service.generate_exercise_text(exercise_type, topic, difficulty, length)

        # Vérifications
        assert result == "Voici un texte pour l'exercice."
        # Vérifier que la requête a été faite avec stream=False
        request = list(m.requests.values())[0][0] # Accéder à la requête interceptée
        sent_payload = request.kwargs['json'] # Accéder directement au dict
        assert sent_payload.get("stream") is False

# Test de la gestion d'erreur API pour la génération d'exercice avec aioresponses
@pytest.mark.asyncio
async def test_generate_exercise_text_api_error(llm_service_instance):
    service = llm_service_instance
    url = service.api_url

    with aioresponses() as m:
        m.post(url, status=400, body="Bad Request")
        with pytest.raises(aiohttp.ClientResponseError):
            await service.generate_exercise_text("diction")

# Test de la gestion du timeout pour la génération d'exercice avec aioresponses
@pytest.mark.asyncio
async def test_generate_exercise_text_timeout(llm_service_instance):
    service = llm_service_instance
    url = service.api_url

    with aioresponses() as m:
        m.post(url, exception=asyncio.TimeoutError())
        with pytest.raises(TimeoutError, match="Timeout API LLM exercice"):
            await service.generate_exercise_text("diction")
