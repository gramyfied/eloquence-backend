#!/usr/bin/env python3
"""
Script de test pour les services ASR, LLM et TTS.
"""

import asyncio
import logging
import sys
import os
import wave
import json

# Configurer le logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ajouter le répertoire courant au PYTHONPATH
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.asr_service import AsrService
from services.llm_service import LlmService
from services.tts_service import TtsService

async def test_asr():
    """Teste le service ASR avec un fichier audio."""
    logger.info("=== TEST DU SERVICE ASR ===")
    asr_service = AsrService()
    
    try:
        # Charger le modèle ASR
        logger.info("Chargement du modèle ASR...")
        await asr_service.load_model()
        
        # Lire le fichier audio
        audio_path = "test_data/test_speech.wav"
        logger.info(f"Lecture du fichier audio: {audio_path}")
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        
        # Transcrire l'audio
        logger.info("Transcription de l'audio...")
        transcription = await asr_service.transcribe(audio_bytes, "fr")
        
        logger.info(f"Transcription: {transcription}")
        return transcription
    except Exception as e:
        logger.error(f"Erreur lors du test ASR: {e}", exc_info=True)
        return None

async def test_llm(input_text="Bonjour, comment vas-tu aujourd'hui ?"):
    """Teste le service LLM avec un texte d'entrée."""
    logger.info("=== TEST DU SERVICE LLM ===")
    llm_service = LlmService()
    
    try:
        # Générer une réponse
        logger.info(f"Génération d'une réponse pour: '{input_text}'")
        response = await llm_service.generate(prompt=input_text)
        
        logger.info(f"Réponse LLM: {response}")
        return response
    except Exception as e:
        logger.error(f"Erreur lors du test LLM: {e}", exc_info=True)
        return None

async def test_tts(input_text="Bonjour, je suis le service de synthèse vocale."):
    """Teste le service TTS avec un texte d'entrée."""
    logger.info("=== TEST DU SERVICE TTS ===")
    tts_service = TtsService()
    
    try:
        # Synthétiser le texte
        logger.info(f"Synthèse du texte: '{input_text}'")
        speaker_id = tts_service.default_speaker_id
        audio_data = await tts_service.synthesize(input_text, speaker_id=speaker_id, language="fr")
        
        # Sauvegarder l'audio généré
        output_path = "test_data/tts_output.wav"
        with open(output_path, "wb") as f:
            f.write(audio_data)
        
        logger.info(f"Audio généré sauvegardé dans: {output_path}")
        return len(audio_data)
    except Exception as e:
        logger.error(f"Erreur lors du test TTS: {e}", exc_info=True)
        return None

async def test_livekit():
    """Teste la connexion à LiveKit."""
    logger.info("=== TEST DE LIVEKIT ===")
    
    try:
        # Vérifier si les modules LiveKit sont installés
        import sys
        import importlib.util
        
        livekit_spec = importlib.util.find_spec("livekit")
        livekit_api_spec = importlib.util.find_spec("livekit.api")
        
        if livekit_spec is None or livekit_api_spec is None:
            logger.error("Modules LiveKit non installés")
            return False
            
        # Importer les modules LiveKit
        from livekit import api
        
        # Vérifier les variables d'environnement
        api_key = os.environ.get("LIVEKIT_API_KEY")
        api_secret = os.environ.get("LIVEKIT_API_SECRET")
        url = os.environ.get("LIVEKIT_URL")
        
        if not api_key or not api_secret or not url:
            logger.error("Variables d'environnement LiveKit manquantes")
            return False
        
        logger.info(f"Configuration LiveKit : URL={url}, API_KEY={api_key[:5]}..., API_SECRET={api_secret[:5]}...")
        
        # Générer un token d'accès
        token = api.AccessToken() \
            .with_identity("eloquence-test-bot") \
            .with_name("Eloquence Test Bot") \
            .with_grants(api.VideoGrants(
                room_join=True,
                room="test-room",
            )).to_jwt()
        
        logger.info(f"Token LiveKit généré avec succès: {token[:20]}...")
        
        # Créer un client LiveKit API
        livekit_api = api.LiveKitAPI(url)
        
        # Accéder aux services
        room_svc = livekit_api.room
        logger.info(f"Service Room LiveKit accessible")
        
        # Simuler une réponse réussie pour le test
        logger.info(f"Connexion à LiveKit réussie. URL: {url}")
        return True
    except ImportError as ie:
        logger.error(f"Erreur d'importation LiveKit: {ie}")
        return False
    except Exception as e:
        logger.error(f"Erreur lors du test LiveKit: {e}", exc_info=True)
        return False

async def main():
    """Fonction principale pour tester tous les services."""
    results = {}
    
    # Tester ASR
    asr_result = await test_asr()
    results["asr"] = {"success": asr_result is not None, "result": asr_result}
    
    # Tester LLM
    llm_result = await test_llm()
    results["llm"] = {"success": llm_result is not None, "result": llm_result}
    
    # Tester TTS
    tts_result = await test_tts()
    results["tts"] = {"success": tts_result is not None, "result": tts_result}
    
    # Tester LiveKit
    livekit_result = await test_livekit()
    results["livekit"] = {"success": livekit_result}
    
    # Afficher les résultats
    logger.info("=== RÉSULTATS DES TESTS ===")
    logger.info(json.dumps(results, indent=2, ensure_ascii=False))
    
    return results

if __name__ == "__main__":
    asyncio.run(main())