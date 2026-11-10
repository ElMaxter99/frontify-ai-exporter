# SPDX-License-Identifier: Apache-2.0
"""Tiny helpers. No settings framework: the URL, token and folder come from the UI/CLI (token may also come from FRONTIFY_TOKEN)."""
from __future__ import annotations

import re


def normalize_domain(value: str) -> str:
    """``https://Acme.Frontify.com/foo`` -> ``acme.frontify.com``."""
    v = re.sub(r"^https?://", "", (value or "").strip(), flags=re.I)
    return v.split("/")[0].strip().lower()
