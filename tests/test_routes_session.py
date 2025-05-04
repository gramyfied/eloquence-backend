import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock, ANY
import uuid
import json
from typing import Generator, Dict, Any, List

from fastapi import FastAPI
from starlette.testclient import TestClient # Utiliser starlette directement
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# Mocker les dépendances avant l'import de l'app
import sys
mock_orchestrator_module = MagicMock()
mock_orchestrator_instance = AsyncMock()
mock_orchestrator_module.orchestrator = mock_orchestrator_instance
sys.modules["core.orchestrator"] = mock_orchestrator_module

# Importer l'application et les dépendances nécessaires
from app.main import app # Assurez-vous que c'est le bon point d'entrée
from core.database import get_db # Dépendance DB originale
from core.models import CoachingSession, SessionTurn, ScenarioTemplate
from app.schemas import SessionStartRequest, SessionEndResponse
from core.auth import get_current_user_id # Dépendance Auth originale

# --- Fixtures --- 

# Fixture pour la session DB asynchrone (suppose qu'elle vient de conftest.py)
@pytest_asyncio.fixture
async def db_session(async_test_db: AsyncSession) -> AsyncSession:
    # Retourner directement la session au lieu d'utiliser yield
    return async_test_db

# Fixture pour le client de test FastAPI avec override de la DB
@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    # Créer une fonction asynchrone qui retourne la session directement
    async def get_test_db():
        return db_session
    
    # Remplacer la dépendance get_db dans l'application FastAPI
    app.dependency_overrides[get_db] = get_test_db
    
    # Utiliser httpx.AsyncClient pour tester l'application asynchrone
    import httpx
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver"
    ) as c:
        # Retourner directement le client au lieu d'utiliser yield
        return c
    
    # Note: Le nettoyage des overrides est géré par la fixture cleanup_dependency_overrides dans conftest.py

# Fixture pour mocker les dépendances des routes session
@pytest.fixture
def session_route_mocks(mocker: MagicMock) -> Dict[str, Any]:
    # Mock get_current_user_id
    mock_get_user = mocker.patch("app.routes.session.get_current_user_id", return_value="test_user_session_route")
    
    # Mock l'instance orchestrator importée dans app.routes.session
    # Utiliser autospec pour un mock plus fidèle
    mock_orchestrator = mocker.patch("app.routes.session.orchestrator", autospec=True)
    
    # Configurer les méthodes mockées nécessaires
    mock_orchestrator.get_or_create_session = AsyncMock()
    mock_orchestrator.generate_text_response = AsyncMock()
    mock_orchestrator.cleanup_session = AsyncMock()
    
    return {
        "get_user": mock_get_user,
        "orchestrator": mock_orchestrator
    }

# --- Tests pour /session/start --- 

@pytest.mark.asyncio
async def test_start_session_success(
    client: TestClient, 
    db_session: AsyncSession, 
    session_route_mocks: Dict[str, Any]
):
    mock_orchestrator = session_route_mocks["orchestrator"]
    user_id = "test_user_session_route"
    scenario_id_str = "test_scenario_start"
    language = "fr"
    goal = "améliorer ma prononciation"

    # Insérer un scénario de test
    mock_scenario = ScenarioTemplate(id=scenario_id_str, name="Test Scenario", initial_prompt="...")
    db_session.add(mock_scenario)
    await db_session.commit()
    # await db_session.refresh(mock_scenario) # Pas nécessaire si on ne le réutilise pas

    # Configurer les mocks de l'orchestrateur
    generated_session_id = str(uuid.uuid4())
    mock_session_state = MagicMock(session_id=generated_session_id, db_session_id=uuid.uuid4())
    mock_orchestrator.get_or_create_session.return_value = mock_session_state
    initial_text = "Bonjour Coach!"
    initial_emotion = "neutre"
    mock_orchestrator.generate_text_response.return_value = {
        "text_response": initial_text,
        "emotion_label": initial_emotion
    }
    
    request_data = {
        "user_id": user_id, # Ce champ est-il vraiment nécessaire si on a get_current_user_id ?
        "scenario_id": scenario_id_str,
        "language": language,
        "goal": goal
    }
    
    # Utiliser await pour l'appel asynchrone
    # Utiliser le chemin corrigé /session/start (supposant que c'est défini dans app/api.py)
    response = await client.post("/session/start", json=request_data)
    
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    # L'ID retourné doit être celui généré DANS l'endpoint, pas celui du mock SessionState
    assert uuid.UUID(data["session_id"]) 
    assert data["websocket_url"] == f"/ws/{data['session_id']}"
    assert data["initial_message"]["text"] == initial_text
    # assert data["initial_message"]["emotion"] == initial_emotion # Vérifier si emotion est dans le schéma
    
    # Vérifier les appels mocks
    mock_orchestrator.get_or_create_session.assert_awaited_once_with(
        ANY, # L'ID de session est généré dans l'endpoint
        db_session,
        scenario_id=scenario_id_str,
        user_id=user_id,
        language=language,
        goal=goal
    )
    
    # Récupérer l'ID de session généré lors de l'appel pour le vérifier dans le second appel
    generated_session_id_arg = mock_orchestrator.get_or_create_session.call_args[0][0]
    expected_prompt = f"Tu es un coach de prononciation français. L'utilisateur souhaite améliorer sa prononciation en {language}. Son objectif est: {goal}. Commence la session en te présentant brièvement et propose un premier exercice."

    mock_orchestrator.generate_text_response.assert_awaited_once_with(
        generated_session_id_arg,
        expected_prompt,
        db_session
    )

