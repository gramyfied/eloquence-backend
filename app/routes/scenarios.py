# DEBUG-MARKER-SCENARIOS-V1
"""
Routes pour la gestion des scénarios de coaching.
"""

import logging
import json
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.auth import get_current_user_id
from core.config import settings
from core.models import ScenarioTemplate

logger = logging.getLogger(__name__)

router = APIRouter()

class ScenarioResponse(BaseModel):
    id: str
    name: str
    description: str
    type: str
    difficulty: Optional[str] = None
    language: str = "fr"
    tags: Optional[List[str]] = None
    preview_image: Optional[str] = None

@router.get("/scenarios/", response_model=List[ScenarioResponse]) # Ajout du slash final
async def list_scenarios(
    type: Optional[str] = None,
    difficulty: Optional[str] = None,
    language: str = "fr",
    # db: AsyncSession = Depends(get_db), # Commenté pour débogage 500
    # current_user_id: str = Depends(get_current_user_id) # Commenté pour débogage 500
):
    """
    Liste tous les scénarios disponibles.
    MODIFIÉ POUR DÉBOGAGE 500 : Retourne une liste factice.
    """
    logger.warning("<<<< EXÉCUTION DE list_scenarios MODIFIÉE POUR DÉBOGAGE 500 >>>>")
    try:
        # Retourner une liste factice pour le test
        dummy_scenarios = [
            {
                "id": "demo-1",
                "name": "Entretien d'embauche (Factice)",
                "description": "Simulation d'un entretien d'embauche.",
                "type": "entretien",
                "difficulty": "medium",
                "language": "fr",
                "tags": ["emploi", "communication"],
                "preview_image": None
            },
            {
                "id": "demo-2",
                "name": "Présentation Projet (Factice)",
                "description": "Simulation d'une présentation de projet.",
                "type": "presentation",
                "difficulty": "hard",
                "language": "fr",
                "tags": ["professionnel", "discours"],
                "preview_image": None
            }
        ]
        
        # Filtrer la liste factice si des paramètres sont fournis (pour simuler le comportement)
        filtered_scenarios = []
        for scenario in dummy_scenarios:
             if (type and scenario.get("type") != type) or \
                (difficulty and scenario.get("difficulty") != difficulty) or \
                (language and scenario.get("language", "fr") != language):
                 continue
             filtered_scenarios.append(scenario)

        return filtered_scenarios
        
    except Exception as e:
        # Ce bloc ne devrait pas être atteint avec la logique factice,
        # mais on le garde par sécurité.
        logger.error(f"Erreur inattendue dans list_scenarios (version factice): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur interne lors de la récupération des scénarios factices: {str(e)}"
        )

@router.get("/scenarios/{scenario_id}", response_model=Dict[str, Any])
async def get_scenario(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Récupère un scénario spécifique par son ID.
    """
    try:
        # Chercher le scénario dans la base de données
        query = """
        SELECT id, name, description, type, difficulty, language, tags, preview_image, structure, initial_prompt
        FROM scenario_templates
        WHERE id = $1
        """
        
        result = await db.execute(query, [scenario_id])
        scenario_data = await result.fetchone()
        
        if scenario_data:
            # Construire la réponse
            scenario = {
                "id": scenario_data[0],
                "name": scenario_data[1],
                "description": scenario_data[2],
                "type": scenario_data[3],
                "difficulty": scenario_data[4],
                "language": scenario_data[5],
                "tags": scenario_data[6] if scenario_data[6] else [],
                "preview_image": scenario_data[7],
                "structure": json.loads(scenario_data[8]) if scenario_data[8] else {},
                "initial_prompt": scenario_data[9]
            }
            
            return scenario
        else:
            # Chercher le scénario dans les fichiers d'exemple
            examples_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "examples")
            
            example_files = [
                "scenario_entretien_embauche.json",
                "scenario_presentation.json",
                "scenario_conversation.json"
            ]
            
            for filename in example_files:
                file_path = os.path.join(examples_dir, filename)
                if os.path.exists(file_path):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            
                            if data.get("id") == scenario_id or filename.split(".")[0] == scenario_id:
                                return data
                    except Exception as e:
                        logger.error(f"Erreur lors du chargement du scénario {filename}: {e}")
            
            # Si le scénario n'est pas trouvé
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scénario {scenario_id} non trouvé"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du scénario {scenario_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération du scénario: {str(e)}"
        )

@router.post("/scenarios", status_code=status.HTTP_201_CREATED)
async def create_scenario(
    scenario: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Crée un nouveau scénario.
    """
    try:
        # Générer un ID si non fourni
        if "id" not in scenario:
            scenario["id"] = str(uuid.uuid4())
        
        # Valider les champs obligatoires
        required_fields = ["name", "description", "type"]
        for field in required_fields:
            if field not in scenario:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Le champ '{field}' est obligatoire"
                )
        
        # Préparer les données pour l'insertion
        structure = json.dumps(scenario.get("structure", {})) if "structure" in scenario else None
        tags = scenario.get("tags", [])
        
        # Insérer le scénario dans la base de données
        query = """
        INSERT INTO scenario_templates (
            id, name, description, type, difficulty, language, tags, preview_image, structure, initial_prompt, created_by
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
        )
        """
        
        await db.execute(
            query,
            [
                scenario["id"],
                scenario["name"],
                scenario["description"],
                scenario["type"],
                scenario.get("difficulty", "medium"),
                scenario.get("language", "fr"),
                tags,
                scenario.get("preview_image"),
                structure,
                scenario.get("initial_prompt"),
                current_user_id
            ]
        )
        
        return {
            "id": scenario["id"],
            "message": "Scénario créé avec succès"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la création du scénario: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la création du scénario: {str(e)}"
        )