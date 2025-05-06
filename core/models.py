import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, ForeignKey, Text, Float, JSON, Boolean
)
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
import uuid

from core.config import settings # Pour l'URL de la base de données si besoin ici

# Base pour les modèles déclaratifs
Base = declarative_base()

class ScenarioTemplate(Base):
    __tablename__ = "scenario_templates"

    id = Column(String, primary_key=True) # ID unique du scénario (ex: "entretien_simulation")
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    initial_prompt = Column(Text, nullable=True) # Prompt initial pour le LLM au début
    structure = Column(JSON, nullable=True) # Structure JSON (étapes, variables, points clés)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class AgentProfile(Base):
    """
    Profil d'un agent IA pouvant participer à une session.
    Permet de définir différents types d'agents avec des personnalités et rôles variés.
    """
    __tablename__ = "agent_profiles"

    id = Column(String, primary_key=True) # ID unique du profil (ex: "coach", "interviewer", "student")
    name = Column(String, nullable=False) # Nom de l'agent
    description = Column(Text, nullable=True) # Description du rôle et de la personnalité
    system_prompt = Column(Text, nullable=True) # Prompt système spécifique pour cet agent
    voice_id = Column(String, nullable=True) # ID de la voix à utiliser pour cet agent
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relation inverse
    participants = relationship("Participant", back_populates="agent_profile")

class CoachingSession(Base):
    __tablename__ = "coaching_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, index=True) # ID utilisateur principal (peut venir de Node.js/Supabase)
    scenario_template_id = Column(String, ForeignKey("scenario_templates.id"), nullable=True, index=True) # Clé étrangère vers le scénario
    language = Column(String(10), default='fr')
    goal = Column(Text, nullable=True) # Objectif spécifique de cette session
    current_scenario_state = Column(JSON, nullable=True) # État actuel (ex: étape, variables remplies)
    # La colonne is_multi_agent est commentée car elle n'existe pas encore dans la base de données
    # is_multi_agent = Column(Boolean, default=False) # Indique si la session utilise plusieurs agents
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="active") # Ex: active, ended, error

    scenario_template = relationship("ScenarioTemplate") # Relation vers le template
    turns = relationship("SessionTurn", back_populates="session", order_by="SessionTurn.turn_number")
    participants = relationship("Participant", back_populates="session")

class Participant(Base):
    """
    Représente un participant à une session (utilisateur ou agent IA).
    Permet de gérer plusieurs participants dans une même session.
    """
    __tablename__ = "participants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("coaching_sessions.id"), nullable=False, index=True)
    agent_profile_id = Column(String, ForeignKey("agent_profiles.id"), nullable=True) # Null pour un utilisateur humain
    name = Column(String, nullable=False) # Nom du participant
    role = Column(String(20), nullable=False) # 'user' ou 'agent'
    is_primary = Column(Boolean, default=False) # Indique si c'est le participant principal
    voice_id = Column(String, nullable=True) # ID de la voix à utiliser (pour les agents)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    session = relationship("CoachingSession", back_populates="participants")
    agent_profile = relationship("AgentProfile", back_populates="participants")
    turns = relationship("SessionTurn", back_populates="participant")

class SessionTurn(Base):
    __tablename__ = "session_turns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("coaching_sessions.id"), nullable=False, index=True)
    participant_id = Column(UUID(as_uuid=True), ForeignKey("participants.id"), nullable=False, index=True)
    turn_number = Column(Integer, nullable=False) # Numéro du tour dans la session
    role = Column(String(10), nullable=False) # 'user' ou 'agent'
    text_content = Column(Text, nullable=True) # Transcription (user) ou réponse (agent)
    audio_path = Column(String, nullable=True) # Chemin vers le fichier audio - stocké localement ou S3
    emotion_label = Column(String(50), nullable=True) # Émotion détectée/demandée
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    session = relationship("CoachingSession", back_populates="turns")
    participant = relationship("Participant", back_populates="turns")
    feedback = relationship("KaldiFeedback", back_populates="turn", uselist=False) # One-to-one

class KaldiFeedback(Base):
    __tablename__ = "kaldi_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    turn_id = Column(UUID(as_uuid=True), ForeignKey("session_turns.id"), nullable=False, unique=True, index=True)
    # Utiliser JSON pour stocker les résultats structurés
    # Cela offre de la flexibilité si le format des résultats Kaldi évolue
    pronunciation_scores = Column(JSON, nullable=True) # Contient overall_gop, phonemes, problematic_phonemes
    fluency_metrics = Column(JSON, nullable=True) # Contient speech_rate, silence_ratio, filled_pauses
    lexical_metrics = Column(JSON, nullable=True) # Contient ttr, repeated_words
    prosody_metrics = Column(JSON, nullable=True) # Structure à définir
    personalized_feedback = Column(JSON, nullable=True) # Feedback personnalisé généré par le LLM
    raw_kaldi_output_path = Column(String, nullable=True) # Chemin vers les logs/fichiers bruts Kaldi si besoin
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    turn = relationship("SessionTurn", back_populates="feedback")

# Classes pour l'orchestrateur
class Session(Base):
    """
    Modèle pour stocker les données de session de l'orchestrateur.
    """
    __tablename__ = "orchestrator_sessions"

    id = Column(String, primary_key=True)
    history = Column(Text, nullable=True)  # JSON stringifié de l'historique des messages
    scenario_context = Column(Text, nullable=True)  # JSON stringifié du contexte du scénario
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    latency_metrics = Column(Text, nullable=True)  # JSON stringifié des métriques de latence
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    segments = relationship("SessionSegment", back_populates="session")

class SessionSegment(Base):
    """
    Modèle pour stocker les segments audio d'une session.
    """
    __tablename__ = "orchestrator_segments"

    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("orchestrator_sessions.id"), nullable=False, index=True)
    audio_path = Column(String, nullable=False)
    transcript_path = Column(String, nullable=True)
    kaldi_result_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    session = relationship("Session", back_populates="segments")


# --- Configuration et Moteur (peut être déplacé dans database.py) ---
# Utiliser l'URL de la base de données depuis les settings
# Note: Pour l'async, on utilisera create_async_engine dans database.py
# Ceci est juste pour référence ou pour des scripts synchrones
# engine = create_engine(settings.DATABASE_URL)
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Fonction pour créer les tables (utile pour les tests ou initialisation simple)
# def create_db_tables():
#     Base.metadata.create_all(bind=engine)

# if __name__ == "__main__":
#     # Crée les tables si le script est exécuté directement
#     print("Création des tables de la base de données...")
#     create_db_tables()
#     print("Tables créées.")