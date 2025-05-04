#!/bin/bash

# Script de démarrage pour le service Coqui TTS
# Ce script télécharge les modèles nécessaires si besoin, puis lance l'API

# Vérifier si les modèles sont déjà téléchargés
if [ ! -d "/app/models/tts_models" ]; then
    echo "Téléchargement des modèles TTS..."
    
    # Télécharger le modèle VITS pour le français
    python -c "from TTS.utils.manage import ModelManager; ModelManager().download_model('tts_models/fr/mai/vits-nathalie-hifigan')"
    
    # Télécharger le modèle XTTS v2 (pour les émotions)
    python -c "from TTS.utils.manage import ModelManager; ModelManager().download_model('tts_models/multilingual/multi-dataset/xtts_v2')"
    
    # Déplacer les modèles téléchargés vers le répertoire /app/models
    mkdir -p /app/models/tts_models
    cp -r ~/.local/share/tts/tts_models/* /app/models/tts_models/
    
    echo "Modèles téléchargés avec succès."
fi

# Créer les fichiers de référence pour les émotions si nécessaires
if [ ! -d "/app/speakers/emotions" ]; then
    echo "Création des fichiers de référence pour les émotions..."
    
    mkdir -p /app/speakers/emotions
    
    # Télécharger des échantillons pour chaque émotion
    # Ces URLs sont des exemples et devraient être remplacées par des fichiers réels
    wget -O /app/speakers/emotions/neutre.wav https://example.com/samples/neutre.wav || echo "Échec du téléchargement de neutre.wav"
    wget -O /app/speakers/emotions/encouragement.wav https://example.com/samples/encouragement.wav || echo "Échec du téléchargement de encouragement.wav"
    wget -O /app/speakers/emotions/empathie.wav https://example.com/samples/empathie.wav || echo "Échec du téléchargement de empathie.wav"
    wget -O /app/speakers/emotions/enthousiasme_modere.wav https://example.com/samples/enthousiasme_modere.wav || echo "Échec du téléchargement de enthousiasme_modere.wav"
    wget -O /app/speakers/emotions/curiosite.wav https://example.com/samples/curiosite.wav || echo "Échec du téléchargement de curiosite.wav"
    wget -O /app/speakers/emotions/reflexion.wav https://example.com/samples/reflexion.wav || echo "Échec du téléchargement de reflexion.wav"
    
    echo "Fichiers de référence créés."
fi

# Lancer l'API
echo "Démarrage du serveur TTS..."
uvicorn app:app --host 0.0.0.0 --port 5002