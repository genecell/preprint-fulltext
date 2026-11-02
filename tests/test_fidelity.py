"""Regression and integration tests for pf-text/2 text-extraction fidelity (D1-D15)."""

from __future__ import annotations

import io
import os
import pathlib
import re
import zipfile

import httpx
import lxml.html
import pytest
import respx
from lxml import etree

from preprint_fulltext.config import Settings
from preprint_fulltext.core import http as http_mod
from preprint_fulltext.core.render import TextOptions
from preprint_fulltext.mcp_server import build_server
from preprint_fulltext.pipeline.router import Router
from preprint_fulltext.sources.biorxiv_api import BASE as API_BASE
from preprint_fulltext.sources.biorxiv_html import BiorxivHTML, parse_biorxiv_html
from preprint_fulltext.sources.biorxiv_s3 import extract_article_xml
from preprint_fulltext.sources.europepmc import BASE as EPMC, EuropePMC

from .fidelity_helpers import (
    EMPTY_BRACKETS,
    fulltext,
    html,
    html_page,
    jats,
    jats_doc,
    section,
    text_of,
)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(http_mod, "_sleep", lambda s: None)


# --- D1: Hyperlinks ----------------------------------------------------------
LINKS_HTML = (
    '<div class="section" id="sec-8"><h2>Code availability</h2><p id="p-9">'
    'Code is available at <a href="https://github.com/mouseland/kilosort">https://github.com/mouseland/kilosort</a>. '
    'The datasets are available at <a href="http://data.cortexlab.net/singlePhase3/">http://data.cortexlab.net/singlePhase3/</a> '
    'and <a href="https://zenodo.org/records/1">Zenodo</a>. Models are in our repository '
    '“<a href="https://github.com/agemagician/Ankh">https://github.com/agemagician/Ankh</a>”.</p></div>'
)


def test_html_links_kept_inline():
    assert text_of(html(LINKS_HTML), "Code availability") == (
        "Code is available at https://github.com/mouseland/kilosort. The datasets are available at "
        "http://data.cortexlab.net/singlePhase3/ and Zenodo (https://zenodo.org/records/1). "
        "Models are in our repository “https://github.com/agemagician/Ankh”."
    )


def test_links_list_offsets_point_into_text():
    ft = fulltext(html(LINKS_HTML))
    assert [lnk.url for lnk in ft.links] == [
        "https://github.com/mouseland/kilosort",
        "http://data.cortexlab.net/singlePhase3/",
        "https://zenodo.org/records/1",
        "https://github.com/agemagician/Ankh",
    ]
    for lnk in ft.links:
        span = next(s for s in ft.sections if s.id == lnk.section_id).text[lnk.start : lnk.end]
        assert span.startswith(lnk.text) and lnk.url in span


def test_links_text_option():
    t = text_of(html(LINKS_HTML, options=TextOptions(links="text")), "Code availability")
    assert "at https://github.com/mouseland/kilosort." in t and " and Zenodo. " in t


JATS_LINKS = (
    '<sec><title>Code availability</title><p>Code is at <ext-link ext-link-type="uri" '
    'xlink:href="https://github.com/a/b">https://github.com/a/b</ext-link>; weights are on <ext-link '
    'ext-link-type="uri" xlink:href="https://zenodo.org/records/1">Zenodo</ext-link>.</p></sec>'
)


def test_jats_ext_link_href_kept():
    assert (
        text_of(jats(JATS_LINKS), "Code availability")
        == "Code is at https://github.com/a/b; weights are on Zenodo (https://zenodo.org/records/1)."
    )


# --- D2: Citations -----------------------------------------------------------
CITES_HTML = (
    '<div class="section" id="sec-1"><h2>Introduction</h2><p id="p-2">'
    'Prior work (<a class="xref-bibr" href="#ref-1">Smith et al., 2020</a>; <a class="xref-bibr" href="#ref-2">Jones, 2021</a>) '
    'and frameworks [<a class="xref-bibr" href="#ref-3">1</a>–<a class="xref-bibr" href="#ref-4">3</a>] differ. '
    'Following <a class="xref-bibr" href="#ref-5">Giambartolomei et al. (2014)</a>, we define colocalization '
    '(e.g., <a class="xref-bibr" href="#ref-6">Nica et al. (2010)</a>). '
    'Expression varies<sup><a class="xref-bibr" href="#ref-7">22</a>–<a class="xref-bibr" href="#ref-8">24</a></sup>. '
    'Composites occur in IMR90<sup><a class="xref-bibr" href="#ref-9">134</a></sup>. '
    'Results were displayed [<a class="xref-bibr" href="#ref-10">12</a>] (<a class="xref-fig" href="#F9">Figure S1</a>). '
    'Cells numbered 10–20 [<a class="xref-bibr" href="#ref-11">5</a>].</p></div>'
)


