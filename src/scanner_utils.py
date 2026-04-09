import os
import re
import zlib

WINDOWS_CACHE_SUFFIX_RE = re.compile(r'~\d+(?=\.[^.]+$)')
BRACKET_COPY_SUFFIX_RE = re.compile(r'\[\d+\](?=\.[^.]+$|$)')

USEFUL_EXTENSIONS = {
    ".bmp",
    ".css",
    ".db",
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
    ".ldb",
    ".localstorage",
    ".log",
    ".manifest",
    ".m4a",
    ".m4v",
    ".mp3",
    ".mp4",
    ".ogg",
    ".php",
    ".png",
    ".sqlite",
    ".sqlite3",
    ".sol",
    ".swf",
    ".txt",
    ".wav",
    ".webm",
    ".webp",
    ".xml",
}

KNOWN_DIRECTORY_COMPONENTS = {
    "fantage.com",
    "loginserverselect.swf",
    "ratingwidget.swf",
    "play.fantage.com",
    "secure.fantage.com",
    "secm.fantage.com",
    "static.fantage.com",
    "upload.fantage.com",
    "www.fantage.com",
}

KNOWN_DOMAIN_COMPONENTS = {
    "fantage.com",
    "play.fantage.com",
    "secure.fantage.com",
    "secm.fantage.com",
    "static.fantage.com",
    "upload.fantage.com",
    "www.fantage.com",
}

SPECIAL_FILENAME_SUFFIXES = (
    ".db-journal",
    ".localstorage-journal",
    ".sqlite-journal",
    ".sqlite-shm",
    ".sqlite-wal",
)

FANTAGE_ASSET_DIR_COMPONENTS = {
    "accb",
    "acch",
    "air2",
    "air4",
    "airb",
    "body",
    "brow",
    "cfg",
    "cmod",
    "cost",
    "earr",
    "emot",
    "eyes",
    "facd",
    "face",
    "fbct",
    "female",
    "full",
    "fun",
    "futb",
    "hair",
    "har2",
    "idbg",
    "images",
    "img",
    "lips",
    "lipd",
    "male",
    "mobile",
    "onep",
    "panels",
    "pant",
    "playpages",
    "r1",
    "rasterpet",
    "resource",
    "shoe",
    "shrt",
    "sound",
    "themes",
    "tutorial",
    "uni",
}

DIRECT_MATCH_STEMS = {
    "cachedassets",
    "cmod_configuration",
    "dynamicmodule_config",
    "first_login",
    "global_config",
    "gsb_module_config",
    "homepage_config",
    "idfone_level",
    "last_server_key",
    "last_user",
    "login_page_standalone",
    "loginserverselect",
    "microloaderparam_enlarge",
    "microloaderparam_enlarge11",
    "module_object_coordinates",
    "petanimation",
    "petwalkinganimation",
    "questlist_config",
    "rasteravatarconfig",
    "rasteravatareffect",
    "rasterpetrect",
    "saved_avatar_list_name",
    "server_selection_page",
    "sounddata",
    "stampbook_asset",
    "stampbook_event",
    "stampbook_tooltip",
    "useravatarbitmap",
    "userinfo",
    "userlogincookieproxy",
    "username",
    "world_loader",
    "world_map_list",
}

CONTEXTUAL_MATCH_STEMS = DIRECT_MATCH_STEMS | {
    "admodule",
    "appversion",
    "backgroundsoundmodule",
    "beach",
    "blogclientmodule",
    "boardshop",
    "bubble2",
    "candycane",
    "catalog_button",
    "castleroom",
    "classpreloader",
    "clubmanager",
    "comet",
    "cmodcontroller",
    "config",
    "configcachemodule",
    "crossdomain",
    "default-world-room-list",
    "downtown",
    "dressingpanelmanager",
    "emoticon_icon",
    "eventmovieplayer_christmas2012",
    "fantagedoggy",
    "fashionshowpetcontroller",
    "filmstrip",
    "fishfishmobile2011",
    "flyingcarmodule",
    "furnitureset1a",
    "furnitureset1c",
    "furnitureset1d",
    "friendshipbracelet",
    "game2012xmas",
    "gamecard_2012",
    "genericsignbuttons",
    "gsb_module",
    "helpandnpcguide",
    "holidaybash2012controller",
    "holidayecoingift",
    "homepage_register",
    "homepage_register_rd",
    "homepagefooter",
    "homepageloader",
    "homepageloader2",
    "ice2012limited",
    "icerink2012controller",
    "idfonebackground",
    "imchat",
    "inventory_new",
    "invitationreward",
    "jumbotron_tradensell",
    "lang",
    "leshop",
    "mainscreen",
    "maintenancemodule",
    "medalset1",
    "missionmodule",
    "mobilefantage",
    "monthlypmgift",
    "mountaincave",
    "newbannerstellar",
    "newidfone",
    "newuserguide",
    "newworld",
    "oasis",
    "northpole",
    "npcguide",
    "outtercontroller",
    "petcontroller",
    "petshop",
    "petvillage",
    "photoalbummodule",
    "polarexpress",
    "portalinside",
    "rasteravatarconfig",
    "rasteravatareffect",
    "rasterpetrect",
    "register_loader",
    "reportermodule",
    "resellingshop",
    "schoolroommanager",
    "secretadvgates",
    "selling_panel_btn_module",
    "shop",
    "skicontainer",
    "server_icons",
    "slideshow_mainscreen",
    "sounddata",
    "spaeffect",
    "stampbookmodule",
    "star_double_machine_button",
    "stampbook_asset",
    "stampbook_event",
    "stampbook_tooltip",
    "tradingpanelmanager",
    "timemodule",
    "top",
    "topbar",
    "userfarm",
    "userhomepartymodule",
    "usernavigation",
    "userquestmodule",
    "wizardshop",
    "world2012xmas",
    "world_loader",
    "worldmap",
}

