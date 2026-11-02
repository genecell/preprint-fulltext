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
import sqlite3
import struct
import zipfile
import zlib
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings, get_settings
from ..core.assemble import build_fulltext
from ..core.cache import Cache
from ..core.jats import parse_jats
from ..core.models import FullText, Server, SourceName
from ..core.render import TextOptions
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


_SKIP_MECA_XML = {"manifest.xml", "directives.xml", "transfer.xml"}


@dataclass(frozen=True)
class ZipXmlEntry:
    xml_filename: str
    xml_stem: str
    lfh_offset: int
    compress_size: int
    uncompress_size: int
    compress_method: int
    fn_len: int


def extract_zip_xml_entry(tail: bytes, total_size: int | None = None) -> ZipXmlEntry | None:
    """Parse the PKZIP End-of-Central-Directory + Central Directory from the last 4-64 KB of a ``.meca``.

    Returns the :class:`ZipXmlEntry` for the article JATS XML inside ``content/*.xml``,
    or ``None`` if the buffer is not a standard ZIP or has no article XML entry.
    """
    eocd_pos = tail.rfind(b"PK\x05\x06")
    if eocd_pos < 0 or eocd_pos + 22 > len(tail):
        return None
    try:
        (
            _sig,
            _disk,
            _cd_disk,
            _disk_entries,
            total_entries,
            cd_size,
            cd_offset,
            _comment_len,
        ) = struct.unpack("<4sHHHHIIH", tail[eocd_pos : eocd_pos + 22])
    except struct.error:
        return None
    if cd_offset == 0xFFFFFFFF or cd_size == 0xFFFFFFFF or total_entries == 0:
        return None
    if total_size is not None and total_size >= len(tail):
        tail_start = total_size - len(tail)
        cd_rel = cd_offset - tail_start
    else:
        cd_rel = eocd_pos - cd_size
    if cd_rel < 0 or cd_rel + cd_size > len(tail):
        return None
    cd_buf = tail[cd_rel : cd_rel + cd_size]
    candidates: list[ZipXmlEntry] = []
    pos = 0
    for _ in range(total_entries):
        if pos + 46 > len(cd_buf) or cd_buf[pos : pos + 4] != b"PK\x01\x02":
            break
        hdr = struct.unpack("<4sHHHHHHIIIHHHHHII", cd_buf[pos : pos + 46])
        compress_method = hdr[4]
        compress_size = hdr[8]
        uncompress_size = hdr[9]
        fn_len = hdr[10]
        extra_len = hdr[11]
        comment_len = hdr[12]
        lfh_offset = hdr[16]
        raw_name = cd_buf[pos + 46 : pos + 46 + fn_len]
        pos += 46 + fn_len + extra_len + comment_len
        filename = raw_name.replace(b"\\", b"/").decode("utf-8", errors="replace").lstrip("/")
        base = filename.rsplit("/", 1)[-1].lower()
        if not base.endswith(".xml") or base in _SKIP_MECA_XML:
            continue
        stem = filename.rsplit("/", 1)[-1][:-4]
        candidates.append(
            ZipXmlEntry(
                xml_filename=filename,
                xml_stem=stem,
                lfh_offset=lfh_offset,
                compress_size=compress_size,
                uncompress_size=uncompress_size,
                compress_method=compress_method,
                fn_len=fn_len,
            )
        )
    if not candidates:
        return None
    content_cands = [c for c in candidates if c.xml_filename.startswith("content/")] or candidates
    return max(content_cands, key=lambda c: c.uncompress_size)


def _next_month(d: dt.date) -> dt.date:
    if d.month == 12:
        return dt.date(d.year + 1, 1, 1)
    return dt.date(d.year, d.month + 1, 1)


def _doi_tail(doi: str) -> str:
    suffix = doi.split("/", 1)[-1] if "/" in doi else doi
    return suffix.rsplit(".", 1)[-1]