def test_citations_dropped_cleanly():
    t = text_of(html(CITES_HTML), "Introduction")
    assert t == (
        "Prior work and frameworks differ. Following Giambartolomei et al. (2014), we define "
        "colocalization (e.g., Nica et al. (2010)). Expression varies. Composites occur in IMR90. "
        "Results were displayed (Figure S1). Cells numbered 10–20."
    )
    assert not EMPTY_BRACKETS.search(t)


def test_citations_kept_verbatim():
    t = text_of(html(CITES_HTML, options=TextOptions(citations="keep")), "Introduction")
    assert t == (
        "Prior work (Smith et al., 2020; Jones, 2021) and frameworks [1–3] differ. Following "
        "Giambartolomei et al. (2014), we define colocalization (e.g., Nica et al. (2010)). "
        "Expression varies [22–24]. Composites occur in IMR90 [134]. Results were displayed [12] "
        "(Figure S1). Cells numbered 10–20 [5]."
    )


def test_citation_records_carry_reference_ids():
    ft = fulltext(html(CITES_HTML))
    assert [c.ref_ids for c in ft.citations] == [
        ["ref-1", "ref-2"],
        ["ref-3", "ref-4"],
        ["ref-5"],
        ["ref-6"],
        ["ref-7", "ref-8"],
        ["ref-9"],
        ["ref-10"],
        ["ref-11"],
    ]
    intro = next(s for s in ft.sections if s.title == "Introduction")
    for c in ft.citations:
        assert intro.text[c.start : c.end] == ("" if c.removed else c.text)


def test_jats_citations():
    body = (
        '<sec><title>R</title><p><xref ref-type="bibr" rid="c2">Lee et al. (2019)</xref> showed it'
        '<sup><xref ref-type="bibr" rid="c3">3</xref></sup> twice, and frameworks '
        '[<xref ref-type="bibr" rid="c4">1</xref>–<xref ref-type="bibr" rid="c5">3</xref>] differ.</p></sec>'
    )
    assert text_of(jats(body), "R") == "Lee et al. (2019) showed it twice, and frameworks differ."
    assert (
        text_of(jats(body, options=TextOptions(citations="keep")), "R")
        == "Lee et al. (2019) showed it [3] twice, and frameworks [1–3] differ."
    )


# --- D3: Cross-references ----------------------------------------------------
XREFS_HTML = (
    '<div class="section" id="sec-2"><h2>Results</h2><p id="p-3">Units were found '
    '(<a class="xref-fig" href="#F1">Figure 1e</a>; see <a class="xref-table" href="#T1">Table 1</a> and '
    '<a class="xref-sec" href="#sec-5">Section 1.4</a>), as shown in <a class="xref-disp-formula" '
    'href="#disp-formula-6">Equation (6)</a> and <a class="xref-fig" href="#F5">Figures 5a</a> and '
    '<a class="xref-fig" href="#F5">5b</a>.</p></div>'
)


def test_html_xref_text_kept():
    art = html(XREFS_HTML)
    assert text_of(art, "Results") == (
        "Units were found (Figure 1e; see Table 1 and Section 1.4), "
        "as shown in Equation (6) and Figures 5a and 5b."
    )
    assert [(x.text, x.target, x.type) for x in fulltext(art).xrefs] == [
        ("Figure 1e", "F1", "fig"),
        ("Table 1", "T1", "table"),
        ("Section 1.4", "sec-5", "sec"),
        ("Equation (6)", "disp-formula-6", "disp-formula"),
        ("Figures 5a", "F5", "fig"),
        ("5b", "F5", "fig"),
    ]


def test_jats_xref_text_kept():
    body = (
        '<sec><title>R</title><p>We find <bold>strong</bold> effects (<xref ref-type="fig" rid="F1">Fig. 1</xref>; '
        '<xref ref-type="table" rid="T1">Table 1</xref>; <xref ref-type="supplementary-material" rid="S3">'
        "Supplementary Fig. 3</xref>).</p></sec>"
    )
    assert text_of(jats(body), "R") == "We find strong effects (Fig. 1; Table 1; Supplementary Fig. 3)."


