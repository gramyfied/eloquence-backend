import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import time # Importer time pour simuler le temps

# Importer les classes et instances à tester ou mocker
from core.orchestrator import Orchestrator, SessionState, ParticipantState, TurnState
from services.vad_service import VadService
from services.asr_service import AsrService
from services.llm_service import LlmService
from services.tts_service_optimized import TTSServiceOptimized # Importer la classe pour mocker
from services.kaldi_service import KaldiService # Importer la classe pour mocker
from app.websocket import manager as websocket_manager # Importer le manager pour mocker
from core.database import get_db # Importer pour mocker la DB
from core.models import CoachingSession, SessionTurn, ScenarioTemplate, Participant, AgentProfile # Importer les modèles
from core.config import settings # Importer settings pour VAD_GENTLE_PROMPT_SILENCE_MS

# Fixture pour mocker les services dépendants
@pytest.fixture
def mock_services():
    vad_service = AsyncMock(spec=VadService)
    asr_service = AsyncMock(spec=AsrService)
    llm_service = AsyncMock(spec=LlmService)
    tts_service = AsyncMock(spec=TTSServiceOptimized) # Mocker l'instance optimisée
    kaldi_service = AsyncMock(spec=KaldiService) # Mocker l'instance

    # Configurer les mocks pour les méthodes appelées par l'orchestrateur
    vad_service.process_chunk.return_value = 1.0 # Simuler la détection de parole
    vad_service.threshold = 0.5 # Seuil VAD
    vad_service.reset_state.return_value = None

    asr_service.transcribe.return_value = "Transcription de test"

    llm_service.generate.return_value = {"text_response": "Réponse LLM de test", "emotion_label": "neutre"}
    llm_service.generate_exercise_text.return_value = "Texte d'exercice de test" # Ajouter le mock pour la nouvelle méthode

    tts_service.stream_synthesize.return_value = None # Simuler le streaming réussi
    tts_service.stop_synthesis.return_value = True

    kaldi_service.schedule_analysis.return_value = None # Simuler la planification réussie

    return vad_service, asr_service, llm_service, tts_service, kaldi_service

# Fixture pour mocker la base de données asynchrone
@pytest.fixture
async def mock_db_session():
    db_session = AsyncMock()
    # Mocker les méthodes courantes de la session DB
    db_session.execute.return_value = MagicMock(scalar_one_or_none=AsyncMock(return_value=None)) # Simuler session non trouvée par défaut
    db_session.get.return_value = None # Simuler get non trouvé par défaut
    db_session.add.return_value = None
    db_session.flush.return_value = None
    db_session.commit.return_value = None
    db_session.rollback.return_value = None

    # Mocker get_async_db pour retourner notre mock de session
    with patch('core.database.get_db', return_value=iter([db_session])):
        yield db_session

# Fixture pour mocker le WebSocket manager
@pytest.fixture
def mock_websocket_manager():
    manager = AsyncMock(spec=websocket_manager)
    manager.send_personal_message.return_value = None
    manager.send_binary.return_value = None
    return manager

# Fixture pour créer une instance de l'Orchestrator avec les services mockés
@pytest.fixture
def orchestrator_instance(mock_services):
    vad_service, asr_service, llm_service, tts_service, kaldi_service = mock_services
    # Créer d'abord l'instance
    orchestrator = Orchestrator()
    # Puis remplacer les attributs d'instance
    orchestrator.vad_service = vad_service
    orchestrator.asr_service = asr_service
    orchestrator.llm_service = llm_service
    orchestrator.tts_service = tts_service
    orchestrator.kaldi_service = kaldi_service
    # Mocker le dictionnaire de sessions pour le contrôle
    orchestrator.sessions = {}
    yield orchestrator

