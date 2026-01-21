import shutil
import zipfile
from pathlib import Path
import re

from datetime import datetime

from src.modules.drawing_coordinator.logger import HeadlessLogger

class FolderBuilder:

    def __init__(self, output_dir: Path, classified_files: dict, transmittal_type, transmittal_number, job_number=None, utils = None):
        self.output_dir = output_dir.resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.classified_files = self._validate_paths(classified_files)
        self.transmittal_type = transmittal_type
        self.transmittal_number = transmittal_number
        self.job_number = job_number
        self.utils = utils

        self.current_date = datetime.now().strftime("%y%m%d")

        # Determine job bucket
        job_bucket = self.job_number if self.job_number else "Unknown Job Number"

        # Base folder name: "YYMMDD - ###"
        folder_name = f"{self.current_date} - {self.transmittal_number}"

        if self.transmittal_type and self.transmittal_type.lower() == "ifa":
            folder_name += " IFA"

        # Final base path
        self.base = Path(self.output_dir) / job_bucket / folder_name

        self.structure = {
            "revisions":        self.base / "Revisions",
            "fab":              self.base / "Drawings/Fabrication Drawings",
            "erection":         self.base / "Drawings/Erection Drawings",
            "field":            self.base / "Drawings/Field Work",
            "parts":            self.base / "Drawings/Part Drawings",
            "nc1":              self.base / "CNC Data/NC1",
            "nc_issue":         self.base / "CNC Data/NC Error - See import log for details",
            "dxf":              self.base / "CNC Data/DXF",
            "nc_dxf":           self.base / "CNC Data/NC-DXF Combined",
            "enc":              self.base / "CNC Data/ENC",
            "zeman":            self.base / "Zeman Folders",
            "void":             self.base / "Drawings/Void Drawings",
            "model":            self.base / "Model",
            "import":           self.base / "Import Files",
            "zips":             self.base / "Lists & Misc/Nested Zips",
            "other":            self.base / "Lists & Misc",
            "original":         self.base / "Original Files"
        }

        self.revision_map = {
            "fab": "Fabrication",
            "erection": "Erection",
            "field": "Field",
            "parts": "Parts",
            "void": "Void"
        }

    def build_folder_structure(self) -> dict:
        self._copy_originals()
        self._copy_to_revisions()
        self._copy_drawings()
        self._copy_data_files()
        self._check_stray_nc_files()
        self._copy_import_files()
        self._copy_zeman_folders()
        self._copy_model_files()
        self._copy_other_folders()
        self._finalize()

        return {
            "built_output": self.base,
            "structure": self.structure,
            "job_number": self.job_number,
            "transmittal_number": self.transmittal_number,
            "transmittal_type": self.transmittal_type,
        }