# --- D4 & D5: Figures and tables ---------------------------------------------
FIG_TABLE_HTML = (
    '<div class="section" id="sec-2"><h2>Results</h2><p id="p-4">Text before.</p>'
    '<div id="F1" class="fig pos-float type-figure  odd"><div class="highwire-figure"><div class="fig-inline-img-wrapper">'
    '<div class="fig-inline-img"><a href="https://www.biorxiv.org/content/biorxiv/early/2099/01/01/000001/F1.large.jpg" '
    'title="Spike detection." class="highwire-fragment fragment-images colorbox-load"><img alt="Spike detection." '
    'src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" '
    'data-src="https://www.biorxiv.org/content/biorxiv/early/2099/01/01/000001/F1.medium.gif"/></a></div></div>'
    '<ul class="highwire-figure-links inline"><li class="download-fig first"><a href="https://www.biorxiv.org/content/'
    'biorxiv/early/2099/01/01/000001/F1.large.jpg?download=true" class="highwire-figure-link highwire-figure-link-download">'
    'Download figure</a></li></ul></div><div class="fig-caption"><span class="fig-label">Figure 1:</span> '
    '<span class="caption-title">Spike detection.</span><p id="p-5" class="first-child">a, Pipeline. e, 42 units at '
    '10<sup>5</sup> Hz (<a class="xref-bibr" href="#ref-9">9</a>).</p><div class="sb-div caption-clear"></div></div></div>'
    '<div id="T1" class="table pos-float"><div class="table-inline table-callout-links"><div class="callout">'
    '<span>View this table:</span><ul class="callout-links"><li class="view-inline first"><a href="" '
    'class="table-expand-inline" data-table-url="/highwire/markup/123/expansion?postprocessors=highwire_tables&amp;'
    'table-expand-inline=1">View inline</a></li></ul></div></div><div class="table-caption"><span class="table-label">'
    'Table 1:</span> <p id="p-6" class="first-child">Results summary.</p><div class="sb-div caption-clear"></div></div></div>'
    '<p id="p-7">Text after.</p></div>'
)


def test_html_figure_caption_extracted():
    art = html(FIG_TABLE_HTML)
    assert text_of(art, "Results") == "Text before. Text after."
    (fig,) = art.figures
    assert (fig.id, fig.label, fig.title) == ("F1", "Figure 1", "Spike detection.")
    assert fig.caption == "Spike detection. a, Pipeline. e, 42 units at 10^5 Hz."
    assert (
        fig.image_url
        == "https://www.biorxiv.org/content/biorxiv/early/2099/01/01/000001/F1.large.jpg"
    )


def test_legends_as_section_option():
    leg = section(
        html(FIG_TABLE_HTML, options=TextOptions(legends_as_section=True)), "Figure legends"
    )
    assert leg.role == "figure_legends"
    assert leg.text == "Figure 1: Spike detection. a, Pipeline. e, 42 units at 10^5 Hz."


def test_jats_figure_caption_extracted():
    body = (
        '<sec><title>Results</title><p>Text before.</p><fig id="F1"><label>Figure 1.</label><caption>'
        "<title>Overview.</title><p>Panel a shows 42 cells at 10<sup>5</sup> Hz.</p></caption>"
        '<graphic xlink:href="F1.tif"/></fig><p>Text after.</p></sec>'
    )
    art = jats(body)
    (fig,) = art.figures
    assert (fig.id, fig.label, fig.title, fig.caption) == (
        "F1",
        "Figure 1",
        "Overview.",
        "Overview. Panel a shows 42 cells at 10^5 Hz.",
    )
    assert text_of(art, "Results") == "Text before. Text after."


def test_html_table_recorded_with_source_url():
    art = html(
        FIG_TABLE_HTML,
        base_url="https://www.biorxiv.org/content/10.1101/2099.01.01.000001v1.full",
    )
    (tab,) = art.tables
    assert (tab.id, tab.label, tab.caption, tab.rows, tab.status) == (
        "T1",
        "Table 1",
        "Results summary.",
        None,
        "not_in_page",
    )
    assert tab.source_url == (
        "https://www.biorxiv.org/highwire/markup/123/expansion?"
        "postprocessors=highwire_tables&table-expand-inline=1"
    )


def test_jats_table_rows():
    body = (
        '<sec><title>Results</title><table-wrap id="T1"><label>Table 1</label><caption><p>Scores.</p></caption>'
        "<table><thead><tr><th>Model</th><th>AUC</th></tr></thead><tbody><tr><td>Ankh</td><td>0.91</td></tr>"
        "<tr><td>ESM</td><td>0.88</td></tr></tbody></table><table-wrap-foot><fn><p>n = 3 seeds.</p></fn>"
        "</table-wrap-foot></table-wrap></sec>"
    )
    (tab,) = jats(body).tables
    assert tab.rows == [["Model", "AUC"], ["Ankh", "0.91"], ["ESM", "0.88"]] and tab.header_rows == 1
    assert (tab.label, tab.caption, tab.footnotes) == ("Table 1", "Scores.", ["n = 3 seeds."])
    assert tab.markdown == "| Model | AUC |\n| --- | --- |\n| Ankh | 0.91 |\n| ESM | 0.88 |"


