import zipfile
import tempfile
import shutil
from pathlib import Path
from src.modules.drawing_coordinator.logger import HeadlessLogger

class ZipHandler:

    def __init__(self, input_zip_file: str | Path, utils = None):
        self.input_zip_file = input_zip_file
        self.utils = utils
        self.temp_dir = Path(tempfile.mkdtemp(prefix="TransmitPro_"))


    def extract(self) -> Path:
        try:
            with zipfile.ZipFile(self.input_zip_file, "r") as zip_ref:
                zip_ref.extractall(self.temp_dir)
            if self.utils:
                self.utils.set_status_bar("Zip extracted successfully")
                self.utils.append_log_action("Zip extracted successfully", "Success")

            self._extract_nested_zips(self.temp_dir)
            return self.temp_dir.resolve()

        except zipfile.BadZipFile:
            if self.utils:
                self.utils.set_status_bar("Error: Invalid ZIP file")
                self.utils.append_log_action("Error: Invalid ZIP file", "Error")
            raise
        except Exception as e:
            if self.utils:
                self.utils.set_status_bar(f"Error: {e}")
                self.utils.append_log_action(f"Extraction error: {e}", "Error")
            raise


    def cleanup(self):
        try:
            shutil.rmtree(self.temp_dir)
            if self.utils:
                self.utils.set_status_bar("Cleaning up..")
                self.utils.append_log_action(f"Cleaned temp folder: {self.temp_dir}", "Success")
        except Exception as e:
            if self.utils:
                self.utils.set_status_bar(f"Error: {e}")
                self.utils.append_log_action(f"Cleanup error: {e}", "Error")


    def info_list(self) -> list:
        with zipfile.ZipFile(self.input_zip_file, "r") as zip_ref:
            return zip_ref.namelist()

    def copy_path(self, path: str):
        """Pass the full path to the specified location back"""
        og_path = Path(self.input_zip_file)
        copy_path = Path(path) / og_path.name
        return [og_path, copy_path]

    def _extract_nested_zips(self, temp_dir: Path):
        for zip_file in temp_dir.rglob("*.zip"):
            try:
                extract_dir = (temp_dir / zip_file.stem).resolve()
                extract_dir.mkdir(exist_ok=True)
                with zipfile.ZipFile(zip_file, "r") as nested_zip_ref:
                    nested_zip_ref.extractall(extract_dir)

                if self.utils:
                    self.utils.append_log_action(f"Extracted nested zip: {zip_file}", "Success")

                self._extract_nested_zips(extract_dir)
            except Exception as e:
                if self.utils:
                    self.utils.append_log_action(f"Error extracting nested zip: {zip_file}: {e}", "Error")