# ---------------------------------------------------------------------

    def _copy_originals(self):
        original_files = self.classified_files.get("original", [])
        if not original_files:
            return

        original_dir = self.structure["original"]
        original_dir.mkdir(parents=True, exist_ok=True)

        for src in original_files:
            if src.is_dir():
                dest_dir = original_dir / src.name
                self._safe_copy_dir(src, dest_dir)
                continue

            if src.is_file() and src.suffix.lower() == ".zip":
                self._safe_copy(src, original_dir / src.name)

                try:
                    with zipfile.ZipFile(src, "r") as zip_ref:
                        zip_ref.extractall(original_dir)
                    if self.utils:
                        self.utils.append_log_action(f"Extracted nested zip: {src}", "Success")
                except Exception as e:
                    if self.utils:
                        self.utils.append_log_action(f"Error extracting nested zip: {src}: {e}", "Error")
                continue

            if src.is_file():
                self._safe_copy(src, original_dir / src.name)

        if self.utils:
            self.utils.append_log_action("Copied all original files", "Success")
            self.utils.set_status_bar("Original Files Backup - Complete")


    def _copy_to_revisions(self):
        copy_map = {}
        drawing_categories = self._get_drawing_categories()
        revision_map = self.revision_map

        revision_dir = self.structure["revisions"]
        revision_dir.mkdir(parents=True, exist_ok=True)

        for category in drawing_categories:
            files = self.classified_files.get(category, [])
            copy_map[category] = []

            if not files:
                continue

            target_dir = revision_dir / revision_map[category]
            target_dir.mkdir(parents=True, exist_ok=True)

            for src in files:
                if src.suffix.lower() != ".pdf":
                    continue

                dest = target_dir / src.name
                self._safe_copy(src, dest)
                copy_map[category].append(dest)
                # print(f'Source: {src} | Destination: {dest}\n')

            if self.utils:
                self.utils.append_log_action(f"Copied {len(files)} {category} drawings to {target_dir}", "Success")

        if self.utils:
            self.utils.append_log_action("Copied all revisions", "Success")
            self.utils.set_status_bar("Revisions Backup - Complete")

        return copy_map


    def _copy_drawings(self):
        for category in self._get_drawing_categories():
            files = self.classified_files.get(category, [])
            if not files:
                if self.utils:
                    print(f"No files to copy for {category}")
                    self.utils.append_log_action(f"No files to copy for {category}", "info")
                continue

            for src in files:
                if src.suffix.lower() != ".pdf":
                    continue

                target_dir = self.structure[category]
                target_dir.mkdir(parents=True, exist_ok=True)

                if category == "erection":
                    bucket = self._detect_bucket(src.name, "E") # -> "E1", "E2", etc.
                    if bucket:
                        target_dir = target_dir / bucket
                        target_dir.mkdir(parents=True, exist_ok=True)

                if category == "field":
                    bucket = self._detect_bucket(src.name, "F") # -> "F1", "F2", etc.
                    if bucket:
                        target_dir = target_dir / bucket
                        target_dir.mkdir(parents=True, exist_ok=True)

                dest = self._rename_and_copy(src, target_dir)

            if self.utils:
                self.utils.append_log_action(
                    f"Copied {len(files)} {category} drawings to {target_dir}",
                    "Success"
                )


    def _copy_data_files(self):
        """
        Copies CNC and DXF files into their respective folders under 'CNC Data'.
        """
        try:
            nc_files = self.classified_files.get("nc1", [])
            dxf_files = self.classified_files.get("dxf", [])
            enc_files = self.classified_files.get("enc", [])

            if not nc_files and not dxf_files and not enc_files:
                if self.utils:
                    self.utils.append_log_action("No Data files to copy", "Info")
                return

            if nc_files:
                # Make sure dir exists
                nc_dir = self.structure["nc1"]
                nc_dir.mkdir(parents=True, exist_ok=True)

                nc_dxf_combined_dir = self.structure["nc_dxf"]
                nc_dxf_combined_dir.mkdir(parents=True, exist_ok=True)

                # Copy NC1 files
                for src in nc_files:
                    dest = nc_dir / src.name
                    self._safe_copy(src, dest)
                    combine_dest = nc_dxf_combined_dir / src.name
                    self._safe_copy(src, combine_dest)


            if dxf_files:
                # Make sure dir exists
                dxf_dir = self.structure["dxf"]
                dxf_dir.mkdir(parents=True, exist_ok=True)
                nc_dxf_combined_dir = self.structure["nc_dxf"]
                nc_dxf_combined_dir.mkdir(parents=True, exist_ok=True)

                # Copy DXF files
                for src in dxf_files:
                    dest = dxf_dir / src.name
                    self._safe_copy(src, dest)
                    combine_dest = nc_dxf_combined_dir / src.name
                    self._safe_copy(src, combine_dest)

            if enc_files:
                # Make sure dir exists
                enc_dir = self.structure["enc"]
                enc_dir.mkdir(parents=True, exist_ok=True)

                # Copy ENC files
                for src in enc_files:
                    dest = enc_dir / src.name
                    self._safe_copy(src, dest)

            if self.utils:
                nc_count = len(nc_files)
                dxf_count = len(dxf_files)
                enc_count = len(enc_files)

                nc_msg = f"Copied {nc_count} NC1 to \\CNC Data folder"
                dxf_msg = f"Copied {dxf_count} DXF to \\CNC Data folder"
                both_msg = f"Copied {nc_count} NC1 and {dxf_count} DXF to \\CNC Data folder"


                if enc_count > 0:
                    self.utils.append_log_action(f"Copied {enc_count} ENC files to \\CNC Data folder", "Success")
                    self.utils.set_status_bar(f"Copied {enc_count} ENC files to \\CNC Data folder")
                else:
                    self.utils.append_log_action(f"No ENC files to copy", "Info")

                if nc_count > 0 and dxf_count > 0:
                    self.utils.append_log_action(both_msg, "Success")
                    self.utils.set_status_bar(both_msg)

                elif nc_count > 0 and dxf_count == 0:
                    self.utils.append_log_action(nc_msg, "Success")
                    self.utils.set_status_bar(nc_msg)

                elif nc_count == 0 and dxf_count > 0:
                    self.utils.append_log_action(dxf_msg, "Success")
                    self.utils.set_status_bar(dxf_msg)

        except Exception as e:
            if self.utils:
                self.utils.append_log_action(f"Error copying CNC or DXF files: {e}", "Error")
                self.utils.set_status_bar("Error: Failed to copy CNC or DXF files")


    def _copy_import_files(self):

        import_files = self.classified_files.get("import", [])
        if not import_files:
            if self.utils:
                self.utils.append_log_action("No import files to copy", "Error")
            return

        import_dir = self.structure["import"]
        import_dir.mkdir(parents=True, exist_ok=True)

        for src in import_files:
            dest = import_dir / src.name
            self._safe_copy(src, dest)

        if self.utils:
            self.utils.append_log_action("Copied all import files", "Success")
            self.utils.set_status_bar("All import files copied successfully")


    def _copy_zeman_folders(self):

        zeman_folders = self.classified_files.get("zeman", [])
        if not zeman_folders:
            if self.utils:
                self.utils.append_log_action("No Zeman reports to copy", "Info")

            return

        zeman_base_folder = self.structure["zeman"]
        zeman_base_folder.mkdir(parents=True, exist_ok=True)

        copied_count = 0
        for folder in zeman_folders:
            dest = zeman_base_folder / folder.name
            try:
                if dest.exists():
                    shutil.rmtree(dest)

                self._safe_copy_dir(folder, dest)
                copied_count += 1
            except Exception as e:
                print(e)
                if self.utils:
                    self.utils.append_log_action(f"Error copying Zeman folder {folder}: {e}", "Error")
                    self.utils.set_status_bar("Error: Failed to copy Zeman folder")

        if self.utils:
            self.utils.append_log_action(f"Copied {copied_count} Zeman folders", "Success")
            self.utils.set_status_bar(f"Copied {copied_count} Zeman folders")


    def _copy_model_files(self):
        model_files = self.classified_files.get("model", [])
        if not model_files:
            return

        model_dir = self.structure["model"]
        model_dir.mkdir(parents=True, exist_ok=True)

        for src in model_files:
            dest = model_dir / src.name
            self._safe_copy(src, dest)

        if self.utils:
            self.utils.append_log_action(f"Copied {len(model_files)} model files", "Success")
            self.utils.set_status_bar("Copied model files")



    def _copy_other_folders(self):
        other_files = self.classified_files.get("other", [])
        if not other_files:
            if self.utils:
                self.utils.append_log_action("No Other/List files to copy", "Info")
            return

        other_dir = self.structure["other"]
        other_dir.mkdir(parents=True, exist_ok=True)


        for src in other_files:
            if src.name.lower().endswith(".xsr"):
                xsr_dir = self.structure["other"] / "XSR Files"
                xsr_dir.mkdir(parents=True, exist_ok=True)
                dest = xsr_dir / src.name
                self._safe_copy(src, dest)
                continue

            dest = other_dir / src.name
            self._safe_copy(src, dest)

        self._copy_zip_folders()

        if self.utils:
            self.utils.append_log_action(f"Copied {len(other_files)} List/Other files", "Success")


    def _copy_zip_folders(self):
        zip_files = self.classified_files.get("zips", [])
        if not zip_files:
            return
        zip_dir = self.structure["zips"]
        zip_dir.mkdir(parents=True, exist_ok=True)

        for src in zip_files:
            dest = zip_dir / src.name
            self._safe_copy(src, dest)

        if self.utils:
            self.utils.append_log_action(f"Copied {len(zip_files)} zip files to /Lists & Misc", "Success")

    def _check_stray_nc_files(self):
        nc_issue_files = self.classified_files.get("nc_issue", [])
        if not nc_issue_files:
            return

        nc_issue_dir = self.structure["nc_issue"]
        nc_issue_dir.mkdir(parents=True, exist_ok=True)

        for src in nc_issue_files:
            dest = nc_issue_dir / src.name
            self._safe_copy(src, dest)

        if self.utils:
            self.utils.append_log_action(f"Copied {len(nc_issue_files)} NC Error files to /CNC Data - NC files found outside of zeman folders", "Success")
            self.utils.set_status_bar("NC Error files copied successfully - Please see log for details")

    def _finalize(self):
        if self.utils:
            self.utils.append_log_action("Folder structure built successfully", "Success")
            self.utils.set_status_bar("Folder structure built successfully")

            self.utils.append_log_action(f"Transmittal Build: {self.transmittal_type} | {self.transmittal_number} | Complete", "Success")
            self.utils.set_status_bar("Transmittal Build Complete")

            self.utils.append_log_action(
                "Files:\n"
                    f"    NC: {len(self.classified_files['nc1'])}\n"
                    f"    DXF: {len(self.classified_files['dxf'])}\n"
                    f"    Fabrication: {len(self.classified_files['fab'])}\n"
                    f"    Erection: {len(self.classified_files['erection'])}\n"
                    f"    Field Work: {len(self.classified_files['field'])}\n"
                    f"    Parts: {len(self.classified_files['parts'])}\n"
                    f"    Zeman Folders: {len(self.classified_files['zeman'])}\n"
                    f"    Other: {len(self.classified_files['other'])}",
                    "Success"
            )

    # --- Helper methods -------------------------------------------

