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
    # Utiliser directement asyncpg au lieu de SQLAlchemy
    
    # Variables pour stocker la connexion asyncpg
    _pool = None
    
    # Fonction pour obtenir un pool de connexions asyncpg
    async def get_pool():
        global _pool
        if _pool is None:
            try:
                # Extraire les informations de connexion de la chaîne DATABASE_URL
                # Format: postgresql+asyncpg://username:password@host:port/database?param=value
                url_parts = settings.DATABASE_URL.replace("postgresql+asyncpg://", "").split("@")
                auth = url_parts[0].split(":")
                username = auth[0]
                password = auth[1]
                
                host_parts = url_parts[1].split("/")
                host_port = host_parts[0].split(":")
                host = host_port[0]
                port = int(host_port[1]) if len(host_port) > 1 else 5432
                
                database = host_parts[1].split("?")[0]
                
                logger.info(f"Connexion à la base de données Supabase: {host}:{port}/{database}")
                
                # Créer un pool de connexions asyncpg avec statement_cache_size=0
                _pool = await asyncpg.create_pool(
                    user=username,
                    password=password,
                    host=host,
                    port=port,
                    database=database,
                    statement_cache_size=0,  # Désactiver le cache des prepared statements
                    max_size=10,
                    min_size=1
                )
                
                logger.info("✅ Pool de connexions asyncpg créé avec succès")
            except Exception as e:
                logger.error(f"❌ Erreur lors de la création du pool de connexions asyncpg: {e}")
                raise
        
        return _pool
    
    # Classe pour encapsuler un résultat de requête asyncpg
    class AsyncpgResult:
        def __init__(self, rows):
            self.rows = rows
        
        async def fetchall(self):
            """Retourne toutes les lignes du résultat"""
            return self.rows
        
        async def fetchone(self):
            """Retourne la première ligne du résultat ou None"""
            return self.rows[0] if self.rows else None
        
        async def scalar_one_or_none(self):
            """Retourne la première valeur de la première ligne ou None"""
            if not self.rows:
                return None
            return self.rows[0][0] if self.rows[0] else None
        
        async def scalars(self):
            """Retourne un objet qui a une méthode all() qui retourne toutes les premières valeurs de chaque ligne"""
            class ScalarsResult:
                def __init__(self, rows):
                    self.rows = rows
                
                def all(self):
                    return [row[0] for row in self.rows] if self.rows else []
                
                def unique(self):
                    return self
            
            return ScalarsResult(self.rows)
    
    # Classe pour encapsuler une connexion asyncpg
    class AsyncpgConnection:
        def __init__(self, connection):
            self.connection = connection
        
        async def execute(self, query, params=None):
            """Exécute une requête SQL et retourne le résultat encapsulé"""
            try:
                if params:
                    # Vérifier si params est une liste ou un dictionnaire
                    if isinstance(params, list):
                        rows = await self.connection.fetch(query, *params)
                    else:
                        rows = await self.connection.fetch(query, *params.values())
                else:
                    rows = await self.connection.fetch(query)
                
                # Encapsuler le résultat dans un objet AsyncpgResult
                return AsyncpgResult(rows)
            except Exception as e:
                logger.error(f"❌ Erreur lors de l'exécution de la requête: {e}")
                raise
        
        async def close(self):
            """Libère la connexion"""
            await self.connection.close()
        
        async def commit(self):
            """Commit la transaction"""
            # asyncpg gère automatiquement les transactions
            pass
    
    # Fonction pour obtenir une connexion asyncpg
    async def get_db():
        pool = await get_pool()
        connection = await pool.acquire()
        try:
            yield AsyncpgConnection(connection)
        finally:
            await pool.release(connection)
    
    # Fonction factice pour compatibilité
    def get_sync_db():
        class DummySession:
            def close(self):
                pass
        
        session = DummySession()
        try:
            yield session
        finally:
            session.close()
    
    # Fonction pour initialiser la base de données
    async def init_db():
        """
        Initialise la base de données en vérifiant la connexion.
        """
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                # Vérifier la connexion
                await conn.execute("SELECT 1")
            
            logger.info("✅ Base de données initialisée avec succès")
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'initialisation de la base de données: {e}")
            raise