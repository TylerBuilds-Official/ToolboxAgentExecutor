from pathlib import Path
import shutil


class DistributionHandler:
    sd_drive = r'C:\Users\tylere.METALSFAB\Desktop\Shop Drawings\Jobs'
    nc_drive = r'C:\Users\tylere.METALSFAB\Desktop\NC Files'

    def __init__(self, job_data: dict, utils = None):
        self.job_data = job_data
        self.utils = utils
        self.transmittal_type = job_data.get("transmittal_type", "IFF")

        self.shop_drawings_drive =  Path(self.sd_drive)
        self.nc_drive =             Path(self.nc_drive)

        self.built_root =           Path(job_data["built_output"])
        self.job_number =           str(job_data["job_number"])

        self.sd_dest =              self._discover_sd_dest(self.shop_drawings_drive, self.job_number)
        self.nc_dest =              self._discover_nc_dest(self.nc_drive, self.job_number)
        self.enc_dest =             self._discover_enc_dest(self.nc_drive, self.job_number)
        self.zeman_dest =           self._discover_zeman_dest(self.nc_drive, self.job_number)

        self.structure =            self._discover_structure()


    def distribute(self):
        # Log what type of distribution is happening
        if self.utils:
            if self.transmittal_type == "IFA":
                self.utils.append_log_action(
                    "IFA transmittal detected - distributing ONLY erection drawings",
                    "Info"
                )
            else:
                self.utils.append_log_action(
                    f"{self.transmittal_type} transmittal detected - full distribution enabled",
                    "Info"
                )

        discovered_files = self._discover_files()
        routing_table = self._routing_table()
        distribution_map = {}
        
        allowed_categories = self._get_allowed_categories()

        seen_nc = set()
        seen_dxf = set()

        for category, path in routing_table.items():
            # Skip categories not allowed for this transmittal type
            if category not in allowed_categories:
                if self.utils:
                    self.utils.append_log_action(
                        f"Skipping {category} distribution for {self.transmittal_type} transmittal",
                        "Info"
                    )
                continue

            if category == "zeman":
                zeman_folders = self._get_zeman_folders()
                if not zeman_folders:
                    continue

                path.mkdir(parents=True, exist_ok=True)
                for folder in zeman_folders:
                    dest_folder = path / folder.name
                    if self.utils:
                        self.utils.append_log_action(f"Copying Zeman folder {folder.name} to {path}", "Success")
                    try:
                        shutil.copytree(folder, dest_folder, dirs_exist_ok=True)
                        distribution_map.setdefault(category, []).append(folder)
                    except Exception as e:
                        if self.utils:
                            self.utils.append_log_action(f"Error copying Zeman folder {folder}: {e}", "Error")
                continue

            files = discovered_files.get(category, [])
            if not files:
                continue

            path.mkdir(parents=True, exist_ok=True)
            for file in files:
                distribution_map.setdefault(category, []).append(file)

                if category in ("nc1", "nc_dxf") and file.suffix.lower() == ".nc1":
                    seen_nc.add(file.stem)
                if category in ("dxf", "nc_dxf") and file.suffix.lower() == ".dxf":
                    seen_dxf.add(file.stem)

                try:
                    shutil.copy2(file, path)
                except Exception as e:
                    if self.utils:
                        self.utils.append_log_action(f"Error copying {file}: {e}", "Error")

        count_data = {}
        for category, files in distribution_map.items():
            if category == "nc1":
                count_data[category] = len(seen_nc)
            elif category == "dxf":
                count_data[category] = len(seen_dxf)
            elif category == "nc_dxf":
                count_data[category] = len(seen_nc) + len(seen_dxf)
            else:
                count_data[category] = len(files)

        return {"count_data": count_data,
                "distribution_map": distribution_map}

    def _discover_structure(self) -> dict:
        mapping = {
            "fab":          self.built_root / "Drawings/Fabrication Drawings",
            "erection":     self.built_root / "Drawings/Erection Drawings",
            "field":        self.built_root / "Drawings/Field Work",
            "parts":        self.built_root / "Drawings/Part Drawings",
            "void":         self.built_root / "Drawings/Void Drawings",

            "nc1":          self.built_root / "CNC Data/NC1",
            "dxf":          self.built_root / "CNC Data/DXF",
            "nc_dxf":       self.built_root / "CNC Data/NC-DXF Combined",
            "enc":          self.built_root / "CNC Data/ENC",
            "nc_issue":     self.built_root / "CNC Data/NC Error - See import log for details",

            "zeman":        self.built_root / "Zeman Folders",
        }

        return {k: v for k, v in mapping.items() if v.exists()}

    def _get_allowed_categories(self) -> list:
        """
        Returns list of categories that should be distributed based on transmittal type.
        
        - IFF: All categories (full distribution)
        - IFA: Only erection drawings
        """
        if self.transmittal_type == "IFA":
            return ["erection"]
        else:  # IFF or any other type defaults to full distribution
            return ["fab", "erection", "field", "parts", "void", 
                    "nc1", "dxf", "nc_dxf", "enc", "zeman"]


    def _discover_files(self):
        file_discovery = {}
        if self.utils:
            self.utils.append_log_action("Starting file discovery...", level="info")
        for category, path in self.structure.items():
            files = self._scan_category(path)
            file_discovery[category] = files
        return file_discovery


    def _routing_table(self):
        if self.utils:
            self.utils.append_log_action("Building routing table...", level="info")
        return {
            # SHOP DRAWINGS
            "fab":      self.sd_dest / "Drawings/Fabrication",
            "erection": self.sd_dest / "Drawings/ESheets",
            "field":    self.sd_dest / "Drawings/Field Work",
            "parts":    self.sd_dest / "Drawings/Parts",
            "void":     self.sd_dest / "Drawings/Void",

            # CNC DESTINATIONS
            "nc1":      self.nc_dest,
            "dxf":      self.nc_dest,
            "nc_dxf":   self.nc_dest,
            "enc":      self.enc_dest,

            # Folder-level special handling
            "zeman":    self.zeman_dest,
        }


    def _scan_category(self, path: Path):
        if self.utils:
            self.utils.append_log_action(f"Scanning {path.name} for files...", level="Info")
        if not path.exists():
            return []
        return [p for p in path.rglob("*") if p.is_file()]


    def _get_zeman_folders(self) -> list:
        """Return list of Zeman subfolders (not files) to copy as complete directories."""
        zeman_path = self.structure.get("zeman")
        if not zeman_path or not zeman_path.exists():
            return []
        return [p for p in zeman_path.iterdir() if p.is_dir()]


    def _discover_nc_dest(self, nc_drive: Path, job_number: str) -> Path:
        if self.utils:
            self.utils.append_log_action(f"Searching for NC folder for job {job_number}...", level="Info")

        if not nc_drive.exists():
            if self.utils:
                self.utils.append_log_action(f"NC drive {nc_drive} does not exist - creating...", level="Info")
            return nc_drive / f"{job_number}"

        job_number_lower = job_number.lower()

        for folder in nc_drive.iterdir():
            if folder.is_dir() and job_number_lower in folder.name.lower():
                return folder

        return nc_drive / f"{job_number}"


    def _discover_enc_dest(self, nc_drive: Path, job_number: str) -> Path:
        if self.utils:
            self.utils.append_log_action(f"Searching for ENC folder for job {job_number}...", level="Info")

        job_nc_folder = self._discover_nc_dest(nc_drive, job_number)
        job_nc_folder.mkdir(parents=True, exist_ok=True)

        # First: search nested ENC
        for folder in job_nc_folder.iterdir():
            if (
                    folder.is_dir()
                    and job_number.lower() in folder.name.lower()
                    and ("stairs" in folder.name.lower() or "rails" in folder.name.lower() or "enc" in folder.name.lower())):
                return folder

        # Second: search nested
        job_number_lower = job_number.lower()
        for folder in job_nc_folder.iterdir():
            if folder.is_dir() and "enc" in folder.name.lower():
                return folder

        # Default folder inside the NC job folder
        if self.utils:
            self.utils.append_log_action("No ENC folder found - creating default...", level="Info")

        return job_nc_folder / "ENC"


    def _discover_zeman_dest(self, nc_drive: Path, job_number: str) -> Path:
        if self.utils:
            self.utils.append_log_action(f"Searching for Zeman folder for job {job_number}...", level="Info")

        for folder in nc_drive.iterdir():
            if folder.is_dir() and job_number.lower() in folder.name.lower() and "zeman" in folder.name.lower():
                return folder

        # Default
        if self.utils:
            self.utils.append_log_action("No Zeman folder found - creating default...", level="Info")
        return nc_drive / f"{job_number} - Zeman"


    def _discover_sd_dest(self, sd_drive: Path, job_number: str) -> Path:
        if self.utils:
            self.utils.append_log_action(f"Searching for SD folder for job {job_number}...", level="Info")

        if not sd_drive.exists():
            return sd_drive / job_number

        job_number_lower = job_number.lower()

        for folder in sd_drive.iterdir():
            if folder.is_dir() and job_number_lower in folder.name.lower():
                return folder

        if self.utils:
            self.utils.append_log_action("No SD folder found - creating default...", level="Info")
        return sd_drive / job_number