@respx.mock
def test_html_fetch_tables_opt_in_and_429_abort():
    doi = "10.1101/2099.01.01.000001"
    url = f"https://www.biorxiv.org/content/{doi}.full"
    exp1 = "https://www.biorxiv.org/highwire/markup/123/expansion?postprocessors=highwire_tables&table-expand-inline=1"
    respx.get(url).mock(return_value=httpx.Response(200, content=html_page(FIG_TABLE_HTML)))
    respx.get(f"{API_BASE}/details/biorxiv/{doi}").mock(
        return_value=httpx.Response(200, json={"collection": []})
    )
    respx.get(exp1).mock(
        return_value=httpx.Response(
            200,
            content=b"<div><table><thead><tr><th>Model</th><th>AUC</th></tr></thead>"
            b"<tbody><tr><td>Ankh</td><td>0.91</td></tr></tbody></table></div>",
        )
    )
    ft = BiorxivHTML(Settings()).get_fulltext(doi, fetch_tables=True)
    assert ft is not None
    assert ft.tables[0].status == "parsed"
    assert ft.tables[0].rows == [["Model", "AUC"], ["Ankh", "0.91"]]

    # Now test 429 on expansion URL -> status == "fetch_failed:429" with no retries and no further table requests
    two_tables_html = FIG_TABLE_HTML + FIG_TABLE_HTML.replace('id="T1"', 'id="T2"').replace(
        "/123/", "/456/"
    )
    exp2 = "https://www.biorxiv.org/highwire/markup/456/expansion?postprocessors=highwire_tables&table-expand-inline=1"
    respx.get(url).mock(return_value=httpx.Response(200, content=html_page(two_tables_html)))
    r1 = respx.get(exp1).mock(return_value=httpx.Response(429))
    r1.calls.clear()
    r2 = respx.get(exp2).mock(return_value=httpx.Response(200))
    ft2 = BiorxivHTML(Settings()).get_fulltext(doi, fetch_tables=True)
    assert ft2 is not None
    assert ft2.tables[0].status == "fetch_failed:429"
    assert ft2.tables[1].status == "fetch_failed:429"
    assert r1.call_count == 1
    assert r2.call_count == 0


# --- D6: Superscripts --------------------------------------------------------
SUP_HTML = (
    '<div class="section" id="sec-2"><h2>Results</h2><p id="p-3">We sorted 6.1 × 10<sup>6</sup> spikes from '
    "∼10<sup>9</sup> samples at 5 × 10<sup>−8</sup>; ε = 10<sup>−10</sup>; 10<sup>3</sup> µm<sup>3</sup>; "
    "R<sup>2</sup> = 0.91; the 25<sup>th</sup> percentile; Ca<sup>2+</sup>; a 90<sup>◦</sup> turn; "
    "(log(1 + n))<sup>2</sup>.</p></div>"
)


def test_superscripts_never_merge_into_digits():
    assert text_of(html(SUP_HTML), "Results") == (
        "We sorted 6.1 × 10^6 spikes from ∼10^9 samples at 5 × 10^−8; ε = 10^−10; 10^3 µm^3; "
        "R^2 = 0.91; the 25th percentile; Ca^2+; a 90◦ turn; (log(1 + n))^2."
    )


def test_superscripts_unicode_option():
    t = text_of(html(SUP_HTML, options=TextOptions(scripts="unicode")), "Results")
    assert "6.1 × 10⁶" in t and "5 × 10⁻⁸" in t and "10³ µm³" in t and "Ca²⁺" in t and "25th" in t


def test_jats_superscripts():
    body = "<sec><title>R</title><p>At <italic>P</italic> &lt; 5 × 10<sup>−8</sup> with 6.1 × 10<sup>6</sup> SNPs.</p></sec>"
    assert text_of(jats(body), "R") == "At P < 5 × 10^−8 with 6.1 × 10^6 SNPs."


# --- D7: JATS word order & token subsequence invariant -----------------------
REORDER_JATS = (
    "<sec><title>R</title>"
    '<p>The <italic>Gata1</italic> gene is required (<xref ref-type="bibr" rid="c1">Smith, 2020</xref>) in mice.</p>'
    '<p>We find <bold>strong</bold> effects (<xref ref-type="fig" rid="F1">Fig. 1</xref>), which persist '
    '(<xref ref-type="fig" rid="F2">Fig. 2</xref>) over time.</p>'
    '<p><xref ref-type="bibr" rid="c0">Lee et al. (2019)</xref> showed it<sup><xref ref-type="bibr" rid="c1">1</xref></sup> twice.</p></sec>'
)