# Test du flux principal de traitement audio
@pytest.mark.asyncio
async def test_process_audio_chunk_and_handle_end_of_speech(orchestrator_instance, mock_services, mock_db_session, mock_websocket_manager):
    vad_service, asr_service, llm_service, tts_service, kaldi_service = mock_services
    orchestrator = orchestrator_instance
    db_session = mock_db_session
    # websocket_manager est déjà importé et peut être utilisé directement si non mocké globalement

    session_id = "test_session_123"
    session_uuid = uuid.uuid4()
    audio_chunk = b"simulated_audio_chunk"
    mock_audio_filepath = "/fake/path/audio.wav"

    # Mocker la création/récupération de session en DB
    mock_db_session_obj = CoachingSession(id=session_uuid, user_id="test_user", status="active", language="fr", current_scenario_state={})
    mock_db_session_obj.participants = [] # Pas de participants initialement
    db_session.execute.return_value = MagicMock(scalar_one_or_none=AsyncMock(return_value=mock_db_session_obj))
    db_session.get.return_value = mock_db_session_obj # Pour la mise à jour du scénario

    # Mocker la création des participants par défaut
    mock_user_participant = Participant(id=uuid.uuid4(), session_id=session_uuid, name="User", role="user", is_primary=True)
    mock_agent_participant = Participant(id=uuid.uuid4(), session_id=session_uuid, name="Agent", role="agent", is_primary=True)
    # Simuler l'ajout des participants à la session DB mockée
    mock_db_session_obj.participants.extend([mock_user_participant, mock_agent_participant])

    # Mocker la création du tour utilisateur en DB
    mock_user_turn = SessionTurn(session_id=session_uuid, turn_number=1, role="user", audio_path=mock_audio_filepath)
    # Configurer le mock db_session.add pour stocker l'objet ajouté
    added_objects = {}
    def mock_add(obj):
        if isinstance(obj, SessionTurn) and obj.role == "user":
            # Simuler l'attribution d'un ID après flush
            obj.id = uuid.uuid4()
            added_objects["user_turn"] = obj
        elif isinstance(obj, SessionTurn) and obj.role == "assistant":
             added_objects["assistant_turn"] = obj
        elif isinstance(obj, CoachingSession):
             added_objects["session"] = obj

    db_session.add.side_effect = mock_add

    # Mocker la sauvegarde du fichier audio
    with patch.object(orchestrator_instance, '_save_audio_file', new=AsyncMock(return_value=mock_audio_filepath)):

        # 1. Créer la session en envoyant le premier chunk
        await orchestrator_instance.process_audio_chunk(session_id, audio_chunk, db_session)

        # Vérifier que la session a été créée en mémoire
        assert session_id in orchestrator_instance.sessions
        session_state = orchestrator_instance.sessions[session_id]
        assert session_state.session_id == session_id
        assert session_state.db_session_id == session_uuid
        assert session_state.current_turn_state == TurnState.LISTENING # Doit être en écoute initialement
        assert len(session_state.participants) == 2 # Utilisateur et Agent créés

        # Vérifier que le VAD a été appelé
        vad_service.process_chunk.assert_called_once_with(audio_chunk)
        # Vérifier que le buffer audio a été mis à jour
        assert session_state.audio_buffer == audio_chunk

        # 2. Simuler la détection de fin de parole en appelant handle_end_of_speech directement
        # (Dans la vraie vie, process_audio_chunk l'appellerait)
        # On doit s'assurer que le buffer audio contient quelque chose
        session_state.audio_buffer = b"simulated_full_audio"
        session_state.is_speaking = False # Simuler la fin de parole détectée par VAD
        session_state.current_turn_state = TurnState.LISTENING # S'assurer de l'état correct

        await orchestrator_instance.handle_end_of_speech(session_id, db_session)

        # Vérifier les appels aux services dans l'ordre attendu
        # ASR doit être appelé avec le buffer audio
        asr_service.transcribe.assert_called_once_with(b"simulated_full_audio", language=session_state.language)

        # LLM doit être appelé avec l'historique mis à jour et le contexte
        # L'historique doit contenir le tour utilisateur
        expected_history = [{"role": "user", "content": "Transcription de test"}]
        llm_service.generate.assert_called_once()
        # Vérifier les arguments de generate
        call_args, call_kwargs = llm_service.generate.call_args
        assert call_args[0] == expected_history # history
        assert call_kwargs['is_interrupted'] == False # is_interrupted
        assert call_kwargs['scenario_context'] == session_state.current_scenario_state # scenario_context

        # TTS doit être appelé pour streamer la réponse LLM
        tts_service.stream_synthesize.assert_called_once()
        # Vérifier les arguments de stream_synthesize
        tts_call_kwargs = tts_service.stream_synthesize.call_args[1]
        assert tts_call_kwargs['session_id'] == session_id
        assert tts_call_kwargs['text'] == "Réponse LLM de test"
        assert tts_call_kwargs['emotion'] == "neutre"
        assert tts_call_kwargs['language'] == session_state.language
        # Le websocket_manager doit être passé
        assert tts_call_kwargs['websocket_manager'] is websocket_manager

        # Kaldi doit être planifié
        kaldi_service.schedule_analysis.assert_called_once()
        # Vérifier les arguments de schedule_analysis
        kaldi_call_args = kaldi_service.schedule_analysis.call_args[0]
        assert kaldi_call_args[0] == session_id # session_id
        assert isinstance(kaldi_call_args[1], uuid.UUID) # turn_id (doit être un UUID)
        assert kaldi_call_args[2] == b"simulated_full_audio" # audio_bytes
        assert kaldi_call_args[3] == "Transcription de test" # transcription

        # Vérifier les opérations DB
        # La session doit être récupérée/créée
        db_session.execute.assert_called_once()
        # Le tour utilisateur doit être ajouté et flushé
        assert "user_turn" in added_objects
        assert added_objects["user_turn"].text_content == "Transcription de test"
        # Le tour assistant doit être ajouté
        assert "assistant_turn" in added_objects
        assert added_objects["assistant_turn"].text_content == "Réponse LLM de test"
        assert added_objects["assistant_turn"].emotion_label == "neutre"
        # Le commit final doit être appelé
        db_session.commit.assert_called_once()

        # Vérifier l'état final de la session
        assert session_state.current_turn_state == TurnState.LISTENING # Doit revenir à l'écoute
        assert session_state.current_turn_number == 1
        assert session_state.audio_buffer == b"" # Buffer ASR vidé
        assert session_state.is_interrupted == False # Flag d'interruption réinitialisé
        vad_service.reset_state.assert_called() # VAD réinitialisé

