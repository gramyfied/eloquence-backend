# Guide de Débogage pour l'Intégration LiveKit

Ce document fournit des instructions détaillées pour résoudre les problèmes courants lors de l'intégration de LiveKit avec l'application Flutter Eloquence.

## Résolution de l'Erreur 404 sur `/api/sessions`

D'après les logs fournis, l'application Flutter reçoit une erreur 404 lors de l'appel à `http://51.159.110.4:8083/api/sessions`. Voici les étapes pour résoudre ce problème :

### 1. Vérifier que l'API est en cours d'exécution

```bash
# Vérifier si le processus API est en cours d'exécution
ps aux | grep api.py

# Vérifier le statut du service si vous utilisez systemd
sudo systemctl status eloquence-api.service
```

Si l'API n'est pas en cours d'exécution, démarrez-la :

```bash
# Démarrer l'API manuellement
cd /home/ubuntu/eloquence_backend_py
python api.py

# Ou démarrer le service systemd
sudo systemctl start eloquence-api.service
```

### 2. Vérifier que l'API est accessible

```bash
# Tester l'API avec curl
curl -v http://51.159.110.4:8083/

# Tester spécifiquement l'endpoint /api/sessions
curl -v -X POST http://51.159.110.4:8083/api/sessions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: default-key" \
  -d '{"user_id": "test-user", "language": "fr"}'
```

### 3. Vérifier les logs de l'API

```bash
# Vérifier les logs de l'API
sudo journalctl -u eloquence-api.service -f

# Ou si vous exécutez l'API manuellement, vérifiez la sortie du terminal
```

### 4. Vérifier la configuration du pare-feu

```bash
# Vérifier que le port 8083 est ouvert
sudo ufw status
sudo iptables -L -n | grep 8083

# Ouvrir le port si nécessaire
sudo ufw allow 8083/tcp
```

### 5. Vérifier la configuration réseau

```bash
# Vérifier que l'API écoute sur toutes les interfaces réseau
netstat -tulpn | grep 8083

# Si l'API n'écoute que sur localhost (127.0.0.1), modifiez api.py pour écouter sur 0.0.0.0
# Remplacez:
# uvicorn.run(app, host="127.0.0.1", port=8083)
# Par:
# uvicorn.run(app, host="0.0.0.0", port=8083)
```

## Solution Temporaire : Adapter l'Application Flutter

En attendant que l'API soit correctement déployée, vous pouvez adapter temporairement l'application Flutter pour utiliser les anciens endpoints :

```dart
// Dans api_service.dart, modifiez la méthode startSession

// Ancien code qui utilise le nouvel endpoint (qui retourne 404)
final response = await http.post(
  Uri.parse('$baseUrl/api/sessions'),
  headers: {
    ...headers,
    'X-API-Key': 'votre-clé-api',
  },
  body: jsonEncode({
    'user_id': userId,
    'language': language,
    'scenario_id': scenarioId,
    'is_multi_agent': isMultiAgent,
  }),
);

// Nouveau code qui utilise l'ancien endpoint (qui fonctionne)
final response = await http.post(
  Uri.parse('$baseUrl/api/session/start'),
  headers: headers,
  body: jsonEncode({
    'user_id': userId,
    'language': language,
    'scenario_id': scenarioId,
    'is_multi_agent': isMultiAgent,
  }),
);
```

## Vérification de l'Installation de l'API

Pour vérifier que l'API est correctement installée et configurée :

### 1. Vérifier les fichiers de l'API

```bash
# Vérifier que tous les fichiers nécessaires sont présents
ls -la /home/ubuntu/eloquence_backend_py/
ls -la /home/ubuntu/eloquence_backend_py/adapters/
```

### 2. Vérifier les dépendances Python

```bash
# Vérifier que toutes les dépendances sont installées
cd /home/ubuntu/eloquence_backend_py
pip list | grep livekit
pip list | grep fastapi
pip list | grep uvicorn
```

### 3. Tester l'API manuellement

```bash
# Démarrer l'API en mode debug
cd /home/ubuntu/eloquence_backend_py
python -m uvicorn api:app --host 0.0.0.0 --port 8083 --log-level debug
```

## Déploiement Correct de l'API

Si l'API n'est pas correctement déployée, suivez ces étapes pour la déployer :

### 1. Copier les fichiers

```bash
# Créer le répertoire si nécessaire
mkdir -p /home/ubuntu/eloquence_backend_py/adapters

# Copier les fichiers
cp -r /chemin/vers/eloquence_backend_py/* /home/ubuntu/eloquence_backend_py/
```

### 2. Installer les dépendances

```bash
cd /home/ubuntu/eloquence_backend_py
pip install -r requirements.txt
```

### 3. Configurer l'environnement

```bash
# Modifier .env.local si nécessaire
nano /home/ubuntu/eloquence_backend_py/.env.local
```

### 4. Démarrer l'API

```bash
# Démarrer l'API manuellement
cd /home/ubuntu/eloquence_backend_py
python api.py

# Ou configurer et démarrer le service systemd
sudo cp /home/ubuntu/eloquence_backend_py/eloquence-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable eloquence-api.service
sudo systemctl start eloquence-api.service
```

## Vérification de l'URL et du Port

Assurez-vous que l'URL et le port utilisés dans l'application Flutter correspondent à ceux de l'API déployée :

```dart
// Dans l'application Flutter, vérifiez que l'URL de base est correcte
final baseUrl = 'http://51.159.110.4:8083';
```

Si l'API est déployée sur un autre serveur ou port, mettez à jour l'URL en conséquence.

## Vérification des Logs en Temps Réel

Pour surveiller les logs de l'API et de l'application Flutter en même temps :

```bash
# Terminal 1 : Logs de l'API
sudo journalctl -u eloquence-api.service -f

# Terminal 2 : Logs de l'application Flutter
./run_with_filtered_logs.sh
```

## Conclusion

Si après avoir suivi ces étapes, l'erreur 404 persiste, il est possible que :

1. L'API ne soit pas correctement déployée
2. L'URL ou le port utilisé dans l'application Flutter soit incorrect
3. Un pare-feu ou un proxy bloque les requêtes

Dans ce cas, vérifiez les logs de l'API et de l'application Flutter pour obtenir plus d'informations sur l'erreur.