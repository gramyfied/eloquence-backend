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
    pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY . .

# Créer les répertoires nécessaires
RUN mkdir -p /app/data/audio /app/data/feedback /app/data/models /app/logs

# Exposer le port
EXPOSE 8000

# Commande par défaut avec timeouts WebSocket augmentés
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--websocket-ping-interval", "60", "--websocket-ping-timeout", "300"]