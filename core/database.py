import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from core.config import settings
# Importer Base depuis models pour la création de tables
from core.models import Base

logger = logging.getLogger(__name__)

# Créer le moteur asynchrone
# Ajouter ?async_fallback=True si le driver ne supporte pas nativement l'async (ex: psycopg2)
# Préférer asyncpg pour PostgreSQL si possible (pip install asyncpg)
try:
    # Assurer que l'URL est compatible async
    async_db_url = settings.DATABASE_URL
    
    # Gérer différents types de bases de données
    if async_db_url.startswith("postgresql"):
        if async_db_url.startswith("postgresql+psycopg2"):
            async_db_url = async_db_url.replace("postgresql+psycopg2", "postgresql+asyncpg", 1)
            logger.info("Adaptation de l'URL DB pour asyncpg.")
        elif not async_db_url.startswith("postgresql+asyncpg"):
            logger.warning(f"Driver DB non asyncpg détecté ({async_db_url}). Assurez-vous que le driver supporte asyncio ou installez asyncpg.")
            # Tenter avec psycopg si asyncpg n'est pas là (nécessite psycopg[binary] >= 3.1)
            async_db_url = async_db_url.replace("postgresql+psycopg2", "postgresql+psycopg", 1)
    elif async_db_url.startswith("sqlite"):
        # S'assurer que l'URL SQLite est compatible avec aiosqlite
        if not async_db_url.startswith("sqlite+aiosqlite"):
            async_db_url = async_db_url.replace("sqlite", "sqlite+aiosqlite", 1)
            logger.info("Adaptation de l'URL DB pour aiosqlite.")

    # Créer le moteur avec les options appropriées
    connect_args = {}
    if async_db_url.startswith("sqlite"):
        # Options spécifiques à SQLite pour permettre l'accès concurrent
        connect_args = {"check_same_thread": False}
    
    engine = create_async_engine(
        async_db_url,
        echo=False,
        future=True,
        connect_args=connect_args
    )
    logger.info(f"Moteur de base de données asynchrone créé pour: {async_db_url}")

except ImportError as ie:
    logger.error(f"Driver de base de données non installé: {ie}")
    if "asyncpg" in str(ie):
        logger.error("Le driver asyncpg n'est pas installé. Veuillez l'installer: pip install asyncpg")
    elif "aiosqlite" in str(ie):
        logger.error("Le driver aiosqlite n'est pas installé. Veuillez l'installer: pip install aiosqlite")
    engine = None  # Marquer comme non initialisé

except Exception as e:
    logger.critical(f"Erreur lors de la création du moteur de base de données asynchrone: {e}")
    engine = None

# Créer une factory de session asynchrone
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False, # Important pour l'utilisation avec FastAPI
    autocommit=False,
    autoflush=False,
) if engine else None

async def get_db() -> AsyncSession:
    """
    Dépendance FastAPI pour obtenir une session de base de données asynchrone.
    """
    if AsyncSessionLocal is None:
        logger.error("La session de base de données n'a pas pu être initialisée.")
        raise RuntimeError("Database session not initialized")

    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# --- Fonctions d'initialisation (optionnel, préférer Alembic) ---
async def init_db():
    """Initialise la base de données (crée les tables). Préférer Alembic en production."""
    if not engine:
        logger.error("Le moteur de base de données n'est pas initialisé, impossible de créer les tables.")
        return
    async with engine.begin() as conn:
        try:
            # Importer Base ici pour éviter les dépendances circulaires
            from core.models import Base
            logger.info("Création des tables de la base de données (si elles n'existent pas)...")
            # await conn.run_sync(Base.metadata.drop_all) # Pour réinitialiser pendant le dev
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Tables créées (ou déjà existantes).")
        except Exception as e:
            logger.error(f"Erreur lors de la création des tables: {e}")

async def close_db():
    """Ferme proprement le moteur de base de données."""
    if engine:
        logger.info("Fermeture du moteur de base de données.")
        await engine.dispose()
from sqlalchemy import create_engine as create_sync_engine

# --- Moteur et Session Synchrone (pour Celery/scripts) ---
sync_engine = None
SyncSessionLocal = None
try:
    # Utiliser l'URL DB standard (non async)
    sync_engine = create_sync_engine(settings.DATABASE_URL, echo=False)
    SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
    logger.info(f"Moteur de base de données synchrone créé pour: {settings.DATABASE_URL}")
except Exception as e:
    logger.error(f"Impossible de créer le moteur de base de données synchrone: {e}")

def get_sync_db():
    """Fournit une session DB synchrone (pour Celery)."""
    if SyncSessionLocal is None:
        logger.error("La session de base de données synchrone n'a pas pu être initialisée.")
        raise RuntimeError("Sync Database session not initialized")
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()