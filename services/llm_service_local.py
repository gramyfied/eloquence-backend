import asyncio
import logging
import json
from typing import List, Dict, Optional
import aiohttp
import os

from core.config import settings
from core.latency_monitor import measure_latency, STEP_LLM_GENERATE

logger = logging.getLogger(__name__)

# Liste des émotions cibles pour le prompt LLM
TARGET_EMOTIONS = ["encouragement", "empathie", "neutre", "enthousiasme_modere", "curiosite", "reflexion"]

class LlmService:
    """
    Service pour interagir avec Mistral en local via vLLM ou TGI.
    """
    def __init__(self):
        self.api_url = settings.LLM_LOCAL_API_URL
        self.model_name = settings.LLM_MODEL_NAME
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
        self.timeout = aiohttp.ClientTimeout(total=settings.LLM_TIMEOUT_S)
        self.backend = settings.LLM_BACKEND.lower()  # 'vllm' ou 'tgi'
        logger.info(f"Initialisation du service LLM local avec backend: {self.backend}, API URL: {self.api_url}, Model: {self.model_name}")

    def _build_prompt(self, history: List[Dict[str, str]], is_interrupted: bool, scenario_context: Optional[Dict] = None) -> str:
        """
        Construit le prompt pour le LLM, en incluant le contexte du scénario si fourni.
        scenario_context pourrait contenir: {"name": "...", "goal": "...", "current_step": "...", "variables": {...}}
        """
        # Limiter l'historique pour ne pas dépasser les limites de contexte
        context_limit = 6  # Nombre de tours de parole (user + assistant) à inclure
        limited_history = history[-(context_limit * 2):]  # Prend les derniers messages

        history_str = "\n".join(f"{msg['role']}: {msg['content']}" for msg in limited_history)

        # Contexte du scénario
        scenario_prompt_part = ""
        if scenario_context:
            scenario_name = scenario_context.get("name", "exercice")
            scenario_goal = scenario_context.get("goal", "améliorer son expression")
            current_step = scenario_context.get("current_step", "étape actuelle")  # L'état pourrait être plus complexe
            scenario_prompt_part = (
                f"CONTEXTE SCÉNARIO: Nous sommes dans un scénario '{scenario_name}'.\n"
                f"OBJECTIF DU SCÉNARIO: {scenario_goal}.\n"
                f"ÉTAPE ACTUELLE: {current_step}.\n"
                # Ajouter d'autres infos pertinentes du scénario si nécessaire
                f"Adapte ta réponse en fonction de ce contexte.\n\n"
            )

        # Instruction système
        system_prompt = (
            f"Tu es un coach vocal interactif pour l'application Eloquence. Ton objectif est d'aider l'utilisateur à améliorer son expression orale en français. "
            f"Sois encourageant, patient et constructif. Limite tes réponses à 3-4 phrases maximum. "
            f"IMPORTANT: Termine TOUJOURS ta réponse par une étiquette d'émotion sur une nouvelle ligne, choisie parmi cette liste : {', '.join(TARGET_EMOTIONS)}. "
            f"Format: '[EMOTION: nom_emotion]'. Par exemple: '[EMOTION: encouragement]'.\n\n"
            f"{scenario_prompt_part}"  # Injecter le contexte du scénario ici
            f"Voici l'historique récent de la conversation:\n{history_str}\n\n"
        )

        # Ajouter le contexte d'interruption si nécessaire
        if is_interrupted:
            interrupt_prompt = (
                "L'utilisateur vient de t'interrompre. Accuse réception brièvement (ex: 'Oui ?', 'Je t'écoute...') puis réponds à sa dernière intervention.\n"
                "Coach:"
            )
            return system_prompt + interrupt_prompt
        else:
            return system_prompt + "Coach:"

    def _build_messages(self, history: List[Dict[str, str]], is_interrupted: bool, scenario_context: Optional[Dict] = None) -> List[Dict[str, str]]:
        """
        Construit les messages au format attendu par vLLM/TGI pour Mistral.
        """
        # Limiter l'historique pour ne pas dépasser les limites de contexte
        context_limit = 6  # Nombre de tours de parole (user + assistant) à inclure
        limited_history = history[-(context_limit * 2):]  # Prend les derniers messages

        # Instruction système
        system_content = (
            f"Tu es un coach vocal interactif pour l'application Eloquence. Ton objectif est d'aider l'utilisateur à améliorer son expression orale en français. "
            f"Sois encourageant, patient et constructif. Limite tes réponses à 3-4 phrases maximum. "
            f"IMPORTANT: Termine TOUJOURS ta réponse par une étiquette d'émotion sur une nouvelle ligne, choisie parmi cette liste : {', '.join(TARGET_EMOTIONS)}. "
            f"Format: '[EMOTION: nom_emotion]'. Par exemple: '[EMOTION: encouragement]'."
        )

        # Ajouter le contexte du scénario si fourni
        if scenario_context:
            scenario_name = scenario_context.get("name", "exercice")
            scenario_goal = scenario_context.get("goal", "améliorer son expression")
            current_step = scenario_context.get("current_step", "étape actuelle")
            system_content += (
                f"\n\nCONTEXTE SCÉNARIO: Nous sommes dans un scénario '{scenario_name}'. "
                f"OBJECTIF DU SCÉNARIO: {scenario_goal}. "
                f"ÉTAPE ACTUELLE: {current_step}. "
                f"Adapte ta réponse en fonction de ce contexte."
            )

        # Ajouter le contexte d'interruption si nécessaire
        if is_interrupted:
            system_content += "\n\nL'utilisateur vient de t'interrompre. Accuse réception brièvement (ex: 'Oui ?', 'Je t'écoute...') puis réponds à sa dernière intervention."

        # Construire les messages
        messages = [{"role": "system", "content": system_content}]
        
        # Ajouter l'historique
        for msg in limited_history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        return messages

    @measure_latency(STEP_LLM_GENERATE)
    async def generate(self, history: List[Dict[str, str]], is_interrupted: bool = False, scenario_context: Optional[Dict] = None) -> Dict[str, str]:
        """
        Génère une réponse du LLM de manière asynchrone.
        Retourne un dictionnaire avec 'text_response' et 'emotion_label'.
        """
        if self.backend == 'vllm':
            return await self._generate_vllm(history, is_interrupted, scenario_context)
        elif self.backend == 'tgi':
            return await self._generate_tgi(history, is_interrupted, scenario_context)
        else:
            logger.error(f"Backend LLM non supporté: {self.backend}")
            raise ValueError(f"Backend LLM non supporté: {self.backend}")

    async def _generate_vllm(self, history: List[Dict[str, str]], is_interrupted: bool = False, scenario_context: Optional[Dict] = None) -> Dict[str, str]:
        """
        Génère une réponse en utilisant vLLM.
        """
        messages = self._build_messages(history, is_interrupted, scenario_context)
        
        headers = {'Content-Type': 'application/json'}
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False
        }

        logger.debug(f"Envoi de la requête vLLM à {self.api_url} avec le payload: {json.dumps(payload, indent=2)}")

        try:
            # Créer une session HTTP asynchrone
            session = aiohttp.ClientSession(timeout=self.timeout)
            try:
                # Faire la requête POST
                response = await session.post(f"{self.api_url}/v1/chat/completions", headers=headers, json=payload)
                try:
                    response_status = response.status
                    response_text = await response.text()  # Lire le texte pour le log en cas d'erreur

                    if response_status == 200:
                        response_data = json.loads(response_text)
                        logger.debug(f"Réponse vLLM reçue: {json.dumps(response_data, indent=2)}")

                        # Extraire la réponse selon le format de vLLM
                        if response_data.get("choices") and len(response_data["choices"]) > 0:
                            full_response = response_data["choices"][0].get("message", {}).get("content", "")

                            # Extraire l'émotion et le texte de la réponse
                            text_response = full_response
                            emotion_label = "neutre"  # Défaut

                            lines = full_response.strip().split('\n')
                            last_line = lines[-1].strip()
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

                            if not text_response:  # Si le LLM n'a retourné que l'émotion
                                text_response = "..."  # Fournir un texte minimal

                            return {"text_response": text_response, "emotion_label": emotion_label}
                        else:
                            logger.error(f"Réponse vLLM invalide (manque choices): {response_text}")
                            raise ValueError("Format de réponse vLLM invalide")
                    else:
                        logger.error(f"Erreur API vLLM ({response_status}): {response_text}")
                        raise aiohttp.ClientResponseError(
                            response.request_info,
                            response.history,
                            status=response_status,
                            message=f"Erreur API vLLM: {response_text}",
                            headers=response.headers
                        )
                finally:
                    # Fermer la réponse
                    response.close()
            finally:
                # Fermer la session
                await session.close()

        except asyncio.TimeoutError:
            logger.error(f"Timeout lors de l'appel à l'API vLLM ({settings.LLM_TIMEOUT_S}s)")
            raise TimeoutError("Timeout API vLLM")
        except aiohttp.ClientError as e:
            logger.error(f"Erreur client HTTP lors de l'appel vLLM: {e}", exc_info=True)
            raise ConnectionError(f"Erreur de connexion API vLLM: {e}")
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la génération vLLM: {e}", exc_info=True)
            raise RuntimeError(f"Erreur vLLM: {e}")

    async def _generate_tgi(self, history: List[Dict[str, str]], is_interrupted: bool = False, scenario_context: Optional[Dict] = None) -> Dict[str, str]:
        """
        Génère une réponse en utilisant TGI (Text Generation Inference).
        """
        # Pour TGI, nous utilisons le prompt textuel plutôt que les messages
        prompt = self._build_prompt(history, is_interrupted, scenario_context)
        
        headers = {'Content-Type': 'application/json'}
        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": self.temperature,
                "max_new_tokens": self.max_tokens,
                "do_sample": True,
                "return_full_text": False
            }
        }

        logger.debug(f"Envoi de la requête TGI à {self.api_url} avec le payload: {json.dumps(payload, indent=2)}")

        try:
            # Créer une session HTTP asynchrone
            session = aiohttp.ClientSession(timeout=self.timeout)
            try:
                # Faire la requête POST
                response = await session.post(f"{self.api_url}/generate", headers=headers, json=payload)
                try:
                    response_status = response.status
                    response_text = await response.text()  # Lire le texte pour le log en cas d'erreur

                    if response_status == 200:
                        response_data = json.loads(response_text)
                        logger.debug(f"Réponse TGI reçue: {json.dumps(response_data, indent=2)}")

                        # Extraire la réponse selon le format de TGI
                        if isinstance(response_data, list) and len(response_data) > 0:
                            full_response = response_data[0].get("generated_text", "")
                        else:
                            full_response = response_data.get("generated_text", "")

                        # Extraire l'émotion et le texte de la réponse
                        text_response = full_response
                        emotion_label = "neutre"  # Défaut

                        lines = full_response.strip().split('\n')
                        last_line = lines[-1].strip()
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

                        if not text_response:  # Si le LLM n'a retourné que l'émotion
                            text_response = "..."  # Fournir un texte minimal

                        return {"text_response": text_response, "emotion_label": emotion_label}
                    else:
                        logger.error(f"Erreur API TGI ({response_status}): {response_text}")
                        raise aiohttp.ClientResponseError(
                            response.request_info,
                            response.history,
                            status=response_status,
                            message=f"Erreur API TGI: {response_text}",
                            headers=response.headers
                        )
                finally:
                    # Fermer la réponse
                    response.close()
            finally:
                # Fermer la session
                await session.close()

        except asyncio.TimeoutError:
            logger.error(f"Timeout lors de l'appel à l'API TGI ({settings.LLM_TIMEOUT_S}s)")
            raise TimeoutError("Timeout API TGI")
        except aiohttp.ClientError as e:
            logger.error(f"Erreur client HTTP lors de l'appel TGI: {e}", exc_info=True)
            raise ConnectionError(f"Erreur de connexion API TGI: {e}")
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la génération TGI: {e}", exc_info=True)
            raise RuntimeError(f"Erreur TGI: {e}")