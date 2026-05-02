import ctypes
import gzip
import hashlib
import os
import platform
import re
import shutil
import struct
import zlib
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import unquote, urlsplit


FANTAGE_URL_RE = re.compile(
    rb'https?://[^\s<>"\'\x00\x01-\x1f]*fantage\.com[^\s<>"\'\x00\x01-\x1f]*',
    re.IGNORECASE,
)

IE_COPY_SUFFIX_RE = re.compile(r"\[\d+\](?=\.[^.]+$|$)")
CHROME_EXTERNAL_FILE_RE = re.compile(r"^f_([0-9a-f]{6})$", re.IGNORECASE)
CHROME_SIMPLE_CACHE_FILE_RE = re.compile(r"^[0-9a-f]{8,}_(?:0|1|s)$", re.IGNORECASE)
FIREFOX_CACHE1_EXTERNAL_RE = re.compile(
    r"^(?P<prefix>[0-9a-f]{5}|[0-9a-f]{8})(?P<kind>[dm])(?P<generation>[0-9a-f]{2})$",
    re.IGNORECASE,
)
QUERY_SAFE_HASH_LEN = 8
MAX_DECODE_FILE_SIZE = 128 * 1024 * 1024
URL_SNIFF_HEAD_BYTES = 1024 * 1024
URL_SNIFF_TAIL_BYTES = 1024 * 1024
FIREFOX_CACHE2_CHUNK_SIZES = (256 * 1024, 512 * 1024)


USEFUL_URL_EXTENSIONS = {
    ".bmp",
    ".css",
    ".do",
    ".flv",
    ".gif",
    ".htm",
    ".html",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".manifest",
    ".m4a",
    ".m4v",
    ".mp3",
    ".mp4",
    ".ogg",
    ".php",
    ".png",
    ".swf",
    ".txt",
    ".wav",
    ".webm",
    ".webp",
    ".xml",
}


CONTENT_TYPE_EXTENSIONS = (
    (b"application/x-shockwave-flash", ".swf"),
    (b"application/vnd.adobe.flash.movie", ".swf"),
    (b"application/javascript", ".js"),
    (b"text/javascript", ".js"),
    (b"application/json", ".json"),
    (b"text/css", ".css"),
    (b"text/html", ".html"),
    (b"text/xml", ".xml"),
    (b"application/xml", ".xml"),
    (b"image/png", ".png"),
    (b"image/jpeg", ".jpg"),
    (b"image/gif", ".gif"),
    (b"audio/mpeg", ".mp3"),
    (b"video/mp4", ".mp4"),
)


@dataclass(frozen=True)
class DecodedEntry:
    source_path: str
    url: str
    payload: Optional[bytes] = None
    file_extension: str = ""


def decode_browser_cache_source(source_root: str, destination_root: str, copied_paths: set) -> int:
    copied = 0
    seen_targets = set()

    for entry in _decode_ie_index_dat_entries(source_root):
        if _copy_decoded_entry(entry, destination_root, copied_paths, seen_targets):
            copied += 1

    for entry in _decode_chromium_disk_cache_entries(source_root):
        if _copy_decoded_entry(entry, destination_root, copied_paths, seen_targets):
            copied += 1

    for entry in _decode_firefox_cache1_external_entries(source_root):
        if _copy_decoded_entry(entry, destination_root, copied_paths, seen_targets):
            copied += 1

    for entry in _decode_metadata_embedded_entries(source_root):
        if _copy_decoded_entry(entry, destination_root, copied_paths, seen_targets):
            copied += 1

    return copied


def decode_windows_wininet_cache(destination_root: str, copied_paths: set) -> int:
    if platform.system() != "Windows":
        return 0

    copied = 0
    seen_targets = set()
    for entry in _iter_wininet_entries():
        if _copy_decoded_entry(entry, destination_root, copied_paths, seen_targets):
            copied += 1
    return copied


