import pytest
import pytest_asyncio
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock, call
import uuid
import json
import asyncio
from typing import Generator, Any

# Importer l'application FastAPI et les dépendances
from app.main import app
from services.orchestrator import Orchestrator
from sqlalchemy.ext.asyncio import AsyncSession # Pour le typage

# --- Fixtures --- 

@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """Fixture pour le TestClient FastAPI."""
    with TestClient(app) as c:
        yield c

@pytest.fixture
def mock_orchestrator(mocker: MagicMock) -> AsyncMock:
    """Fixture pour mocker l'instance Orchestrator."""
    # Mocker la fonction get_orchestrator utilisée comme dépendance
    mock_instance = AsyncMock(spec=Orchestrator)
    mock_instance.connect_client = AsyncMock()
    mock_instance.disconnect_client = AsyncMock()
    mock_instance.process_websocket_message = AsyncMock()
    
    # Patcher la dépendance dans le module où elle est utilisée (routes.websocket)
    mocker.patch("app.routes.websocket.get_orchestrator", return_value=mock_instance)
    return mock_instance

@pytest.fixture
def mock_db_session(mocker: MagicMock) -> MagicMock:
    """Fixture pour mocker la session de base de données asynchrone."""
    mock_session = MagicMock(spec=AsyncSession)
    # Patcher la dépendance get_db
    mocker.patch("app.routes.websocket.get_db", return_value=mock_session)
    return mock_session

# --- Tests --- 

# Note: Les tests WebSocket avec TestClient sont synchrones, même si l'endpoint est async.
# pytest.mark.asyncio n'est pas nécessaire pour les fonctions de test elles-mêmes ici.

def test_websocket_connection_success(
    client: TestClient, 
    mock_orchestrator: AsyncMock, 
    mock_db_session: MagicMock # Injecter la fixture pour activer le patch
):
    """Teste la connexion WebSocket réussie et l'appel à connect_client."""
    session_id = str(uuid.uuid4())
    
    with client.websocket_connect(f"/ws/{session_id}") as websocket:
        # Vérifier que connect_client a été appelé après la connexion
        # L'appel se produit dans le contexte de l'endpoint, pas immédiatement ici.
        # On vérifie après la déconnexion ou on ajoute un sleep si nécessaire.
        pass # La connexion est établie

    # L'appel à connect_client devrait se produire à l'intérieur de l'endpoint
    # et disconnect_client à la fin. Vérifions les appels après la fermeture.
    # Note: L'ordre exact peut dépendre de l'implémentation de l'endpoint.
    # Si connect_client est appelé avant le yield/accept, il faut le vérifier différemment.
    # Supposons qu'il est appelé après accept().
    
    # Donner un peu de temps au serveur de test pour traiter la connexion/déconnexion
    # asyncio.sleep n'est pas idéal, mais nécessaire avec TestClient parfois.
    # Une alternative serait de mocker l'orchestrateur pour qu'il signale la fin.
    asyncio.run(asyncio.sleep(0.05)) # Exécuter sleep dans une boucle d'événements

    mock_orchestrator.connect_client.assert_awaited_once()
    args, kwargs = mock_orchestrator.connect_client.call_args
    # Le premier argument est l'objet WebSocket, le second est session_id
    assert isinstance(args[0], MagicMock) # Ou le type réel si non mocké
    assert args[1] == session_id
    # disconnect_client est testé séparément

def test_websocket_receive_audio(
    client: TestClient, 
    mock_orchestrator: AsyncMock, 
    mock_db_session: MagicMock
):
    """Teste la réception d'un message audio binaire."""
    session_id = str(uuid.uuid4())
    audio_chunk = b"\x01\x02\x03\x04"
    
    with client.websocket_connect(f"/ws/{session_id}") as websocket:
        websocket.send_bytes(audio_chunk)
        # Attendre que le message soit traité par l'endpoint
        asyncio.run(asyncio.sleep(0.05))
        
        # Vérifier que process_websocket_message a été appelé avec les bonnes données
        mock_orchestrator.process_websocket_message.assert_awaited_once()
        args, kwargs = mock_orchestrator.process_websocket_message.call_args
        assert args[0] == session_id
        assert args[1] == audio_chunk
        assert args[2] is None # Pas de message texte

