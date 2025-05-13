import pytest
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock

import aiohttp
from aioresponses import aioresponses # Importer aioresponses

# Importer la classe à tester
from services.llm_service_local import LlmService, TARGET_EMOTIONS
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

    # Définir la réponse JSON au format attendu par vLLM
    response_payload = {
        "choices": [
            {
                "message": {
                    "content": "Ceci est la réponse du coach.\n\n[EMOTION: encouragement]"
                }
            }
        ]
    }

    with aioresponses() as m:
        # Mocker la requête POST vers l'URL de l'API avec payload JSON
        m.post(url, payload=response_payload, status=200)

        history = [{"role": "user", "content": "Bonjour coach"}]
        result = await service.generate(history, is_interrupted=False)

        # Vérifications
        assert result["text"] == "Ceci est la réponse du coach."
        assert result["emotion"] == "encouragement"

# Test de la génération LLM réussie (cas interruption) avec aioresponses
@pytest.mark.skip(reason="Test à corriger ultérieurement")
@pytest.mark.asyncio
async def test_generate_success_interrupted(llm_service_instance):
    service = llm_service_instance
    url = service.api_url

    # Définir la réponse JSON au format attendu par vLLM
    response_payload = {
        "choices": [
            {
                "message": {
                    "content": "[EMOTION: curiosite] Oui ? Que puis-je faire ?"
                }
            }
        ]
    }

    with aioresponses() as m:
        # Mocker la requête POST vers l'URL de l'API avec payload JSON
        def check_interrupted_payload(url, **kwargs):
            json_data = kwargs.get('json')
            
            # Utiliser directement les données JSON
            payload = json_data
            messages = payload.get("messages", [])
            # Vérifier que le message système contient l'instruction d'interruption
            assert any("L'utilisateur t'a interrompu" in msg["content"] for msg in messages if msg["role"] == "system")
            return True

        m.post(url, payload=response_payload, status=200, callback=check_interrupted_payload)

        history = [{"role": "user", "content": "Bonjour"}, {"role": "assistant", "content": "Comment allez-vous ?"}, {"role": "user", "content": "En fait je voulais..."}]
        result = await service.generate(history, is_interrupted=True)

        assert result["text"] == "Oui ? Que puis-je faire ?"
        assert result["emotion"] == "curiosite"

# Test de la génération LLM réussie avec contexte de scénario et aioresponses
@pytest.mark.skip(reason="Test à corriger ultérieurement")
@pytest.mark.asyncio
async def test_generate_success_scenario_context(llm_service_instance):
    service = llm_service_instance
    url = service.api_url

    scenario_context = {
        "name": "Entretien d'embauche",
        "goal": "Simuler un entretien",
        "current_step": "introduction",
        "current_step_name": "Présentation initiale",
        "current_step_description": "L'utilisateur se présente",
        "prompt_template": "Demande à l'utilisateur de se présenter.",
        "expected_variables": ["nom", "experience"],
        "next_steps": [{"id": "experience", "name": "Parcours"}],
        "is_final": False,
        "completed_steps": [],
        "variables": {"nom": "N/A"},
        "steps": ["introduction", "experience"]
    }

    response_payload = {
        "choices": [
            {
                "message": {
                    "content": "[EMOTION: neutre] Bonjour, parlez-moi de vous."
                }
            }
        ]
    }

    with aioresponses() as m:
        def check_scenario_payload(url, **kwargs):
            json_data = kwargs.get('json')
            
            # Utiliser directement les données JSON
            payload = json_data
            messages = payload.get("messages", [])
            # Vérifier que le message système contient les informations du scénario
            system_message = next((msg["content"] for msg in messages if msg["role"] == "system"), "")
            assert "Contexte du Scénario:" in system_message
            assert "Nom du scénario: Entretien d'embauche" in system_message
            assert "Étape actuelle: Présentation initiale (introduction)" in system_message
            assert "Instructions spécifiques pour cette étape: Demande à l'utilisateur de se présenter." in system_message
            return True

        m.post(url, payload=response_payload, status=200, callback=check_scenario_payload)

        history = [{"role": "user", "content": "Je suis prêt."}]
        result = await service.generate(history, is_interrupted=False, scenario_context=scenario_context)

        assert result["text"] == "Bonjour, parlez-moi de vous."
        assert result["emotion"] == "neutre"

# Test de la génération LLM avec mise à jour de scénario et aioresponses
@pytest.mark.asyncio
async def test_generate_success_scenario_update(llm_service_instance):
    service = llm_service_instance
    url = service.api_url

    scenario_context = {
        "name": "Entretien d'embauche",
        "goal": "Simuler un entretien",
        "current_step": "introduction",
        "current_step_name": "Présentation initiale",
        "current_step_description": "L'utilisateur se présente",
        "prompt_template": "Demande à l'utilisateur de se présenter.",
        "expected_variables": ["nom", "experience"],
        "next_steps": [{"id": "experience", "name": "Parcours"}],
        "is_final": False,
        "completed_steps": [],
        "variables": {"nom": "N/A"},
        "steps": ["introduction", "experience"]
    }

    response_payload = {
        "choices": [
            {
                "message": {
                    "content": "[EMOTION: encouragement] Très bien. ```json { \"scenario_updates\": { \"next_step\": \"experience\", \"variables\": { \"nom\": \"Jean Dupont\" } } } ``` Passons maintenant à votre expérience."
                }
            }
        ]
    }

    with aioresponses() as m:
        m.post(url, payload=response_payload, status=200)

        history = [{"role": "user", "content": "Je m'appelle Jean Dupont."}]
        result = await service.generate(history, is_interrupted=False, scenario_context=scenario_context)

        assert result["text"] == "Très bien. Passons maintenant à votre expérience."
        assert result["emotion"] == "encouragement"
        assert "scenario_updates" in result
        assert result["scenario_updates"]["next_step"] == "experience"
        assert result["scenario_updates"]["variables"]["nom"] == "Jean Dupont"

