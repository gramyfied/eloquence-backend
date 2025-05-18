# Guide de Migration pour l'Intégration LiveKit dans l'Application Flutter Eloquence

Ce document détaille les modifications nécessaires pour adapter l'application Flutter Eloquence existante à la nouvelle implémentation backend LiveKit.

## Comparaison des Endpoints

### Endpoints Actuels vs Nouveaux Endpoints

| Fonctionnalité | Endpoint Actuel | Nouvel Endpoint | Méthode HTTP |
|----------------|----------------|-----------------|--------------|
| Démarrer une session | `/api/session/start` | `/api/sessions` | POST |
| Terminer une session | `/api/session/{id}/end` | `/api/sessions/{id}` | DELETE |
| Récupérer un token LiveKit | `/livekit/token` | *Intégré dans la réponse de `/api/sessions`* | - |
| WebSocket | `ws://51.159.110.4:8083/ws/simple/{session_id}` | *Remplacé par LiveKit WebRTC* | - |

### Changements dans les Paramètres de Requête

#### Démarrer une session (POST /api/sessions)

**Ancien format :**
```json
{
  // Format non spécifié dans les logs
}
```

**Nouveau format :**
```json
{
  "user_id": "user123",
  "language": "fr",
  "scenario_id": "scenario123",
  "goal": "Améliorer la prononciation",
  "agent_profile_id": "coach",
  "is_multi_agent": false
}
```

#### Réponse de création de session

**Ancien format :**
```json
{
  // Format non spécifié dans les logs
}
```

**Nouveau format :**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "room_name": "eloquence-550e8400-e29b-41d4-a716-446655440000",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "url": "ws://localhost:7880"
}
```

## Modifications Nécessaires dans le Code

### 1. Mise à jour des Endpoints API

#### Démarrer une session

```dart
// Ancien code
final url = '$baseUrl/api/session/start';
final response = await http.post(
  Uri.parse(url),
  headers: headers,
  body: jsonEncode(requestBody),
);

// Nouveau code
final url = '$baseUrl/api/sessions';
final response = await http.post(
  Uri.parse(url),
  headers: {
    ...headers,
    'X-API-Key': 'votre-clé-api',
    'Content-Type': 'application/json',
  },
  body: jsonEncode({
    'user_id': 'user-${DateTime.now().millisecondsSinceEpoch}',
    'language': 'fr',
    'scenario_id': scenarioId,
    'goal': goal,
    'agent_profile_id': agentProfileId,
    'is_multi_agent': isMultiAgent,
  }),
);
```

#### Terminer une session

```dart
// Ancien code
final response = await http.post(
  Uri.parse('$baseUrl/api/session/$sessionId/end'),
  headers: headers,
);

// Nouveau code
final response = await http.delete(
  Uri.parse('$baseUrl/api/sessions/$sessionId'),
  headers: {
    ...headers,
    'X-API-Key': 'votre-clé-api',
  },
);
```

### 2. Remplacement du WebSocket par LiveKit

#### Installation du SDK LiveKit

Ajoutez la dépendance LiveKit à votre `pubspec.yaml` :

```yaml
dependencies:
  livekit_client: ^1.4.0
```

#### Connexion à LiveKit

```dart
// Ancien code - Connexion WebSocket
WebSocketChannel channel = WebSocketChannel.connect(
  Uri.parse('ws://$baseUrl/ws/simple/$sessionId'),
);

// Nouveau code - Connexion LiveKit
Future<void> connectToLiveKit(Map<String, dynamic> sessionData) async {
  final url = sessionData['url'];
  final token = sessionData['token'];
  
  // Créer une room LiveKit
  final room = Room();
  
  try {
    // Se connecter à la room
    await room.connect(url, token);
    
    // Publier le microphone
    final audioTrack = await LocalAudioTrack.create();
    await room.localParticipant?.publishAudioTrack(audioTrack);
    
    // Configurer les écouteurs d'événements
    room.participants.forEach((sid, participant) {
      participant.addListener(_onParticipantEvent);
    });
    
    room.on<ParticipantConnectedEvent>((event) {
      event.participant.addListener(_onParticipantEvent);
    });
    
    print('Connecté à LiveKit avec succès');
  } catch (e) {
    print('Erreur lors de la connexion à LiveKit: $e');
    throw e;
  }
}

void _onParticipantEvent(ParticipantEvent event) {
  if (event is TrackSubscribedEvent) {
    if (event.publication.kind == TrackType.audio) {
      print('Audio de l\'agent reçu');
      // Traiter l'audio entrant
    }
  }
}
```

### 3. Exemple Complet d'Intégration

```dart
class EloquenceSession {
  final String baseUrl;
  final String apiKey;
  
  String? sessionId;
  Room? room;
  LocalAudioTrack? microphoneTrack;
  
  EloquenceSession({
    required this.baseUrl,
    required this.apiKey,
  });
  
