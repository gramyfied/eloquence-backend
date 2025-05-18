# Commandes pour Consulter les Logs

Ce document fournit les commandes pour consulter les logs des différents composants du système Eloquence avec LiveKit pendant les tests.

## 1. Logs de l'Agent LiveKit

### En mode développement (console)

Lorsque vous exécutez l'agent en mode console, les logs sont affichés directement dans le terminal :

```bash
cd eloquence_backend_py
python agent.py console
```

### En mode service

Si l'agent est exécuté en tant que service systemd :

```bash
# Afficher les logs en temps réel
sudo journalctl -u eloquence-agent.service -f

# Afficher les logs avec horodatage
sudo journalctl -u eloquence-agent.service --since "1 hour ago"

# Afficher uniquement les erreurs
sudo journalctl -u eloquence-agent.service -p err
```

### Logs de débogage détaillés

Pour activer les logs de débogage détaillés, modifiez le niveau de log dans `agent.py` :

```python
logging.basicConfig(
    level=logging.DEBUG,  # Changer INFO en DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

## 2. Logs de l'API

### En mode développement

Lorsque vous exécutez l'API directement :

```bash
cd eloquence_backend_py
python api.py
```

### En mode service

Si l'API est exécutée en tant que service systemd :

```bash
# Afficher les logs en temps réel
sudo journalctl -u eloquence-api.service -f

# Afficher les logs avec horodatage
sudo journalctl -u eloquence-api.service --since "1 hour ago"

# Afficher uniquement les erreurs
sudo journalctl -u eloquence-api.service -p err
```

## 3. Logs du Serveur LiveKit

```bash
# Afficher les logs en temps réel
sudo journalctl -u livekit.service -f

# Afficher les logs avec horodatage
sudo journalctl -u livekit.service --since "1 hour ago"

# Afficher uniquement les erreurs
sudo journalctl -u livekit.service -p err
```

## 4. Logs des Adaptateurs

### Logs de l'Adaptateur Whisper

Pour voir les logs spécifiques à l'adaptateur Whisper :

```bash
sudo journalctl -u eloquence-agent.service -f | grep "whisper_adapter"
```

### Logs de l'Adaptateur Mistral

Pour voir les logs spécifiques à l'adaptateur Mistral :

```bash
sudo journalctl -u eloquence-agent.service -f | grep "mistral_adapter"
```

### Logs de l'Adaptateur Coqui

Pour voir les logs spécifiques à l'adaptateur Coqui :

```bash
sudo journalctl -u eloquence-agent.service -f | grep "coqui_adapter"
```

## 5. Logs Combinés pour le Débogage

Pour voir tous les logs pertinents en même temps pendant les tests :

```bash
# Ouvrir plusieurs terminaux et exécuter une commande dans chacun
# Terminal 1 - Logs de l'API
sudo journalctl -u eloquence-api.service -f

# Terminal 2 - Logs de l'Agent
sudo journalctl -u eloquence-agent.service -f

# Terminal 3 - Logs de LiveKit
sudo journalctl -u livekit.service -f
```

Ou utilisez `tmux` pour diviser votre terminal :

```bash
# Installer tmux si nécessaire
sudo apt install tmux

# Démarrer une session tmux
tmux

# Diviser l'écran horizontalement
Ctrl+b "

# Diviser l'écran verticalement
Ctrl+b %

# Naviguer entre les panneaux
Ctrl+b flèche

# Dans chaque panneau, exécutez une des commandes de log
```

## 6. Logs Temporaires pour les Tests

Si vous exécutez les composants manuellement pour les tests, vous pouvez rediriger les logs vers des fichiers :

```bash
# Exécuter l'agent avec logs dans un fichier
python agent.py > agent_logs.txt 2>&1 &

# Exécuter l'API avec logs dans un fichier
python api.py > api_logs.txt 2>&1 &

# Suivre les logs en temps réel
tail -f agent_logs.txt
tail -f api_logs.txt
```

## 7. Logs des Services Existants

Pour voir les logs des services existants (Whisper, Mistral, Coqui) :

```bash
# Logs du service Whisper
sudo journalctl -u whisper-service.service -f

# Logs du service Mistral
sudo journalctl -u mistral-service.service -f

# Logs du service Coqui
sudo journalctl -u coqui-service.service -f
```

## 8. Logs du Frontend Flutter

Pour voir les logs du frontend Flutter pendant les tests :

```bash
# Logs Flutter sur Android
flutter run --verbose

# Logs Flutter sur iOS
flutter logs
```

Ces commandes vous permettront de surveiller tous les aspects du système pendant vos tests et de diagnostiquer rapidement tout problème qui pourrait survenir.