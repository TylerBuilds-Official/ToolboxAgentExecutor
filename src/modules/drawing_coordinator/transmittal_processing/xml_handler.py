# src/core/xml_handler.py
from pathlib import Path

class XMLHandler:
    def __init__(self, logger=None):
        self.logger = logger

    def process_xml_file(self, xml_file: Path):
        try:
            text = xml_file.read_text(encoding="utf-8")

            # Perform replacements
            text = text.replace(
                "<CNCDirectory>\\CNC</CNCDirectory>",
                "<CNCDirectory>\\CNC Data\\NC-DXF Combined</CNCDirectory>"
            )
            text = text.replace(
                "<DrawingDirectory>\\Drawings</DrawingDirectory>",
                "<DrawingDirectory>\\Drawings\\Fabrication</DrawingDirectory>"
            )

            xml_file.write_text(text, encoding="utf-8")

            if self.logger:
                self.logger.append_log_action(f"Patched XML: {xml_file.name}", "Success")

        except Exception as e:
            if self.logger:
                self.logger.append_log_action(f"Error patching XML {xml_file}: {e}", "Error")
