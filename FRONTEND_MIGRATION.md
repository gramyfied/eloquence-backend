# Guide de Migration pour le Frontend Eloquence

Ce guide explique les modifications à apporter au frontend Flutter pour qu'il fonctionne correctement avec le backend LiveKit sécurisé.

## Compatibilité avec l'Existant

**Bonne nouvelle** : Le backend a été conçu pour être **compatible avec l'application Flutter existante**. Les anciens endpoints sont toujours disponibles :

- `/api/session/start` pour démarrer une session
- `/api/session/{id}/end` pour terminer une session
- `/ws/simple/{session_id}` pour la communication WebSocket

Cependant, quelques ajustements sont nécessaires pour la sécurité.

## Modifications Requises

### 1. Ajouter l'API Key dans les Requêtes

Toutes les requêtes API doivent maintenant inclure l'en-tête `X-API-Key` :

```dart
// Exemple en Dart/Flutter
final response = await http.post(
  Uri.parse('$apiUrl/api/session/start'),
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': 'eloquence_secure_api_key_change_me_in_production', // Ajouter cette ligne
  },
  body: jsonEncode({
    'user_id': userId,
    'language': 'fr',
    'scenario_id': scenarioId,
    'is_multi_agent': false,
  }),
);
```

### 2. Validation des Entrées

Le backend valide maintenant strictement les entrées. Assurez-vous que :

- `user_id` : 3-50 caractères, alphanumérique ou avec underscores
- `scenario_id` : 3-50 caractères, alphanumérique ou avec underscores/tirets
- `language` : 2-5 caractères

Exemple de validation côté frontend :

```dart
bool isValidUserId(String userId) {
  return userId.length >= 3 && 
         userId.length <= 50 && 
         RegExp(r'^[a-zA-Z0-9_]+$').hasMatch(userId);
}

bool isValidScenarioId(String scenarioId) {
  return scenarioId.length >= 3 && 
         scenarioId.length <= 50 && 
         RegExp(r'^[a-zA-Z0-9_\-]+$').hasMatch(scenarioId);
}
```

### 3. Gestion des Nouvelles Erreurs

Le backend peut maintenant renvoyer de nouveaux codes d'erreur :

- `401` : API key manquante ou invalide
- `403` : Accès non autorisé (IP différente)
- `429` : Trop de requêtes (rate limiting)

Exemple de gestion des erreurs :

```dart
try {
  final response = await http.post(...);
  
  if (response.statusCode == 200) {
    // Traitement normal
  } else if (response.statusCode == 401) {
    // Problème d'authentification
    showDialog(context: context, builder: (_) => AlertDialog(
      title: Text('Erreur d\'authentification'),
      content: Text('Veuillez vérifier votre clé API.'),
    ));
  } else if (response.statusCode == 403) {
    // Accès non autorisé
    showDialog(context: context, builder: (_) => AlertDialog(
      title: Text('Accès non autorisé'),
      content: Text('Vous n\'êtes pas autorisé à effectuer cette action.'),
    ));
  } else if (response.statusCode == 429) {
    // Trop de requêtes
    showDialog(context: context, builder: (_) => AlertDialog(
      title: Text('Trop de requêtes'),
      content: Text('Veuillez réessayer plus tard.'),
    ));
  } else {
    // Autre erreur
    showDialog(context: context, builder: (_) => AlertDialog(
      title: Text('Erreur'),
      content: Text('Une erreur est survenue: ${response.statusCode}'),
    ));
  }
} catch (e) {
  // Erreur de connexion
  showDialog(context: context, builder: (_) => AlertDialog(
    title: Text('Erreur de connexion'),
    content: Text('Impossible de se connecter au serveur.'),
  ));
}
```

### 4. Mode Développement

Pour faciliter le développement, vous pouvez :

1. Ajouter votre URL de développement dans `ALLOWED_ORIGINS` dans le fichier `.env.local` du backend
2. Utiliser l'API key de développement fournie dans `.env.local`

## Migration vers LiveKit (Optionnel)

Si vous souhaitez migrer vers LiveKit pour bénéficier de ses avantages (latence réduite, meilleure coordination), vous pouvez utiliser les nouveaux endpoints :

- `/api/sessions` (POST) pour créer une session
- `/api/sessions/{id}` (DELETE) pour supprimer une session

Ces endpoints renvoient des informations au format LiveKit (token, room_name, etc.) que vous pouvez utiliser avec le SDK LiveKit Flutter.

Exemple d'intégration LiveKit :

```dart
// 1. Créer une session
final response = await http.post(
  Uri.parse('$apiUrl/api/sessions'),
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': apiKey,
  },
  body: jsonEncode({
    'user_id': userId,
    'language': 'fr',
    'scenario_id': scenarioId,
    'is_multi_agent': false,
  }),
);

final sessionData = jsonDecode(response.body);
final roomName = sessionData['room_name'];
final token = sessionData['token'];
final url = sessionData['url'];

// 2. Connecter à LiveKit
final room = Room();
await room.connect(url, token);

// 3. Publier l'audio
final localAudio = await LocalAudioTrack.createTrack();
await room.localParticipant?.publishAudioTrack(localAudio);

// 4. S'abonner aux pistes distantes
room.remoteParticipants.forEach((participant) {
  participant.onTrackSubscribed = (track, publication) {
    if (track is RemoteAudioTrack) {
      // Lire l'audio
      track.enabled = true;
    }
  };
});
```

## Besoin d'Aide ?

Si vous rencontrez des problèmes lors de la migration, consultez :

- `TROUBLESHOOTING.md` pour les problèmes courants
- `SECURITY.md` pour comprendre les mesures de sécurité
- Les logs du backend pour identifier les erreurs spécifiques