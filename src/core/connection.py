import asyncio
import json
import logging
from typing import TYPE_CHECKING, Optional

import websockets

from src.utils.config import config

if TYPE_CHECKING:
    from src.core.dispatch import CommandDispatcher
    from updater import UpdateManager

logger = logging.getLogger(__name__)


class AgentConnection:
    """
    WebSocket connection to the FabCore central API.
    
    Handles:
    - Connection establishment and reconnection with backoff
    - Message routing (commands, pings, update notifications)
    - Heartbeat/ping-pong
    """
    
    def __init__(
        self,
        server_url: str,
        identity: dict,
        dispatcher: "CommandDispatcher",
        update_manager: Optional["UpdateManager"] = None
    ):
        self.server_url = server_url
        self.identity = identity
        self.dispatcher = dispatcher
        self.update_manager = update_manager
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self.websocket is not None

    async def run_forever(self):
        """Connect and reconnect forever with exponential backoff."""
        attempt = 0
        
        while True:
            try:
                attempt += 1
                await self.connect()
                attempt = 0  # Reset on successful connection
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"Connection closed: {e}")
                self._connected = False
            except Exception as e:
                logger.error(f"Connection error: {e}")
                self._connected = False
            
            # Always retry with exponential backoff, cap at 5 minutes
            delay = min(config.reconnect_delay_sec * (2 ** min(attempt - 1, 6)), 300)
            logger.info(f"Reconnecting in {delay}s... (attempt {attempt})")
            await asyncio.sleep(delay)

    async def connect(self):
        """Establish WebSocket connection and handle messages."""
        logger.info(f"Connecting to {self.server_url}...")
        
        async with websockets.connect(
            self.server_url,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=5
        ) as websocket:
            self.websocket = websocket
            self._connected = True
            logger.info("Connected to central API")

            # Register with server
            await self._send_registration()

            # Listen for messages
            async for message in websocket:
                try:
                    response = await self.handle_message(message)
                    if response:
                        # Guard against serialization and send failures
                        try:
                            payload = json.dumps(response)
                        except (TypeError, ValueError) as e:
                            logger.error(f"Failed to serialize response: {e}")
                            payload = json.dumps({
                                "command_id": response.get("command_id"),
                                "success": False,
                                "error": f"Response serialization failed: {e}"
                            })
                        
                        # Guard against oversized payloads killing the socket
                        if len(payload) > 10 * 1024 * 1024:  # 10MB limit
                            logger.warning(f"Response too large ({len(payload)} bytes), truncating")
                            payload = json.dumps({
                                "command_id": response.get("command_id"),
                                "success": False,
                                "error": f"Response too large ({len(payload)} bytes). Consider reading smaller chunks."
                            })
                        
                        await websocket.send(payload)
                except websockets.exceptions.ConnectionClosed:
                    raise  # Let the outer handler deal with reconnection
                except Exception as e:
                    logger.exception(f"Error processing message (connection preserved): {e}")

    async def _send_registration(self):
        """Send registration message to server."""
        registration = {
            "type": "register",
            **self.identity
        }
        await self.websocket.send(json.dumps(registration))
        logger.info("Registration sent")

    async def handle_message(self, message: str) -> dict | None:
        """
        Parse and dispatch incoming message.
        
        Message types:
        - registered: Server acknowledged our registration
        - ping: Heartbeat, respond with pong
        - update_available: New version available (optional update)
        - update_required: New version required (forced update)
        - command: Module/action to dispatch
        
        Returns:
            Response dict to send back, or None if no response needed
        """
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            # Registration acknowledgment
            if msg_type == "registered":
                logger.info(f"Registered with server: {data.get('message', 'OK')}")
                return None
            
            # Heartbeat
            elif msg_type == "ping":
                return {"type": "pong"}
            
            # Update notifications
            elif msg_type == "update_available":
                return await self._handle_update_notification(data, force=False)
            
            elif msg_type == "update_required":
                return await self._handle_update_notification(data, force=True)
            
            # Rollback command from server
            elif msg_type == "rollback":
                logger.warning(f"Rollback requested: {data.get('reason', 'No reason given')}")
                # TODO: Implement server-triggered rollback
                return {"type": "rollback_ack", "status": "not_implemented"}
            
            # Command dispatch (module/action pattern)
            elif "module" in data and "action" in data:
                logger.info(f"Received command: {data.get('module')}.{data.get('action')}")
                return await self.dispatcher.dispatch(data)
            
            # Unknown message
            else:
                logger.warning(f"Unknown message type: {msg_type}")
                return None
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received: {e}")
            return {"success": False, "error": f"Invalid JSON: {e}"}
        except Exception as e:
            logger.exception(f"Error handling message: {e}")
            return {"success": False, "error": str(e)}

    async def _handle_update_notification(self, data: dict, force: bool) -> dict | None:
        """
        Handle update_available or update_required message.
        
        Args:
            data: Message payload
            force: Whether this is a forced update
            
        Returns:
            Acknowledgment response
        """
        if not self.update_manager:
            logger.warning("Update notification received but no UpdateManager configured")
            return {"type": "update_ack", "version": data.get("version"), "status": "no_update_manager"}
        
        # Ensure force flag is set correctly
        data["force"] = force or data.get("force", False)
        
        version = data.get("version", "unknown")
        logger.info(f"Update notification: version={version}, force={data['force']}")
        
        try:
            response = await self.update_manager.handle_update_notification(data)
            return response
        except Exception as e:
            logger.error(f"Failed to handle update notification: {e}")
            return {"type": "update_ack", "version": version, "status": "error", "error": str(e)}

    async def send(self, message: dict):
        """Send a message to the server (for external use)."""
        if self.websocket and self._connected:
            await self.websocket.send(json.dumps(message))
        else:
            logger.warning("Cannot send message: not connected")
