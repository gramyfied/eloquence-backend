#!/usr/bin/env python3
"""
Script de test pour vérifier la connexion WebSocket avec le backend FastAPI
et tester l'envoi d'audio et la réception de la réponse TTS.
"""

import json
import logging
import sys
import time
import asyncio
import websocket
import wave
import os
import uuid
from threading import Thread

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Chemin vers un fichier audio de test (WAV 16kHz mono)
# Remplacer par le chemin d'un fichier audio de test si disponible
AUDIO_FILE = "test_audio.wav"

# Créer un fichier audio de test si nécessaire
def create_test_audio():
    if os.path.exists(AUDIO_FILE):
        return
    
    # Créer un fichier WAV vide de 2 secondes (silence)
    with wave.open(AUDIO_FILE, 'wb') as wf:
        wf.setnchannels(1)  # Mono
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(16000)  # 16kHz
        # 2 secondes de silence (valeurs à zéro)
        wf.writeframes(b'\x00\x00' * 16000 * 2)
    
    logger.info(f"Fichier audio de test créé: {AUDIO_FILE}")

# Lire le fichier audio
def read_audio_file():
    with open(AUDIO_FILE, 'rb') as f:
        return f.read()

# Callbacks WebSocket
def on_message(ws, message):
    """Callback pour les messages reçus"""
    try:
        # Essayer de décoder comme JSON
        if isinstance(message, str):
            logger.info(f"✅ Message texte reçu: {message}")
            data = json.loads(message)
            logger.info(f"✅ Message JSON valide: {data}")
            
            # Si c'est un message de contrôle audio, on peut réagir
            if data.get("type") == "audio_control":
                if data.get("event") == "ia_speech_end":
                    logger.info("🔊 Fin de la parole de l'IA")
        else:
            # C'est probablement un message binaire (audio)
            logger.info(f"✅ Message binaire reçu: {len(message)} bytes")
            logger.info("🔊 Audio de l'IA reçu")
    except json.JSONDecodeError:
        logger.warning(f"⚠️ Le message n'est pas un JSON valide")
    except Exception as e:
        logger.error(f"❌ Erreur lors du traitement du message: {e}")

def on_error(ws, error):
    """Callback pour les erreurs"""
    logger.error(f"❌ Erreur: {error}")

def on_close(ws, close_status_code, close_msg):
    """Callback pour la fermeture de la connexion"""
    logger.info(f"❌ Connexion fermée: {close_status_code} - {close_msg}")

def on_open(ws):
    """Callback pour l'ouverture de la connexion"""
    logger.info("✅ Connexion établie!")
    
    # Démarrer un thread pour envoyer l'audio après un court délai
    def run():
        time.sleep(1)  # Attendre 1 seconde
        
        # Envoyer un message de contrôle pour indiquer le début de la parole
        control_msg = {
            "type": "control",
            "event": "user_speech_start"
        }
        ws.send(json.dumps(control_msg))
        logger.info(f"✅ Message de contrôle envoyé: {control_msg}")
        
        # Lire et envoyer l'audio
        audio_data = read_audio_file()
        ws.send(audio_data, websocket.ABNF.OPCODE_BINARY)
        logger.info(f"✅ Audio envoyé: {len(audio_data)} bytes")
        
        # Attendre un peu
        time.sleep(0.5)
        
        # Envoyer un message de contrôle pour indiquer la fin de la parole
        control_msg = {
            "type": "control",
            "event": "user_speech_end"
        }
        ws.send(json.dumps(control_msg))
        logger.info(f"✅ Message de contrôle envoyé: {control_msg}")
    
    Thread(target=run).start()

async def main_async():
    """Fonction principale asynchrone"""
    # Créer un fichier audio de test si nécessaire
    create_test_audio()
    
    # Générer un ID de session unique
    session_id = str(uuid.uuid4())
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
    
    # Démarrer la connexion dans un thread séparé
    wst = Thread(target=ws.run_forever)
    wst.daemon = True
    wst.start()
    
    # Attendre que le test se termine
    await asyncio.sleep(30)  # Attendre 30 secondes maximum
    
    # Fermer la connexion
    ws.close()
    logger.info("Test terminé")

def main():
    """Point d'entrée principal"""
    asyncio.run(main_async())

if __name__ == "__main__":
    main()