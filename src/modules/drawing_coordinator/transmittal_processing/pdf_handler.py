import re

from pathlib import Path
from datetime import datetime
from PyPDF2 import PdfMerger, PdfReader
from PyPDF2.generic import DictionaryObject, NumberObject, NameObject, ArrayObject, TextStringObject


class PdfHandler:
    def __init__(self, drawings: dict, job_number: int, transmittal_number: str, transmittal_type: str, utils=None):
        self.drawings = drawings
        self.job_number = job_number
        self.transmittal_number = transmittal_number
        self.transmittal_type = transmittal_type
        self.utils = utils
        self.current_date = datetime.now().strftime("%y%m%d")



    def create_cover_sheet(self, drawings: dict, output_path: Path | str) -> Path:
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        merger = PdfMerger()

        # Order: Erection -> Field -> Fab
        cover_order = ["erection", "field", "fab", "void"]

        current_page = 0

        for category in cover_order:
            files = drawings.get(category, [])
            if not files:
                continue

            sorted_files = sorted(files, key=self.natural_key)

            for file in sorted_files:
                merger.append(str(file))

                # Page label based on filename stem
                label = Path(file).stem
                self.set_page_label(merger, current_page, label)

                # Advance page counter
                num_pages = len(PdfReader(str(file)).pages)
                current_page += num_pages

        if self.transmittal_type == "IFA":
            merger.write(output_path / f"{self.job_number} - {self.transmittal_number} IFA.pdf")
        else:
            merger.write(output_path / f"{self.job_number} - {self.transmittal_number}.pdf")

        merger.close()

    def final_fab_check(self, folder_path: Path):
        """Merge fabrication drawings with suffixes like ' - 1.pdf', ' - 2.pdf', etc."""
        fab_folder = Path(folder_path)
        pdfs = {f.name: f for f in fab_folder.glob("*.pdf")}

        # Match files with " - X.pdf" where X is 1, 2, or 3
        pattern = re.compile(r" - (\d+)\.pdf$")

        for name, path in pdfs.items():
            match = pattern.search(name)
            if not match:
                continue

            suffix_num = int(match.group(1))
            if suffix_num not in range(1, 10):
                continue

            # Strip off the suffix to find base name
            base_name = pattern.sub(".pdf", name)
            base_path = pdfs.get(base_name)

            if base_path and base_path.exists():
                merged_path = fab_folder / base_name
                merged_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    merger = PdfMerger()
                    merger.append(str(base_path))
                    merger.append(str(path))
                    merger.write(str(merged_path))
                    merger.close()

                    path.unlink(missing_ok=True)

                    msg = f"Merged {base_name} + {name}\nMerged to: {merged_path}"

                    print(msg)
                    if self.utils:
                        self.utils.append_log_action(msg, "Success")
                        self.utils.set_status_bar("Merged PDFs")

                except Exception as e:
                    err_msg = f"Error merging {name}: {e}"
                    print(err_msg)
                    if self.utils:
                        self.utils.append_log_action(err_msg, "Error")
                        self.utils.set_status_bar("Error merging PDFs")


    @staticmethod
    def natural_key(path: Path):
        """Return a natural sort key for filenames like E001, 1234, FW002."""
        import re
        return [int(text) if text.isdigit() else text.lower()
                for text in re.split(r'(\d+)', path.stem)]

    @staticmethod
    def set_page_label(merger, page_index, label):
        """Apply a label to a specific page."""
        page_labels = merger.output._root_object.get("/PageLabels")
        if not page_labels:
            page_labels = DictionaryObject()
            page_labels.update({
                NameObject("/Nums"): ArrayObject()
            })
            merger.output._root_object.update({NameObject("/PageLabels"): page_labels})

        nums = page_labels["/Nums"]

        nums.append(NumberObject(page_index))
        nums.append(DictionaryObject({
            NameObject("/P"): TextStringObject(label)  # <-- CORRECT FIX
        }))