def test_jats_word_order_preserved():
    t = text_of(jats(REORDER_JATS), "R")
    a = t.index("The Gata1 gene is required in mice.")
    b = t.index("We find strong effects (Fig. 1), which persist (Fig. 2) over time.")
    c = t.index("Lee et al. (2019) showed it twice.")
    assert a < b < c


def test_jats_output_tokens_are_a_subsequence_of_source_tokens():
    for snippet in (REORDER_JATS, JATS_LINKS):
        for p in etree.fromstring(jats_doc(snippet)).iter("p"):
            # Skip paragraphs with links where href is appended inline (use links="text" for pure token check)
            src = iter(re.findall(r"\w+", " ".join(p.itertext())))
            frag = etree.tostring(p, encoding="unicode", with_tail=False)
            out = re.findall(
                r"\w+",
                text_of(
                    jats("<sec><title>X</title>" + frag + "</sec>", options=TextOptions(links="text")),
                    "X",
                ),
            )
            assert all(any(w == s for s in src) for w in out), out


# --- D8: Formulas ------------------------------------------------------------
FORMULA_HTML = (
    '<div class="section" id="sec-2"><h2>Results</h2><p id="p-4">The estimate <span class="inline-formula" '
    'id="inline-formula-1"><span class="highwire-responsive-lazyload"><img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAA'
    'AP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" class="highwire-embed lazyload" alt="Embedded Image" '
    'data-src="https://www.biorxiv.org/x/embed/inline-graphic-1.gif"/></span></span> = 4.98 under the model\n'
    '<span class="disp-formula" id="disp-formula-1"><span class="highwire-responsive-lazyload"><img src="data:image/gif;'
    'base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" class="highwire-embed lazyload" alt="Embedded Image" '
    'data-src="https://www.biorxiv.org/x/embed/graphic-1.gif"/></span></span>\nwhere y is centred.</p></div>'
)


def test_html_formula_placeholders():
    art = html(FORMULA_HTML)
    assert (
        text_of(art, "Results")
        == "The estimate [formula] = 4.98 under the model [equation] where y is centred."
    )
    assert [(f.id, f.display, f.image_url) for f in art.formulas] == [
        ("inline-formula-1", False, "https://www.biorxiv.org/x/embed/inline-graphic-1.gif"),
        ("disp-formula-1", True, "https://www.biorxiv.org/x/embed/graphic-1.gif"),
    ]


FORMULA_JATS = (
    "<sec><title>Results</title><p>The estimate <inline-formula><alternatives><tex-math>\\alpha_1</tex-math>"
    "<mml:math><mml:msub><mml:mi>α</mml:mi><mml:mn>1</mml:mn></mml:msub></mml:math></alternatives></inline-formula> = 4.98.</p>"
    '<disp-formula id="E1"><label>(1)</label><alternatives><tex-math>y = X\\beta + \\epsilon</tex-math></alternatives>'
    "</disp-formula><p>where y is centred.</p></sec>"
)


def test_jats_formulas():
    art = jats(FORMULA_JATS)
    assert text_of(art, "Results") == "The estimate α_1 = 4.98. [equation (1)] where y is centred."
    assert text_of(jats(FORMULA_JATS, options=TextOptions(math="placeholder")), "Results").startswith(
        "The estimate [formula] = 4.98."
    )
    (disp,) = [f for f in art.formulas if f.display]
    assert (disp.label, disp.tex) == ("(1)", r"y = X\beta + \epsilon")


# --- D9: Footnotes & back matter ---------------------------------------------
def test_html_footnotes_and_funding_kept():
    art = html(
        '<div class="section" id="sec-1"><h2>Discussion</h2><p>d.</p></div>'
        '<div class="section fn-group" id="fn-group-1"><h2>Footnotes</h2><ul><li class="fn" id="fn-1">'
        '<p id="p-11"><a href="https://github.com/agemagician/Ankh">https://github.com/agemagician/Ankh</a></p>'
        '</li></ul></div><div class="funding-group"><h2>Funder Information Declared</h2><div class="award-group">'
        '<span class="funding-source">NIH</span>, <span class="award-id">U01HG009431</span></div></div>'
    )
    fn = section(art, "Footnotes")
    assert fn.role == "footnotes" and fn.text == "https://github.com/agemagician/Ankh"
    assert "U01HG009431" in next(s for s in art.sections if s.role == "funding").text


