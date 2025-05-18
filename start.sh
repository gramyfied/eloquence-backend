#!/bin/bash

# Activer l'environnement virtuel si nécessaire
# source venv/bin/activate

# Charger les variables d'environnement
if [ -f .env.local ]; then
    export $(grep -v '^#' .env.local | xargs)
fi

# Démarrer l'agent Eloquence
python agent.py --url $LIVEKIT_URL --api-key $LIVEKIT_API_KEY --api-secret $LIVEKIT_API_SECRET