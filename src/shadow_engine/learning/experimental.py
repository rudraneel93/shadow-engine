"""Experimental engine feature-flag support.

All engines marked as experimental are gated behind the
SHADOW_EXPERIMENTAL=1 environment variable. When disabled,
they are replaced with NoOp stubs that return safe defaults.

Usage:
    from shadow_engine.learning.experimental import is_experimental_enabled

    if is_experimental_enabled():
        from .causal_engine import CausalEngine
    else:
        CausalEngine = None
"""

from __future__ import annotations

import os


def is_experimental_enabled() -> bool:
    """Check if experimental AI engines should be loaded.

    Set SHADOW_EXPERIMENTAL=1 to enable causal reasoning, debate,
    PR simulation, temporal anomaly detection, intervention,
    strategy evolution, speculative context, and transfer learning.
    """
    return os.environ.get("SHADOW_EXPERIMENTAL", "").lower() in ("1", "true", "yes")