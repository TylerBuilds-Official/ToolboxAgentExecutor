import asyncio
import logging
import sys

from src.core.connection import AgentConnection
from src.core.dispatch import CommandDispatcher
from src.core.registration import AgentRegistration
from src.utils.config import config
from updater import UpdateManager, UpdateInfo
from version import __version__

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Global references (for potential tray icon integration later)
update_manager: UpdateManager = None
connection: AgentConnection = None


def on_update_ready(update: UpdateInfo):
    """
    Called when an optional update has been downloaded and is ready to apply.
    
    For now, just log it. Later, this will trigger a system tray notification.
    """
    logger.info(f"Update {update.version} is ready to install")
    logger.info(f"Changelog: {update.changelog}")
    # TODO: Show tray notification
    # TODO: Could auto-apply during idle or prompt user


def on_force_update(update: UpdateInfo):
    """
    Called when a forced update is about to be applied.
    
    This is a notification only - the update will proceed regardless.
    """
    logger.warning(f"Forced update to {update.version} - restarting soon...")
    # TODO: Show tray notification


async def check_for_updates_on_startup():
    """Check for updates when the agent starts."""
    global update_manager
    
    if not update_manager:
        return
    
    logger.info("Checking for updates on startup...")
    
    try:
        update = await update_manager.check_for_update()
        if update:
            logger.info(f"Update available: {update.version}")
            if update.force:
                logger.warning("This is a forced update, applying now...")
                await update_manager.handle_update_notification({
                    "version": update.version,
                    "force": True,
                    "changelog": update.changelog,
                    "download_url": update.download_url,
                    "min_version": update.min_version
                })
            else:
                on_update_ready(update)
        else:
            logger.info("No updates available")
    except Exception as e:
        logger.error(f"Startup update check failed: {e}")


async def main():
    global update_manager, connection
    
    # Initialize dispatcher with available modules
    dispatcher = CommandDispatcher()
    
    # Get agent identity (hostname, username, version, capabilities)
    identity = AgentRegistration.get_agent_identity(
        capabilities=dispatcher.get_capabilities()
    )
    
    # Derive HTTP base URL from WebSocket URL for update downloads
    # ws://host:port/path -> http://host:port
    # wss://host:port/path -> https://host:port
    ws_url = config.central_api_url
    if ws_url.startswith("wss://"):
        http_base = ws_url.replace("wss://", "https://").split("/agent")[0]
    else:
        http_base = ws_url.replace("ws://", "http://").split("/agent")[0]
    
    # Initialize update manager
    update_manager = UpdateManager(
        current_version=__version__,
        server_base_url=http_base,
        on_update_ready=on_update_ready,
        on_force_update=on_force_update
    )
    
    # Initialize connection with update manager
    connection = AgentConnection(
        server_url=config.central_api_url,
        identity=identity,
        dispatcher=dispatcher,
        update_manager=update_manager
    )
    
    # Print startup info
    print("=" * 50)
    print(f"  FabCore Agent v{identity['version']}")
    print("=" * 50)
    print(f"  Hostname:     {identity['hostname']}")
    print(f"  User:         {identity['username']}")
    print(f"  Capabilities: {', '.join(identity['capabilities'])}")
    print(f"  Server:       {config.central_api_url}")
    print("=" * 50)
    
    # Check for updates on startup (non-blocking)
    asyncio.create_task(check_for_updates_on_startup())
    
    # Connect and run forever
    logger.info("Starting connection to central API...")
    await connection.run_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Agent stopped by user")
    except ConnectionError as e:
        logger.error(f"Connection failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(1)
