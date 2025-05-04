import asyncio
import os
from dotenv import load_dotenv

# Charger les variables d'environnement depuis .env
load_dotenv()

# Ajouter le répertoire parent au path pour pouvoir importer les modules de l'application
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from services.llm_service import LlmService
from core.config import settings

async def main():
    # Assurez-vous que la clé API Scaleway est définie dans votre fichier .env
    if not settings.SCW_LLM_API_KEY:
        print("Erreur : La variable d'environnement SCW_LLM_API_KEY n'est pas définie.")
        print("Veuillez l'ajouter à votre fichier .env à la racine du répertoire eloquence_backend_py.")
        return

    llm_service = LlmService()

    print(f"Test de la génération LLM avec Scaleway Mistral ({llm_service.model_name})...")

    history = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Quelle est la capitale de la France ?"}
    ]

    try:
        # Appeler la méthode generate qui utilise le streaming
        response = await llm_service.generate(history)

        print("\nRéponse reçue :")
        print(f"Texte : {response.get('text_response')}")
        print(f"Émotion : {response.get('emotion_label')}")
        if "scenario_updates" in response:
            print(f"Mises à jour de scénario : {response.get('scenario_updates')}")

    except Exception as e:
        print(f"\nUne erreur est survenue lors de l'appel à l'API Scaleway : {e}")

if __name__ == "__main__":
    asyncio.run(main())
