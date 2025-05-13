import asyncio
import websockets
import json
import sys

async def test_websocket(session_id):
    uri = f"ws://localhost:8083/ws/simple/{session_id}"
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
        print("Usage: python test_websocket_simple.py <session_id>")
        sys.exit(1)
    
    session_id = sys.argv[1]
    asyncio.run(test_websocket(session_id))