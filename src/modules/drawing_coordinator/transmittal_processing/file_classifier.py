import re
from pathlib import Path
from src.modules.drawing_coordinator.logger import HeadlessLogger

class FileClassifier:

    def __init__(self, temp_dir: Path, transmittal_type: str, transmittal_number, utils = None):
        self.temp_dir = Path(temp_dir).resolve()
        self.transmittal_type = transmittal_type
        self.transmittal_number = transmittal_number
        self.utils = utils

        self.categories = {
            "fab":          [],
            "erection":     [],
            "field":        [],
            "parts":        [],
            "nc1":          [],
            "dxf":          [],
            "enc":          [],
            "zeman":        [],
            "void":         [],
            "import":       [],
            "model":        [],
            "nc_issue":     [],
            "other":        [],
            "zips":         [],
            "original":     []
        }


        self.patterns = {
            "zeman":            re.compile(r"(?:\d+\.\s*)?\bzeman([\s_\-]?(files?|reports?|exports?))?\b", re.IGNORECASE),
            "fab_dwgs":         re.compile(r"^(?!.*part)(?:\d+\.\s*)?(fab|assembly)[\s_\-]?(11x17|16x24|24x36|dwg(s)?|drawings?)?", re.IGNORECASE),
            "fab_folder":       re.compile(r"^(?!.*part)(?:\d+\.\s*)?(shop|fab(rication)?)[\s_\-]?(drawings?|dwg(s)?)?", re.IGNORECASE),
            "parts":            re.compile(r"(?:\d+[\.\-\s]*)?\b((?:part|single[\s_\-]?part|gather)s?[\s_\-]?(?:dwg(s)?|drawings?|sheet(s)?)?)\b",re.IGNORECASE),
            "erection":         re.compile(r"(?:\d+\.\s*)?\b(e[\s_\-]*(sheet(s)?|dwg(s)?|drawings?)|erection([\s_\-]?(drawings?|dwg(s)?|sheet(s)?))?)\b",re.IGNORECASE),
            "erection_OL":      re.compile(r"^\s*e[\s_\-]*plans?\b", re.IGNORECASE),
            "field":            re.compile(r"(?:\d+\.\s*)?\b((field[\s_\-]?work?)|fw)[\s_\-]*(drawings?|dwg(s)?|sheet(s)?)?\b",re.IGNORECASE),
            "list_cover":       re.compile(r"transmittal(?:[\s_\-#]*t?\s*#?\d+)?(?:[\s_\-]?(?:list|cover(?:ing)?[\s_\-]?letter|sheet|summary|pkg|package|info|record))?",re.IGNORECASE),
            "list_cover_":      re.compile(r"\b(?!FW\b)[A-Z]{2,4}(?:[-_][A-Z0-9]{2,4}){2,}(?:[-_]\d+)+", re.IGNORECASE),
            "void":             re.compile(r"void", re.IGNORECASE)
        }



    def classify(self) -> dict:
        # --- ZEMAN HANDLING (GLOBAL) ---
        self._collect_all_zeman_folders()

        # --- ORIGINAL FILES (GLOBAL) ---
        self._collect_original_files()

        # --- OTHER CATEGORIES ---
        for folder in self.temp_dir.rglob("*"):
            if not folder.is_dir():
                continue

            if self._is_ignored_folder(folder):
                continue

            if self._is_root_transmittal_folder(folder):
                if self.utils:
                    self.utils.append_log_action(f"Skipping root transmittal folder: {folder}", "Info")
                continue

            if self.utils:
                self.utils.append_log_action(f"Classifying {folder}", "Info")

            # skip already-detected Zeman folders
            if any(folder.is_relative_to(z) or z.is_relative_to(folder) for z in self.categories["zeman"]):
                continue

            if self.patterns["fab_dwgs"].search(folder.name):
                for pdf in folder.rglob("*.pdf"):
                    if self._is_ignored_fab_dwg(pdf):
                        continue
                    if pdf not in self.categories["fab"]:
                        self.categories["fab"].append(pdf)
                continue

            if self.patterns["fab_folder"].search(folder.name):
                for pdf in folder.rglob("*.pdf"):
                    if self._is_ignored_fab_dwg(pdf):
                        continue
                    if pdf not in self.categories["fab"]:
                        self.categories["fab"].append(pdf)
                continue

            if self.patterns["parts"].search(folder.name):
                for pdf in folder.rglob("*.pdf"):
                    if pdf not in self.categories["parts"]:
                        self.categories["parts"].append(pdf)
                continue

            if self.patterns["erection"].search(folder.name):
                for pdf in folder.rglob("*.pdf"):
                    if pdf not in self.categories["erection"]:
                        self.categories["erection"].append(pdf)
                continue

            if self.patterns["erection_OL"].search(folder.name):
                for pdf in folder.rglob("*.pdf"):
                    if pdf not in self.categories["erection"]:
                        self.categories["erection"].append(pdf)
                continue

            if self.patterns["field"].search(folder.name):
                for pdf in folder.rglob("*.pdf"):
                    if pdf not in self.categories["field"]:
                        self.categories["field"].append(pdf)
                continue

            if self.patterns["void"].search(folder.name):
                for pdf in folder.rglob("*.pdf"):
                    if pdf not in self.categories["void"]:
                        self.categories["void"].append(pdf)
                continue

        if self.utils:
            self.utils.append_log_action("Classified all folders", "Info")
            self.utils.append_log_action("Starting file level classification..", "Info")

        # --- FILE-LEVEL SCAN ---
        for file in self.temp_dir.rglob("*"):
            if not file.is_file():
                continue

            # Skip any file inside Zeman folders
            if any(file.is_relative_to(z_path) for z_path in self.categories["zeman"]):
                continue

            ext = file.suffix.lower()
            if ext in [".xml", ".kss"]:
                self.categories["import"].append(file)
                continue
            if ext == ".dxf":
                self.categories["dxf"].append(file)
                continue
            if ext == ".nc1":
                self.categories["nc1"].append(file)
                continue
            if ext == ".ifc" or ext == ".trb" or ext == ".dwg":
                self.categories["model"].append(file)
                continue
            if ext == ".zip":
                self.categories["zips"].append(file)
                continue
            if ext == ".enc":
                self.categories["enc"].append(file)
                continue

            # Catch Lists and Cover letters
            if self.patterns["list_cover"].search(file.name):
                self.categories["other"].append(file)
                continue
            if self.patterns["list_cover_"].search(file.name):
                self.categories["other"].append(file)
                continue


        # --- OTHER FILES ---
        classified_files = {f for v in self.categories.values() for f in v}
        zeman_paths = set(self.categories["zeman"])

        other_exclusions = [
            '.db',
            '.db1'
        ]

        if self.utils:
            self.utils.append_log_action("Collecting other files..", "Info")

        for file in self.temp_dir.rglob("*"):
            if not file.is_file():
                continue

            # Skip anything already classified
            if file in classified_files:
                continue

            # Skip anything with an excluded extension
            if file.suffix.lower() in other_exclusions:
                continue

            # Skip anything inside a Zeman folder (or its subfolders)
            if any(file.is_relative_to(z) for z in zeman_paths):
                continue

            # Skip PDFs from the catch all drawings folder
            if file.parent.name.lower() == "drawings" and file.suffix.lower() == ".pdf":
                continue

            # Skip PDFs from the IFC Package repeat drawings folder
            if file.parent.name.lower() == "pdf parts" or file.parent.name.lower() == "pdf assemblies":
                continue

            # Redundant skip using full path helper
            if self._is_ignored_folder(file):
                continue

            # Safeguard for an edge case: .nc files not in Zeman folders should be in nc1
            if file.suffix.lower() == ".nc" and not self.patterns["zeman"].search(file.parent.name.lower()):
                self.categories["nc_issue"].append(file)
                continue

            self.categories["other"].append(file)

        # Rare fallback case - no folders match fab regex - check usual ignored repeat drawings folder

        # --- FALLBACK: USE PDF ASSEMBLIES IF NO FAB DRAWINGS WERE FOUND ---
        if not self.categories["fab"]:
            if self.utils:
                self.utils.append_log_action(
                    "No fab/shop drawings found; checking PDF Assemblies as fallback...",
                    "Info"
                )

            pdf_assemblies_dirs = [
                folder for folder in self.temp_dir.rglob("*")
                if folder.is_dir() and folder.name.lower() == "pdf assemblies"
            ]

            for folder in pdf_assemblies_dirs:
                # Skip any PDF Assemblies folder that lives under a Zeman path
                if any(folder.is_relative_to(z) for z in zeman_paths):
                    continue

                for pdf in folder.rglob("*.pdf"):
                    # Also skip PDFs inside Zeman subtrees, just in case
                    if any(pdf.is_relative_to(z) for z in zeman_paths):
                        continue
                    if pdf not in self.categories["fab"]:
                        self.categories["fab"].append(pdf)

            if self.utils:
                self.utils.append_log_action(
                    f"Added {len(self.categories['fab'])} drawings from PDF Assemblies to fab category (fallback).",
                    "Info"
                )

        # --- LOGGING ---
        if self.utils:
            total = sum(len(v) for v in self.categories.values())
            self.utils.append_log_action(
                f"Classified {total} files into {len(self.categories)} categories",
                "Success"
            )

            fw_in_fab = [f for f in self.categories["fab"] if "fw" in f.name.lower()]
            if fw_in_fab:

                self.utils.append_log_action(
                    f"Found {len(fw_in_fab)} drawings with FW in the fab folder. Please inspect:",
                    "Warning")

                for filename in fw_in_fab:
                    self.utils.append_log_action(f"  - {filename.name}", "Warning")

        return self.categories

    def _collect_all_zeman_folders(self):
        """Find any Zeman folders anywhere in the temp_dir (even nested)."""

        # Acceptable child folder patterns
        numeric_or_alpha = re.compile(r"^\d+[A-Z]*$", re.IGNORECASE)
        zeman_style = re.compile(r"^[A-Z]{1,3}\d+[A-Z]*$", re.IGNORECASE)

        for folder in self.temp_dir.rglob("*"):
            if not folder.is_dir():
                continue

            # Detect the actual Zeman parent
            if self.patterns["zeman"].search(folder.name):

                # Search children inside the parent
                for sub in folder.iterdir():
                    if not sub.is_dir():
                        continue

                    name = sub.name

                    # Semi redundant validation check preferred of gathering all subfolders.
                    # VALID child folder if it matches EITHER pattern
                    if numeric_or_alpha.match(name) or zeman_style.match(name):
                        self.categories["zeman"].append(sub)

    def _collect_original_files(self):

        for f in self.temp_dir.iterdir():
            self.categories["original"].append(f)


    def _is_ignored_fab_dwg(self, path: Path) -> bool:
        path_str = str(path).lower()
        return any(tok in path_str for tok in ("pdf assemblies", "pdf parts", "ifc package"))

    def _is_ignored_folder(self, path: Path) -> bool:
        for part in path.parts:
            if part.lower() in {"drawings", "pdf assemblies", "ifc package"}:
                return True
        return False

    def _is_root_transmittal_folder(self, folder: Path) -> bool:
        """
        Detects if a folder is likely a root-level container from a zip extraction.
        """

        # Must be a direct child of temp_dir
        if folder.parent != self.temp_dir:
            return False

        name = folder.name.lower()

        # Strong transmittal indicators (definite root)
        if "transmittal" in name:
            return True
        if re.search(r'\btr#\d+|\bt#\d+', name):  # TR#017, T#09
            return True
        if "seq." in name or "sequence" in name:
            return True

        # Status indicators (IFF, IFA, RFF, etc.)
        if re.search(r'\b(iff|ifa|rff|rfa|ifc)\b', name):
            return True

        # Job prefix with date pattern
        has_job_prefix = bool(re.match(r'^\d{4}[_\-\s#]', name))
        has_date = bool(re.search(r'\d{1,2}[-.]\d{1,2}[-.]\d{2,4}', name))
        if has_job_prefix and has_date:
            return True

        # Company prefix patterns (rpktspl_, jpwengineering_, wetransfer_)
        if re.match(r'^[a-z]+_\d{4}', name):  # company_jobnumber pattern
            return True

        # High complexity structure (multiple underscores/hyphens suggesting structured naming)
        segment_count = name.count('_') + name.count('-')
        if segment_count >= 3:  # 3+ segments = likely structured transmittal name
            return True

        # If we get here, check for category keywords
        ROOT_CATEGORY_KEYWORDS = [
            "fw", "fwd", "field",
            "fab", "fabrication",
            "e-dwg", "edwg", "erection",
            "shop",
            "nc1", "nc",
            "dxf",
            "parts",
            "zeman"
        ]

        has_category_keyword = any(kw in name for kw in ROOT_CATEGORY_KEYWORDS)

        if has_category_keyword:
            segment_count = name.count('_') + name.count('-')

            # Paper sizes should be treated as simple content markers, not complexity
            SIMPLE_CONTENT_INDICATORS = ["11x17", "16x24", "24x36", "drawing", "drawings"]
            has_simple_indicator = any(word in name for word in SIMPLE_CONTENT_INDICATORS)

            if segment_count <= 1 and has_simple_indicator:
                return False  # Simple content folder

            if segment_count <= 1 and not re.search(r'\d{4}', name):  # no 4-digit job number
                return False  # Simple content folder

            return True

        return False
