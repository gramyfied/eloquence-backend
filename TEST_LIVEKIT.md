# Guide d'Utilisation du Script de Test LiveKit

Ce document explique comment utiliser le script `test_livekit.py` pour vérifier que LiveKit, l'API et l'agent Eloquence fonctionnent correctement.

## Présentation

Le script `test_livekit.py` permet de tester trois composants principaux :

1. **Serveur LiveKit** : Vérifie que le serveur LiveKit est accessible et fonctionne correctement
2. **API** : Vérifie que l'API est accessible et que les endpoints fonctionnent correctement
3. **Agent Eloquence** : Vérifie que l'agent peut se connecter à une room LiveKit

## Prérequis

Avant d'exécuter le script, assurez-vous que :

1. Le serveur LiveKit est en cours d'exécution
2. L'API est en cours d'exécution
3. Les variables d'environnement sont correctement configurées dans `.env.local`

## Utilisation

### Test Complet

Pour exécuter tous les tests :

```bash
cd eloquence_backend_py
./test_livekit.py
```

### Test Spécifique

Pour tester uniquement un composant spécifique :

```bash
# Tester uniquement le serveur LiveKit
./test_livekit.py --test livekit

# Tester uniquement l'API
./test_livekit.py --test api

# Tester uniquement l'agent
./test_livekit.py --test agent
```

### Personnalisation des URLs

Vous pouvez spécifier des URLs personnalisées pour le serveur LiveKit et l'API :

```bash
./test_livekit.py --livekit-url ws://livekit.example.com:7880 --api-url http://api.example.com:8083
```

### Personnalisation de la Clé API

Vous pouvez spécifier une clé API personnalisée :

```bash
./test_livekit.py --api-key votre-clé-api
```

## Interprétation des Résultats

Le script affiche des logs détaillés pour chaque test, avec des indicateurs de succès (✅) ou d'échec (❌).

À la fin de l'exécution, un résumé des tests est affiché :

```
=== Résumé des Tests ===
Serveur LiveKit: ✅ OK
API: ✅ OK
Agent: ✅ OK
```

Le script retourne un code de sortie 0 si tous les tests réussissent, et 1 si au moins un test échoue.

## Exemples de Scénarios

### 1. Vérification après Déploiement

Après avoir déployé le backend Eloquence avec LiveKit, exécutez le test complet pour vérifier que tout fonctionne correctement :

```bash
cd eloquence_backend_py
./test_livekit.py
```

### 2. Débogage du Serveur LiveKit

Si vous rencontrez des problèmes avec le serveur LiveKit, exécutez le test spécifique :

```bash
./test_livekit.py --test livekit
```

### 3. Débogage de l'API

Si vous rencontrez des problèmes avec l'API, exécutez le test spécifique :

```bash
./test_livekit.py --test api
```

### 4. Test avec un Serveur de Production

Pour tester avec un serveur de production :

```bash
./test_livekit.py --livekit-url wss://livekit.production.com:7880 --api-url https://api.production.com
```

## Résolution des Problèmes Courants

### Erreur de Connexion au Serveur LiveKit

Si le test du serveur LiveKit échoue :

1. Vérifiez que le serveur LiveKit est en cours d'exécution :
   ```bash
   sudo systemctl status livekit.service
   ```

2. Vérifiez que l'URL est correcte et que le port 7880 est accessible :
   ```bash
   nc -zv localhost 7880
   ```

3. Vérifiez les logs du serveur LiveKit :
   ```bash
   sudo journalctl -u livekit.service -f
   ```

### Erreur de Connexion à l'API

Si le test de l'API échoue :

1. Vérifiez que l'API est en cours d'exécution :
   ```bash
   sudo systemctl status eloquence-api.service
   ```

2. Vérifiez que l'URL est correcte et que le port 8083 est accessible :
   ```bash
   nc -zv localhost 8083
   ```

3. Vérifiez les logs de l'API :
   ```bash
   sudo journalctl -u eloquence-api.service -f
   ```

### Erreur avec l'Agent

Si le test de l'agent échoue :

1. Vérifiez que l'agent est correctement configuré :
   ```bash
   cat eloquence_backend_py/.env.local
   ```

2. Vérifiez les logs de l'agent :
   ```bash
   sudo journalctl -u eloquence-agent.service -f
   ```

## Intégration dans un Pipeline CI/CD

Vous pouvez intégrer ce script dans un pipeline CI/CD pour vérifier automatiquement que LiveKit fonctionne correctement après chaque déploiement :

```yaml
# Exemple pour GitHub Actions
test_livekit:
  runs-on: ubuntu-latest
  steps:
    - name: Checkout code
      uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        cd eloquence_backend_py
        pip install -r requirements.txt
    
    - name: Test LiveKit
      run: |
        cd eloquence_backend_py
        ./test_livekit.py --livekit-url ${{ secrets.LIVEKIT_URL }} --api-url ${{ secrets.API_URL }} --api-key ${{ secrets.API_KEY }}
```

## Conclusion

Le script `test_livekit.py` est un outil puissant pour vérifier que LiveKit, l'API et l'agent Eloquence fonctionnent correctement. Utilisez-le régulièrement pour vous assurer que votre déploiement est en bon état.