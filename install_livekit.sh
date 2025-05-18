#!/bin/bash
# Script pour installer le package LiveKit dans le conteneur Docker

# Installer le package LiveKit
pip install livekit

# Vérifier l'installation
python -c "import livekit; print('LiveKit installé avec succès')"