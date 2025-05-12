import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:web_socket_channel/status.dart' as status;

/// Classe améliorée pour gérer les connexions WebSocket avec gestion d'erreurs et reconnexion
class EloquenceWebSocket {
  // Configuration
  final String sessionId;
  final String baseUrl;
  final String endpoint;
  final bool useSecureProtocol;
  final Map<String, String>? headers;
  final Duration connectionTimeout;
  final Duration reconnectDelay;
  final int maxReconnectAttempts;

  // État interne
  WebSocketChannel? _channel;
  bool _isConnected = false;
  bool _isConnecting = false;
  int _reconnectAttempts = 0;
  Timer? _heartbeatTimer;
  Timer? _reconnectTimer;
  DateTime? _lastMessageReceived;
  
  // Callbacks
  final Function(Map<String, dynamic>)? onTextMessage;
  final Function(List<int>)? onBinaryMessage;
  final Function(dynamic)? onError;
  final Function()? onConnected;
  final Function()? onDisconnected;
  final Function(int, int)? onReconnecting;

  /// Constructeur avec paramètres par défaut
  EloquenceWebSocket({
    required this.sessionId,
    this.baseUrl = '51.159.110.4:8083',
    this.endpoint = 'simple', // 'simple', 'debug' ou '' (standard)
    this.useSecureProtocol = false,
    this.headers,
    this.connectionTimeout = const Duration(seconds: 5),
    this.reconnectDelay = const Duration(seconds: 2),
    this.maxReconnectAttempts = 5,
    this.onTextMessage,
    this.onBinaryMessage,
    this.onError,
    this.onConnected,
    this.onDisconnected,
    this.onReconnecting,
  });

  /// État actuel de la connexion
  bool get isConnected => _isConnected;
  bool get isConnecting => _isConnecting;

  /// Établir la connexion WebSocket
  Future<bool> connect() async {
    if (_isConnected || _isConnecting) {
      print('Connexion déjà établie ou en cours');
      return _isConnected;
    }

    _isConnecting = true;
    
    try {
      // Construire l'URL avec le protocole approprié
      final protocol = useSecureProtocol ? 'wss' : 'ws';
      final path = endpoint.isNotEmpty ? '/ws/$endpoint/$sessionId' : '/ws/$sessionId';
      final wsUrl = '$protocol://$baseUrl$path';
      
      print('Tentative de connexion WebSocket à: $wsUrl');
      
      // Créer la connexion
      _channel = WebSocketChannel.connect(Uri.parse(wsUrl));
      
      // Attendre que la connexion soit établie
      final connected = await _waitForConnection();
      if (!connected) {
        _isConnecting = false;
        return false;
      }
      
      // Configurer les listeners
      _setupListeners();
      
      // Démarrer le heartbeat
      _startHeartbeat();
      
      _isConnected = true;
      _isConnecting = false;
      _reconnectAttempts = 0;
      
      if (onConnected != null) onConnected!();
      print('Connexion WebSocket établie avec succès');
      
      return true;
    } catch (e) {
      print('Échec de la connexion WebSocket: $e');
      if (onError != null) onError!(e);
      
      _isConnected = false;
      _isConnecting = false;
      
      return false;
    }
  }

  /// Attendre que la connexion soit établie ou échoue
  Future<bool> _waitForConnection() async {
    final completer = Completer<bool>();
    
    // Timeout pour éviter de bloquer indéfiniment
    Timer(connectionTimeout, () {
      if (!completer.isCompleted) {
        print('Timeout de connexion WebSocket');
        completer.complete(false);
      }
    });
    
    try {
      // Attendre le premier message ou une erreur
      _channel!.stream.first.then((_) {
        if (!completer.isCompleted) {
          completer.complete(true);
        }
      }).catchError((e) {
        if (!completer.isCompleted) {
          print('Erreur lors de l\'établissement de la connexion: $e');
          completer.complete(false);
        }
      });
    } catch (e) {
      if (!completer.isCompleted) {
        print('Exception lors de l\'établissement de la connexion: $e');
        completer.complete(false);
      }
    }
    
    return completer.future;
  }

