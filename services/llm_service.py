"""
Service pour interagir avec les modèles de langage (LLM).
"""

import logging
import json
from typing import Dict, List, Optional, Any
import aiohttp

from core.config import settings
from core.latency_monitor import measure_latency, STEP_LLM_GENERATE

logger = logging.getLogger(__name__)

class LlmService:
    """
    Service pour interagir avec les modèles de langage (LLM).
    """
    def __init__(self):
        self.api_url = settings.LLM_API_URL
        # Utiliser LLM_API_KEY s'il existe, sinon None
        self.api_key = getattr(settings, 'LLM_API_KEY', None)
        self.model = settings.LLM_MODEL_NAME  # Utiliser LLM_MODEL_NAME au lieu de LLM_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
        self.timeout = aiohttp.ClientTimeout(total=settings.LLM_TIMEOUT_S)
        logger.info(f"Initialisation du service LLM avec API URL: {self.api_url}")

    @measure_latency(STEP_LLM_GENERATE)
    async def generate(self, prompt: str = None, context: Dict = None, history: List[Dict[str, str]] = None, is_interrupted: bool = False, scenario_context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Génère une réponse du LLM de manière asynchrone.
        Supporte deux interfaces:
        1. Avec prompt et context (interface utilisée par les routes)
        2. Avec history, is_interrupted et scenario_context (interface alternative)
        
        Retourne un dictionnaire avec 'text' et 'emotion'.
        """
        # Préparer les messages pour l'API
        messages = []
        
        # Construire le message système dynamique
        system_message_parts = [
            "Tu es un coach vocal interactif pour l'application Eloquence.",
            "Ton objectif est d'aider l'utilisateur à améliorer son expression orale en français."
        ]

        # Ajouter le contexte du scénario si disponible
        if scenario_context:
            system_message_parts.append(f"\n\nContexte du Scénario:")
            system_message_parts.append(f"- Nom du scénario: {scenario_context.get('name', 'N/A')}")
            system_message_parts.append(f"- Objectif du scénario: {scenario_context.get('goal', 'N/A')}")
            system_message_parts.append(f"- Étape actuelle: {scenario_context.get('current_step_name', 'N/A')} ({scenario_context.get('current_step', 'N/A')})")
            if scenario_context.get('current_step_description'):
                 system_message_parts.append(f"  Description de l'étape: {scenario_context['current_step_description']}")
            if scenario_context.get('is_final'):
                 system_message_parts.append(f"  Ceci est l'étape finale du scénario.")
            if scenario_context.get('variables'):
                 system_message_parts.append(f"  Variables du scénario: {json.dumps(scenario_context['variables'], ensure_ascii=False)}")
            if scenario_context.get('completed_steps'):
                 system_message_parts.append(f"  Étapes complétées: {', '.join(scenario_context['completed_steps'])}")
            if scenario_context.get('next_steps'):
                 system_message_parts.append(f"  Prochaines étapes possibles: {', '.join([step.get('name', step.get('id', 'N/A')) for step in scenario_context['next_steps']])}")
            
            # Ajouter des instructions spécifiques basées sur le prompt_template si présent
            if scenario_context.get('prompt_template'):
                 system_message_parts.append(f"\nInstructions spécifiques pour cette étape:\n{scenario_context['prompt_template']}")
                 
            # Ajouter des instructions pour la progression du scénario
            system_message_parts.append("\n\nSi l'utilisateur a satisfait les critères de l'étape actuelle ou si une transition est logique, propose une mise à jour du scénario dans ta réponse JSON.")
            system_message_parts.append("Le format JSON doit être inclus dans un bloc markdown comme ceci: ```json { \"scenario_updates\": { \"next_step\": \"id_de_la_prochaine_etape\", \"variables\": { \"nom_variable\": \"nouvelle_valeur\" } } } ```")
            system_message_parts.append("Tu peux mettre à jour l'étape ('next_step') et/ou les variables ('variables').")
            system_message_parts.append("Ne propose une mise à jour de l'étape que si l'utilisateur a clairement progressé ou terminé l'objectif de l'étape actuelle.")
            system_message_parts.append("Si l'étape actuelle est marquée comme 'is_final', ne propose pas de 'next_step'.")


        # Ajouter des instructions pour la gestion des interruptions
        if is_interrupted:
            system_message_parts.append("\n\nNote: L'utilisateur t'a interrompu. Adapte ta réponse pour reconnaître l'interruption et permettre à l'utilisateur de continuer.")
            system_message_parts.append("Sois concis et encourageant.")

        # Ajouter des instructions pour la génération d'émotions
        system_message_parts.append("\n\nPour chaque réponse, choisis une émotion appropriée parmi: neutre, encouragement, empathie, enthousiasme_modere, curiosite, reflexion.")
        system_message_parts.append("Indique l'émotion au début de ta réponse en utilisant le format [EMOTION: nom_emotion].")
        system_message_parts.append("Exemple: [EMOTION: encouragement] C'est une excellente idée, continuez !")

        system_message = " ".join(system_message_parts)
        messages.append({"role": "system", "content": system_message})

        # Ajouter l'historique de conversation
        if history:
            for msg in history:
                # S'assurer que le rôle est valide pour l'API (user/assistant)
                role = "user" if msg["role"] == "user" else "assistant"
                messages.append({"role": role, "content": msg["content"]})
        # Si pas d'historique mais un prompt initial, l'ajouter
        elif prompt:
            messages.append({"role": "user", "content": prompt})

        # Préparer les headers et le payload
        headers = {
            "Content-Type": "application/json"
        }
        
        # Ajouter l'en-tête d'autorisation si une clé API est disponible
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
        
        try:
            # Créer une session HTTP asynchrone
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                # Faire la requête POST
                async with session.post(self.api_url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Erreur LLM {response.status}: {error_text}")
                        return {"text": f"Erreur du service LLM: {response.status}", "emotion": "neutre"}
                    
                    # Traiter la réponse
                    response_json = await response.json()
                    
                    # Extraire le texte de la réponse
                    content = response_json.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if not content:
                        logger.error(f"Format de réponse LLM inattendu: {response_json}")
                        return {"text": "Erreur: format de réponse inattendu", "emotion": "neutre"}
                    
                    # Extraire l'émotion du texte (si présente)
                    emotion = "neutre"  # Valeur par défaut
                    emotion_markers = ["[EMOTION:", "[ÉMOTION:"]
                    for marker in emotion_markers:
                        if marker in content:
                            start_idx = content.find(marker)
                            end_idx = content.find("]", start_idx)
                            if end_idx > start_idx:
                                emotion_text = content[start_idx + len(marker):end_idx].strip()
                                emotion = emotion_text
                                # Supprimer le tag d'émotion du texte
                                content = content[:start_idx].strip() + content[end_idx + 1:].strip()
                                break
                    
                    return {"text": content, "emotion": emotion}
        except aiohttp.ClientError as e:
            logger.error(f"Erreur de connexion au service LLM: {e}")
            return {"text": f"Erreur de connexion au service LLM: {str(e)}", "emotion": "neutre"}
        except Exception as e:
            logger.error(f"Erreur lors de la génération LLM: {e}")
            return {"text": f"Erreur du service LLM: {str(e)}", "emotion": "neutre"}

    async def generate_exercise_text(self, exercise_type: str, topic: Optional[str] = None, difficulty: Optional[str] = "moyen", length: Optional[str] = "court") -> str:
        """
        Génère le texte pour un exercice de coaching en utilisant le LLM.

        Args:
            exercise_type (str): Type d'exercice (ex: "présentation", "entretien d'embauche").
            topic (Optional[str]): Sujet de l'exercice.
            difficulty (Optional[str]): Difficulté de l'exercice ("facile", "moyen", "difficile").
            length (Optional[str]): Longueur souhaitée du texte ("court", "moyen", "long").

        Returns:
            str: Le texte généré pour l'exercice.

        Raises:
            Exception: Si la génération échoue.
        """
        logger.info(f"Appel LLM pour générer un exercice: type={exercise_type}, topic={topic}, difficulty={difficulty}, length={length}")

        # Construire le prompt pour la génération d'exercice
        exercise_prompt_parts = [
            "Génère un texte pour un exercice de coaching vocal.",
            f"Type d'exercice: {exercise_type}.",
            f"Difficulté: {difficulty}.",
            f"Longueur: {length}."
        ]
        if topic:
            exercise_prompt_parts.append(f"Sujet: {topic}.")

        exercise_prompt = " ".join(exercise_prompt_parts)

        # Préparer les messages pour l'API
        messages = [
            {"role": "system", "content": "Tu es un générateur de texte pour des exercices de coaching vocal. Ton objectif est de créer des textes pertinents et adaptés aux paramètres demandés."},
            {"role": "user", "content": exercise_prompt}
        ]

        headers = {
            "Content-Type": "application/json"
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7, # Température spécifique pour la créativité de l'exercice
            "max_tokens": 500 # Limiter la longueur de l'exercice
        }

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(self.api_url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Erreur API LLM pour génération d'exercice {response.status}: {error_text}")
                        raise Exception(f"Erreur du service LLM lors de la génération d'exercice: {response.status}")

                    response_json = await response.json()
                    content = response_json.get("choices", [{}])[0].get("message", {}).get("content", "")

                    if not content:
                        logger.error(f"Format de réponse LLM inattendu pour génération d'exercice: {response_json}")
                        raise Exception("Erreur: format de réponse LLM inattendu pour génération d'exercice")

                    logger.info(f"Texte d'exercice généré (début): '{content[:100]}...'")
                    return content.strip()

        except aiohttp.ClientError as e:
            logger.error(f"Erreur de connexion au service LLM pour génération d'exercice: {e}")
            raise Exception(f"Erreur de connexion au service LLM pour génération d'exercice: {str(e)}")
        except Exception as e:
            logger.error(f"Erreur lors de la génération de l'exercice LLM: {e}")
            raise Exception(f"Erreur du service LLM lors de la génération d'exercice: {str(e)}")