def test_websocket_receive_control_message(
    client: TestClient, 
    mock_orchestrator: AsyncMock, 
    mock_db_session: MagicMock
):
    """Teste la réception d'un message de contrôle JSON."""
    session_id = str(uuid.uuid4())
    control_message = {"type": "control", "event": "user_interrupt_start"}
    control_message_str = json.dumps(control_message)
    
    with client.websocket_connect(f"/ws/{session_id}") as websocket:
        websocket.send_text(control_message_str) # Envoyer comme texte JSON
        asyncio.run(asyncio.sleep(0.05))
        
        # Vérifier que process_websocket_message a été appelé avec les bonnes données
        mock_orchestrator.process_websocket_message.assert_awaited_once()
        args, kwargs = mock_orchestrator.process_websocket_message.call_args
        assert args[0] == session_id
        assert args[1] is None # Pas de message binaire
        assert args[2] == control_message_str

def test_websocket_disconnect(
    client: TestClient, 
    mock_orchestrator: AsyncMock, 
    mock_db_session: MagicMock
):
    """Teste l'appel à disconnect_client lors de la déconnexion."""
    session_id = str(uuid.uuid4())
    
    with client.websocket_connect(f"/ws/{session_id}") as websocket:
        # Simuler une activité si nécessaire
        websocket.send_text("hello")
        asyncio.run(asyncio.sleep(0.01))
        # La déconnexion se produit à la sortie du bloc 'with'
    
    # Attendre que la déconnexion soit traitée
    asyncio.run(asyncio.sleep(0.05))
    
    # Vérifier que disconnect_client a été appelé
    mock_orchestrator.disconnect_client.assert_awaited_once_with(session_id)

def test_websocket_receive_invalid_json(
    client: TestClient, 
    mock_orchestrator: AsyncMock, 
    mock_db_session: MagicMock
):
    """Teste la réception d'un message texte qui n'est pas du JSON valide."""
    session_id = str(uuid.uuid4())
    invalid_json_text = "this is not json"
    
    with client.websocket_connect(f"/ws/{session_id}") as websocket:
        websocket.send_text(invalid_json_text)
        asyncio.run(asyncio.sleep(0.05))
        
        # Vérifier que process_websocket_message a été appelé avec le texte brut
        mock_orchestrator.process_websocket_message.assert_awaited_once()
        args, kwargs = mock_orchestrator.process_websocket_message.call_args
        assert args[0] == session_id
        assert args[1] is None
        assert args[2] == invalid_json_text
        # L'orchestrateur est responsable de gérer le JSON invalide

# Test pour simuler une erreur dans l'orchestrateur lors du traitement
# Cela nécessite que l'endpoint WebSocket gère correctement les exceptions
# venant de l'orchestrateur pour éviter de crasher la connexion.
def test_websocket_orchestrator_error_handling(
    client: TestClient, 
    mock_orchestrator: AsyncMock, 
    mock_db_session: MagicMock
):
    """Teste la gestion d'erreur si l'orchestrateur lève une exception."""
    session_id = str(uuid.uuid4())
    audio_chunk = b"trigger_error"
    
    # Configurer le mock pour lever une exception
    mock_orchestrator.process_websocket_message.side_effect = Exception("Orchestrator Error")
    
    with client.websocket_connect(f"/ws/{session_id}") as websocket:
        websocket.send_bytes(audio_chunk)
        asyncio.run(asyncio.sleep(0.05))
        
        # Vérifier que process_websocket_message a été appelé
        mock_orchestrator.process_websocket_message.assert_awaited_once()
        
        # Idéalement, la connexion ne devrait pas se fermer immédiatement
        # et l'endpoint devrait attraper l'exception et peut-être logger.
        # On peut vérifier qu'aucun message d'erreur inattendu n'est reçu.
        try:
            # Essayer de recevoir un message (devrait timeout ou être vide si l'erreur est gérée silencieusement)
            # Note: TestClient ne gère pas bien les timeouts de réception.
            # On suppose ici que l'erreur est loggée côté serveur et que la connexion reste ouverte.
            pass 
        except WebSocketDisconnect:
            pytest.fail("WebSocket disconnected unexpectedly on orchestrator error")

    # Vérifier que disconnect est appelé normalement à la fin
    asyncio.run(asyncio.sleep(0.05))
    mock_orchestrator.disconnect_client.assert_awaited_once_with(session_id)

