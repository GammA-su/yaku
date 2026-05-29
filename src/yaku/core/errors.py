"""Custom exception hierarchy for Yaku."""


class YakuError(Exception):
    """Base exception for all Yaku errors."""


class ConfigError(YakuError):
    """Configuration validation or loading error."""


class InvalidModeError(ConfigError):
    """Unknown or unsupported operating mode."""


class InvalidBackendError(ConfigError):
    """Unknown or unsupported backend name."""


class InvalidRenderModeError(ConfigError):
    """Unknown or unsupported render mode."""


class OptionalDependencyMissing(YakuError, ImportError):
    """An optional dependency required by this backend is not installed.

    The exception message always includes the ``uv add <package>`` command
    needed to install it, e.g.::

        raise OptionalDependencyMissing(
            "manga-ocr is not installed. Install with: uv add manga-ocr"
        )
    """


class CacheError(YakuError):
    """SQLite cache read/write failure."""


class CaptureError(YakuError):
    """Screen capture failure."""


class OCRError(YakuError):
    """OCR extraction failure."""


class TranslationError(YakuError):
    """Translation backend failure."""


class InpaintError(YakuError):
    """Inpainting backend failure."""


class AITextEditError(YakuError):
    """AI text-editing backend failure or unavailability."""


class RenderError(YakuError):
    """Frame-rendering failure (mask/inpaint/text compositing)."""


class InputForwardError(YakuError):
    """Input-forwarding failure (mouse/keyboard injection)."""


class PipelineError(YakuError):
    """Generic pipeline-stage failure not covered by a more specific error."""
