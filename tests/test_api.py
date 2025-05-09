import pytest
import uuid
import json
import httpx # <--- Ajouter cet import
from unittest.mock import MagicMock, AsyncMock, patch, ANY
from typing import List, Optional, Dict, Any, Generator

# from fastapi.testclient import TestClient # Plus nécessaire pour le client async
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

# Importer l'application et les dépendances nécessaires
from app.main import app
from core import database as database_module
from core.models import CoachingSession, SessionTurn, KaldiFeedback, ScenarioTemplate, Participant
from app.schemas import FeedbackResponse, SessionStartRequest, SessionEndResponse
from services.orchestrator import Orchestrator # Importer pour le spec du mock
from core.auth import get_current_user_id # Importer pour patcher
# Les routes API utilisent get_orchestrator depuis app.routes.websocket
from app.routes.websocket import get_orchestrator as api_get_orchestrator

# --- Fixtures --- 

# Utiliser la fixture client de conftest.py

# Fixture pour mocker l'orchestrateur (sans patch)
@pytest.fixture(scope="function")
def api_mocks() -> Dict[str, Any]: # <-- Ne fait plus le patch, mocker retiré
    """Fixture pour mocker l'orchestrateur (sans patch)."""
    # Créer un AsyncMock simple sans spec
    mock_orchestrator_instance = AsyncMock()
    # Définir explicitement les méthodes nécessaires comme AsyncMock
    mock_orchestrator_instance.get_or_create_session = AsyncMock()
    mock_orchestrator_instance.generate_text_response = AsyncMock()
    mock_orchestrator_instance.end_session = AsyncMock()
    mock_orchestrator_instance.cleanup_session = AsyncMock()
    # Pas de patch ici
    return {
        "orchestrator_instance": mock_orchestrator_instance # Retourne juste le mock pour référence si besoin ailleurs
    }

# --- Tests --- 

@pytest.mark.asyncio
# Utiliser les nouvelles fixtures client: httpx.AsyncClient et async_test_session: AsyncSession
async def test_get_feedback_success(client: httpx.AsyncClient, async_test_session: AsyncSession, api_mocks: Dict[str, Any]):
    """Teste GET /feedback avec succès."""
    # Utiliser la session directement
    db = async_test_session
    session_id = uuid.uuid4()
    participant_id = uuid.uuid4()
    turn_id_1 = uuid.uuid4()
    turn_id_2 = uuid.uuid4()
    feedback_id_1 = uuid.uuid4()

    # Insérer données de test
    mock_session = CoachingSession(id=session_id, user_id="test-user", status="active")
    mock_participant = Participant(id=participant_id, session_id=session_id, name="Test User", role="user")
    mock_turn_1 = SessionTurn(id=turn_id_1, session_id=session_id, participant_id=participant_id, turn_number=1, role="user", text_content="test transcription 1")
    mock_turn_2 = SessionTurn(id=turn_id_2, session_id=session_id, participant_id=participant_id, turn_number=2, role="user", text_content="test transcription 2")
    feedback_id_2 = uuid.uuid4() # Ajouter un deuxième ID de feedback
    mock_feedback_1 = KaldiFeedback(
        id=feedback_id_1, turn_id=turn_id_1,
        pronunciation_scores={"overall_gop_score": 0.9}, fluency_metrics={"speech_rate_wpm": 120},
        lexical_metrics={"ttr": 0.8}, prosody_metrics={"pitch": 150}
    )
    mock_feedback_2 = KaldiFeedback( # Ajouter un deuxième objet feedback
        id=feedback_id_2, turn_id=turn_id_2,
        pronunciation_scores={"overall_gop_score": 0.8}, fluency_metrics={"speech_rate_wpm": 130},
        lexical_metrics={"ttr": 0.9}, prosody_metrics={"pitch": 160}
    )
    # Ajouter les deux feedbacks à la session
    db.add_all([mock_session, mock_participant, mock_turn_1, mock_turn_2, mock_feedback_1, mock_feedback_2])
    await db.commit()

    # Utiliser le client directement (il est yieldé par la fixture)
    response = await client.get(f"/api/session/{session_id}/feedback")

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == str(session_id)
    assert len(data["feedback_results"]) == 2
    
    feedback_map = {item["turn_number"]: item for item in data["feedback_results"]}
    
    assert 1 in feedback_map
    fb1 = feedback_map[1]
    # Correction: L'API retourne l'ID du turn dans segment_id, pas l'ID du feedback
    assert fb1["segment_id"] == str(turn_id_1)
    # Correction: Accéder aux scores via la clé "feedback"
    assert fb1["feedback"]["pronunciation_scores"]["overall_gop_score"] == 0.9
    # ... autres assertions pour fb1 ...

    assert 2 in feedback_map # <-- Indentation corrigée
    fb2 = feedback_map[2]
    # Correction: L'API retourne l'ID du turn dans segment_id, pas l'ID du feedback
    assert fb2["segment_id"] == str(turn_id_2)
    # Correction: Accéder aux scores via la clé "feedback"
    assert fb2["feedback"]["pronunciation_scores"] == {"overall_gop_score": 0.8} # Vérifier le contenu exact
    assert fb2["feedback"]["fluency_metrics"] == {"speech_rate_wpm": 130} # Vérifier le contenu exact
    assert fb2["feedback"]["lexical_metrics"] == {"ttr": 0.9} # Vérifier le contenu exact
    assert fb2["feedback"]["prosody_metrics"] == {"pitch": 160} # Vérifier le contenu exact
    # ...

