#!/usr/bin/env python3
"""
Script de test pour le service ASR (Speech-to-Text).
"""

import asyncio
import logging
import sys
import os

# Configurer le logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ajouter le répertoire courant au PYTHONPATH
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.asr_service import AsrService

async def test_asr():
    """Teste le service ASR avec un fichier audio."""
    logger.info("Initialisation du service ASR...")
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

if __name__ == "__main__":
    asyncio.run(test_asr())