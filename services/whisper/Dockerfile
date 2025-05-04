# Utiliser une image Python officielle comme base
FROM python:3.12-slim

# Définir le répertoire de travail dans le conteneur
WORKDIR /app

# Variables d'environnement pour Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Installer les dépendances système nécessaires
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    build-essential \
    pkg-config \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavutil-dev \
    libavfilter-dev \
    libswscale-dev \
    libswresample-dev \
    && rm -rf /var/lib/apt/lists/*

# Ajouter les chemins de recherche de pkg-config
ENV PKG_CONFIG_PATH=/usr/local/lib/pkgconfig:/usr/lib/pkgconfig

# Installer faster-whisper et ses dépendances
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    faster-whisper==0.9.0 \
    fastapi==0.104.1 \
    uvicorn==0.23.2 \
    python-multipart==0.0.6 \
    soundfile==0.12.1 \
    numpy==1.26.0 \
    av==9.2.0 # Spécifier une version de PyAV potentiellement plus stable

# Copier le code de l'application
COPY app.py .

# Exposer le port sur lequel l'application FastAPI écoutera
EXPOSE 8000

# Commande par défaut pour lancer l'application FastAPI avec Uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]