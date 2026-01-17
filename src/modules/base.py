from abc import ABC

class BaseModule(ABC):
    name: str

    def _success(self, **data):
        return {"success": True, **data}

    def _error(self, msg: str):
        return {"success": False, "error": msg}