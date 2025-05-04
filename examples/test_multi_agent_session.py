#!/usr/bin/env python3
"""
Script de test pour une session multi-agents avec un scénario hybride.
Ce script simule une interaction entre un utilisateur et un agent IA dans le cadre d'un scénario d'entretien d'embauche.
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from typing import Dict, List, Optional

# Ajouter le répertoire parent au path pour pouvoir importer les modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.orchestrator import Orchestrator
from examples.create_scenario_session import init_db, create_scenario_template, create_agent_profile, create_session, async_session

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Fonction pour simuler une interaction utilisateur
async def simulate_user_interaction(orchestrator: Orchestrator, session_id: str, db: AsyncSession):
    """Simule une interaction utilisateur avec le système."""
    # Récupérer la session
    session_state = await orchestrator.get_or_create_session(
        session_id_str=str(session_id),
        db=db,
        is_multi_agent=True,
        agent_profile_id="recruteur"
    )
    
    if not session_state:
        logger.error(f"Impossible de récupérer la session {session_id}")
        return
    
    # Afficher les informations de la session
    logger.info(f"Session récupérée: {session_id}")
    logger.info(f"Scénario: {session_state.scenario_template.id if session_state.scenario_template else 'Aucun'}")
    logger.info(f"Étape actuelle: {session_state.current_scenario_state.get('current_step', 'Aucune')}")
    logger.info(f"Variables: {session_state.current_scenario_state.get('variables', {})}")
    
    # Afficher les participants
    logger.info(f"Nombre de participants: {len(session_state.participants)}")
    for participant_id, participant in session_state.participants.items():
        logger.info(f"Participant: {participant.name} (ID: {participant_id})")
        logger.info(f"  Rôle: {participant.role}")
        logger.info(f"  Principal: {participant.is_primary}")
        if participant.role == "agent":
            logger.info(f"  Profil d'agent: {participant.agent_profile_id}")
            logger.info(f"  Voix: {participant.voice_id}")
    
    # Simuler une réponse utilisateur
    user_response = "Bonjour, je m'appelle Jean Dupont. Je suis développeur web avec 5 ans d'expérience, spécialisé en JavaScript et React."
    
    # Créer un chunk audio simulé (dans un cas réel, ce serait de l'audio encodé)
    simulated_audio = b"SIMULATED_AUDIO_DATA"
    
    # Traiter l'audio simulé
    logger.info(f"Envoi d'une réponse utilisateur simulée: {user_response}")
    await orchestrator.process_audio_chunk(str(session_id), simulated_audio, db)
    
    # Dans un cas réel, nous attendrions la réponse de l'agent via WebSocket
    # Ici, nous simulons simplement l'attente
    logger.info("Attente de la réponse de l'agent...")
    await asyncio.sleep(2)
    
    # Afficher l'état mis à jour de la session
    logger.info(f"État mis à jour:")
    logger.info(f"Étape actuelle: {session_state.current_scenario_state.get('current_step', 'Aucune')}")
    logger.info(f"Variables: {session_state.current_scenario_state.get('variables', {})}")

# Fonction principale
async def main():
    # Initialiser la base de données
    await init_db()
    
    # Créer une instance de l'orchestrateur
    orchestrator = Orchestrator()
    await orchestrator.initialize()
    
    try:
        # Créer une session de base de données
        async with async_session() as db:
            # Créer le template de scénario
            scenario = await create_scenario_template(db, "examples/scenario_entretien_embauche.json")
            
            # Créer le profil d'agent
            agent = await create_agent_profile(db, "examples/agent_recruteur.json")
            
            # Créer une session
            session = await create_session(db, scenario.id, agent.id)
            
            # Simuler une interaction utilisateur
            await simulate_user_interaction(orchestrator, session.id, db)
    finally:
        # Arrêter l'orchestrateur
        await orchestrator.shutdown()

if __name__ == "__main__":
    asyncio.run(main())