@pytest.mark.asyncio
# Utiliser les nouvelles fixtures client: httpx.AsyncClient et async_test_session: AsyncSession
async def test_get_feedback_session_not_found(client: httpx.AsyncClient, async_test_session: AsyncSession, api_mocks: Dict[str, Any]):
    """Teste GET /feedback avec session non trouvée."""
    session_id = uuid.uuid4()
    # Utiliser le client directement
    response = await client.get(f"/api/session/{session_id}/feedback")
    assert response.status_code == 404
    # Correction: Vérifier que le message d'erreur contient la partie générique
    assert "Session non trouvée" in response.json()["detail"]

@pytest.mark.asyncio
# Utiliser les nouvelles fixtures client: httpx.AsyncClient et async_test_session: AsyncSession
async def test_get_feedback_no_feedback_found(client: httpx.AsyncClient, async_test_session: AsyncSession, api_mocks: Dict[str, Any]):
    """Teste GET /feedback sans feedback existant."""
    db = async_test_session # Utiliser la session directement
    session_id = uuid.uuid4()
    mock_session = CoachingSession(id=session_id, user_id="test-user", status="active")
    db.add(mock_session)
    await db.commit()

    # Utiliser le client directement
    response = await client.get(f"/api/session/{session_id}/feedback")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == str(session_id)
    assert len(data["feedback_results"]) == 0

