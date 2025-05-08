# DEBUG-MARKER-SCENARIOS-V2
import logging # Assurez-vous que logging est importé
logger_scenarios = logging.getLogger(__name__)
logger_scenarios.error("<<<<< SCENARIOS.PY MODULE CHARGÉ - V2 >>>>>") # Log au chargement du module

"""
Routes pour la gestion des scénarios de coaching.
"""

# import logging # Déplacé plus haut
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

@router.get("/scenarios/", response_model=List[ScenarioResponse], include_in_schema=True)
async def list_scenarios(
    type: Optional[str] = Query(None, description="Filtrer par type de scénario"),
    difficulty: Optional[str] = Query(None, description="Filtrer par difficulté"),
    language: str = Query("fr", description="Langue des scénarios"),
    # db: AsyncSession = Depends(get_db), # Gardé commenté pour l'instant
    # current_user_id: str = Depends(get_current_user_id) # Gardé commenté pour l'instant
):
    """
    Liste tous les scénarios disponibles en lisant les fichiers JSON du répertoire 'examples'.
    """
    logger_scenarios.error("<<<<< DANS list_scenarios - V3 - Lecture depuis /examples/ >>>>>")
    
    scenarios = []
    # Chemin vers le répertoire 'examples', relatif à l'emplacement de ce fichier (app/routes/scenarios.py)
    # __file__ -> app/routes/scenarios.py
    # os.path.dirname(__file__) -> app/routes
    # os.path.dirname(os.path.dirname(__file__)) -> app
    # os.path.dirname(os.path.dirname(os.path.dirname(__file__))) -> racine du projet (eloquence_backend_py)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    examples_path = os.path.join(base_dir, "examples")
    logger_scenarios.info(f"Recherche de scénarios dans : {examples_path}")

    if not os.path.isdir(examples_path):
        logger_scenarios.error(f"Le répertoire des scénarios '{examples_path}' n'existe pas.")
        # Retourner une liste vide ou une erreur appropriée si le répertoire n'existe pas
        # Pour l'instant, nous allons lever une exception pour être clair sur le problème.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Configuration incorrecte du serveur: Répertoire des scénarios non trouvé à {examples_path}"
        )

    try:
        for filename in os.listdir(examples_path):
            if filename.startswith("scenario_") and filename.endswith(".json"):
                file_path = os.path.join(examples_path, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        
                        # Appliquer les filtres
                        if type and data.get("type") != type:
                            continue
                        if difficulty and data.get("difficulty") != difficulty:
                            continue
                        if language and data.get("language", "fr") != language: # fr par défaut si non spécifié dans JSON
                            continue
                        
                        # Utiliser le nom du fichier (sans .json) comme ID si non présent dans le JSON
                        scenario_id = data.get("id", filename[:-5]) # exemple: scenario_entretien_embauche

                        scenarios.append(
                            ScenarioResponse(
                                id=scenario_id,
                                name=data.get("name", "Nom non défini"),
                                description=data.get("description", "Description non définie"),
                                type=data.get("type", "inconnu"),
                                difficulty=data.get("difficulty"),
                                language=data.get("language", "fr"),
                                tags=data.get("tags", []),
                                preview_image=data.get("preview_image")
                            )
                        )
                except json.JSONDecodeError:
                    logger_scenarios.error(f"Erreur de décodage JSON pour le fichier: {file_path}")
                except Exception as e_file:
                    logger_scenarios.error(f"Erreur lors du traitement du fichier {file_path}: {e_file}")
        
        logger_scenarios.info(f"{len(scenarios)} scénarios trouvés et filtrés.")
        return scenarios
        
    except Exception as e:
        logger_scenarios.error(f"Erreur inattendue dans list_scenarios (V3): {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur interne du serveur lors de la récupération des scénarios: {str(e)}"
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