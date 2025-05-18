"""
Routes REST pour la gestion des templates de scénarios hybrides.
"""

import logging
import json
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete

from core.database import get_db
from core.auth import get_current_user_id, check_user_access
from core.models import ScenarioTemplate
from app.schemas import (
    ScenarioTemplateCreate,
    ScenarioTemplateUpdate,
    ScenarioTemplateResponse,
    ScenarioVariable,
    ScenarioStep
)

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/scenarios", response_model=List[ScenarioTemplateResponse])
async def get_scenarios(
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Récupère tous les templates de scénarios disponibles.
    """
    # Dans une version future, on pourrait filtrer par droits d'accès
    query = select(ScenarioTemplate)
    result = await db.execute(query)
    scenarios = result.scalars().all()
    
    # Convertir les objets ScenarioTemplate en ScenarioTemplateResponse
    response = []
    for scenario in scenarios:
        structure = json.loads(scenario.structure) if scenario.structure else {}
        response.append(
            ScenarioTemplateResponse(
                id=scenario.id,
                name=scenario.name,
                description=scenario.description or "",
                initial_prompt=scenario.initial_prompt,
                variables=structure.get("variables", {}),
                steps=structure.get("steps", {}),
                first_step=structure.get("first_step", ""),
                created_at=scenario.created_at
            )
        )
    
    return response

@router.get("/scenarios/{scenario_id}", response_model=ScenarioTemplateResponse)
async def get_scenario(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Récupère un template de scénario spécifique par son ID.
    """
    query = select(ScenarioTemplate).where(ScenarioTemplate.id == scenario_id)
    result = await db.execute(query)
    scenario = result.scalar_one_or_none()
    
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scénario {scenario_id} non trouvé"
        )
    
    # Convertir l'objet ScenarioTemplate en ScenarioTemplateResponse
    structure = json.loads(scenario.structure) if scenario.structure else {}
    return ScenarioTemplateResponse(
        id=scenario.id,
        name=scenario.name,
        description=scenario.description or "",
        initial_prompt=scenario.initial_prompt,
        variables=structure.get("variables", {}),
        steps=structure.get("steps", {}),
        first_step=structure.get("first_step", ""),
        created_at=scenario.created_at
    )

@router.post("/scenarios", response_model=ScenarioTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_scenario(
    scenario: ScenarioTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Crée un nouveau template de scénario.
    """
    # Vérifier si un scénario avec cet ID existe déjà
    query = select(ScenarioTemplate).where(ScenarioTemplate.id == scenario.id)
    result = await db.execute(query)
    existing_scenario = result.scalar_one_or_none()
    
    if existing_scenario:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Un scénario avec l'ID {scenario.id} existe déjà"
        )
    
    # Créer la structure JSON
    structure = {
        "variables": {k: v.dict() for k, v in scenario.variables.items()},
        "steps": {k: v.dict() for k, v in scenario.steps.items()},
        "first_step": scenario.first_step
    }
    
    # Créer le nouveau scénario
    new_scenario = ScenarioTemplate(
        id=scenario.id,
        name=scenario.name,
        description=scenario.description,
        initial_prompt=scenario.initial_prompt,
        structure=json.dumps(structure)
    )
    
    db.add(new_scenario)
    await db.commit()
    await db.refresh(new_scenario)
    
    # Retourner la réponse
    return ScenarioTemplateResponse(
        id=new_scenario.id,
        name=new_scenario.name,
        description=new_scenario.description or "",
        initial_prompt=new_scenario.initial_prompt,
        variables=scenario.variables,
        steps=scenario.steps,
        first_step=scenario.first_step,
        created_at=new_scenario.created_at
    )

@router.put("/scenarios/{scenario_id}", response_model=ScenarioTemplateResponse)
async def update_scenario(
    scenario_id: str,
    scenario_update: ScenarioTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Met à jour un template de scénario existant.
    """
    # Vérifier si le scénario existe
    query = select(ScenarioTemplate).where(ScenarioTemplate.id == scenario_id)
    result = await db.execute(query)
    existing_scenario = result.scalar_one_or_none()
    
    if not existing_scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scénario {scenario_id} non trouvé"
        )
    
    # Charger la structure existante
    existing_structure = json.loads(existing_scenario.structure) if existing_scenario.structure else {}
    
    # Mettre à jour les champs simples si fournis
    update_data = {}
    if scenario_update.name is not None:
        update_data["name"] = scenario_update.name
    if scenario_update.description is not None:
        update_data["description"] = scenario_update.description
    if scenario_update.initial_prompt is not None:
        update_data["initial_prompt"] = scenario_update.initial_prompt
    
    # Mettre à jour la structure
    new_structure = dict(existing_structure)
    if scenario_update.variables is not None:
        new_structure["variables"] = {k: v.dict() for k, v in scenario_update.variables.items()}
    if scenario_update.steps is not None:
        new_structure["steps"] = {k: v.dict() for k, v in scenario_update.steps.items()}
    if scenario_update.first_step is not None:
        new_structure["first_step"] = scenario_update.first_step
    
    update_data["structure"] = json.dumps(new_structure)
    
    # Appliquer les mises à jour
    await db.execute(
        update(ScenarioTemplate)
        .where(ScenarioTemplate.id == scenario_id)
        .values(**update_data)
    )
    await db.commit()
    
    # Récupérer le scénario mis à jour
    query = select(ScenarioTemplate).where(ScenarioTemplate.id == scenario_id)
    result = await db.execute(query)
    updated_scenario = result.scalar_one_or_none()
    
    # Convertir l'objet ScenarioTemplate en ScenarioTemplateResponse
    updated_structure = json.loads(updated_scenario.structure) if updated_scenario.structure else {}
    return ScenarioTemplateResponse(
        id=updated_scenario.id,
        name=updated_scenario.name,
        description=updated_scenario.description or "",
        initial_prompt=updated_scenario.initial_prompt,
        variables=updated_structure.get("variables", {}),
        steps=updated_structure.get("steps", {}),
        first_step=updated_structure.get("first_step", ""),
        created_at=updated_scenario.created_at
    )

@router.delete("/scenarios/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scenario(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Supprime un template de scénario.
    """
    # Vérifier si le scénario existe
    query = select(ScenarioTemplate).where(ScenarioTemplate.id == scenario_id)
    result = await db.execute(query)
    existing_scenario = result.scalar_one_or_none()
    
    if not existing_scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scénario {scenario_id} non trouvé"
        )
    
    # Supprimer le scénario
    await db.execute(
        delete(ScenarioTemplate)
        .where(ScenarioTemplate.id == scenario_id)
    )
    await db.commit()