@pytest.mark.asyncio
# Utiliser les nouvelles fixtures client: httpx.AsyncClient et async_test_session: AsyncSession
async def test_get_feedback_with_segment_id_filter(client: httpx.AsyncClient, async_test_session: AsyncSession, api_mocks: Dict[str, Any]):
    """Teste GET /feedback avec filtre segment_id."""
    db = async_test_session # Utiliser la session directement
    session_id = uuid.uuid4()
    turn_id_1, turn_id_2 = uuid.uuid4(), uuid.uuid4()
    feedback_id_1, feedback_id_2 = uuid.uuid4(), uuid.uuid4()

    participant_id = uuid.uuid4()
    mock_session = CoachingSession(id=session_id, user_id="test-user", status="active") # <-- Utilise déjà "test-user"
    mock_participant = Participant(id=participant_id, session_id=session_id, name="Test User", role="user")
    mock_turn_1 = SessionTurn(id=turn_id_1, session_id=session_id, participant_id=participant_id, turn_number=1, role="user")
    mock_turn_2 = SessionTurn(id=turn_id_2, session_id=session_id, participant_id=participant_id, turn_number=2, role="user")
    mock_feedback_1 = KaldiFeedback(id=feedback_id_1, turn_id=turn_id_1, pronunciation_scores={"overall_gop_score": 0.8})
    mock_feedback_2 = KaldiFeedback(id=feedback_id_2, turn_id=turn_id_2, pronunciation_scores={"overall_gop_score": 0.9})
    db.add_all([mock_session, mock_participant, mock_turn_1, mock_turn_2, mock_feedback_1, mock_feedback_2])
    await db.commit()

    # Utiliser le client directement
    
    # Filtrer par turn_id_2
    response_turn = await client.get(f"/api/session/{session_id}/feedback?segment_id={turn_id_2}")
    assert response_turn.status_code == 200
    data_turn = response_turn.json()
    assert len(data_turn["feedback_results"]) == 1
    assert data_turn["feedback_results"][0]["turn_number"] == 2
    assert data_turn["feedback_results"][0]["segment_id"] == str(turn_id_2) # Correction: comparer avec turn_id_2

    # Filtrer par turn_id_1 (ID du SessionTurn)
    response_fb = await client.get(f"/api/session/{session_id}/feedback?segment_id={turn_id_1}") # <-- Corrigé
    assert response_fb.status_code == 200
    data_fb = response_fb.json()
    assert len(data_fb["feedback_results"]) == 1
    assert data_fb["feedback_results"][0]["turn_number"] == 1
    assert data_fb["feedback_results"][0]["segment_id"] == str(turn_id_1) # Correction: comparer avec turn_id_1

@pytest.mark.asyncio
# Utiliser les nouvelles fixtures client: httpx.AsyncClient et async_test_session: AsyncSession
async def test_start_session_success(client: httpx.AsyncClient, async_test_session: AsyncSession, api_mocks: Dict[str, Any]):
    """Teste POST /start avec succès."""
    db = async_test_session # Utiliser la session directement
    orchestrator_instance = api_mocks["orchestrator_instance"]
    user_id = "test-user" # <-- Corrigé
    scenario_id = "test_scenario"

    mock_scenario = ScenarioTemplate(id=scenario_id, name="Test Scenario", initial_prompt="Prompt")
    db.add(mock_scenario)
    await db.commit()

    # Pas besoin de mocker l'orchestrateur pour cette route
    # mock_session_state = MagicMock(session_id="mock-session-uuid", db_session_id=uuid.uuid4())
    # orchestrator_instance.get_or_create_session.return_value = mock_session_state
    # orchestrator_instance.generate_text_response.return_value = {"text_response": "Initial message", "emotion_label": "neutre"}

    # Utiliser le client directement

    request_data = {"user_id": user_id, "scenario_id": scenario_id, "language": "fr", "goal": "Goal"} # user_id est maintenant "test-user"
    response = await client.post("/api/session/start", json=request_data)

    assert response.status_code == 200
    data = response.json()
    # Vérifier que c'est un UUID valide
    try:
        uuid.UUID(data["session_id"])
        is_valid_uuid = True
    except ValueError:
        is_valid_uuid = False
    assert is_valid_uuid
    # Le scénario de test a un initial_prompt, donc il devrait être utilisé
    assert data["initial_message"]["text"] == "Prompt"
    # Vérifier que la session a été créée en DB
    session_uuid = uuid.UUID(data["session_id"])
    result = await db.execute(select(CoachingSession).where(CoachingSession.id == session_uuid)) # <-- Corrigé
    db_session = result.scalar_one_or_none()
    assert db_session is not None
    assert db_session.user_id == user_id
    assert db_session.scenario_template_id == scenario_id
    # Les appels à l'orchestrateur ne sont pas faits dans cette route
    orchestrator_instance.get_or_create_session.assert_not_awaited()
    orchestrator_instance.generate_text_response.assert_not_awaited()

