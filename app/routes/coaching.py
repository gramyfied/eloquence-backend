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
from datetime import datetime

from core.database import get_db
from core.auth import get_current_user_id, check_user_access
from core.models import CoachingSession, ScenarioTemplate, Participant
from services.llm_service import LlmService

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
        
        # Vérifier la structure de la table coaching_sessions
        table_info_query = """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'coaching_sessions'
        """
        columns_result = await db.execute(table_info_query)
        columns_data = await columns_result.fetchall()
        columns = [row[0] for row in columns_data] if columns_data else []
        
        # Créer la session dans la base de données en utilisant une requête SQL directe
        # Adapter les colonnes en fonction de celles qui existent réellement
        insert_query = "INSERT INTO coaching_sessions (id, user_id"
        values_part = "VALUES ($1, $2"
        params = [session_id, user_id]
        param_index = 3
        
        if "created_at" in columns:
            insert_query += ", created_at"
            values_part += f", ${param_index}"
            params.append(datetime.utcnow())
            param_index += 1
        
        # Finaliser la requête
        insert_query += f") {values_part})"
        
        await db.execute(insert_query, params)
        
        return {
            "session_id": str(session_id),
            "user_id": user_id,
            "status": "initialized"
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
        llm_service = LlmService()
        logger.info("Utilisation du service LLM local")
        
        # Construire le message pour générer l'exercice
        exercise_prompt = f"""
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
        
        # Créer l'historique avec le message système et le prompt
        history = [
            {"role": "system", "content": "Tu es un coach vocal qui génère des exercices de diction et d'élocution."},
            {"role": "user", "content": exercise_prompt}
        ]
        
        # Créer le contexte du scénario
        scenario_context = None
        if request.context:
            scenario_context = {
                "name": "exercise_generation",
                "goal": f"Générer un exercice de {request.exercise_type}",
                "current_step": "generation",
                "variables": request.context
            }
        
        # Générer l'exercice
        result = await llm_service.generate(
            history=history,
            scenario_context=scenario_context
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
        
        # Construire la réponse
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