def _copy_decoded_entry(entry: DecodedEntry, destination_root: str, copied_paths: set, seen_targets: set) -> bool:
    if not entry.url or "fantage.com" not in entry.url.lower():
        return False

    try:
        source_key = os.path.normcase(os.path.abspath(entry.source_path))
    except OSError:
        source_key = entry.source_path
    if source_key in copied_paths and entry.payload is None:
        return False

    payload = entry.payload
    if payload is None:
        try:
            if not os.path.isfile(entry.source_path):
                return False
            payload = _read_file(entry.source_path)
        except OSError:
            return False

    if not payload:
        return False

    payload = _maybe_decompress_http_payload(payload)
    payload = _trim_known_payload(payload)
    destination_path = _destination_for_url(destination_root, entry.url, payload, entry.file_extension)
    destination_key = os.path.normcase(os.path.abspath(destination_path))

    if destination_key in seen_targets:
        destination_path = _dedupe_destination(destination_path, payload)
        destination_key = os.path.normcase(os.path.abspath(destination_path))

    if os.path.exists(destination_path):
        if _file_has_same_bytes(destination_path, payload):
            copied_paths.add(source_key)
            seen_targets.add(destination_key)
            return False
        destination_path = _dedupe_destination(destination_path, payload)
        destination_key = os.path.normcase(os.path.abspath(destination_path))

    try:
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        with open(destination_path, "wb") as handle:
            handle.write(payload)
        if entry.payload is None:
            try:
                shutil.copystat(entry.source_path, destination_path)
            except OSError:
                pass
        copied_paths.add(source_key)
        seen_targets.add(destination_key)
        return True
    except OSError:
        return False


def _read_file(path: str, limit: int = MAX_DECODE_FILE_SIZE) -> bytes:
    size = os.path.getsize(path)
    if size <= 0 or size > limit:
        return b""
    with open(path, "rb") as handle:
        return handle.read()


def _read_url_sniff(path: str) -> bytes:
    try:
        size = os.path.getsize(path)
    except OSError:
        return b""
    if size <= 0:
        return b""
    with open(path, "rb") as handle:
        if size <= URL_SNIFF_HEAD_BYTES + URL_SNIFF_TAIL_BYTES:
            return handle.read()
        head = handle.read(URL_SNIFF_HEAD_BYTES)
        handle.seek(max(0, size - URL_SNIFF_TAIL_BYTES))
        tail = handle.read(URL_SNIFF_TAIL_BYTES)
        return head + tail


def _destination_for_url(destination_root: str, url: str, payload: bytes, file_extension: str = "") -> str:
    parsed = urlsplit(url)
    host = _sanitize_component((parsed.netloc or "unknown-host").split("@")[-1].lower())
    path = unquote(parsed.path or "")
    parts = [_sanitize_component(part) for part in path.split("/") if part and part not in {".", ".."}]

    if not parts:
        parts = ["index"]

    basename = parts[-1]
    stem, ext = os.path.splitext(basename)
    if not ext:
        ext = file_extension or _infer_extension(payload, url)
        if ext:
            parts[-1] = f"{basename}{ext}"

    return os.path.join(destination_root, "Decoded", host, *parts)


def _dedupe_destination(path: str, payload: bytes) -> str:
    directory, basename = os.path.split(path)
    stem, ext = os.path.splitext(basename)
    digest = hashlib.sha1(payload).hexdigest()[:QUERY_SAFE_HASH_LEN]
    candidate = os.path.join(directory, f"{stem}_{digest}{ext}")
    if not os.path.exists(candidate):
        return candidate

    index = 2
    while True:
        candidate = os.path.join(directory, f"{stem}_{digest}_{index}{ext}")
        if not os.path.exists(candidate):
            return candidate
        index += 1


def _sanitize_component(value: str) -> str:
    value = value.replace("\\", "_").replace("/", "_")
    value = re.sub(r'[<>:"|?*\x00-\x1f]+', "_", value)
    value = value.strip(" .")
    return value or "unnamed"


def _file_has_same_bytes(path: str, payload: bytes) -> bool:
    try:
        if os.path.getsize(path) != len(payload):
            return False
        with open(path, "rb") as handle:
            return handle.read() == payload
    except OSError:
        return False


def _infer_extension(payload: bytes, url: str = "") -> str:
    lower_url = url.lower()
    for marker, extension in CONTENT_TYPE_EXTENSIONS:
        if marker in payload[:4096].lower():
            return extension
    if payload.startswith((b"FWS", b"CWS", b"ZWS")):
        return ".swf"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if payload.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if payload.startswith(b"BM"):
        return ".bmp"
    if payload.startswith(b"\x00\x00\x00") and b"ftyp" in payload[:16]:
        return ".mp4"
    if payload[:128].lstrip().lower().startswith((b"<!doctype html", b"<html")):
        return ".html"
    if payload[:128].lstrip().startswith((b"<?xml", b"<cross-domain-policy", b"<config", b"<list")):
        return ".xml"
    _, extension = os.path.splitext(urlsplit(lower_url).path)
    if extension in USEFUL_URL_EXTENSIONS:
        return extension
    return ""


