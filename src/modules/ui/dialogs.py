"""
UI operations module for native dialogs.
"""
import asyncio
import tkinter as tk
from tkinter import filedialog
from src.modules.base import BaseModule


class UIModule(BaseModule):
    """Handles native UI dialogs."""

    async def pick_folder(self, title: str = "Select Folder") -> dict:
        """
        Show native folder picker dialog.
        Returns selected path or None if cancelled.
        """
        try:
            # Run tkinter in a thread to avoid blocking
            loop = asyncio.get_event_loop()
            path = await loop.run_in_executor(None, self._show_folder_dialog, title)
            
            if path:
                return self._success(path=path)
            else:
                return self._success(path=None, cancelled=True)
                
        except Exception as e:
            return self._error(f"Failed to show folder picker: {e}")

    def _show_folder_dialog(self, title: str) -> str:
        """Show the actual folder dialog (runs in thread)."""
        # Create hidden root window
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)  # Bring dialog to front
        
        # Show folder picker
        folder_path = filedialog.askdirectory(
            title=title,
            mustexist=True
        )
        
        root.destroy()
        return folder_path
