from pathlib import Path
from typing import Optional
import json

from src.modules.drawing_coordinator.logger import HeadlessLogger
from src.modules.drawing_coordinator.transmittal_processing.backend_facade import BackendFacade
from src.modules.drawing_coordinator.config import DEFAULT_OUTPUT_PATH, DISTRIBUTION_ENABLED

def process_transmittal(
        zip_path: str,
        output_path: Optional[str] = None,
        job_number: Optional[str] = None,
        distribute_data: bool = True) -> dict:
        """
    Process a transmittal ZIP file through the full pipeline.

    Args:
        zip_path: Full path to the input ZIP file
        output_path: Directory where processed output should be saved (optional, defaults to ~/Desktop/DrawingCoordinatorMCP/Output)
        job_number: Optional 4-digit job number. If not provided, will attempt auto-detection.
        distribute_data: Bool indicating whether to distribute files to network destinations.

    Returns:
        dict containing:
            - success: bool
            - job_data: dict with all detected/processed information
            - logs: summarized log entries (errors, warnings, key milestones)
            - status: final status message
            - error: error message if failed (only present on failure)
            - log_file: path to detailed log file if created
    """

        logger = HeadlessLogger()
        facade = BackendFacade()

        # Apply default output path if not provided
        if output_path is None:
            output_path = DEFAULT_OUTPUT_PATH
            logger.append_log_action(f"No output path provided, using default: {output_path}", "Info")
        else:
            logger.append_log_action(f"Using provided output path: {output_path}", "Info")

        job_data = {
            "zip_path":             zip_path,
            "output_path":          output_path,
            "job_number":           job_number,
            "transmittal_type":     None,
            "transmittal_number":   None,
            "temp_dir":             None,
            "classified":           None,
            "final_output_folder":  None
        }

        try:
            logger.append_log_action("Starting transmittal processing pipeline", "Info")

            # Validate inputs
            zip_file = Path(zip_path)
            if not zip_file.exists():
                raise FileNotFoundError(f"ZIP file not found: {zip_path}")
            if not zip_file.suffix.lower() == ".zip":
                raise ValueError(f"Input file must be a ZIP archive: {zip_path}")

            # Convert to Path and ensure output directory exists
            output_path = Path(output_path)
            output_path.mkdir(parents=True, exist_ok=True)
            logger.append_log_action(f"Output directory ready: {output_path}", "Info")

            # ---- STEP 1: Extract ZIP ----
            logger.append_log_action("Step 1: Extracting ZIP", "Info")
            temp_dir = facade.extract_zip(job_data, logger)

            # ---- STEP 2: Detect Types ----
            logger.append_log_action("Step 2: Detecting transmittal metadata", "Info")
            facade.detect_types(job_data, logger)

            # ---- STEP 3: Handle Missing Job Number ----
            # If job_number wasn't provided and detection failed, raise error
            if not job_data.get("job_number") or job_data["job_number"] == "UNKNOWN":
                if job_number:
                    # User provided it, use it
                    job_data["job_number"] = job_number
                    logger.append_log_action(f"Using provided job number: {job_number}", "Info")
                else:
                    # Can't proceed without job number in headless mode
                    raise ValueError(
                        "Job number could not be detected from ZIP filename or contents. "
                        "Please provide job_number parameter."
                    )

            # ---- STEP 4: Handle Missing Transmittal Number ----
            if job_data.get("transmittal_number") == "UNKNOWN":
                logger.append_log_action(
                    "Warning: Transmittal number could not be detected. Using 'UNKNOWN'.",
                    "Warning"
                )

            # ---- STEP 5: Classify Files ----
            logger.append_log_action("Step 3: Classifying files", "Info")
            classified = facade.classify_files(job_data, logger)

            # ---- STEP 6: Build Output Structure ----
            logger.append_log_action("Step 4: Building output folder structure", "Info")
            facade.build_output(job_data, logger)

            # ---- STEP 7: Create Cover Sheet ----
            logger.append_log_action("Step 5: Creating cover sheet PDF", "Info")
            facade.create_cover_sheet(job_data, logger)

            # ---- STEP 8: Finalize Output ----
            logger.append_log_action("Step 6: Finalizing output", "Info")
            facade.finalize_output(job_data, logger)

            # ---- STEP 9: Distribute Files ----
            if distribute_data and DISTRIBUTION_ENABLED:
                logger.append_log_action("Step 7: Distributing files to destinations", "Info")
                facade.distribute_files(job_data, logger)
            elif distribute_data and not DISTRIBUTION_ENABLED:
                logger.append_log_action("Distribution disabled via config (DISTRIBUTION_ENABLED=False)", "Info")
            else:
                logger.append_log_action("Skipping file distribution (user request)", "Info")

            # ---- STEP 10: Cleanup ----
            logger.append_log_action("Step 8: Cleaning up temporary files", "Info")
            facade.cleanup_temp(job_data, logger)

            logger.append_log_action("Transmittal processing complete!", "Success")
            logger.set_status_bar("Processing completed successfully")

            # Write detailed logs to file for large transmittals
            log_file_path = None
            if job_data.get("final_output_folder"):
                try:
                    import json
                    log_file_path = Path(job_data["final_output_folder"]) / "processing_log.json"
                    with open(log_file_path, 'w') as f:
                        json.dump(logger.as_dict(), f, indent=2)
                    logger.append_log_action(f"Detailed logs saved to: {log_file_path}", "Info")
                except Exception as e:
                    logger.append_log_action(f"Warning: Could not save log file: {e}", "Warning")

            # success response
            # Limit logs to prevent context overflow for large transmittals
            all_logs = logger.as_dict()["entries"]
            log_summary = {
                "total_entries": len(all_logs),
                "errors": [log for log in all_logs if log["level"] == "Error"],
                "warnings": [log for log in all_logs if log["level"] == "Warning"],
                "key_milestones": [log for log in all_logs if any(phrase in log["message"] 
                    for phrase in ["Step", "complete", "Starting", "Finalizing"])]
            }
            
            return {
                "success": True,
                "job_data": {
                    "job_number": job_data["job_number"],
                    "transmittal_number": job_data["transmittal_number"],
                    "transmittal_type": job_data["transmittal_type"],
                    "output_folder": str(job_data["final_output_folder"]),
                    "file_counts": {
                        "fabrication": len(job_data["classified"].get("fab", [])),
                        "erection": len(job_data["classified"].get("erection", [])),
                        "field": len(job_data["classified"].get("field", [])),
                        "parts": len(job_data["classified"].get("parts", [])),
                        "nc1": len(job_data["classified"].get("nc1", [])),
                        "dxf": len(job_data["classified"].get("dxf", [])),
                        "zeman_folders": len(job_data["classified"].get("zeman", [])),
                        "other": len(job_data["classified"].get("other", []))
                    },
                    "distribution": job_data.get("distribution_result", {}).get("count_data", {})
                },
                "logs": log_summary,
                "log_file": str(log_file_path) if log_file_path else None,
                "status": logger.status
            }

        except Exception as e:
            logger.append_log_action(f"Pipeline failed: {str(e)}", "Error")
            logger.set_status_bar(f"Processing failed: {str(e)}")

            # Cleanup on failure
            try:
                if job_data.get("temp_dir"):
                    facade.cleanup_temp(job_data, logger)
            except:
                pass

            # Summarize logs for error response too
            all_logs = logger.as_dict()["entries"]
            log_summary = {
                "total_entries": len(all_logs),
                "errors": [log for log in all_logs if log["level"] == "Error"],
                "warnings": [log for log in all_logs if log["level"] == "Warning"],
                "recent_actions": all_logs[-10:] if len(all_logs) > 10 else all_logs  # Last 10 entries
            }

            # failure response
            return {
                "success": False,
                "error": str(e),
                "job_data": {
                    "job_number": job_data.get("job_number"),
                    "transmittal_number": job_data.get("transmittal_number"),
                    "transmittal_type": job_data.get("transmittal_type")
                },
                "logs": log_summary,
                "status": logger.status
            }