class S3Index:
    """Persistent SQLite index mapping S3 ``.meca`` keys to their internal XML filename & byte offsets."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS s3_objects (
                    server TEXT NOT NULL,
                    s3_key TEXT NOT NULL,
                    folder TEXT NOT NULL,
                    etag TEXT NOT NULL DEFAULT '',
                    size INTEGER NOT NULL DEFAULT 0,
                    xml_stem TEXT,
                    xml_filename TEXT,
                    lfh_offset INTEGER,
                    compress_size INTEGER,
                    uncompress_size INTEGER,
                    compress_method INTEGER,
                    fn_len INTEGER,
                    PRIMARY KEY (server, s3_key)
                );
                CREATE INDEX IF NOT EXISTS idx_s3_objects_folder
                    ON s3_objects (server, folder);
                CREATE INDEX IF NOT EXISTS idx_s3_objects_stem
                    ON s3_objects (server, folder, xml_stem);
                """
            )

    def get_folder_rows(self, server: str, folder: str) -> dict[str, dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM s3_objects WHERE server = ? AND folder = ?",
                (server, folder),
            ).fetchall()
        return {r["s3_key"]: dict(r) for r in rows}

    def upsert_rows(self, rows: list[tuple]) -> None:
        if not rows:
            return
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO s3_objects (
                    server, s3_key, folder, etag, size,
                    xml_stem, xml_filename, lfh_offset,
                    compress_size, uncompress_size, compress_method, fn_len
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (server, s3_key) DO UPDATE SET
                    folder = excluded.folder,
                    etag = excluded.etag,
                    size = excluded.size,
                    xml_stem = excluded.xml_stem,
                    xml_filename = excluded.xml_filename,
                    lfh_offset = excluded.lfh_offset,
                    compress_size = excluded.compress_size,
                    uncompress_size = excluded.uncompress_size,
                    compress_method = excluded.compress_method,
                    fn_len = excluded.fn_len
                """,
                rows,
            )


def extract_article_xml(meca_bytes: bytes) -> bytes | None:
    """Locate the article JATS inside a ``.meca`` zip (manifest-first, size-fallback)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(meca_bytes))
    except zipfile.BadZipFile:
        return None
    with zf:
        names = zf.namelist()
        # 1) manifest.xml points at the article instance href.
        # Real bioRxiv .meca manifests often write Windows backslashes (e.g. "content\007724.xml")
        # and also list directives.xml / transfer.xml as XML instances.
        if "manifest.xml" in names:
            try:
                from lxml import etree

                man = etree.fromstring(
                    zf.read("manifest.xml"),
                    parser=etree.XMLParser(recover=True, no_network=True, load_dtd=False),
                )
                for inst in man.iter():
                    if not isinstance(inst.tag, str) or not inst.tag.endswith("instance"):
                        continue
                    parent = inst.getparent()
                    if parent is not None:
                        ptype = (parent.get("type") or parent.get("item-type") or "").lower()
                        if ptype in ("directive", "transfer"):
                            continue
                    raw_href = inst.get(f"{{{_XLINK}}}href") or inst.get("href")
                    if not raw_href:
                        continue
                    href = raw_href.replace("\\", "/").lstrip("/")
                    base = href.rsplit("/", 1)[-1].lower()
                    if base in _SKIP_MECA_XML:
                        continue
                    if href.lower().endswith(".xml") and href in names:
                        return zf.read(href)
            except Exception:
                pass  # fall through to size heuristic
        # 2) largest content/*.xml (excluding MECA packaging XMLs).
        xmls = [
            n
            for n in names
            if n.lower().endswith(".xml") and n.rsplit("/", 1)[-1].lower() not in _SKIP_MECA_XML
        ]
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
        self.index = S3Index(self.cache.dir / "s3_index.sqlite")
        self.bytes_downloaded = 0
        self.last_error: str | None = None

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
        for obj in self._list_prefix_objects(bucket, prefix):
            yield obj["Key"]

    def _list_prefix_objects(self, bucket: str, prefix: str) -> Iterator[dict]:
        token = None
        while True:
            kwargs = dict(Bucket=bucket, Prefix=prefix, RequestPayer="requester")
            if token:
                kwargs["ContinuationToken"] = token
            resp = self.client.list_objects_v2(**kwargs)
            for obj in resp.get("Contents", []) or []:
                yield obj
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

    def fetch_meca_xml_range(
        self,
        server: Server | str,
        key: str,
        entry: ZipXmlEntry,
    ) -> bytes | None:
        """Download and inflate ONLY the compressed ``content/*.xml`` byte range (~20 KB)."""
        bucket = self._bucket(server)
        cache_key = self.cache.key("biorxiv_s3_xml", bucket, key, entry.xml_filename)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        end_byte = entry.lfh_offset + 30 + entry.fn_len + 256 + entry.compress_size
        try:
            obj = self.client.get_object(
                Bucket=bucket,
                Key=key,
                RequestPayer="requester",
                Range=f"bytes={entry.lfh_offset}-{end_byte}",
            )
            chunk = obj["Body"].read()
            self.bytes_downloaded += len(chunk)
            base = -1
            if chunk[:4] == b"PK\x03\x04":
                base = 0
            elif (
                len(chunk) > entry.lfh_offset + 30
                and chunk[entry.lfh_offset : entry.lfh_offset + 4] == b"PK\x03\x04"
            ):
                base = entry.lfh_offset
            if base >= 0 and len(chunk) >= base + 30:
                fn_len_local, extra_len_local = struct.unpack("<HH", chunk[base + 26 : base + 30])
                data_start = base + 30 + fn_len_local + extra_len_local
                data_end = data_start + entry.compress_size
                if data_end <= len(chunk):
                    raw = chunk[data_start:data_end]
                    if entry.compress_method == 8:
                        xml_bytes = zlib.decompress(raw, -15)
                        self.cache.put(cache_key, xml_bytes)
                        return xml_bytes
                    if entry.compress_method == 0:
                        self.cache.put(cache_key, raw)
                        return raw
        except Exception:
            pass

        # Fallback: full .meca download if extra field >256B or non-standard compression
        meca = self.fetch_meca(server, key)
        xml_bytes = extract_article_xml(meca)
        if xml_bytes:
            self.cache.put(cache_key, xml_bytes)
        return xml_bytes

    def parse_xml_bytes(
        self,
        xml: bytes,
        server: Server | str,
        key: str,
        *,
        options: TextOptions | None = None,
    ) -> FullText | None:
        parsed = parse_jats(xml, options=options)
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

    def parse_meca(
        self,
        meca_bytes: bytes,
        server: Server | str,
        key: str,
        *,
        options: TextOptions | None = None,
    ) -> FullText | None:
        xml = extract_article_xml(meca_bytes)
        if not xml:
            return None
        return self.parse_xml_bytes(xml, server, key, options=options)

    def index_folder(
        self,
        server: Server | str,
        folder: str,
        *,
        max_scan: int | None = None,
        max_workers: int = 32,
    ) -> list[dict]:
        """List ``folder`` (e.g. ``Current_Content/November_2018``) and index any unindexed
        ``.meca`` Central Directories via 4 KB suffix Range requests into SQLite.
        """
        srv = Server(server)
        bucket = self._bucket(srv)
        clean_folder = folder.strip("/")
        objs = [
            o
            for o in self._list_prefix_objects(bucket, f"{clean_folder}/")
            if o.get("Key", "").endswith(".meca")
        ]
        if max_scan is not None:
            objs = objs[:max_scan]
        if not objs:
            return []

        existing = self.index.get_folder_rows(srv.value, clean_folder)
        to_inspect: list[dict] = []
        for o in objs:
            k = o["Key"]
            etag = (o.get("ETag") or "").strip('"')
            size = int(o.get("Size") or 0)
            row = existing.get(k)
            if row is not None and row.get("etag") == etag and row.get("size") == size:
                continue
            to_inspect.append(o)

        def _inspect_one(o: dict) -> tuple[tuple, int, tuple[str, bytes] | None]:
            k = o["Key"]
            etag = (o.get("ETag") or "").strip('"')
            size = int(o.get("Size") or 0)
            bytes_used = 0
            entry: ZipXmlEntry | None = None
            cached_xml: tuple[str, bytes] | None = None
            try:
                range_hdr = (
                    f"bytes={size - 4096}-{size - 1}" if size > 4096 else "bytes=-4096"
                )
                resp = self.client.get_object(
                    Bucket=bucket,
                    Key=k,
                    RequestPayer="requester",
                    Range=range_hdr,
                )
                tail = resp["Body"].read()
                bytes_used += len(tail)
                entry = extract_zip_xml_entry(tail, total_size=size if size > 0 else None)
                if entry is None and size > 4096:
                    range_hdr2 = (
                        f"bytes={max(0, size - 65536)}-{size - 1}"
                        if size > 65536
                        else f"bytes=0-{size - 1}"
                    )
                    resp2 = self.client.get_object(
                        Bucket=bucket,
                        Key=k,
                        RequestPayer="requester",
                        Range=range_hdr2,
                    )
                    tail2 = resp2["Body"].read()
                    bytes_used += len(tail2)
                    entry = extract_zip_xml_entry(tail2, total_size=size if size > 0 else None)
                elif (
                    entry is not None
                    and len(tail) < 4096
                    and tail[:4] == b"PK\x03\x04"
                ):
                    # Entire tiny .meca was returned in the 4 KB Range call (e.g. unit tests)
                    xml_b = extract_article_xml(tail)
                    if xml_b:
                        ck = self.cache.key("biorxiv_s3_xml", bucket, k, entry.xml_filename)
                        cached_xml = (ck, xml_b)
            except Exception:
                entry = None

            row_tuple = (
                srv.value,
                k,
                clean_folder,
                etag,
                size,
                entry.xml_stem if entry else None,
                entry.xml_filename if entry else None,
                entry.lfh_offset if entry else None,
                entry.compress_size if entry else None,
                entry.uncompress_size if entry else None,
                entry.compress_method if entry else None,
                entry.fn_len if entry else None,
            )
            return row_tuple, bytes_used, cached_xml

        if to_inspect:
            new_rows: list[tuple] = []
            if len(to_inspect) <= 4 or max_workers <= 1:
                results = [_inspect_one(o) for o in to_inspect]
            else:
                with ThreadPoolExecutor(max_workers=min(max_workers, len(to_inspect))) as pool:
                    results = list(pool.map(_inspect_one, to_inspect))
            for row_tuple, b_used, cached_xml in results:
                self.bytes_downloaded += b_used
                new_rows.append(row_tuple)
                if cached_xml is not None:
                    self.cache.put(cached_xml[0], cached_xml[1])
            self.index.upsert_rows(new_rows)
            existing = self.index.get_folder_rows(srv.value, clean_folder)

        return [existing[o["Key"]] for o in objs if o["Key"] in existing]

    # --- bulk + single --------------------------------------------------------
    def iter_fulltext(
        self,
        server: Server | str,
        *,
        since: dt.date | None = None,
        include_back_content: bool = False,
        max_items: int | None = None,
        options: TextOptions | None = None,
    ) -> Iterator[FullText]:
        n = 0
        for key in self.iter_keys(server, since=since, include_back_content=include_back_content):
            meca = self.fetch_meca(server, key)
            ft = self.parse_meca(meca, server, key, options=options)
            if ft is None:
                continue
            yield ft
            n += 1
            if max_items is not None and n >= max_items:
                return

    def _candidate_folders(
        self,
        doi: str,
        candidate_dates: list[dt.date | str] | None = None,
        *,
        include_back_content: bool = False,
    ) -> list[str]:
        dates: list[dt.date] = []
        if candidate_dates:
            for cd in reversed(candidate_dates):
                if isinstance(cd, dt.date):
                    dates.append(cd)
                elif isinstance(cd, str):
                    try:
                        dates.append(dt.date.fromisoformat(cd[:10]))
                    except ValueError:
                        pass
        posting = doi_posting_date(doi)
        if posting and posting not in dates:
            dates.append(posting)
        if not dates:
            return []

        primary: list[str] = []
        rollover: list[str] = []
        back_batches: list[str] = []
        for d in dates:
            if d >= dt.date(2018, 12, 1):
                f1 = f"Current_Content/{month_folder(d)}"
                if f1 not in primary:
                    primary.append(f1)
                f2 = f"Current_Content/{month_folder(_next_month(d))}"
                if f2 not in primary and f2 not in rollover:
                    rollover.append(f2)
            elif d >= dt.date(2018, 11, 1):
                for m_name in (
                    "Current_Content/November_2018",
                    "Current_Content/December_2018",
                ):
                    if m_name not in primary:
                        primary.append(m_name)
            elif include_back_content:
                for m_name in (
                    "Current_Content/November_2018",
                    "Current_Content/December_2018",
                ):
                    if m_name not in rollover:
                        rollover.append(m_name)
                # Pre-Nov 2018 papers without a later revision live in Back_Content/Batch_01..Batch_28.
                tail = _doi_tail(doi)
                if tail.isdigit():
                    ms_num = int(tail)
                    est = max(1, min(28, round((ms_num / 485000.0) * 28)))
                    for delta in (0, -1, 1, -2, 2, -3, 3):
                        b_idx = est + delta
                        if 1 <= b_idx <= 28:
                            bf = f"Back_Content/Batch_{b_idx:02d}"
                            if bf not in back_batches:
                                back_batches.append(bf)
        return primary + [f for f in rollover if f not in primary] + back_batches

    def get_fulltext(
        self,
        doi: str,
        version: int | None = None,
        server: Server | str | None = None,
        *,
        max_scan: int = 5000,
        options: TextOptions | None = None,
        candidate_dates: list[dt.date | str] | None = None,
        include_back_content: bool = False,
    ) -> FullText | None:
        """Retrieve a single DOI from S3 using the persistent SQLite Central-Directory
        index and 2-step PKZIP ``Range`` extraction (~24 KB total per paper instead of
        scanning gigabytes of full ``.meca`` archives).
        """
        self.last_error = None
        folders = self._candidate_folders(
            doi,
            candidate_dates=candidate_dates,
            include_back_content=include_back_content,
        )
        if not folders:
            self.last_error = f"cannot infer S3 month folder from DOI {doi!r}"
            return None

        servers = [Server(server)] if server else [Server.BIORXIV, Server.MEDRXIV]
        tail = _doi_tail(doi)
        suffix = doi.split("/", 1)[-1] if "/" in doi else doi
        exact_stems = {tail, suffix}
        generic_stems = {"article", "main"}
        best: FullText | None = None
        primary_folder = folders[0]
        primary_scanned = 0

        for srv in servers:
            for f_idx, folder in enumerate(folders):
                rows = self.index_folder(srv, folder, max_scan=max_scan)
                if f_idx == 0 and primary_scanned == 0:
                    primary_scanned = len(rows)
                if not rows:
                    continue
                exact = [r for r in rows if r.get("xml_stem") in exact_stems]
                generic = [r for r in rows if r.get("xml_stem") in generic_stems]
                for r in exact + generic:
                    if not r.get("xml_filename") or r.get("lfh_offset") is None:
                        continue
                    entry = ZipXmlEntry(
                        xml_filename=r["xml_filename"],
                        xml_stem=r["xml_stem"] or "",
                        lfh_offset=int(r["lfh_offset"]),
                        compress_size=int(r["compress_size"] or 0),
                        uncompress_size=int(r["uncompress_size"] or 0),
                        compress_method=int(r["compress_method"] or 0),
                        fn_len=int(r["fn_len"] or 0),
                    )
                    xml = self.fetch_meca_xml_range(srv, r["s3_key"], entry)
                    if not xml:
                        continue
                    ft = self.parse_xml_bytes(xml, srv, r["s3_key"], options=options)
                    if ft is not None and ft.preprint.doi and ft.preprint.doi.lower() == doi.lower():
                        if version is not None:
                            if ft.preprint.version == version:
                                return ft
                            if best is None:
                                ft.preprint.version = version
                                best = ft
                        else:
                            return ft
                if best is not None:
                    return best

        self.last_error = (
            f"DOI {doi} not found in {primary_folder} (scanned {primary_scanned} archives)"
        )
        return None


__all__ = [
    "BiorxivS3",
    "S3Index",
    "ZipXmlEntry",
    "doi_posting_date",
    "extract_article_xml",
    "extract_zip_xml_entry",
    "month_folder",
    "parse_month_folder",
]
