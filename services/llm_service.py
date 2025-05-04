import asyncio
import logging
import json
from typing import List, Dict, Optional
import aiohttp

from core.config import settings

logger = logging.getLogger(__name__)

# Liste des émotions cibles pour le prompt LLM
TARGET_EMOTIONS = ["encouragement", "empathie", "neutre", "enthousiasme_modere", "curiosite", "reflexion"]

from services.conversation_memory import conversation_memory

class LlmService:
    """
    Service pour interagir avec le Large Language Model (LLM) via une API.
    Gère également la continuité de la conversation après les interruptions.
    """
    def __init__(self):
        # Utiliser l'URL locale pour vLLM/TGI par défaut
        self.api_url = settings.LLM_LOCAL_API_URL
        # self.api_key = settings.LLM_API_KEY # Non nécessaire pour API locale
        # self.model_name = settings.LLM_MODEL_NAME # Souvent non nécessaire dans le payload pour vLLM/TGI
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
        self.timeout = aiohttp.ClientTimeout(total=settings.LLM_TIMEOUT_S)
        # Supprimer self.model_name de la ligne de log car il n'est plus un attribut
        logger.info(f"Initialisation du service LLM avec API URL: {self.api_url}")

    def _build_prompt(self, history: List[Dict[str, str]], is_interrupted: bool, scenario_context: Optional[Dict] = None, session_id: Optional[str] = None) -> str:
        """
        Construit le prompt pour le LLM, en incluant le contexte du scénario si fourni.
        Gère également la continuité de la conversation après les interruptions.
        
        Args:
            history: Historique de la conversation
            is_interrupted: Indique si l'utilisateur a interrompu l'IA
            scenario_context: Contexte du scénario (optionnel)
            session_id: ID de la session (nécessaire pour la mémoire conversationnelle)
            
        Returns:
            str: Prompt pour le LLM
        """
        # Limiter l'historique pour ne pas dépasser les limites de contexte
        context_limit = 6 # Nombre de tours de parole (user + assistant) à inclure
        limited_history = history[-(context_limit * 2):] # Prend les derniers messages

        history_str = "\n".join(f"{msg['role']}: {msg['content']}" for msg in limited_history)

        # Contexte du scénario
        scenario_prompt_part = ""
        if scenario_context:
            scenario_name = scenario_context.get("name", "exercice")
            scenario_goal = scenario_context.get("goal", "améliorer son expression")
            current_step_id = scenario_context.get("current_step", "")
            current_step_name = scenario_context.get("current_step_name", "")
            current_step_description = scenario_context.get("current_step_description", "")
            prompt_template = scenario_context.get("prompt_template", "")
            variables = scenario_context.get("variables", {})
            
            # Remplacer les variables dans le template de prompt si disponible
            step_prompt = prompt_template
            if prompt_template and variables:
                for var_name, var_value in variables.items():
                    step_prompt = step_prompt.replace(f"{{{var_name}}}", str(var_value))
            
            scenario_prompt_part = (
                f"CONTEXTE SCÉNARIO: Nous sommes dans un scénario '{scenario_name}'.\n"
                f"OBJECTIF DU SCÉNARIO: {scenario_goal}.\n"
                f"ÉTAPE ACTUELLE: {current_step_name} ({current_step_id}).\n"
                f"DESCRIPTION DE L'ÉTAPE: {current_step_description}.\n"
            )
            
            # Ajouter le prompt spécifique à l'étape s'il est disponible
            if step_prompt:
                scenario_prompt_part += f"INSTRUCTIONS SPÉCIFIQUES: {step_prompt}\n"
            
            scenario_prompt_part += "Adapte ta réponse en fonction de ce contexte.\n\n"

        # Instruction système
        system_prompt = (
            f"Tu es un coach vocal interactif pour l'application Eloquence. Ton objectif est d'aider l'utilisateur à améliorer son expression orale en français. "
            f"Sois encourageant, patient et constructif. Limite tes réponses à 3-4 phrases maximum.\n\n"
            
            f"IMPORTANT: Termine TOUJOURS ta réponse par une étiquette d'émotion sur une nouvelle ligne, choisie parmi cette liste : {', '.join(TARGET_EMOTIONS)}. "
            f"Format: '[EMOTION: nom_emotion]'. Par exemple: '[EMOTION: encouragement]'.\n\n"
            
            f"Guide pour le choix de l'émotion:\n"
            f"- encouragement: Utilise cette émotion quand l'utilisateur a besoin de motivation ou après un progrès.\n"
            f"- empathie: Utilise cette émotion quand l'utilisateur exprime des difficultés ou des frustrations.\n"
            f"- neutre: Émotion par défaut pour les explications factuelles ou les instructions.\n"
            f"- enthousiasme_modere: Utilise cette émotion pour féliciter l'utilisateur ou exprimer de l'excitation.\n"
            f"- curiosite: Utilise cette émotion pour poser des questions ou encourager l'exploration.\n"
            f"- reflexion: Utilise cette émotion pour des moments de réflexion ou d'analyse approfondie.\n\n"
            
            f"Choisis l'émotion qui correspond le mieux au contenu et au contexte de ta réponse.\n\n"
        )
        
        # Ajouter les instructions spécifiques au scénario si un contexte est fourni
        if scenario_context:
            scenario_steps = scenario_context.get("steps", [])
            current_step = scenario_context.get("current_step", "")
            variables = scenario_context.get("variables", {})
            
            # Ajouter des instructions pour la mise à jour du scénario
            next_steps = scenario_context.get("next_steps", [])
            expected_variables = scenario_context.get("expected_variables", [])
            is_final = scenario_context.get("is_final", False)
            
            # Construire les instructions de mise à jour
            scenario_update_instructions = (
                f"Si tu estimes que l'utilisateur a terminé l'étape actuelle '{current_step_name}' ou si tu souhaites mettre à jour "
                f"des variables du scénario, tu peux inclure une mise à jour de scénario dans ta réponse.\n"
            )
            
            # Ajouter des instructions spécifiques pour les étapes suivantes
            if is_final:
                scenario_update_instructions += f"Cette étape est finale. Il n'y a pas d'étape suivante.\n"
            elif next_steps:
                scenario_update_instructions += (
                    f"Format pour la mise à jour: [SCENARIO_UPDATE: {{\"next_step\": \"id_étape\", \"variables\": {{\"var1\": \"valeur1\", ...}}}}]\n"
                    f"Étapes suivantes possibles: {next_steps}\n"
                )
            else:
                scenario_update_instructions += (
                    f"Format pour la mise à jour: [SCENARIO_UPDATE: {{\"next_step\": \"id_étape\", \"variables\": {{\"var1\": \"valeur1\", ...}}}}]\n"
                    f"Étapes disponibles: {scenario_context.get('steps', [])}\n"
                )
            
            # Ajouter des instructions pour les variables attendues
            if expected_variables:
                scenario_update_instructions += (
                    f"Variables attendues dans cette étape: {expected_variables}\n"
                    f"Essaie d'extraire ces variables des réponses de l'utilisateur.\n"
                )
            
            scenario_update_instructions += f"Variables actuelles: {json.dumps(variables, ensure_ascii=False)}\n\n"
            
            system_prompt += f"{scenario_prompt_part}{scenario_update_instructions}"
        
        # Ajouter l'historique de conversation
        system_prompt += f"Voici l'historique récent de la conversation:\n{history_str}\n\n"

        # Gérer les interruptions avec la mémoire conversationnelle
        if is_interrupted and session_id:
            # Récupérer le contexte de conversation précédent
            conv_context = conversation_memory.get_context(session_id)
            
            if not conv_context and len(history) >= 2:
                # Si pas de contexte sauvegardé mais historique disponible, extraire le sujet
                # et sauvegarder le contexte pour les futures interruptions
                topic = conversation_memory.extract_topic(history[:-1])  # Exclure le dernier message (interruption)
                if len(history) >= 2 and history[-2]["role"] == "assistant":
                    last_assistant_msg = history[-2]["content"]
                else:
                    last_assistant_msg = ""
                
                # Sauvegarder le contexte pour les futures interruptions
                conversation_memory.save_context(session_id, topic, last_assistant_msg)
                
                # Pour la première interruption, utiliser un prompt simple
                interrupt_prompt = (
                    "L'utilisateur vient de t'interrompre. Accuse réception brièvement (ex: 'Oui ?', 'Je t'écoute...') puis réponds à sa dernière intervention.\n"
                    "Dans ce contexte d'interruption, privilégie les émotions 'curiosite' ou 'empathie' pour montrer que tu es attentif à ce que l'utilisateur souhaite exprimer.\n"
                    "Coach:"
                )
            else:
                # Si contexte disponible, générer un prompt avec continuité
                if conv_context:
                    topic = conv_context.get("topic", "notre conversation")
                    continuity_phrases = conversation_memory.generate_continuity_phrases(conv_context)
                    continuity_phrase = continuity_phrases[0]  # Prendre la première phrase
                    
                    interrupt_prompt = (
                        f"L'utilisateur vient de t'interrompre. Accuse réception brièvement (ex: 'Oui ?', 'Je t'écoute...') puis réponds à sa dernière intervention.\n"
                        f"Après avoir répondu à l'interruption, utilise une phrase de transition comme '{continuity_phrase}' pour revenir au sujet principal qui était: {topic}.\n"
                        f"Assure la continuité de la conversation en faisant référence au sujet précédent.\n"
                        f"Dans ce contexte d'interruption, privilégie d'abord l'émotion 'curiosite' ou 'empathie', puis reviens à l'émotion appropriée pour le sujet principal.\n"
                        f"Coach:"
                    )
                else:
                    # Fallback si pas de contexte
                    interrupt_prompt = (
                        "L'utilisateur vient de t'interrompre. Accuse réception brièvement (ex: 'Oui ?', 'Je t'écoute...') puis réponds à sa dernière intervention.\n"
                        "Dans ce contexte d'interruption, privilégie les émotions 'curiosite' ou 'empathie' pour montrer que tu es attentif à ce que l'utilisateur souhaite exprimer.\n"
                        "Coach:"
                    )
            
            return system_prompt + interrupt_prompt
        else:
            # Si ce n'est pas une interruption mais que c'est une réponse après une interruption,
            # sauvegarder le contexte actuel pour les futures interruptions
            if session_id and len(history) >= 2:
                topic = conversation_memory.extract_topic(history)
                if len(history) >= 1 and history[-1]["role"] == "user":
                    # Trouver le dernier message de l'assistant
                    last_assistant_msg = ""
                    for msg in reversed(history[:-1]):
                        if msg["role"] == "assistant":
                            last_assistant_msg = msg["content"]
                            break
                    
                    # Sauvegarder le contexte
                    conversation_memory.save_context(session_id, topic, last_assistant_msg)
            
            return system_prompt + "Coach:"


    async def generate(self, history: List[Dict[str, str]], is_interrupted: bool = False,
                      scenario_context: Optional[Dict] = None, session_id: Optional[str] = None) -> Dict[str, str]:
        """
        Génère une réponse du LLM de manière asynchrone.
        
        Args:
            history: Historique de la conversation
            is_interrupted: Indique si l'utilisateur a interrompu l'IA
            scenario_context: Contexte du scénario (optionnel)
            session_id: ID de la session (nécessaire pour la mémoire conversationnelle)
            
        Returns:
            Dict[str, str]: Dictionnaire avec 'text_response', 'emotion_label' et optionnellement 'scenario_updates'
        """
        prompt = self._build_prompt(history, is_interrupted, scenario_context, session_id)
        headers = {
            'Content-Type': 'application/json'
        }
        # Pas d'API Key pour API locale vLLM/TGI

        # Adapter le payload au format typique de vLLM/TGI (peut varier, mais souvent plus simple)
        # Exemple pour TGI ou vLLM avec endpoint /generate
        payload = {
            "inputs": prompt, # Ou "prompt": prompt selon l'API
            "parameters": {
                "max_new_tokens": self.max_tokens,
                "temperature": self.temperature,
                # "do_sample": True, # Souvent nécessaire si temperature != 1.0
                # "top_p": 0.9, # Exemple
                "stop": ["[EMOTION:", "\nuser:", "\nassistant:"] # Séquences d'arrêt importantes
            }
        }
        # Note: Le format exact peut dépendre de la configuration du serveur vLLM/TGI.
        # Consulter la documentation de l'API du serveur d'inférence si nécessaire.

        logger.debug(f"Envoi de la requête LLM à {self.api_url} avec le payload: {json.dumps(payload, indent=2)}")

        try:
            # Créer une session HTTP asynchrone
            session = aiohttp.ClientSession(timeout=self.timeout)
            try:
                # Faire la requête POST
                response = await session.post(self.api_url, headers=headers, json=payload)
                try:
                    response_status = response.status
                    response_text = await response.text() # Lire le texte pour le log en cas d'erreur

                    if response_status == 200:
                        response_data = json.loads(response_text)
                        logger.debug(f"Réponse LLM reçue: {json.dumps(response_data, indent=2)}")

                        # Extraire la réponse selon le format de l'API (vLLM/TGI)
                        # Exemple: {"generated_text": "Réponse [EMOTION: encouragement]"}
                        # Le format exact peut varier.
                        full_response = response_data.get("generated_text", "")
                        if not full_response and isinstance(response_data, list): # Autre format possible vLLM
                             full_response = response_data[0].get("generated_text", "")

                        if not full_response:
                             logger.error(f"Réponse LLM invalide (champ 'generated_text' manquant ou vide): {response_text}")
                             raise ValueError("Format de réponse LLM invalide")

                        # Extraire l'émotion et le texte de la réponse
                        text_response = full_response
                        emotion_label = "neutre" # Défaut

                        lines = full_response.strip().split('\n')
                        last_line = lines[-1].strip()
                        
                        # Chercher l'émotion sur la dernière ligne
                        if last_line.startswith("[EMOTION:") and last_line.endswith("]"):
                            try:
                                extracted_emotion = last_line.split(":")[1].strip()[:-1].lower()
                                if extracted_emotion in TARGET_EMOTIONS:
                                    emotion_label = extracted_emotion
                                    # Retirer la ligne d'émotion du texte principal
                                    text_response = "\n".join(lines[:-1]).strip()
                                else:
                                    logger.warning(f"Émotion extraite '{extracted_emotion}' non valide. Utilisation de 'neutre'.")
                            except Exception:
                                logger.warning(f"Impossible d'extraire l'émotion de '{last_line}'. Utilisation de 'neutre'.")
                        else:
                             logger.warning(f"Balise [EMOTION: ...] non trouvée à la fin de la réponse LLM: '{last_line}'. Utilisation de 'neutre'.")


                        if not text_response: # Si le LLM n'a retourné que l'émotion
                            text_response = "..." # Fournir un texte minimal
                        
                        # Extraire les mises à jour de scénario si présentes
                        scenario_updates = None
                        if scenario_context:
                            # Utiliser full_response car la balise peut être n'importe où
                            scenario_updates = self._extract_scenario_updates(full_response, scenario_context)
                        
                        result = {
                            "text_response": text_response,
                            "emotion_label": emotion_label
                        }
                        
                        if scenario_updates:
                            result["scenario_updates"] = scenario_updates
                            
                        return result
                    else:
                        logger.error(f"Erreur API LLM ({response_status}): {response_text}")
                        raise aiohttp.ClientResponseError(
                            response.request_info,
                            response.history,
                            status=response_status,
                            message=f"Erreur API LLM: {response_text}",
                            headers=response.headers
                        )
                finally:
                    # Fermer la réponse
                    response.close()
            finally:
                # Fermer la session
                await session.close()

        except asyncio.TimeoutError:
            logger.error(f"Timeout lors de l'appel à l'API LLM ({settings.LLM_TIMEOUT_S}s)")
            raise TimeoutError("Timeout API LLM")
        except aiohttp.ClientError as e:
            logger.error(f"Erreur client HTTP lors de l'appel LLM: {e}", exc_info=True)
            raise ConnectionError(f"Erreur de connexion API LLM: {e}")
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la génération LLM: {e}", exc_info=True)
            raise RuntimeError(f"Erreur LLM: {e}")
            
    def _extract_scenario_updates(self, full_response: str, scenario_context: Dict) -> Optional[Dict]:
        """
        Extrait les mises à jour de scénario à partir de la réponse du LLM.
        
        Le LLM peut inclure des directives de mise à jour de scénario dans sa réponse,
        sous la forme de balises JSON ou de sections spéciales.
        
        Format attendu dans la réponse:
        [SCENARIO_UPDATE: {"next_step": "...", "variables": {"var1": "value1", ...}}]
        
        Returns:
            Dict or None: Dictionnaire contenant les mises à jour de scénario, ou None si aucune mise à jour n'est trouvée.
        """
        # Rechercher les balises de mise à jour de scénario
        import re
        
        # Rechercher le pattern [SCENARIO_UPDATE: {...}]
        scenario_update_pattern = r'\[SCENARIO_UPDATE:\s*(\{.*?\})\]'
        match = re.search(scenario_update_pattern, full_response, re.DOTALL)
        
        if match:
            try:
                # Extraire et parser le JSON
                update_json_str = match.group(1)
                update_data = json.loads(update_json_str)
                logger.info(f"Mise à jour de scénario extraite: {update_data}")
                return update_data
            except json.JSONDecodeError as e:
                logger.warning(f"Impossible de parser la mise à jour de scénario: {e}")
                return None
        
        # Si aucune balise explicite n'est trouvée, essayer d'inférer les mises à jour
        # basées sur le contexte du scénario et la réponse
        current_step = scenario_context.get("current_step")
        if current_step:
            # Logique simple: si la réponse contient des mots-clés indiquant une progression
            progress_keywords = ["passons à", "prochaine étape", "continuons avec", "maintenant"]
            if any(keyword in full_response.lower() for keyword in progress_keywords):
                # Inférer la prochaine étape basée sur une logique simple
                # Ceci est un exemple très basique, à adapter selon la structure réelle des scénarios
                steps = scenario_context.get("steps", [])
                if steps and current_step in steps:
                    current_index = steps.index(current_step)
                    if current_index < len(steps) - 1:
                        next_step = steps[current_index + 1]
                        logger.info(f"Progression de scénario inférée: {current_step} -> {next_step}")
                        return {"next_step": next_step}
        
        return None