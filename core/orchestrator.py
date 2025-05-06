import asyncio
import logging
from typing import Dict, List, Optional
import time
import json
import numpy as np
import uuid
import os
import soundfile as sf
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# Importer le monitoring de latence
from core.latency_monitor import (
    latency_monitor,
    measure_latency,
    LatencyContext,
    AsyncLatencyContext,
    STEP_VAD_PROCESS,
    STEP_ASR_TRANSCRIBE,
    STEP_LLM_GENERATE,
    STEP_TTS_SYNTHESIZE,
    STEP_TOTAL_TURN,
    STEP_AUDIO_SAVE,
    STEP_DB_OPERATION,
    STEP_KALDI_SCHEDULE
)

# Importer les services (à créer/compléter)
from services.vad_service import VadService
from services.asr_service import AsrService
from services.llm_service import LlmService
from services.tts_service import TtsService
from services.kaldi_service import kaldi_service # Importer l'instance du service
# Importer le manager ici car l'orchestrateur peut le faire sans cycle
from app.websocket import manager as websocket_manager
from core.config import settings
from core.models import CoachingSession, SessionTurn, ScenarioTemplate, Participant, AgentProfile # Importer les modèles DB
# Importer selectinload pour charger les relations
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

# États possibles d'une session ou d'un tour
class TurnState:
    LISTENING = "listening"
    PROCESSING_ASR = "processing_asr"
    PROCESSING_LLM = "processing_llm"
    SPEAKING_TTS = "speaking_tts"
    WAITING = "waiting" # En attente après la fin de parole IA

class ParticipantState:
    """
    État d'un participant dans une session.
    Contient les informations spécifiques à un participant (utilisateur ou agent IA).
    """
    def __init__(self,
                 participant_id: uuid.UUID,
                 name: str,
                 role: str,
                 is_primary: bool = False,
                 agent_profile_id: Optional[str] = None,
                 voice_id: Optional[str] = None):
        self.participant_id: uuid.UUID = participant_id
        self.name: str = name
        self.role: str = role  # 'user' ou 'agent'
        self.is_primary: bool = is_primary
        self.agent_profile_id: Optional[str] = agent_profile_id
        self.voice_id: Optional[str] = voice_id
        self.history: List[Dict[str, str]] = []  # Historique spécifique à ce participant
        self.is_speaking: bool = False
        self.audio_buffer: bytes = b""  # Buffer pour l'ASR
        self.vad_audio_buffer = np.array([], dtype=np.float32)  # Buffer spécifique pour VAD
        self.silence_start_time: Optional[float] = None
        self.speech_start_time: Optional[float] = None
        self.last_activity_time: float = time.time()
        self.is_interrupted: bool = False
        self.current_tts_task: Optional[asyncio.Task] = None
        self.current_llm_task: Optional[asyncio.Task] = None
        self.system_prompt: Optional[str] = None  # Prompt système spécifique pour cet agent

class SessionState:
    def __init__(self,
                 session_id: str,
                 db_session_id: uuid.UUID,
                 language: str = 'fr',
                 goal: Optional[str] = None,
                 scenario_template: Optional[ScenarioTemplate] = None,
                 current_scenario_state: Optional[Dict] = None,
                 is_multi_agent: bool = False):
        self.session_id: str = session_id  # ID externe (peut être string ou UUID)
        self.db_session_id: uuid.UUID = db_session_id  # PK de la table coaching_sessions
        self.language: str = language
        self.goal: Optional[str] = goal  # Objectif spécifique session
        self.scenario_template: Optional[ScenarioTemplate] = scenario_template  # Template chargé
        self.current_scenario_state: Dict = current_scenario_state or {}  # État actuel du scénario
        self.is_multi_agent: bool = False  # Valeur par défaut car la colonne n'existe pas encore dans la base de données
        self.participants: Dict[uuid.UUID, ParticipantState] = {}  # Participants indexés par ID
        self.primary_user_id: Optional[uuid.UUID] = None  # ID du participant utilisateur principal
        self.primary_agent_id: Optional[uuid.UUID] = None  # ID du participant agent principal
        self.active_participant_id: Optional[uuid.UUID] = None  # ID du participant actuellement actif
        self.current_turn_state: str = TurnState.LISTENING
        self.current_turn_number: int = 0  # Compteur de tours
        self.last_activity_time: float = time.time()  # Pour timeouts généraux
        self.gentle_prompt_triggered: bool = False  # Flag pour la relance douce
        
    def add_participant(self, participant_state: ParticipantState) -> None:
        """Ajoute un participant à la session."""
        self.participants[participant_state.participant_id] = participant_state
        
        # Définir comme participant principal si c'est le premier de son rôle ou s'il est marqué comme principal
        if participant_state.role == 'user' and (participant_state.is_primary or self.primary_user_id is None):
            self.primary_user_id = participant_state.participant_id
        elif participant_state.role == 'agent' and (participant_state.is_primary or self.primary_agent_id is None):
            self.primary_agent_id = participant_state.participant_id
            
        # Si c'est le premier participant, le définir comme actif
        if self.active_participant_id is None:
            self.active_participant_id = participant_state.participant_id
            
    def get_active_participant(self) -> Optional[ParticipantState]:
        """Retourne le participant actuellement actif."""
        if self.active_participant_id is None:
            return None
        return self.participants.get(self.active_participant_id)
    
    def get_primary_user(self) -> Optional[ParticipantState]:
        """Retourne le participant utilisateur principal."""
        if self.primary_user_id is None:
            return None
        return self.participants.get(self.primary_user_id)
    
    def get_primary_agent(self) -> Optional[ParticipantState]:
        """Retourne le participant agent principal."""
        if self.primary_agent_id is None:
            return None
        return self.participants.get(self.primary_agent_id)
    
    def get_next_speaker(self) -> Optional[ParticipantState]:
        """
        Détermine le prochain participant qui devrait parler.
        Dans le cas d'une session à deux participants, alterne simplement entre les deux.
        Pour les sessions multi-agents, utilise une logique plus complexe (à implémenter).
        """
        if len(self.participants) <= 1:
            return None
            
        if not self.is_multi_agent:
            # Session simple avec un utilisateur et un agent
            if self.active_participant_id == self.primary_user_id:
                return self.get_primary_agent()
            else:
                return self.get_primary_user()
        else:
            # Session multi-agents (logique à implémenter)
            # Pour l'instant, simplement alterner entre l'utilisateur principal et l'agent principal
            if self.active_participant_id == self.primary_user_id:
                return self.get_primary_agent()
            else:
                return self.get_primary_user()

