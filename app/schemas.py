from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
import datetime

# --- Schémas pour le Feedback Kaldi ---

class PhonemeScore(BaseModel):
    ph: str
    score: float

class PronunciationFeedback(BaseModel):
    overall_gop_score: Optional[float] = None
    phonemes: Optional[List[PhonemeScore]] = None
    problematic_phonemes: Optional[List[PhonemeScore]] = None
    # Ajouter d'autres métriques si parsées depuis Kaldi

class FluencyFeedback(BaseModel):
    speech_rate_wpm: Optional[float] = None
    silence_ratio: Optional[float] = None
    filled_pauses_count: Optional[int] = None
    # Ajouter d'autres métriques

class LexicalFeedback(BaseModel):
    type_token_ratio: Optional[float] = None
    repeated_words: Optional[List[str]] = None
    # Ajouter d'autres métriques

class ProsodyFeedback(BaseModel):
    # Définir la structure si des métriques de prosodie sont calculées
    pitch_variation: Optional[float] = None # Exemple
    energy_variation: Optional[float] = None # Exemple

class FeedbackResultItem(BaseModel):
    segment_id: Optional[str] = None # ID unique du segment analysé (ex: turn_id ou UUID de KaldiFeedback)
    turn_number: Optional[int] = None # Numéro du tour correspondant
    pronunciation: Optional[PronunciationFeedback] = None
    fluency: Optional[FluencyFeedback] = None
    lexical_diversity: Optional[LexicalFeedback] = None
    prosody: Optional[ProsodyFeedback] = None
    # Ajouter un champ pour le texte transcrit associé ?
    # text_content: Optional[str] = None

class FeedbackResponse(BaseModel):
    session_id: uuid.UUID
    feedback_results: List[FeedbackResultItem]

# --- Schémas pour le Chat ---

class ChatRequest(BaseModel):
    """Modèle pour les requêtes de chat."""
    message: str
    context: Optional[str] = None

class ChatResponse(BaseModel):
    """Modèle pour les réponses de chat."""
    status: str
    message: str
    data: Dict[str, Any]

# --- Autres Schémas (si nécessaire pour d'autres endpoints) ---

# Schémas pour /session/start
class SessionStartRequest(BaseModel):
    scenario_id: Optional[str] = None
    user_id: str
    language: Optional[str] = 'fr'
    goal: Optional[str] = None

class InitialMessage(BaseModel):
    text: str
    audio_url: Optional[str] = None

class SessionStartResponse(BaseModel):
    session_id: uuid.UUID
    websocket_url: str
    initial_message: InitialMessage

# Schémas pour /session/{session_id}/end
class SessionEndResponse(BaseModel):
    message: str
    final_summary: str
    final_summary_url: Optional[str] = None

# Schémas pour les scénarios hybrides
class ScenarioVariable(BaseModel):
    """Représente une variable dans un scénario."""
    name: str
    description: str
    default_value: Optional[str] = None
    type: str = "text"  # text, number, boolean, choice
    options: Optional[List[str]] = None  # Pour le type "choice"
    required: bool = False

class ScenarioStep(BaseModel):
    """Représente une étape dans un scénario."""
    id: str  # Identifiant unique de l'étape (ex: "introduction", "question_1", etc.)
    name: str
    description: str
    prompt_template: str  # Template de prompt pour le LLM avec variables {variable_name}
    expected_variables: Optional[List[str]] = None  # Variables à collecter dans cette étape
    next_steps: Optional[List[str]] = None  # Étapes possibles suivantes
    is_final: bool = False  # Indique si c'est une étape finale

class ScenarioTemplateBase(BaseModel):
    """Schéma de base pour un template de scénario."""
    name: str
    description: str
    initial_prompt: Optional[str] = None
    variables: Dict[str, ScenarioVariable] = Field(default_factory=dict)
    steps: Dict[str, ScenarioStep] = Field(default_factory=dict)
    first_step: str  # ID de la première étape

class ScenarioTemplateCreate(ScenarioTemplateBase):
    """Schéma pour créer un nouveau template de scénario."""
    id: str  # ID unique du scénario (ex: "entretien_simulation")

class ScenarioTemplateUpdate(ScenarioTemplateBase):
    """Schéma pour mettre à jour un template de scénario existant."""
    name: Optional[str] = None
    description: Optional[str] = None
    initial_prompt: Optional[str] = None
    variables: Optional[Dict[str, ScenarioVariable]] = None
    steps: Optional[Dict[str, ScenarioStep]] = None
    first_step: Optional[str] = None

class ScenarioTemplateResponse(ScenarioTemplateBase):
    """Schéma pour la réponse lors de la récupération d'un template de scénario."""
    id: str
    created_at: datetime.datetime

class ScenarioState(BaseModel):
    """Représente l'état actuel d'un scénario en cours d'exécution."""
    current_step: str
    completed_steps: List[str] = Field(default_factory=list)
    variables: Dict[str, Any] = Field(default_factory=dict)
