#!/usr/bin/env python3
"""
Script de test simple pour vérifier la connexion WebSocket au backend Eloquence.
Utilise uniquement les bibliothèques standard de Python.
"""

import socket
import ssl
import json
import time
import sys
import base64
import hashlib
import random
import struct
from urllib.parse import urlparse

# Configuration
WS_URL = "ws://51.159.110.4:8082/ws/resilient/test-session" # Utilisation de l'endpoint résilient
TEST_DURATION = 30  # secondes
RECONNECT_ATTEMPTS = 3

class SimpleWebSocket:
    """
    Implémentation simple d'un client WebSocket utilisant uniquement les bibliothèques standard.
    """
    def __init__(self, url):
        self.url = url
        self.socket = None
        self.connected = False
        self.handshake_completed = False
        
        # Parser l'URL
        parsed_url = urlparse(url)
        self.host = parsed_url.hostname
        self.port = parsed_url.port or (443 if parsed_url.scheme == 'wss' else 80)
        self.path = parsed_url.path or '/'
        if parsed_url.query:
            self.path += '?' + parsed_url.query
        self.use_ssl = parsed_url.scheme == 'wss'
    
    def connect(self):
        """
        Établit une connexion WebSocket.
        """
        try:
            # Créer un socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # Configurer SSL si nécessaire
            if self.use_ssl:
                context = ssl.create_default_context()
                self.socket = context.wrap_socket(self.socket, server_hostname=self.host)
            
            # Connecter au serveur
            self.socket.connect((self.host, self.port))
            
            # Effectuer la poignée de main WebSocket
            self._handshake()
            
            self.connected = True
            return True
        except Exception as e:
            print(f"Erreur de connexion: {e}")
            self.close()
            return False
    
    def _handshake(self):
        """
        Effectue la poignée de main WebSocket.
        """
        # Générer une clé WebSocket aléatoire
        key = base64.b64encode(bytes(random.getrandbits(8) for _ in range(16))).decode()
        
        # Construire la requête HTTP
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"Origin: http://{self.host}:{self.port}\r\n"
            f"\r\n"
        )
        
        # Envoyer la requête
        self.socket.sendall(request.encode())
        
        # Recevoir la réponse
        response = b""
        while b"\r\n\r\n" not in response:
            response += self.socket.recv(4096)
        
        # Vérifier la réponse
        response_str = response.decode('utf-8', 'ignore')
        if "101 Switching Protocols" not in response_str:
            raise Exception(f"Handshake failed: {response_str}")
        
        self.handshake_completed = True
    
    def send(self, message):
        """
        Envoie un message au serveur.
        """
        if not self.connected:
            raise Exception("Not connected")
        
        # Convertir le message en JSON si c'est un dictionnaire
        if isinstance(message, dict):
            message = json.dumps(message)
        
        # Convertir le message en bytes si c'est une chaîne
        if isinstance(message, str):
            message = message.encode('utf-8')
        
        # Construire le frame WebSocket
        header = bytearray()
        header.append(0x81)  # FIN + text frame
        
        # Masquer les données (obligatoire pour les clients)
        mask_key = bytes(random.getrandbits(8) for _ in range(4))
        masked_data = bytearray()
        for i, b in enumerate(message):
            masked_data.append(b ^ mask_key[i % 4])
        
        # Ajouter la longueur
        length = len(message)
        if length < 126:
            header.append(0x80 | length)  # Masqué + longueur
        elif length < 65536:
            header.append(0x80 | 126)  # Masqué + 126 (longueur sur 2 octets)
            header.extend(struct.pack(">H", length))
        else:
            header.append(0x80 | 127)  # Masqué + 127 (longueur sur 8 octets)
            header.extend(struct.pack(">Q", length))
        
        # Ajouter la clé de masquage
        header.extend(mask_key)
        
        # Envoyer le frame
        self.socket.sendall(header + masked_data)
    
    def receive(self, timeout=5):
        """
        Reçoit un message du serveur.
        """
        if not self.connected:
            raise Exception("Not connected")
        
        # Configurer le timeout
        self.socket.settimeout(timeout)
        
        try:
            # Recevoir l'en-tête (2 octets minimum)
            header = self.socket.recv(2)
            if not header:
                return None
            
            # Analyser l'en-tête
            fin = (header[0] & 0x80) != 0
            opcode = header[0] & 0x0F
            masked = (header[1] & 0x80) != 0
            length = header[1] & 0x7F
            
            # Gérer les différentes longueurs
            if length == 126:
                length_bytes = self.socket.recv(2)
                length = struct.unpack(">H", length_bytes)[0]
            elif length == 127:
                length_bytes = self.socket.recv(8)
                length = struct.unpack(">Q", length_bytes)[0]
            
            # Lire la clé de masquage si nécessaire
            mask_key = self.socket.recv(4) if masked else None
            
            # Lire les données
            data = bytearray()
            remaining = length
            while remaining > 0:
                chunk = self.socket.recv(min(remaining, 4096))
                if not chunk:
                    break
                data.extend(chunk)
                remaining -= len(chunk)
            
            # Démasquer les données si nécessaire
            if masked:
                for i in range(len(data)):
                    data[i] ^= mask_key[i % 4]
            
            # Gérer les différents types de frames
            if opcode == 0x1:  # Text frame
                return data.decode('utf-8')
            elif opcode == 0x2:  # Binary frame
                return data
            elif opcode == 0x8:  # Close frame
                self.connected = False
                print("[SimpleWebSocket] Close frame received")
                return None
            elif opcode == 0x9:  # Ping frame
                # Répondre automatiquement aux pings
                print("[SimpleWebSocket] Ping frame received, sending Pong")
                self._send_pong(data)
                return self.receive(timeout)  # Continuer à recevoir pour un message applicatif
            elif opcode == 0xA:  # Pong frame
                print("[SimpleWebSocket] Pong frame received")
                # Renvoyer une indication qu'un pong a été reçu,
                # plutôt que de simplement rappeler receive() qui pourrait timer out.
                # La boucle principale peut décider d'ignorer cela et d'attendre un autre message si nécessaire.
                return "<PONG_RECEIVED>"
            
            return data
        except socket.timeout:
            return None
        except Exception as e:
            print(f"Erreur lors de la réception: {e}")
            self.connected = False
            return None
    
    def _send_pong(self, data):
        """
        Envoie un frame Pong en réponse à un Ping.
        """
        header = bytearray()
        header.append(0x8A)  # FIN + pong frame
        
        # Ajouter la longueur
        length = len(data)
        if length < 126:
            header.append(length)
        elif length < 65536:
            header.append(126)
            header.extend(struct.pack(">H", length))
        else:
            header.append(127)
            header.extend(struct.pack(">Q", length))
        
        # Envoyer le frame
        self.socket.sendall(header + data)
    
    def close(self):
        """
        Ferme la connexion WebSocket.
        """
        if self.socket:
            try:
                # Envoyer un frame de fermeture
                if self.connected and self.handshake_completed:
                    close_frame = bytearray([0x88, 0x02, 0x03, 0xE8])  # Code 1000 (fermeture normale)
                    self.socket.sendall(close_frame)
            except:
                pass
            
            try:
                self.socket.close()
            except:
                pass
        
        self.socket = None
        self.connected = False
        self.handshake_completed = False

