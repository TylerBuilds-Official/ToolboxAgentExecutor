import socket
import getpass
from version import __version__


class AgentRegistration:

    @staticmethod
    def get_agent_identity(capabilities: list[str] = None) -> dict:
        return {
            'hostname': socket.gethostname(),
            'username': getpass.getuser(),
            'version': __version__,
            'capabilities': capabilities or ['filesystem', 'ui']
        }
