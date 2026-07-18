"""licenses.py — map a raw license string/URL to a canonical :class:`License`.

The single input to the compliance gate is ``License.redistributable``. The
CC family permits redistribution (with conditions), so all CC variants map to
``redistributable=True``; only the bioRxiv default ("no reuse without
permission" / all-rights-reserved) and **anything unrecognized** map to
``redistributable=False`` (fail safe).

Kept small and data-driven so it is easy to extend and test.
"""

from __future__ import annotations

import re

from .models import License

# spdx_id -> (redistributable, requires_attribution). CC0 needs no attribution.
_SPDX_FLAGS: dict[str, tuple[bool, bool]] = {
    "CC0-1.0": (True, False),
    "CC-BY": (True, True),
    "CC-BY-SA": (True, True),
    "CC-BY-ND": (True, True),
    "CC-BY-NC": (True, True),
    "CC-BY-NC-SA": (True, True),
    "CC-BY-NC-ND": (True, True),
}

# Ordered longest-first so "by-nc-nd" wins before "by-nc" / "by".
_URL_VARIANTS = [
    ("by-nc-nd", "CC-BY-NC-ND"),
    ("by-nc-sa", "CC-BY-NC-SA"),
    ("by-nc", "CC-BY-NC"),
    ("by-nd", "CC-BY-ND"),
    ("by-sa", "CC-BY-SA"),
    ("by", "CC-BY"),
]

# Version as "/4.0/" (URL) or a bare "4.0" token (prose, e.g. "CC BY-NC 4.0").
_VERSION_RE = re.compile(r"/(\d\.\d)/|(?<!\d)(\d\.\d)(?!\d)")
# Text-form CC markers, e.g. "CC-BY-NC 4.0", "Creative Commons Attribution-NonCommercial".
_TEXT_VARIANTS = [
    ("by-nc-nd", "CC-BY-NC-ND"),
    ("by-nc-sa", "CC-BY-NC-SA"),
    ("by-nc", "CC-BY-NC"),
    ("by-nd", "CC-BY-ND"),
    ("by-sa", "CC-BY-SA"),
    ("by", "CC-BY"),
]
_ATTR_WORDS = {
    "attribution-noncommercial-noderiv": "CC-BY-NC-ND",
    "attribution-noncommercial-sharealike": "CC-BY-NC-SA",
    "attribution-noncommercial": "CC-BY-NC",
    "attribution-noderiv": "CC-BY-ND",
    "attribution-sharealike": "CC-BY-SA",
    "attribution": "CC-BY",
}


def _raw_to_str(raw: str | dict | None) -> str:
    """Accept the parser's {'href', 'text'} dict or a bare string/URL."""
    if raw is None:
        return ""
    if isinstance(raw, dict):
        return " ".join(str(v) for v in (raw.get("href"), raw.get("text")) if v)
    return str(raw)


def _detect_spdx(s: str) -> tuple[str | None, str | None]:
    """Return (base_spdx, version_or_None). base_spdx is None if unrecognized."""
    low = s.lower()

    if "publicdomain/zero" in low or re.search(r"\bcc0\b", low) or "cc-zero" in low:
        return "CC0-1.0", None

    version = None
    m = _VERSION_RE.search(low)
    if m:
        version = m.group(1) or m.group(2)

    # URL form: creativecommons.org/licenses/<variant>/<version>/
    url_m = re.search(r"creativecommons\.org/licenses/([a-z-]+)", low)
    if url_m:
        variant = url_m.group(1)
        for key, spdx in _URL_VARIANTS:
            if variant == key:
                return spdx, version

    # Compact text form: "cc-by-nc-nd", "cc by nc", "ccby"
    compact = re.sub(r"[^a-z]", "", low)  # "ccbync40" etc.
    for key, spdx in _TEXT_VARIANTS:
        if ("cc" + key.replace("-", "")) in compact:
            return spdx, version

    # Spelled-out form: "Creative Commons Attribution-NonCommercial"
    if "creativecommons" in compact or "creative commons" in low:
        joined = low.replace(" ", "-")
        for key, spdx in _ATTR_WORDS.items():
            if key in joined:
                return spdx, version

    return None, version


def parse_license(raw: str | dict | None) -> License:
    """Map a raw license string/URL (or the parser's dict) to a :class:`License`.

    Unknown / empty / all-rights-reserved → ``redistributable=False`` (fail safe).
    """
    s = _raw_to_str(raw)
    raw_repr = s.strip()

    base, version = _detect_spdx(s)
    if base is None:
        # Unrecognized OR explicitly restrictive → non-redistributable.
        return License(raw=raw_repr, spdx_id=None, redistributable=False, requires_attribution=True)

    redistributable, attribution = _SPDX_FLAGS[base]
    if base == "CC0-1.0":
        spdx = base
    else:
        spdx = f"{base}-{version}" if version else base
    return License(
        raw=raw_repr,
        spdx_id=spdx,
        redistributable=redistributable,
        requires_attribution=attribution,
    )


__all__ = ["parse_license"]
