#!/usr/bin/env python3
"""
Script pour corriger les imports dans main.py
"""

import os

# Fichier à modifier
MAIN_PY_PATH = "/home/ubuntu/eloquence_backend_py/app/main.py"

def fix_main_imports():
    """
    Modifie les imports dans main.py pour éviter les erreurs de connexion à la base de données
    """
    print("🔧 Modification des imports dans main.py...")
    
    with open(MAIN_PY_PATH, 'r') as file:
        content = file.read()
    
    # Remplacer l'import de database
    old_import = """from core.config import settings
from core.database import engine, get_db, AsyncSessionLocal # Importer AsyncSessionLocal
from core.models import Base"""
    
    new_import = """from core.config import settings
# Imports de database désactivés en mode sans base de données
# from core.database import engine, get_db, AsyncSessionLocal
# from core.models import Base"""
    
    # Remplacer les imports dans les routes
    old_routes_import = """from app.routes import api_router"""
    
    new_routes_import = """# Import des routes avec gestion des erreurs potentielles
try:
    from app.routes import api_router
except ImportError as e:
    import logging
    logging.error(f"Erreur lors de l'import des routes: {e}")
    # Créer un router vide en cas d'erreur
    from fastapi import APIRouter
    api_router = APIRouter()"""
    
    # Effectuer les remplacements
    content = content.replace(old_import, new_import)
    content = content.replace(old_routes_import, new_routes_import)
    
    # Écrire le contenu modifié
    with open(MAIN_PY_PATH, 'w') as file:
        file.write(content)
    
    print("✅ Imports dans main.py modifiés avec succès.")
    return True

# Créer un fichier main.py simplifié pour le mode sans base de données
def create_simplified_main():
    """
    Crée un fichier main.py simplifié pour le mode sans base de données
    """
    print("🔧 Création d'un fichier main.py simplifié...")
    
    simplified_main = """
\"\"\"
Point d'entrée principal de l'application Eloquence Backend (mode sans base de données).
\"\"\"

import logging
import os
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)

logger = logging.getLogger(__name__)

# Initialisation de l'application FastAPI
app = FastAPI(
    title="Eloquence Backend API (Mode Sans Base de Données)",
    description="API pour le système de coaching vocal Eloquence - Mode de diagnostic sans base de données",
    version="1.0.0",
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Événements de démarrage et d'arrêt
@app.on_event("startup")
async def startup_event():
    \"\"\"
    Événement exécuté au démarrage de l'application.
    \"\"\"
    logger.info("Démarrage de l'application Eloquence Backend en mode sans base de données")
    logger.warning("⚠️ Mode sans base de données activé - Fonctionnalités limitées")

@app.on_event("shutdown")
async def shutdown_event():
    \"\"\"
    Événement exécuté à l'arrêt de l'application.
    \"\"\"
    logger.info("Arrêt de l'application Eloquence Backend")

# Route de santé
@app.get("/health")
async def health_check():
    \"\"\"
    Vérifie l'état de santé de l'application.
    \"\"\"
    return {"status": "ok", "version": "1.0.0", "mode": "sans base de données"}

# Route racine
@app.get("/")
async def root():
    \"\"\"
    Route racine de l'API.
    \"\"\"
    html_content = \"\"\"
    <html>
        <head>
            <title>Backend Test Server</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    line-height: 1.6;
                }
                h1 {
                    color: #4CAF50;
                }
                .warning {
                    background-color: #fff3cd;
                    color: #856404;
                    padding: 10px;
                    border-radius: 5px;
                    margin: 20px 0;
                }
                .endpoints {
                    background-color: #f8f9fa;
                    padding: 15px;
                    border-radius: 5px;
                }
            </style>
        </head>
        <body>
            <h1>Backend Test Server</h1>
            <p>If you can see this, your connection is working!</p>
            
            <div class="warning">
                <strong>Mode sans base de données activé</strong>
                <p>Le serveur fonctionne en mode diagnostic sans connexion à la base de données.</p>
                <p>Seules les routes de base sont disponibles.</p>
            </div>
            
            <div class="endpoints">
                <h3>Endpoints disponibles:</h3>
                <ul>
                    <li><a href="/health">/health</a> - Vérification de l'état du serveur</li>
                    <li><a href="/docs">/docs</a> - Documentation API</li>
                </ul>
            </div>
        </body>
    </html>
    \"\"\"
    return HTMLResponse(content=html_content)

# Gestionnaire d'exceptions global
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    \"\"\"
    Gestionnaire d'exceptions global pour l'application.
    \"\"\"
    logger.error(f"Exception non gérée: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Une erreur interne est survenue"}
    )

# Ajouter quelques routes de test pour les services principaux
@app.get("/api/tts")
async def test_tts():
    return {"status": "mock", "message": "Service TTS simulé en mode sans base de données"}

@app.get("/api/stt")
async def test_stt():
    return {"status": "mock", "message": "Service STT simulé en mode sans base de données"}

@app.get("/coaching/init")
async def test_coaching_init():
    return {"status": "mock", "session_id": "test-session-123", "message": "Session de coaching simulée en mode sans base de données"}

@app.get("/api/session/start")
async def test_session_start():
    return {"status": "mock", "session_id": "test-session-123", "message": "Session simulée en mode sans base de données"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8082,
        reload=True
    )
"""
    
    # Sauvegarder l'original
    backup_path = MAIN_PY_PATH + ".backup"
    if not os.path.exists(backup_path):
        with open(MAIN_PY_PATH, 'r') as src:
            with open(backup_path, 'w') as dst:
                dst.write(src.read())
        print(f"✅ Sauvegarde de l'original créée: {backup_path}")
    
    # Écrire le fichier simplifié
    with open(MAIN_PY_PATH, 'w') as file:
        file.write(simplified_main)
    
    print("✅ Fichier main.py simplifié créé avec succès.")
    return True

if __name__ == "__main__":
    # fix_main_imports()  # Approche 1: Modifier les imports
    create_simplified_main()  # Approche 2: Remplacer complètement le fichier
    print("🔄 Redémarrez le service pour appliquer les modifications.")