KNOWN_FILE_NAMES = {
    "f2utg.sol",
    "https_secure.fantage.com_0.localstorage",
    "https_secure.fantage.com_0.localstorage-journal",
}

CONTENT_STRONG_MARKERS = (
    b"fantage",
    b"play.fantage.com",
    b"www.fantage.com",
    b"secure.fantage.com",
    b"static.fantage.com",
    b"upload.fantage.com",
    b"secm.fantage.com",
    b"mobilefantage",
)

BROWSER_CONTENT_STRONG_MARKERS = (
    b"fantage.com",
    b"play.fantage.com",
    b"www.fantage.com",
    b"secure.fantage.com",
    b"static.fantage.com",
    b"upload.fantage.com",
    b"secm.fantage.com",
)

CONTENT_MEDIUM_MARKERS = (
    b"/r1/",
    b"/uni/",
    b"cachedassets",
    b"cmod",
    b"global_config",
    b"gsb_module",
    b"idfone",
    b"loginserverselect",
    b"missionmodule",
    b"monthlypmgift",
    b"petanimation",
    b"rasteravatar",
    b"secretadvgates",
    b"userhomepartymodule",
    b"userlogincookieproxy",
    b"world_loader",
    b"worldmap",
)

OPAQUE_CACHE_FILE_RE = re.compile(
    r'^(cache(?:_data)?|data_\d+|entries|f_[0-9a-f]+|index(?:\.dat)?|the-real-index)$'
)

PET_ASSET_RE = re.compile(
    r'^[a-z0-9]+_(blink|cry|custom|eat|idle|jump|victory|walk)\.(gif|jpeg|jpg|png)$'
)
AVATAR_ASSET_RE = re.compile(
    r'^(boy|girl)-[a-z0-9_-]+\.(gif|jpeg|jpg|png)$'
)
BASE_ASSET_RE = re.compile(
    r'^(body|board|bracelet|brow|cachedassets|face|global_config|head|idfone_level|'
    r'logo_big_worldbelow|mainscreen|missionmodule|module_object_coordinates|new-eyes|'
    r'petanimation|questlist_config|rasteravatarconfig|server_icons|server_selection_page|'
    r'slideshow_mainscreen|sounddata|topbar|world_loader|worldmap)'
    r'([_-][a-z0-9-]+|\d+)?\.(gif|jpeg|jpg|mp3|png|swf|xml)$'
)

MAX_SNIFF_BYTES = 512 * 1024
MAX_SNIFF_FILE_SIZE = 24 * 1024 * 1024


def normalize_cache_name(name):
    normalized = name.lower().replace("\\", "/")
    normalized = WINDOWS_CACHE_SUFFIX_RE.sub("", normalized)
    normalized = BRACKET_COPY_SUFFIX_RE.sub("", normalized)
    return normalized


def _normalized_parts(path):
    return [part for part in normalize_cache_name(path).split("/") if part not in {"", ".", ".."}]


def _normalized_basename(path):
    parts = _normalized_parts(path)
    return parts[-1] if parts else ""


def _normalized_stem(path):
    basename = _normalized_basename(path)
    stem, _ = os.path.splitext(basename)
    return stem


def _extension(path):
    basename = _normalized_basename(path)
    _, ext = os.path.splitext(basename)
    return ext


def _is_useful_extension(path):
    basename = _normalized_basename(path)
    return basename.endswith(SPECIAL_FILENAME_SUFFIXES) or _extension(path) in USEFUL_EXTENSIONS


def is_opaque_cache_file(path):
    return bool(OPAQUE_CACHE_FILE_RE.match(_normalized_basename(path)))


def _path_reason(path, keyword="fantage"):
    keyword = keyword.lower().strip()
    normalized_path = normalize_cache_name(path)
    parts = _normalized_parts(path)
    cleaned_parts = [part.lstrip("#") for part in parts]
    basename = _normalized_basename(path)
    cleaned_basename = basename.lstrip("#")
    stem = _normalized_stem(path)

    if keyword and keyword in normalized_path:
        return "keyword in path"
    if any(part in KNOWN_DIRECTORY_COMPONENTS for part in cleaned_parts):
        return "known Fantage directory"
    if cleaned_basename in KNOWN_FILE_NAMES:
        return "known Fantage file"
    if stem in DIRECT_MATCH_STEMS:
        return "known Fantage asset name"
    return None


