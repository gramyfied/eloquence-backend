#!/usr/bin/env python3
"""
Script d'exemple pour créer un scénario hybride et une session multi-agents.
Ce script montre comment:
1. Créer un template de scénario
2. Créer un profil d'agent
3. Démarrer une session avec ce scénario et cet agent
"""

import asyncio
import json
import logging
import os
import sys
import uuid

# Ajouter le répertoire parent au path pour pouvoir importer les modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from core.database import get_db, Base
from core.models import ScenarioTemplate, AgentProfile, CoachingSession, Participant
from core.orchestrator import Orchestrator, SessionState, ParticipantState

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# URL de la base de données
DATABASE_URL = "sqlite+aiosqlite:///./test.db"

# Créer le moteur de base de données
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Fonction pour initialiser la base de données
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Fonction pour créer un template de scénario à partir d'un fichier JSON
async def create_scenario_template(db: AsyncSession, json_file: str) -> ScenarioTemplate:
    with open(json_file, 'r', encoding='utf-8') as f:
        scenario_data = json.load(f)
    
    # Vérifier si le scénario existe déjà
    scenario = await db.get(ScenarioTemplate, scenario_data['id'])
    if scenario:
        logger.info(f"Le scénario {scenario_data['id']} existe déjà.")
        return scenario
    
    # Créer le scénario
    scenario = ScenarioTemplate(
        id=scenario_data['id'],
        name=scenario_data['name'],
        description=scenario_data['description'],
        initial_prompt=scenario_data['initial_prompt'],
        structure=json.dumps({
            'variables': scenario_data['variables'],
            'steps': scenario_data['steps'],
            'first_step': scenario_data['first_step']
        })
    )
    db.add(scenario)
    await db.commit()
    logger.info(f"Scénario {scenario.id} créé avec succès.")
    return scenario

# Fonction pour créer un profil d'agent à partir d'un fichier JSON
async def create_agent_profile(db: AsyncSession, json_file: str) -> AgentProfile:
    with open(json_file, 'r', encoding='utf-8') as f:
        agent_data = json.load(f)
    
    # Vérifier si l'agent existe déjà
    agent = await db.get(AgentProfile, agent_data['id'])
    if agent:
        logger.info(f"L'agent {agent_data['id']} existe déjà.")
        return agent
    
    # Créer l'agent
    agent = AgentProfile(
        id=agent_data['id'],
        name=agent_data['name'],
        description=agent_data['description'],
        system_prompt=agent_data['system_prompt'],
        voice_id=agent_data.get('voice_id')
    )
    db.add(agent)
    await db.commit()
    logger.info(f"Agent {agent.id} créé avec succès.")
    return agent

# Fonction pour créer une session avec un scénario et un agent
async def create_session(db: AsyncSession, scenario_id: str, agent_id: str, user_id: str = "test_user") -> CoachingSession:
    # Créer la session
    session_id = uuid.uuid4()
    session = CoachingSession(
        id=session_id,
        user_id=user_id,
        scenario_template_id=scenario_id,
        language='fr',
        goal="S'entraîner à un entretien d'embauche",
        status='active',
        is_multi_agent=True
    )
    db.add(session)
    await db.flush()
    
    # Créer le participant utilisateur
    user_participant = Participant(
        session_id=session_id,
        name=f"Utilisateur {user_id}",
        role="user",
        is_primary=True
    )
    db.add(user_participant)
    await db.flush()
    
    # Créer le participant agent
    agent_participant = Participant(
        session_id=session_id,
        agent_profile_id=agent_id,
        name="Recruteur",
        role="agent",
        is_primary=True
    )
    db.add(agent_participant)
    await db.commit()
    
    logger.info(f"Session {session_id} créée avec succès.")
    return session

# Fonction principale
async def main():
    # Initialiser la base de données
    await init_db()
    
    # Créer une session de base de données
    async with async_session() as db:
        # Créer le template de scénario
        scenario = await create_scenario_template(db, "examples/scenario_entretien_embauche.json")
        
        # Créer le profil d'agent
        agent = await create_agent_profile(db, "examples/agent_recruteur.json")
        
        # Créer une session
        session = await create_session(db, scenario.id, agent.id)
        
        # Afficher les informations de la session
        logger.info(f"Session créée: {session.id}")
        logger.info(f"Scénario: {session.scenario_template_id}")
        logger.info(f"URL WebSocket: ws://localhost:8000/ws/{session.id}")
        logger.info("Pour démarrer la session, utilisez l'URL WebSocket ci-dessus.")

if __name__ == "__main__":
    asyncio.run(main())