def test_jats_back_matter_and_body_level_text():
    art = jats(
        "<p>A body paragraph outside any section reports 12 samples.</p><sec><title>Discussion</title><p>d.</p></sec>",
        back=(
            "<ack><title>Acknowledgements</title><p>We thank Z.</p></ack>"
            '<sec sec-type="data-availability"><title>Data availability</title><p>Data are at <ext-link '
            'ext-link-type="uri" xlink:href="https://doi.org/10.5281/zenodo.2">Zenodo</ext-link>.</p></sec>'
            '<app-group><app id="app1"><title>Appendix A Derivation</title><p>Appendix text.</p></app></app-group>'
            '<fn-group><fn id="fn1"><p>Code mirror: <ext-link ext-link-type="uri" '
            'xlink:href="https://gitlab.com/a/b">https://gitlab.com/a/b</ext-link></p></fn></fn-group>'
        ),
    )
    s = art.sections
    assert s[0].title is None and s[0].text == "A body paragraph outside any section reports 12 samples."
    assert [(x.title, x.role) for x in s[1:]] == [
        ("Discussion", None),
        ("Acknowledgements", "acknowledgements"),
        ("Data availability", "data_availability"),
        ("Appendix A Derivation", "appendix"),
        ("Footnotes", "footnotes"),
    ]
    assert text_of(art, "Data availability") == "Data are at Zenodo (https://doi.org/10.5281/zenodo.2)."
    assert text_of(art, "Footnotes") == "Code mirror: https://gitlab.com/a/b"


# --- D10: Section kind classification ----------------------------------------
KINDS_HTML = (
    '<div class="section"><h2>Methods</h2><div class="subsection"><h3>Neighbor finding with subsampling</h3>'
    '<p>a</p></div><div class="subsection"><h3>Extracting PC features with background subtraction</h3><p>b</p></div></div>'
    '<div class="section"><h2>Results</h2><div class="subsection"><h3>CNNs learn sequence preferences from background '
    'cleavage profiles</h3><p>c</p></div></div><div class="section"><h2>Discussion</h2><div class="subsection"><h3>ChromBPNet '
    'introduces several technical innovations</h3><p>d</p></div><div class="subsection"><h3>Our study advances both the '
    'methodology and benchmarking standards</h3><p>e</p></div></div><div class="section"><h2>Data and code availability</h2>'
    '<div class="subsection"><h3>Code to reproduce results and generate figures</h3><p>f</p></div></div>'
    '<div class="section"><h2>7 Supplementary Materials</h2><div class="subsection"><h3>7.1 Pre-Training Data</h3><p>g</p>'
    '</div></div><div class="section"><h2>Appendix A Multiple Imputation Procedure</h2><p>h</p></div>'
)


def test_section_kinds_inherit_and_anchor_keywords():
    assert {s.title: (s.kind, s.role) for s in html(KINDS_HTML).sections} == {
        "Methods": ("methods", None),
        "Neighbor finding with subsampling": ("methods", None),
        "Extracting PC features with background subtraction": ("methods", None),
        "Results": ("results", None),
        "CNNs learn sequence preferences from background cleavage profiles": ("results", None),
        "Discussion": ("discussion", None),
        "ChromBPNet introduces several technical innovations": ("discussion", None),
        "Our study advances both the methodology and benchmarking standards": ("discussion", None),
        "Data and code availability": ("other", "data_availability"),
        "Code to reproduce results and generate figures": ("other", "data_availability"),
        "7 Supplementary Materials": ("other", "supplementary"),
        "7.1 Pre-Training Data": ("other", "supplementary"),
        "Appendix A Multiple Imputation Procedure": ("other", "appendix"),
    }


# --- D11: Element boundary separators ----------------------------------------
def test_adjacent_inline_blocks_separated():
    t = text_of(
        html(
            '<div class="section"><h2>Data</h2><p>An example: <q id="disp-quote-1">MATCH (n:Neuron) WHERE '
            't.type = ‘MBON18’</q><q id="disp-quote-2">RETURN n.type</q> This query works.</p></div>'
        ),
        "Data",
    )
    assert "‘MBON18’ RETURN n.type" in t


def test_jats_lists_and_structured_abstract_not_glued():
    art = jats(
        '<sec><title>Steps</title><list list-type="order"><list-item><label>(i)</label><p>first</p></list-item>'
        '<list-item><label>(ii)</label><p>second</p></list-item></list></sec>',
        abstract="<abstract><sec><title>Background</title><p>We study X.</p></sec><sec><title>Results</title>"
        "<p>Y is 10<sup>5</sup>.</p></sec></abstract>",
    )
    assert text_of(art, "Steps") == "(i) first (ii) second"
    assert "Background: We study X." in art.abstract and "10^5" in art.abstract
    assert "BackgroundWe" not in art.abstract


