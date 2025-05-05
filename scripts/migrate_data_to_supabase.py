import asyncio
import logging
import argparse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

# Importer les modèles directement
from core.models import Base, ScenarioTemplate, AgentProfile, CoachingSession, Participant, SessionTurn, KaldiFeedback, Session, SessionSegment

# Configuration des logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# URL de l'ancienne base de données SQLite
OLD_DATABASE_URL = "sqlite+aiosqlite:///./eloquence.db"

async def migrate_table(old_session: AsyncSession, new_session: AsyncSession, table_model: Base):
    """Migre les données d'une table de l'ancienne DB vers la nouvelle."""
    table_name = table_model.__tablename__
    logger.info(f"Migration de la table '{table_name}'...")

    try:
        # Lire les données de l'ancienne table
        result = await old_session.execute(select(table_model))
        rows = result.scalars().all()
        
        if not rows:
            logger.info(f"Aucune donnée à migrer dans la table '{table_name}'.")
            return

        # Insérer les données dans la nouvelle table
        # Utiliser bulk_insert_mappings pour une insertion plus efficace
        # Note: Cela suppose que les colonnes et types sont compatibles.
        # Des transformations pourraient être nécessaires pour des cas complexes (ex: UUIDs générés différemment)
        
        # Convertir les objets SQLAlchemy en dictionnaires pour bulk_insert_mappings
        data_to_insert = [row.__dict__ for row in rows]
        
        # Supprimer les clés internes de SQLAlchemy si elles existent
        data_to_insert = [{k: v for k, v in row.items() if not k.startswith('_')} for row in data_to_insert]

        await new_session.bulk_insert_mappings(table_model, data_to_insert)
        await new_session.commit()
        logger.info(f"Migration de {len(rows)} enregistrements terminée pour la table '{table_name}'.")

    except Exception as e:
        logger.error(f"Erreur lors de la migration de la table '{table_name}': {e}")
        await new_session.rollback() # Annuler la transaction en cas d'erreur

async def main(supabase_project_ref: str, supabase_db_password: str, supabase_region: str):
    # Construire l'URL de la base de données Supabase
    NEW_DATABASE_URL = f"postgresql+asyncpg://postgres.{supabase_project_ref}:{supabase_db_password}@aws-0-{supabase_region}.pooler.supabase.com:6543/postgres"

    # Créer les moteurs pour les deux bases de données
    old_engine = create_async_engine(OLD_DATABASE_URL, echo=False, future=True)
    new_engine = create_async_engine(NEW_DATABASE_URL, echo=False, future=True)

    # Créer les factories de session
    OldAsyncSessionLocal = sessionmaker(bind=old_engine, class_=AsyncSession, expire_on_commit=False)
    NewAsyncSessionLocal = sessionmaker(bind=new_engine, class_=AsyncSession, expire_on_commit=False)

    async with OldAsyncSessionLocal() as old_session, NewAsyncSessionLocal() as new_session:
        # Liste des modèles de table à migrer
        # Assurez-vous que l'ordre respecte les dépendances de clés étrangères si nécessaire
        # (bien que bulk_insert_mappings gère généralement cela si les IDs sont préservés)
        table_models = [
            ScenarioTemplate,
            AgentProfile,
            CoachingSession,
            Participant,
            SessionTurn,
            KaldiFeedback,
            Session,
            SessionSegment,
        ]

        for model in table_models:
            await migrate_table(old_session, new_session, model)

    logger.info("Processus de migration terminé.")

    # Fermer les moteurs
    await old_engine.dispose()
    await new_engine.dispose()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate data from SQLite to Supabase PostgreSQL.")
    parser.add_argument("--supabase-project-ref", required=True, help="Supabase project reference ID")
    parser.add_argument("--supabase-db-password", required=True, help="Supabase database password")
    parser.add_argument("--supabase-region", required=True, help="Supabase project region")

    args = parser.parse_args()

    asyncio.run(main(args.supabase_project_ref, args.supabase_db_password, args.supabase_region))
