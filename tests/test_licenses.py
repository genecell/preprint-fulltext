"""Tests for core/licenses.py."""

from __future__ import annotations

import pytest

from preprint_fulltext.core.licenses import parse_license


@pytest.mark.parametrize(
    "url,spdx,redist,attr",
    [
        ("http://creativecommons.org/licenses/by/4.0/", "CC-BY-4.0", True, True),
        ("https://creativecommons.org/licenses/by-nc/4.0/", "CC-BY-NC-4.0", True, True),
        ("http://creativecommons.org/licenses/by-nc-nd/4.0/", "CC-BY-NC-ND-4.0", True, True),
        ("http://creativecommons.org/licenses/by-nd/4.0/", "CC-BY-ND-4.0", True, True),
        ("http://creativecommons.org/licenses/by-sa/3.0/", "CC-BY-SA-3.0", True, True),
        ("http://creativecommons.org/publicdomain/zero/1.0/", "CC0-1.0", True, False),
    ],
)
def test_cc_urls(url, spdx, redist, attr):
    lic = parse_license(url)
    assert lic.spdx_id == spdx
    assert lic.redistributable is redist
    assert lic.requires_attribution is attr


def test_longest_variant_wins():
    # by-nc-nd must not be misdetected as by or by-nc.
    lic = parse_license("http://creativecommons.org/licenses/by-nc-nd/4.0/")
    assert lic.spdx_id == "CC-BY-NC-ND-4.0"


def test_spelled_out_text_form():
    lic = parse_license("Creative Commons Attribution-NonCommercial 4.0 International")
    assert lic.spdx_id == "CC-BY-NC-4.0"
    assert lic.redistributable is True


def test_dict_input_from_parser():
    lic = parse_license({"href": "http://creativecommons.org/licenses/by/4.0/",
                         "text": "CC BY 4.0"})
    assert lic.spdx_id == "CC-BY-4.0"


def test_all_rights_reserved_not_redistributable():
    lic = parse_license({"href": None,
                         "text": "All rights reserved. No reuse allowed without permission."})
    assert lic.spdx_id is None
    assert lic.redistributable is False


@pytest.mark.parametrize("raw", ["", None, "some weird custom license", {"href": None, "text": None}])
def test_unknown_or_empty_is_fail_safe(raw):
    lic = parse_license(raw)
    assert lic.redistributable is False


def test_cc0_needs_no_attribution():
    assert parse_license("CC0 1.0").requires_attribution is False
