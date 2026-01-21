import shutil
from pathlib import Path

from src.modules.drawing_coordinator.transmittal_processing.xml_handler import XMLHandler
from src.modules.drawing_coordinator.transmittal_processing.zip_handler import ZipHandler
from src.modules.drawing_coordinator.transmittal_processing.type_detector import TypeDetector
from src.modules.drawing_coordinator.transmittal_processing.file_classifier import FileClassifier
from src.modules.drawing_coordinator.transmittal_processing.folder_builder import FolderBuilder
from src.modules.drawing_coordinator.transmittal_processing.distribution_handler import DistributionHandler
from src.modules.drawing_coordinator.transmittal_processing.pdf_handler import PdfHandler


# DialogManager not used in agent context
DialogManager = None


class BackendFacade:
    """
    High-level API that exposes the 4–5 main steps the worker will run.
    Each function updates job_data and uses backend modules
    """

    def extract_zip(self, job_data, logger):
        zip_path = Path(job_data["zip_path"])
        handler = ZipHandler(zip_path, utils=logger)

        temp_dir = handler.extract()
        job_data["temp_dir"] = temp_dir
        return temp_dir

    def detect_types(self, job_data, logger):
        zip_path = Path(job_data["zip_path"])
        detector = TypeDetector(zip_path, utils=logger)

        job_data["transmittal_type"] = detector.detect_type()
        job_data["transmittal_number"] = detector.detect_transmittal_number()
        job_data["job_number"] = detector.detect_job_number()

        return job_data

    def classify_files(self, job_data, logger):
        classifier = FileClassifier(
            job_data["temp_dir"],
            job_data["transmittal_type"],
            job_data["transmittal_number"],
            utils=logger
        )

        classified = classifier.classify()
        job_data["classified"] = classified

        return classified

    def build_output(self, job_data, logger):
        out_dir = Path(job_data["output_path"])

        builder = FolderBuilder(
            out_dir,
            job_data["classified"],
            job_data["transmittal_type"],
            job_data["transmittal_number"],
            job_data["job_number"],
            utils=logger
        )

        build_result = builder.build_folder_structure()

        job_data["final_output_folder"] = build_result["built_output"]
        job_data["built_output"] = build_result["built_output"]
        job_data["output_structure"] = build_result["structure"]

        return build_result


    def create_cover_sheet(self, job_data, logger):
        handler = PdfHandler(
            job_data["classified"],
            job_data["job_number"],
            job_data["transmittal_number"],
            job_data["transmittal_type"],
            utils=logger
        )
        handler.create_cover_sheet(job_data["classified"], job_data["final_output_folder"])
        logger.append_log_action("Created Cover Sheet", "Success")

    def finalize_output(self, job_data, logger):
        # Run final fab check if fab folder exists
        final_output = job_data.get("final_output_folder")
        if final_output:
            handler = PdfHandler(
                job_data["classified"],
                job_data["job_number"],
                job_data["transmittal_number"],
                job_data["transmittal_type"],
                utils=logger
            )
            
            fab_folder = final_output / "Drawings/Fabrication Drawings"
            if fab_folder.exists():
                logger.append_log_action("Running final fabrication drawing check..", "Info")
                handler.final_fab_check(fab_folder)

            self.patch_xml_files(job_data, logger)

        logger.append_log_action("Output Finalized..", "Success")

    def distribute_files(self, job_data, logger):
        """
        Distribute processed files to their final destinations (SD drive, NC drive, etc.)
        """
        if not job_data.get("built_output"):
            logger.append_log_action("No built_output path - skipping distribution", "Warning")
            return None

        handler = DistributionHandler(job_data, utils=logger)
        result = handler.distribute()

        job_data["distribution_result"] = result
        logger.append_log_action(
            f"Distribution complete: {result['count_data']}",
            "Success"
        )

        return result


    def cleanup_temp(self, job_data, logger):
        """
        Safely delete the temp directory for this job, if it exists.
        """
        temp_dir = job_data.get("temp_dir")
        if not temp_dir:
            return

        temp_dir = Path(temp_dir)
        if not temp_dir.exists():
            logger.append_log_action(f"Temp directory already gone: {temp_dir}", "Info")
            return

        try:
            shutil.rmtree(temp_dir)
            logger.append_log_action(f"Cleaned temp folder: {temp_dir}", "Success")
        except Exception as e:
            logger.append_log_action(f"Cleanup error for {temp_dir}: {e}", "Error")

    def get_job_number(self, job_data, logger):
        # Prefer headless path first (job_data provided)
        job_no = job_data.get("job_number")
        if job_no:
            logger.append_log_action(f"Using provided job number: {job_no}", "Info")
            return job_no

        # Fallback to UI dialog if available
        if DialogManager is not None:
            dlg = DialogManager().job_number_dialog()
            dlg.exec()
            job_data["job_number"] = dlg.trans_number_label.text()
            return dlg.trans_number_label.text()

        # If neither provided nor UI available, raise a clear error
        raise RuntimeError(
            "Job number is required in headless mode. Provide job_data['job_number']."
        )

    def patch_xml_files(self, job_data, logger):
        """
        If the output contains an Import Files directory, search for XML files
        and apply the required replacements.
        """

        final_output = job_data.get("final_output_folder")
        if not final_output:
            logger.append_log_action("No final output folder—skipping XML patching", "Info")
            return

        import_dir = final_output / "Import Files"
        if not import_dir.exists():
            logger.append_log_action("No 'Import Files' folder—skipping XML patching", "Info")
            return

        xml_handler = XMLHandler(logger)

        count = 0
        for xml_file in import_dir.rglob("*.xml"):
            xml_handler.process_xml_file(xml_file)
            count += 1

        logger.append_log_action(f"XML patching complete ({count} files patched)", "Success")