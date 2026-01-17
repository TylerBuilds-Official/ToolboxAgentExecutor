import asyncio
import websockets
import json
from typing import TYPE_CHECKING

from src.utils.config import config

if TYPE_CHECKING:
    from src.core.dispatch import CommandDispatcher


class AgentConnection:
    def __init__(self, server_url: str, identity: dict, dispatcher: "CommandDispatcher"):
        self.server_url = server_url
        self.identity = identity
        self.dispatcher = dispatcher
        self.websocket = None

    async def run_forever(self):
        """Connect and reconnect forever with exponential backoff."""
        attempt = 0
        while True:
            try:
                attempt += 1
                await self.connect()
                attempt = 0  # Reset on successful connection
            except Exception as e:
                print(f"Connection lost..."
                      f"\nError: {e}")
                
                if attempt < config.max_reconnect_attempts:
                    delay = config.reconnect_delay_sec
                    print(f"Reconnecting in {delay} seconds... (attempt {attempt}/{config.max_reconnect_attempts})")
                    await asyncio.sleep(delay)
                else:
                    raise ConnectionError(
                        f"Max reconnect attempts ({config.max_reconnect_attempts}) reached. "
                        f"Please restart the agent."
                    )

    async def connect(self):
        """Establish WebSocket connection and handle messages."""
        async with websockets.connect(self.server_url) as websocket:
            self.websocket = websocket
            print("Connected to central API")

            # Register with server
            await websocket.send(json.dumps({
                "type": "register",
                **self.identity
            }))
            print("Registration sent")

            # Listen for messages
            async for message in websocket:
                response = await self.handle_message(message)
                if response:  # Only send if we have a response
                    await websocket.send(json.dumps(response))

    async def handle_message(self, message: str) -> dict | None:
        """Parse and dispatch incoming message."""
        try:
            data = json.loads(message)
            
            # Handle different message types
            msg_type = data.get("type")
            
            if msg_type == "registered":
                # Acknowledgment from server - no response needed
                print(f"Registered with server: {data.get('message')}")
                return None
            
            elif msg_type == "ping":
                # Heartbeat - respond with pong
                return {"type": "pong"}
            
            # Otherwise, treat as a command to dispatch
            if "module" in data and "action" in data:
                print(f"Received command: {data.get('module')}.{data.get('action')}")
                return await self.dispatcher.dispatch(data)
            
            # Unknown message format
            print(f"Unknown message format: {data}")
            return None
            
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON: {e}"}
        except Exception as e:
            return {"success": False, "error": f"{e}"}
