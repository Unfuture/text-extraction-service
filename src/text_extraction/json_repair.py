#!/usr/bin/env python3
"""
JSON Repair Module - Fix common LLM JSON generation errors

Issue #3: 4 PDFs (9.5%) failing with JSON parsing errors
Error pattern: Expecting ',' delimiter at specific line/column positions

This module attempts to repair common JSON syntax errors before parsing:
1. Missing commas between object properties
2. Trailing commas before closing braces
3. Missing quotes around property names
4. Unescaped quotes in string values
"""

import json
import re
import logging
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)


def repair_json_text(text: str, error: Optional[json.JSONDecodeError] = None) -> str:
    """
    Attempt to repair JSON text with common LLM generation errors

    Args:
        text: Raw JSON text that failed to parse
        error: Optional JSONDecodeError with line/column information

    Returns:
        Repaired JSON text (or original if repair not possible)
    """
    original_text = text

    # Strategy 1: Fix missing commas based on error position
    if error and "Expecting ',' delimiter" in str(error):
        text = _fix_missing_comma_at_position(text, error)
        try:
            json.loads(text)
            logger.info("✅ JSON repaired: Missing comma fixed at error position")
            return text
        except json.JSONDecodeError:
            text = original_text  # Revert if repair didn't work

    # Strategy 2: Fix missing commas between object properties (pattern matching)
    text = _fix_missing_commas_pattern(text)
    try:
        json.loads(text)
        logger.info("✅ JSON repaired: Missing commas fixed via pattern matching")
        return text
    except json.JSONDecodeError:
        text = original_text  # Revert

    # Strategy 3: Remove trailing commas
    text = _remove_trailing_commas(text)
    try:
        json.loads(text)
        logger.info("✅ JSON repaired: Trailing commas removed")
        return text
    except json.JSONDecodeError:
        text = original_text  # Revert

    # Strategy 4: Fix unescaped quotes
    text = _fix_unescaped_quotes(text)
    try:
        json.loads(text)
        logger.info("✅ JSON repaired: Unescaped quotes fixed")
        return text
    except json.JSONDecodeError:
        text = original_text  # Revert

    # If all strategies fail, return original
    logger.warning("⚠️ JSON repair failed: All strategies exhausted")
    return original_text


def _fix_missing_comma_at_position(text: str, error: json.JSONDecodeError) -> str:
    """
    Fix missing comma at the specific line/column from JSONDecodeError

    Example error: Expecting ',' delimiter: line 38 column 168 (char 1298)
    """
    try:
        # Get error position
        line_num = error.lineno
        col_num = error.colno

        # Split into lines
        lines = text.split('\n')

        # Validate line number
        if line_num < 1 or line_num > len(lines):
            logger.warning(f"Invalid line number {line_num} for text with {len(lines)} lines")
            return text

        # Get the problematic line (1-indexed)
        line_idx = line_num - 1
        problem_line = lines[line_idx]

        # Insert comma at the position
        # Usually the error points to where the comma SHOULD be
        # We need to find the previous character that's not whitespace
        insert_pos = col_num - 1

        # Find the last non-whitespace character before insert_pos
        for i in range(insert_pos - 1, -1, -1):
            if i < len(problem_line) and problem_line[i] not in (' ', '\t'):
                # Insert comma after this character
                fixed_line = problem_line[:i+1] + ',' + problem_line[i+1:]
                lines[line_idx] = fixed_line
                logger.debug(f"Inserted comma at line {line_num}, position {i+1}")
                return '\n'.join(lines)

        # Fallback: Insert at column position
        if insert_pos <= len(problem_line):
            fixed_line = problem_line[:insert_pos] + ',' + problem_line[insert_pos:]
            lines[line_idx] = fixed_line
            logger.debug(f"Inserted comma at line {line_num}, column {col_num}")
            return '\n'.join(lines)

    except Exception as e:
        logger.warning(f"Failed to fix comma at position: {e}")

    return text


