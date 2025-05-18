import sys
import os
import subprocess

# Ajouter le répertoire courant au chemin Python
sys.path.insert(0, os.path.abspath("."))

# Afficher le chemin Python pour le débogage
print("Python path:", sys.path)

# Exécuter la commande Gunicorn avec les arguments appropriés
cmd = [
    "gunicorn",
    "app.main:app",
    "--workers", "1",
    "--worker-class", "uvicorn.workers.UvicornWorker",
    "--bind", "0.0.0.0:8000",
    "--timeout", "120",
    "--keep-alive", "65",
    "--log-level", "info"
]

# Exécuter la commande
subprocess.run(cmd)