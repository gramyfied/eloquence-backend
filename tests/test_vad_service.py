import pytest
import pytest_asyncio
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
import torch
from typing import Generator, Tuple, Any

# Importer la classe à tester et les dépendances
from services.vad_service import VadService
from core.config import settings

# --- Fixtures --- 

# Mock pour le modèle Silero VAD et ses utilitaires
@pytest.fixture
def mock_silero_vad() -> Tuple[MagicMock, MagicMock]:
    mock_model = MagicMock(name="SileroVADModelMock")
    # Simuler le retour de l'appel au modèle: (probabilité, état_h, état_c)
    # Par défaut, simuler une probabilité de silence
    mock_model.return_value = (torch.tensor([[0.1]]), MagicMock(), MagicMock())
    
    mock_utils = MagicMock(name="SileroVADUtilsMock")
    # Ajouter les méthodes utilitaires mockées si nécessaire
    # mock_utils.some_method.return_value = ...
    
    return mock_model, mock_utils

# Fixture pour le service VAD avec dépendances mockées
@pytest_asyncio.fixture
async def vad_service(mocker: MagicMock, mock_silero_vad: Tuple[MagicMock, MagicMock]) -> Generator[VadService, None, None]:
    mock_model, mock_utils = mock_silero_vad
    
    # Mocker torch.hub.load pour retourner nos mocks
    mocker.patch("torch.hub.load", return_value=(mock_model, mock_utils))
    
    # Mocker les settings VAD si nécessaire pour les tests
    # mocker.patch("core.config.settings.VAD_THRESHOLD", 0.5)
    # mocker.patch("core.config.settings.VAD_SAMPLING_RATE", 16000)
    # mocker.patch("core.config.settings.VAD_WINDOW_SIZE_SAMPLES", 512)
    # mocker.patch("core.config.settings.VAD_SPEECH_PAD_MS", 30)
    # mocker.patch("core.config.settings.VAD_CONSECUTIVE_SPEECH_FRAMES", 2)
    # mocker.patch("core.config.settings.VAD_CONSECUTIVE_SILENCE_FRAMES", 8)

    # Initialiser le service
    # Utiliser une taille de fenêtre cohérente avec les tests
    service = VadService(
        threshold=settings.VAD_THRESHOLD, 
        window_size_samples=settings.VAD_WINDOW_SIZE_SAMPLES # Utiliser settings
    )
    # Charger le modèle mocké
    await service.load_model()
    # Assurer que les états internes sont initialisés
    service.reset_state()
    yield service
    # Cleanup si nécessaire

# --- Helper Functions --- 

def create_mock_audio_chunk(size: int) -> bytes:
    """Crée un chunk audio simulé (bytes)."""
    return np.random.rand(size).astype(np.float32).tobytes()

# --- Tests --- 

@pytest.mark.asyncio
async def test_vad_load_model(vad_service: VadService, mock_silero_vad: Tuple[MagicMock, MagicMock]):
    # Le modèle est chargé dans la fixture vad_service
    mock_model, mock_utils = mock_silero_vad
    assert vad_service.model is mock_model
    assert vad_service.utils is mock_utils
    # Vérifier que les états internes sont initialisés (si le modèle les retourne)
    assert hasattr(vad_service, "_h")
    assert hasattr(vad_service, "_c")

# Note: process_chunk n'est pas async, donc pas besoin de @pytest.mark.asyncio ici
# Mais load_model l'est, donc la fixture doit être async

def test_vad_process_chunk_initial_silence(vad_service: VadService, mock_silero_vad: Tuple[MagicMock, MagicMock]):
    mock_model, _ = mock_silero_vad
    mock_model.return_value = (torch.tensor([[0.1]]), MagicMock(), MagicMock()) # Silence
    
    audio_chunk = create_mock_audio_chunk(vad_service.window_size_samples)
    result = vad_service.process_chunk(audio_chunk)
    
    assert result["is_speech"] is False
    assert result["speech_prob"] == 0.1
    assert vad_service.is_speaking is False
    assert vad_service.silence_frames_count == 1
    assert vad_service.speech_frames_count == 0

