#!/bin/bash

# Script pour filtrer les logs et ne garder que les informations importantes
# Usage: commande | ./filter_logs.sh
# Exemple: flutter run | ./filter_logs.sh
# Exemple: uvicorn app.main:app --reload | ./filter_logs.sh

# Définir les couleurs pour une meilleure lisibilité
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Lire l'entrée standard ligne par ligne
while IFS= read -r line; do
    # Filtrer les logs DEBUG
    if [[ $line == *"DEBUG"* ]]; then
        continue
    fi
    
    # Mettre en évidence les erreurs
    if [[ $line == *"ERROR"* || $line == *"CRITICAL"* || $line == *"Exception"* || $line == *"Error"* ]]; then
        echo -e "${RED}$line${NC}"
        continue
    fi
    
    # Mettre en évidence les avertissements
    if [[ $line == *"WARNING"* || $line == *"WARN"* ]]; then
        echo -e "${YELLOW}$line${NC}"
        continue
    fi
    
    # Filtrer les logs INFO trop verbeux
    if [[ $line == *"INFO"* ]]; then
        # Garder les logs INFO importants
        if [[ $line == *"Transcription ASR"* || 
              $line == *"Synthèse TTS"* || 
              $line == *"Traitement complet"* || 
              $line == *"Session"*"terminée"* || 
              $line == *"Interruption"* ]]; then
            echo -e "${GREEN}$line${NC}"
        # Ignorer les logs INFO moins importants
        elif [[ $line == *"send_json"* || 
                $line == *"WebSocket trouvé"* || 
                $line == *"Appel de send_json"* || 
                $line == *"Message texte reçu"* || 
                $line == *"Type de message"* || 
                $line == *"Timeout en attendant"* ]]; then
            continue
        else
            # Afficher les autres logs INFO
            echo -e "${BLUE}$line${NC}"
        fi
        continue
    fi
    
    # Mettre en évidence les durées et métriques de performance
    if [[ $line == *"terminée en"* || $line == *"durée:"* || $line == *"latence:"* ]]; then
        echo -e "${PURPLE}$line${NC}"
        continue
    fi
    
    # Afficher les autres lignes sans modification
    echo "$line"
done

exit 0