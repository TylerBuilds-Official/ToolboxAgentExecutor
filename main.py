import asyncio
from src.core.connection import AgentConnection
from src.core.dispatch import CommandDispatcher
from src.core.registration import AgentRegistration
from src.utils.config import config

async def main():
    dispatcher = CommandDispatcher()
    identity = AgentRegistration.get_agent_identity(capabilities=dispatcher.get_capabilities())
    
    connection = AgentConnection(
        server_url=config.central_api_url,
        identity=identity,
        dispatcher=dispatcher
    )
    
    print(f"ToolboxAgentExecutor v{identity['version']}")
    print(f"Hostname: {identity['hostname']}")
    print(f"User: {identity['username']}")
    print(f"Capabilities: {', '.join(identity['capabilities'])}")
    print(f"Connecting to {config.central_api_url}...")
    
    await connection.run_forever()

if __name__ == "__main__":
    asyncio.run(main())