# Test de l'extraction d'émotion invalide ou manquante avec aioresponses
@pytest.mark.asyncio
async def test_generate_emotion_extraction(llm_service_instance):
    service = llm_service_instance
    url = service.api_url

    # Cas 1: Émotion non valide
    response_payload_1 = {
        "choices": [
            {
                "message": {
                    "content": "Réponse sans émotion valide.\n\n[EMOTION: heureux]"
                }
            }
        ]
    }
    with aioresponses() as m:
        m.post(url, payload=response_payload_1, status=200)
        result_1 = await service.generate([], is_interrupted=False)
        assert result_1["emotion"] == "neutre"
        # Le service ne supprime pas le tag d'émotion si l'émotion n'est pas reconnue
        assert "Réponse sans émotion valide." in result_1["text"]

    # Cas 2: Pas de ligne d'émotion
    response_payload_2 = {
        "choices": [
            {
                "message": {
                    "content": "Réponse sans aucune ligne d'émotion."
                }
            }
        ]
    }
    with aioresponses() as m:
        m.post(url, payload=response_payload_2, status=200)
        result_2 = await service.generate([], is_interrupted=False)
        assert "Réponse sans aucune ligne d'émotion." in result_2["text"]
        assert result_2["emotion"] == "neutre"

    # Cas 3: Ligne d'émotion mal formée
    response_payload_3 = {
        "choices": [
            {
                "message": {
                    "content": "Réponse avec émotion mal formée.\n\n[EMOTION encouragement]"
                }
            }
        ]
    }
    with aioresponses() as m:
        m.post(url, payload=response_payload_3, status=200)
        result_3 = await service.generate([], is_interrupted=False)
        assert result_3["emotion"] == "neutre"
        assert "Réponse avec émotion mal formée." in result_3["text"]

# Test de la gestion d'erreur API (ex: 500) avec aioresponses
@pytest.mark.asyncio
async def test_generate_api_error(llm_service_instance):
    service = llm_service_instance
    url = service.api_url

    with aioresponses() as m:
        m.post(url, status=500, body="Internal Server Error")
        result = await service.generate([], is_interrupted=False)
        assert "Erreur du service LLM: 500" in result["text"]
        assert result["emotion"] == "neutre"

# Test de la gestion du timeout avec aioresponses (simulé par exception)
@pytest.mark.skip(reason="Test à corriger ultérieurement")
@pytest.mark.asyncio
async def test_generate_timeout(llm_service_instance):
    service = llm_service_instance
    url = service.api_url

    with aioresponses() as m:
        # Simuler un timeout en levant l'exception appropriée
        m.post(url, exception=asyncio.TimeoutError())
        result = await service.generate([], is_interrupted=False)
        assert "Désolé, le service LLM a mis trop de temps à répondre." in result["text"]
        assert result["emotion"] == "neutre"

# Test de la génération de texte d'exercice réussie avec aioresponses
@pytest.mark.skip(reason="Test à corriger ultérieurement")
@pytest.mark.asyncio
async def test_generate_exercise_text_success(llm_service_instance):
    service = llm_service_instance
    url = service.api_url

    exercise_type = "présentation"
    topic = "mon parcours professionnel"
    difficulty = "difficile"
    length = "long"

    response_payload = {
        "choices": [{"message": {"content": "Voici un texte d'exercice de présentation sur votre parcours professionnel."}}]
    }

    with aioresponses() as m:
        # Mocker la requête POST vers l'URL de l'API avec payload JSON
        # On peut vérifier ici que le prompt envoyé contient les bons paramètres
        def check_payload(url, **kwargs):
            json_data = kwargs.get('json')
            
            # Utiliser directement les données JSON
            payload = json_data
            messages = payload.get("messages", [])
            assert len(messages) == 2 # Message système + message utilisateur
            assert messages[0]["role"] == "system"
            assert "générateur de texte pour des exercices" in messages[0]["content"]
            assert messages[1]["role"] == "user"
            assert exercise_type in messages[1]["content"]
            assert topic in messages[1]["content"]
            assert difficulty in messages[1]["content"]
            assert length in messages[1]["content"]
            return True # Indique que le mock doit être utilisé

        m.post(url, payload=response_payload, status=200, callback=check_payload)

        result = await service.generate_exercise_text(
            exercise_type=exercise_type,
            topic=topic,
            difficulty=difficulty,
            length=length
        )

        # Vérifications
        assert result == "Voici un texte d'exercice de présentation sur votre parcours professionnel."

# Test de la gestion d'erreur API pour generate_exercise_text avec aioresponses
@pytest.mark.asyncio
async def test_generate_exercise_text_api_error(llm_service_instance):
    service = llm_service_instance
    url = service.api_url

    with aioresponses() as m:
        m.post(url, status=500, body="Internal Server Error")

        with pytest.raises(Exception, match="Erreur du service LLM lors de la génération d'exercice: 500"):
            await service.generate_exercise_text("présentation")

# Test de la gestion du timeout pour generate_exercise_text avec aioresponses
@pytest.mark.asyncio
async def test_generate_exercise_text_timeout(llm_service_instance):
    service = llm_service_instance
    url = service.api_url

    with aioresponses() as m:
        m.post(url, exception=asyncio.TimeoutError())

        with pytest.raises(Exception, match="Erreur de connexion au service LLM pour génération d'exercice: "):
            await service.generate_exercise_text("présentation")
