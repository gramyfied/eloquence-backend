#!/bin/bash
# Script pour récupérer les fichiers audio de test depuis la branche eloquence-v2

set -e  # Arrêter le script en cas d'erreur

# Répertoire de destination pour les fichiers audio
AUDIO_DIR="../assets/test_audio"
REPO_URL="https://github.com/votre-organisation/eloquence.git"  # À remplacer par l'URL réelle du dépôt
BRANCH="eloquence-v2"

# Créer le répertoire de destination s'il n'existe pas
mkdir -p "$AUDIO_DIR"

echo "=== Récupération des fichiers audio de test ==="
echo "Branche source: $BRANCH"
echo "Répertoire de destination: $AUDIO_DIR"

# Vérifier si git est installé
if ! command -v git &> /dev/null; then
    echo "Erreur: git n'est pas installé. Veuillez l'installer pour continuer."
    exit 1
fi

# Créer un répertoire temporaire
TMP_DIR=$(mktemp -d)
echo "Répertoire temporaire créé: $TMP_DIR"

# Cloner uniquement la branche spécifiée et de manière superficielle (--depth 1)
echo "Clonage du dépôt (branche $BRANCH)..."
git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$TMP_DIR" || {
    echo "Erreur: Impossible de cloner le dépôt. Vérifiez l'URL et vos permissions."
    rm -rf "$TMP_DIR"
    exit 1
}

# Vérifier si le répertoire assets/test_audio existe dans le dépôt cloné
if [ ! -d "$TMP_DIR/assets/test_audio" ]; then
    echo "Erreur: Le répertoire assets/test_audio n'existe pas dans la branche $BRANCH."
    rm -rf "$TMP_DIR"
    exit 1
fi

# Copier les fichiers audio
echo "Copie des fichiers audio..."
cp -r "$TMP_DIR/assets/test_audio/"* "$AUDIO_DIR/"

# Nettoyer
rm -rf "$TMP_DIR"

# Afficher les fichiers récupérés
echo "Fichiers audio récupérés:"
ls -la "$AUDIO_DIR"

echo "=== Récupération terminée avec succès ==="