# File Copying helpers

    def _safe_copy(self, src, dest):
        try:
            if src.is_file():
                shutil.copy2(src, dest)

                # Per file logging causes UI lockups on large transmittals — removed for now.
                # if self.utils:
                #     self.utils.append_log_action(f"Copied file {src} → {dest}", "Success")

        except Exception as e:
            if self.utils:
                self.utils.append_log_action(f"Error copying file {src}: {e}", "Error")


    def _safe_copy_dir(self, src, dest):
        try:
            if src.is_dir() and not dest.is_relative_to(src):
                shutil.copytree(src, dest, dirs_exist_ok=True)

        except Exception as e:
            print(e)
            if self.utils:
                self.utils.append_log_action(f"Error copying folder {src}: {e}", "Error")


    def _rename_and_copy(self, src, dest_dir):
        clean_name = self._strip_revision(src.name)
        dest = dest_dir / clean_name

        if dest.exists():
            if self.utils:
                self.utils.append_log_action(f"Skipping: File already exists", "Warning")

        self._safe_copy(src, dest)
        return dest



# File Naming Helpers

    def _strip_revision(self, filename):
        name, ext = Path(filename).stem, Path(filename).suffix

        # Pre-pass: collapse patterns like
        #   "<prefix> - <DESC> - Rev/Revision X"
        # into
        #   "<prefix> - Rev/Revision X"
        #
        # This is specifically to handle parts-style names such as:
        #   "p698 - PLATE - Rev 0"
        #   "698 - BEAM - Revision A"
        #   "AB12-03 - BOLLARD - Rev 2"
        #
        # We don't assume anything about <prefix>; we just require:
        #   - three segments separated by " - "
        #   - the middle segment has no digits (looks like a descriptor)
        part_like_pattern = re.compile(
            r"^(?P<prefix>.+?)\s*-\s*(?P<desc>[^-]+?)\s*-\s*(?P<rev>rev(?:ision)?[\s_\-]?[a-z0-9]+)\s*$",
            re.IGNORECASE,
        )

        m = part_like_pattern.match(name)
        if m:
            desc = m.group("desc").strip()
            # Only treat as a descriptor if it has no digits at all
            if desc and not any(ch.isdigit() for ch in desc):
                # e.g. "p698 - PLATE - Rev 0" -> "p698 - Rev 0"
                name = f"{m.group('prefix').strip()} - {m.group('rev')}"

        # General-purpose revision stripping
        cleaned = re.sub(
            r"([_\-\s]?rev[\s_\-]?[a-z0-9]+|_[a-z0-9]$)",
            "",
            name,
            flags=re.IGNORECASE
        )

        cleaned = cleaned.strip("_- ") + ext
        return cleaned


    def _detect_bucket(self, filename: str, prefix: str) -> str:
        """
        Generic detection of bucket name based on revision identifier.
        Supports both:
          - Standard formats: "Rev A", "Revision 1", "R3"
          - Suffix formats: "_A", "_0", "-1", "-B" (1–2 chars only at end)
        """
        match = re.search(
            r"(?:\b(?:rev(?:ision)?\s*[-_.:]*\s*|r(?:\s*[-_.:]+\s*|\s+|(?=[0-9])))([A-Z0-9]+)|[-_]([A-Z0-9]{1,2})(?=\.[^.]+$|$))",
            filename,
            re.IGNORECASE
        )

        if not match:
            return f"{prefix} - Unknown"

        # pick whichever branch matched
        rev = match.group(1) or match.group(2)
        rev = rev.upper().strip()

        # Strip random junk at end of revision. I.e (for field)
        rev = re.split(r"[\s\(\[]", rev)[0]

        return f"{prefix}{rev}"

    def _get_drawing_categories(self):
        """Return a list of drawing directories."""
        return ["fab", "erection", "field", "parts", "void"]

    def _validate_paths(self, classified_files: dict) -> dict:
        validated = {}
        for category, files in classified_files.items():
            validated[category] = [f for f in files if Path(f).exists()]

        return validated



    # REMOVED AND REPLACED FUNCTIONS
    # REPLACED: ->   _detect_bucket()
    # def _detect_erection_bucket(self, filename: str) -> str:
    #     """
    #         Detects erection bucket name based on revision identifier.
    #         Supports both:
    #           - Standard formats: "Rev A", "Revision 1", "R3"
    #           - Suffix formats: "_A", "_0", "-1", "-B" (1–2 chars only at end)
    #         """
    #
    #     # Combined regex:
    #     #  Group 1 → Rev/Revision/R formats (Enforced boundaries to avoid "randomfile" or "PART")
    #     #  Group 2 → _A / -1 suffix formats (1–2 chars only, end of filename)
    #     match = re.search(
    #         r"(?:\b(?:rev(?:ision)?\s*[-_.:]*\s*|r(?:\s*[-_.:]+\s*|\s+|(?=[0-9])))([A-Z0-9]+)|[-_]([A-Z0-9]{1,2})(?=\.[^.]+$|$))",
    #         filename,
    #         re.IGNORECASE
    #     )
    #
    #     if not match:
    #         return "E - Unknown"
    #
    #     # pick whichever branch matched
    #     rev = match.group(1) or match.group(2)
    #     rev = rev.upper().strip()
    #
    #     # Strip random junk at end of revision. I.e (for field)
    #     rev = re.split(r"[\s\(\[]", rev)[0]
    #
    #     return f"E{rev}"
    #
    # REPLACED: ->   _detect_bucket()
    # def _detect_field_work_bucket(self, filename: str) -> str:
    #     """
    #     Detects field work bucket name based on revision identifier.
    #     Mirrors _detect_erection_bucket but prefixes with 'F' instead of 'E'.
    #     Examples:
    #       FW-2160-Rev_0 -> F0
    #       FW-2145-Rev_1 -> F1
    #       FW-2123-Rev_A -> FA
    #       FW-2031 -> F - Unknown
    #     """
    #     match = re.search(r"(?:rev(?:ision)?|r)\s*[-_.:]*\s*([A-Z0-9]+)\b", filename, re.IGNORECASE)
    #
    #     if not match or match.group(1) is None:
    #         return "F - Unknown"
    #
    #     rev = match.group(1).upper().strip()
    #     rev = re.split(r"[\s\(\[]", rev)[0]
    #
    #     return f"F{rev}"


    # # REMOVED: -> final_fab_check() -> added to - PDFHandler
    # def _final_fab_check(self, folder_path: Path):
    #     """Merge fabrication drawings with suffixes like ' - 1.pdf', ' - 2.pdf', etc."""
    #     fab_folder = Path(folder_path)
    #     pdfs = {f.name: f for f in fab_folder.glob("*.pdf")}
    #
    #     # Match files with " - X.pdf" where X is 1, 2, or 3
    #     pattern = re.compile(r" - (\d+)\.pdf$")
    #
    #     for name, path in pdfs.items():
    #         match = pattern.search(name)
    #         if not match:
    #             continue
    #
    #         suffix_num = int(match.group(1))
    #         if suffix_num not in range(1, 10):
    #             continue
    #
    #         # Strip off the suffix to find base name
    #         base_name = pattern.sub(".pdf", name)
    #         base_path = pdfs.get(base_name)
    #
    #         if base_path and base_path.exists():
    #             merged_path = fab_folder / base_name
    #             merged_path.parent.mkdir(parents=True, exist_ok=True)
    #             try:
    #                 merger = PdfMerger()
    #                 merger.append(str(base_path))
    #                 merger.append(str(path))
    #                 merger.write(str(merged_path))
    #                 merger.close()
    #
    #                 path.unlink(missing_ok=True)
    #
    #                 msg = f"Merged {base_name} + {name}\nMerged to: {merged_path}"
    #
    #                 print(msg)
    #                 if self.utils:
    #                     self.utils.append_log_action(msg, "Success")
    #                     self.utils.set_status_bar("Merged PDFs")
    #
    #             except Exception as e:
    #                 err_msg = f"Error merging {name}: {e}"
    #                 print(err_msg)
    #                 if self.utils:
    #                     self.utils.append_log_action(err_msg, "Error")
    #                     self.utils.set_status_bar("Error merging PDFs")
    #
    # # REMOVED: Unified to _copy_drawings()
    # def _copy_void_dwgs(self):
    #     """
    #     Removed*
    #     This function was used to classify and gather void drawings, but this has been unified to _copy_drawings.
    #     """
    #     void_files = self.classified_files.get("void", [])
    #     if void_files:
    #         void_dir = self.structure["void"]
    #         void_dir.mkdir(parents=True, exist_ok=True)
    #         for src in void_files:
    #             dest = void_dir / src.name
    #             self._safe_copy(src, dest)
    #
    #         if self.utils:
    #             self.utils.append_log_action(f"Copied {len(void_files)} void drawings to {void_dir}", "Success")
    #     return NotImplementedError