def _trim_known_payload(payload: bytes) -> bytes:
    if len(payload) < 8:
        return payload

    if payload.startswith(b"FWS"):
        declared_size = struct.unpack_from("<I", payload, 4)[0]
        if 8 <= declared_size <= len(payload):
            return payload[:declared_size]
        return payload

    if payload.startswith(b"CWS"):
        try:
            decompressor = zlib.decompressobj()
            decompressor.decompress(payload[8:])
            consumed = len(payload[8:]) - len(decompressor.unused_data)
            if consumed > 0:
                return payload[: 8 + consumed]
        except zlib.error:
            return payload

    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        marker = payload.find(b"IEND")
        if marker >= 0 and marker + 8 <= len(payload):
            return payload[: marker + 8]

    if payload.startswith(b"\xff\xd8\xff"):
        marker = payload.rfind(b"\xff\xd9")
        if marker >= 0:
            return payload[: marker + 2]

    if payload.startswith((b"GIF87a", b"GIF89a")):
        marker = payload.rfind(b"\x3b")
        if marker >= 0:
            return payload[: marker + 1]

    return payload


def _maybe_decompress_http_payload(payload: bytes) -> bytes:
    if not payload.startswith(b"\x1f\x8b"):
        return payload
    try:
        decompressed = gzip.decompress(payload)
    except (OSError, EOFError):
        return payload
    return decompressed or payload


def _extract_fantage_urls(blob: bytes) -> List[str]:
    urls = []
    seen = set()
    for match in FANTAGE_URL_RE.finditer(blob):
        raw_url = match.group(0).rstrip(b".,);]")
        try:
            url = raw_url.decode("utf-8", "ignore")
        except UnicodeDecodeError:
            continue
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _looks_like_http_cache_metadata(path: str, data: bytes, urls: Sequence[str]) -> bool:
    basename = os.path.basename(path).lower()
    if not urls:
        return False

    if not _is_embedded_metadata_cache_blob(path):
        return False

    extension = os.path.splitext(basename)[1].lower()
    if extension:
        return False

    if data.startswith((b"FWS", b"CWS", b"ZWS", b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"BM")):
        return True
    if CHROME_SIMPLE_CACHE_FILE_RE.match(basename):
        return True
    if _is_firefox_cache2_entry(path):
        return True
    return False


def _is_embedded_metadata_cache_blob(path: str) -> bool:
    basename = os.path.basename(path).lower()
    if basename in {"index", "index.dat", "_cache_map_"}:
        return False
    if basename.startswith("data_") or basename.startswith("_cache_"):
        return False
    if CHROME_EXTERNAL_FILE_RE.match(basename):
        return False
    return _is_firefox_cache2_entry(path) or _is_chrome_simple_cache_entry(path)


def _is_firefox_cache2_entry(path: str) -> bool:
    parts = os.path.normpath(path).lower().split(os.sep)
    basename = os.path.basename(path)
    return "cache2" in parts and len(basename) >= 16 and "." not in basename


def _is_chrome_simple_cache_entry(path: str) -> bool:
    basename = os.path.basename(path).lower()
    if not CHROME_SIMPLE_CACHE_FILE_RE.match(basename):
        return False
    parts = set(os.path.normpath(path).lower().split(os.sep))
    return bool(parts & {"cache", "code cache", "gpucache", "media cache"})


def _decode_metadata_embedded_entries(source_root: str) -> Iterator[DecodedEntry]:
    for root, _, files in os.walk(source_root):
        for file_name in files:
            path = os.path.join(root, file_name)
            try:
                sniff = _read_url_sniff(path)
            except OSError:
                continue

            urls = _extract_fantage_urls(sniff)
            if not _looks_like_http_cache_metadata(path, sniff, urls):
                continue

            try:
                data = _read_file(path)
            except OSError:
                continue
            if not data:
                continue

            urls = _metadata_embedded_urls(path, data, urls)
            if not urls:
                continue
            payload = _metadata_embedded_payload(path, data, urls)
            for url in urls:
                yield DecodedEntry(path, url, payload=payload)