# --- D12: Paragraph separator, section labels, untitled subsections ----------
def test_paragraph_separator_option():
    assert (
        text_of(
            html(
                '<div class="section"><h2>R</h2><p>A.</p><p>B.</p></div>',
                options=TextOptions(paragraph_sep="\n\n"),
            ),
            "R",
        )
        == "A.\n\nB."
    )


def test_jats_section_label_in_title():
    assert (
        jats("<sec><label>2.1</label><title>Model and Notation</title><p>x</p></sec>")
        .sections[0]
        .title
        == "2.1 Model and Notation"
    )


def test_untitled_subsection_merged_into_parent():
    art = html(
        '<div class="section"><h2>5.3.3 Embedding</h2><div class="subsection"><p>x.</p></div>'
        '<div class="subsection"><p>y.</p></div></div>'
    )
    assert [(s.title, s.text) for s in art.sections] == [("5.3.3 Embedding", "x. y.")]


# --- D13: HTML decoding charset ----------------------------------------------
def test_html_decoding_uses_declared_charset():
    raw = html_page(
        '<div class="section"><h2>R</h2><p>6.1 × 10 µm, ε = 0.5</p></div>', meta_charset=False
    )
    assert text_of(parse_biorxiv_html(raw, encoding="utf-8"), "R") == "6.1 × 10 µm, ε = 0.5"


# --- D14: Routing and robustness ---------------------------------------------
@respx.mock
def test_epmc_skips_fulltext_when_not_in_epmc():
    respx.get(f"{EPMC}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "resultList": {
                    "result": [
                        {"id": "PPR593906", "source": "PPR", "inEPMC": "N", "isOpenAccess": "N"}
                    ]
                }
            },
        )
    )
    route = respx.get(f"{EPMC}/PPR593906/fullTextXML").mock(return_value=httpx.Response(500))
    assert EuropePMC().get_fulltext("10.1101/2023.01.07.523036") is None
    assert route.call_count == 0


@respx.mock
def test_epmc_fulltext_500_is_not_retried():
    respx.get(f"{EPMC}/search").mock(
        return_value=httpx.Response(
            200, json={"resultList": {"result": [{"id": "PPR1", "source": "PPR", "inEPMC": "Y"}]}}
        )
    )
    route = respx.get(f"{EPMC}/PPR1/fullTextXML").mock(
        return_value=httpx.Response(500, json={"status": 500, "error": "Internal Server Error"})
    )
    assert EuropePMC().get_fulltext("10.1101/x") is None and route.call_count == 1


@respx.mock
def test_router_cloudflare_429_and_honest_reason(monkeypatch):
    import boto3

    class _NoCreds:
        def get_credentials(self):
            return None

    monkeypatch.setattr(boto3, "Session", lambda *a, **k: _NoCreds())

    doi = "10.1101/2024.12.25.630221"
    respx.get(f"{EPMC}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "resultList": {
                    "result": [{"id": "PPR999", "source": "PPR", "inEPMC": "N", "isOpenAccess": "N"}]
                }
            },
        )
    )
    respx.get(f"{API_BASE}/details/biorxiv/{doi}").mock(
        return_value=httpx.Response(
            200,
            json={
                "collection": [
                    {
                        "doi": doi,
                        "title": "T",
                        "authors": "A, B.",
                        "date": "2024-12-25",
                        "version": "1",
                        "license": "cc_by",
                        "published": "NA",
                        "server": "biorxiv",
                    }
                ]
            },
        )
    )
    html_route = respx.get(f"https://www.biorxiv.org/content/{doi}.full").mock(
        return_value=httpx.Response(429, content=b"<title>Attention Required! | Cloudflare</title>")
    )
    res = Router(Settings()).get_fulltext(doi, server="biorxiv", allow_html=True)
    assert res.fulltext is None
    assert "429" in (res.reason or "")
    assert "non-CC" not in (res.reason or "")
    assert html_route.call_count == 1


def test_mcp_exposes_allow_html_and_source():
    server = build_server()
    resp = server.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    gf = next(t for t in resp["result"]["tools"] if t["name"] == "get_fulltext")
    props = gf["inputSchema"]["properties"]
    assert "allow_html" in props and "source" in props


