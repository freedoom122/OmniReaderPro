"""Translation subsystem."""
from omnireader_pro.core.translation.translator import (
    TranslationResult,
    argos_available,
    detect_language,
    installed_pairs,
    translate_offline,
    translate_online,
)

__all__ = ["TranslationResult", "argos_available", "detect_language",
           "installed_pairs", "translate_offline", "translate_online"]
