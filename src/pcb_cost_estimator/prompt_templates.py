"""
Prompt template management with versioning.

Loads and manages versioned LLM prompt templates from YAML configuration files.
"""

import logging
from pathlib import Path
from typing import Dict, Optional

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class PromptTemplate(BaseModel):
    """Versioned prompt template."""

    version: str
    description: str
    system_prompt: str
    user_prompt_template: str
    created: Optional[str] = None
    updated: Optional[str] = None
    examples: Optional[list] = None


class PromptTemplateManager:
    """Manages loading and caching of prompt templates."""

    def __init__(self, templates_dir: Optional[Path] = None):
        """
        Initialize the prompt template manager.

        Args:
            templates_dir: Directory containing prompt template YAML files.
                          Defaults to config/llm_prompts in the package.
        """
        if templates_dir is None:
            # Default to package config directory
            package_root = Path(__file__).parent.parent.parent
            templates_dir = package_root / "config" / "llm_prompts"

        self.templates_dir = Path(templates_dir)
        self._cache: Dict[str, PromptTemplate] = {}

        if not self.templates_dir.exists():
            logger.warning(
                f"Prompt templates directory not found: {self.templates_dir}. "
                f"LLM enrichment may not work correctly."
            )

    def load_template(self, template_name: str, version: str = "v1") -> Optional[PromptTemplate]:
        """
        Load a prompt template by name and version.

        Args:
            template_name: Name of the template (e.g., 'component_classification')
            version: Template version (default: 'v1')

        Returns:
            PromptTemplate if found, None otherwise
        """
        cache_key = f"{template_name}_{version}"

        # Check cache
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Load from file
        template_file = self.templates_dir / f"{template_name}_{version}.yaml"

        if not template_file.exists():
            logger.error(f"Prompt template not found: {template_file}")
            return None

        try:
            with open(template_file, 'r') as f:
                data = yaml.safe_load(f)

            template = PromptTemplate(**data)
            self._cache[cache_key] = template

            logger.debug(
                f"Loaded prompt template: {template_name} v{template.version} "
                f"from {template_file}"
            )

            return template

        except Exception as e:
            logger.error(f"Failed to load prompt template from {template_file}: {e}")
            return None

    def render_template(
        self,
        template_name: str,
        variables: Dict[str, any],
        version: str = "v1"
    ) -> Optional[tuple[str, str]]:
        """
        Load and render a prompt template with variables.

        Args:
            template_name: Name of the template
            variables: Dictionary of variables to substitute
            version: Template version

        Returns:
            Tuple of (system_prompt, user_prompt) if successful, None otherwise
        """
        template = self.load_template(template_name, version)
        if not template:
            return None

        try:
            # Render user prompt with variables
            user_prompt = template.user_prompt_template.format(**variables)
            system_prompt = template.system_prompt

            return system_prompt, user_prompt

        except KeyError as e:
            logger.error(
                f"Missing required variable for template {template_name}: {e}"
            )
            return None
        except Exception as e:
            logger.error(f"Failed to render template {template_name}: {e}")
            return None

    def list_templates(self) -> list[str]:
        """List all available template names."""
        if not self.templates_dir.exists():
            return []

        templates = []
        for file in self.templates_dir.glob("*.yaml"):
            # Extract template name (remove version suffix)
            name = file.stem
            if "_v" in name:
                name = name.rsplit("_v", 1)[0]
            if name not in templates:
                templates.append(name)

        return sorted(templates)

    def clear_cache(self) -> None:
        """Clear the template cache."""
        self._cache.clear()
        logger.debug("Prompt template cache cleared")


# Global template manager instance
_template_manager: Optional[PromptTemplateManager] = None


def get_template_manager(templates_dir: Optional[Path] = None) -> PromptTemplateManager:
    """
    Get or create the global template manager instance.

    Args:
        templates_dir: Optional custom templates directory

    Returns:
        PromptTemplateManager instance
    """
    global _template_manager

    if _template_manager is None or templates_dir is not None:
        _template_manager = PromptTemplateManager(templates_dir)

    return _template_manager