def _decode_firefox_cache1_external_entries(source_root: str) -> Iterator[DecodedEntry]:
    data_files: Dict[Tuple[str, str], str] = {}
    metadata_files: List[Tuple[Tuple[str, str], str]] = []

    for root, _, files in os.walk(source_root):
        for file_name in files:
            match = FIREFOX_CACHE1_EXTERNAL_RE.match(file_name)
            if not match:
                continue

            key = (match.group("prefix").lower(), match.group("generation").lower())
            path = os.path.join(root, file_name)
            if match.group("kind").lower() == "d":
                data_files.setdefault(key, path)
            else:
                metadata_files.append((key, path))

    for key, metadata_path in metadata_files:
        data_path = data_files.get(key)
        if not data_path:
            continue
        metadata = _read_file(metadata_path)
        parsed = _parse_firefox_cache1_metadata(metadata)
        if not parsed:
            continue

        url, cached_data_size = parsed
        if "fantage.com" not in url.lower():
            continue

        payload = _read_file(data_path)
        if cached_data_size and cached_data_size <= len(payload):
            payload = payload[:cached_data_size]
        yield DecodedEntry(data_path, url, payload=payload)


def _parse_firefox_cache1_metadata(metadata: bytes) -> Optional[Tuple[str, int]]:
    if len(metadata) < 36:
        return None
    try:
        (
            major_version,
            _minor_version,
            _location,
            fetch_count,
            last_fetched_time,
            _last_modified_time,
            _expiration_time,
            cached_data_size,
            request_size,
            information_size,
        ) = struct.unpack_from(">HHIiiIIIII", metadata, 0)
    except struct.error:
        return None

    if major_version != 1:
        return None
    if request_size <= 0 or request_size > 65536:
        return None
    if information_size > MAX_DECODE_FILE_SIZE:
        return None
    if fetch_count < 0 or last_fetched_time <= 0:
        return None
    if 36 + request_size > len(metadata):
        return None

    raw_url = metadata[36 : 36 + request_size].split(b"\x00", 1)[0]
    url = raw_url.decode("ascii", "ignore")
    if not url.lower().startswith(("http://", "https://")):
        return None
    return url, cached_data_size


def _metadata_embedded_payload(path: str, data: bytes, urls: Sequence[str]) -> bytes:
    if _is_firefox_cache2_entry(path):
        content_size = _firefox_cache2_content_size(data)
        if content_size is not None:
            return data[:content_size]

    trimmed = _trim_known_payload(data)
    if len(trimmed) < len(data):
        return trimmed

    if data.startswith((b"FWS", b"CWS", b"ZWS", b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"BM")):
        return trimmed

    # Chrome simple-cache and Firefox cache2 entries often append binary metadata
    # containing the original URL after the response body. For text responses the
    # URL can also be part of the legitimate body, so only cut when there is a
    # clear binary separator immediately before the cached key.
    url_bytes = [url.encode("utf-8", "ignore") for url in urls if url]
    positions = [data.find(raw) for raw in url_bytes if raw and data.find(raw) > 0]
    if not positions:
        return data

    first_url_position = min(positions)
    separator_start = first_url_position
    while separator_start > 0 and data[separator_start - 1] in b"\x00\r\n\t :Q":
        separator_start -= 1
    if separator_start > 0 and b"\x00" in data[max(0, separator_start - 32) : first_url_position]:
        return data[:separator_start].rstrip(b"\x00\r\n")

    return data


def _metadata_embedded_urls(path: str, data: bytes, fallback_urls: Sequence[str]) -> List[str]:
    if _is_firefox_cache2_entry(path):
        key_urls = _firefox_cache2_key_urls(data)
        if key_urls:
            return key_urls

        content_size = _firefox_cache2_content_size(data)
        if content_size is not None and content_size < len(data):
            metadata_urls = _extract_fantage_urls(data[content_size:])
            if metadata_urls:
                return [metadata_urls[0]]

    if _is_chrome_simple_cache_entry(path):
        tail_urls = _extract_fantage_urls(data[-URL_SNIFF_TAIL_BYTES:])
        if tail_urls:
            return [tail_urls[-1]]
        if fallback_urls:
            return [fallback_urls[-1]]

    return list(fallback_urls)


def _firefox_cache2_content_size(data: bytes) -> Optional[int]:
    if len(data) < 4:
        return None
    content_size = struct.unpack_from(">I", data, len(data) - 4)[0]
    if 0 < content_size <= len(data) - 4:
        return content_size
    return None


