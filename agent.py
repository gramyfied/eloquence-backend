import os
import asyncio
import logging
import numpy as np
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# Importer les composants LiveKit
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    function_tool,
    RunContext,
)
from livekit.plugins import silero

# Importer les adaptateurs pour les services existants
from adapters.whisper_adapter import WhisperAdapter
from adapters.mistral_adapter import MistralAdapter
from adapters.coqui_adapter import CoquiAdapter

# Configurer le logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("eloquence-agent")

# Charger les variables d'environnement
load_dotenv(dotenv_path=".env.local")

class EloquenceAgent(Agent):
    """Agent de coaching vocal Eloquence utilisant LiveKit."""
    
    def __init__(self) -> None:
        # Initialiser les adaptateurs
        self.whisper_adapter = WhisperAdapter()
        self.mistral_adapter = MistralAdapter()
        self.coqui_adapter = CoquiAdapter()
        
        # Initialiser l'agent avec les instructions
        super().__init__(
            instructions=(
                "Vous êtes un coach vocal interactif qui aide les utilisateurs à améliorer "
                "leur expression orale. Votre objectif est de fournir des conseils personnalisés, "
                "des exercices pratiques et des retours constructifs sur la prononciation, "
                "l'intonation, le rythme et la clarté du discours. Utilisez un langage naturel "
                "et conversationnel, avec des contractions et expressions familières. "
                "Soyez concis dans vos réponses et adaptez-vous au contexte de la conversation."
            )
        )
        
        logger.info("Agent Eloquence initialisé avec succès")
    
    async def on_session_start(self, session_id: str):
        """Appelé lorsqu'une session commence."""
        logger.info(f"Session démarrée: {session_id}")
        # Générer un message d'accueil
        await self.session.generate_reply()
    
    async def on_session_end(self, session_id: str):
        """Appelé lorsqu'une session se termine."""
        logger.info(f"Session terminée: {session_id}")
    
    async def on_transcript(self, transcript: str, is_final: bool):
        """Appelé lorsqu'une transcription est disponible."""
        if is_final and transcript:
            logger.info(f"Transcription finale: {transcript}")
    
    async def on_message(self, text: str, metadata: Optional[Dict[str, Any]] = None):
        """Appelé lorsqu'un message est généré par le LLM."""
        emotion = metadata.get("emotion") if metadata else "neutral"
        logger.info(f"Message généré ({emotion}): {text}")
    
    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> Dict[str, Any]:
        """Transcrit l'audio en utilisant l'adaptateur Whisper."""
        result = await self.whisper_adapter.transcribe(audio, sample_rate)
        return {"text": result.get("text", "")}
    
    async def generate(self, prompt: str, conversation_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Génère une réponse en utilisant l'adaptateur Mistral."""
        # Construire le contexte à partir de l'historique
        context = ""
        for turn in conversation_history[-5:]:  # Limiter à 5 derniers tours pour la mémoire
            role = "user" if turn.get("role") == "user" else "assistant"
            context += f"{role}: {turn.get('content', '')}\n"
        
        # Ajouter le prompt actuel
        full_prompt = f"{context}\nuser: {prompt}\nassistant:"
        
        # Générer la réponse
        system_prompt = self.instructions
        result = await self.mistral_adapter.generate(full_prompt, system_prompt)
        
        return {
            "text": result.get("text", ""),
            "emotion": result.get("emotion", "neutral")
        }
    
    async def synthesize(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Synthétise du texte en audio en utilisant l'adaptateur Coqui."""
        # Extraire l'émotion des métadonnées si disponible
        emotion = metadata.get("emotion") if metadata else None
        
        # Synthétiser l'audio
        result = await self.coqui_adapter.synthesize(text, emotion)
        
        return {
            "audio": result.get("audio", b""),
            "sample_rate": result.get("sample_rate", 22050)
        }
    
    @function_tool
    async def evaluate_pronunciation(self, context: RunContext, transcription: str):
        """Évalue la prononciation de l'utilisateur et fournit des conseils d'amélioration.
        Args:
            transcription: Le texte transcrit de la parole de l'utilisateur
        """
        # Exemple simple pour démonstration
        return {
            "feedback": "Votre prononciation est claire et bien articulée.",
            "score": 85,
            "improvement_tips": "Travaillez sur le rythme des phrases longues."
        }

def prewarm(proc):
    """Précharge les modèles pour optimiser les performances."""
    # Précharger le VAD pour optimiser les performances
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("VAD préchargé avec succès")

async def entrypoint(ctx: JobContext):
    """Point d'entrée principal de l'agent."""
    logger.info(f"Connexion à la room {ctx.room.name}")
    
    # Se connecter à la room et s'abonner à l'audio uniquement
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    
    # Attendre qu'un participant se connecte
    participant = await ctx.wait_for_participant()
    logger.info(f"Participant connecté: {participant.identity}")
    
    # Créer et démarrer l'agent Eloquence
    agent = EloquenceAgent()
    
    # Créer une session avec le VAD préchargé
    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        # Paramètres d'endpointing pour la détection de fin de parole
        min_endpointing_delay=0.5,  # Attente minimale après silence détecté
        max_endpointing_delay=2.0,  # Attente maximale après silence détecté
    )
    
    # Démarrer la session avec l'agent et le participant
    await session.start(
        room=ctx.room,
        agent=agent,
        participant=participant,
    )
    
    logger.info("Agent Eloquence démarré avec succès")

if __name__ == "__main__":
    # Exécuter l'application
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )