#!/usr/bin/env python3
"""
Script de test pour vérifier que l'API Eloquence fonctionne correctement.
"""

import os
import sys
import json
import requests
import logging
from dotenv import load_dotenv

# Configurer le logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("api-test")

# Charger les variables d'environnement
load_dotenv(".env.local")

# Configuration API
API_URL = os.environ.get("API_URL", "http://localhost:8083")
API_KEY = os.environ.get("API_KEY", "default-key")

class ApiTester:
    """Classe pour tester l'API Eloquence."""
    
    def __init__(self, api_url=None, api_key=None):
        """Initialise le testeur d'API."""
        self.api_url = api_url or API_URL
        self.api_key = api_key or API_KEY
        logger.info(f"ApiTester initialisé avec URL API: {self.api_url}")
    
    def test_api_root(self):
        """Teste l'endpoint racine de l'API."""
        logger.info("Test de l'endpoint racine de l'API...")
        try:
            response = requests.get(f"{self.api_url}/")
            if response.status_code == 200:
                logger.info(f"✅ Connexion à l'API réussie: {response.text}")
                return True
            else:
                logger.error(f"❌ Erreur lors de la connexion à l'API: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ Erreur lors du test de l'API: {e}")
            return False
    
    def test_create_session(self):
        """Teste la création d'une session."""
        logger.info("Test de création d'une session...")
        try:
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
                    return False, None
                
                return True, session_data
            else:
                logger.error(f"❌ Erreur lors de la création de la session: {response.status_code}")
                logger.error(f"Réponse: {response.text}")
                return False, None
        except Exception as e:
            logger.error(f"❌ Erreur lors de la création de la session: {e}")
            return False, None
    
    def test_end_session(self, session_id):
        """Teste la terminaison d'une session."""
        logger.info(f"Test de terminaison de la session {session_id}...")
        try:
            response = requests.delete(
                f"{self.api_url}/api/sessions/{session_id}",
                headers={
                    "X-API-Key": self.api_key
                }
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Session terminée avec succès: {response.json()}")
                return True
            else:
                logger.error(f"❌ Erreur lors de la terminaison de la session: {response.status_code}")
                logger.error(f"Réponse: {response.text}")
                return False
        except Exception as e:
            logger.error(f"❌ Erreur lors de la terminaison de la session: {e}")
            return False
    
    def run_all_tests(self):
        """Exécute tous les tests."""
        logger.info("Exécution de tous les tests...")
        
        # Test de l'endpoint racine
        root_ok = self.test_api_root()
        
        # Test de création de session
        create_ok, session_data = self.test_create_session()
        
        # Test de terminaison de session (seulement si la création a réussi)
        end_ok = False
        if create_ok and session_data:
            session_id = session_data["session_id"]
            end_ok = self.test_end_session(session_id)
        else:
            logger.warning("⚠️ Test de terminaison de session ignoré car la création a échoué")
        
        # Résumé des tests
        logger.info("=== Résumé des Tests ===")
        logger.info(f"Endpoint racine: {'✅ OK' if root_ok else '❌ ÉCHEC'}")
        logger.info(f"Création de session: {'✅ OK' if create_ok else '❌ ÉCHEC'}")
        logger.info(f"Terminaison de session: {'✅ OK' if end_ok else '❌ ÉCHEC'}")
        
        return root_ok and create_ok and end_ok

def main():
    """Fonction principale."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test de l'API Eloquence")
    parser.add_argument("--api-url", help="URL de l'API")
    parser.add_argument("--api-key", help="Clé API")
    parser.add_argument("--test", choices=["all", "root", "create", "end"], default="all", help="Test à exécuter")
    args = parser.parse_args()
    
    tester = ApiTester(
        api_url=args.api_url,
        api_key=args.api_key
    )
    
    if args.test == "all":
        success = tester.run_all_tests()
    elif args.test == "root":
        success = tester.test_api_root()
    elif args.test == "create":
        success, _ = tester.test_create_session()
    elif args.test == "end":
        # Pour tester uniquement la terminaison, nous devons d'abord créer une session
        create_ok, session_data = tester.test_create_session()
        if create_ok and session_data:
            session_id = session_data["session_id"]
            success = tester.test_end_session(session_id)
        else:
            logger.error("❌ Impossible de tester la terminaison car la création a échoué")
            success = False
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()