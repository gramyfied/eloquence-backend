# Utiliser une image de base Python avec support CUDA
FROM python:3.12-slim

# Définir les variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Installer les dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1 \
    ffmpeg \
    git \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Créer et définir le répertoire de travail
WORKDIR /app

# Copier les fichiers de dépendances
COPY requirements.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn  # Ajouter Gunicorn explicitement

# Copier le code source
COPY . .

# Créer les répertoires nécessaires
RUN mkdir -p /app/data/audio /app/data/feedback /app/data/models /app/logs

# Exposer le port
EXPOSE 8000

# Commande par défaut - Utiliser Gunicorn avec 4 workers Uvicorn
# --workers 4: Utiliser 4 processus worker (ajuster selon le nombre de CPU disponibles)
# --worker-class uvicorn.workers.UvicornWorker: Utiliser les workers Uvicorn pour ASGI
# --timeout 120: Timeout de 120 secondes pour les requêtes
# --keep-alive 65: Garder les connexions ouvertes pendant 65 secondes
# --log-level info: Niveau de log info
CMD ["gunicorn", "app.main:app", "--workers", "1", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "120", "--keep-alive", "65", "--log-level", "info"]