  Future<void> startSession({
    required String userId,
    String language = 'fr',
    String? scenarioId,
    String? goal,
    String? agentProfileId,
    bool isMultiAgent = false,
  }) async {
    try {
      // 1. Créer une session via l'API
      final response = await http.post(
        Uri.parse('$baseUrl/api/sessions'),
        headers: {
          'X-API-Key': apiKey,
          'Content-Type': 'application/json',
        },
        body: jsonEncode({
          'user_id': userId,
          'language': language,
          'scenario_id': scenarioId,
          'goal': goal,
          'agent_profile_id': agentProfileId,
          'is_multi_agent': isMultiAgent,
        }),
      );
      
      if (response.statusCode != 200) {
        throw Exception('Échec de la création de session: ${response.statusCode}');
      }
      
      final sessionData = jsonDecode(response.body);
      sessionId = sessionData['session_id'];
      
      // 2. Se connecter à LiveKit
      await connectToLiveKit(sessionData);
      
      return sessionId;
    } catch (e) {
      print('Erreur lors du démarrage de la session: $e');
      throw e;
    }
  }
  
  Future<void> connectToLiveKit(Map<String, dynamic> sessionData) async {
    final url = sessionData['url'];
    final token = sessionData['token'];
    
    // Créer une room LiveKit
    room = Room();
    
    try {
      // Se connecter à la room
      await room!.connect(url, token);
      
      // Publier le microphone
      microphoneTrack = await LocalAudioTrack.create();
      await room!.localParticipant?.publishAudioTrack(microphoneTrack!);
      
      // Configurer les écouteurs d'événements
      room!.participants.forEach((sid, participant) {
        participant.addListener(_onParticipantEvent);
      });
      
      room!.on<ParticipantConnectedEvent>((event) {
        event.participant.addListener(_onParticipantEvent);
      });
      
      print('Connecté à LiveKit avec succès');
    } catch (e) {
      print('Erreur lors de la connexion à LiveKit: $e');
      throw e;
    }
  }
  
  void _onParticipantEvent(ParticipantEvent event) {
    if (event is TrackSubscribedEvent) {
      if (event.publication.kind == TrackType.audio) {
        print('Audio de l\'agent reçu');
        // Traiter l'audio entrant
      }
    }
  }
  
  Future<void> endSession() async {
    try {
      // 1. Déconnecter de LiveKit
      await microphoneTrack?.stop();
      await room?.disconnect();
      
      // 2. Terminer la session via l'API
      if (sessionId != null) {
        final response = await http.delete(
          Uri.parse('$baseUrl/api/sessions/$sessionId'),
          headers: {
            'X-API-Key': apiKey,
          },
        );
        
        if (response.statusCode != 200) {
          print('Avertissement: Échec de la terminaison de session: ${response.statusCode}');
        }
      }
      
      microphoneTrack = null;
      room = null;
      sessionId = null;
    } catch (e) {
      print('Erreur lors de la fin de la session: $e');
      throw e;
    }
  }
}
```

## Résolution des Problèmes Courants

### Erreur 502 lors de la connexion à LiveKit

Si vous rencontrez une erreur 502 lors de la connexion à `wss://livekit.xn--loquence-90a.com`, vérifiez les points suivants :

1. **URL correcte** : Assurez-vous d'utiliser l'URL fournie dans la réponse de l'API `/api/sessions`
2. **Port correct** : Vérifiez que le port 7880 est ouvert et accessible
3. **Certificats SSL** : Pour les connexions WSS, vérifiez que les certificats SSL sont valides
4. **Pare-feu** : Vérifiez que les ports nécessaires (7880 pour la signalisation, 50000-60000 pour les flux média) sont ouverts

### Problèmes d'authentification

Si vous rencontrez des erreurs 401 ou 403, vérifiez que vous incluez l'en-tête `X-API-Key` avec la bonne valeur dans toutes vos requêtes API.

### Problèmes de connexion WebRTC

Si la connexion WebRTC échoue après une connexion réussie à LiveKit :

1. **Permissions** : Vérifiez que les permissions de microphone sont accordées
2. **Ports média** : Assurez-vous que les ports UDP/TCP 50000-60000 sont ouverts
3. **STUN/TURN** : Vérifiez que les serveurs STUN/TURN sont accessibles

## Configuration pour Différents Environnements

### Développement

```dart
const baseUrl = 'http://localhost:8083';
const livekitUrl = 'ws://localhost:7880';
```

### Production

```dart
const baseUrl = 'https://api.eloquence.com';
const livekitUrl = 'wss://livekit.eloquence.com';
```

## Vérification de la Configuration LiveKit

Pour vérifier que votre serveur LiveKit est correctement configuré et accessible :

```bash
# Vérifier que le port 7880 est ouvert
nc -zv livekit.xn--loquence-90a.com 7880

# Vérifier les certificats SSL
openssl s_client -connect livekit.xn--loquence-90a.com:7880

# Vérifier les logs du serveur LiveKit
sudo journalctl -u livekit.service -f
```

## Conclusion

Cette migration nécessite principalement des changements dans les endpoints API et le remplacement du WebSocket par LiveKit WebRTC. En suivant ce guide, vous pourrez adapter votre application Flutter Eloquence existante pour utiliser la nouvelle implémentation backend LiveKit.

Pour toute assistance supplémentaire, consultez les fichiers `FRONTEND_INTEGRATION.md`, `ENDPOINTS.md` et `LOGS.md`.