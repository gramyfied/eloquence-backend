#!/usr/bin/env python3
"""
Script de test pour vérifier que l'API Eloquence fonctionne correctement
avec les anciens endpoints.
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
    """Classe pour tester l'API Eloquence avec les anciens endpoints."""
    
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
    
    def test_get_scenarios(self):
        """Teste la récupération des scénarios."""
        logger.info("Test de récupération des scénarios...")
        try:
            response = requests.get(f"{self.api_url}/api/scenarios/?language=fr")
            if response.status_code == 200:
                scenarios = response.json()
                logger.info(f"✅ Scénarios récupérés avec succès: {len(scenarios)} scénarios")
                for scenario in scenarios:
                    logger.info(f"  - {scenario['id']}: {scenario['name']}")
                return True, scenarios
            else:
                logger.error(f"❌ Erreur lors de la récupération des scénarios: {response.status_code}")
                logger.error(f"Réponse: {response.text}")
                return False, None
        except Exception as e:
            logger.error(f"❌ Erreur lors de la récupération des scénarios: {e}")
            return False, None
    
    def test_create_session(self, scenario_id="coaching_adaptatif"):
        """Teste la création d'une session avec l'ancien endpoint."""
        logger.info(f"Test de création d'une session (ancien endpoint) avec scénario '{scenario_id}'...")
        try:
            response = requests.post(
                f"{self.api_url}/api/session/start",
                headers={
                    "Content-Type": "application/json"
                },
                json={
                    "user_id": f"test-user-{scenario_id}",
                    "language": "fr",
                    "scenario_id": scenario_id,
                    "is_multi_agent": False
                }
            )
            
            if response.status_code == 200:
                session_data = response.json()
                logger.info(f"✅ Session créée avec succès: {session_data}")
                
                # Vérifier que la réponse contient les champs attendus
                if "session_id" in session_data:
                    return True, session_data
                else:
                    logger.error(f"❌ Champ 'session_id' manquant dans la réponse")
                    return False, None
            else:
                logger.error(f"❌ Erreur lors de la création de la session: {response.status_code}")
                logger.error(f"Réponse: {response.text}")
                return False, None
        except Exception as e:
            logger.error(f"❌ Erreur lors de la création de la session: {e}")
            return False, None
    
    def test_end_session(self, session_id):
        """Teste la terminaison d'une session avec l'ancien endpoint."""
        logger.info(f"Test de terminaison de la session {session_id} (ancien endpoint)...")
        try:
            response = requests.post(
                f"{self.api_url}/api/session/{session_id}/end",
                headers={
                    "Content-Type": "application/json"
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
    
    def test_get_livekit_token(self):
        """Teste la récupération d'un token LiveKit."""
        logger.info("Test de récupération d'un token LiveKit...")
        try:
            # Utiliser les bons paramètres pour l'endpoint LiveKit token
            response = requests.post(
                f"{self.api_url}/livekit/token",
                headers={
                    "Content-Type": "application/json"
                },
                json={
                    "room_name": "test-room",
                    "participant_identity": "test-user"
                }
            )
            
            if response.status_code == 200:
                token_data = response.json()
                logger.info(f"✅ Token LiveKit récupéré avec succès: {token_data}")
                return True
            else:
                logger.error(f"❌ Erreur lors de la récupération du token LiveKit: {response.status_code}")
                logger.error(f"Réponse: {response.text}")
                return False
        except Exception as e:
            logger.error(f"❌ Erreur lors de la récupération du token LiveKit: {e}")
            return False
    
    def run_all_tests(self):
        """Exécute tous les tests."""
        logger.info("Exécution de tous les tests...")
        
        # Test de l'endpoint racine
        root_ok = self.test_api_root()
        
        # Test de récupération des scénarios
        scenarios_ok, scenarios = self.test_get_scenarios()
        
        # Déterminer un scénario valide
        scenario_id = "coaching_adaptatif"
        if scenarios_ok and scenarios:
            scenario_id = scenarios[0]["id"]
        
        # Test de récupération d'un token LiveKit
        token_ok = self.test_get_livekit_token()
        
        # Test de création de session
        create_ok, session_data = self.test_create_session(scenario_id)
        
        # Test de terminaison de session (seulement si la création a réussi)
        end_ok = False
        if create_ok and session_data and "session_id" in session_data:
            session_id = session_data["session_id"]
            end_ok = self.test_end_session(session_id)
        else:
            logger.warning("⚠️ Test de terminaison de session ignoré car la création a échoué")
        
        # Résumé des tests
        logger.info("=== Résumé des Tests ===")
        logger.info(f"Endpoint racine: {'✅ OK' if root_ok else '❌ ÉCHEC'}")
        logger.info(f"Récupération des scénarios: {'✅ OK' if scenarios_ok else '❌ ÉCHEC'}")
        logger.info(f"Token LiveKit: {'✅ OK' if token_ok else '❌ ÉCHEC'}")
        logger.info(f"Création de session: {'✅ OK' if create_ok else '❌ ÉCHEC'}")
        logger.info(f"Terminaison de session: {'✅ OK' if end_ok else '❌ ÉCHEC'}")
        
        return root_ok and scenarios_ok and token_ok and create_ok and end_ok

def main():
    """Fonction principale."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test de l'API Eloquence avec les anciens endpoints")
    parser.add_argument("--api-url", help="URL de l'API")
    parser.add_argument("--api-key", help="Clé API")
    parser.add_argument("--test", choices=["all", "root", "scenarios", "token", "create", "end"], default="all", help="Test à exécuter")
    parser.add_argument("--scenario-id", help="ID du scénario à utiliser pour les tests", default="coaching_adaptatif")
    args = parser.parse_args()
    
    tester = ApiTester(
        api_url=args.api_url,
        api_key=args.api_key
    )
    
    if args.test == "all":
        success = tester.run_all_tests()
    elif args.test == "root":
        success = tester.test_api_root()
    elif args.test == "scenarios":
        success, _ = tester.test_get_scenarios()
    elif args.test == "token":
        success = tester.test_get_livekit_token()
    elif args.test == "create":
        success, _ = tester.test_create_session(args.scenario_id)
    elif args.test == "end":
        # Pour tester uniquement la terminaison, nous devons d'abord créer une session
        create_ok, session_data = tester.test_create_session(args.scenario_id)
        if create_ok and session_data and "session_id" in session_data:
            session_id = session_data["session_id"]
            success = tester.test_end_session(session_id)
        else:
            logger.error("❌ Impossible de tester la terminaison car la création a échoué")
            success = False
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()