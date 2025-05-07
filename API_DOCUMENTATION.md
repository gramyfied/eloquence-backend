# Documentation API Eloquence pour Flutter/Dart

Cette documentation détaille tous les endpoints de l'API Eloquence, avec des exemples d'utilisation en Dart pour l'intégration avec une application Flutter.

## Table des matières

1. [Configuration](#configuration)
8. [Endpoints de scénarios](#endpoints-de-scénarios)
2. [Authentification](#authentification)
3. [Endpoints de santé](#endpoints-de-santé)
4. [Endpoints de chat](#endpoints-de-chat)
5. [Endpoints de coaching](#endpoints-de-coaching)
6. [Endpoints audio (TTS/STT)](#endpoints-audio)
7. [Endpoints de session](#endpoints-de-session)
8. [Endpoints de monitoring](#endpoints-de-monitoring)
9. [WebSockets](#websockets)
10. [Gestion des erreurs](#gestion-des-erreurs)
11. [Exemples complets](#exemples-complets)

## Configuration

### URL de base

```dart
// URL de base pour l'environnement de production
const String baseUrl = 'http://51.159.110.4:8083';

// URL de base pour l'environnement de développement local
const String localBaseUrl = 'http://localhost:8083';
```

### Configuration HTTP

```dart
import 'package:http/http.dart' as http;
import 'dart:convert';

// Configuration des en-têtes par défaut
Map<String, String> headers = {
  'Content-Type': 'application/json',
  'Accept': 'application/json',
};

// Ajouter un token d'authentification (si nécessaire)
void setAuthToken(String token) {
  headers['Authorization'] = 'Bearer $token';
}
```

## Authentification

L'API utilise une authentification simplifiée pour le développement. Dans l'environnement de production, un système d'authentification plus robuste sera mis en place.

```dart
// Fonction pour simuler l'authentification (à remplacer par une vraie authentification)
Future<String> authenticate(String username, String password) async {
  // Dans une implémentation réelle, vous feriez un appel API ici
  // Pour l'instant, on retourne un token factice
  return 'fake-auth-token';
}
```

## Endpoints de santé

### Vérifier l'état du serveur

```dart
Future<bool> checkServerHealth() async {
  final response = await http.get(Uri.parse('$baseUrl/health'), headers: headers);
  
  if (response.statusCode == 200) {
    final data = jsonDecode(response.body);
    return data['status'] == 'ok';
  }
  return false;
}
```

## Endpoints de chat

### Envoyer un message au chatbot

**Endpoint:** `POST /chat/`

**Paramètres:**
- `message`: Le message de l'utilisateur
- `context`: (Optionnel) Contexte pour le chatbot
- `session_id`: (Optionnel) ID de session pour continuer une conversation
- `history`: (Optionnel) Historique des messages précédents

```dart
Future<Map<String, dynamic>> sendChatMessage({
  required String message,
  String? context,
  String? sessionId,
  List<Map<String, String>>? history,
}) async {
  final Map<String, dynamic> body = {
    'message': message,
  };
  
  if (context != null) body['context'] = context;
  if (sessionId != null) body['session_id'] = sessionId;
  if (history != null) body['history'] = history;
  
  final response = await http.post(
    Uri.parse('$baseUrl/chat/'),
    headers: headers,
    body: jsonEncode(body),
  );
  
  if (response.statusCode == 200) {
    return jsonDecode(response.body);
  } else {
    throw Exception('Échec de l\'envoi du message: ${response.body}');
  }
}
```

**Exemple d'utilisation:**

```dart
try {
  final response = await sendChatMessage(
    message: "Bonjour, comment puis-je améliorer ma diction ?",
    context: "coaching_vocal",
  );
  
  print("Réponse du chatbot: ${response['response']}");
  if (response.containsKey('emotion')) {
    print("Émotion détectée: ${response['emotion']}");
  }
} catch (e) {
  print("Erreur: $e");
}
```

## Endpoints de coaching

### Initialiser une session de coaching

**Endpoint:** `GET /coaching/init`

**Paramètres:**
- `user_id`: ID de l'utilisateur (obligatoire)

```dart
Future<Map<String, dynamic>> initCoachingSession(String userId) async {
  final response = await http.get(
    Uri.parse('$baseUrl/coaching/init?user_id=$userId'),
    headers: headers,
  );
  
  if (response.statusCode == 200) {
    return jsonDecode(response.body);
  } else {
    throw Exception('Échec de l\'initialisation de la session: ${response.body}');
  }
}
```

### Générer un exercice de coaching

**Endpoint:** `POST /coaching/exercise/generate`

**Paramètres:**
- `exercise_type`: Type d'exercice (diction, articulation, etc.)
- `difficulty`: Niveau de difficulté (easy, medium, hard)
- `language`: Langue de l'exercice (fr, en, etc.)
- `context`: (Optionnel) Contexte supplémentaire

```dart
Future<Map<String, dynamic>> generateExercise({
  String exerciseType = 'diction',
  String difficulty = 'medium',
  String language = 'fr',
  Map<String, dynamic>? context,
}) async {
  final Map<String, dynamic> body = {
    'exercise_type': exerciseType,
    'difficulty': difficulty,
    'language': language,
  };
  
  if (context != null) body['context'] = context;
  
  final response = await http.post(
    Uri.parse('$baseUrl/coaching/exercise/generate'),
    headers: headers,
    body: jsonEncode(body),
  );
  
  if (response.statusCode == 200) {
    return jsonDecode(response.body);
  } else {
    throw Exception('Échec de la génération de l\'exercice: ${response.body}');
  }
}
```

**Exemple d'utilisation:**

```dart
try {
  final exercise = await generateExercise(
    exerciseType: 'articulation',
    difficulty: 'hard',
  );
  
  print("Titre: ${exercise['title']}");
  print("Description: ${exercise['description']}");
  print("Instructions: ${exercise['instructions']}");
  print("Contenu: ${exercise['content']}");
} catch (e) {
  print("Erreur: $e");
}
```

## Endpoints audio

### Synthèse vocale (TTS)

**Endpoint:** `POST /api/tts`

**Paramètres:**
- `text`: Texte à synthétiser (obligatoire)
- `voice`: Voix à utiliser (défaut: "default")
- `emotion`: Émotion à exprimer (défaut: "neutre")

```dart
Future<String> synthesizeSpeech({
  required String text,
  String voice = 'default',
  String emotion = 'neutre',
}) async {
  final response = await http.post(
    Uri.parse('$baseUrl/api/tts?text=${Uri.encodeComponent(text)}&voice=$voice&emotion=$emotion'),
    headers: headers,
  );
  
  if (response.statusCode == 200) {
    final data = jsonDecode(response.body);
    return data['audio_id']; // Retourne l'ID de l'audio généré
  } else {
    throw Exception('Échec de la synthèse vocale: ${response.body}');
  }
}
```

### Reconnaissance vocale (STT)

**Endpoint:** `POST /api/stt`

**Paramètres:**
- `audio_file`: Fichier audio à transcrire (multipart/form-data)
- `audio_id`: ID d'un fichier audio existant (alternative à audio_file)
- `language`: Langue de l'audio (défaut: "fr")

```dart
import 'package:http/http.dart' as http;
import 'dart:io';

Future<String> transcribeAudio({
  File? audioFile,
  String? audioId,
  String language = 'fr',
}) async {
  if (audioFile == null && audioId == null) {
    throw ArgumentError('Vous devez fournir soit un fichier audio, soit un ID audio');
  }
  
  if (audioId != null) {
    // Utiliser un ID audio existant
    final response = await http.post(
      Uri.parse('$baseUrl/api/stt?audio_id=$audioId&language=$language'),
      headers: headers,
    );
    
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      return data['text'];
    } else {
      throw Exception('Échec de la transcription: ${response.body}');
    }
  } else {
    // Envoyer un fichier audio
    var request = http.MultipartRequest('POST', Uri.parse('$baseUrl/api/stt?language=$language'));
    
    // Ajouter les en-têtes
    headers.forEach((key, value) {
      request.headers[key] = value;
    });
    
    // Ajouter le fichier audio
    request.files.add(await http.MultipartFile.fromPath(
      'audio_file',
      audioFile!.path,
    ));
    
    // Envoyer la requête
    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);
    
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      return data['text'];
    } else {
      throw Exception('Échec de la transcription: ${response.body}');
    }
  }
}
```

### Récupérer un fichier audio

**Endpoint:** `GET /audio/{filename}`

```dart
Future<File> downloadAudio(String filename, String localPath) async {
  final response = await http.get(
    Uri.parse('$baseUrl/audio/$filename'),
    headers: headers,
  );
  
  if (response.statusCode == 200) {
    final file = File(localPath);
    await file.writeAsBytes(response.bodyBytes);
    return file;
  } else {
    throw Exception('Échec du téléchargement de l\'audio: ${response.body}');
  }
}
```

## Endpoints de session

### Démarrer une session

**Endpoint:** `POST /api/session/start`

**Paramètres:**
- `user_id`: ID de l'utilisateur (obligatoire)
- `scenario_id`: (Optionnel) ID du scénario à utiliser
- `language`: (Optionnel) Langue de la session (défaut: "fr")
- `goal`: (Optionnel) Objectif de la session

```dart
Future<Map<String, dynamic>> startSession({
  required String userId,
  String? scenarioId,
  String language = 'fr',
  String? goal,
}) async {
  final Map<String, dynamic> body = {
    'user_id': userId,
    'language': language,
  };
  
  if (scenarioId != null) body['scenario_id'] = scenarioId;
  if (goal != null) body['goal'] = goal;
  
  final response = await http.post(
    Uri.parse('$baseUrl/api/session/start'),
    headers: headers,
    body: jsonEncode(body),
  );
  
  if (response.statusCode == 200) {
    return jsonDecode(response.body);
  } else {
    throw Exception('Échec du démarrage de la session: ${response.body}');
  }
}
```

### Récupérer le feedback d'une session

**Endpoint:** `GET /api/session/{session_id}/feedback`

**Paramètres:**
- `session_id`: ID de la session (obligatoire)
- `segment_id`: (Optionnel) ID du segment spécifique
- `feedback_type`: (Optionnel) Type de feedback à récupérer

```dart
Future<Map<String, dynamic>> getSessionFeedback({
  required String sessionId,
  String? segmentId,
  String? feedbackType,
}) async {
  String url = '$baseUrl/api/session/$sessionId/feedback';
  
  // Ajouter les paramètres optionnels
  List<String> queryParams = [];
  if (segmentId != null) queryParams.add('segment_id=$segmentId');
  if (feedbackType != null) queryParams.add('feedback_type=$feedbackType');
  
  if (queryParams.isNotEmpty) {
    url += '?' + queryParams.join('&');
  }
  
  final response = await http.get(
    Uri.parse(url),
    headers: headers,
  );
  
  if (response.statusCode == 200) {
    return jsonDecode(response.body);
  } else {
    throw Exception('Échec de la récupération du feedback: ${response.body}');
  }
}
```

### Terminer une session

**Endpoint:** `POST /api/session/{session_id}/end`

```dart
Future<Map<String, dynamic>> endSession(String sessionId) async {
  final response = await http.post(
    Uri.parse('$baseUrl/api/session/$sessionId/end'),
    headers: headers,
  );
  
  if (response.statusCode == 200) {
## Endpoints de scénarios

### Lister les scénarios disponibles

**Endpoint:** `GET /api/scenarios`

**Paramètres:**
- `type`: (Optionnel) Type de scénario (entretien, présentation, etc.)
- `difficulty`: (Optionnel) Niveau de difficulté (easy, medium, hard)
- `language`: (Optionnel) Langue du scénario (défaut: "fr")

```dart
Future<List<Map<String, dynamic>>> listScenarios({
  String? type,
  String? difficulty,
  String language = 'fr',
}) async {
  // Construire l'URL avec les paramètres de requête
  String url = '$baseUrl/api/scenarios';
  List<String> queryParams = [];
  
  if (type != null) queryParams.add('type=$type');
  if (difficulty != null) queryParams.add('difficulty=$difficulty');
  if (language != null) queryParams.add('language=$language');
  
  if (queryParams.isNotEmpty) {
    url += '?' + queryParams.join('&');
  }
  
  final response = await http.get(
    Uri.parse(url),
    headers: headers,
  );
  
  if (response.statusCode == 200) {
    final List<dynamic> data = jsonDecode(response.body);
    return data.cast<Map<String, dynamic>>();
  } else {
    throw Exception('Échec de la récupération des scénarios: ${response.body}');
  }
}
```

**Exemple d'utilisation:**

```dart
try {
  // Récupérer tous les scénarios d'entretien en français
  final scenarios = await listScenarios(
    type: 'entretien',
    language: 'fr',
  );
  
  // Afficher les scénarios disponibles
  for (var scenario in scenarios) {
    print("ID: ${scenario['id']}");
    print("Nom: ${scenario['name']}");
    print("Description: ${scenario['description']}");
    print("Difficulté: ${scenario['difficulty']}");
    print("---");
  }
} catch (e) {
  print("Erreur: $e");
}
```

### Récupérer un scénario spécifique

**Endpoint:** `GET /api/scenarios/{scenario_id}`

```dart
Future<Map<String, dynamic>> getScenario(String scenarioId) async {
  final response = await http.get(
    Uri.parse('$baseUrl/api/scenarios/$scenarioId'),
    headers: headers,
  );
  
  if (response.statusCode == 200) {
    return jsonDecode(response.body);
  } else {
    throw Exception('Échec de la récupération du scénario: ${response.body}');
  }
}
```

**Exemple d'utilisation:**

```dart
try {
  // Récupérer un scénario spécifique
  final scenario = await getScenario('scenario_entretien_embauche');
  
  // Afficher les détails du scénario
  print("Nom: ${scenario['name']}");
  print("Description: ${scenario['description']}");
  print("Type: ${scenario['type']}");
  print("Difficulté: ${scenario['difficulty']}");
  
  // Accéder à la structure du scénario (étapes, personnages, etc.)
  if (scenario.containsKey('structure')) {
    final structure = scenario['structure'];
    
    // Afficher les étapes du scénario
    if (structure.containsKey('steps')) {
      print("\nÉtapes du scénario:");
      for (var step in structure['steps']) {
        print("- ${step['name']}: ${step['description']}");
      }
    }
    
    // Afficher les personnages du scénario
    if (structure.containsKey('characters')) {
      print("\nPersonnages:");
      for (var character in structure['characters']) {
        print("- ${character['name']}: ${character['role']}");
      }
    }
  }
  
  // Afficher le prompt initial
  if (scenario.containsKey('initial_prompt')) {
    print("\nPrompt initial: ${scenario['initial_prompt']}");
  }
} catch (e) {
  print("Erreur: $e");
}
```

### Créer un nouveau scénario

**Endpoint:** `POST /api/scenarios`

```dart
Future<String> createScenario(Map<String, dynamic> scenario) async {
  final response = await http.post(
    Uri.parse('$baseUrl/api/scenarios'),
    headers: headers,
    body: jsonEncode(scenario),
  );
  
  if (response.statusCode == 201) {
    final data = jsonDecode(response.body);
    return data['id']; // Retourne l'ID du scénario créé
  } else {
    throw Exception('Échec de la création du scénario: ${response.body}');
  }
}
```

**Exemple d'utilisation:**

```dart
try {
  // Créer un nouveau scénario
  final scenarioId = await createScenario({
    'name': 'Entretien technique',
    'description': 'Simulation d\'un entretien technique pour un poste de développeur',
    'type': 'entretien',
    'difficulty': 'hard',
    'language': 'fr',
    'tags': ['technique', 'développement', 'informatique'],
    'structure': {
      'characters': [
        {
          'name': 'Recruteur',
          'role': 'interviewer',
          'description': 'Responsable technique expérimenté'
        },
        {
          'name': 'Candidat',
          'role': 'user',
          'description': 'Développeur postulant pour un poste'
        }
      ],
      'steps': [
        {
          'name': 'Introduction',
          'description': 'Présentation et questions générales'
        },
        {
          'name': 'Questions techniques',
          'description': 'Questions sur les compétences techniques'
        },
        {
          'name': 'Mise en situation',
          'description': 'Résolution d\'un problème technique'
        },
        {
          'name': 'Conclusion',
          'description': 'Questions du candidat et fin de l\'entretien'
        }
      ]
    },
    'initial_prompt': 'Bonjour, je suis le responsable technique. Pouvez-vous vous présenter et me parler de votre expérience ?'
  });
  
  print("Scénario créé avec l'ID: $scenarioId");
} catch (e) {
  print("Erreur: $e");
}
```
    return jsonDecode(response.body);
  } else {
    throw Exception('Échec de la terminaison de la session: ${response.body}');
  }
}
```

## Endpoints de monitoring

### Récupérer les statistiques de latence

**Endpoint:** `GET /api/monitoring/latency`

```dart
Future<Map<String, dynamic>> getLatencyStats() async {
  final response = await http.get(
    Uri.parse('$baseUrl/api/monitoring/latency'),
    headers: headers,
  );
  
  if (response.statusCode == 200) {
    return jsonDecode(response.body);
  } else {
    throw Exception('Échec de la récupération des statistiques: ${response.body}');
  }
}
```

## WebSockets

### Connexion WebSocket pour les sessions de coaching

```dart
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:web_socket_channel/status.dart' as status;

class CoachingWebSocket {
  WebSocketChannel? _channel;
  String sessionId;
  Function(Map<String, dynamic>)? onMessage;
  Function(dynamic)? onError;
  Function()? onDone;
  
  CoachingWebSocket(this.sessionId);
  
### Exemple complet d'une session de coaching avec scénario

```dart
import 'package:flutter/material.dart';
import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';
import 'package:audioplayers/audioplayers.dart';

class ScenarioCoachingScreen extends StatefulWidget {
  @override
  _ScenarioCoachingScreenState createState() => _ScenarioCoachingScreenState();
}

class _ScenarioCoachingScreenState extends State<ScenarioCoachingScreen> {
  final String userId = 'user-123';
  String? sessionId;
  CoachingWebSocket? webSocket;
  final AudioPlayer audioPlayer = AudioPlayer();
  final Record audioRecorder = Record();
  bool isRecording = false;
  List<Map<String, dynamic>> messages = [];
  
  // Informations sur le scénario
  Map<String, dynamic>? selectedScenario;
  List<Map<String, dynamic>> availableScenarios = [];
  bool isLoadingScenarios = true;
  
  @override
  void initState() {
    super.initState();
    _loadScenarios();
  }
  
  @override
  void dispose() {
    webSocket?.close();
    audioPlayer.dispose();
    audioRecorder.dispose();
    super.dispose();
  }
  
  Future<void> _loadScenarios() async {
    try {
      setState(() {
        isLoadingScenarios = true;
      });
      
      // Charger la liste des scénarios disponibles
      final scenarios = await listScenarios(
        type: 'entretien',  // Vous pouvez changer le type selon vos besoins
        language: 'fr',
      );
      
      setState(() {
        availableScenarios = scenarios;
        isLoadingScenarios = false;
      });
    } catch (e) {
      setState(() {
        isLoadingScenarios = false;
      });
      _showError('Erreur lors du chargement des scénarios: $e');
    }
  }
  
  Future<void> _selectScenario(Map<String, dynamic> scenario) async {
    try {
      // Charger les détails complets du scénario
      final scenarioDetails = await getScenario(scenario['id']);
      
      setState(() {
        selectedScenario = scenarioDetails;
      });
      
      // Initialiser la session avec le scénario sélectionné
      _initSession(scenarioDetails['id']);
    } catch (e) {
      _showError('Erreur lors du chargement du scénario: $e');
    }
  }
  
  Future<void> _initSession(String scenarioId) async {
    try {
      // Initialiser la session avec le scénario sélectionné
      final sessionData = await startSession(
        userId: userId,
        scenarioId: scenarioId,
        language: 'fr',
      );
      
      setState(() {
        sessionId = sessionData['session_id'];
        
        // Ajouter le message initial
        if (sessionData.containsKey('initial_message')) {
          messages.add({
            'role': 'coach',
            'text': sessionData['initial_message']['text'],
            'audio_url': sessionData['initial_message']['audio_url'],
          });
        }
      });
      
      // Initialiser la connexion WebSocket
      _initWebSocket();
    } catch (e) {
      _showError('Erreur lors de l\'initialisation de la session: $e');
    }
  }
  
  void _initWebSocket() {
    if (sessionId == null) return;
    
    webSocket = CoachingWebSocket(sessionId!);
    
    webSocket!.onMessage = (data) {
      setState(() {
        if (data.containsKey('type')) {
          switch (data['type']) {
            case 'transcription':
              // Ajouter la transcription comme message utilisateur
              messages.add({
                'role': 'user',
                'text': data['text'],
              });
              break;
            case 'coach_response':
              // Ajouter la réponse du coach
              messages.add({
                'role': 'coach',
                'text': data['text'],
                'audio_url': data['audio_url'],
              });
              
              // Jouer l'audio automatiquement
              if (data.containsKey('audio_url')) {
                _playAudio(data['audio_url']);
              }
              break;
          }
        }
      });
    };
    
    webSocket!.onError = (error) {
      _showError('Erreur WebSocket: $error');
    };
    
    webSocket!.connect();
  }
  
  Future<void> _startRecording() async {
    try {
      if (await audioRecorder.hasPermission()) {
        final tempDir = await getTemporaryDirectory();
        final filePath = '${tempDir.path}/audio_${DateTime.now().millisecondsSinceEpoch}.wav';
        
        await audioRecorder.start(path: filePath);
        setState(() {
          isRecording = true;
        });
      }
    } catch (e) {
      _showError('Erreur lors de l\'enregistrement: $e');
    }
  }
  
  Future<void> _stopRecording() async {
    try {
      final filePath = await audioRecorder.stop();
      setState(() {
        isRecording = false;
      });
      
      if (filePath != null && webSocket != null) {
        final file = File(filePath);
        final bytes = await file.readAsBytes();
        final base64Audio = base64Encode(bytes);
        
        webSocket!.send({
          'type': 'audio',
          'data': base64Audio,
          'format': 'wav',
        });
      }
    } catch (e) {
      _showError('Erreur lors de l\'arrêt de l\'enregistrement: $e');
    }
  }
  
  Future<void> _playAudio(String audioUrl) async {
    try {
      await audioPlayer.play(UrlSource('$baseUrl$audioUrl'));
    } catch (e) {
      _showError('Erreur lors de la lecture audio: $e');
    }
  }
  
  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }
  
  @override
  Widget build(BuildContext context) {
    // Si aucun scénario n'est sélectionné, afficher la liste des scénarios
    if (selectedScenario == null) {
      return Scaffold(
        appBar: AppBar(
          title: Text('Choisir un scénario'),
        ),
        body: isLoadingScenarios
          ? Center(child: CircularProgressIndicator())
          : ListView.builder(
              itemCount: availableScenarios.length,
              itemBuilder: (context, index) {
                final scenario = availableScenarios[index];
                return ListTile(
                  title: Text(scenario['name']),
                  subtitle: Text(scenario['description']),
                  trailing: Text(scenario['difficulty'] ?? 'medium'),
                  onTap: () => _selectScenario(scenario),
                );
              },
            ),
      );
    }
    
    // Si un scénario est sélectionné, afficher l'interface de coaching
    return Scaffold(
      appBar: AppBar(
        title: Text(selectedScenario!['name']),
        actions: [
          IconButton(
            icon: Icon(Icons.info_outline),
            onPressed: () {
              // Afficher les informations du scénario
              showDialog(
                context: context,
                builder: (context) => AlertDialog(
                  title: Text(selectedScenario!['name']),
                  content: SingleChildScrollView(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(selectedScenario!['description']),
                        SizedBox(height: 16),
                        Text('Type: ${selectedScenario!['type']}'),
                        Text('Difficulté: ${selectedScenario!['difficulty']}'),
                      ],
                    ),
                  ),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(context),
                      child: Text('Fermer'),
                    ),
                  ],
                ),
              );
            },
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              itemCount: messages.length,
              itemBuilder: (context, index) {
                final message = messages[index];
                final isCoach = message['role'] == 'coach';
                
                return ListTile(
                  leading: isCoach ? Icon(Icons.person) : Icon(Icons.account_circle),
                  title: Text(message['text']),
                  trailing: isCoach && message.containsKey('audio_url')
                    ? IconButton(
                        icon: Icon(Icons.play_arrow),
                        onPressed: () => _playAudio(message['audio_url']),
                      )
                    : null,
                );
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: ElevatedButton(
              onPressed: isRecording ? _stopRecording : _startRecording,
              child: Text(isRecording ? 'Arrêter l\'enregistrement' : 'Commencer à parler'),
              style: ElevatedButton.styleFrom(
                backgroundColor: isRecording ? Colors.red : Colors.blue,
                minimumSize: Size(double.infinity, 50),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
```
  void connect() {
    final wsUrl = 'ws://51.159.110.4:8083/ws/$sessionId';
    _channel = WebSocketChannel.connect(Uri.parse(wsUrl));
    
    _channel!.stream.listen(
      (message) {
        final data = jsonDecode(message);
        if (onMessage != null) onMessage!(data);
      },
      onError: onError,
      onDone: onDone,
    );
  }
  
  void send(Map<String, dynamic> data) {
    if (_channel != null) {
      _channel!.sink.add(jsonEncode(data));
    }
  }
  
  void close() {
    _channel?.sink.close(status.goingAway);
  }
}
```

**Exemple d'utilisation:**

```dart
// Initialiser la connexion WebSocket
final ws = CoachingWebSocket('votre-session-id');

// Définir les callbacks
ws.onMessage = (data) {
  print('Message reçu: $data');
  
  // Traiter les différents types de messages
  if (data.containsKey('type')) {
    switch (data['type']) {
      case 'transcription':
        print('Transcription: ${data['text']}');
        break;
      case 'feedback':
        print('Feedback: ${data['feedback']}');
        break;
      case 'coach_response':
        print('Réponse du coach: ${data['text']}');
        // Jouer l'audio si disponible
        if (data.containsKey('audio_url')) {
          playAudio(data['audio_url']);
        }
        break;
    }
  }
};

ws.onError = (error) {
  print('Erreur WebSocket: $error');
};

ws.onDone = () {
  print('Connexion WebSocket fermée');
};

// Établir la connexion
ws.connect();

// Envoyer un message audio
void sendAudioMessage(File audioFile) async {
  // Convertir le fichier audio en base64
  final bytes = await audioFile.readAsBytes();
  final base64Audio = base64Encode(bytes);
  
  ws.send({
    'type': 'audio',
    'data': base64Audio,
    'format': 'wav',
  });
}

// Fermer la connexion quand vous avez terminé
void closeConnection() {
  ws.close();
}
```

## Gestion des erreurs

```dart
class ApiException implements Exception {
  final int statusCode;
  final String message;
  
  ApiException(this.statusCode, this.message);
  
  @override
  String toString() {
    return 'ApiException: [$statusCode] $message';
  }
}

Future<T> handleApiResponse<T>(Future<http.Response> responseFuture, T Function(Map<String, dynamic>) parser) async {
  try {
    final response = await responseFuture;
    
    if (response.statusCode >= 200 && response.statusCode < 300) {
      final data = jsonDecode(response.body);
      return parser(data);
    } else {
      String message = 'Erreur inconnue';
      
      try {
        final errorData = jsonDecode(response.body);
        message = errorData['detail'] ?? 'Erreur inconnue';
      } catch (_) {
        message = response.body;
      }
      
      throw ApiException(response.statusCode, message);
    }
  } catch (e) {
    if (e is ApiException) {
      rethrow;
    }
    throw ApiException(0, e.toString());
  }
}
```

## Exemples complets

### Exemple complet d'une session de coaching

```dart
import 'package:flutter/material.dart';
import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';
import 'package:audioplayers/audioplayers.dart';

class CoachingSessionScreen extends StatefulWidget {
  @override
  _CoachingSessionScreenState createState() => _CoachingSessionScreenState();
}

class _CoachingSessionScreenState extends State<CoachingSessionScreen> {
  final String userId = 'user-123';
  String? sessionId;
  CoachingWebSocket? webSocket;
  final AudioPlayer audioPlayer = AudioPlayer();
  final Record audioRecorder = Record();
  bool isRecording = false;
  List<Map<String, dynamic>> messages = [];
  
  @override
  void initState() {
    super.initState();
    _initSession();
  }
  
  @override
  void dispose() {
    webSocket?.close();
    audioPlayer.dispose();
    audioRecorder.dispose();
    super.dispose();
  }
  
  Future<void> _initSession() async {
    try {
      // Initialiser la session
      final sessionData = await startSession(userId: userId);
      setState(() {
        sessionId = sessionData['session_id'];
        
        // Ajouter le message initial
        if (sessionData.containsKey('initial_message')) {
          messages.add({
            'role': 'coach',
            'text': sessionData['initial_message']['text'],
            'audio_url': sessionData['initial_message']['audio_url'],
          });
        }
      });
      
      // Initialiser la connexion WebSocket
      _initWebSocket();
    } catch (e) {
      _showError('Erreur lors de l\'initialisation de la session: $e');
    }
  }
  
  void _initWebSocket() {
    if (sessionId == null) return;
    
    webSocket = CoachingWebSocket(sessionId!);
    
    webSocket!.onMessage = (data) {
      setState(() {
        if (data.containsKey('type')) {
          switch (data['type']) {
            case 'transcription':
              // Ajouter la transcription comme message utilisateur
              messages.add({
                'role': 'user',
                'text': data['text'],
              });
              break;
            case 'coach_response':
              // Ajouter la réponse du coach
              messages.add({
                'role': 'coach',
                'text': data['text'],
                'audio_url': data['audio_url'],
              });
              
              // Jouer l'audio automatiquement
              if (data.containsKey('audio_url')) {
                _playAudio(data['audio_url']);
              }
              break;
          }
        }
      });
    };
    
    webSocket!.onError = (error) {
      _showError('Erreur WebSocket: $error');
    };
    
    webSocket!.connect();
  }
  
  Future<void> _startRecording() async {
    try {
      if (await audioRecorder.hasPermission()) {
        final tempDir = await getTemporaryDirectory();
        final filePath = '${tempDir.path}/audio_${DateTime.now().millisecondsSinceEpoch}.wav';
        
        await audioRecorder.start(path: filePath);
        setState(() {
          isRecording = true;
        });
      }
    } catch (e) {
      _showError('Erreur lors de l\'enregistrement: $e');
    }
  }
  
  Future<void> _stopRecording() async {
    try {
      final filePath = await audioRecorder.stop();
      setState(() {
        isRecording = false;
      });
      
      if (filePath != null && webSocket != null) {
        final file = File(filePath);
        final bytes = await file.readAsBytes();
        final base64Audio = base64Encode(bytes);
        
        webSocket!.send({
          'type': 'audio',
          'data': base64Audio,
          'format': 'wav',
        });
      }
    } catch (e) {
      _showError('Erreur lors de l\'arrêt de l\'enregistrement: $e');
    }
  }
  
  Future<void> _playAudio(String audioUrl) async {
    try {
      await audioPlayer.play(UrlSource('$baseUrl$audioUrl'));
    } catch (e) {
      _showError('Erreur lors de la lecture audio: $e');
    }
  }
  
  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Session de coaching'),
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              itemCount: messages.length,
              itemBuilder: (context, index) {
                final message = messages[index];
                final isCoach = message['role'] == 'coach';
                
                return ListTile(
                  leading: isCoach ? Icon(Icons.person) : Icon(Icons.account_circle),
                  title: Text(message['text']),
                  trailing: isCoach && message.containsKey('audio_url')
                    ? IconButton(
                        icon: Icon(Icons.play_arrow),
                        onPressed: () => _playAudio(message['audio_url']),
                      )
                    : null,
                );
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: ElevatedButton(
              onPressed: isRecording ? _stopRecording : _startRecording,
              child: Text(isRecording ? 'Arrêter l\'enregistrement' : 'Commencer à parler'),
              style: ElevatedButton.styleFrom(
                backgroundColor: isRecording ? Colors.red : Colors.blue,
                minimumSize: Size(double.infinity, 50),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
```

### Exemple d'utilisation des exercices de coaching

```dart
class ExerciseScreen extends StatefulWidget {
  @override
  _ExerciseScreenState createState() => _ExerciseScreenState();
}

class _ExerciseScreenState extends State<ExerciseScreen> {
  Map<String, dynamic>? exercise;
  bool isLoading = true;
  
  @override
  void initState() {
    super.initState();
    _loadExercise();
  }
  
  Future<void> _loadExercise() async {
    setState(() {
      isLoading = true;
    });
    
    try {
      final result = await generateExercise(
        exerciseType: 'diction',
        difficulty: 'medium',
      );
      
      setState(() {
        exercise = result;
        isLoading = false;
      });
    } catch (e) {
      setState(() {
        isLoading = false;
      });
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Erreur: $e')),
      );
    }
  }
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Exercice de coaching'),
        actions: [
          IconButton(
            icon: Icon(Icons.refresh),
            onPressed: _loadExercise,
          ),
        ],
      ),
      body: isLoading
        ? Center(child: CircularProgressIndicator())
        : exercise == null
          ? Center(child: Text('Aucun exercice disponible'))
          : SingleChildScrollView(
              padding: EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    exercise!['title'],
                    style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
                  ),
                  SizedBox(height: 16),
                  Text(
                    exercise!['description'],
                    style: TextStyle(fontSize: 16, fontStyle: FontStyle.italic),
                  ),
                  SizedBox(height: 24),
                  Text(
                    'Instructions:',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                  SizedBox(height: 8),
                  Text(
                    exercise!['instructions'],
                    style: TextStyle(fontSize: 16),
                  ),
                  SizedBox(height: 24),
                  Text(
                    'Contenu:',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                  SizedBox(height: 8),
                  Container(
                    padding: EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.grey[200],
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      exercise!['content'],
                      style: TextStyle(fontSize: 18),
                    ),
                  ),
                  SizedBox(height: 24),
                  ElevatedButton(
                    onPressed: () {
                      // Implémenter la fonctionnalité d'enregistrement ici
                    },
                    child: Text('Commencer l\'exercice'),
                    style: ElevatedButton.styleFrom(
                      minimumSize: Size(double.infinity, 50),
                    ),
                  ),
                ],
              ),
            ),
    );
  }
}
```

## Notes importantes

1. **Gestion des erreurs**: Toujours encapsuler les appels API dans des blocs try-catch pour gérer les erreurs correctement.

2. **Authentification**: L'authentification actuelle est simplifiée pour le développement. Dans une version de production, utilisez un système d'authentification plus robuste.

3. **WebSockets**: Les connexions WebSocket sont essentielles pour les fonctionnalités en temps réel comme les sessions de coaching. Assurez-vous de gérer correctement les reconnexions en cas de perte de connexion.

4. **Permissions**: Pour les fonctionnalités audio (enregistrement, lecture), assurez-vous de demander les permissions nécessaires sur les appareils mobiles.

5. **Optimisation**: Pour une application de production, considérez l'utilisation d'un gestionnaire d'état comme Provider, Riverpod ou Bloc pour une meilleure organisation du code.

6. **Tests**: Testez tous les endpoints avec différents scénarios pour assurer la robustesse de votre application.