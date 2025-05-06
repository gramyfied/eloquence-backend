import torch
import torchaudio
import numpy as np
import logging
from typing import Tuple, Optional, Dict, Any
from collections import deque

from core.config import settings

logger = logging.getLogger(__name__)

class VadService:
    """
    Service pour la Détection d'Activité Vocale (VAD) utilisant Silero VAD PyTorch.
    Implémente une détection robuste avec comptage de frames consécutives.
    """
    def __init__(self,
                 threshold: float = settings.VAD_THRESHOLD,
                 sample_rate: int = 16000,
                 window_size_samples: int = 512): # Taille de fenêtre typique pour Silero VAD
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.window_size_samples = window_size_samples
        self.model = None # Utiliser l'attribut model pour le modèle PyTorch
        self.utils = None
        self._h = None # État caché initial (sera un tenseur PyTorch)
        self._c = None # État cellule initial (sera un tenseur PyTorch)
        self.audio_buffer = np.array([], dtype=np.float32)
        
        # Nouveaux attributs pour la détection robuste
        self.speech_frames_count = 0
        self.silence_frames_count = 0
        self.consecutive_speech_frames = settings.VAD_CONSECUTIVE_SPEECH_FRAMES
        self.consecutive_silence_frames = settings.VAD_CONSECUTIVE_SILENCE_FRAMES
        self.last_probabilities = deque(maxlen=5)  # Garder un historique des dernières probabilités
        self.is_speaking = False  # État actuel (parole ou silence)

    async def load_model(self):
        """Charge le modèle VAD PyTorch."""
        try:
            logger.info("Début du chargement du modèle VAD PyTorch via torch.hub.load...")
            
            # Télécharger et charger le modèle PyTorch (sans force_reload pour utiliser le cache)
            self.model, self.utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                           model='silero_vad',
                                           force_reload=False)
            logger.info("Modèle VAD PyTorch téléchargé et chargé en mémoire.")

            logger.info("Mise en mode évaluation du modèle VAD PyTorch...")
            self.model.eval() # Mettre le modèle en mode évaluation
            logger.info("Modèle VAD PyTorch mis en mode évaluation.")
            
            # Initialiser les états cachés et de cellule après le chargement du modèle
            # La forme correcte dépend du modèle chargé, mais (2, 1, 64) est typique
            self._h = torch.zeros(2, 1, 64)
            self._c = torch.zeros(2, 1, 64)
            logger.info("États cachés et de cellule du VAD initialisés.")

            logger.info("Initialisation du service VAD terminée avec succès.")
        except Exception as e:
            logger.error(f"Erreur lors du chargement du modèle VAD PyTorch: {e}", exc_info=True)
            raise

    def _bytes_to_audio_tensor(self, audio_bytes: bytes) -> Optional[torch.Tensor]:
        """Convertit les bytes audio (PCM 16-bit) en tenseur float 16kHz."""
        try:
            # Convertir les bytes en array numpy int16
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
            # Convertir en float32 et normaliser entre -1 et 1
            audio_float = audio_np.astype(np.float32) / 32768.0
            # Convertir en tenseur PyTorch
            audio_tensor = torch.from_numpy(audio_float)
            # Assurer le bon sample rate (si nécessaire, bien que le flux soit attendu en 16k)
            # Ici, on suppose que l'audio entrant est déjà en 16kHz mono
            return audio_tensor
        except Exception as e:
            logger.error(f"Erreur lors de la conversion bytes vers tenseur audio: {e}")
            return None

    def process_chunk(self, audio_chunk_bytes: bytes) -> Dict[str, Any]:
        """
        Traite un chunk audio et retourne un dictionnaire contenant:
        - speech_prob: la probabilité de parole brute
        - is_speech: True si la parole est détectée de manière robuste, False sinon
        - confidence: niveau de confiance dans la détection (0-1)
        
        Utilise un compteur de frames consécutives pour une détection plus robuste.
        """
        if self.model is None:
            logger.error("Le modèle VAD n'est pas chargé.")
            return {"speech_prob": None, "is_speech": False, "confidence": 0.0}

        audio_tensor = self._bytes_to_audio_tensor(audio_chunk_bytes)
        if audio_tensor is None:
            return {"speech_prob": None, "is_speech": False, "confidence": 0.0}

        # Ajouter le nouveau chunk au buffer
        self.audio_buffer = np.concatenate((self.audio_buffer, audio_tensor.numpy()))

        speech_prob = None
        # Traiter autant de fenêtres complètes que possible depuis le buffer
        while self.audio_buffer.shape[0] >= self.window_size_samples:
            window_np = self.audio_buffer[:self.window_size_samples]
            self.audio_buffer = self.audio_buffer[self.window_size_samples:] # Consommer la fenêtre

            # Convertir la fenêtre en tenseur PyTorch et ajouter la dimension batch
            audio_tensor_window = torch.from_numpy(window_np).unsqueeze(0)

            # Exécuter l'inférence PyTorch
            with torch.no_grad():
                # Passer les états cachés et de cellule actuels
                out, self._h, self._c = self.model(audio_tensor_window, self._h, self._c)

            speech_prob = out.item() # Probabilité de parole pour cette fenêtre
            self.last_probabilities.append(speech_prob)
            
            # Logique de détection robuste avec comptage de frames consécutives
            if speech_prob >= self.threshold:
                self.speech_frames_count += 1
                self.silence_frames_count = 0
                if self.speech_frames_count >= self.consecutive_speech_frames and not self.is_speaking:
                    self.is_speaking = True
                    logger.debug(f"Début de parole détecté avec probabilité {speech_prob:.2f}")
            else:
                self.silence_frames_count += 1
                self.speech_frames_count = 0
                if self.silence_frames_count >= self.consecutive_silence_frames and self.is_speaking:
                    self.is_speaking = False
                    logger.debug(f"Fin de parole détectée avec probabilité {speech_prob:.2f}")

        # Si aucune fenêtre n'a été traitée, retourner les valeurs par défaut
        if speech_prob is None:
            return {"speech_prob": None, "is_speech": self.is_speaking, "confidence": 0.0}
        
        # Calculer la confiance basée sur l'historique des probabilités
        avg_prob = sum(self.last_probabilities) / len(self.last_probabilities) if self.last_probabilities else 0
        confidence = abs(avg_prob - 0.5) * 2  # Transformer [0,1] en [0,1] avec 0.5 -> 0 et 0/1 -> 1
        
        return {
            "speech_prob": speech_prob,
            "is_speech": self.is_speaking,
            "confidence": confidence
        }

    def reset_state(self):
        """Réinitialise l'état interne du VAD (pour une nouvelle session/segment)."""
        # Réinitialiser les états cachés et de cellule en tenseurs PyTorch
        self._h = torch.zeros(2, 1, 64)
        self._c = torch.zeros(2, 1, 64)
        self.audio_buffer = np.array([], dtype=np.float32)
        
        # Réinitialiser les compteurs et l'état de détection robuste
        self.speech_frames_count = 0
        self.silence_frames_count = 0
        self.last_probabilities.clear()
        self.is_speaking = False
        
        logger.debug("État du VAD réinitialisé.")

# Note: La logique de décision (speech start/end) basée sur les probabilités
# et les durées/seuils sera probablement gérée dans l'Orchestrator
# en utilisant les probabilités retournées par process_chunk.
