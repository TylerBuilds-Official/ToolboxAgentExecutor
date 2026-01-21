"""
Document Creation Module

Provides document generation capabilities for the agent.
Internal tools for AI orchestration - callable through natural language only.
"""
from typing import Optional, Any
from src.modules.base import BaseModule
from src.modules.document_creation.creators.html_creator import HtmlCreator
from src.modules.document_creation.config import DEFAULT_OUTPUT_PATH


class DocumentCreationModule(BaseModule):
    """
    Document creation operations module.
    
    Handles generation of:
    - HTML reports (template-based and raw)
    - Excel exports (future)
    - PDF documents (future)
    
    Note: These are internal AI tools, not exposed in toolbox UI.
    """
    name = 'document_creation'
    
    def __init__(self):
        self._html_creator = None
    
    @property
    def html_creator(self) -> HtmlCreator:
        """Lazy-load HTML creator."""
        if self._html_creator is None:
            self._html_creator = HtmlCreator()
        return self._html_creator

    # =========================================================================
    # HTML Report Actions
    # =========================================================================

    async def create_html_report(
        self,
        template_name: str,
        data: Optional[dict[str, Any]] = None,
        title: Optional[str] = None,
        output_filename: Optional[str] = None
    ) -> dict:
        """
        Create an HTML report from a template with injected data.
        
        Args:
            template_name: Template file name (e.g., "base_report.html")
            data: Dictionary of data to inject into the template (optional, defaults to {})
            title: Report title (optional, can also be in data)
            output_filename: Output filename (optional, auto-generated if not provided)
            
        Returns:
            Dict with success status, file path, and metadata
        """
        try:
            # Default data to empty dict
            if data is None:
                data = {}
            
            result = self.html_creator.create_from_template(
                template_name=template_name,
                data=data,
                title=title,
                output_filename=output_filename
            )
            
            if result.get("success"):
                return self._success(**result)
            else:
                return self._error(result.get("error", "Failed to create report"))
                
        except Exception as e:
            return self._error(f"Report creation failed: {e}")

    async def save_raw_html(
        self,
        content: str,
        output_filename: str
    ) -> dict:
        """
        Save raw HTML content to a file.
        
        Use when the AI generates complete HTML content directly.
        
        Args:
            content: Complete HTML string
            output_filename: Output filename (required)
            
        Returns:
            Dict with success status and file path
        """
        try:
            result = self.html_creator.save_raw_html(
                content=content,
                output_filename=output_filename
            )
            
            if result.get("success"):
                return self._success(**result)
            else:
                return self._error(result.get("error", "Failed to save HTML"))
                
        except Exception as e:
            return self._error(f"Save failed: {e}")

    async def list_report_templates(self) -> dict:
        """
        List available HTML report templates and include skill documentation.
        
        Returns:
            Dict with list of templates, descriptions, and skill guide for data formatting
        """
        try:
            result = self.html_creator.list_templates()
            
            if result.get("success"):
                return self._success(**result)
            else:
                return self._error(result.get("error", "Failed to list templates"))
                
        except Exception as e:
            return self._error(f"List failed: {e}")

    async def get_report_skill(self) -> dict:
        """
        Get the HTML report skill documentation.
        
        AI can read this to understand how to use report creation effectively.
        
        Returns:
            Dict with skill markdown content
        """
        try:
            result = self.html_creator.get_skill_content()
            
            if result.get("success"):
                return self._success(**result)
            else:
                return self._error(result.get("error", "Skill not found"))
                
        except Exception as e:
            return self._error(f"Failed to get skill: {e}")

    async def get_default_output_path(self) -> dict:
        """
        Get the default output path for documents.
        
        Returns:
            Dict with path and whether it exists
        """
        return self._success(
            path=str(DEFAULT_OUTPUT_PATH),
            exists=DEFAULT_OUTPUT_PATH.exists()
        )