def _browser_cache_path_reason(path):
    normalized_path = normalize_cache_name(path)
    parts = _normalized_parts(path)
    cleaned_parts = [part.lstrip("#") for part in parts]
    basename = _normalized_basename(path).lstrip("#")

    if "fantage.com" in normalized_path:
        return "Fantage domain in path"
    if any(part in KNOWN_DOMAIN_COMPONENTS for part in cleaned_parts):
        return "known Fantage domain directory"
    if "fantage.com" in basename:
        return "Fantage domain in filename"
    return None


def has_path_marker(path, keyword="fantage"):
    return bool(_path_reason(path, keyword))


def has_browser_cache_marker(path):
    return bool(_browser_cache_path_reason(path))


def _should_sniff_contents(path):
    try:
        size = os.path.getsize(path)
    except OSError:
        return False

    if size <= 0 or size > MAX_SNIFF_FILE_SIZE:
        return False

    ext = _extension(path)
    return ext in USEFUL_EXTENSIONS or not ext


def _read_sniff_blob(path):
    try:
        with open(path, "rb") as handle:
            header = handle.read(8)
            handle.seek(0)
            if header.startswith(b"CWS"):
                data = handle.read()
                decompressed = data[:8] + zlib.decompress(data[8:])
                return decompressed[:MAX_SNIFF_BYTES]
            return handle.read(MAX_SNIFF_BYTES)
    except Exception:
        return b""


def _content_reason(path):
    if not _should_sniff_contents(path):
        return None

    blob = _read_sniff_blob(path)
    if not blob:
        return None

    haystack = blob.lower()
    if any(marker in haystack for marker in CONTENT_STRONG_MARKERS):
        return "Fantage marker in content"

    medium_hits = sum(1 for marker in CONTENT_MEDIUM_MARKERS if marker in haystack)
    if medium_hits >= 2:
        return "Fantage asset markers in content"

    return None


def _browser_cache_content_reason(path):
    if not _should_sniff_contents(path):
        return None

    blob = _read_sniff_blob(path)
    if not blob:
        return None

    haystack = blob.lower()
    if any(marker in haystack for marker in BROWSER_CONTENT_STRONG_MARKERS):
        return "Fantage domain in browser cache content"

    return None


def is_contextual_candidate(path):
    basename = _normalized_basename(path)
    stem = _normalized_stem(path)

    if not _is_useful_extension(path):
        return False
    if _path_reason(path):
        return True
    if stem in CONTEXTUAL_MATCH_STEMS:
        return True
    if PET_ASSET_RE.match(basename):
        return True
    if AVATAR_ASSET_RE.match(basename):
        return True
    if BASE_ASSET_RE.match(basename):
        return True
    return False


def classify_directory(path, dirs, files, keyword="fantage"):
    if _path_reason(path, keyword):
        return "all"

    asset_dir_count = sum(1 for name in dirs if _normalized_basename(name) in FANTAGE_ASSET_DIR_COMPONENTS)
    related_dir_count = sum(1 for name in dirs if _path_reason(name, keyword))
    related_file_count = sum(1 for name in files if _path_reason(name, keyword))
    contextual_file_count = sum(1 for name in files if is_contextual_candidate(name))
    opaque_cache_file_count = sum(1 for name in files if is_opaque_cache_file(name))
    total_dirs = max(1, len(dirs))
    total_files = max(1, len(files))
    asset_dir_ratio = asset_dir_count / total_dirs
    related_dir_ratio = related_dir_count / total_dirs
    contextual_ratio = contextual_file_count / total_files

    if asset_dir_count >= 4 and asset_dir_ratio >= 0.5:
        return "all"
    if asset_dir_count >= 2 and contextual_file_count >= 2:
        return "all"
    if related_dir_count >= 2 and related_dir_ratio >= 0.5:
        return "all"
    if related_dir_count >= 2 and contextual_file_count >= 4:
        return "all"
    if related_dir_count >= 1 and asset_dir_count >= 1 and (related_file_count >= 1 or contextual_file_count >= 2):
        return "all"
    if related_dir_count >= 1 and contextual_file_count >= 6:
        return "all"

    if related_dir_count >= 1 and (related_file_count >= 1 or contextual_file_count >= 2 or opaque_cache_file_count >= 1):
        return "files"
    if related_file_count >= 4:
        return "files"
    if contextual_file_count >= 6 and contextual_ratio >= 0.5:
        return "files"
    if contextual_file_count >= 4 and opaque_cache_file_count >= 1:
        return "files"
    return None


def is_related(filepath, keyword="fantage"):
    return bool(_path_reason(filepath, keyword) or _content_reason(filepath))


def is_browser_cache_related(filepath):
    return bool(_browser_cache_path_reason(filepath) or _browser_cache_content_reason(filepath))
