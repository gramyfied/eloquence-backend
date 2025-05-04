# Eloquence Backend

Backend du système de coaching vocal interactif pour l'application "Eloquence". Ce système permet aux utilisateurs d'améliorer leur expression orale grâce à une interaction naturelle, réactive et émotionnellement adaptée avec un coach IA.

## Architecture

Le backend est composé des modules suivants :

- **API Gateway (FastAPI/Starlette)** : Point d'entrée REST et WebSocket
- **Orchestrateur** : Cœur logique qui coordonne les modules et maintient l'état de session
- **Module VAD (Silero)** : Détecte début/fin de parole et pauses sur le flux audio entrant
- **Module ASR (faster-whisper)** : Transcrit les segments audio
- **Module LLM (Mistral)** : Génère réponses textuelles, adapte scénarios, détermine émotions
- **Module TTS (Coqui TTS)** : Synthétise le texte en audio avec émotion/voix spécifiée
- **Module Analyse (Kaldi)** : Exécute analyses GOP, fluidité, etc., de manière asynchrone
- **Stockage (BD/Cache/Fichiers)** : Persiste sessions, historique, scénarios, résultats feedback

## Fonctionnalités clés

- **Interaction naturelle** avec gestion des pauses et silences
- **Gestion des interruptions** avec arrêt rapide du TTS (<200ms)
- **Voix émotionnelle** avec 6 émotions cibles : encouragement, empathie, neutre, enthousiasme_modere, curiosite, reflexion
- **Feedback détaillé** sur la prononciation, fluidité et richesse lexicale
- **Scénarios hybrides** adaptables par l'IA
- **Architecture préparée** pour le multi-interlocuteurs

## Prérequis

- Python 3.10+
- Docker et Docker Compose
- CUDA compatible GPU (recommandé pour ASR et LLM)
- Au moins 16GB de RAM (32GB+ recommandé)
- Au moins 50GB d'espace disque

## Installation

### Avec Docker (recommandé)

1. Cloner le dépôt :
   ```bash
   git clone https://github.com/votre-organisation/eloquence-backend.git
   cd eloquence-backend
   ```

2. Créer un fichier `.env` à partir du modèle :
   ```bash
   cp .env.example .env
   ```

3. Modifier le fichier `.env` selon votre configuration

4. Lancer les services avec Docker Compose :
   ```bash
   docker-compose up -d
   ```

### Installation manuelle (développement)

1. Cloner le dépôt :
   ```bash
   git clone https://github.com/votre-organisation/eloquence-backend.git
   cd eloquence-backend
   ```

2. Créer un environnement virtuel Python :
   ```bash
   python -m venv venv
   source venv/bin/activate  # Sur Windows : venv\Scripts\activate
   ```

3. Installer les dépendances :
   ```bash
   pip install -r requirements.txt
   ```

4. Créer un fichier `.env` à partir du modèle :
   ```bash
   cp .env.example .env
   ```

5. Modifier le fichier `.env` selon votre configuration

6. Lancer les services externes (Redis, PostgreSQL, etc.) :
   ```bash
   docker-compose up -d redis db kaldi
   ```

7. Lancer l'application :
   ```bash
   uvicorn app.main:app --reload
   ```

8. Lancer le worker Celery dans un autre terminal :
   ```bash
   celery -A core.celery_app worker --loglevel=info
   ```

## Configuration

La configuration se fait via le fichier `.env` ou des variables d'environnement. Voici les principales options :

- `DATABASE_URL` : URL de connexion à la base de données
- `REDIS_URL` : URL de connexion à Redis
- `ASR_API_URL`, `LLM_API_URL`, `TTS_API_URL` : URLs des services d'IA
- `VAD_THRESHOLD`, `VAD_MIN_SILENCE_DURATION_MS` : Paramètres du VAD
- `ASR_MODEL_NAME`, `ASR_DEVICE`, `ASR_COMPUTE_TYPE` : Configuration ASR
- `LLM_MODEL_NAME`, `LLM_TEMPERATURE` : Configuration LLM
- `TTS_USE_CACHE`, `TTS_CACHE_EXPIRATION_S` : Configuration TTS

Voir `core/config.py` pour la liste complète des options.

## API

### API REST

- `POST /api/session/start` : Démarre une nouvelle session
- `GET /api/session/{session_id}/feedback` : Récupère les résultats d'analyse
- `POST /api/session/{session_id}/end` : Termine une session

### WebSocket

- `WS /ws/{session_id}` : Point d'entrée WebSocket pour le streaming audio bidirectionnel

## Développement

### Structure du projet

```
eloquence_backend_py/
├── app/                    # Application FastAPI
│   ├── routes/             # Routes API
│   └── main.py             # Point d'entrée
├── core/                   # Modules centraux
│   ├── config.py           # Configuration
│   ├── database.py         # Connexion BD
│   ├── models.py           # Modèles SQLAlchemy
│   └── celery_app.py       # Configuration Celery
├── services/               # Services métier
│   ├── vad_service.py      # Service VAD
│   ├── asr_service.py      # Service ASR
│   ├── llm_service.py      # Service LLM
│   ├── tts_service.py      # Service TTS
│   ├── kaldi_service.py    # Service Kaldi
│   └── orchestrator.py     # Orchestrateur
├── tests/                  # Tests unitaires et d'intégration
├── data/                   # Données persistantes
│   ├── audio/              # Fichiers audio
│   ├── feedback/           # Résultats d'analyse
│   └── models/             # Modèles IA
├── docker-compose.yml      # Configuration Docker Compose
├── Dockerfile              # Dockerfile principal
└── requirements.txt        # Dépendances Python
```

### Tests

Exécuter les tests unitaires :

```bash
pytest
```

Exécuter les tests avec couverture :

```bash
pytest --cov=app --cov=core --cov=services
```

## Performances

- **Latence visée** : < 5s pour le cycle complet (utilisateur parle -> IA répond)
- **TTFB du TTS** : < 1s
- **Arrêt TTS sur interruption** : < 200ms

## Licence

Ce projet est sous licence [MIT](LICENSE).