@pytest.mark.asyncio
async def test_start_session_failure(
    client: TestClient, 
    db_session: AsyncSession, 
    session_route_mocks: Dict[str, Any]
):
    mock_orchestrator = session_route_mocks["orchestrator"]
    user_id = "test_user_session_route"
    
    # Simuler l'échec de get_or_create_session
    mock_orchestrator.get_or_create_session.return_value = None

    request_data = {"user_id": user_id, "scenario_id": None}
    
    # Utiliser await et le chemin corrigé
    response = await client.post("/session/start", json=request_data)
    
    assert response.status_code == 500
    assert "Erreur interne lors du démarrage de la session." in response.json()["detail"]
    
    mock_orchestrator.get_or_create_session.assert_awaited_once_with(
         ANY, db_session, scenario_id=None, user_id=user_id, language="fr", goal=None
    )
    mock_orchestrator.generate_text_response.assert_not_awaited()

# --- Tests pour /session/{session_id}/end --- 

@pytest.mark.asyncio
async def test_end_session_success(
    client: TestClient, 
    db_session: AsyncSession, 
    session_route_mocks: Dict[str, Any]
):
    mock_orchestrator = session_route_mocks["orchestrator"]
    user_id = "test_user_session_route"
    session_id = uuid.uuid4()
    session_id_str = str(session_id)

    # Insérer session et tours
    mock_session = CoachingSession(id=session_id, user_id=user_id, status="active")
    mock_turn_1 = SessionTurn(id=uuid.uuid4(), session_id=session_id, turn_number=1, role="user", text_content="Bonjour")
    mock_turn_2 = SessionTurn(id=uuid.uuid4(), session_id=session_id, turn_number=2, role="assistant", text_content="Salut")
    db_session.add_all([mock_session, mock_turn_1, mock_turn_2])
    await db_session.commit()
    
    # Configurer mock pour le résumé final
    final_summary_text = "Session terminée."
    mock_orchestrator.generate_text_response.return_value = {"text_response": final_summary_text}
    
    # Utiliser await et le chemin corrigé
    response = await client.post(f"/session/{session_id_str}/end") 
    
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Session terminée avec succès"
    assert data["final_summary"] == final_summary_text
    
    # Vérifier en DB (recharger l'objet)
    await db_session.refresh(mock_session)
    assert mock_session.status == "ended"
    assert mock_session.ended_at is not None
    
    # Vérifier appels mocks
    expected_history = "Utilisateur: Bonjour\nCoach: Salut"
    expected_prompt = f"Tu es un coach de prononciation français. Voici l'historique complet d'une session de coaching:\n{expected_history}\n\nFais un résumé des points forts et des points à améliorer de l'utilisateur, ainsi que des recommandations pour continuer à progresser. Limite ta réponse à 5-6 phrases."
    mock_orchestrator.generate_text_response.assert_awaited_once_with(session_id_str, expected_prompt, db_session)
    mock_orchestrator.cleanup_session.assert_awaited_once_with(session_id_str, db_session)

@pytest.mark.asyncio
async def test_end_session_not_found(
    client: TestClient, 
    db_session: AsyncSession, 
    session_route_mocks: Dict[str, Any]
):
    mock_orchestrator = session_route_mocks["orchestrator"]
    session_id_str = str(uuid.uuid4())
    
    # Ne pas insérer la session

    # Utiliser await et le chemin corrigé
    response = await client.post(f"/session/{session_id_str}/end") 
    
    assert response.status_code == 404
    assert "Session non trouvée" in response.json()["detail"]
    mock_orchestrator.generate_text_response.assert_not_awaited()
    mock_orchestrator.cleanup_session.assert_not_awaited()
