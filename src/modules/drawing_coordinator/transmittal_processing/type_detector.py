import re
import datetime
from pathlib import Path

from src.modules.drawing_coordinator.transmittal_processing.zip_handler import ZipHandler
from src.modules.drawing_coordinator.logger import HeadlessLogger


class TypeDetector:
    IFA_PATTERNS = [
        "ifa",
        "for_approval",
        "in_for_approval",
        "approval_dwg",
        "review_set",
    ]
    IFA_REGEX = [re.compile(r"\brev[\s_\-]*[A-Z]{1,2}\b", re.IGNORECASE)]


    IFF_PATTERNS = [
        "iff",
        "for_fabrication",
        "fabrication",
        "for_construction",
        "in_for_fabrication",
        "construction_set",
        "fabrication_set",
    ]

    IFF_REGEX = [re.compile(r"rev[\s_\-]*\d+", re.IGNORECASE)]

    TRANS_REGEX = re.compile(r"(?:\btransmittal|\btr|\bt)[\s#]*0*(\d{1,3})(?=\b|[^0-9])", re.IGNORECASE)

    JOB_NUM_REGEX = re.compile(r"(?<!\d)\d{4}(?!\d)")



    def __init__(self, zip_path: Path, utils = None):
        self.zip_path = Path(zip_path)
        self.utils = utils

        if zip_path.is_dir():
            raise ValueError(f"TypeDetector expects a ZIP file, got a directory. {self.zip_path}")

    # ----------------------------------------------------------------
    def detect_type(self) -> str:
        """
        Determines type by checking only the zip file name.
        If no matches are found, falls back to scanning the ZIP's contents.
        """
        detected = "UNKNOWN"
        zip_name = self.zip_path.name.lower()

        # 🔹 Check filename patterns first
        if any(term in zip_name for term in self.IFA_PATTERNS) or any(
            rgx.search(zip_name) for rgx in self.IFA_REGEX
        ):
            detected = "IFA"

        elif any(term in zip_name for term in self.IFF_PATTERNS) or any(
            rgx.search(zip_name) for rgx in self.IFF_REGEX
        ):
            detected = "IFF"

        else:
            # Fallback — search inside ZIP
            detected = self._scan_contents_for_type()

        if self.utils:
            if '-content' in detected:
                self.utils.append_log_action(f"Detected type: {detected} from filename", "Success")

            else:
                self.utils.append_log_action(f"Detected type: {detected} from .zipfile name", "Success")
        if '-content' in detected:
            detected = detected.replace('-content', '')
        return detected

    # ----------------------------------------------------------------
    def detect_job_number(self) -> str:
        detected = "UNKNOWN"
        zip_name = self.zip_path.name.lower()

        zip_name = zip_name.replace(".zip", "").replace("-", " ").replace("_", " ")

        try:
            matches = self.JOB_NUM_REGEX.findall(zip_name)
            # First, try to get a non-year 4-digit number from the zip filename
            for match in matches:
                if match == self._get_current_year():
                    # Skip year-like matches (e.g. 2025)
                    continue
                detected = match
                break

            # If nothing valid was found in the filename, scan the contents
            if detected == "UNKNOWN":
                detected = self._scan_contents_for_job_number()

            return detected

        except Exception as e:
            if self.utils:
                self.utils.append_log_action(f"Error detecting job number: {e}", "Error")
                self.utils.set_status_bar(f"Could not detect job number")
            return detected

    # ----------------------------------------------------------------

    def detect_transmittal_number(self) -> str:
        detected = "UNKNOWN"
        zip_name = self.zip_path.name.lower()

        # Remove .zip and normalize separators a bit
        zip_name = zip_name.replace(".zip", "").replace("-", " ").replace("_", " ")

        try:
            match = self.TRANS_REGEX.search(zip_name)
            if match:
                detected = f"T{int(match.group(1)):03d}"
            else:
                detected = self._scan_contents_for_transmittal_number()

            return detected

        except Exception as e:
            if self.utils:
                self.utils.append_log_action(f"Error detecting transmittal number: {e}", "Error")
            return detected

    # ----------------------------------------------------------------

    def _scan_contents_for_transmittal_number(self) -> str:
        """
        Scans inside the ZIP for transmittal indicators in file or folder names.
        Returns the first detected T### pattern, or 'UNKNOWN' if none found.
        """
        detected = "UNKNOWN"
        try:
            zip_handler = ZipHandler(self.zip_path)
            info_list = zip_handler.info_list()

            for file in info_list:
                lower_name = file.lower().replace("-", " ").replace("_", " ")

                match = self.TRANS_REGEX.search(lower_name)
                if match:
                    detected = f"T{int(match.group(1)):03d}"
                    break

            if self.utils:
                self.utils.append_log_action(
                    f"Detected transmittal number from ZIP contents: {detected}", "Info"
                )

        except Exception as e:
            if self.utils:
                self.utils.append_log_action(f"Error scanning ZIP contents: {e}", "Error")

        return detected
    # ----------------------------------------------------------------

    def _scan_contents_for_type(self) -> str:
        """
        Inspects the contents of the ZIP for patterns in file names.
        Returns 'IFA', 'IFF', or 'UNKNOWN'.
        Uses simple scoring so that files with both IFA and IFF hints
        are resolved by whichever has more evidence.
        """
        detected = "UNKNOWN"
        try:
            zip_handler = ZipHandler(self.zip_path)
            info_list = zip_handler.info_list()  # list of filenames inside the ZIP

            ifa_score = 0
            iff_score = 0

            for file in info_list:
                lower_name = file.lower()

                # IFA checks
                if any(term in lower_name for term in self.IFA_PATTERNS):
                    ifa_score += 2   # direct keyword is a strong indicator

                if any(rgx.search(lower_name) for rgx in self.IFA_REGEX):
                    ifa_score += 1   # revision-letter is a weak indicator

                # IFF checks
                if any(term in lower_name for term in self.IFF_PATTERNS):
                    iff_score += 2

                if any(rgx.search(lower_name) for rgx in self.IFF_REGEX):
                    iff_score += 1

            if ifa_score > iff_score and ifa_score > 0:
                detected = "IFA-content"
            elif iff_score > ifa_score and iff_score > 0:
                detected = "IFF-content"
            else:
                detected = "UNKNOWN"

            if self.utils:
                self.utils.append_log_action(
                    f"Type detected via contents (IFA score={ifa_score}, IFF score={iff_score}): {detected}",
                    "Info"
                )

        except Exception as e:
            if self.utils:
                self.utils.append_log_action(f"Error scanning ZIP contents: {e}", "Error")

        return detected

    def _scan_contents_for_job_number(self) -> str:
        """
        Scans all filenames inside the ZIP looking for a job number.
        A job number is defined as exactly 4 digits (per JOB_NUM_REGEX).
        Returns the first match found, or 'UNKNOWN'.
        """
        detected = "UNKNOWN"

        try:
            zip_handler = ZipHandler(self.zip_path)
            info_list = zip_handler.info_list()  # filenames inside ZIP

            for file in info_list:
                lower_name = file.lower()

                matches = self.JOB_NUM_REGEX.findall(lower_name)
                for match in matches:
                    if match == self._get_current_year():
                        continue

                    detected = match
                    break

                if detected != "UNKNOWN":
                    break

            if self.utils:
                self.utils.append_log_action(f"Job number detected via contents: {detected}", "Info")

        except Exception as e:
            if self.utils:
                self.utils.append_log_action(f"Error scanning ZIP contents for job number: {e}", "Error")

        return detected



    def _get_current_year(self) -> str:
        return f'{datetime.datetime.now().year}'
