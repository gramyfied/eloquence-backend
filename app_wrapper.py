import sys
import os

# Ajouter le répertoire parent au chemin de recherche Python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importer l'application FastAPI
from app.main import app

# Cette variable est utilisée par Gunicorn
application = app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)