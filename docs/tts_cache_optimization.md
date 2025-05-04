# Optimisation du Cache TTS pour Eloquence

Ce document décrit l'optimisation du cache Redis pour le service TTS (Text-to-Speech) dans le système Eloquence. Cette optimisation vise à réduire la latence et à améliorer les performances du système.

## Architecture

L'optimisation du cache TTS repose sur trois composants principaux :

1. **Service de Cache TTS** (`tts_cache_service.py`) : Gère le stockage et la récupération des données audio dans Redis, avec des fonctionnalités avancées comme la compression, les métriques et le préchargement.

2. **Service TTS Optimisé** (`tts_service_optimized.py`) : Version améliorée du service TTS qui utilise le service de cache pour réduire la latence.

3. **API de Gestion du Cache** (`app/routes/tts_cache.py`) : Endpoints REST pour gérer le cache, obtenir des métriques et précharger des phrases courantes.

## Fonctionnalités Clés

### 1. Génération Optimisée des Clés de Cache

- Utilisation de hachage MD5 pour les textes longs
- Clés basées sur la langue, l'ID du speaker, l'émotion et le texte
- Préfixe configurable pour faciliter la gestion

### 2. Compression des Données

- Compression zlib des données audio avant stockage
- Compression conditionnelle basée sur la taille et le ratio de compression
- Stockage des métadonnées de compression avec les données

### 3. Métriques et Monitoring

- Suivi des taux de hit/miss du cache
- Mesure de la latence pour les opérations de lecture/écriture
- Statistiques sur l'utilisation de la mémoire Redis

### 4. Préchargement du Cache

- Script pour précharger des phrases courantes
- Catégorisation des phrases (salutations, instructions, feedback, etc.)
- Support pour différentes émotions

### 5. Gestion des Connexions Redis

- Pool de connexions pour une utilisation efficace
- Gestion robuste des erreurs
- Paramètres configurables (expiration, compression, etc.)

## Configuration

Les paramètres de configuration du cache TTS sont définis dans `core/config.py` :

```python
# Configuration du cache TTS
TTS_USE_CACHE: bool = True  # Activer/désactiver le cache
TTS_CACHE_PREFIX: str = "tts_cache:"  # Préfixe pour les clés de cache
TTS_CACHE_EXPIRATION_S: int = 3600 * 24  # Durée d'expiration (24h par défaut)
```

## Utilisation

### Intégration dans le Code

Pour utiliser le service TTS optimisé dans votre code :

```python
from services.tts_service_optimized import tts_service_optimized

# Synthétiser du texte en audio
audio_data = await tts_service_optimized.synthesize_text(
    text="Bonjour et bienvenue à Eloquence.",
    language="fr",
    emotion="encouragement"
)

# Streamer l'audio vers un client WebSocket
await tts_service_optimized.stream_synthesize(
    websocket_manager=websocket_manager,
    session_id=session_id,
    text="Bonjour et bienvenue à Eloquence.",
    emotion="encouragement"
)
```

### API REST

L'API REST expose les endpoints suivants pour gérer le cache :

- `GET /tts-cache/metrics` : Obtenir les métriques du cache
- `POST /tts-cache/reset-metrics` : Réinitialiser les métriques
- `POST /tts-cache/clear` : Vider le cache
- `POST /tts-cache/preload` : Précharger des phrases courantes
- `GET /tts-cache/status` : Obtenir l'état du cache

Exemple d'utilisation avec curl :

```bash
# Obtenir les métriques du cache
curl -X GET http://localhost:8000/tts-cache/metrics

# Précharger des phrases courantes
curl -X POST http://localhost:8000/tts-cache/preload \
  -H "Content-Type: application/json" \
  -d '{"phrases": ["Bonjour et bienvenue.", "Comment allez-vous ?"], "emotion": "encouragement"}'
```

### Script de Préchargement

Le script `scripts/preload_tts_cache.py` permet de précharger le cache avec des phrases courantes :

```bash
# Précharger toutes les catégories avec toutes les émotions
python scripts/preload_tts_cache.py

# Précharger des catégories spécifiques
python scripts/preload_tts_cache.py --categories greetings feedback_positive

# Précharger avec des émotions spécifiques
python scripts/preload_tts_cache.py --emotions encouragement empathie

# Vider le cache avant de précharger
python scripts/preload_tts_cache.py --clear

# Enregistrer les statistiques dans un fichier
python scripts/preload_tts_cache.py --output stats.json
```

## Performances

L'optimisation du cache TTS apporte les améliorations suivantes :

1. **Réduction de la Latence** : La latence est considérablement réduite pour les phrases courantes, passant de plusieurs secondes à quelques millisecondes.

2. **Économie de Ressources** : Moins de requêtes à l'API TTS, ce qui réduit la charge sur le serveur TTS.

3. **Meilleure Expérience Utilisateur** : Réponses plus rapides et plus fluides, particulièrement pour les phrases fréquemment utilisées.

## Bonnes Pratiques

Pour tirer le meilleur parti du cache TTS :

1. **Préchargez les Phrases Courantes** : Utilisez le script de préchargement pour les phrases fréquemment utilisées.

2. **Surveillez les Métriques** : Vérifiez régulièrement les métriques pour identifier les opportunités d'optimisation.

3. **Ajustez les Paramètres** : Adaptez les paramètres de cache (expiration, compression) en fonction de vos besoins.

4. **Gérez la Mémoire Redis** : Surveillez l'utilisation de la mémoire Redis et videz le cache si nécessaire.

## Dépannage

### Problèmes Courants

1. **Cache Non Utilisé** : Vérifiez que `TTS_USE_CACHE` est activé dans la configuration.

2. **Erreurs Redis** : Vérifiez que Redis est en cours d'exécution et accessible.

3. **Latence Élevée** : Vérifiez les métriques pour identifier les goulots d'étranglement.

### Logs

Les logs du service TTS et du cache contiennent des informations utiles pour le dépannage :

```
INFO - Cache TTS HIT pour session 123456
INFO - Cache TTS MISS pour texte: 'Bonjour et bienvenue...'
INFO - Audio TTS mis en cache (clé: tts_cache:fr:p225:Bonjour_et_bienvenue)
ERROR - Erreur lors de la lecture du cache TTS Redis: Connection refused
```

## Évolutions Futures

Voici quelques pistes d'amélioration pour le cache TTS :

1. **Cache Distribué** : Support pour un cache Redis distribué pour les déploiements à grande échelle.

2. **Préchargement Intelligent** : Analyse des logs pour identifier et précharger automatiquement les phrases les plus utilisées.

3. **Compression Adaptative** : Ajustement dynamique des paramètres de compression en fonction des caractéristiques des données.

4. **Intégration avec Prometheus/Grafana** : Exposition des métriques pour un monitoring avancé.