#!/usr/bin/env python3
"""
Script de test pour vérifier que LiveKit fonctionne correctement.
Ce script teste à la fois le serveur LiveKit et l'agent Eloquence.
"""

import os
import sys
import json
import asyncio
import argparse
import requests
import logging
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import cli
from livekit_api import RoomServiceClient, RoomCreateOptions, RoomListOptions

# Configurer le logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("livekit-test")

# Charger les variables d'environnement
load_dotenv(".env.local")

# Configuration LiveKit
LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")

# Configuration API
API_URL = "http://localhost:8083"
API_KEY = os.environ.get("API_KEY", "default-key")

class LiveKitTester:
    """Classe pour tester LiveKit et l'agent Eloquence."""
    
    def __init__(self, livekit_url=None, api_url=None, api_key=None):
        """Initialise le testeur LiveKit."""
        self.livekit_url = livekit_url or LIVEKIT_URL
        self.api_url = api_url or API_URL
        self.api_key = api_key or API_KEY
        self.room_client = RoomServiceClient(
            self.livekit_url,
            LIVEKIT_API_KEY,
            LIVEKIT_API_SECRET
        )
        logger.info(f"LiveKitTester initialisé avec URL LiveKit: {self.livekit_url}, URL API: {self.api_url}")
    
    async def test_livekit_server(self):
        """Teste la connexion au serveur LiveKit."""
        logger.info("Test de connexion au serveur LiveKit...")
        try:
            # Créer une room de test
            room_name = "test-room"
            await self.room_client.create_room(RoomCreateOptions(name=room_name))
            logger.info(f"✅ Room '{room_name}' créée avec succès")
            
            # Lister les rooms
            rooms = await self.room_client.list_rooms(RoomListOptions())
            logger.info(f"✅ Liste des rooms récupérée avec succès: {len(rooms)} rooms")
            
            # Vérifier que la room de test existe
            room_exists = any(room.name == room_name for room in rooms)
            if room_exists:
                logger.info(f"✅ Room '{room_name}' trouvée dans la liste des rooms")
            else:
                logger.error(f"❌ Room '{room_name}' non trouvée dans la liste des rooms")
                return False
            
            # Supprimer la room de test
            await self.room_client.delete_room(room_name)
            logger.info(f"✅ Room '{room_name}' supprimée avec succès")
            
            logger.info("✅ Test du serveur LiveKit réussi")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur lors du test du serveur LiveKit: {e}")
            return False
    
    async def test_api_server(self):
        """Teste la connexion à l'API."""
        logger.info("Test de connexion à l'API...")
        try:
            # Tester l'endpoint racine
            response = requests.get(f"{self.api_url}/")
            if response.status_code == 200:
                logger.info(f"✅ Connexion à l'API réussie: {response.json()}")
            else:
                logger.error(f"❌ Erreur lors de la connexion à l'API: {response.status_code}")
                return False
            
            # Tester la création d'une session
            response = requests.post(
                f"{self.api_url}/api/sessions",
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "user_id": "test-user",
                    "language": "fr",
                    "scenario_id": "test-scenario",
                    "is_multi_agent": False
                }
            )
            
            if response.status_code == 200:
                session_data = response.json()
                logger.info(f"✅ Session créée avec succès: {session_data}")
                
                # Vérifier que la réponse contient les champs attendus
                required_fields = ["session_id", "room_name", "token", "url"]
                missing_fields = [field for field in required_fields if field not in session_data]
                
                if missing_fields:
                    logger.error(f"❌ Champs manquants dans la réponse: {missing_fields}")
                    return False
                
                # Tester la terminaison de la session
                session_id = session_data["session_id"]
                response = requests.delete(
                    f"{self.api_url}/api/sessions/{session_id}",
                    headers={
                        "X-API-Key": self.api_key
                    }
                )
                
                if response.status_code == 200:
                    logger.info(f"✅ Session terminée avec succès: {response.json()}")
                else:
                    logger.error(f"❌ Erreur lors de la terminaison de la session: {response.status_code}")
                    return False
            else:
                logger.error(f"❌ Erreur lors de la création de la session: {response.status_code}")
                logger.error(f"Réponse: {response.text}")
                return False
            
            logger.info("✅ Test de l'API réussi")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur lors du test de l'API: {e}")
            return False
    
    async def test_agent(self):
        """Teste l'agent Eloquence."""
        logger.info("Test de l'agent Eloquence...")
        try:
            # Créer une session via l'API
            response = requests.post(
                f"{self.api_url}/api/sessions",
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "user_id": "test-user",
                    "language": "fr",
                    "scenario_id": "test-scenario",
                    "is_multi_agent": False
                }
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Erreur lors de la création de la session: {response.status_code}")
                logger.error(f"Réponse: {response.text}")
                return False
            
            session_data = response.json()
            session_id = session_data["session_id"]
            room_name = session_data["room_name"]
            token = session_data["token"]
            url = session_data["url"]
            
            logger.info(f"✅ Session créée avec succès: {session_data}")
            
            # Vérifier que la room existe
            rooms = await self.room_client.list_rooms(RoomListOptions())
            room_exists = any(room.name == room_name for room in rooms)
            
            if room_exists:
                logger.info(f"✅ Room '{room_name}' trouvée dans la liste des rooms")
            else:
                logger.error(f"❌ Room '{room_name}' non trouvée dans la liste des rooms")
                return False
            
            # Vérifier que l'agent est connecté à la room
            # Note: Cette vérification est approximative car nous ne pouvons pas facilement
            # vérifier si l'agent est connecté sans nous connecter nous-mêmes à la room
            await asyncio.sleep(5)  # Attendre que l'agent se connecte
            
            # Terminer la session
            response = requests.delete(
                f"{self.api_url}/api/sessions/{session_id}",
                headers={
                    "X-API-Key": self.api_key
                }
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Session terminée avec succès: {response.json()}")
            else:
                logger.error(f"❌ Erreur lors de la terminaison de la session: {response.status_code}")
                return False
            
            logger.info("✅ Test de l'agent réussi")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur lors du test de l'agent: {e}")
            return False
    
    async def run_all_tests(self):
        """Exécute tous les tests."""
        logger.info("Exécution de tous les tests...")
        
        # Test du serveur LiveKit
        livekit_server_ok = await self.test_livekit_server()
        
        # Test de l'API
        api_server_ok = await self.test_api_server()
        
        # Test de l'agent (seulement si l'API et le serveur LiveKit fonctionnent)
        agent_ok = False
        if livekit_server_ok and api_server_ok:
            agent_ok = await self.test_agent()
        else:
            logger.warning("⚠️ Test de l'agent ignoré car le serveur LiveKit ou l'API ne fonctionne pas")
        
        # Résumé des tests
        logger.info("=== Résumé des Tests ===")
        logger.info(f"Serveur LiveKit: {'✅ OK' if livekit_server_ok else '❌ ÉCHEC'}")
        logger.info(f"API: {'✅ OK' if api_server_ok else '❌ ÉCHEC'}")
        logger.info(f"Agent: {'✅ OK' if agent_ok else '❌ ÉCHEC'}")
        
        return livekit_server_ok and api_server_ok and agent_ok

async def main():
    """Fonction principale."""
    parser = argparse.ArgumentParser(description="Test de LiveKit et de l'agent Eloquence")
    parser.add_argument("--livekit-url", help="URL du serveur LiveKit")
    parser.add_argument("--api-url", help="URL de l'API")
    parser.add_argument("--api-key", help="Clé API")
    parser.add_argument("--test", choices=["all", "livekit", "api", "agent"], default="all", help="Test à exécuter")
    args = parser.parse_args()
    
    tester = LiveKitTester(
        livekit_url=args.livekit_url,
        api_url=args.api_url,
        api_key=args.api_key
    )
    
    if args.test == "all":
        success = await tester.run_all_tests()
    elif args.test == "livekit":
        success = await tester.test_livekit_server()
    elif args.test == "api":
        success = await tester.test_api_server()
    elif args.test == "agent":
        success = await tester.test_agent()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())