@pytest.mark.asyncio
# Utiliser les nouvelles fixtures client: httpx.AsyncClient et async_test_session: AsyncSession
async def test_start_session_failure(client: httpx.AsyncClient, async_test_session: AsyncSession, api_mocks: Dict[str, Any]):
    """Teste POST /start avec un scenario_id inexistant.""" # <-- Mise à jour docstring
    db = async_test_session # Utiliser la session directement
    # Pas besoin de mocker l'orchestrateur pour ce cas
    # orchestrator_instance = api_mocks["orchestrator_instance"]
    # orchestrator_instance.get_or_create_session.return_value = None

    user_id = "test-user"
    non_existent_scenario_id = "non_existent_scenario"

    # Utiliser le client directement

    request_data = {"user_id": user_id, "scenario_id": non_existent_scenario_id}
    response = await client.post("/api/session/start", json=request_data)

    assert response.status_code == 404 # <-- Attendre 404 Not Found
    assert f"Scénario {non_existent_scenario_id} non trouvé" in response.json()["detail"] # <-- Vérifier le message d'erreur
    # Les appels à l'orchestrateur ne devraient pas avoir lieu
    api_mocks["orchestrator_instance"].get_or_create_session.assert_not_awaited()
    api_mocks["orchestrator_instance"].generate_text_response.assert_not_awaited()

@pytest.mark.asyncio
@patch("services.orchestrator.Orchestrator.end_session")
async def test_end_session_successfully_v2( # Renommage du test
    mock_orchestrator_end_session: AsyncMock,
    client: httpx.AsyncClient,
    async_test_session: AsyncSession,
):
    """Teste POST /end avec succès. v2""" # Mise à jour docstring
    print("<<<<< EXECUTING test_end_session_successfully_v2 >>>>>") # Log de début de test
    db = async_test_session
    user_id = "test-user"
    session_id = uuid.uuid4()

    participant_id = uuid.uuid4()
    # Assurer que le statut est bien 'active' pour que la logique de end_session fonctionne
    mock_session = CoachingSession(id=session_id, user_id=user_id, status="active")
    mock_participant = Participant(id=participant_id, session_id=session_id, name="Test User", role="user")
    mock_turn_1 = SessionTurn(id=uuid.uuid4(), session_id=session_id, participant_id=participant_id, turn_number=1, role="user")
    mock_turn_2 = SessionTurn(id=uuid.uuid4(), session_id=session_id, participant_id=participant_id, turn_number=2, role="assistant")
    db.add_all([mock_session, mock_participant, mock_turn_1, mock_turn_2])
    await db.commit()
    await db.refresh(mock_session) # S'assurer que le statut est bien pris en compte avant l'appel API
    print(f"DEBUG test_end_session_successfully_v2: mock_session.status before API call: {mock_session.status}")


    response = await client.post(f"/api/session/{session_id}/end")
    print(f"DEBUG test_end_session_successfully_v2: response_status={response.status_code}")
    data = response.json()
    print(f"DEBUG test_end_session_successfully_v2: data received: {data}")
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
    assert data["message"] == "Session terminée avec succès", f"Unexpected message: {data.get('message')}"
    assert "final_summary" not in data
    # Correction: Vérifier que final_summary_url est une chaîne non nulle
    assert data["final_summary_url"] is not None
    assert isinstance(data["final_summary_url"], str)

    # Vérifier que la session est terminée en DB
    await db.refresh(mock_session)
    print(f"DEBUG test_end_session_successfully_v2: mock_session.status after API call: {mock_session.status}")
    assert mock_session.status == "ended"
    assert mock_session.ended_at is not None

    # Vérifier l'appel sur le mock direct de la méthode
    # Correction: S'attendre à l'appel avec l'argument nommé session_id
    mock_orchestrator_end_session.assert_awaited_once_with(session_id=session_id)