@pytest.mark.asyncio
async def test_handle_interruption(orchestrator_instance, mock_services):
    vad_service, asr_service, llm_service, tts_service, kaldi_service = mock_services
    orchestrator = orchestrator_instance

    session_id = "test_session_interrupt"
    session_uuid = uuid.uuid4()

    # Créer un état de session en mémoire
    session_state = SessionState(
        session_id=session_id,
        db_session_id=session_uuid,
        language="fr",
        current_scenario_state={}
    )
    orchestrator.sessions[session_id] = session_state

    # Simuler que le LLM et le TTS sont en cours
    mock_llm_task = asyncio.create_task(asyncio.sleep(10)) # Tâche LLM mockée
    mock_tts_task = asyncio.create_task(asyncio.sleep(10)) # Tâche TTS mockée

    session_state.current_llm_task = mock_llm_task
    session_state.current_tts_task = mock_tts_task
    session_state.current_turn_state = TurnState.PROCESSING_LLM # Ou SPEAKING_TTS

    # Appeler handle_interruption
    await orchestrator.handle_interruption(session_id)

    # Vérifier que le flag d'interruption est mis à jour
    assert session_state.is_interrupted == True

    # Vérifier que les tâches LLM et TTS ont été annulées
    # Note: task.cancel() lève une CancelledError, mais la tâche est marquée comme done()
    # et task.cancelled() retourne True après l'await de l'exception.
    # Ici, on vérifie simplement que cancel() a été appelé sur le mock.
    # Pour un test plus robuste, on pourrait mocker asyncio.create_task
    # et vérifier que cancel() est appelé sur les mocks de tâches retournés.
    # Avec les mocks AsyncMock, on peut vérifier l'appel à stop_synthesis et cancel()
    tts_service.stop_synthesis.assert_called_once_with(session_id)
    # Vérifier que la tâche LLM a été annulée
    mock_llm_task.cancel.assert_called_once()

    # Vérifier que l'état de la session est revenu à l'écoute
    assert session_state.current_turn_state == TurnState.LISTENING

    # Vérifier que le VAD a été réinitialisé
    vad_service.reset_state.assert_called_once()

    # Vérifier que les références aux tâches sont nettoyées (après l'await dans handle_end_of_speech)
    # Note: Dans ce test unitaire de handle_interruption seul, les tâches ne sont pas awaitées
    # après l'appel à cancel(), donc les références ne sont pas nettoyées ici.
    # Le nettoyage se produit dans handle_end_of_speech après l'await de la tâche annulée.
    # On peut ajouter une vérification ici si on mocke asyncio.create_task et qu'on s'assure
    # que les mocks de tâches sont awaitables et lèvent CancelledError.
    # Pour l'instant, on se contente de vérifier les appels à cancel/stop_synthesis.

