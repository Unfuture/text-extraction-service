#!/usr/bin/env python3
"""
TwoPassOCRProcessor - Advanced OCR handling for scanned PDFs
Implements a two-pass strategy for documents with poor text extraction
"""

import time
import atexit
import logging
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    import fitz  # PyMuPDF
except ImportError:
    raise ImportError(
        "PyMuPDF (fitz) is required for two-pass OCR processing. "
        "Install with: pip install pymupdf"
    )

from prompt_manager import PromptManager
from assistant_config import AssistantConfig, OCR_DEFAULT_CONFIG
from file_operations import extract_json_from_response
from pdf_type_detector import PDFTypeDetector, PDFType

logger = logging.getLogger(__name__)


class TwoPassOCRProcessor:
    """
    Advanced OCR processor using two-pass strategy for scanned PDFs

    Pass 1: Extract text from scanned pages using OCR-specific prompt
    Pass 2: Analyze full document with OCR context injected into prompt

    This approach significantly improves recognition rate for scanned documents
    while maintaining compatibility with normal PDFs.
    """

    def __init__(
        self,
        langdock_client,
        text_threshold: int = 10,
        ocr_model_config: Optional[AssistantConfig] = None,
        analysis_model_config: Optional[AssistantConfig] = None
    ):
        """
        Initialize TwoPassOCRProcessor

        Args:
            langdock_client: Instance of LangdockClient (or BatchLangdockClient)
                            Must have _make_api_call() method
            text_threshold: Minimum number of text lines to consider page as "readable"
                           Pages with fewer lines are treated as scanned. Default: 10
            ocr_model_config: AssistantConfig for OCR extraction (Pass 1)
                             If None, uses OCR_DEFAULT_CONFIG (Claude Sonnet 4.5)
            analysis_model_config: AssistantConfig for invoice analysis (Pass 2)
                                   If None, uses DETERMINISTIC_CONFIG (gpt-4o)

        Raises:
            ValueError: If client doesn't have required methods
        """
        if not hasattr(langdock_client, '_make_api_call'):
            raise ValueError(
                "langdock_client must have _make_api_call() method. "
                "This method should be added to BatchLangdockClient."
            )

        self.client = langdock_client
        self.text_threshold = text_threshold
        self.ocr_model_config = ocr_model_config or OCR_DEFAULT_CONFIG

        # Import config here to avoid circular dependency
        from assistant_config import DETERMINISTIC_CONFIG
        self.analysis_model_config = analysis_model_config or DETERMINISTIC_CONFIG

        # Create OCR-specific client with configured model
        # Import here to avoid circular dependency
        from langdock_inline_client import LangdockInlineClient
        self.ocr_client = LangdockInlineClient(config=self.ocr_model_config)
        self.analysis_client = LangdockInlineClient(config=self.analysis_model_config)

        # Initialize PDF Type Detector (Issue #4 Phase 0)
        self.pdf_detector = PDFTypeDetector(
            text_block_threshold=2,
            image_block_threshold=1
        )

        # Create secure temp directory
        self.temp_dir = Path(tempfile.mkdtemp(prefix="ocr_processor_"))
        logger.info(
            f"Initialized TwoPassOCRProcessor with temp dir: {self.temp_dir}",
            extra={
                'text_threshold': text_threshold,
                'ocr_model': self.ocr_model_config.model,
                'analysis_model': self.analysis_model_config.model
            }
        )

        # Register cleanup on exit
        atexit.register(self._cleanup_temp_dir)

    def _cleanup_temp_dir(self):
        """Clean up temporary directory on exit"""
        if self.temp_dir and self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temp directory: {self.temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp dir: {e}")

    def classify_pdf_type(self, pdf_path: Path):
        """
        Classify PDF type using block-type detection (Issue #4 Phase 0).

        Args:
            pdf_path: Path to PDF file

        Returns:
            PDFClassificationResult with type and page details
        """
        return self.pdf_detector.classify_pdf(pdf_path)

    def detect_scanned_pages(self, pdf_path: Path) -> List[int]:
        """
        Detect which pages are scanned (have minimal embedded text).

        UPDATED (Issue #4 Phase 0): Now uses block-type detection instead
        of line-counting heuristic.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of 1-indexed page numbers that are scanned (e.g., [1, 3, 5])

        Raises:
            FileNotFoundError: If PDF doesn't exist
            Exception: If PDF cannot be opened
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        logger.info(
            f"Detecting scanned pages in: {pdf_path.name} (using block-type detection)",
            extra={'pdf_path': str(pdf_path)}
        )

        try:
            # NEW: Use block-type detection (Issue #4 Phase 0)
            classification = self.pdf_detector.classify_pdf(pdf_path)

            # Scanned pages = image_pages + hybrid_pages (conservative approach)
            scanned_pages = classification.image_pages + classification.hybrid_pages
            scanned_pages.sort()  # Keep pages sorted

            logger.info(
                f"PDF classified as {classification.pdf_type.value}: "
                f"{len(scanned_pages)}/{classification.total_pages} pages need OCR",
                extra={
                    'pdf_type': classification.pdf_type.value,
                    'scanned_pages': scanned_pages,
                    'total_pages': classification.total_pages,
                    'text_blocks': classification.total_text_blocks,
                    'image_blocks': classification.total_image_blocks,
                    'confidence': classification.confidence
                }
            )

            return scanned_pages

        except Exception as e:
            logger.error(f"Error detecting scanned pages: {e}", exc_info=True)
            raise

    def _split_page_to_temp(self, pdf_path: Path, page_num: int) -> Path:
        """
        Extract single page from PDF and save to temp file

        Args:
            pdf_path: Source PDF path
            page_num: 1-indexed page number to extract

        Returns:
            Path to temporary single-page PDF

        Raises:
            Exception: If page extraction fails
        """
        try:
            # Open source PDF
            doc = fitz.open(pdf_path)

            # Create new PDF with single page (convert to 0-indexed)
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=page_num - 1, to_page=page_num - 1)

            # Save to temp file
            temp_file = self.temp_dir / f"{pdf_path.stem}_page_{page_num}.pdf"
            new_doc.save(temp_file)

            # Cleanup
            new_doc.close()
            doc.close()

            logger.debug(
                f"Extracted page {page_num} to: {temp_file.name}",
                extra={'page': page_num, 'temp_file': str(temp_file)}
            )

            return temp_file

        except Exception as e:
            logger.error(f"Failed to extract page {page_num}: {e}", exc_info=True)
            raise

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def extract_text_pass(
        self,
        pdf_path: Path,
        scanned_pages: List[int]
    ) -> Dict[int, str]:
        """
        Pass 1: Extract text from scanned pages using OCR prompt

        For each scanned page:
        1. Split page to temporary single-page PDF
        2. Send to Langdock API with OCR extraction prompt
        3. Parse and store extracted text

        Args:
            pdf_path: Path to original PDF
            scanned_pages: List of 1-indexed page numbers to process

        Returns:
            Dictionary mapping page numbers to extracted text
            Example: {1: "Company Name\\nInvoice 123", 3: "Line items..."}

        Raises:
            Exception: If OCR extraction fails after retries
        """
        if not scanned_pages:
            logger.info("No scanned pages to process in Pass 1")
            return {}

        ocr_context = {}
        ocr_prompt = PromptManager.get_ocr_extraction_prompt()

        logger.info(
            f"Starting OCR text extraction (Pass 1): {len(scanned_pages)} pages",
            extra={'scanned_pages': scanned_pages, 'pdf': pdf_path.name}
        )

        for page_num in scanned_pages:
            page_start_time = time.time()

            try:
                logger.info(
                    f"Extracting text from page {page_num}...",
                    extra={'page': page_num, 'total_pages': len(scanned_pages)}
                )

                # Split page to temp file
                temp_page_pdf = self._split_page_to_temp(pdf_path, page_num)

                # Call API with OCR-specific client and prompt (90s timeout per page)
                response = self.ocr_client._make_api_call(
                    pdf_path=temp_page_pdf,
                    prompt=ocr_prompt,
                    request_timeout=90
                )

                # Extract text from response using OCR client's parser
                extracted_text = self._extract_ocr_text_from_response(response)

                if extracted_text:
                    ocr_context[page_num] = extracted_text
                    logger.info(
                        f"✅ Page {page_num}: Extracted {len(extracted_text)} chars",
                        extra={
                            'page': page_num,
                            'chars': len(extracted_text),
                            'duration': round(time.time() - page_start_time, 2)
                        }
                    )
                    # DEBUG: Log first 500 chars of extracted text
                    logger.info(
                        f"📝 OCR Text Preview (Page {page_num}): {extracted_text[:500]}...",
                        extra={'page': page_num, 'preview_length': min(500, len(extracted_text))}
                    )
                else:
                    logger.warning(
                        f"⚠️  Page {page_num}: No text extracted",
                        extra={'page': page_num}
                    )

                # Cleanup temp file
                try:
                    temp_page_pdf.unlink()
                except Exception:
                    pass

            except Exception as e:
                logger.error(
                    f"❌ Page {page_num} extraction failed: {str(e)[:100]}",
                    extra={'page': page_num, 'error': str(e)},
                    exc_info=True
                )
                # Continue with other pages even if one fails
                ocr_context[page_num] = f"[OCR extraction failed: {str(e)[:100]}]"

        logger.info(
            f"OCR text extraction complete: {len(ocr_context)}/{len(scanned_pages)} successful",
            extra={'successful_pages': len(ocr_context), 'total_pages': len(scanned_pages)}
        )

        return ocr_context

    def _extract_ocr_text_from_response(self, response: Dict[str, Any]) -> str:
        """
        Extract OCR text from Langdock API response

        Handles both markdown code blocks and plain text responses.

        Args:
            response: Raw API response

        Returns:
            Extracted text string

        Raises:
            ValueError: If text cannot be extracted
        """
        # Navigate response structure
        for result in response.get('result', []):
            if result.get('role') == 'assistant':
                content = result.get('content', '')

                # Handle list format (new API)
                if isinstance(content, list):
                    for item in content:
                        if item.get('type') == 'text':
                            text_content = item.get('text', '')
                            # Look for ```text block
                            if '```text' in text_content:
                                start_idx = text_content.find('```text\n')
                                if start_idx != -1:
                                    start_idx += len('```text\n')
                                    end_idx = text_content.find('\n```', start_idx)
                                    if end_idx != -1:
                                        return text_content[start_idx:end_idx]
                            # Fallback: return full text if no code block
                            return text_content.strip()

                # Handle string format (old API)
                elif isinstance(content, str):
                    # Look for ```text block
                    if '```text' in content:
                        start_idx = content.find('```text\n')
                        if start_idx != -1:
                            start_idx += len('```text\n')
                            end_idx = content.find('\n```', start_idx)
                            if end_idx != -1:
                                return content[start_idx:end_idx]
                    # Fallback: return full content
                    return content.strip()

        logger.warning("Could not extract OCR text from response")
        return ""

    def analysis_pass(
        self,
        pdf_path: Path,
        base_prompt: str,
        ocr_context: Dict[int, str]
    ) -> dict:
        """
        Pass 2: Analyze full document with OCR context

        Builds enhanced prompt with OCR-extracted text and sends full PDF
        for comprehensive analysis.

        Args:
            pdf_path: Path to original PDF
            base_prompt: Base analysis prompt (from PromptManager)
            ocr_context: OCR text extracted in Pass 1 (page_num -> text)

        Returns:
            Analysis result dictionary

        Raises:
            Exception: If analysis fails
        """
        logger.info(
            f"Starting document analysis (Pass 2): {pdf_path.name}",
            extra={'ocr_pages': len(ocr_context), 'pdf': pdf_path.name}
        )

        analysis_start_time = time.time()

        try:
            # Build enhanced prompt with OCR context
            enhanced_prompt = PromptManager.build_ocr_enhanced_prompt(
                base_prompt=base_prompt,
                ocr_context=ocr_context
            )

            logger.info(
                f"Enhanced prompt built: {len(enhanced_prompt)} chars "
                f"({len(ocr_context)} OCR pages)",
                extra={'prompt_size': len(enhanced_prompt), 'ocr_pages': len(ocr_context)}
            )

            # Call API with enhanced prompt using analysis client (Pass 2)
            # This ensures the configured analysis model is used
            response = self.analysis_client.process(
                pdf_path=pdf_path,
                prompt=enhanced_prompt
            )

            # Parse result using file_operations helper
            parsed_result = extract_json_from_response(response)

            duration = time.time() - analysis_start_time

            logger.info(
                f"✅ Analysis complete: {duration:.2f}s",
                extra={'duration': duration, 'result_keys': list(parsed_result.keys())}
            )

            return parsed_result

        except Exception as e:
            duration = time.time() - analysis_start_time
            logger.error(
                f"❌ Analysis failed after {duration:.2f}s: {str(e)[:100]}",
                extra={'duration': duration, 'error': str(e)},
                exc_info=True
            )
            raise

    def process(
        self,
        pdf_path: Path,
        prompt: str
    ) -> dict:
        """
        Main entry point: Process PDF with two-pass OCR strategy

        Workflow:
        1. Detect scanned pages
        2. If scanned pages found: Run Pass 1 (OCR extraction)
        3. Run Pass 2 (analysis with OCR context)
        4. Return result with two_pass_metadata

        If no scanned pages detected, falls back to direct analysis.

        Args:
            pdf_path: Path to PDF file
            prompt: Base analysis prompt

        Returns:
            {
                "success": bool,
                "data": {...parsed result...},
                "raw_response": {...},
                "two_pass_metadata": {
                    "used_two_pass_ocr": bool,
                    "scanned_pages": [1, 3],
                    "total_pages": 5,
                    "detection_method": "pymupdf_text_threshold",
                    "text_threshold": 10,
                    "ocr_api_calls": 2,
                    "ocr_duration_seconds": 45.3,
                    "analysis_duration_seconds": 12.1,
                    "total_duration_seconds": 57.4
                }
            }

        Raises:
            Exception: On critical failures (falls back to normal processing)
        """
        process_start_time = time.time()

        logger.info(
            f"Starting two-pass OCR processing: {pdf_path.name}",
            extra={'pdf': str(pdf_path), 'pdf_size_mb': pdf_path.stat().st_size / (1024 * 1024)}
        )

        try:
            # Step 1: Detect scanned pages
            scanned_pages = self.detect_scanned_pages(pdf_path)

            # Get total page count
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            doc.close()

            # If no scanned pages, use normal processing
            if not scanned_pages:
                logger.info(
                    f"No scanned pages detected, using normal processing",
                    extra={'total_pages': total_pages}
                )
                return self._fallback_normal_processing(
                    pdf_path=pdf_path,
                    prompt=prompt,
                    scanned_pages=[],
                    total_pages=total_pages,
                    process_start_time=process_start_time
                )

            # Step 2: OCR extraction (Pass 1)
            ocr_start_time = time.time()
            ocr_context = self.extract_text_pass(pdf_path, scanned_pages)
            ocr_duration = time.time() - ocr_start_time

            # Step 3: Analysis with OCR context (Pass 2)
            analysis_start_time = time.time()
            result_data = self.analysis_pass(pdf_path, prompt, ocr_context)
            analysis_duration = time.time() - analysis_start_time

            total_duration = time.time() - process_start_time

            # Build metadata
            metadata = {
                "used_two_pass_ocr": True,
                "scanned_pages": scanned_pages,
                "total_pages": total_pages,
                "detection_method": "pymupdf_text_threshold",
                "text_threshold": self.text_threshold,
                "ocr_model": self.ocr_model_config.model,
                "ocr_api_calls": len(scanned_pages),
                "ocr_duration_seconds": round(ocr_duration, 2),
                "analysis_duration_seconds": round(analysis_duration, 2),
                "total_duration_seconds": round(total_duration, 2)
            }

            logger.info(
                f"✅ Two-pass OCR processing complete: {total_duration:.2f}s",
                extra=metadata
            )

            return {
                "success": True,
                "data": result_data,
                "raw_response": {"two_pass_ocr": True},
                "two_pass_metadata": metadata
            }

        except Exception as e:
            # Fallback to normal processing on any error
            logger.warning(
                f"Two-pass OCR failed, falling back to normal processing: {str(e)[:100]}",
                extra={'error': str(e)},
                exc_info=True
            )

            return self._fallback_normal_processing(
                pdf_path=pdf_path,
                prompt=prompt,
                scanned_pages=[],
                total_pages=0,
                process_start_time=process_start_time,
                error=str(e)
            )

    def _fallback_normal_processing(
        self,
        pdf_path: Path,
        prompt: str,
        scanned_pages: List[int],
        total_pages: int,
        process_start_time: float,
        error: Optional[str] = None
    ) -> dict:
        """
        Fallback to normal processing (without two-pass OCR)

        Args:
            pdf_path: Path to PDF
            prompt: Analysis prompt
            scanned_pages: Detected scanned pages (may be empty)
            total_pages: Total page count
            process_start_time: Start time for duration calculation
            error: Optional error message if fallback was triggered by error

        Returns:
            Result dictionary with two_pass_metadata indicating fallback
        """
        logger.info(f"Using normal processing for: {pdf_path.name}")

        try:
            # Use client's existing method
            response = self.client._make_api_call(
                pdf_path=pdf_path,
                prompt=prompt,
                request_timeout=150
            )

            result_data = self.client._extract_json_from_response(response)
            total_duration = time.time() - process_start_time

            metadata = {
                "used_two_pass_ocr": False,
                "scanned_pages": scanned_pages,
                "total_pages": total_pages,
                "detection_method": "pymupdf_text_threshold",
                "text_threshold": self.text_threshold,
                "ocr_api_calls": 0,
                "ocr_duration_seconds": 0,
                "analysis_duration_seconds": round(total_duration, 2),
                "total_duration_seconds": round(total_duration, 2)
            }

            if error:
                metadata["fallback_reason"] = error[:200]

            return {
                "success": True,
                "data": result_data,
                "raw_response": response,
                "two_pass_metadata": metadata
            }

        except Exception as e:
            total_duration = time.time() - process_start_time
            logger.error(f"Normal processing also failed: {e}", exc_info=True)
            raise
