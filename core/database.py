import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker as sync_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from core.config import settings
# Importer Base depuis models pour la création de tables
from core.models import Base

logger = logging.getLogger(__name__)

# Utiliser le flag IS_TESTING de settings
if settings.IS_TESTING:
    # Configuration pour les tests (SQLite en mémoire)
    logger.info("Mode test détecté: utilisation de SQLite en mémoire")
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=settings.DEBUG,
        future=True
    )
    
    # Créer un moteur synchrone pour les opérations qui nécessitent une connexion synchrone
    sync_engine = create_engine(
        "sqlite:///:memory:",
        echo=settings.DEBUG,
        future=True
    )
else:
    # Configuration pour la production (Supabase/PostgreSQL)
    logger.info(f"Connexion à la base de données Supabase: {settings.DATABASE_URL.split('@')[1].split('/')[0]}")
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        future=True,
        pool_pre_ping=True,
        # Désactiver le cache des prepared statements pour éviter les problèmes avec Supabase
        connect_args={"prepared_statement_cache_size": 0}
    )
    
    # Créer un moteur synchrone pour les opérations qui nécessitent une connexion synchrone
    # Remplacer asyncpg par psycopg2 pour la connexion synchrone
    sync_engine = create_engine(
        settings.DATABASE_URL.replace("sqlite+aiosqlite", "sqlite").replace("postgresql+asyncpg", "postgresql+psycopg2"),
        echo=settings.DEBUG,
        future=True,
        pool_pre_ping=True
    )

# Créer une fabrique de sessions asynchrones
async_session_factory = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False,
    autoflush=False
)

# Créer une fabrique de sessions synchrones
sync_session_factory = sync_sessionmaker(
    sync_engine,
    expire_on_commit=False,
    autoflush=False
)

# Fonction pour obtenir une session de base de données asynchrone
async def get_db():
    session = async_session_factory()
    try:
        yield session
    finally:
        await session.close()

# Fonction pour obtenir une session de base de données synchrone
def get_sync_db():
    session = sync_session_factory()
    try:
        yield session
    finally:
        session.close()

# Fonction pour initialiser la base de données
async def init_db():
    """
    Initialise la base de données en créant toutes les tables définies dans les modèles.
    """
    try:
        # Créer les tables de manière asynchrone
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("✅ Base de données initialisée avec succès")
    except Exception as e:
        logger.error(f"❌ Erreur lors de l'initialisation de la base de données: {e}")
        raise

# Fonction pour vérifier la connexion à la base de données
async def check_db_connection():
    """
    Vérifie si la connexion à la base de données est fonctionnelle.
    
    Returns:
        bool: True si la connexion est fonctionnelle, False sinon
    """
    try:
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur de connexion à la base de données: {e}")
        return False

# Fonction pour exécuter une migration de base de données
async def run_migrations():
    """
    Exécute les migrations de base de données.
    Cette fonction est un placeholder et devrait être implémentée avec Alembic.
    """
    logger.info("⚠️ Migrations de base de données non implémentées")
    # Dans une implémentation réelle, on utiliserait Alembic pour les migrations
    # from alembic.config import Config
    # from alembic import command
    # alembic_cfg = Config("alembic.ini")
    # command.upgrade(alembic_cfg, "head")