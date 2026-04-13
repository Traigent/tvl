"""Export TVL specs into JSON presets consumed by the Orientation RAG MicroSim."""

from .bridge import build_presets, dump_presets  # noqa: F401

__all__ = ["build_presets", "dump_presets"]