class Orchestrator:
    def __init__(self):
        self.sessions: Dict[str, SessionState] = {}
        # Initialiser les services
        self.vad_service = VadService()
        self.asr_service = AsrService()
        self.llm_service = LlmService()
        self.tts_service = TtsService()
        self.kaldi_service = kaldi_service # Utiliser l'instance importée
        logger.info("Orchestrator initialisé.")

    async def initialize(self):
        # Charger les modèles, établir les connexions, etc.
        # Charger en parallèle pour accélérer le démarrage
        # Charger les modèles/initialiser les services en parallèle
        load_tasks = [
            self.vad_service.load_model(),
            self.asr_service.load_model(),
            # self.tts_service n'a pas de load_model async, l'init suffit (pool Redis)
        ]
        # Filtrer les tâches None si certains services n'ont pas de load_model
        await asyncio.gather(*[task for task in load_tasks if task is not None])
        logger.info("Modèles et services de l'Orchestrator chargés.")

    async def shutdown(self):
        # Libérer les ressources
        logger.info("Arrêt de l'Orchestrator.")

    @measure_latency(STEP_DB_OPERATION, "session_id_str")
    async def get_or_create_session(self, session_id_str: str, db: AsyncSession, scenario_id: Optional[str] = None, user_id: Optional[str] = "unknown", language: Optional[str] = 'fr', goal: Optional[str] = None, is_multi_agent: bool = False, agent_profile_id: Optional[str] = None) -> Optional[SessionState]:
        """
        Récupère une session existante ou en crée une nouvelle en mémoire et dans la DB.
        Accepte des paramètres optionnels pour la création.
        Supporte désormais les sessions multi-agents.
        """
        if session_id_str in self.sessions:
            return self.sessions[session_id_str]

        logger.info(f"Tentative de récupération/création de la session {session_id_str} en DB.")
        try:
            session_uuid = uuid.UUID(session_id_str) # Convertir l'ID string en UUID
            # Essayer de charger depuis la DB, en chargeant aussi le template de scénario associé et les participants
            stmt = select(CoachingSession).options(
                selectinload(CoachingSession.scenario_template),
                selectinload(CoachingSession.participants)
            ).where(CoachingSession.id == session_uuid)

            result = await db.execute(stmt)
            db_session: Optional[CoachingSession] = result.scalar_one_or_none()

            scenario_template_obj: Optional[ScenarioTemplate] = None
            agent_profile_obj: Optional[AgentProfile] = None

            if db_session:
                logger.info(f"Session {session_id_str} trouvée dans la DB (Scenario ID: {db_session.scenario_template_id}).")
                # Utiliser les valeurs de la DB
                language = db_session.language
                goal = db_session.goal
                # Gérer le cas où la colonne is_multi_agent n'existe pas encore dans la base de données
                try:
                    is_multi_agent = db_session.is_multi_agent
                except AttributeError:
                    logger.warning(f"La colonne 'is_multi_agent' n'existe pas dans la table 'coaching_sessions'. Utilisation de la valeur par défaut: False")
                    is_multi_agent = False
                # Vérifier que goal n'est pas None pour le debug
                logger.debug(f"Session {session_id_str}: goal from DB = {goal}")
                # Ajouter une vérification explicite
                if goal is None and hasattr(db_session, 'goal'):
                    goal = getattr(db_session, 'goal')
                    logger.debug(f"Session {session_id_str}: goal récupéré via getattr = {goal}")
                scenario_template_obj = db_session.scenario_template # Récupérer l'objet chargé
                current_scenario_state = db_session.current_scenario_state or {}
                
                # Créer l'état en mémoire
                session_state = SessionState(
                    session_id=session_id_str,
                    db_session_id=db_session.id,
                    language=language,
                    goal=goal,
                    scenario_template=scenario_template_obj,
                    current_scenario_state=current_scenario_state,
                    is_multi_agent=is_multi_agent
                )
                
                # Charger les participants existants
                for participant in db_session.participants:
                    participant_state = ParticipantState(
                        participant_id=participant.id,
                        name=participant.name,
                        role=participant.role,
                        is_primary=participant.is_primary,
                        agent_profile_id=participant.agent_profile_id,
                        voice_id=participant.voice_id
                    )
                    session_state.add_participant(participant_state)
                    
                # Si aucun participant n'a été trouvé, créer les participants par défaut
                if not db_session.participants:
                    await self._create_default_participants(db, db_session, session_state, user_id, agent_profile_id)
            else:
                logger.info(f"Session {session_id_str} non trouvée. Création en DB.")
                # Charger le template si un ID est fourni lors de la création
                if scenario_id:
                     template_result = await db.execute(select(ScenarioTemplate).where(ScenarioTemplate.id == scenario_id))
                     scenario_template_obj = template_result.scalar_one_or_none()
                     if not scenario_template_obj:
                         logger.warning(f"Scenario template ID '{scenario_id}' non trouvé lors de la création de session.")
                         scenario_id = None # Ne pas lier si non trouvé

                # Charger le profil d'agent si un ID est fourni
                if agent_profile_id:
                    agent_result = await db.execute(select(AgentProfile).where(AgentProfile.id == agent_profile_id))
                    agent_profile_obj = agent_result.scalar_one_or_none()
                    if not agent_profile_obj:
                        logger.warning(f"Agent profile ID '{agent_profile_id}' non trouvé lors de la création de session.")
                        agent_profile_id = None # Ne pas lier si non trouvé

                # Initialiser l'état du scénario si un template est fourni
                current_scenario_state = {}
                if scenario_template_obj:
                    # Charger la structure du scénario
                    structure = json.loads(scenario_template_obj.structure) if scenario_template_obj.structure else {}
                    
                    # Initialiser l'état avec la première étape et les variables par défaut
                    first_step = structure.get("first_step", "")
                    variables = {}
                    
                    # Initialiser les variables avec leurs valeurs par défaut
                    for var_name, var_info in structure.get("variables", {}).items():
                        if "default_value" in var_info:
                            variables[var_name] = var_info["default_value"]
                    
                    current_scenario_state = {
                        "current_step": first_step,
                        "completed_steps": [],
                        "variables": variables
                    }
                    
                    logger.info(f"État initial du scénario créé pour la session {session_id_str}, étape initiale: {first_step}")
                # Créer une nouvelle session sans inclure la colonne is_multi_agent
                db_session = CoachingSession(
                    id=session_uuid,
                    user_id=user_id,
                    scenario_template_id=scenario_id, # Lier l'ID du template
                    language=language,
                    goal=goal,
                    status='active',
                    current_scenario_state=current_scenario_state
                )
                db.add(db_session)
                await db.flush() # Pour obtenir l'ID si généré par défaut (pas le cas ici car on le fournit)
                await db.commit() # Commit après création
                logger.info(f"Session {session_id_str} créée en DB avec Scenario ID: {scenario_id}")
                history = []


            # Créer l'état en mémoire
            session_state = SessionState(
                session_id=session_id_str,
                db_session_id=db_session.id,
                language=language,
                goal=goal,
                scenario_template=scenario_template_obj,
                current_scenario_state=current_scenario_state,
                is_multi_agent=is_multi_agent
            )
            
            # Créer les participants par défaut
            await self._create_default_participants(db, db_session, session_state, user_id, agent_profile_id)
            
            self.sessions[session_id_str] = session_state
            self.vad_service.reset_state() # Réinitialiser VAD pour la nouvelle session en mémoire
            logger.info(f"État VAD réinitialisé pour la session {session_id_str}")
            return session_state

        except ValueError:
             logger.error(f"L'ID de session '{session_id_str}' n'est pas un UUID valide.")
             return None
        except Exception as e:
            logger.error(f"Erreur DB lors de get_or_create_session pour {session_id_str}: {e}", exc_info=True)
            await db.rollback() # Assurer le rollback en cas d'erreur
            return None

    async def _create_default_participants(self, db: AsyncSession, db_session: CoachingSession, session_state: SessionState, user_id: str, agent_profile_id: Optional[str] = None) -> None:
        """
        Crée les participants par défaut pour une session.
        Pour une session standard, crée un utilisateur et un agent coach.
        """
        # Créer le participant utilisateur
        user_participant = Participant(
            session_id=db_session.id,
            name=f"Utilisateur {user_id}",
            role="user",
            is_primary=True
        )
        db.add(user_participant)
        await db.flush()
        
        # Créer l'état du participant utilisateur
        user_participant_state = ParticipantState(
            participant_id=user_participant.id,
            name=user_participant.name,
            role=user_participant.role,
            is_primary=user_participant.is_primary
        )
        session_state.add_participant(user_participant_state)
        
        # Créer le participant agent (coach par défaut)
        agent_profile_id = agent_profile_id or "coach"  # Utiliser "coach" comme profil par défaut
        agent_name = "Coach IA"
        agent_voice_id = None
        
        # Charger le profil d'agent si disponible
        agent_profile_result = await db.execute(select(AgentProfile).where(AgentProfile.id == agent_profile_id))
        agent_profile = agent_profile_result.scalar_one_or_none()
        if agent_profile:
            agent_name = agent_profile.name
            agent_voice_id = agent_profile.voice_id
        
        agent_participant = Participant(
            session_id=db_session.id,
            agent_profile_id=agent_profile_id,
            name=agent_name,
            role="agent",
            is_primary=True,
            voice_id=agent_voice_id
        )
        db.add(agent_participant)
        await db.flush()
        
        # Créer l'état du participant agent
        agent_participant_state = ParticipantState(
            participant_id=agent_participant.id,
            name=agent_participant.name,
            role=agent_participant.role,
            is_primary=agent_participant.is_primary,
            agent_profile_id=agent_participant.agent_profile_id,
            voice_id=agent_participant.voice_id
        )
        
        # Définir le prompt système si disponible
        if agent_profile and agent_profile.system_prompt:
            agent_participant_state.system_prompt = agent_profile.system_prompt
            
        session_state.add_participant(agent_participant_state)
    @measure_latency(STEP_VAD_PROCESS, "session_id")
    async def process_audio_chunk(self, session_id: str, chunk: bytes, db: AsyncSession):
        """Traite un chunk audio, effectue le VAD et gère les transitions d'état."""
        session = self.sessions.get(session_id) # Récupérer depuis la mémoire
        if not session:
             logger.error(f"Session {session_id} non trouvée en mémoire dans process_audio_chunk.")
             # Tenter de la recréer/charger ? Pour l'instant, on ignore.
             return
        session.last_activity_time = time.time()

        # Ne traiter l'audio que si on écoute ou si on a été interrompu
        if session.current_turn_state != TurnState.LISTENING and not session.is_interrupted:
            # logger.debug(f"Session {session_id}: Reçu audio pendant l'état {session.current_turn_state}. Ignoré.")
            return

        # Ajouter au buffer ASR seulement si on est en train de parler ou si on vient de commencer
        # (pour éviter d'ajouter du silence avant le début de la parole)
        if session.is_speaking or len(session.audio_buffer) > 0:
             session.audio_buffer += chunk

        # Traiter avec le VAD
        speech_prob = self.vad_service.process_chunk(chunk)

        if speech_prob is None: # Pas assez de données pour une fenêtre VAD complète
            return

        # Logique de détection Start/End Speech
        is_currently_speech = speech_prob >= self.vad_service.threshold
        now = time.time()

        if is_currently_speech and not session.is_speaking:
            # Début de parole détecté
            session.is_speaking = True
            session.silence_start_time = None
            session.speech_start_time = now
            logger.debug(f"Session {session_id}: Début de parole détecté.")
            # Commencer à bufferiser pour ASR à partir de maintenant (ou un peu avant avec padding)
            # On peut ajouter le chunk courant au buffer ASR ici si ce n'est pas déjà fait
            if len(session.audio_buffer) == 0:
                session.audio_buffer += chunk # Ajouter le premier chunk de parole

        elif not is_currently_speech and session.is_speaking:
            # Fin de parole potentielle (début de silence)
            if session.silence_start_time is None:
                session.silence_start_time = now
            logger.debug(f"Session {session_id}: Silence détecté après parole (depuis {session.silence_start_time:.2f}).")

            silence_duration_ms = (now - session.silence_start_time) * 1000
            if silence_duration_ms >= settings.VAD_MIN_SILENCE_DURATION_MS:
                logger.info(f"Session {session_id}: Silence > {settings.VAD_MIN_SILENCE_DURATION_MS}ms détecté.")
                session.is_speaking = False
                session.silence_start_time = None # Réinitialiser pour la prochaine détection
                session.speech_start_time = None
                # Déclencher le traitement ASR/LLM/TTS
                await self.handle_end_of_speech(session_id, db)
            elif settings.VAD_GENTLE_PROMPT_SILENCE_MS > 0 and \
                 silence_duration_ms >= settings.VAD_GENTLE_PROMPT_SILENCE_MS and \
                 not session.gentle_prompt_triggered:
                 # Déclencher la relance douce si le seuil est atteint et non déjà déclenché
                 logger.info(f"Session {session_id}: Silence > {settings.VAD_GENTLE_PROMPT_SILENCE_MS}ms. Déclenchement relance douce.")
                 session.gentle_prompt_triggered = True # Marquer comme déclenché pour ce silence
                 # Lancer la tâche en arrière-plan pour ne pas bloquer le traitement VAD
                 asyncio.create_task(self.handle_gentle_prompt(session_id, db))


        elif not is_currently_speech and not session.is_speaking:
            # Silence continu avant le début de parole, ne rien faire
            pass
        elif is_currently_speech and session.is_speaking:
             # Parole continue
             session.silence_start_time = None # Réinitialiser au cas où il y aurait eu un court silence


    @measure_latency(STEP_TOTAL_TURN, "session_id")
    async def handle_end_of_speech(self, session_id: str, db: AsyncSession = None):
        """Gère la fin de parole détectée par le VAD."""
        session = self.sessions.get(session_id)
        
        # Si db n'est pas fourni, c'est une erreur car nous en avons besoin pour les opérations DB
        if db is None:
            logger.error(f"Session {session_id}: handle_end_of_speech appelé sans session DB.")
            return
        # Vérifier si la session existe et si on était bien en train d'écouter
        # (ou si on a été interrompu et que l'utilisateur a fini de parler)
        if not session or (session.current_turn_state != TurnState.LISTENING and not session.is_interrupted):
            logger.warning(f"Session {session_id}: handle_end_of_speech appelé dans un état inattendu ({session.current_turn_state if session else 'None'}).")
            return

        # Assurer qu'on passe à l'état de traitement ASR
        session.current_turn_state = TurnState.PROCESSING_ASR
        logger.info(f"Session {session_id}: Passage à l'état {TurnState.PROCESSING_ASR}.")

        audio_to_process = session.audio_buffer
        session.audio_buffer = b"" # Réinitialiser le buffer ASR

        # Réinitialiser l'état VAD pour le prochain tour
        self.vad_service.reset_state()

        if not audio_to_process:
            logger.warning(f"Session {session_id}: Buffer audio ASR vide après fin de parole. Retour à l'écoute.")
            session.current_turn_state = TurnState.LISTENING
            return

        session.current_turn_number += 1
        user_turn_id = None
        audio_filepath = None

        try:
            # Sauvegarder l'audio utilisateur
            async with AsyncLatencyContext(STEP_AUDIO_SAVE, session_id):
                audio_filepath = await self._save_audio_file(session_id, session.current_turn_number, audio_to_process)

            # Créer le tour utilisateur dans la DB (initialement sans transcription)
            async with AsyncLatencyContext(STEP_DB_OPERATION, session_id):
                user_turn = SessionTurn(
                    session_id=session.db_session_id,
                    turn_number=session.current_turn_number,
                    role="user",
                    audio_path=audio_filepath # Stocker le chemin
                )
                db.add(user_turn)
                await db.flush() # Pour obtenir l'ID du tour
                user_turn_id = user_turn.id
                logger.info(f"Session {session_id}: Tour utilisateur {session.current_turn_number} créé en DB (ID: {user_turn_id}).")

            # Appeler ASR
            async with AsyncLatencyContext(STEP_ASR_TRANSCRIBE, session_id):
                transcription = await self.asr_service.transcribe(audio_to_process, language=session.language)
            logger.info(f"Session {session_id}: Transcription ASR: '{transcription}'")

            # Mettre à jour le tour utilisateur avec la transcription
            async with AsyncLatencyContext(STEP_DB_OPERATION, session_id):
                user_turn.text_content = transcription
                db.add(user_turn) # Ajouter à nouveau pour la mise à jour
                await db.flush()

            # Déclencher Kaldi en arrière-plan (asynchrone) avec l'ID du tour
            with LatencyContext(STEP_KALDI_SCHEDULE, session_id):
                if audio_to_process and transcription and user_turn_id:
                    # Passer l'ID du tour à la tâche Celery
                    self.kaldi_service.schedule_analysis(session_id, user_turn_id, audio_to_process, transcription)
                else:
                    logger.warning(f"Session {session_id}: Audio, transcription ou turn_id manquant(e), analyse Kaldi non déclenchée.")

            # Ajouter à l'historique en mémoire pour le LLM
            session.history.append({"role": "user", "content": transcription})
            session.current_turn_state = TurnState.PROCESSING_LLM

            # Construire le contexte du scénario pour le LLM
            # Construire le contexte du scénario pour le LLM
            scenario_context = None
            if session.scenario_template:
                # Charger la structure du scénario
                structure = json.loads(session.scenario_template.structure) if session.scenario_template.structure else {}
                
                # Récupérer les informations de l'étape actuelle
                current_step_id = session.current_scenario_state.get("current_step", "")
                steps = structure.get("steps", {})
                current_step_info = steps.get(current_step_id, {})
                
                # Construire le contexte
                scenario_context = {
                    "name": session.scenario_template.name,
                    "goal": session.scenario_template.description,
                    "current_step": current_step_id,
                    "current_step_name": current_step_info.get("name", ""),
                    "current_step_description": current_step_info.get("description", ""),
                    "prompt_template": current_step_info.get("prompt_template", ""),
                    "expected_variables": current_step_info.get("expected_variables", []),
                    "next_steps": current_step_info.get("next_steps", []),
                    "is_final": current_step_info.get("is_final", False),
                    "completed_steps": session.current_scenario_state.get("completed_steps", []),
                    "variables": session.current_scenario_state.get("variables", {}),
                    "steps": list(steps.keys())  # Liste des IDs d'étapes disponibles
                }

            # Appeler LLM
            logger.info(f"Session {session_id}: Appel LLM avec interruption={session.is_interrupted}, contexte scénario: {scenario_context is not None}")
            async with AsyncLatencyContext(STEP_LLM_GENERATE, session_id):
                session.current_llm_task = asyncio.create_task(
                    self.llm_service.generate(session.history, session.is_interrupted, scenario_context) # Passer le contexte
                )
                try:
                    llm_response = await session.current_llm_task
                except asyncio.CancelledError:
                    logger.info(f"Session {session_id}: Tâche LLM annulée.")
                    # Si annulé (probablement par interruption), revenir à l'écoute
                    session.current_turn_state = TurnState.LISTENING
                    return # Ne pas continuer le traitement
                finally:
                    session.current_llm_task = None # Nettoyer la référence à la tâche

            logger.info(f"Session {session_id}: Réponse LLM: '{llm_response['text_response']}', Emotion: {llm_response['emotion_label']}")
            
            # Traiter les mises à jour de scénario si présentes
            if 'scenario_updates' in llm_response and session.scenario_template:
                scenario_updates = llm_response['scenario_updates']
                logger.info(f"Session {session_id}: Mises à jour de scénario reçues: {scenario_updates}")
                
                # Charger la structure du scénario
                structure = json.loads(session.scenario_template.structure) if session.scenario_template.structure else {}
                steps = structure.get("steps", {})
                
                # Mettre à jour l'étape courante
                if 'next_step' in scenario_updates:
                    next_step = scenario_updates['next_step']
                    
                    # Vérifier que l'étape existe dans le scénario
                    if next_step in steps:
                        # Ajouter l'étape actuelle aux étapes complétées
                        current_step = session.current_scenario_state.get("current_step", "")
                        if current_step and current_step not in session.current_scenario_state.get("completed_steps", []):
                            if "completed_steps" not in session.current_scenario_state:
                                session.current_scenario_state["completed_steps"] = []
                            session.current_scenario_state["completed_steps"].append(current_step)
                        
                        # Mettre à jour l'étape courante
                        session.current_scenario_state["current_step"] = next_step
                        logger.info(f"Session {session_id}: Progression à l'étape '{next_step}'")
                    else:
                        logger.warning(f"Session {session_id}: Étape '{next_step}' non trouvée dans le scénario")
                
                # Mettre à jour les variables du scénario
                if 'variables' in scenario_updates and isinstance(scenario_updates['variables'], dict):
                    # Initialiser le dictionnaire de variables s'il n'existe pas
                    if 'variables' not in session.current_scenario_state:
                        session.current_scenario_state['variables'] = {}
                    
                    # Mettre à jour les variables
                    for key, value in scenario_updates['variables'].items():
                        session.current_scenario_state['variables'][key] = value
                        logger.info(f"Session {session_id}: Variable '{key}' mise à jour: {value}")
                
                # Mettre à jour l'état du scénario dans la DB
                async with AsyncLatencyContext(STEP_DB_OPERATION, session_id):
                    try:
                        db_session = await db.get(CoachingSession, session.db_session_id)
                        if db_session:
                            db_session.current_scenario_state = session.current_scenario_state
                            db.add(db_session)
                            await db.flush()
                            logger.info(f"Session {session_id}: État du scénario mis à jour en DB")
                        else:
                            logger.warning(f"Session {session_id}: Session non trouvée en DB pour mise à jour du scénario")
                    except Exception as e:
                        logger.error(f"Session {session_id}: Erreur lors de la mise à jour du scénario en DB: {e}")

            # Ajouter à l'historique en mémoire
            session.history.append({"role": "assistant", "content": llm_response["text_response"]})
            session.is_interrupted = False # Réinitialiser l'état d'interruption après l'appel LLM réussi

            # Créer le tour assistant dans la DB
            async with AsyncLatencyContext(STEP_DB_OPERATION, session_id):
                assistant_turn = SessionTurn(
                    session_id=session.db_session_id,
                    turn_number=session.current_turn_number, # Même numéro de tour que l'utilisateur
                    role="assistant",
                    text_content=llm_response["text_response"],
                    emotion_label=llm_response["emotion_label"]
                )
                db.add(assistant_turn)
                await db.flush() # Pas besoin de l'ID ici, mais flush avant commit
                logger.info(f"Session {session_id}: Tour assistant {session.current_turn_number} créé en DB.")

            session.current_turn_state = TurnState.SPEAKING_TTS

            # Appeler TTS et streamer vers WebSocket
            logger.info(f"Session {session_id}: Appel TTS pour streamer la réponse.")
            async with AsyncLatencyContext(STEP_TTS_SYNTHESIZE, session_id):
                session.current_tts_task = asyncio.create_task(
                    self.tts_service.stream_synthesize(
                        session_id=session_id,
                        text=llm_response["text_response"],
                        emotion=llm_response["emotion_label"],
                        language=session.language
                    )
                )
                try:
                    await session.current_tts_task
                except asyncio.CancelledError:
                    logger.info(f"Session {session_id}: Tâche TTS annulée pendant l'attente.")
                    # L'annulation est gérée dans stream_synthesize et handle_interruption
                    # Pas besoin de changer l'état ici, handle_interruption le fera si nécessaire
                finally:
                    session.current_tts_task = None # Nettoyer la référence à la tâche

            # Après la fin (ou l'annulation) du TTS, revenir à l'écoute
            # sauf si une erreur majeure est survenue avant
            if session.current_turn_state == TurnState.SPEAKING_TTS: # Vérifier si l'état n'a pas changé (ex: par erreur)
                 session.current_turn_state = TurnState.LISTENING
                 logger.info(f"Session {session_id}: Retour à l'état {TurnState.LISTENING} après TTS.")

            # Commit final pour ce tour (user + assistant turns)
            async with AsyncLatencyContext(STEP_DB_OPERATION, session_id):
                await db.commit()
            logger.debug(f"Session {session_id}: Commit DB pour le tour {session.current_turn_number}.")

        except Exception as e:
            logger.error(f"Erreur lors du traitement du tour pour session {session_id}: {e}", exc_info=True)
            await db.rollback() # Rollback en cas d'erreur pendant le tour
            session.current_turn_state = TurnState.LISTENING # Revenir à l'écoute en cas d'erreur
            # Envoyer un message d'erreur au client ?
            try:
                await websocket_manager.send_personal_message(json.dumps({"type": "error", "message": "Une erreur interne est survenue."}), session_id)
            except Exception as send_error:
                 logger.error(f"Impossible d'envoyer le message d'erreur à la session {session_id}: {send_error}")


    async def handle_gentle_prompt(self, session_id: str, db: AsyncSession):
        """Génère et envoie une relance douce après un silence modéré."""
        session = self.sessions.get(session_id)
        if not session or session.current_turn_state != TurnState.LISTENING or not session.is_speaking:
            # Ne pas envoyer si l'état a changé ou si l'utilisateur a repris la parole
            logger.debug(f"Session {session_id}: Annulation de la relance douce (état={session.current_turn_state if session else 'None'}, is_speaking={session.is_speaking if session else 'N/A'}).")
            return

        # Ne pas interrompre si l'IA parle déjà (ce qui ne devrait pas arriver ici, mais sécurité)
        if session.current_tts_task and not session.current_tts_task.done():
             logger.warning(f"Session {session_id}: Tentative de relance douce alors que le TTS est actif. Annulé.")
             return

        logger.info(f"Session {session_id}: Préparation de la relance douce.")
        # Créer un prompt spécifique pour la relance
        gentle_prompt_text = "L'utilisateur fait une pause. Propose une courte relance encourageante (ex: 'Vous pouvez continuer...', 'Prenez votre temps...', 'Oui...?')."
        # Utiliser une partie de l'historique pour le contexte ? Pour l'instant, non.
        temp_history = [{"role": "system", "content": gentle_prompt_text}]

        try:
            # Construire le contexte du scénario (même si le prompt de relance ne l'utilise pas forcément)
            # Construire le contexte du scénario pour la relance douce
            scenario_context = None
            if session.scenario_template:
                # Charger la structure du scénario
                structure = json.loads(session.scenario_template.structure) if session.scenario_template.structure else {}
                
                # Récupérer les informations de l'étape actuelle
                current_step_id = session.current_scenario_state.get("current_step", "")
                steps = structure.get("steps", {})
                current_step_info = steps.get(current_step_id, {})
                
                # Construire le contexte
                scenario_context = {
                    "name": session.scenario_template.name,
                    "goal": session.scenario_template.description,
                    "current_step": current_step_id,
                    "current_step_name": current_step_info.get("name", ""),
                    "current_step_description": current_step_info.get("description", ""),
                    "prompt_template": current_step_info.get("prompt_template", ""),
                    "expected_variables": current_step_info.get("expected_variables", []),
                    "next_steps": current_step_info.get("next_steps", []),
                    "is_final": current_step_info.get("is_final", False),
                    "completed_steps": session.current_scenario_state.get("completed_steps", []),
                    "variables": session.current_scenario_state.get("variables", {}),
                    "steps": list(steps.keys())  # Liste des IDs d'étapes disponibles
                }

            # Appeler LLM pour la relance (sans marquer comme interrompu)
            llm_response = await self.llm_service.generate(temp_history, is_interrupted=False, scenario_context=scenario_context) # Passer le contexte
            logger.info(f"Session {session_id}: Relance douce LLM: '{llm_response['text_response']}', Emotion: {llm_response['emotion_label']}")

            # Ne pas ajouter cette relance à l'historique principal de la conversation
            # Créer un tour 'system' ou 'internal' dans la DB si on veut tracer ? Pour l'instant non.

            # Appeler TTS pour streamer la relance
            # Utiliser une tâche séparée pour ne pas bloquer si le TTS prend du temps
            # Mais attention aux interruptions concurrentes
            logger.info(f"Session {session_id}: Appel TTS pour relance douce.")
            # On ne stocke pas cette tâche TTS dans session.current_tts_task pour ne pas interférer
            # avec la gestion d'interruption principale. Si l'utilisateur interrompt PENDANT
            # la relance douce, handle_interruption ne l'arrêtera pas directement.
            # C'est un compromis pour la simplicité.
            await self.tts_service.stream_synthesize(
                session_id=session_id,
                text=llm_response["text_response"],
                emotion=llm_response["emotion_label"], # Utiliser l'émotion suggérée
                language=session.language
            )
            logger.info(f"Session {session_id}: Fin streaming relance douce.")

        except Exception as e:
            logger.error(f"Erreur lors de la génération/streaming de la relance douce pour session {session_id}: {e}", exc_info=True)
            # Ne pas envoyer d'erreur au client pour une simple relance


    async def handle_interruption(self, session_id: str):
        # Pas besoin de session DB ici, on modifie juste l'état en mémoire et annule les tâches
        session = self.sessions.get(session_id)
        if not session:
            return

        logger.info(f"Session {session_id}: Interruption utilisateur reçue.")
        session.is_interrupted = True

        # 1. Arrêter le TTS en cours
        if session.current_tts_task and not session.current_tts_task.done():
            logger.info(f"Session {session_id}: Annulation de la tâche TTS en cours.")
            # Essayer d'abord d'arrêter proprement la génération via l'API
            try:
                # Appeler la méthode stop_generation du service TTS
                stop_success = await self.tts_service.stop_generation(session_id)
                if not stop_success:
                    # Si l'arrêt via API échoue, annuler la tâche asyncio
                    logger.info(f"Session {session_id}: Arrêt via API échoué, annulation de la tâche asyncio.")
                    session.current_tts_task.cancel()
            except Exception as e:
                logger.error(f"Session {session_id}: Erreur lors de l'arrêt TTS: {e}")
                # En cas d'erreur, annuler la tâche asyncio
                session.current_tts_task.cancel()

        # 2. Annuler la tâche LLM si elle est en cours (moins probable mais possible)
        if session.current_llm_task and not session.current_llm_task.done():
             logger.info(f"Session {session_id}: Annulation de la tâche LLM en cours.")
             session.current_llm_task.cancel()

        # 3. Réinitialiser le buffer audio ? Ou le garder pour le prochain tour ? Gardons-le pour l'instant.
        # session.audio_buffer = b""

        # 4. Passer à l'état d'écoute pour traiter le nouvel audio de l'utilisateur
        session.current_turn_state = TurnState.LISTENING
        # Réinitialiser l'état VAD car l'utilisateur va recommencer à parler
        self.vad_service.reset_state()
        logger.info(f"Session {session_id}: Prêt à écouter après interruption. État VAD réinitialisé.")


    async def cleanup_session(self, session_id: str, db: AsyncSession):
        """Nettoie la session en mémoire et met à jour son statut en DB."""
        if session_id in self.sessions:
            logger.info(f"Nettoyage de la session en mémoire: {session_id}")
            session = self.sessions[session_id]

            # Mettre à jour le statut en DB
            try:
                result = await db.execute(select(CoachingSession).where(CoachingSession.id == session.db_session_id))
                db_session = result.scalar_one_or_none()
                if db_session:
                    db_session.status = "disconnected" # Ou 'ended' si fin normale
                    db_session.ended_at = time.time() # Utiliser datetime.utcnow() ?
                    db.add(db_session)
                    await db.commit()
                    logger.info(f"Statut de la session {session_id} mis à jour en DB: disconnected.")
                else:
                    logger.warning(f"Session {session_id} (DB ID: {session.db_session_id}) non trouvée en DB lors du cleanup.")
            except Exception as e:
                logger.error(f"Erreur DB lors du cleanup de la session {session_id}: {e}", exc_info=True)
                await db.rollback()

            # Annuler les tâches en cours si elles existent
            if session.current_tts_task and not session.current_tts_task.done():
                session.current_tts_task.cancel()
            if session.current_llm_task and not session.current_llm_task.done():
                session.current_llm_task.cancel()
            del self.sessions[session_id]

    async def generate_exercise(self, exercise_type: str, topic: Optional[str] = None, difficulty: Optional[str] = "moyen", length: Optional[str] = "court") -> str:
        """
        Génère le texte pour un exercice de coaching en utilisant le LLM.

        Args:
            exercise_type (str): Type d'exercice.
            topic (Optional[str]): Sujet de l'exercice.
            difficulty (Optional[str]): Difficulté de l'exercice.
            length (Optional[str]): Longueur souhaitée du texte.

        Returns:
            str: Le texte généré pour l'exercice.
        
        Raises:
            Exception: Si la génération échoue.
        """
        logger.info(f"Demande de génération d'exercice: type={exercise_type}, topic={topic}, difficulty={difficulty}, length={length}")
        try:
            # Utiliser la nouvelle méthode du LlmService
            exercise_text = await self.llm_service.generate_exercise_text(
                exercise_type=exercise_type,
                topic=topic,
                difficulty=difficulty,
                length=length
            )
            logger.info(f"Texte d'exercice généré avec succès.")
            return exercise_text
        except Exception as e:
            logger.error(f"Erreur lors de la génération de l'exercice '{exercise_type}': {e}", exc_info=True)
            # Remonter l'exception pour que la route API puisse retourner une erreur 500
            raise Exception(f"Impossible de générer le texte pour l'exercice: {e}")
            
    async def end_session(self, session_id: uuid.UUID) -> None:
        """
        Termine une session de coaching.
        Met à jour le statut de la session et nettoie les ressources associées.
        
        Args:
            session_id (uuid.UUID): L'ID de la session à terminer.
            
        Returns:
            None
        """
        session_id_str = str(session_id)
        logger.info(f"Demande de fin de session: {session_id_str}")
        
        # Vérifier si la session existe en mémoire
        if session_id_str not in self.sessions:
            logger.warning(f"Session {session_id_str} non trouvée en mémoire lors de end_session.")
            return
            
        # Nettoyer la session (utiliser la méthode existante)
        # Note: cleanup_session s'occupe déjà de mettre à jour le statut en DB
        # et de nettoyer les ressources en mémoire
        await self.cleanup_session(session_id_str, None)
        
        logger.info(f"Session {session_id_str} terminée avec succès.")


# Instance globale de l'orchestrateur
orchestrator = Orchestrator()
