"""
Estimator Module

Provides PDF classification operations for the agent.
Requires 'estimator' specialty permission.
"""
from src.modules.base import BaseModule
from src.modules.estimator.tool_classify_pdf import classify_and_breakout
from src.modules.estimator.config import DEFAULT_OUTPUT_PATH


class EstimatorModule(BaseModule):
    """Estimator operations — construction plan classification and breakout"""

    name = 'estimator'

    # =========================================================================
    # Classification
    # =========================================================================

    async def classify_and_breakout(
            self,
            pdf_path: str,
            anthropic_api_key: str,
            output_path: str | None = None,
            breakout_filter: str = 'all' ) -> dict:
        """
        Classify a construction plan PDF and split into per-discipline files.

        Args:
            pdf_path: Full path to the PDF file
            anthropic_api_key: Anthropic API key for AI classification
            output_path: Directory for breakout PDFs
            breakout_filter: 'all' for every discipline, 'standard' for common disciplines only
        """

        try:
            result = classify_and_breakout(
                pdf_path=pdf_path,
                anthropic_api_key=anthropic_api_key,
                output_path=output_path,
                breakout_filter=breakout_filter,
            )

            if result.get("success"):
                return self._success(**result)
            else:
                return self._error(result.get("error", "Classification/breakout failed"))

        except FileNotFoundError as e:
            return self._error(f"PDF not found: {e}")
        except Exception as e:
            return self._error(f"Classification/breakout failed: {e}")

    async def get_default_output_path(self) -> dict:
        """Get the default output path for classification breakout files"""

        return self._success(
            path=str(DEFAULT_OUTPUT_PATH),
            exists=DEFAULT_OUTPUT_PATH.exists(),
        )
