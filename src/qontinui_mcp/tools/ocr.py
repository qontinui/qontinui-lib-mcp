"""OCR extraction utilities for checkpoint validation.

This module provides OCR text extraction for screenshots captured during
checkpoint evaluation. It attempts to use qontinui's OCR engines first,
falling back to pytesseract if available.
"""

from __future__ import annotations

import base64
import logging
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage
else:
    PILImage = Any

logger = logging.getLogger(__name__)

# Check qontinui OCR availability
QONTINUI_OCR_AVAILABLE = False
try:
    from qontinui.actions.basic.find.implementations.find_text.ocr_engines import (
        TesseractEngine,
    )

    QONTINUI_OCR_AVAILABLE = True
    logger.info("qontinui OCR engines available")
except ImportError:
    logger.debug("qontinui OCR not available, will try pytesseract fallback")

# Check pytesseract availability
PYTESSERACT_AVAILABLE = False
try:
    import pytesseract  # type: ignore[import-not-found]  # noqa: F401

    PYTESSERACT_AVAILABLE = True
    logger.info("pytesseract available")
except ImportError:
    logger.debug("pytesseract not available")


def is_ocr_available() -> bool:
    """Check if any OCR engine is available.

    Returns:
        True if qontinui OCR or pytesseract is available
    """
    return QONTINUI_OCR_AVAILABLE or PYTESSERACT_AVAILABLE


def load_image(image_source: str) -> PILImage | None:
    """Load image from path or base64 string.

    Args:
        image_source: File path or base64-encoded image string

    Returns:
        PIL Image or None if loading fails
    """
    try:
        from PIL import Image

        # Check if it's a base64 string
        if "," in image_source and (
            image_source.startswith("data:image/") or "base64" in image_source.lower()
        ):
            # Extract base64 data after comma
            base64_data = image_source.split(",", 1)[1]
            image_bytes = base64.b64decode(base64_data)
            return Image.open(BytesIO(image_bytes))
        elif image_source.startswith("data:") or len(image_source) > 1000:
            # Likely base64 without prefix or very long string
            try:
                image_bytes = base64.b64decode(image_source)
                return Image.open(BytesIO(image_bytes))
            except Exception:
                # Not valid base64, try as path
                pass

        # Try as file path
        path = Path(image_source)
        if path.exists() and path.is_file():
            return Image.open(path)

        logger.error(f"Could not load image from: {image_source[:100]}...")
        return None

    except Exception as e:
        logger.error(f"Error loading image: {e}")
        return None


def extract_text_with_qontinui(image: PILImage) -> str | None:
    """Extract text using qontinui OCR engines.

    Args:
        image: PIL Image to extract text from

    Returns:
        Extracted text or None if extraction fails
    """
    if not QONTINUI_OCR_AVAILABLE:
        return None

    try:
        # Import numpy and qontinui for OCR compatibility
        import numpy as np  # noqa: PLC0415
        from qontinui.model.element.region import Region  # noqa: PLC0415

        # Convert PIL Image to numpy array
        image_array: Any = np.array(image)

        # Create a region covering the entire image
        region = Region(x=0, y=0, width=image.width, height=image.height)

        # Initialize Tesseract engine
        engine = TesseractEngine(psm_mode=3, oem_mode=3, return_word_boxes=False)

        if not engine.is_available():
            logger.warning("Tesseract engine not available in qontinui")
            return None

        # Extract text with default English language
        results = engine.extract_text(
            image=image_array,
            region=region,
            language="eng",
            confidence_threshold=0.5,
        )

        # Combine all text results
        if results:
            text_parts = [result.text for result in results if result.text.strip()]
            full_text = " ".join(text_parts)
            logger.info(f"Extracted {len(full_text)} characters using qontinui OCR")
            return full_text

        logger.warning("No text extracted by qontinui OCR")
        return ""

    except Exception as e:
        logger.error(f"Error extracting text with qontinui: {e}")
        return None


def extract_text_with_pytesseract(image: PILImage) -> str | None:
    """Extract text using pytesseract directly.

    Args:
        image: PIL Image to extract text from

    Returns:
        Extracted text or None if extraction fails
    """
    if not PYTESSERACT_AVAILABLE:
        return None

    try:
        import pytesseract

        # Extract text with default configuration
        text: str = pytesseract.image_to_string(image, lang="eng")
        logger.info(f"Extracted {len(text)} characters using pytesseract")
        return text

    except Exception as e:
        logger.error(f"Error extracting text with pytesseract: {e}")
        return None


def extract_ocr_text(image_source: str) -> str | None:
    """Extract OCR text from an image file or base64 string.

    This function attempts to extract text using available OCR engines:
    1. First tries qontinui OCR engines (preferred)
    2. Falls back to pytesseract if qontinui is not available
    3. Returns None if no OCR engine is available

    Args:
        image_source: Path to image file or base64-encoded image string.
                     Supports:
                     - File path: "/path/to/screenshot.png"
                     - Base64 with prefix: "data:image/png;base64,iVBORw0KGgo..."
                     - Base64 without prefix: "iVBORw0KGgo..."

    Returns:
        Extracted text as a string, or None if extraction fails or no OCR available.

    Examples:
        >>> # From file path
        >>> text = extract_ocr_text("/tmp/screenshot.png")
        >>> if text:
        ...     print(f"Found text: {text}")

        >>> # From base64
        >>> text = extract_ocr_text("data:image/png;base64,iVBORw0KGgo...")
        >>> if text:
        ...     print(f"Found text: {text}")
    """
    # Check if any OCR is available
    if not is_ocr_available():
        logger.error("No OCR engine available (install pytesseract or qontinui)")
        return None

    # Load image
    image = load_image(image_source)
    if image is None:
        logger.error("Failed to load image for OCR")
        return None

    # Try qontinui OCR first
    if QONTINUI_OCR_AVAILABLE:
        text = extract_text_with_qontinui(image)
        if text is not None:
            return text
        logger.warning("qontinui OCR failed, trying pytesseract fallback")

    # Fall back to pytesseract
    if PYTESSERACT_AVAILABLE:
        text = extract_text_with_pytesseract(image)
        if text is not None:
            return text

    logger.error("All OCR extraction methods failed")
    return None


def extract_ocr_text_from_path(image_path: str) -> str | None:
    """Convenience function to extract OCR text from a file path.

    Args:
        image_path: Path to image file

    Returns:
        Extracted text or None if extraction fails
    """
    return extract_ocr_text(image_path)


def extract_ocr_text_from_base64(base64_image: str) -> str | None:
    """Convenience function to extract OCR text from base64 string.

    Args:
        base64_image: Base64-encoded image string

    Returns:
        Extracted text or None if extraction fails
    """
    return extract_ocr_text(base64_image)