# --- D15: S3 .meca manifest with Windows backslash + directives.xml ----------
def test_extract_article_xml_handles_backslash_and_directives():
    manifest = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<manifest xmlns="http://highwire.org/submission/manifest">'
        b'<item id="a1" type="article"><instance media-type="application/xml" href="content\\007724.xml"/></item>'
        b'<item id="d1" type="directive"><instance media-type="application/xml" href="directives.xml"/></item>'
        b'<item id="t1" type="transfer"><instance media-type="application/xml" href="transfer.xml"/></item>'
        b"</manifest>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.xml", manifest)
        zf.writestr("directives.xml", b"<directives/>")
        zf.writestr("transfer.xml", b"<transfer/>")
        zf.writestr("content/007724.xml", b"<article><body><sec><title>Real</title><p>Body.</p></sec></body></article>")
    xml = extract_article_xml(buf.getvalue())
    assert xml is not None and b"<title>Real</title>" in xml


# --- Full-page integration test (§7.1) ---------------------------------------
FULL = html_page(
    '<div class="section abstract" id="abstract-1"><h2>Abstract</h2><p id="p-1">We sorted 6.1 × 10<sup>6</sup> spikes.</p></div>'
    + CITES_HTML
    + FIG_TABLE_HTML
    + LINKS_HTML
    + FORMULA_HTML
    + '<div class="section fn-group" id="fn-group-1"><h2>Footnotes</h2><ul><li class="fn" id="fn-1"><p id="p-11">'
    '<a href="https://github.com/agemagician/Ankh">https://github.com/agemagician/Ankh</a></p></li></ul></div>'
    '<div class="section ref-list" id="ref-list-1"><h2>References</h2><ol class="cit-list"><li><span class="ref-label">1.'
    '</span><div class="cit ref-cit ref-journal" id="cit-1"><span class="cit-auth">Smith</span> '
    '<span class="cit-pub-date">2020</span></div></li></ol></div>'
)


def test_full_page():
    art = parse_biorxiv_html(FULL)
    ft = fulltext(art)
    corpus = "\n".join(s.text for s in ft.sections)
    assert ft.sections[0].text == "We sorted 6.1 × 10^6 spikes."
    assert "References" not in [s.title for s in ft.sections]
    for href in (
        "https://github.com/mouseland/kilosort",
        "http://data.cortexlab.net/singlePhase3/",
        "https://zenodo.org/records/1",
        "https://github.com/agemagician/Ankh",
    ):
        assert href in corpus
    assert not EMPTY_BRACKETS.search(corpus) and "“”" not in corpus
    ids = {s.id for s in ft.sections}
    assert all(
        x.section_id in ids
        for x in [*ft.links, *ft.citations, *ft.xrefs, *ft.formulas, *ft.figures, *ft.tables]
    )
    ft.model_dump(mode="json")
    from preprint_fulltext.cli import _render_markdown

    md = _render_markdown(ft)
    assert "## Figures" in md and "## Tables" in md


# --- Golden invariants on locally saved pages (§7.3) -------------------------
GOLDEN = os.environ.get("PF_GOLDEN_DIR")


@pytest.mark.skipif(not GOLDEN, reason="set PF_GOLDEN_DIR to a folder of saved bioRxiv .full pages")
@pytest.mark.parametrize(
    "page", sorted(pathlib.Path(GOLDEN or ".").glob("*.html")), ids=lambda p: p.name
)
def test_golden_page_invariants(page):
    raw = page.read_bytes()
    ft = fulltext(parse_biorxiv_html(raw))
    corpus = "\n".join(s.text for s in ft.sections)
    view = lxml.html.fromstring(raw).xpath('//div[contains(@class,"fulltext-view")]')[0]
    not_in_text = 'ancestor::div[contains(@class,"ref-list") or contains(@class,"fig") or contains(@class,"table")]'
    for a in view.xpath('.//p//a[starts-with(@href,"http")]'):
        if not a.xpath(not_in_text):
            assert a.get("href") in corpus, a.get("href")
    assert not EMPTY_BRACKETS.search(corpus)
    for a in view.xpath('.//a[contains(@class,"xref-fig") or contains(@class,"xref-table")]'):
        if not a.xpath(not_in_text):
            assert a.text_content().strip() in corpus
    assert len(ft.figures) == len(view.xpath('.//div[contains(@class,"fig-caption")]'))
    assert len(ft.tables) == len(
        view.xpath(
            './/div[contains(concat(" ",@class," ")," table ") and contains(@class,"pos-float")]'
        )
    )
    for sup in view.xpath(".//p//sup[not(.//a)]"):
        prev = sup.getprevious()
        before = (prev.tail if prev is not None else sup.getparent().text) or ""
        s = sup.text_content().strip()
        if re.search(r"\d$", before) and re.match(r"[−\-]?\d", s) and not sup.xpath(not_in_text):
            assert ("^" + s) in corpus or ("^(" + s + ")") in corpus
