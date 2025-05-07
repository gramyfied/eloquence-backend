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
    async def generate(self, history: List[Dict[str, str]] = None, is_interrupted: bool = False, scenario_context: Optional[Dict] = None, prompt: str = None, context: Dict = None) -> Dict[str, str]:
        """
        Génère une réponse du LLM de manière asynchrone.
        Supporte deux interfaces:
        1. Avec history, is_interrupted et scenario_context (interface originale)
        2. Avec prompt et context (interface utilisée par les routes)
        
        Retourne un dictionnaire avec 'text_response' et 'emotion_label'.
        """
        # Si prompt et context sont fournis, convertir au format attendu par l'interface originale
        if prompt is not None and history is None:
            # Créer un historique à partir du prompt
            history = [{"role": "user", "content": prompt}]
            
            # Extraire le contexte du scénario si disponible
            if context:
                scenario_context = {
                    "name": context.get("context_type", "general"),
                    "goal": "améliorer l'expression orale",
                    "current_step": "conversation"
                }
                
                # Si un historique est fourni dans le contexte, l'utiliser
                if "history" in context and context["history"]:
                    history = context["history"] + history
        
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
                async with session.post(self.api_url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Erreur vLLM {response.status}: {error_text}")
                        return {"text": f"Erreur du service LLM: {response.status}", "emotion": "neutre"}
                    
                    # Traiter la réponse
                    response_json = await response.json()
                    
                    # Extraire le texte de la réponse
                    if "choices" in response_json and len(response_json["choices"]) > 0:
                        content = response_json["choices"][0]["message"]["content"]
                    else:
                        logger.error(f"Format de réponse vLLM inattendu: {response_json}")
                        return {"text": "Erreur: format de réponse inattendu", "emotion": "neutre"}
                    
                    # Extraire l'émotion du texte
                    emotion = "neutre"  # Valeur par défaut
                    for target_emotion in TARGET_EMOTIONS:
                        if f"[EMOTION: {target_emotion}]" in content:
                            emotion = target_emotion
                            # Supprimer le tag d'émotion du texte
                            content = content.replace(f"[EMOTION: {target_emotion}]", "").strip()
                            break
                    
                    return {"text": content, "emotion": emotion}
            finally:
                await session.close()
        except asyncio.TimeoutError:
            logger.error(f"Timeout lors de la requête vLLM après {self.timeout.total} secondes")
            return {"text": "Désolé, le service LLM a mis trop de temps à répondre.", "emotion": "neutre"}
        except Exception as e:
            logger.error(f"Erreur lors de la génération vLLM: {e}")
            return {"text": f"Erreur du service LLM: {str(e)}", "emotion": "neutre"}

    async def _generate_tgi(self, history: List[Dict[str, str]], is_interrupted: bool = False, scenario_context: Optional[Dict] = None) -> Dict[str, str]:
        """
        Génère une réponse en utilisant TGI (Text Generation Inference).
        """
        # Construire le prompt au format texte (TGI n'utilise pas le format de messages)
        prompt = self._build_prompt(history, is_interrupted, scenario_context)
        
        headers = {'Content-Type': 'application/json'}
        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": self.temperature,
                "max_new_tokens": self.max_tokens,
                "do_sample": True,
                "top_p": 0.9,
                "top_k": 50
            }
        }

        logger.debug(f"Envoi de la requête TGI à {self.api_url} avec le payload: {json.dumps(payload, indent=2)}")

        try:
            # Créer une session HTTP asynchrone
            session = aiohttp.ClientSession(timeout=self.timeout)
            try:
                # Faire la requête POST
                async with session.post(self.api_url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Erreur TGI {response.status}: {error_text}")
                        return {"text": f"Erreur du service LLM: {response.status}", "emotion": "neutre"}
                    
                    # Traiter la réponse
                    response_json = await response.json()
                    
                    # Extraire le texte de la réponse
                    if isinstance(response_json, list) and len(response_json) > 0 and "generated_text" in response_json[0]:
                        content = response_json[0]["generated_text"]
                        # Supprimer le prompt de la réponse
                        if content.startswith(prompt):
                            content = content[len(prompt):].strip()
                    else:
                        logger.error(f"Format de réponse TGI inattendu: {response_json}")
                        return {"text": "Erreur: format de réponse inattendu", "emotion": "neutre"}
                    
                    # Extraire l'émotion du texte
                    emotion = "neutre"  # Valeur par défaut
                    for target_emotion in TARGET_EMOTIONS:
                        if f"[EMOTION: {target_emotion}]" in content:
                            emotion = target_emotion
                            # Supprimer le tag d'émotion du texte
                            content = content.replace(f"[EMOTION: {target_emotion}]", "").strip()
                            break
                    
                    return {"text": content, "emotion": emotion}
            finally:
                await session.close()
        except asyncio.TimeoutError:
            logger.error(f"Timeout lors de la requête TGI après {self.timeout.total} secondes")
            return {"text": "Désolé, le service LLM a mis trop de temps à répondre.", "emotion": "neutre"}
        except Exception as e:
            logger.error(f"Erreur lors de la génération TGI: {e}")
            return {"text": f"Erreur du service LLM: {str(e)}", "emotion": "neutre"}