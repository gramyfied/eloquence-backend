#!/usr/bin/env python3
"""
Script de test pour vérifier la connexion WebSocket au backend Eloquence.
"""

import asyncio
import websockets
import json
import time
import sys

# Configuration
WS_URL = "ws://51.159.110.4:8082/ws/test-session"
TEST_DURATION = 30  # secondes
RECONNECT_ATTEMPTS = 3

async def test_websocket_connection():
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
            
            async with websockets.connect(WS_URL) as websocket:
                stats["successful_connections"] += 1
                print(f"Connexion établie!")
                
                # Envoyer un ping
                ping_message = json.dumps({"type": "ping", "timestamp": time.time()})
                await websocket.send(ping_message)
                stats["messages_sent"] += 1
                print(f"Message envoyé: {ping_message}")
                
                # Attendre la réponse
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    stats["messages_received"] += 1
                    print(f"Réponse reçue: {response}")
                except asyncio.TimeoutError:
                    print("Timeout en attente de réponse")
                
                # Simuler une déconnexion pour tester la reconnexion
                if stats["reconnections"] < RECONNECT_ATTEMPTS:
                    print("Simulation d'une déconnexion...")
                    await websocket.close()
                    stats["reconnections"] += 1
                    print(f"Déconnexion simulée #{stats['reconnections']}")
                    # Attendre avant de tenter une reconnexion
                    await asyncio.sleep(2)
                else:
                    # Rester connecté et envoyer des pings périodiques
                    while time.time() < end_time:
                        try:
                            ping_message = json.dumps({"type": "ping", "timestamp": time.time()})
                            await websocket.send(ping_message)
                            stats["messages_sent"] += 1
                            print(f"Ping envoyé: {ping_message}")
                            
                            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                            stats["messages_received"] += 1
                            print(f"Pong reçu: {response}")
                            
                            await asyncio.sleep(2)
                        except Exception as e:
                            print(f"Erreur pendant la connexion: {e}")
                            break
        
        except Exception as e:
            stats["failed_connections"] += 1
            print(f"Erreur de connexion: {e}")
            print(f"Tentative de reconnexion dans 2 secondes...")
            await asyncio.sleep(2)
    
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
        success = asyncio.run(test_websocket_connection())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nTest interrompu par l'utilisateur")
        sys.exit(130)