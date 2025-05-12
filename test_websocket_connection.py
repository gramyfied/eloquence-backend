import asyncio
import websockets
import json
import logging
import sys

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

async def test_websocket_connection(uri):
    """Test simple de connexion WebSocket au serveur."""
    try:
        logger.info(f"Tentative de connexion à {uri}")
        
        # Tentative de connexion avec timeout
        async with websockets.connect(uri, ping_interval=None, close_timeout=5) as websocket:
            logger.info("✅ Connexion établie!")
            
            # Envoyer un message texte
            message = {
                "type": "text",
                "content": "Test message"
            }
            await websocket.send(json.dumps(message))
            logger.info(f"✅ Message envoyé: {message}")
            
            # Attendre la réponse avec timeout
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                logger.info(f"✅ Réponse reçue: {response}")
                
                # Tenter de parser la réponse JSON
                try:
                    json_response = json.loads(response)
                    logger.info(f"✅ Réponse JSON valide: {json_response}")
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ La réponse n'est pas un JSON valide")
            except asyncio.TimeoutError:
                logger.error("❌ Timeout en attendant la réponse du serveur")
            
            # Maintenir la connexion pendant quelques secondes
            logger.info("Maintien de la connexion pendant 3 secondes...")
            await asyncio.sleep(3)
            logger.info("✅ Test terminé avec succès")
            
    except websockets.exceptions.InvalidStatusCode as e:
        logger.error(f"❌ Erreur de statut HTTP: {e}")
        logger.error(f"   Cela peut indiquer un problème de handshake WebSocket ou que le serveur n'accepte pas la connexion")
    except websockets.exceptions.InvalidHandshake as e:
        logger.error(f"❌ Erreur de handshake: {e}")
        logger.error(f"   Vérifiez que l'endpoint est bien un endpoint WebSocket")
    except websockets.exceptions.ConnectionClosed as e:
        logger.error(f"❌ Connexion fermée prématurément: code={e.code}, raison={e.reason}")
    except asyncio.TimeoutError:
        logger.error("❌ Timeout lors de la tentative de connexion")
        logger.error("   Vérifiez que le serveur est accessible et que le port est ouvert")
    except ConnectionRefusedError:
        logger.error("❌ Connexion refusée")
        logger.error("   Vérifiez que le serveur est en cours d'exécution et que le port est correct")
    except Exception as e:
        logger.error(f"❌ Erreur inattendue: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Utiliser l'URI fournie en argument ou l'URI par défaut
    if len(sys.argv) > 1:
        uri = sys.argv[1]
    else:
        # URI par défaut
        session_id = "test-session-123"
        uri = f"ws://localhost:8083/ws/simple/{session_id}"
        
    logger.info(f"Test de connexion WebSocket à {uri}")
    asyncio.run(test_websocket_connection(uri))