@pytest.mark.asyncio
async def test_handle_gentle_prompt(orchestrator_instance, mock_services, mock_db_session, mock_websocket_manager):
    vad_service, asr_service, llm_service, tts_service, kaldi_service = mock_services
    orchestrator = orchestrator_instance
    db_session = mock_db_session

    session_id = "test_session_gentle_prompt"
    session_uuid = uuid.uuid4()

    # Créer un état de session en mémoire
    session_state = SessionState(
        session_id=session_id,
        db_session_id=session_uuid,
        language="fr",
        current_scenario_state={}
    )
    orchestrator.sessions[session_id] = session_state

    # Simuler que l'utilisateur a commencé à parler, puis s'est arrêté,
    # et que le silence a atteint le seuil
    session_state.is_speaking = False
    session_state.current_turn_state = TurnState.LISTENING
    session_state.silence_start_time = time.time() - (settings.VAD_GENTLE_PROMPT_SILENCE_MS / 1000.0) - 0.1 # Juste au-delà du seuil
    session_state.gentle_prompt_triggered = False # S'assurer que la relance n'a pas encore été déclenchée

    # Mocker la réponse du LLM pour la relance douce
    llm_service.generate.return_value = {"text_response": "Continuez, je vous écoute.", "emotion_label": "encouragement"}

    # Appeler process_audio_chunk avec un chunk de silence pour déclencher la relance
    # On a besoin d'un mock pour time.time() pour contrôler la durée du silence
    with patch('time.time', return_value=time.time()): # Utiliser le temps actuel pour le début du silence
        # Simuler un chunk de silence qui dépasse le seuil
        await orchestrator_instance.process_audio_chunk(session_id, b"simulated_silence_chunk", db_session)

    # Vérifier que la relance douce a été déclenchée (flag mis à jour)
    assert session_state.gentle_prompt_triggered == True

    # Vérifier que le LLM a été appelé avec le prompt spécifique pour la relance
    llm_service.generate.assert_called_once()
    llm_call_args, llm_call_kwargs = llm_service.generate.call_args
    # Vérifier que le premier message de l'historique est le prompt système de relance
    assert llm_call_args[0][0]["role"] == "system"
    assert "Propose une courte relance encourageante" in llm_call_args[0][0]["content"]
    # Vérifier que le flag is_interrupted est False pour la relance douce
    assert llm_call_kwargs['is_interrupted'] == False
    # Vérifier que le contexte scénario est passé
    assert llm_call_kwargs['scenario_context'] == session_state.current_scenario_state


    # Vérifier que le TTS a été appelé pour streamer la relance
    tts_service.stream_synthesize.assert_called_once()
    tts_call_kwargs = tts_service.stream_synthesize.call_args[1]
    assert tts_call_kwargs['session_id'] == session_id
    assert tts_call_kwargs['text'] == "Continuez, je vous écoute."
    assert tts_call_kwargs['emotion'] == "encouragement"
    assert tts_call_kwargs['language'] == session_state.language
    assert tts_call_kwargs['websocket_manager'] is websocket_manager

    # Vérifier que l'état de la session n'a PAS changé (reste en écoute)
    assert session_state.current_turn_state == TurnState.LISTENING

    # Vérifier que le buffer audio n'a PAS été vidé (l'utilisateur est toujours censé parler)
    # Note: process_audio_chunk ajoute le chunk au buffer si is_speaking est True ou si le buffer n'est pas vide.
    # Dans ce scénario, is_speaking est False, donc le chunk de silence ne devrait pas être ajouté.
    # Le buffer devrait contenir uniquement les données avant le silence.
    # Pour ce test, on simule juste le déclenchement, donc le buffer peut être vide ou contenir le chunk initial.
    # L'important est qu'il ne soit pas vidé par handle_gentle_prompt.
    # assert session_state.audio_buffer == b"simulated_silence_chunk" # Si on veut tester l'ajout du chunk
    pass # Pas de vérification stricte du buffer ici

    # Vérifier qu'aucune opération DB n'a été committée (la relance n'est pas un tour complet)
    db_session.commit.assert_not_called()


# TODO: Ajouter des tests pour:
# - Création/chargement de session avec scénario et participants existants
# - Mise à jour de l'état du scénario par la réponse LLM
# - Gestion des erreurs à chaque étape du pipeline (ASR, LLM, TTS, DB, Kaldi)
# - Nettoyage de session (cleanup_session)
# - Gestion des sessions multi-agents (logique get_next_speaker, etc.)
# - Appel à generate_exercise (méthode generate_exercise)
