from src.modules.filesystem.operations import FileSystemModule
from src.modules.ui.dialogs import UIModule
from src.modules.drawing_coordinator.operations import DrawingCoordinatorModule


class CommandDispatcher:
    def __init__(self):
        self.modules = {
            "filesystem": FileSystemModule(),
            "ui": UIModule(),
            "drawing_coordinator": DrawingCoordinatorModule(),
        }

    def get_capabilities(self) -> list[str]:
        """Return list of available module names."""
        return list(self.modules.keys())

    async def dispatch(self, cmd: dict) -> dict:
        """Route command to appropriate module."""
        command_id = cmd.get("command_id")
        module_name = cmd.get("module")
        action = cmd.get("action")
        params = cmd.get("params", {})

        base_response = {"command_id": command_id}

        if module_name not in self.modules:
            return {**base_response, "success": False, "error": f"Unknown module: {module_name}"}

        module = self.modules[module_name]

        if not hasattr(module, action):
            return {**base_response, "success": False, "error": f"Unknown action: {action}"}

        try:
            method = getattr(module, action)
            result = await method(**params)
            return {**base_response, **result}
        except Exception as e:
            return {**base_response, "success": False, "error": str(e)}
