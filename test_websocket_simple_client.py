#!/usr/bin/env python3
"""
Script de test simple pour vérifier la connexion WebSocket avec le backend FastAPI.
Utilise le module websocket-client qui est peut-être déjà installé.
"""

import json
import logging
import sys
import time
import websocket

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def on_message(ws, message):
    """Callback pour les messages reçus"""
    logger.info(f"✅ Message reçu: {message}")
    
    # Tenter de parser le message JSON
    try:
        data = json.loads(message)
        logger.info(f"✅ Message JSON valide: {data}")
    except json.JSONDecodeError:
        logger.warning(f"⚠️ Le message n'est pas un JSON valide")

def on_error(ws, error):
    """Callback pour les erreurs"""
    logger.error(f"❌ Erreur: {error}")

def on_close(ws, close_status_code, close_msg):
    """Callback pour la fermeture de la connexion"""
    logger.info(f"❌ Connexion fermée: {close_status_code} - {close_msg}")

def on_open(ws):
    """Callback pour l'ouverture de la connexion"""
    logger.info("✅ Connexion établie!")
    
    # Envoyer un message texte
    message = {
        "type": "text",
        "content": "Test message from simple client"
    }
    ws.send(json.dumps(message))
    logger.info(f"✅ Message envoyé: {message}")

def main():
    """Fonction principale"""
    # URI par défaut
    session_id = "c320c269-9bfd-48c6-beea-7bdddf43a441"
    uri = f"ws://localhost:8083/ws/simple/{session_id}"
    
    logger.info(f"Test de connexion WebSocket à {uri}")
    
    # Activer le mode debug pour voir les détails de la connexion
    websocket.enableTrace(True)
    
    # Créer une connexion WebSocket
    ws = websocket.WebSocketApp(
        uri,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    
    # Démarrer la connexion
    ws.run_forever()

if __name__ == "__main__":
    main()