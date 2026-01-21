"""
HTML Report Creator

Creates HTML reports using Jinja2 templating.
Supports both template-based and raw HTML generation.
"""
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.modules.document_creation.config import (
    TEMPLATES_PATH,
    SKILLS_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_REPORT_TITLE,
)


class HtmlCreator:
    """
    Creates HTML documents from templates or raw content.
    
    Usage:
        creator = HtmlCreator()
        
        # From template
        path = creator.create_from_template(
            template_name="base_report.html",
            data={"title": "My Report", "items": [...]},
            output_filename="my_report.html"
        )
        
        # Raw HTML
        path = creator.save_raw_html(
            content="<html>...</html>",
            output_filename="custom.html"
        )
    """
    
    def __init__(self, output_path: Optional[Path] = None):
        """
        Initialize the HTML creator.
        
        Args:
            output_path: Directory for output files. Defaults to config DEFAULT_OUTPUT_PATH.
        """
        self.output_path = Path(output_path) if output_path else DEFAULT_OUTPUT_PATH
        self.templates_path = TEMPLATES_PATH / "reports"
        
        # Ensure directories exist
        self.output_path.mkdir(parents=True, exist_ok=True)
        
        # Set up Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_path)),
            autoescape=select_autoescape(['html', 'xml'])
        )
        
        # Add custom filters
        self.env.filters['format_date'] = self._format_date
        self.env.filters['format_number'] = self._format_number
    
    # =========================================================================
    # Public Methods
    # =========================================================================
    
    def create_from_template(
        self,
        template_name: str,
        data: dict[str, Any],
        output_filename: Optional[str] = None,
        title: Optional[str] = None
    ) -> dict:
        """
        Create an HTML report from a template.
        
        Args:
            template_name: Name of template file (e.g., "base_report.html")
            data: Dictionary of data to inject into template
            output_filename: Output filename. Auto-generated if not provided.
            title: Report title. Uses default if not provided.
            
        Returns:
            Dict with success status and file path
        """
        try:
            # Defensive: ensure data is a dict
            if data is None:
                data = {}
            if not isinstance(data, dict):
                return {
                    "success": False,
                    "error": f"Data must be a dictionary, got {type(data).__name__}"
                }
            
            # Sanitize data - ensure lists are actually lists, not methods
            sanitized_data = self._sanitize_data(data)
            
            # Load template
            template = self.env.get_template(template_name)
            
            # Build context - only spread sanitized data
            context = {
                "title": title or sanitized_data.get("title", DEFAULT_REPORT_TITLE),
                "generated_at": datetime.now(),
                "data": sanitized_data,
                **sanitized_data  # Also spread data at top level for convenience
            }
            
            # Render
            html_content = template.render(**context)
            
            # Generate filename if not provided
            if not output_filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                base_name = template_name.replace(".html", "")
                output_filename = f"{base_name}_{timestamp}.html"
            
            # Ensure .html extension
            if not output_filename.endswith(".html"):
                output_filename += ".html"
            
            # Save
            output_file = self.output_path / output_filename
            output_file.write_text(html_content, encoding="utf-8")
            
            return {
                "success": True,
                "file_path": str(output_file),
                "filename": output_filename,
                "template_used": template_name
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def save_raw_html(
        self,
        content: str,
        output_filename: str
    ) -> dict:
        """
        Save raw HTML content directly to a file.
        
        Use this when the AI generates complete HTML content.
        
        Args:
            content: Complete HTML string
            output_filename: Output filename
            
        Returns:
            Dict with success status and file path
        """
        try:
            # Ensure .html extension
            if not output_filename.endswith(".html"):
                output_filename += ".html"
            
            output_file = self.output_path / output_filename
            output_file.write_text(content, encoding="utf-8")
            
            return {
                "success": True,
                "file_path": str(output_file),
                "filename": output_filename
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def list_templates(self) -> dict:
        """
        List available HTML report templates and include skill documentation.
        
        Returns:
            Dict with list of template names, descriptions, and skill guide
        """
        try:
            templates = []
            
            if self.templates_path.exists():
                for template_file in self.templates_path.glob("*.html"):
                    # Read first few lines to extract description comment
                    content = template_file.read_text(encoding="utf-8")
                    description = self._extract_template_description(content)
                    
                    templates.append({
                        "name": template_file.name,
                        "description": description
                    })
            
            # Also include the skill content for data formatting guidance
            skill_content = None
            skill_result = self.get_skill_content()
            if skill_result.get("success"):
                skill_content = skill_result.get("skill_content")
            
            return {
                "success": True,
                "templates_path": str(self.templates_path),
                "templates": templates,
                "count": len(templates),
                "skill_guide": skill_content
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_skill_content(self) -> dict:
        """
        Get the HTML report skill documentation for AI guidance.
        
        Returns:
            Dict with skill content
        """
        try:
            skill_file = SKILLS_PATH / "html_report_skill.md"
            
            if skill_file.exists():
                content = skill_file.read_text(encoding="utf-8")
                return {
                    "success": True,
                    "skill_content": content
                }
            else:
                return {
                    "success": False,
                    "error": f"Skill file not found: {skill_file}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    # =========================================================================
    # Private Helpers
    # =========================================================================
    
    def _sanitize_data(self, data: Any) -> Any:
        """
        Recursively sanitize data to ensure it's safe for Jinja2 templates.
        
        Handles:
        - Converting non-dict/list/primitive types to strings
        - Filtering out callable objects (methods, functions)
        - Ensuring lists are actually lists
        """
        if data is None:
            return None
        
        # Handle callables (methods, functions) - convert to string representation
        if callable(data):
            return f"<callable: {type(data).__name__}>"
        
        # Handle dictionaries
        if isinstance(data, dict):
            return {k: self._sanitize_data(v) for k, v in data.items()}
        
        # Handle lists/tuples
        if isinstance(data, (list, tuple)):
            return [self._sanitize_data(item) for item in data]
        
        # Handle primitives (str, int, float, bool)
        if isinstance(data, (str, int, float, bool)):
            return data
        
        # Handle datetime objects
        if isinstance(data, datetime):
            return data
        
        # Anything else - convert to string
        try:
            return str(data)
        except Exception:
            return f"<unconvertible: {type(data).__name__}>"
    
    def _extract_template_description(self, content: str) -> str:
        """Extract description from HTML comment at top of template."""
        import re
        match = re.search(r'<!--\s*Description:\s*(.+?)\s*-->', content, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return "No description available"
    
    @staticmethod
    def _format_date(value, format_str: str = "%m/%d/%Y") -> str:
        """Jinja2 filter for date formatting."""
        if isinstance(value, datetime):
            return value.strftime(format_str)
        return str(value)
    
    @staticmethod
    def _format_number(value, decimals: int = 2) -> str:
        """Jinja2 filter for number formatting with commas."""
        try:
            return f"{float(value):,.{decimals}f}"
        except (ValueError, TypeError):
            return str(value)
