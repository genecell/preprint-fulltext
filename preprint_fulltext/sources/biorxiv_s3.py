"""biorxiv_s3.py — authoritative bulk corpus via the requester-pays S3 buckets.

CORRECTNESS-CRITICAL invariants:
  * EVERY S3 call passes ``RequestPayer="requester"`` (list_objects_v2, get_object).
  * Objects are ``.meca`` ZIPs; the article JATS is found via ``manifest.xml`` and,
    failing that, the largest ``content/*.xml``.
  * ``Current_Content/<MonthName_YYYY>/`` is the only date-addressable prefix;
    ``Back_Content/`` holds undated ``Batch_[nn]/`` folders (opt-in only).
  * Bytes downloaded are tracked for requester-pays cost visibility; objects are
    streamed one at a time (never the whole bucket in memory).
"""

from __future__ import annotations

import datetime as dt
import io
import re
import zipfile
from collections.abc import Iterator

from ..config import Settings, get_settings
from ..core.assemble import build_fulltext
from ..core.cache import Cache
from ..core.jats import parse_jats
from ..core.models import FullText, Server, SourceName
from .base import SourceError

_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_XLINK = "http://www.w3.org/1999/xlink"
# bioRxiv/medRxiv DOIs embed the posting date after ANY openRxiv prefix:
# legacy CSHL 10.1101/YYYY.MM.DD.NNNNNN and current openRxiv 10.64898/YYYY.MM.DD.NNNNNNNN
# (the trailing number is 6 or 8 digits). Match the prefix generically.
_DOI_DATE_RE = re.compile(r"10\.\d+/(\d{4})\.(\d{2})\.(\d{2})\.")


def month_folder(d: dt.date) -> str:
    return f"{_MONTHS[d.month - 1]}_{d.year}"


def parse_month_folder(name: str) -> dt.date | None:
    """'June_2025' -> date(2025, 6, 1); None if not a Month_Year folder."""
    try:
        mon, year = name.split("_")
        return dt.date(int(year), _MONTHS.index(mon) + 1, 1)
    except (ValueError, IndexError):
        return None


