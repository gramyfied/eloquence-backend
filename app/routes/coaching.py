"""
Routes pour les services de coaching.
"""

import logging
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.database import get_db
from core.auth import get_current_user_id, check_user_access
from core.models import CoachingSession, ScenarioTemplate, Participant
from services.llm_service import LlmService
from services.llm_service_local import LlmServiceLocal

logger = logging.getLogger(__name__)

router = APIRouter()

class ExerciseRequest(BaseModel):
    exercise_type: Optional[str] = "diction"
    difficulty: Optional[str] = "medium"
    language: Optional[str] = "fr"
    context: Optional[Dict[str, Any]] = None

class ExerciseResponse(BaseModel):
    exercise_id: str
    title: str
    description: str
    instructions: str
    content: str

@router.get("/init")
async def init_coaching(
    user_id: str = Query(..., description="ID de l'utilisateur"),
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Initialise une session de coaching.
    """
    # Vérifier que l'utilisateur est autorisé
    if not check_user_access(user_id, current_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'êtes pas autorisé à initialiser une session pour cet utilisateur"
        )
    
    try:
        # Créer une nouvelle session
        session_id = uuid.uuid4()
        
        # Créer la session dans la base de données
        db_session = CoachingSession(
            id=session_id,
            user_id=user_id,
            language="fr"
        )
        
        # Créer un participant (l'utilisateur)
        participant = Participant(
            id=uuid.uuid4(),
            session_id=session_id,
            name="Utilisateur",
            role="user",
            is_primary=True
        )
        
        # Ajouter à la base de données
        db.add(db_session)
        db.add(participant)
        await db.commit()
        
        return {
            "status": "success",
            "message": "Session de coaching initialisée",
            "data": {
                "session_id": str(session_id)
            }
        }
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation de la session de coaching: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'initialisation de la session de coaching: {str(e)}"
        )

@router.post("/exercise/generate", response_model=ExerciseResponse)
async def generate_exercise(
    request: ExerciseRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Génère un exercice de coaching.
    """
    try:
        # Initialiser le service LLM
        try:
            llm_service = LlmServiceLocal()
            logger.info("Utilisation du service LLM local")
        except Exception as e:
            logger.warning(f"Service LLM local non disponible: {e}. Utilisation du service distant.")
            llm_service = LlmService()
        
        # Construire le prompt pour générer l'exercice
        prompt = f"""
        Génère un exercice de {request.exercise_type} en français de niveau {request.difficulty}.
        L'exercice doit inclure:
        1. Un titre
        2. Une brève description
        3. Des instructions claires
        4. Le contenu de l'exercice (texte à prononcer, questions, etc.)
        
        Format de réponse:
        {{
            "title": "Titre de l'exercice",
            "description": "Description de l'exercice",
            "instructions": "Instructions détaillées",
            "content": "Contenu de l'exercice"
        }}
        """
        
        # Générer l'exercice
        result = await llm_service.generate(
            prompt=prompt,
            context=request.context or {}
        )
        
        # Extraire la réponse
        response_text = result.get("text", "")
        
        # Essayer de parser la réponse comme JSON
        try:
            # Trouver le début et la fin du JSON dans la réponse
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}") + 1
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                exercise_data = json.loads(json_str)
            else:
                # Fallback si le format JSON n'est pas trouvé
                exercise_data = {
                    "title": "Exercice de " + request.exercise_type,
                    "description": "Exercice généré automatiquement",
                    "instructions": "Suivez les instructions ci-dessous",
                    "content": response_text
                }
        except json.JSONDecodeError:
            # Fallback si le parsing JSON échoue
            exercise_data = {
                "title": "Exercice de " + request.exercise_type,
                "description": "Exercice généré automatiquement",
                "instructions": "Suivez les instructions ci-dessous",
                "content": response_text
            }
        
        # Générer un ID pour l'exercice
        exercise_id = f"exercise-{uuid.uuid4()}"
        
        return ExerciseResponse(
            exercise_id=exercise_id,
            title=exercise_data.get("title", "Exercice de " + request.exercise_type),
            description=exercise_data.get("description", "Exercice généré automatiquement"),
            instructions=exercise_data.get("instructions", "Suivez les instructions ci-dessous"),
            content=exercise_data.get("content", response_text)
        )
    except Exception as e:
        logger.error(f"Erreur lors de la génération de l'exercice: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la génération de l'exercice: {str(e)}"
        )