def _firefox_cache2_key_urls(data: bytes) -> List[str]:
    content_size = _firefox_cache2_content_size(data)
    if content_size is None:
        return []

    for chunk_size in FIREFOX_CACHE2_CHUNK_SIZES:
        chunks = (content_size + chunk_size - 1) // chunk_size
        metadata_offset = content_size + 4 + (chunks * 2)
        if metadata_offset + 28 > len(data) - 4:
            continue

        try:
            format_version = struct.unpack_from(">I", data, metadata_offset)[0]
            key_size = struct.unpack_from(">I", data, metadata_offset + 24)[0]
        except struct.error:
            continue
        if format_version not in {1, 2, 3} or key_size <= 0 or key_size > 65536:
            continue

        key_offsets = [metadata_offset + 32, metadata_offset + 28] if format_version >= 2 else [metadata_offset + 28]
        for key_offset in key_offsets:
            if key_offset + key_size > len(data):
                continue
            key = data[key_offset : key_offset + key_size]
            urls = _extract_fantage_urls(key)
            if urls:
                return urls
    return []


def _decode_ie_index_dat_entries(source_root: str) -> Iterator[DecodedEntry]:
    index_paths = []
    for root, _, files in os.walk(source_root):
        for file_name in files:
            if file_name.lower() == "index.dat":
                index_paths.append(os.path.join(root, file_name))

    if not index_paths:
        return

    file_index = _build_ie_file_index(source_root)
    used_sources = set()
    for index_path in index_paths:
        for url, local_names in _parse_index_dat_records(index_path):
            candidates = _resolve_ie_local_candidates(index_path, source_root, url, local_names, file_index)
            for source_path in candidates:
                source_key = os.path.normcase(os.path.abspath(source_path))
                if source_key in used_sources:
                    continue
                used_sources.add(source_key)
                yield DecodedEntry(source_path, url)


def _build_ie_file_index(source_root: str) -> Dict[str, List[str]]:
    index: Dict[str, List[str]] = {}
    for root, _, files in os.walk(source_root):
        for file_name in files:
            if file_name.lower() == "index.dat":
                continue
            normalized = _normalize_ie_cache_basename(file_name)
            index.setdefault(normalized, []).append(os.path.join(root, file_name))
    return index


def _normalize_ie_cache_basename(name: str) -> str:
    return IE_COPY_SUFFIX_RE.sub("", os.path.basename(name).lower())


def _parse_index_dat_records(index_path: str) -> Iterator[Tuple[str, List[str]]]:
    try:
        data = _read_file(index_path)
    except OSError:
        return
    if not data.startswith(b"Client UrlCache"):
        return

    for match in re.finditer(rb"(?:URL |LEAK)", data):
        offset = match.start()
        if offset + 8 > len(data):
            continue
        block_count = struct.unpack_from("<I", data, offset + 4)[0]
        if block_count <= 0 or block_count > 4096:
            continue
        record_size = min(block_count * 128, len(data) - offset)
        record = data[offset : offset + record_size]
        urls = _extract_fantage_urls(record)
        if not urls:
            continue
        strings = _extract_ascii_strings(record)
        local_names = [
            value
            for value in strings
            if _could_be_ie_local_name(value) and not value.lower().startswith(("http://", "https://"))
        ]
        for url in urls:
            yield url, local_names


def _extract_ascii_strings(blob: bytes, minimum: int = 3) -> List[str]:
    strings = []
    for match in re.finditer(rb"[\x20-\x7e]{%d,}" % minimum, blob):
        value = match.group(0).decode("latin-1", "ignore").strip()
        if value:
            strings.append(value)
    return strings


def _could_be_ie_local_name(value: str) -> bool:
    normalized = value.replace("\\", "/").strip()
    basename = os.path.basename(normalized)
    if not basename or basename.lower() in {"url", "http", "https"}:
        return False
    _, extension = os.path.splitext(_normalize_ie_cache_basename(basename))
    if extension in USEFUL_URL_EXTENSIONS:
        return True
    if "/" in normalized and len(basename) >= 3:
        return True
    return False


