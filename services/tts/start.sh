#!/bin/bash

# Script de démarrage pour le service Coqui TTS
# Ce script télécharge les modèles nécessaires si besoin, puis lance l'API

# Vérifier si les modèles sont déjà téléchargés
# Définir les chemins et noms de modèles
MODELS_TARGET_DIR="/app/models"
MODEL_FR="tts_models--fr--mai--tacotron2-DDC"
MODEL_XTTS="tts_models--multilingual--multi-dataset--xtts_v2"
DOWNLOAD_CACHE_DIR="/root/.local/share/tts"

# Créer le répertoire cible s'il n'existe pas
mkdir -p "$MODELS_TARGET_DIR"

# Vérifier et télécharger/copier le modèle français
if [ ! -d "$MODELS_TARGET_DIR/$MODEL_FR" ]; then
    echo "Téléchargement/Copie du modèle $MODEL_FR..."
    export COQUI_TOS_AGREED=1 # Accepter les conditions
    # Essayer de télécharger (peut échouer si déjà dans le cache mais pas copié)
    python -c "from TTS.utils.manage import ModelManager; ModelManager().download_model('tts_models/fr/mai/tacotron2-DDC')" || echo "Téléchargement ignoré ou échoué, tentative de copie depuis le cache..."
    # Copier depuis le cache si le téléchargement a réussi ou s'il était déjà là
    if [ -d "$DOWNLOAD_CACHE_DIR/$MODEL_FR" ]; then
        cp -r "$DOWNLOAD_CACHE_DIR/$MODEL_FR" "$MODELS_TARGET_DIR/"
        echo "Modèle $MODEL_FR copié."
    else
        echo "ERREUR: Impossible de trouver $MODEL_FR dans le cache $DOWNLOAD_CACHE_DIR après tentative de téléchargement."
    fi
else
    echo "Modèle $MODEL_FR déjà présent dans $MODELS_TARGET_DIR."
fi

# Vérifier et télécharger/copier le modèle XTTS
if [ ! -d "$MODELS_TARGET_DIR/$MODEL_XTTS" ]; then
    echo "Téléchargement/Copie du modèle $MODEL_XTTS..."
    export COQUI_TOS_AGREED=1 # Accepter les conditions
    # Essayer de télécharger
    python -c "from TTS.utils.manage import ModelManager; ModelManager().download_model('tts_models/multilingual/multi-dataset/xtts_v2')" || echo "Téléchargement ignoré ou échoué, tentative de copie depuis le cache..."
    # Copier depuis le cache
    if [ -d "$DOWNLOAD_CACHE_DIR/$MODEL_XTTS" ]; then
        cp -r "$DOWNLOAD_CACHE_DIR/$MODEL_XTTS" "$MODELS_TARGET_DIR/"
        echo "Modèle $MODEL_XTTS copié."
    else
        echo "ERREUR: Impossible de trouver $MODEL_XTTS dans le cache $DOWNLOAD_CACHE_DIR après tentative de téléchargement."
    fi
else
    echo "Modèle $MODEL_XTTS déjà présent dans $MODELS_TARGET_DIR."
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