  /// Configurer les listeners pour le stream WebSocket
  void _setupListeners() {
    _channel!.stream.listen(
      (message) {
        _lastMessageReceived = DateTime.now();
        
        try {
          // Gérer à la fois les messages texte et binaires
          if (message is String) {
            final data = jsonDecode(message);
            
            // Traiter les heartbeats séparément
            if (data is Map && data['type'] == 'heartbeat') {
              print('Heartbeat reçu: ${data['timestamp']}');
              return;
            }
            
            if (onTextMessage != null) onTextMessage!(data);
          } else if (message is List<int>) {
            if (onBinaryMessage != null) onBinaryMessage!(message);
          }
        } catch (e) {
          print('Erreur lors du traitement du message: $e');
          if (onError != null) onError!(e);
        }
      },
      onError: (error) {
        print('Erreur WebSocket: $error');
        _isConnected = false;
        
        if (onError != null) onError!(error);
        _handleDisconnection();
      },
      onDone: () {
        print('Connexion WebSocket fermée');
        _isConnected = false;
        
        if (onDisconnected != null) onDisconnected!();
        _handleDisconnection();
      },
      cancelOnError: false,
    );
  }

  /// Gérer la déconnexion et tenter une reconnexion si nécessaire
  void _handleDisconnection() {
    _stopHeartbeat();
    
    if (_reconnectAttempts < maxReconnectAttempts) {
      _reconnectAttempts++;
      
      if (onReconnecting != null) {
        onReconnecting!(_reconnectAttempts, maxReconnectAttempts);
      }
      
      print('Tentative de reconnexion ($_reconnectAttempts/$maxReconnectAttempts) dans ${reconnectDelay.inSeconds} secondes...');
      
      _reconnectTimer?.cancel();
      _reconnectTimer = Timer(reconnectDelay, () {
        connect();
      });
    }
  }

  /// Démarrer le timer de heartbeat
  void _startHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = Timer.periodic(const Duration(seconds: 30), (timer) {
      if (_isConnected) {
        // Vérifier si nous avons reçu un message récemment
        final now = DateTime.now();
        final lastReceived = _lastMessageReceived;
        
        if (lastReceived != null && now.difference(lastReceived).inSeconds > 60) {
          // Pas de message depuis plus de 60 secondes, la connexion est peut-être morte
          print('Pas de message reçu depuis 60 secondes, fermeture de la connexion');
          close();
          _handleDisconnection();
          return;
        }
        
        // Envoyer un heartbeat
        send({
          'type': 'heartbeat',
          'timestamp': DateTime.now().millisecondsSinceEpoch
        });
      } else {
        _stopHeartbeat();
      }
    });
  }

  /// Arrêter le timer de heartbeat
  void _stopHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
  }

  /// Envoyer un message texte (JSON)
  void send(Map<String, dynamic> data) {
    if (_channel != null && _isConnected) {
      try {
        _channel!.sink.add(jsonEncode(data));
      } catch (e) {
        print('Erreur lors de l\'envoi du message: $e');
        if (onError != null) onError!(e);
        _handleDisconnection();
      }
    } else {
      print('Impossible d\'envoyer le message: non connecté');
    }
  }

  /// Envoyer des données binaires (audio)
  void sendBinary(List<int> data) {
    if (_channel != null && _isConnected) {
      try {
        _channel!.sink.add(data);
      } catch (e) {
        print('Erreur lors de l\'envoi des données binaires: $e');
        if (onError != null) onError!(e);
        _handleDisconnection();
      }
    } else {
      print('Impossible d\'envoyer les données binaires: non connecté');
    }
  }

  /// Fermer la connexion WebSocket
  void close() {
    _stopHeartbeat();
    _reconnectTimer?.cancel();
    
    try {
      _channel?.sink.close(status.normalClosure);
    } catch (e) {
      print('Erreur lors de la fermeture de la connexion: $e');
    }
    
    _isConnected = false;
    _isConnecting = false;
  }
}

/// Exemple d'utilisation dans un widget Flutter
class WebSocketDemoScreen extends StatefulWidget {
  @override
  _WebSocketDemoScreenState createState() => _WebSocketDemoScreenState();
}