def _resolve_ie_local_candidates(
    index_path: str,
    source_root: str,
    url: str,
    local_names: Sequence[str],
    file_index: Dict[str, List[str]],
) -> List[str]:
    candidates = []
    index_dir = os.path.dirname(index_path)
    for local_name in local_names:
        normalized = local_name.replace("\\", os.sep).replace("/", os.sep)
        for base_dir in (index_dir, source_root):
            path = os.path.abspath(os.path.join(base_dir, normalized))
            if os.path.isfile(path):
                candidates.append(path)
        basename = _normalize_ie_cache_basename(local_name)
        candidates.extend(file_index.get(basename, []))

    url_basename = os.path.basename(urlsplit(url).path)
    if url_basename:
        candidates.extend(file_index.get(_normalize_ie_cache_basename(url_basename), []))

    seen = set()
    resolved = []
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(candidate))
        if key in seen:
            continue
        seen.add(key)
        resolved.append(candidate)
    return resolved


def _decode_chromium_disk_cache_entries(source_root: str) -> Iterator[DecodedEntry]:
    for cache_dir in _iter_chromium_cache_dirs(source_root):
        yield from _parse_chromium_cache_dir(cache_dir)


def _iter_chromium_cache_dirs(source_root: str) -> Iterator[str]:
    seen = set()
    if os.path.isfile(os.path.join(source_root, "index")):
        seen.add(os.path.normcase(os.path.abspath(source_root)))
        yield source_root
    for root, dirs, files in os.walk(source_root):
        if "index" in files and any(name.startswith("data_") for name in files):
            key = os.path.normcase(os.path.abspath(root))
            if key in seen:
                continue
            seen.add(key)
            yield root
            dirs[:] = []


def _parse_chromium_cache_dir(cache_dir: str) -> Iterator[DecodedEntry]:
    block_path = os.path.join(cache_dir, "data_1")
    if not os.path.isfile(block_path):
        return

    try:
        data = _read_file(block_path)
    except OSError:
        return
    if len(data) < 8192 + 256:
        return
    if data[:4] != b"\xc3\xca\x04\xc1":
        return

    block_size = struct.unpack_from("<I", data, 12)[0]
    if block_size != 256:
        return

    for offset in range(8192, len(data) - 256 + 1, 256):
        entry_block = data[offset : offset + 256]
        entry = _parse_chromium_entry(cache_dir, entry_block)
        if entry:
            yield entry


def _parse_chromium_entry(cache_dir: str, entry_block: bytes) -> Optional[DecodedEntry]:
    state = struct.unpack_from("<I", entry_block, 20)[0]
    if state not in {0, 1, 2}:
        return None

    key_len = struct.unpack_from("<I", entry_block, 32)[0]
    long_key_addr = struct.unpack_from("<I", entry_block, 36)[0]
    if key_len <= 0 or key_len > 8192:
        return None

    if long_key_addr:
        key_bytes = _read_chromium_cache_addr(cache_dir, long_key_addr, key_len)
    else:
        if key_len > 160:
            return None
        key_bytes = entry_block[96 : 96 + key_len]

    if not key_bytes:
        return None
    url = key_bytes.split(b"\x00", 1)[0].decode("utf-8", "ignore")
    if "fantage.com" not in url.lower():
        return None

    data_sizes = struct.unpack_from("<IIII", entry_block, 40)
    data_addrs = struct.unpack_from("<IIII", entry_block, 56)
    payload = b""
    source_path = cache_dir
    for stream_index in (1, 0, 2, 3):
        size = data_sizes[stream_index]
        addr = data_addrs[stream_index]
        if not size or not addr:
            continue
        stream = _read_chromium_cache_addr(cache_dir, addr, size)
        if not stream:
            continue
        if stream_index == 0 and _looks_like_chromium_headers(stream):
            continue
        payload = stream
        source_path = _chromium_source_path_for_addr(cache_dir, addr) or cache_dir
        break

    if not payload:
        return None
    return DecodedEntry(source_path, url, payload=payload)


def _looks_like_chromium_headers(payload: bytes) -> bool:
    lower = payload[:512].lower()
    return b"http/" in lower or b"content-type:" in lower or b"vary:" in lower


def _read_chromium_cache_addr(cache_dir: str, addr: int, size: int) -> bytes:
    parsed = _parse_chromium_cache_addr(addr)
    if not parsed:
        return b""

    kind = parsed[0]
    if kind == "external":
        file_number = parsed[1]
        path = os.path.join(cache_dir, f"f_{file_number:06x}")
        try:
            with open(path, "rb") as handle:
                return handle.read(size)
        except OSError:
            return b""

    _, file_number, offset, available = parsed
    path = os.path.join(cache_dir, f"data_{file_number}")
    try:
        with open(path, "rb") as handle:
            handle.seek(offset)
            return handle.read(min(size, available))
    except OSError:
        return b""


