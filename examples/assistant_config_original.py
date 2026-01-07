#!/usr/bin/env python3
"""
Assistant Configuration Module

Provides configuration dataclasses for Langdock inline assistants.
All settings are versioned in Git for Single Source of Truth.
"""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class AssistantConfig:
    """
    Configuration for Langdock Inline Assistant

    This configuration is passed per API request, allowing full control
    over model, temperature, and instructions without pre-created assistants.

    Attributes:
        model: LLM model to use (default: gpt-4o for vision/PDF support)
        temperature: Sampling temperature 0-1 (default: 0 for deterministic)
        system_prompt: System-level instructions for the assistant
        name: Display name for the assistant (for logging/debugging)
    """
    model: str = "gpt-4o"
    temperature: float = 0.0  # Deterministic by default
    system_prompt: str = """Befolge präzise die Anweisungen im User Prompt.
Antworte ausschließlich im angeforderten JSON-Format.
Keine zusätzlichen Erklärungen außerhalb des JSON."""
    name: str = "Invoice Analysis"

    def __post_init__(self):
        """Validate configuration parameters"""
        if not 0 <= self.temperature <= 1:
            raise ValueError(f"Temperature must be between 0 and 1, got {self.temperature}")

        if not self.model:
            raise ValueError("Model cannot be empty")

        if len(self.name) > 64:
            raise ValueError(f"Name too long (max 64 chars): {len(self.name)}")

        if len(self.system_prompt) > 16384:
            raise ValueError(f"System prompt too long (max 16384 chars): {len(self.system_prompt)}")

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert config to API-compatible dictionary

        Returns:
            Dictionary with keys: name, model, temperature, instructions
        """
        return {
            "name": self.name,
            "model": self.model,
            "temperature": self.temperature,
            "instructions": self.system_prompt
        }

    def __repr__(self) -> str:
        """Human-readable representation for logging"""
        return f"AssistantConfig(model={self.model}, temp={self.temperature}, name='{self.name}')"


# Pre-defined configurations for common use cases

DETERMINISTIC_CONFIG = AssistantConfig(
    name="Invoice Analysis (Deterministic)",
    model="gpt-4o",
    temperature=0.0,
    system_prompt="""Befolge präzise die Anweisungen im User Prompt.
Antworte ausschließlich im angeforderten JSON-Format.
Keine zusätzlichen Erklärungen außerhalb des JSON."""
)

CREATIVE_CONFIG = AssistantConfig(
    name="Invoice Analysis (Creative)",
    model="gpt-4o",
    temperature=0.7,
    system_prompt="""Befolge die Anweisungen im User Prompt.
Antworte im angeforderten JSON-Format.
Bei Unklarheiten nutze dein bestes Urteilsvermögen."""
)

BALANCED_CONFIG = AssistantConfig(
    name="Invoice Analysis (Balanced)",
    model="gpt-4o",
    temperature=0.3,
    system_prompt="""Befolge präzise die Anweisungen im User Prompt.
Antworte ausschließlich im angeforderten JSON-Format.
Keine zusätzlichen Erklärungen außerhalb des JSON."""
)

# OCR-optimized configurations for Two-Pass OCR testing
# These configs are specifically tuned for document OCR and table extraction

OCR_GPT4O_CONFIG = AssistantConfig(
    name="OCR Extraction (GPT-4o)",
    model="gpt-4o",
    temperature=0.0,
    system_prompt="""Extrahiere ALLEN sichtbaren Text präzise aus dem Dokument.
Befolge exakt die Anweisungen im User Prompt.
Antworte ausschließlich im angeforderten Format."""
)

OCR_GPT41_CONFIG = AssistantConfig(
    name="OCR Extraction (GPT-4.1)",
    model="gpt-4.1",
    temperature=0.0,
    system_prompt="""Extrahiere ALLEN sichtbaren Text präzise aus dem Dokument.
Befolge exakt die Anweisungen im User Prompt.
Antworte ausschließlich im angeforderten Format."""
)

OCR_CLAUDE45_CONFIG = AssistantConfig(
    name="OCR Extraction (Claude Sonnet 4.5)",
    model="claude-sonnet-4-5@20250929",
    temperature=0.0,
    system_prompt="""Extrahiere ALLEN sichtbaren Text präzise aus dem Dokument.
Befolge exakt die Anweisungen im User Prompt.
Antworte ausschließlich im angeforderten Format."""
)

OCR_GEMINI25_CONFIG = AssistantConfig(
    name="OCR Extraction (Gemini 2.5 Pro)",
    model="gemini-2.5-pro",
    temperature=0.0,
    system_prompt="""Extrahiere ALLEN sichtbaren Text präzise aus dem Dokument.
Befolge exakt die Anweisungen im User Prompt.
Antworte ausschließlich im angeforderten Format."""
)

OCR_GPT5_CONFIG = AssistantConfig(
    name="OCR Extraction (GPT-5)",
    model="gpt-5",
    temperature=0.0,
    system_prompt="""Extrahiere ALLEN sichtbaren Text präzise aus dem Dokument.
Befolge exakt die Anweisungen im User Prompt.
Antworte ausschließlich im angeforderten Format."""
)

# Default OCR config (based on test results - Claude Sonnet 4.5 performs best)
# Test results (2025-10-13): Claude extracted 9 items vs 3-4 for others, correctly detected Bauleistung
OCR_DEFAULT_CONFIG = OCR_CLAUDE45_CONFIG


def get_config(temperature: float = 0.0, name: str = None) -> AssistantConfig:
    """
    Factory function to create custom config

    Args:
        temperature: Sampling temperature (0-1)
        name: Optional custom name

    Returns:
        AssistantConfig instance
    """
    return AssistantConfig(
        temperature=temperature,
        name=name or f"Invoice Analysis (temp={temperature})"
    )


def get_config_by_model_name(model: str, config_type: str = "analysis") -> AssistantConfig:
    """
    Get AssistantConfig by model name string.

    Maps model names from frontend to appropriate AssistantConfig objects.

    Args:
        model: Model name (e.g., "gpt-4o", "claude-sonnet-4-5@20250929")
        config_type: "analysis" for invoice analysis or "ocr" for OCR extraction

    Returns:
        AssistantConfig instance

    Raises:
        ValueError: If model name is unknown
    """
    # Map model names to OCR configs
    ocr_configs = {
        "gpt-4o": OCR_GPT4O_CONFIG,
        "gpt-4.1": OCR_GPT41_CONFIG,
        "claude-sonnet-4-5@20250929": OCR_CLAUDE45_CONFIG,
        "gemini-2.5-pro": OCR_GEMINI25_CONFIG,
        "gpt-5": OCR_GPT5_CONFIG
    }

    # For analysis configs, use deterministic config with specified model
    if config_type == "analysis":
        if model in ocr_configs:
            # Reuse OCR config but change name to indicate analysis purpose
            config = ocr_configs[model]
            return AssistantConfig(
                model=config.model,
                temperature=0.0,  # Deterministic for analysis
                system_prompt=DETERMINISTIC_CONFIG.system_prompt,
                name=f"Invoice Analysis ({model})"
            )
        else:
            raise ValueError(f"Unknown model for analysis: {model}")

    # For OCR configs, return pre-configured OCR config
    elif config_type == "ocr":
        if model in ocr_configs:
            return ocr_configs[model]
        else:
            raise ValueError(f"Unknown model for OCR: {model}")

    else:
        raise ValueError(f"Unknown config_type: {config_type}. Use 'analysis' or 'ocr'.")
