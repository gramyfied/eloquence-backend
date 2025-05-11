"""
Tests de connexion WebSocket utilisant le serveur d'écho de websocket.org.
Ces tests vérifient la fonctionnalité WebSocket de base sans dépendre de l'implémentation
spécifique de notre application.
"""

import pytest
import pytest_asyncio
import asyncio
import websockets
import json
import uuid
from typing import Optional

# URL du serveur d'écho WebSocket
ECHO_SERVER_URL = "wss://ws.postman-echo.com/raw"

@pytest.mark.asyncio
async def test_websocket_echo_text():
    """
    Teste l'envoi et la réception d'un message texte via WebSocket.
    """
    async with websockets.connect(ECHO_SERVER_URL) as websocket:
        # Générer un message unique pour éviter les faux positifs
        message_id = str(uuid.uuid4())
        message = f"Test message {message_id}"
        
        # Envoyer le message
        await websocket.send(message)
        
        # Recevoir la réponse (avec timeout pour éviter de bloquer indéfiniment)
        response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
        
        # Vérifier que la réponse est identique au message envoyé
        assert response == message, f"Le message reçu '{response}' ne correspond pas au message envoyé '{message}'"

@pytest.mark.asyncio
async def test_websocket_echo_json():
    """
    Teste l'envoi et la réception d'un message JSON via WebSocket.
    """
    async with websockets.connect(ECHO_SERVER_URL) as websocket:
        # Créer un message JSON
        message_id = str(uuid.uuid4())
        message = {
            "type": "test",
            "id": message_id,
            "content": "Test JSON message"
        }
        message_str = json.dumps(message)
        
        # Envoyer le message
        await websocket.send(message_str)
        
        # Recevoir la réponse
        response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
        
        # Vérifier que la réponse est identique au message envoyé
        assert response == message_str, f"Le message JSON reçu ne correspond pas au message envoyé"
        
        # Vérifier que la réponse peut être décodée en JSON
        response_json = json.loads(response)
        assert response_json["id"] == message_id, f"L'ID du message reçu ne correspond pas"

@pytest.mark.skip(reason="Le serveur d'écho de Postman ne prend pas en charge les messages binaires")
@pytest.mark.asyncio
async def test_websocket_echo_binary():
    """
    Teste l'envoi et la réception d'un message binaire via WebSocket.
    """
    async with websockets.connect(ECHO_SERVER_URL) as websocket:
        # Créer un message binaire
        binary_data = b"\x01\x02\x03\x04\x05"
        
        # Envoyer le message
        await websocket.send(binary_data)
        
        # Recevoir la réponse
        response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
        
        # Vérifier que la réponse est identique au message envoyé
        assert response == binary_data, f"Le message binaire reçu ne correspond pas au message envoyé"

@pytest.mark.asyncio
async def test_websocket_echo_multiple_messages():
    """
    Teste l'envoi et la réception de plusieurs messages consécutifs via WebSocket.
    """
    async with websockets.connect(ECHO_SERVER_URL) as websocket:
        # Envoyer plusieurs messages
        messages = [f"Message {i}" for i in range(5)]
        
        for message in messages:
            await websocket.send(message)
            
            # Recevoir la réponse immédiatement après chaque envoi
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            assert response == message, f"Le message reçu '{response}' ne correspond pas au message envoyé '{message}'"