def test_websocket_connection():
    """
    Teste la connexion WebSocket au backend Eloquence.
    """
    print(f"Test de connexion WebSocket à {WS_URL}")
    print(f"Durée du test: {TEST_DURATION} secondes")
    print(f"Tentatives de reconnexion: {RECONNECT_ATTEMPTS}")
    print("-" * 50)
    
    # Statistiques
    stats = {
        "connection_attempts": 0,
        "successful_connections": 0,
        "failed_connections": 0,
        "messages_sent": 0,
        "messages_received": 0,
        "reconnections": 0,
    }
    
    start_time = time.time()
    end_time = start_time + TEST_DURATION
    
    # Boucle principale
    while time.time() < end_time:
        try:
            stats["connection_attempts"] += 1
            print(f"Tentative de connexion #{stats['connection_attempts']}...")
            
            ws = SimpleWebSocket(WS_URL)
            if ws.connect():
                stats["successful_connections"] += 1
                print(f"Connexion établie!")
                
                # Envoyer un ping
                ping_message = json.dumps({"type": "ping", "timestamp": time.time()})
                ws.send(ping_message)
                stats["messages_sent"] += 1
                print(f"Message envoyé: {ping_message}")
                
                # Attendre la réponse
                response = ws.receive(timeout=5.0)
                if response == "<PONG_RECEIVED>":
                    stats["messages_received"] += 1 # Compter le pong comme un message reçu pour le test
                    print(f"Réponse PONG reçue du serveur!")
                    # Après un pong, on pourrait vouloir attendre un autre message applicatif
                    # Pour ce test, on va considérer que le pong est suffisant.
                elif response:
                    stats["messages_received"] += 1
                    print(f"Réponse reçue: {response}")
                else:
                    print("Timeout en attente de réponse (aucun message ni pong reçu)")
                
                # Simuler une déconnexion pour tester la reconnexion
                if stats["reconnections"] < RECONNECT_ATTEMPTS:
                    print("Simulation d'une déconnexion...")
                    ws.close()
                    stats["reconnections"] += 1
                    print(f"Déconnexion simulée #{stats['reconnections']}")
                    # Attendre avant de tenter une reconnexion
                    time.sleep(2)
                else:
                    # Rester connecté et envoyer des pings périodiques
                    ping_interval = 2
                    last_ping_time = time.time()
                    
                    while time.time() < end_time:
                        # Vérifier s'il est temps d'envoyer un ping
                        current_time = time.time()
                        if current_time - last_ping_time >= ping_interval:
                            ping_message = json.dumps({"type": "ping", "timestamp": current_time})
                            try:
                                ws.send(ping_message)
                                stats["messages_sent"] += 1
                                print(f"Ping envoyé: {ping_message}")
                                last_ping_time = current_time
                            except:
                                print("Erreur lors de l'envoi du ping, connexion perdue")
                                break
                        
                        # Vérifier s'il y a des messages à recevoir
                        response = ws.receive(timeout=0.1) # Court timeout pour ne pas bloquer
                        if response == "<PONG_RECEIVED>":
                            stats["messages_received"] += 1
                            print(f"Pong périodique reçu.")
                        elif response:
                            stats["messages_received"] += 1
                            print(f"Message reçu: {response}")
                        
                        # Vérifier si la connexion est toujours active
                        if not ws.connected:
                            print("Connexion perdue")
                            break
                        
                        # Petite pause pour éviter de surcharger le CPU
                        time.sleep(0.1)
                    
                    ws.close()
            else:
                stats["failed_connections"] += 1
                print(f"Échec de la connexion")
                time.sleep(2)
        
        except KeyboardInterrupt:
            print("\nTest interrompu par l'utilisateur")
            break
        except Exception as e:
            stats["failed_connections"] += 1
            print(f"Erreur: {e}")
            time.sleep(2)
    
    # Afficher les statistiques
    test_duration = time.time() - start_time
    print("\n" + "=" * 50)
    print(f"Test terminé après {test_duration:.2f} secondes")
    print(f"Tentatives de connexion: {stats['connection_attempts']}")
    print(f"Connexions réussies: {stats['successful_connections']}")
    print(f"Connexions échouées: {stats['failed_connections']}")
    print(f"Messages envoyés: {stats['messages_sent']}")
    print(f"Messages reçus: {stats['messages_received']}")
    print(f"Reconnexions: {stats['reconnections']}")
    
    # Déterminer le résultat du test
    if stats["successful_connections"] > 0 and stats["messages_received"] > 0:
        print("\nTEST RÉUSSI: Connexion WebSocket fonctionnelle")
        return True
    else:
        print("\nTEST ÉCHOUÉ: Problèmes de connexion WebSocket")
        return False

if __name__ == "__main__":
    try:
        success = test_websocket_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nTest interrompu par l'utilisateur")
        sys.exit(130)