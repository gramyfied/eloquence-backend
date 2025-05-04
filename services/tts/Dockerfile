# Utiliser une image Python officielle comme base
FROM python:3.10-slim

# Définir le répertoire de travail dans le conteneur
WORKDIR /app

# Variables d'environnement pour Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Installer les dépendances système nécessaires
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1 \
    ffmpeg \
    espeak-ng \
    git \
    && rm -rf /var/lib/apt/lists/*

# Installer TTS et ses dépendances
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    TTS==0.21.1 \
    fastapi==0.104.1 \
    uvicorn==0.23.2 \
    python-multipart==0.0.6 \
    soundfile==0.12.1 \
    numpy==1.26.0 \
    pydub==0.25.1

# Créer les répertoires pour les modèles et les speakers
RUN mkdir -p /app/models /app/speakers

# Copier le code de l'application
COPY app.py .
COPY start.sh .

# Rendre le script de démarrage exécutable
RUN chmod +x start.sh

# Exposer le port sur lequel l'application FastAPI écoutera
EXPOSE 5002

# Commande par défaut pour lancer l'application
CMD ["./start.sh"]