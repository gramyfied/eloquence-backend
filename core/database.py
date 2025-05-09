import asyncio
import logging
import asyncpg  # Ajout de l'importation de asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker as sync_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from typing import Optional, Any, Dict, List

# Importer Settings au lieu de settings
from core.config import Settings
# Importer Base depuis models pour la création de tables
from core.models import Base

# Créer une instance locale de Settings
settings = Settings()

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
else:
    # Configuration pour la production (Supabase/PostgreSQL)
    logger.info("Mode production détecté: utilisation de PostgreSQL/asyncpg avec SQLAlchemy ORM")
    
    # Créer un moteur asynchrone pour PostgreSQL avec asyncpg
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        future=True,
        pool_size=10, # Ajuster la taille du pool selon les besoins
        max_overflow=20,
        pool_timeout=30,
        connect_args={"server_settings": {"jit": "off"}} # Exemple d'optimisation pour PostgreSQL
    )
    
    # Créer une fabrique de sessions asynchrones
    async_session_factory = sessionmaker(
        engine, 
        class_=AsyncSession, 
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
    
    # Fonction factice pour compatibilité (si get_sync_db est utilisé ailleurs)
    def get_sync_db():
        # En mode asynchrone, l'utilisation d'une session synchrone n'est pas recommandée.
        # Retourner une session factice ou lever une erreur si cette fonction est appelée.
        logger.warning("get_sync_db appelé en mode asynchrone. Utiliser get_db à la place.")
        class DummySession:
            def close(self):
                pass
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
        
        session = DummySession()
        try:
            yield session
        finally:
            session.close()
    
    # Fonction pour initialiser la base de données (créer les tables)
    async def init_db():
        """
        Initialise la base de données en créant toutes les tables définies dans les modèles.
        """
        try:
            async with engine.begin() as conn:
                # Utiliser run_sync pour exécuter des opérations synchrones (comme create_all)
                # dans un contexte asynchrone
                await conn.run_sync(Base.metadata.create_all)
            
            logger.info("✅ Base de données initialisée avec succès")
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'initialisation de la base de données: {e}")
            raise