# Guide d'Intégration Frontend pour Eloquence avec LiveKit

Ce document explique comment intégrer le frontend Flutter avec le nouveau backend Eloquence basé sur LiveKit.

## Vue d'ensemble

Le nouveau backend utilise LiveKit pour gérer les flux audio en temps réel via WebRTC. L'intégration frontend nécessite :

1. Appeler l'API REST pour créer/gérer des sessions
2. Se connecter à LiveKit avec le token fourni par l'API
3. Gérer les flux audio bidirectionnels via WebRTC

## 1. Configuration du SDK LiveKit pour Flutter

### Installation

Ajoutez les dépendances LiveKit à votre `pubspec.yaml` :

```yaml
dependencies:
  livekit_client: ^1.4.0
```

Exécutez `flutter pub get` pour installer les dépendances.

### Configuration des permissions

#### Android

Ajoutez les permissions suivantes à votre fichier `AndroidManifest.xml` :

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.RECORD_AUDIO" />
<uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS" />
```

#### iOS

Ajoutez les descriptions suivantes à votre fichier `Info.plist` :

```xml
<key>NSMicrophoneUsageDescription</key>
<string>Eloquence a besoin d'accéder au microphone pour les sessions de coaching vocal</string>
```

## 2. API REST pour la Gestion des Sessions

### Endpoints

#### Créer une session

```
POST /api/sessions
```

**Headers :**
```
X-API-Key: votre-clé-api
Content-Type: application/json
```

**Request Body :**
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

**Response :**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "room_name": "eloquence-550e8400-e29b-41d4-a716-446655440000",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "url": "ws://localhost:7880"
}
```

#### Terminer une session

```
DELETE /api/sessions/{session_id}
```

**Headers :**
```
X-API-Key: votre-clé-api
```

### Exemple d'utilisation avec Dio

```dart
import 'package:dio/dio.dart';

class EloquenceApi {
  final Dio _dio = Dio();
  final String baseUrl = 'http://votre-serveur:8083';
  final String apiKey = 'votre-clé-api';

  Future<Map<String, dynamic>> createSession({
    required String userId,
    String language = 'fr',
    String? scenarioId,
    String? goal,
    String? agentProfileId,
    bool isMultiAgent = false,
  }) async {
    try {
      final response = await _dio.post(
        '$baseUrl/api/sessions',
        options: Options(
          headers: {
            'X-API-Key': apiKey,
            'Content-Type': 'application/json',
          },
        ),
        data: {
          'user_id': userId,
          'language': language,
          'scenario_id': scenarioId,
          'goal': goal,
          'agent_profile_id': agentProfileId,
          'is_multi_agent': isMultiAgent,
        },
      );
      return response.data;
    } catch (e) {
      throw Exception('Erreur lors de la création de la session: $e');
    }
  }

  Future<void> endSession(String sessionId) async {
    try {
      await _dio.delete(
        '$baseUrl/api/sessions/$sessionId',
        options: Options(
          headers: {
            'X-API-Key': apiKey,
          },
        ),
      );
    } catch (e) {
      throw Exception('Erreur lors de la terminaison de la session: $e');
    }
  }
}
```

## 3. Intégration avec LiveKit

### Connexion à une Room LiveKit

```dart
import 'package:livekit_client/livekit_client.dart';

class EloquenceSession {
  Room? _room;
  LocalAudioTrack? _microphoneTrack;

  Future<void> connect({
    required String url,
    required String token,
  }) async {
    try {
      // Créer une nouvelle room
      _room = Room();

      // Se connecter à la room
      await _room!.connect(
        url,
        token,
        connectOptions: const ConnectOptions(
          autoSubscribe: true,
        ),
      );

      // Activer le microphone
      _microphoneTrack = await LocalAudioTrack.create();
      await _room!.localParticipant?.publishAudioTrack(_microphoneTrack!);

      print('Connecté à la room LiveKit avec succès');
    } catch (e) {
      print('Erreur lors de la connexion à LiveKit: $e');
      throw Exception('Erreur de connexion LiveKit: $e');
    }
  }

  Future<void> disconnect() async {
    try {
      // Libérer les ressources audio
      await _microphoneTrack?.stop();
      
      // Déconnecter de la room
      await _room?.disconnect();
      
      _microphoneTrack = null;
      _room = null;
      
      print('Déconnecté de la room LiveKit');
    } catch (e) {
      print('Erreur lors de la déconnexion: $e');
    }
  }
}
```

### Gestion des Événements Audio

```dart
// Dans votre classe EloquenceSession

void setupEventListeners() {
  _room?.addListener(_onRoomEvent);
  
  // Écouter les participants distants (l'agent)
  _room?.participants.forEach((sid, participant) {
    participant.addListener(_onParticipantEvent);
  });
  
  // Écouter les nouveaux participants
  _room?.on<ParticipantConnectedEvent>((event) {
    event.participant.addListener(_onParticipantEvent);
  });
}

void _onRoomEvent() {
  // Gérer les événements de la room
}

void _onParticipantEvent(ParticipantEvent event) {
  if (event is TrackSubscribedEvent) {
    // Un nouveau track a été souscrit (l'agent a commencé à parler)
    if (event.publication.kind == TrackType.audio) {
      print('Audio de l\'agent reçu');
      // Vous pouvez déclencher une UI pour montrer que l'agent parle
    }
  } else if (event is TrackUnsubscribedEvent) {
    // Un track a été désouscrit (l'agent a arrêté de parler)
    if (event.publication.kind == TrackType.audio) {
      print('Audio de l\'agent terminé');
      // Vous pouvez mettre à jour l'UI pour montrer que l'agent ne parle plus
    }
  }
}
```