def doi_posting_date(doi: str) -> dt.date | None:
    m = _DOI_DATE_RE.search(doi)
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def extract_article_xml(meca_bytes: bytes) -> bytes | None:
    """Locate the article JATS inside a ``.meca`` zip (manifest-first, size-fallback)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(meca_bytes))
    except zipfile.BadZipFile:
        return None
    with zf:
        names = zf.namelist()
        # 1) manifest.xml points at the article instance href.
        if "manifest.xml" in names:
            try:
                from lxml import etree

                man = etree.fromstring(
                    zf.read("manifest.xml"),
                    parser=etree.XMLParser(recover=True, no_network=True, load_dtd=False),
                )
                for inst in man.iter():
                    if inst.tag.endswith("instance"):
                        href = inst.get(f"{{{_XLINK}}}href") or inst.get("href")
                        if href and href.lower().endswith(".xml") and href in names:
                            return zf.read(href)
            except Exception:
                pass  # fall through to size heuristic
        # 2) largest content/*.xml.
        xmls = [n for n in names if n.lower().endswith(".xml") and n.lower() != "manifest.xml"]
        content_xmls = [n for n in xmls if n.startswith("content/")] or xmls
        if not content_xmls:
            return None
        largest = max(content_xmls, key=lambda n: zf.getinfo(n).file_size)
        return zf.read(largest)


class BiorxivS3:
    name = "biorxiv_s3"

    def __init__(self, settings: Settings | None = None, client=None, cache: Cache | None = None):
        self.settings = settings or get_settings()
        self._client = client
        self.cache = cache or Cache(settings=self.settings)
        self.bytes_downloaded = 0

    @property
    def client(self):
        if self._client is None:
            try:
                import boto3

                if boto3.Session().get_credentials() is None:
                    raise SourceError(
                        "AWS credentials required for the requester-pays openRxiv S3 "
                        "buckets. Configure the standard boto3 credential chain "
                        "(env vars, ~/.aws/credentials, or an instance role)."
                    )
                self._client = boto3.client("s3", region_name=self.settings.aws_region)
            except ImportError as e:  # pragma: no cover
                raise SourceError("boto3 is required for the S3 source") from e
        return self._client

    def _bucket(self, server: Server | str) -> str:
        return self.settings.bucket_for(Server(server).value)

    # --- listing --------------------------------------------------------------
    def iter_keys(
        self,
        server: Server | str,
        *,
        since: dt.date | None = None,
        include_back_content: bool = False,
    ) -> Iterator[str]:
        """Yield ``.meca`` object keys for a server, newest month-folders honoured.

        ``since`` filters ``Current_Content`` month folders on a real date (so
        October does not sort before June). ``Back_Content`` is opt-in and undated.
        """
        bucket = self._bucket(server)
        prefixes = ["Current_Content/"]
        if include_back_content:
            prefixes.append("Back_Content/")
        for prefix in prefixes:
            for key in self._list_prefix(bucket, prefix):
                if not key.endswith(".meca"):
                    continue
                if since and prefix == "Current_Content/":
                    folder = key.split("/")[1] if key.count("/") >= 2 else ""
                    fdate = parse_month_folder(folder)
                    if fdate is not None and fdate < since.replace(day=1):
                        continue
                yield key

    def _list_prefix(self, bucket: str, prefix: str) -> Iterator[str]:
        token = None
        while True:
            kwargs = dict(Bucket=bucket, Prefix=prefix, RequestPayer="requester")
            if token:
                kwargs["ContinuationToken"] = token
            resp = self.client.list_objects_v2(**kwargs)
            for obj in resp.get("Contents", []):
                yield obj["Key"]
            if not resp.get("IsTruncated"):
                return
            token = resp.get("NextContinuationToken")

    # --- fetch ----------------------------------------------------------------
    def fetch_meca(self, server: Server | str, key: str) -> bytes:
        """Download one ``.meca`` (cached), counting requester-pays bytes."""
        bucket = self._bucket(server)
        cache_key = self.cache.key("biorxiv_s3", bucket, key)

        def _download() -> bytes:
            obj = self.client.get_object(Bucket=bucket, Key=key, RequestPayer="requester")
            data = obj["Body"].read()
            self.bytes_downloaded += len(data)
            return data

        return self.cache.get_or_fetch(cache_key, _download)

    def parse_meca(self, meca_bytes: bytes, server: Server | str, key: str) -> FullText | None:
        xml = extract_article_xml(meca_bytes)
        if not xml:
            return None
        parsed = parse_jats(xml)
        doi = parsed.doi or ""
        if not doi and not parsed.sections:
            return None
        return build_fulltext(
            parsed,
            doi=doi,
            server=Server(server),
            source=SourceName.BIORXIV_S3,
            raw_ref=f"s3://{self._bucket(server)}/{key}",
            provenance={"source": "biorxiv_s3", "s3_key": key},
        )

    # --- bulk + single --------------------------------------------------------
    def iter_fulltext(
        self,
        server: Server | str,
        *,
        since: dt.date | None = None,
        include_back_content: bool = False,
        max_items: int | None = None,
    ) -> Iterator[FullText]:
        n = 0
        for key in self.iter_keys(server, since=since, include_back_content=include_back_content):
            meca = self.fetch_meca(server, key)
            ft = self.parse_meca(meca, server, key)
            if ft is None:
                continue
            yield ft
            n += 1
            if max_items is not None and n >= max_items:
                return

    def get_fulltext(
        self,
        doi: str,
        version: int | None = None,
        server: Server | str | None = None,
        *,
        max_scan: int = 500,
    ) -> FullText | None:
        """Best-effort single-DOI retrieval. The bucket has NO DOI->object index, so
        we scan the DOI's posting-month folder and match the article DOI inside each
        ``.meca``. This costs requester-pays bytes and is capped by ``max_scan``.
        """
        servers = [Server(server)] if server else [Server.BIORXIV, Server.MEDRXIV]
        posting = doi_posting_date(doi)
        since = posting.replace(day=1) if posting else None
        for srv in servers:
            scanned = 0
            for key in self.iter_keys(srv, since=since):
                # Restrict to the posting month folder when known (bounded cost).
                if posting is not None and f"/{month_folder(posting)}/" not in key:
                    continue
                meca = self.fetch_meca(srv, key)
                ft = self.parse_meca(meca, srv, key)
                scanned += 1
                if ft is not None and ft.preprint.doi == doi:
                    if version is not None:
                        ft.preprint.version = version
                    return ft
                if scanned >= max_scan:
                    break
        return None


__all__ = ["BiorxivS3", "extract_article_xml", "month_folder", "parse_month_folder", "doi_posting_date"]
