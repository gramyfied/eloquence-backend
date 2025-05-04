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
        # Utiliser l'URL de l'API Scaleway Mistral
        self.api_url = "https://api.scaleway.ai/18f6cc9d-07fc-49c3-a142-67be9b59ac63/v1/chat/completions"
        self.api_key = settings.SCW_LLM_API_KEY # Clé API Scaleway
        self.model_name = "mistral-nemo-instruct-2407" # Modèle Scaleway
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_MAX_TOKENS # Utiliser une nouvelle setting pour max_tokens Scaleway si différente
        self.timeout = aiohttp.ClientTimeout(total=settings.LLM_TIMEOUT_S)
        logger.info(f"Initialisation du service LLM Scaleway avec API URL: {self.api_url}")

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

        # Adapter le payload au format de l'API Scaleway (similaire à OpenAI)
        # Assurer l'alternance des rôles user/assistant après le message système optionnel
        messages = []
        system_message_content = "You are a helpful assistant" # Message système par défaut

        # Extraire le message système de l'historique s'il existe
        system_message_in_history = next((msg for msg in history if msg["role"] == "system"), None)
        if system_message_in_history:
             system_message_content = system_message_in_history["content"]

        # Ajouter le message système
        messages.append({"role": "system", "content": system_message_content})

        # Ajouter les messages utilisateur/assistant de l'historique en assurant l'alternance
        # On commence après le message système s'il était dans l'historique, sinon depuis le début
        start_index = history.index(system_message_in_history) + 1 if system_message_in_history else 0

        for i in range(start_index, len(history)):
            msg = history[i]
            # Ignorer les messages système supplémentaires dans l'historique
            if msg["role"] in ["user", "assistant"]:
                 messages.append({"role": msg["role"], "content": msg["content"]})
            # Note: Cette logique simple suppose que l'historique fourni a déjà une structure
            # user/assistant. Si l'historique peut avoir d'autres rôles ou des séquences non alternées,
            # une logique plus complexe pourrait être nécessaire pour le nettoyer.

        # Ajouter le prompt spécifique à la fin comme dernier message utilisateur
        # S'assurer que le dernier message avant le prompt est de l'assistant pour maintenir l'alternance
        if messages and messages[-1]["role"] == "user":
             # Si le dernier message est déjà user, cela signifie qu'il y a un problème dans l'historique fourni
             # ou dans la logique de construction. Pour l'API Scaleway, on ne peut pas avoir deux messages user consécutifs.
             # Dans ce cas, on pourrait soit ignorer le dernier message user de l'historique,
             # soit ajouter un message assistant vide, ou lever une erreur.
             # Pour l'instant, ajoutons un message assistant vide pour tenter de maintenir l'alternance.
             messages.append({"role": "assistant", "content": ""})


        messages.append({"role": "user", "content": prompt})


        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": 1, # Valeur par défaut dans l'exemple utilisateur
            "presence_penalty": 0, # Valeur par défaut dans l'exemple utilisateur
            "stream": True, # Activer le streaming
        }

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        logger.debug(f"Envoi de la requête LLM à {self.api_url} avec le payload: {json.dumps(payload, indent=2)}")

        full_response_content = ""
        emotion_label = "neutre" # Défaut
        scenario_updates = None

        session = None
        response = None
        try:
            session = aiohttp.ClientSession(timeout=self.timeout)
            response = await session.post(self.api_url, headers=headers, json=payload)
            response_status = response.status

            if response_status == 200:
                # Gérer la réponse en streaming (Server-Sent Events)
                async for line in response.content:
                    decoded_line = line.decode('utf-8').strip()
                    
                    if not decoded_line: # Ignorer les lignes vides
                        continue

                    if decoded_line == "data: [DONE]":
                        break
                        
                    # Vérifier si la ligne contient l'émotion
                    if decoded_line.startswith("data: [EMOTION:") and decoded_line.endswith("]"):
                         try:
                             # Extraire l'émotion directement de la ligne
                             emotion_part = decoded_line[len("data: "):].strip()
                             if emotion_part.startswith("[EMOTION:") and emotion_part.endswith("]"):
                                 extracted_emotion = emotion_part.split(":")[1].strip()[:-1].lower()
                                 if extracted_emotion in TARGET_EMOTIONS:
                                     emotion_label = extracted_emotion
                                     logger.debug(f"Émotion extraite du flux: {emotion_label}")
                                 else:
                                     logger.warning(f"Émotion extraite du flux '{extracted_emotion}' non valide. Utilisation de 'neutre'.")
                             else:
                                 logger.warning(f"Format d'émotion inattendu dans le flux: {decoded_line}")
                         except Exception as e:
                             logger.warning(f"Impossible d'extraire l'émotion de la ligne du flux '{decoded_line}': {e}")
                         continue # Passer à la ligne suivante après avoir traité l'émotion

                    # Si ce n'est pas l'émotion, essayer de parser comme JSON pour le contenu
                    if decoded_line.startswith("data: "):
                        try:
                            json_content = decoded_line[len("data: "):]
                            # Gérer le cas où le JSON est vide (ex: 'data: \n')
                            if not json_content:
                                continue
                            data = json.loads(json_content)
                            if data.get("choices") and data["choices"][0]["delta"].get("content"):
                                content = data["choices"][0]["delta"]["content"]
                                full_response_content += content
                        except json.JSONDecodeError:
                            # Ignorer les lignes data: qui ne sont pas du JSON valide (autre que l'émotion déjà traitée)
                            logger.warning(f"Impossible de décoder la ligne JSON du flux (ignorée): {decoded_line}")
                            continue
                        except Exception as e:
                             logger.error(f"Erreur lors du traitement d'un chunk de réponse: {e}", exc_info=True)
                             continue

                # Une fois le flux terminé, traiter la réponse complète
                logger.debug(f"Flux LLM terminé. Contenu complet: {full_response_content}")

                text_response = full_response_content.strip()

                # L'émotion a déjà été extraite pendant le streaming
                # Nettoyer le texte au cas où l'émotion serait quand même présente (par sécurité)
                lines = text_response.split('\n')
                if lines and lines[-1].strip().startswith("[EMOTION:") and lines[-1].strip().endswith("]"):
                    text_response = "\n".join(lines[:-1]).strip()

                if not text_response:
                    text_response = "..." # Fournir un texte minimal si vide

                if scenario_context:
                    scenario_updates = self._extract_scenario_updates(full_response_content, scenario_context) # Utiliser full_response_content pour l'extraction du scénario

                result = {
                    "text_response": text_response,
                    "emotion_label": emotion_label # Utiliser l'émotion extraite pendant le stream
                }
                if scenario_updates:
                    result["scenario_updates"] = scenario_updates
                return result

            else:
                response_text = await response.text()
                logger.error(f"Erreur API LLM ({response_status}): {response_text}")
                response.raise_for_status() # Lève ClientResponseError

        except asyncio.TimeoutError:
            logger.error(f"Timeout lors de l'appel à l'API LLM ({settings.LLM_TIMEOUT_S}s)")
            raise TimeoutError("Timeout API LLM")
        except aiohttp.ClientError as e:
            logger.error(f"Erreur client HTTP lors de l'appel LLM: {e}", exc_info=True)
            # Remonter l'erreur spécifique si possible, sinon une ConnectionError générique
            if isinstance(e, aiohttp.ClientResponseError):
                 raise # Remonter l'erreur telle quelle
            else:
                 raise ConnectionError(f"Erreur de connexion API LLM: {e}")
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la génération LLM: {e}", exc_info=True)
            raise RuntimeError(f"Erreur LLM: {e}")
        finally:
            if response:
                response.close() # Assurer la fermeture de la réponse
            if session:
                await session.close() # Assurer la fermeture de la session
            
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

    async def generate_exercise_text(self, exercise_type: str, topic: Optional[str] = None, difficulty: Optional[str] = "moyen", length: Optional[str] = "court") -> str:
        """
        Génère un texte spécifique pour un exercice de coaching.

        Args:
            exercise_type (str): Le type d'exercice (ex: "diction", "lecture", "jeu_de_role_situation").
            topic (Optional[str]): Le sujet ou thème de l'exercice (ex: "voyage", "technologie").
            difficulty (Optional[str]): Le niveau de difficulté (ex: "facile", "moyen", "difficile").
            length (Optional[str]): La longueur souhaitée du texte (ex: "très court", "court", "moyen", "long").

        Returns:
            str: Le texte généré pour l'exercice.
        """
        # Construire un prompt spécifique pour la génération d'exercice
        prompt = f"Génère un texte en français pour un exercice de coaching vocal de type '{exercise_type}'.\n"
        if topic:
            prompt += f"Le sujet est '{topic}'.\n"
        prompt += f"Le niveau de difficulté souhaité est '{difficulty}'.\n"
        prompt += f"La longueur souhaitée est '{length}'.\n"
        
        if exercise_type == "diction":
            prompt += "Le texte doit contenir des mots ou des phrases spécifiquement choisis pour travailler la diction (ex: allitérations, assonances, sons difficiles en français).\n"
        elif exercise_type == "lecture":
            prompt += "Le texte doit être adapté à une lecture à voix haute, avec une structure narrative ou informative claire.\n"
        elif exercise_type == "jeu_de_role_situation":
            prompt += "Décris une situation de jeu de rôle pour un exercice d'improvisation ou de communication. Fournis le contexte et le rôle de l'utilisateur.\n"
        # Ajouter d'autres types d'exercices si nécessaire
        
        prompt += "Ne génère que le texte de l'exercice lui-même, sans introduction ni conclusion supplémentaire, et sans ajouter d'étiquette d'émotion ou de mise à jour de scénario."

        # Adapter le payload au format de l'API Scaleway (similaire à OpenAI) pour une requête non-streaming
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": self.max_tokens * 2, # Permettre des textes potentiellement plus longs pour les exercices
            "temperature": self.temperature,
            "top_p": 1,
            "presence_penalty": 0,
            "stream": False, # Désactiver le streaming pour cette méthode
        }

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        logger.debug(f"Envoi de la requête LLM (exercice) à {self.api_url} avec le payload: {json.dumps(payload, indent=2)}")

        session = None
        response = None
        try:
            session = aiohttp.ClientSession(timeout=self.timeout)
            response = await session.post(self.api_url, headers=headers, json=payload)
            response_status = response.status

            if response_status == 200:
                response_data = await response.json()
                logger.debug(f"Réponse LLM (exercice) reçue: {json.dumps(response_data, indent=2)}")

                generated_text = ""
                if response_data.get("choices") and response_data["choices"][0].get("message") and response_data["choices"][0]["message"].get("content"):
                     generated_text = response_data["choices"][0]["message"]["content"]

                if not generated_text:
                     logger.error(f"Réponse LLM (exercice) invalide: {await response.text()}")
                     raise ValueError("Format de réponse LLM invalide pour l'exercice")

                cleaned_text = generated_text.strip()
                return cleaned_text
            else:
                response_text = await response.text()
                logger.error(f"Erreur API LLM ({response_status}) pour exercice: {response_text}")
                response.raise_for_status() # Lève ClientResponseError

        except asyncio.TimeoutError:
            logger.error(f"Timeout lors de l'appel à l'API LLM (exercice)")
            raise TimeoutError("Timeout API LLM exercice")
        except aiohttp.ClientError as e:
            logger.error(f"Erreur client HTTP lors de l'appel LLM (exercice): {e}", exc_info=True)
            if isinstance(e, aiohttp.ClientResponseError):
                 raise
            else:
                 raise ConnectionError(f"Erreur de connexion API LLM exercice: {e}")
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la génération LLM (exercice): {e}", exc_info=True)
            raise RuntimeError(f"Erreur LLM exercice: {e}")
        finally:
            if response:
                response.close()
            if session:
                await session.close()