## 4. Exemple Complet d'Intégration

Voici un exemple complet d'intégration dans une application Flutter :

```dart
import 'package:flutter/material.dart';
import 'package:livekit_client/livekit_client.dart';
import 'package:permission_handler/permission_handler.dart';

class CoachingSessionScreen extends StatefulWidget {
  @override
  _CoachingSessionScreenState createState() => _CoachingSessionScreenState();
}

class _CoachingSessionScreenState extends State<CoachingSessionScreen> {
  final EloquenceApi _api = EloquenceApi();
  final EloquenceSession _session = EloquenceSession();
  
  String _sessionId = '';
  bool _isConnected = false;
  bool _isAgentSpeaking = false;
  bool _isUserSpeaking = false;
  
  @override
  void initState() {
    super.initState();
    _requestPermissions();
  }
  
  Future<void> _requestPermissions() async {
    await Permission.microphone.request();
  }
  
  Future<void> _startSession() async {
    try {
      // 1. Créer une session via l'API
      final sessionData = await _api.createSession(
        userId: 'user123',
        goal: 'Améliorer ma prononciation',
      );
      
      setState(() {
        _sessionId = sessionData['session_id'];
      });
      
      // 2. Se connecter à LiveKit
      await _session.connect(
        url: sessionData['url'],
        token: sessionData['token'],
      );
      
      // 3. Configurer les écouteurs d'événements
      _session.setupEventListeners();
      
      setState(() {
        _isConnected = true;
      });
    } catch (e) {
      print('Erreur lors du démarrage de la session: $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Erreur: $e')),
      );
    }
  }
  
  Future<void> _endSession() async {
    try {
      // 1. Déconnecter de LiveKit
      await _session.disconnect();
      
      // 2. Terminer la session via l'API
      if (_sessionId.isNotEmpty) {
        await _api.endSession(_sessionId);
      }
      
      setState(() {
        _isConnected = false;
        _sessionId = '';
      });
    } catch (e) {
      print('Erreur lors de la fin de la session: $e');
    }
  }
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Session de Coaching Vocal'),
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (_isConnected) ...[
              Text('Session active: $_sessionId'),
              SizedBox(height: 20),
              Icon(
                _isAgentSpeaking ? Icons.record_voice_over : Icons.voice_over_off,
                size: 50,
                color: _isAgentSpeaking ? Colors.green : Colors.grey,
              ),
              Text(_isAgentSpeaking ? 'Coach parle' : 'Coach écoute'),
              SizedBox(height: 20),
              Icon(
                _isUserSpeaking ? Icons.mic : Icons.mic_off,
                size: 50,
                color: _isUserSpeaking ? Colors.blue : Colors.grey,
              ),
              Text(_isUserSpeaking ? 'Vous parlez' : 'Vous êtes silencieux'),
              SizedBox(height: 40),
              ElevatedButton(
                onPressed: _endSession,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.red,
                ),
                child: Text('Terminer la session'),
              ),
            ] else ...[
              Text('Pas de session active'),
              SizedBox(height: 20),
              ElevatedButton(
                onPressed: _startSession,
                child: Text('Démarrer une session'),
              ),
            ],
          ],
        ),
      ),
    );
  }
  
  @override
  void dispose() {
    // Assurer que la session est terminée lorsque l'écran est fermé
    if (_isConnected) {
      _endSession();
    }
    super.dispose();
  }
}
```

## 5. Conseils pour le Débogage

### Logs LiveKit

Pour activer les logs détaillés de LiveKit :

```dart
void initLiveKitLogs() {
  Logger.root.level = Level.FINE;
  Logger.root.onRecord.listen((record) {
    print('${record.level.name}: ${record.time}: ${record.message}');
  });
}
```

### Problèmes Courants

1. **Erreur de connexion à LiveKit** : Vérifiez que l'URL et le token sont corrects et que le serveur LiveKit est accessible.

2. **Pas d'audio** : Vérifiez les permissions du microphone et assurez-vous que le track audio est bien publié.

3. **Latence élevée** : Vérifiez la qualité de la connexion réseau et les logs côté serveur.

## 6. Ressources Supplémentaires

- [Documentation LiveKit Flutter](https://docs.livekit.io/client-sdk-flutter/index.html)
- [Exemples LiveKit Flutter](https://github.com/livekit/client-sdk-flutter/tree/main/example)
- [Guide WebRTC pour Flutter](https://webrtc.org/getting-started/flutter)

Pour toute question supplémentaire, contactez l'équipe backend Eloquence.