class _WebSocketDemoScreenState extends State<WebSocketDemoScreen> {
  late EloquenceWebSocket _webSocket;
  final List<String> _messages = [];
  final TextEditingController _textController = TextEditingController();
  bool _isConnected = false;
  bool _isConnecting = false;
  int _reconnectAttempt = 0;
  int _maxReconnectAttempts = 5;

  @override
  void initState() {
    super.initState();
    _initWebSocket();
  }

  void _initWebSocket() {
    // Créer l'instance WebSocket avec les callbacks
    _webSocket = EloquenceWebSocket(
      sessionId: 'demo-${DateTime.now().millisecondsSinceEpoch}',
      baseUrl: 'localhost:8083', // Changer pour votre serveur
      endpoint: 'simple',
      onTextMessage: _handleTextMessage,
      onBinaryMessage: _handleBinaryMessage,
      onError: _handleError,
      onConnected: _handleConnected,
      onDisconnected: _handleDisconnected,
      onReconnecting: _handleReconnecting,
    );

    // Établir la connexion
    setState(() {
      _isConnecting = true;
    });
    
    _webSocket.connect().then((success) {
      if (!success && mounted) {
        setState(() {
          _isConnecting = false;
        });
      }
    });
  }

  void _handleTextMessage(Map<String, dynamic> data) {
    setState(() {
      _messages.add('Reçu: ${jsonEncode(data)}');
    });
  }

  void _handleBinaryMessage(List<int> data) {
    setState(() {
      _messages.add('Reçu: [Données binaires de ${data.length} octets]');
    });
  }

  void _handleError(dynamic error) {
    setState(() {
      _messages.add('Erreur: $error');
    });
  }

  void _handleConnected() {
    setState(() {
      _isConnected = true;
      _isConnecting = false;
      _messages.add('Connecté au serveur WebSocket');
    });
  }

  void _handleDisconnected() {
    setState(() {
      _isConnected = false;
      _messages.add('Déconnecté du serveur WebSocket');
    });
  }

  void _handleReconnecting(int attempt, int maxAttempts) {
    setState(() {
      _reconnectAttempt = attempt;
      _maxReconnectAttempts = maxAttempts;
      _isConnecting = true;
      _messages.add('Tentative de reconnexion $attempt/$maxAttempts...');
    });
  }

  void _sendMessage() {
    final text = _textController.text.trim();
    if (text.isNotEmpty) {
      _webSocket.send({
        'type': 'text',
        'content': text
      });
      
      setState(() {
        _messages.add('Envoyé: $text');
        _textController.clear();
      });
    }
  }

  @override
  void dispose() {
    _webSocket.close();
    _textController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('WebSocket Demo'),
        actions: [
          Container(
            margin: EdgeInsets.all(8.0),
            width: 16,
            height: 16,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: _isConnected 
                ? Colors.green 
                : (_isConnecting ? Colors.orange : Colors.red),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          if (_isConnecting && !_isConnected)
            LinearProgressIndicator(
              value: _reconnectAttempt > 0 
                ? _reconnectAttempt / _maxReconnectAttempts 
                : null,
            ),
          Expanded(
            child: ListView.builder(
              itemCount: _messages.length,
              itemBuilder: (context, index) {
                return Padding(
                  padding: const EdgeInsets.all(8.0),
                  child: Text(_messages[index]),
                );
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _textController,
                    decoration: InputDecoration(
                      hintText: 'Entrez un message',
                      border: OutlineInputBorder(),
                    ),
                    enabled: _isConnected,
                    onSubmitted: (_) => _sendMessage(),
                  ),
                ),
                SizedBox(width: 8),
                IconButton(
                  icon: Icon(Icons.send),
                  onPressed: _isConnected ? _sendMessage : null,
                ),
              ],
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _isConnected 
          ? _webSocket.close 
          : (_isConnecting ? null : _initWebSocket),
        child: Icon(_isConnected ? Icons.close : Icons.refresh),
        tooltip: _isConnected ? 'Déconnecter' : 'Reconnecter',
      ),
    );
  }
}