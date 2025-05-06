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

# Désactiver complètement la connexion à la base de données
logger.warning("⚠️ Mode de fonctionnement sans base de données activé")

# Créer une classe de session factice
class MockSession:
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    async def close(self):
        pass
        
    async def commit(self):
        pass
        
    async def rollback(self):
        pass
        
    def add(self, obj):
        pass
        
    def add_all(self, objs):
        pass
        
    def delete(self, obj):
        pass
        
    async def execute(self, *args, **kwargs):
        class MockResult:
            def scalars(self):
                return self
                
            def first(self):
                return None
                
            def all(self):
                return []
                
            def scalar(self):
                return None
                
            def scalar_one_or_none(self):
                return None
                
            def mappings(self):
                return self
        
        return MockResult()
        
    async def refresh(self, obj):
        pass

# Fonction pour obtenir une session de base de données factice
async def get_db():
    session = MockSession()
    try:
        yield session
    finally:
        await session.close()

# Fonction pour initialiser la base de données (ne fait rien)
async def init_db():
    logger.info("✅ Mode sans base de données activé.")

# Créer une classe de session synchrone factice
class MockSyncSession:
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
        
    def close(self):
        pass
        
    def commit(self):
        pass
        
    def rollback(self):
        pass
        
    def add(self, obj):
        pass
        
    def add_all(self, objs):
        pass
        
    def delete(self, obj):
        pass
        
    def execute(self, *args, **kwargs):
        class MockResult:
            def scalars(self):
                return self
                
            def first(self):
                return None
                
            def all(self):
                return []
                
            def scalar(self):
                return None
                
            def scalar_one_or_none(self):
                return None
                
            def mappings(self):
                return self
        
        return MockResult()
        
    def refresh(self, obj):
        pass

# Fonction pour obtenir une session de base de données synchrone factice
def get_sync_db():
    db = MockSyncSession()
    try:
        yield db
    finally:
        db.close()