def _chromium_source_path_for_addr(cache_dir: str, addr: int) -> Optional[str]:
    parsed = _parse_chromium_cache_addr(addr)
    if not parsed:
        return None
    if parsed[0] == "external":
        return os.path.join(cache_dir, f"f_{parsed[1]:06x}")
    return os.path.join(cache_dir, f"data_{parsed[1]}")


def _parse_chromium_cache_addr(addr: int) -> Optional[Tuple]:
    if not addr or not (addr & 0x80000000):
        return None

    file_type = (addr >> 28) & 0x7
    if file_type == 0:
        return ("external", addr & 0x0FFFFFFF)

    if file_type not in {2, 3, 4}:
        return None

    block_size_by_type = {2: 256, 3: 1024, 4: 4096}
    block_size = block_size_by_type[file_type]
    file_number = (addr >> 16) & 0xFF
    block_number = addr & 0xFFFF
    contiguous_blocks = ((addr >> 24) & 0x3) + 1
    offset = 8192 + (block_number * block_size)
    available = contiguous_blocks * block_size
    return ("block", file_number, offset, available)


def _iter_wininet_entries() -> Iterator[DecodedEntry]:
    try:
        wininet = ctypes.WinDLL("wininet", use_last_error=True)
    except Exception:
        return

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]

    class INTERNET_CACHE_ENTRY_INFO(ctypes.Structure):
        _fields_ = [
            ("dwStructSize", ctypes.c_ulong),
            ("lpszSourceUrlName", ctypes.c_wchar_p),
            ("lpszLocalFileName", ctypes.c_wchar_p),
            ("CacheEntryType", ctypes.c_ulong),
            ("dwUseCount", ctypes.c_ulong),
            ("dwHitRate", ctypes.c_ulong),
            ("dwSizeLow", ctypes.c_ulong),
            ("dwSizeHigh", ctypes.c_ulong),
            ("LastModifiedTime", FILETIME),
            ("ExpireTime", FILETIME),
            ("LastAccessTime", FILETIME),
            ("LastSyncTime", FILETIME),
            ("lpHeaderInfo", ctypes.c_wchar_p),
            ("dwHeaderInfoSize", ctypes.c_ulong),
            ("lpszFileExtension", ctypes.c_wchar_p),
            ("dwReserved", ctypes.c_ulong),
        ]

    FindFirst = wininet.FindFirstUrlCacheEntryW
    FindFirst.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    FindFirst.restype = ctypes.c_void_p
    FindNext = wininet.FindNextUrlCacheEntryW
    FindNext.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    FindNext.restype = ctypes.c_bool
    FindClose = wininet.FindCloseUrlCache
    FindClose.argtypes = [ctypes.c_void_p]
    FindClose.restype = ctypes.c_bool

    size = ctypes.c_ulong(0)
    handle = FindFirst(None, None, ctypes.byref(size))
    if handle:
        FindClose(handle)
        return
    if ctypes.get_last_error() != 122 or size.value <= 0:
        return

    buffer = ctypes.create_string_buffer(size.value)
    handle = FindFirst(None, buffer, ctypes.byref(size))
    if not handle:
        return

    try:
        while True:
            info = ctypes.cast(buffer, ctypes.POINTER(INTERNET_CACHE_ENTRY_INFO)).contents
            url = info.lpszSourceUrlName or ""
            local_file = info.lpszLocalFileName or ""
            extension = info.lpszFileExtension or ""
            if "fantage.com" in url.lower() and local_file and os.path.isfile(local_file):
                yield DecodedEntry(local_file, url, file_extension=_normalize_extension(extension))

            size = ctypes.c_ulong(0)
            ok = FindNext(handle, None, ctypes.byref(size))
            if ok:
                continue
            error = ctypes.get_last_error()
            if error == 259:
                break
            if error != 122 or size.value <= 0:
                break
            buffer = ctypes.create_string_buffer(size.value)
            if not FindNext(handle, buffer, ctypes.byref(size)):
                if ctypes.get_last_error() == 259:
                    break
                break
    finally:
        FindClose(handle)


def _normalize_extension(extension: str) -> str:
    if not extension:
        return ""
    extension = extension.strip().lower()
    if not extension.startswith("."):
        extension = f".{extension}"
    if extension in USEFUL_URL_EXTENSIONS:
        return extension
    return ""
