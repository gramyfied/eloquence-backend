import asyncio
import websockets
import json
import sys

async def test_websocket(session_id, use_simple=False, use_debug=False):
    if use_simple:
        uri = f"ws://localhost:8083/ws/simple/{session_id}"
    elif use_debug:
        uri = f"ws://localhost:8083/ws/debug/{session_id}"
    else:
        uri = f"ws://localhost:8083/ws/{session_id}"
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to WebSocket server!")
            
            # Send a test message
            message = {
                "type": "text",
                "content": "Hello, this is a test message"
            }
            await websocket.send(json.dumps(message))
            print(f"Sent message: {message}")
            
            # Wait for a response
            response = await websocket.recv()
            print(f"Received response: {response}")
            
            # Keep the connection open for a few seconds
            await asyncio.sleep(5)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_websocket.py <session_id> [--simple] [--debug]")
        sys.exit(1)
    
    session_id = sys.argv[1]
    use_simple = "--simple" in sys.argv
    use_debug = "--debug" in sys.argv
    
    asyncio.run(test_websocket(session_id, use_simple, use_debug))