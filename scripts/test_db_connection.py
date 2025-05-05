import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine

# Configuration des logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_connection(supabase_project_ref: str, supabase_db_password: str, supabase_region: str):
    """Teste la connexion à la base de données Supabase."""
    NEW_DATABASE_URL = f"postgresql+asyncpg://postgres.{supabase_project_ref}:{supabase_db_password}@aws-0-{supabase_region}.pooler.supabase.com:6543/postgres"
    logger.info(f"Tentative de connexion à la base de données: {NEW_DATABASE_URL}")

    engine = None
    try:
        # Créer le moteur asynchrone
        engine = create_async_engine(
            NEW_DATABASE_URL,
            echo=False,
            future=True,
        )

        # Tenter d'établir une connexion
        async with engine.connect() as conn:
            logger.info("Connexion à la base de données Supabase réussie!")
            # Optionnel: Exécuter une simple requête pour vérifier davantage
            # result = await conn.execute(text("SELECT 1"))
            # logger.info(f"Résultat de la requête de test: {result.scalar()}")

    except Exception as e:
        logger.error(f"Échec de la connexion à la base de données Supabase: {e}")

    finally:
        # Fermer le moteur
        if engine:
            await engine.dispose()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test connection to Supabase PostgreSQL database.")
    parser.add_argument("--supabase-project-ref", required=True, help="Supabase project reference ID")
    parser.add_argument("--supabase-db-password", required=True, help="Supabase database password")
    parser.add_argument("--supabase-region", required=True, help="Supabase project region")

    args = parser.parse_args()

    asyncio.run(test_connection(args.supabase_project_ref, args.supabase_db_password, args.supabase_region))