def _fix_missing_commas_pattern(text: str) -> str:
    """
    Fix missing commas between object properties using pattern matching

    Pattern: }\n\s*"property" (missing comma after })
    Fix: },\n\s*"property"
    """
    # Pattern 1: Missing comma after closing brace before property
    # Example: }\n            "next_property"
    text = re.sub(
        r'(\})\s*\n\s*("[\w_]+"\s*:)',
        r'\1,\n            \2',
        text
    )

    # Pattern 2: Missing comma after closing bracket before property
    # Example: ]\n            "next_property"
    text = re.sub(
        r'(\])\s*\n\s*("[\w_]+"\s*:)',
        r'\1,\n            \2',
        text
    )

    # Pattern 3: Missing comma after string value before property
    # Example: "value"\n            "next_property"
    text = re.sub(
        r'("\w+")\s*\n\s*("[\w_]+"\s*:)',
        r'\1,\n            \2',
        text
    )

    # Pattern 4: Missing comma after number value before property
    # Example: 123\n            "next_property"
    text = re.sub(
        r'(\d+)\s*\n\s*("[\w_]+"\s*:)',
        r'\1,\n            \2',
        text
    )

    # Pattern 5: Missing comma after boolean value before property
    # Example: true\n            "next_property"
    text = re.sub(
        r'\b(true|false|null)\b\s*\n\s*("[\w_]+"\s*:)',
        r'\1,\n            \2',
        text
    )

    return text


def _remove_trailing_commas(text: str) -> str:
    """
    Remove trailing commas before closing braces/brackets

    Example: {"key": "value",} → {"key": "value"}
    """
    # Remove comma before }
    text = re.sub(r',\s*\}', '}', text)

    # Remove comma before ]
    text = re.sub(r',\s*\]', ']', text)

    return text


def _fix_unescaped_quotes(text: str) -> str:
    """
    Attempt to fix unescaped quotes in string values

    This is conservative - only fixes obvious cases
    """
    # This is complex and risky - implement conservatively
    # For now, just return original text
    # TODO: Implement if needed based on actual error patterns
    return text


def safe_json_parse(text: str, attempt_repair: bool = True) -> Tuple[Dict[str, Any], bool]:
    """
    Safely parse JSON with optional repair attempt

    Args:
        text: JSON text to parse
        attempt_repair: If True, attempt repair on parse failure

    Returns:
        Tuple of (parsed_dict, was_repaired)

    Raises:
        json.JSONDecodeError: If parsing fails after all repair attempts
    """
    # Try normal parsing first
    try:
        data = json.loads(text)
        return data, False
    except json.JSONDecodeError as e:
        if not attempt_repair:
            raise

        # Attempt repair
        logger.info(f"JSON parse failed: {str(e)[:100]}")
        logger.info("Attempting JSON repair...")

        repaired_text = repair_json_text(text, e)

        # Try parsing repaired text
        try:
            data = json.loads(repaired_text)
            return data, True
        except json.JSONDecodeError as repair_error:
            # Repair failed, raise original error
            logger.error(f"JSON repair failed: {str(repair_error)[:100]}")
            raise e  # Raise original error, not repair error


def validate_invoice_json_structure(data: Dict[str, Any]) -> bool:
    """
    Validate that parsed JSON has expected invoice structure

    Expected structure (v10):
    {
        "supplier": {...},
        "amounts": {...},
        "document_flags": {...},
        "line_items": [...]
    }

    Returns:
        True if structure is valid, False otherwise
    """
    required_keys = ['supplier', 'amounts', 'document_flags', 'line_items']

    for key in required_keys:
        if key not in data:
            logger.warning(f"Invalid JSON structure: Missing required key '{key}'")
            return False

    # Validate line_items is a list
    if not isinstance(data['line_items'], list):
        logger.warning("Invalid JSON structure: 'line_items' must be a list")
        return False

    return True
