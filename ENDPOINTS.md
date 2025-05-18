# Endpoints Spécifiques pour l'Intégration Frontend

Ce document détaille les endpoints spécifiques auxquels le frontend doit se connecter pour l'intégration avec le backend Eloquence basé sur LiveKit.

## 1. Endpoints API REST

### Base URL

```
http://votre-serveur:8083
```

Remplacez `votre-serveur` par l'adresse IP ou le nom d'hôte de votre serveur backend.

### Endpoints

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/api/sessions` | Créer une nouvelle session |
| DELETE | `/api/sessions/{session_id}` | Terminer une session existante |

### Authentification

Tous les endpoints nécessitent une clé API dans l'en-tête `X-API-Key`.

## 2. Connexion WebRTC via LiveKit

### URL de Signalisation LiveKit

Le frontend doit se connecter à l'URL LiveKit fournie dans la réponse de l'endpoint `/api/sessions`. Cette URL est généralement au format :

```
ws://votre-serveur-livekit:7880
```

ou pour une connexion sécurisée :

```
wss://votre-serveur-livekit:7880
```

### Processus de Connexion

1. Le frontend appelle l'API REST pour créer une session (`POST /api/sessions`)
2. L'API retourne un token JWT et une URL LiveKit
3. Le frontend utilise ces informations pour établir une connexion WebRTC via le SDK LiveKit

### Exemple de Flux de Connexion

```
Frontend                          API REST                          LiveKit Server
   |                                |                                    |
   |--- POST /api/sessions -------->|                                    |
   |                                |--- Crée une room LiveKit --------->|
   |                                |<-- Room créée --------------------|
   |                                |--- Démarre l'agent Eloquence ---->|
   |<-- session_id, token, url -----|                                    |
   |                                |                                    |
   |--- Connexion WebRTC (url, token) ---------------------------->|
   |<-- Connexion établie ---------------------------------------->|
   |                                |                                    |
   |--- Flux audio bidirectionnel ----------------------------------->|
   |<-- Flux audio bidirectionnel ------------------------------------|
   |                                |                                    |
   |--- DELETE /api/sessions/{id} ->|                                    |
   |                                |--- Supprime la room LiveKit ------>|
   |<-- Succès --------------------|<-- Room supprimée ----------------|
```

## 3. Ports et Protocoles

| Service | Protocole | Port par défaut | Description |
|---------|-----------|-----------------|-------------|
| API REST | HTTP/HTTPS | 8083 | API pour la gestion des sessions |
| LiveKit Signalisation | WebSocket | 7880 | Signalisation WebRTC |
| LiveKit Media | UDP/TCP | 50000-60000 | Flux média WebRTC |

## 4. Configuration Réseau

Pour que l'intégration fonctionne correctement, assurez-vous que :

1. Le frontend peut accéder à l'API REST sur le port 8083
2. Le frontend peut établir une connexion WebSocket avec le serveur LiveKit sur le port 7880
3. Le frontend peut établir des connexions UDP/TCP avec le serveur LiveKit sur les ports 50000-60000 pour les flux média

Si vous utilisez des pare-feux ou des proxys, configurez-les pour autoriser ces connexions.

## 5. Environnements

### Développement

```
API REST: http://localhost:8083
LiveKit: ws://localhost:7880
```

### Production

```
API REST: https://api.votre-domaine.com
LiveKit: wss://livekit.votre-domaine.com
```

Assurez-vous de configurer correctement les certificats SSL pour les connexions sécurisées en production.