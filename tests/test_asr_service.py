import pytest
import asyncio
import numpy as np
import io
import soundfile as sf
from unittest.mock import MagicMock, patch, AsyncMock # Import AsyncMock if needed for async methods
from typing import Tuple, Iterable, Any, Generator

# Importer la classe à tester
from services.asr_service import AsrService
# Importer les settings pour les valeurs par défaut
from core.config import settings

# Mock pour simuler les segments retournés par faster-whisper
# Définir une structure plus proche de l'original si possible
class MockSegment:
    def __init__(self, text: str):
        self.text = text

class MockTranscriptionInfo:
    def __init__(self, language: str = "fr", language_probability: float = 0.95):
        self.language = language
        self.language_probability = language_probability

# Type hint pour le retour de la fixture
ASRFixtureReturnType = Tuple[AsrService, MagicMock]

# Fixture pour initialiser le service ASR
@pytest.fixture
def asr_service(mocker: MagicMock) -> Generator[ASRFixtureReturnType, None, None]:
    # Mocker WhisperModel avant d'instancier AsrService
    # Créer un mock pour l'instance de WhisperModel
    mock_whisper_model_instance = mocker.MagicMock()
    
    # Mocker le constructeur de WhisperModel pour qu'il retourne notre mock
    mock_whisper_model_class = mocker.patch(
        'services.asr_service.WhisperModel',
        return_value=mock_whisper_model_instance
    )

    # Instancier le service ASR
    service = AsrService()
    
    # Remplacer explicitement le modèle chargé par le mock
    service.model = mock_whisper_model_instance
    
    # Retourner le service et l'instance mockée du modèle pour les tests
    yield service, mock_whisper_model_instance
    
    # Nettoyage si nécessaire (pas obligatoire avec mocker)

# Test de la transcription asynchrone avec mocking
@pytest.mark.asyncio
async def test_transcribe_success(asr_service: ASRFixtureReturnType, mocker: MagicMock):
    service, mock_whisper_model = asr_service

    # Mocker soundfile.read
    mock_read = mocker.patch('soundfile.read', autospec=True)
    sample_rate = 16000
    duration = 2
    num_samples = sample_rate * duration
    # Simuler des données audio float32 comme attendu par Whisper
    mock_audio_data_np = np.random.rand(num_samples).astype(np.float32)
    mock_read.return_value = (mock_audio_data_np, sample_rate)
    
    # Simuler la sortie de model.transcribe: (segments, info)
    mock_segments: Iterable[MockSegment] = [MockSegment("Bonjour"), MockSegment(" le monde")]
    mock_info = MockTranscriptionInfo(language="fr", language_probability=0.98)
    # Configurer le mock pour retourner le tuple attendu
    mock_whisper_model.transcribe.return_value = (mock_segments, mock_info)

    # Créer des données audio bytes (PCM 16-bit simulé)
    dummy_audio_bytes = np.random.randint(-1000, 1000, size=num_samples, dtype=np.int16).tobytes()

    # Appeler la méthode à tester
    language = "fr"
    transcription: str = await service.transcribe(dummy_audio_bytes, language)
    
    # Vérifications
    assert transcription == "Bonjour le monde"
    
    # Vérifier que soundfile.read a été appelé correctement
    mock_read.assert_called_once()
    call_args_read, _ = mock_read.call_args
    assert isinstance(call_args_read[0], io.BytesIO)
    assert call_args_read[0].getvalue() == dummy_audio_bytes

    # Vérifier que model.transcribe a été appelé avec les bonnes données et options
    mock_whisper_model.transcribe.assert_called_once()
    call_args_transcribe, call_kwargs_transcribe = mock_whisper_model.transcribe.call_args
    
    # Vérifier l'audio passé à transcribe
    assert isinstance(call_args_transcribe[0], np.ndarray)
    assert call_args_transcribe[0].dtype == np.float32
    assert np.array_equal(call_args_transcribe[0], mock_audio_data_np)
    
    # Vérifier les kwargs passés à transcribe
    assert call_kwargs_transcribe.get("language") == language
    # Vérifier que les paramètres par défaut sont utilisés
    assert call_kwargs_transcribe.get("beam_size") == 5  # Valeur codée en dur dans asr_service.py

# Test de la gestion d'erreur pendant la transcription synchrone
@pytest.mark.asyncio
async def test_transcribe_sync_error(asr_service: ASRFixtureReturnType, mocker: MagicMock):
    service, mock_whisper_model = asr_service

    # Mocker soundfile.read pour retourner des données valides
    mock_read = mocker.patch('soundfile.read', autospec=True)
    mock_audio_data_np = np.zeros(16000, dtype=np.float32)
    mock_sample_rate = 16000
    mock_read.return_value = (mock_audio_data_np, mock_sample_rate)
    
    # Configurer le mock WhisperModel pour qu'il lève une exception
    error_message = "Erreur Whisper simulée"
    mock_whisper_model.transcribe.side_effect = Exception(error_message)

    # Créer des données audio bytes
    dummy_audio_bytes = np.zeros(32000, dtype=np.int16).tobytes() # 2 secondes

    # Appeler la méthode et vérifier que l'exception est levée et correctement encapsulée
    with pytest.raises(RuntimeError, match=f"Erreur ASR: {error_message}"):
        await service.transcribe(dummy_audio_bytes, "fr")

    # Vérifier que transcribe a bien été appelé
    mock_whisper_model.transcribe.assert_called_once()

# Test du cas où le modèle n'est pas chargé
@pytest.mark.asyncio
async def test_transcribe_model_not_loaded(asr_service: ASRFixtureReturnType):
    service, _ = asr_service 
    service.model = None # Assurer que le modèle n'est pas chargé
    dummy_audio_bytes = np.zeros(16000, dtype=np.int16).tobytes()

    with pytest.raises(RuntimeError, match="Le modèle ASR n'est pas chargé"):
        await service.transcribe(dummy_audio_bytes, "fr")

# Test de la conversion audio échouant (mock soundfile.read levant une erreur)
@pytest.mark.asyncio
async def test_audio_conversion_error(asr_service: ASRFixtureReturnType, mocker: MagicMock):
    service, mock_whisper_model = asr_service

    # Mocker soundfile.read pour lever une exception
    error_message = "Format audio non supporté"
    mock_read = mocker.patch('soundfile.read', side_effect=sf.SoundFileError(error_message), autospec=True)

    dummy_audio_bytes = b"dummy invalid audio bytes"

    # Appeler la méthode et vérifier que l'exception est levée
    # L'exception devrait être encapsulée par transcribe
    with pytest.raises(RuntimeError, match=f"Erreur ASR: {error_message}"):
        await service.transcribe(dummy_audio_bytes, "fr")

    # Vérifier que soundfile.read a été appelé
    mock_read.assert_called_once()
    # Vérifier que model.transcribe n'a PAS été appelé car la conversion a échoué avant
    mock_whisper_model.transcribe.assert_not_called()