def test_vad_process_chunk_transition_to_speech(vad_service: VadService, mock_silero_vad: Tuple[MagicMock, MagicMock]):
    mock_model, _ = mock_silero_vad
    audio_chunk = create_mock_audio_chunk(vad_service.window_size_samples)

    # Simuler quelques frames de silence d'abord
    mock_model.return_value = (torch.tensor([[0.1]]), MagicMock(), MagicMock()) # Silence
    for _ in range(settings.VAD_CONSECUTIVE_SILENCE_FRAMES):
        vad_service.process_chunk(audio_chunk)
    assert vad_service.is_speaking is False

    # Simuler la transition vers la parole
    mock_model.return_value = (torch.tensor([[0.9]]), MagicMock(), MagicMock()) # Parole
    results = []
    for i in range(settings.VAD_CONSECUTIVE_SPEECH_FRAMES + 1):
        result = vad_service.process_chunk(audio_chunk)
        results.append(result)
        # Vérifier que l'état change seulement après VAD_CONSECUTIVE_SPEECH_FRAMES
        if i < settings.VAD_CONSECUTIVE_SPEECH_FRAMES -1 :
             assert vad_service.is_speaking is False
             assert result["is_speech"] is False # L'état global n'a pas encore changé
        else:
             assert vad_service.is_speaking is True
             assert result["is_speech"] is True # L'état global a changé

    # Vérifier le dernier résultat
    last_result = results[-1]
    assert last_result["is_speech"] is True
    assert last_result["speech_prob"] == 0.9
    assert vad_service.speech_frames_count == settings.VAD_CONSECUTIVE_SPEECH_FRAMES + 1
    assert vad_service.silence_frames_count == 0 # Réinitialisé lors de la détection de parole

def test_vad_process_chunk_transition_to_silence(vad_service: VadService, mock_silero_vad: Tuple[MagicMock, MagicMock]):
    mock_model, _ = mock_silero_vad
    audio_chunk = create_mock_audio_chunk(vad_service.window_size_samples)

    # Simuler état initial de parole
    mock_model.return_value = (torch.tensor([[0.9]]), MagicMock(), MagicMock()) # Parole
    for _ in range(settings.VAD_CONSECUTIVE_SPEECH_FRAMES):
        vad_service.process_chunk(audio_chunk)
    assert vad_service.is_speaking is True

    # Simuler la transition vers le silence
    mock_model.return_value = (torch.tensor([[0.1]]), MagicMock(), MagicMock()) # Silence
    results = []
    for i in range(settings.VAD_CONSECUTIVE_SILENCE_FRAMES + 1):
        result = vad_service.process_chunk(audio_chunk)
        results.append(result)
        # Vérifier que l'état change seulement après VAD_CONSECUTIVE_SILENCE_FRAMES
        if i < settings.VAD_CONSECUTIVE_SILENCE_FRAMES -1:
            assert vad_service.is_speaking is True
            assert result["is_speech"] is True # L'état global n'a pas encore changé
        else:
            assert vad_service.is_speaking is False
            assert result["is_speech"] is False # L'état global a changé

    # Vérifier le dernier résultat
    last_result = results[-1]
    assert last_result["is_speech"] is False
    assert last_result["speech_prob"] == 0.1
    assert vad_service.silence_frames_count == settings.VAD_CONSECUTIVE_SILENCE_FRAMES + 1
    assert vad_service.speech_frames_count == 0 # Réinitialisé lors de la détection de silence

@pytest.mark.asyncio # car load_model est async
async def test_vad_reset_state(vad_service: VadService):
    # Modifier l'état interne
    vad_service.audio_buffer = np.array([1.0], dtype=np.float32)
    vad_service.speech_frames_count = 5
    vad_service.silence_frames_count = 3
    vad_service.is_speaking = True
    # Simuler des états internes du modèle (si le modèle les maintient)
    vad_service._h = torch.randn(2, 1, 64)
    vad_service._c = torch.randn(2, 1, 64)
    
    # Appeler reset_state
    vad_service.reset_state()
    
    # Vérifier que tout est réinitialisé
    assert len(vad_service.audio_buffer) == 0
    assert vad_service.speech_frames_count == 0
    assert vad_service.silence_frames_count == 0
    assert vad_service.is_speaking is False
    # Vérifier que les états internes du modèle sont réinitialisés à zéro
    assert torch.equal(vad_service._h, torch.zeros(2, 1, 64))
    assert torch.equal(vad_service._c, torch.zeros(2, 1, 64))

