#!/usr/bin/env python3
"""
Langdock Inline Assistant Client

Client for Langdock API using inline assistant creation per request.
Provides Single Source of Truth for all configuration in code (Git).
"""
import os
import requests
import json
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from assistant_config import AssistantConfig, DETERMINISTIC_CONFIG
from json_repair import safe_json_parse

load_dotenv()


class LangdockInlineClient:
    """
    Client for Langdock API using inline assistants

    Unlike the original LangdockClient which uses pre-created assistants,
    this client creates assistants inline per request, allowing full control
    over temperature, model, and instructions.

    Benefits:
    - Single Source of Truth: All config in Git
    - Deterministic: temperature=0 by default
    - Flexible: Easy A/B testing with different configs
    - Transparent: Config visible in code, not hidden in Web UI
    """

    def __init__(self, config: Optional[AssistantConfig] = None):
        """
        Initialize client with assistant configuration

        Args:
            config: AssistantConfig instance (defaults to DETERMINISTIC_CONFIG)
        """
        self.config = config or DETERMINISTIC_CONFIG
        self.api_key = os.getenv('LANGDOCK_API_KEY')
        self.upload_url = os.getenv('LANGDOCK_UPLOAD_URL')
        self.completions_url = "https://api.langdock.com/assistant/v1/chat/completions"

        if not self.api_key:
            raise ValueError("LANGDOCK_API_KEY not found in environment")

        if not self.upload_url:
            raise ValueError("LANGDOCK_UPLOAD_URL not found in environment")

    def upload_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Upload a PDF file to Langdock

        Args:
            pdf_path: Path to PDF file

        Returns:
            Response with attachmentId

        Raises:
            FileNotFoundError: If PDF doesn't exist
            Exception: On upload failure
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        with open(pdf_path, 'rb') as pdf_file:
            files = {'file': (pdf_path.name, pdf_file, 'application/pdf')}
            response = requests.post(self.upload_url, headers=headers, files=files)

        if response.status_code != 200:
            raise Exception(f"Upload failed: {response.status_code} - {response.text}")

        return response.json()

    def analyze_invoice(
        self,
        attachment_id: str,
        prompt: str,
        timeout: int = 120
    ) -> Dict[str, Any]:
        """
        Analyze invoice using inline assistant

        Creates assistant inline with configured temperature/model,
        then sends prompt with attachment for analysis.

        Args:
            attachment_id: ID from upload response
            prompt: Analysis prompt (user message)
            timeout: Request timeout in seconds

        Returns:
            Analysis result as JSON

        Raises:
            Exception: On API failure
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Create inline assistant with our config
        payload = {
            "assistant": self.config.to_dict(),
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "attachmentIds": [attachment_id]
                }
            ]
        }

        response = requests.post(
            self.completions_url,
            headers=headers,
            json=payload,
            timeout=timeout
        )

        if response.status_code != 200:
            raise Exception(
                f"Analysis failed: {response.status_code} - {response.text}"
            )

        return response.json()

    def process_pdf(
        self,
        pdf_path: Path,
        prompt: str,
        timeout: int = 120
    ) -> Dict[str, Any]:
        """
        Complete workflow: upload PDF and analyze

        Args:
            pdf_path: Path to PDF file
            prompt: Analysis prompt
            timeout: Request timeout in seconds

        Returns:
            Dict with success, data, raw_response, retry_metadata

        Raises:
            Exception: On failure
        """
        # Upload PDF
        upload_result = self.upload_pdf(pdf_path)
        attachment_id = upload_result['attachmentId']

        # Analyze
        analysis_result = self.analyze_invoice(attachment_id, prompt, timeout)

        # Return in same format as BatchLangdockClient for compatibility
        return {
            "success": True,
            "data": self._extract_json_from_response(analysis_result),
            "raw_response": analysis_result,
            "retry_metadata": {
                "attempts": 1,
                "total_duration_seconds": 0,  # Not tracked in simple client
                "pdf_size_mb": pdf_path.stat().st_size / (1024 * 1024)
            }
        }

    def _make_api_call(
        self,
        pdf_path: Path,
        prompt: str,
        request_timeout: int = 120
    ) -> Dict[str, Any]:
        """
        Core API call abstraction: upload PDF and analyze

        This is the fundamental building block used by TwoPassOCRProcessor.
        It handles upload, analysis, and basic error handling.

        Args:
            pdf_path: Path to PDF file
            prompt: Analysis prompt
            request_timeout: Timeout in seconds (default: 120)

        Returns:
            Raw API response dictionary

        Raises:
            Exception: On API failure
        """
        # Step 1: Upload PDF
        upload_result = self.upload_pdf(pdf_path)
        attachment_id = upload_result['attachmentId']

        # Step 2: Analyze with prompt
        analysis_result = self.analyze_invoice(attachment_id, prompt, timeout=request_timeout)

        return analysis_result

    def extract_json_from_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract JSON data from API response (public method for TwoPassOCRProcessor)

        The response has nested structure:
        result -> messages -> content -> text (JSON string)

        Args:
            response: Raw API response

        Returns:
            Parsed JSON data
        """
        return self._extract_json_from_response(response)

    def _extract_json_from_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract JSON data from API response (internal method)

        The response has nested structure:
        result -> messages -> content -> text (JSON string)

        Args:
            response: Raw API response

        Returns:
            Parsed JSON data
        """
        if 'result' not in response:
            raise ValueError("No 'result' in response")

        # Find assistant message with text content (iterate backwards to get final response)
        # Claude returns: [tool-call assistant, tool result, final assistant with JSON]
        for message in reversed(response['result']):
            if message.get('role') == 'assistant':
                content = message.get('content', [])

                # Handle both list and string content
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    # Find text content item
                    text = None
                    for content_item in content:
                        if isinstance(content_item, dict) and content_item.get('type') == 'text':
                            text = content_item.get('text', '')
                            break
                        elif isinstance(content_item, str):
                            text = content_item
                            break

                    if text is None:
                        continue
                else:
                    continue

                # Remove markdown code blocks if present
                if '```json' in text:
                    text = text.split('```json')[1].split('```')[0].strip()
                elif '```' in text:
                    text = text.split('```')[1].split('```')[0].strip()

                # Parse JSON with repair (Issue #3 - Priority 1)
                try:
                    data, was_repaired = safe_json_parse(text, attempt_repair=True)
                    if was_repaired:
                        print(f"✅ JSON successfully repaired in inline client")
                    return data
                except json.JSONDecodeError:
                    # Fallback: Try to find JSON object in text
                    json_start = text.find('{')
                    json_end = text.rfind('}') + 1
                    if json_start != -1 and json_end > json_start:
                        data, was_repaired = safe_json_parse(text[json_start:json_end], attempt_repair=True)
                        if was_repaired:
                            print(f"✅ JSON successfully repaired (extracted bounds) in inline client")
                        return data
                    raise

        raise ValueError("No text content found in assistant response")


def main():
    """Test the inline client with a sample PDF"""
    from assistant_config import DETERMINISTIC_CONFIG, CREATIVE_CONFIG

    # Load v8 prompt
    prompt_path = Path('poc/prompt_baupruefung_v8_wartung_fix.md')
    if not prompt_path.exists():
        print(f"❌ Prompt file not found: {prompt_path}")
        return

    with open(prompt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract prompt from markdown
    start_marker = '```text\n'
    start_idx = content.find(start_marker)
    if start_idx == -1:
        start_marker = '```\n'
        start_idx = content.find(start_marker)

    start_idx += len(start_marker)
    end_idx = content.find('\n```', start_idx)
    prompt = content[start_idx:end_idx]

    print(f"✅ Loaded prompt v8 ({len(prompt)} characters)")

    # Test PDF
    pdf_path = Path('poc/pdfs/13b Rechnung, 19% wäre richtig/LANSING Metallbau GMBH & CO. KG - RNr_ 40254.pdf')
    if not pdf_path.exists():
        print(f"❌ PDF not found: {pdf_path}")
        return

    # Test with deterministic config
    print(f"\n🔬 Testing with {DETERMINISTIC_CONFIG}")
    client = LangdockInlineClient(config=DETERMINISTIC_CONFIG)

    try:
        print(f"🔍 Processing: {pdf_path.name}")
        result = client.process_pdf(pdf_path, prompt)

        print(f"✅ Success!")
        print(f"   Config: {client.config}")
        print(f"   Items: {len(result['data']['line_items_analysis']['items'])}")

        # Show line items
        for i, item in enumerate(result['data']['line_items_analysis']['items'], 1):
            is_bau = item['is_bauleistung']
            status = "❌" if is_bau else "✅"
            print(f"   {i}. {status} is_bauleistung={is_bau}")

        # Save result
        output_file = Path('test_inline_client_result.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"💾 Saved: {output_file}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
