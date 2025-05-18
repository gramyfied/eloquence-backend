# Utiliser une image Python officielle comme base
FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime

# Définir le répertoire de travail dans le conteneur
WORKDIR /app

# Variables d'environnement pour Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Variables d'environnement pour les installations non interactives
ENV DEBIAN_FRONTEND=noninteractive
ENV TTS_USE_XTTS=false

# Installer les dépendances système nécessaires
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1 \
    ffmpeg \
    espeak-ng \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Installer TTS et ses dépendances
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    TTS==0.17.0 \
    fastapi==0.104.1 \
    uvicorn==0.23.2 \
    python-multipart==0.0.6 \
    soundfile==0.12.1 \
    numpy==1.22.0 \
    pydub==0.25.1 && \
    pip install --no-cache-dir --force-reinstall torch==2.0.1

# Créer les répertoires pour les modèles et les speakers
RUN mkdir -p /app/models /app/speakers/emotions

# Télécharger les modèles TTS
# Note: Assurez-vous que les noms des modèles sont corrects et que la version de TTS les supporte.
# Le téléchargement peut prendre du temps et augmenter la taille de l'image.
# Les modèles sont maintenant copiés depuis un répertoire local pré-téléchargé
# Assurez-vous que les modèles sont présents dans 'downloaded_models' relatif au contexte de build.
COPY downloaded_models/tts_models--multilingual--multi-dataset--bark /app/models/tts_models--multilingual--multi-dataset--bark/
COPY downloaded_models/tts_models--multilingual--multi-dataset--xtts_v2 /app/models/tts_models--multilingual--multi-dataset--xtts_v2/

# Créer des fichiers audio placeholder pour les émotions
RUN echo "dummy_wav_content" > /app/speakers/emotions/neutre.wav && \
    echo "dummy_wav_content" > /app/speakers/emotions/encouragement.wav && \
    echo "dummy_wav_content" > /app/speakers/emotions/empathie.wav && \
    echo "dummy_wav_content" > /app/speakers/emotions/enthousiasme_modere.wav && \
    echo "dummy_wav_content" > /app/speakers/emotions/curiosite.wav && \
    echo "dummy_wav_content" > /app/speakers/emotions/reflexion.wav

# Copier le code de l'application
COPY app.py .
COPY start.sh .

# Rendre le script de démarrage exécutable
RUN chmod +x start.sh

# Exposer le port sur lequel l'application FastAPI écoutera
EXPOSE 5002

# Commande par défaut pour lancer l'application
CMD ["./start.sh"]