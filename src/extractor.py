import os
import re
import shutil
import platform
import subprocess
import uuid
import zipfile
import threading
try:
    from scanner_utils import classify_directory, is_contextual_candidate, is_opaque_cache_file, is_related
except ImportError:
    from src.scanner_utils import classify_directory, is_contextual_candidate, is_opaque_cache_file, is_related

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

ALLOWED_OUTPUT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".sol", ".swf", ".xml"}

class FantageExtractor:
    def __init__(self, output_dir, update_callback, search_path=None, keyword="fantage", username=""):
        self.output_dir = output_dir
        self.update_callback = update_callback
        self.search_path = search_path
        self.keyword = keyword
        self.username = username
        self.stop_event = threading.Event()
        self.files_found = 0

    @staticmethod
    def _discover_browser_roots(*base_dirs):
        found = []
        seen = set()

        def remember(path):
            if os.path.isdir(path) and path not in seen:
                seen.add(path)
                found.append(path)

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
    def _add_chromium_root(add, browser_root):
        if not os.path.exists(browser_root):
            return

        add(browser_root)
        try:
            entries = list(os.scandir(browser_root))
        except OSError:
            return

        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue

            name = entry.name.lower()
            if name == "default" or name.startswith("profile ") or name in {"guest profile", "system profile"}:
                add(os.path.join(entry.path, "Cache"))
                add(os.path.join(entry.path, "Code Cache"))
                add(os.path.join(entry.path, "GPUCache"))
                add(os.path.join(entry.path, "IndexedDB"))
                add(os.path.join(entry.path, "Local Storage"))
                add(os.path.join(entry.path, "Service Worker"))
                add(os.path.join(entry.path, "Session Storage"))
                add(os.path.join(entry.path, "Pepper Data", "Shockwave Flash", "WritableRoot"))
                add(os.path.join(entry.path, "Pepper Data", "Shockwave Flash", "WritableRoot", "#SharedObjects"))

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
    def _should_copy_file(path):
        _, ext = os.path.splitext(path)
        return ext.lower() in ALLOWED_OUTPUT_EXTENSIONS

    def get_all_cache_paths(self):
        """
        Returns a list of all potential cache directories including Browsers and Flash.
        """
        paths = []
        system = platform.system()
        user_home = os.path.expanduser("~")

        # Helper to safely add paths
        def add(p):
            if os.path.exists(p):
                paths.append(p)

        if system == "Windows":
            local_appdata = os.environ.get('LOCALAPPDATA', os.path.join(user_home, 'AppData', 'Local'))
            local_low = os.path.join(user_home, 'AppData', 'LocalLow')
            roaming_appdata = os.environ.get('APPDATA', os.path.join(user_home, 'AppData', 'Roaming'))
            temp_dir = os.environ.get('TEMP', os.path.join(user_home, 'AppData', 'Local', 'Temp'))
            windows_dir = os.environ.get('WINDIR', 'C:\\Windows')
            
            # ============================================================
            # 1. Flash / Shockwave
            # ============================================================
            
            # Standard Macromedia Flash Player shared objects
            add(os.path.join(roaming_appdata, 'Macromedia', 'Flash Player', '#SharedObjects'))
            add(os.path.join(roaming_appdata, 'Macromedia', 'Flash Player', 'macromedia.com', 'support', 'flashplayer', 'sys'))
            # Adobe Flash Player standalone / projector cache
            add(os.path.join(roaming_appdata, 'Adobe', 'Flash Player'))
            add(os.path.join(local_appdata, 'Adobe', 'Flash Player'))
            # Shockwave Player
            add(os.path.join(roaming_appdata, 'Macromedia', 'Shockwave Player'))
            add(os.path.join(local_appdata, 'Macromedia', 'Shockwave Player'))
            
            # ============================================================
            # 2. Chromium-based Browsers (scan full User Data for all profiles)
            # ============================================================
            chromium_browsers = [
                os.path.join(local_appdata, 'Google', 'Chrome', 'User Data'),
                os.path.join(local_appdata, 'Google', 'Chrome Beta', 'User Data'),
                os.path.join(local_appdata, 'Google', 'Chrome SxS', 'User Data'),
                os.path.join(local_appdata, 'Microsoft', 'Edge', 'User Data'),
                os.path.join(local_appdata, 'Microsoft', 'Edge Beta', 'User Data'),
                os.path.join(local_appdata, 'Microsoft', 'Edge Dev', 'User Data'),
                os.path.join(local_appdata, 'Microsoft', 'Edge SxS', 'User Data'),
                os.path.join(local_appdata, 'BraveSoftware', 'Brave-Browser', 'User Data'),
                os.path.join(local_appdata, 'Vivaldi', 'User Data'),
                os.path.join(local_appdata, 'Yandex', 'YandexBrowser', 'User Data'),
                os.path.join(local_appdata, 'Chromium', 'User Data'),
                os.path.join(local_appdata, 'Thorium', 'User Data'),
                os.path.join(local_appdata, 'The Browser Company', 'Arc', 'User Data'),
                os.path.join(local_appdata, 'Sidekick', 'User Data'),
                os.path.join(local_appdata, 'Naver', 'Naver Whale', 'User Data'),
                os.path.join(local_appdata, 'Avast Software', 'Browser', 'User Data'),
                os.path.join(local_appdata, 'CCleaner Browser', 'User Data'),
                os.path.join(local_appdata, 'CentBrowser', 'User Data'),
                os.path.join(local_appdata, 'Comodo', 'Dragon', 'User Data'),
                os.path.join(local_appdata, 'Torch', 'User Data'),
                os.path.join(local_appdata, 'SRWare Iron', 'User Data'),
                os.path.join(local_appdata, 'Slimjet', 'User Data'),
                os.path.join(local_appdata, '360Browser', 'Browser', 'User Data'),
                os.path.join(local_appdata, '360Chrome', 'Chrome', 'User Data'),
                os.path.join(local_appdata, 'UCBrowser', 'User Data'),
                os.path.join(local_appdata, 'CoolNovo', 'User Data'),
                os.path.join(local_appdata, 'Citrio', 'User Data'),
                os.path.join(local_appdata, 'Epic Privacy Browser', 'User Data'),
                os.path.join(local_appdata, 'CocCoc', 'Browser', 'User Data'),
                os.path.join(local_appdata, 'Iridium', 'User Data'),
            ]

            for browser_path in chromium_browsers:
                self._add_chromium_root(add, browser_path)

            # ============================================================
            # 3. Firefox family Browsers
            # ============================================================
            add(os.path.join(local_appdata, 'Mozilla', 'Firefox', 'Profiles'))
            add(os.path.join(roaming_appdata, 'Mozilla', 'Firefox', 'Profiles'))
            add(os.path.join(local_appdata, 'LibreWolf', 'Profiles'))
            add(os.path.join(roaming_appdata, 'LibreWolf', 'Profiles'))
            add(os.path.join(local_appdata, 'Floorp', 'Profiles'))
            add(os.path.join(roaming_appdata, 'Floorp', 'Profiles'))
            add(os.path.join(local_appdata, 'Zen', 'Profiles'))
            add(os.path.join(roaming_appdata, 'Zen', 'Profiles'))
            add(os.path.join(local_appdata, 'Waterfox', 'Profiles'))
            add(os.path.join(roaming_appdata, 'Waterfox', 'Profiles'))
            add(os.path.join(local_appdata, 'Moonchild Productions', 'Pale Moon', 'Profiles'))
            add(os.path.join(roaming_appdata, 'Moonchild Productions', 'Pale Moon', 'Profiles'))
            add(os.path.join(local_appdata, 'Moonchild Productions', 'Basilisk', 'Profiles'))
            add(os.path.join(roaming_appdata, 'Moonchild Productions', 'Basilisk', 'Profiles'))
            add(os.path.join(local_appdata, 'Mozilla', 'SeaMonkey', 'Profiles'))
            add(os.path.join(roaming_appdata, 'Mozilla', 'SeaMonkey', 'Profiles'))
            add(os.path.join(local_appdata, 'K-Meleon'))
            add(os.path.join(local_appdata, 'Comodo', 'IceDragon', 'Profiles'))
            add(os.path.join(roaming_appdata, 'Comodo', 'IceDragon', 'Profiles'))
            add(os.path.join(roaming_appdata, 'Netscape', 'Navigator', 'Profiles'))

            # ============================================================
            # 4. Opera
            # ============================================================
            add(os.path.join(local_appdata, 'Opera Software'))
            add(os.path.join(roaming_appdata, 'Opera Software'))
            add(os.path.join(roaming_appdata, 'Opera', 'Opera'))  # Legacy Opera Presto

            # ============================================================
            # 5. Maxthon
            # ============================================================
            add(os.path.join(local_appdata, 'Maxthon'))
            add(os.path.join(local_appdata, 'Maxthon3'))
            add(os.path.join(local_appdata, 'Maxthon5', 'User Data'))
            add(os.path.join(roaming_appdata, 'Maxthon3'))
            add(os.path.join(roaming_appdata, 'Maxthon5'))

            # ============================================================
            # 6. Internet Explorer / Legacy Edge / ActiveX
            # ============================================================
            add(os.path.join(local_appdata, 'Microsoft', 'Windows', 'INetCache'))
            add(os.path.join(local_appdata, 'Microsoft', 'Windows', 'Temporary Internet Files'))
            
            # Older IE cache path
            ie_content = os.path.join(local_appdata, 'Microsoft', 'Windows', 'INetCache', 'IE')
            add(ie_content)
            # Safari on Windows
            add(os.path.join(local_appdata, 'Apple Computer', 'Safari'))
            add(os.path.join(roaming_appdata, 'Apple Computer', 'Safari'))
            # Downloaded Program Files (ActiveX / Flash controls)
            add(os.path.join(windows_dir, 'Downloaded Program Files'))

            # ============================================================
            # 7. Generic catch-alls
            # ============================================================
            add(temp_dir)
            add(local_low)  # Unity Web Player and others
            for browser_root in self._discover_browser_roots(local_appdata, roaming_appdata, local_low):
                add(browser_root)
            
        elif system == "Darwin": # Mac
            library = os.path.join(user_home, 'Library')
            preferences = os.path.join(library, 'Preferences')
            caches = os.path.join(library, 'Caches')
            app_support = os.path.join(library, 'Application Support')
            
            # Flash
            add(os.path.join(preferences, 'Macromedia', 'Flash Player', '#SharedObjects'))
            add(os.path.join(preferences, 'Macromedia', 'Flash Player'))
            add(os.path.join(app_support, 'Macromedia'))
            add(os.path.join(app_support, 'Adobe', 'Flash Player'))
            # PepperFlash across Chromium browsers
            for browser_dir in [
                os.path.join('Google', 'Chrome'),
                os.path.join('Google', 'Chrome Beta'),
                os.path.join('Google', 'Chrome Canary'),
                os.path.join('Google', 'Chrome Dev'),
                'Chromium',
                'Vivaldi',
                os.path.join('BraveSoftware', 'Brave-Browser'),
                os.path.join('The Browser Company', 'Arc'),
                'Microsoft Edge',
                os.path.join('Yandex', 'YandexBrowser'),
                'LibreWolf',
                'Floorp',
                'Zen',
                'Opera Software',
            ]:
                pepper = os.path.join(app_support, browser_dir, 'Default', 'Pepper Data',
                                      'Shockwave Flash', 'WritableRoot', '#SharedObjects')
                add(pepper)

            # Browsers (broad scan of caches and app support)
            add(caches)
            add(app_support)
            add(os.path.join(library, 'Safari'))
            add(os.path.join(caches, 'Firefox', 'Profiles'))
            add(os.path.join(app_support, 'Firefox', 'Profiles'))
            add(os.path.join(caches, 'LibreWolf'))
            add(os.path.join(app_support, 'LibreWolf'))
            add(os.path.join(caches, 'Floorp'))
            add(os.path.join(app_support, 'Floorp'))
            add(os.path.join(caches, 'Zen'))
            add(os.path.join(app_support, 'Zen'))
            for browser_root in self._discover_browser_roots(app_support, caches):
                add(browser_root)

        elif system == "Linux":
            cache_home = os.environ.get('XDG_CACHE_HOME', os.path.join(user_home, '.cache'))
            config_home = os.environ.get('XDG_CONFIG_HOME', os.path.join(user_home, '.config'))
            flatpak_config = os.path.join(user_home, '.var', 'app')
            
            # Flash
            add(os.path.join(user_home, '.macromedia', 'Flash_Player', '#SharedObjects'))
            add(os.path.join(user_home, '.macromedia', 'Flash_Player'))
            add(os.path.join(user_home, '.adobe', 'Flash_Player'))

            # PepperFlash across Chromium browsers
            for browser_dir in [
                'google-chrome',
                'google-chrome-beta',
                'google-chrome-unstable',
                'chromium',
                'vivaldi',
                os.path.join('BraveSoftware', 'Brave-Browser'),
                'microsoft-edge',
                'microsoft-edge-beta',
                'microsoft-edge-dev',
                'yandex-browser',
                'opera',
                'librewolf',
                'floorp',
                'zen',
                'thorium',
            ]:
                pepper = os.path.join(config_home, browser_dir, 'Default', 'Pepper Data',
                                      'Shockwave Flash', 'WritableRoot', '#SharedObjects')
                add(pepper)
            
            # Browsers
            add(cache_home)
            add(config_home)
            add(os.path.join(user_home, '.mozilla'))
            add(os.path.join(config_home, 'chromium'))
            add(os.path.join(config_home, 'google-chrome'))
            add(os.path.join(config_home, 'google-chrome-beta'))
            add(os.path.join(config_home, 'google-chrome-unstable'))
            add(os.path.join(config_home, 'vivaldi'))
            add(os.path.join(config_home, 'opera'))
            add(os.path.join(config_home, 'BraveSoftware', 'Brave-Browser'))
            add(os.path.join(config_home, 'brave'))
            add(os.path.join(config_home, 'librewolf'))
            add(os.path.join(config_home, 'floorp'))
            add(os.path.join(config_home, 'zen'))
            add(os.path.join(config_home, 'thorium'))
            add(os.path.join(user_home, '.config', 'waterfox'))
            add(os.path.join(user_home, '.moonchild productions', 'pale moon'))
            add(os.path.join(cache_home, 'mozilla'))
            add(os.path.join(cache_home, 'google-chrome'))
            add(os.path.join(cache_home, 'chromium'))
            add(os.path.join(cache_home, 'BraveSoftware', 'Brave-Browser'))
            add(os.path.join(cache_home, 'librewolf'))
            add(os.path.join(cache_home, 'floorp'))
            add(os.path.join(cache_home, 'zen'))
            if os.path.exists(flatpak_config):
                add(flatpak_config)
                for browser_root in self._discover_browser_roots(flatpak_config):
                    add(browser_root)
            for browser_root in self._discover_browser_roots(config_home, cache_home):
                add(browser_root)
            
        return list(set(paths))

    def run(self):
        try:
            self.files_found = 0
            
            # Determines roots to scan
            scan_roots = []
            if self.search_path:
                self.update_callback(f"Scanning Target: {self.search_path}", 0)
                scan_roots = [self.search_path]
            else:
                self.update_callback("Locating Browser & Flash Caches...", 0)
                scan_roots = self.get_all_cache_paths()

            # Setup extraction folder... append username if provided
            safe_name = ""
            if self.username:
                safe_name = re.sub(r'[^\w\-. ]', '', self.username).strip()
            folder_name = f"Fantage_Extraction_{safe_name}" if safe_name else "Fantage_Extraction"
            zip_name = f"Fantage_Cache_{safe_name}" if self.username and safe_name else "Fantage_Cache_Extracted"
            extract_base, zip_path = self._next_output_targets(self.output_dir, folder_name, zip_name)
            os.makedirs(extract_base)
            
            total_roots = len(scan_roots)
            if total_roots == 0:
                self.update_callback("No cache directories found on this system.", 100)
                return

            stopped = False
            for i, root_path in enumerate(scan_roots):
                if self.stop_event.is_set():
                    stopped = True
                    break
                
                self.update_callback(f"Scanning: {root_path}", int((i / total_roots) * 80))
                
                for root, dirs, files in os.walk(root_path, onerror=self._walk_error):
                    if self.stop_event.is_set():
                        stopped = True
                        break

                    copy_mode = classify_directory(root, dirs, files, self.keyword)
                    if copy_mode == "all":
                        self._copy_directory(root, extract_base, root_path)
                        dirs[:] = []
                        continue

                    for file in files:
                        full_path = os.path.join(root, file)
                        if not self._should_copy_file(full_path):
                            continue
                        if is_related(full_path, self.keyword):
                            self._copy_file(full_path, extract_base, root_path)
                        elif copy_mode == "files" and (is_contextual_candidate(full_path) or is_opaque_cache_file(full_path)):
                            self._copy_file(full_path, extract_base, root_path)
                
                if stopped:
                    break

            # Zip whatever was found (even if stopped early)
            if self.files_found > 0:
                self.update_callback("Zipping files...", 90)
                self._make_zip(extract_base, zip_path)
                status = "Stopped early — partial results zipped." if stopped else "Done!"
                self.update_callback(status, 100)
                self._open_folder(self.output_dir)
            else:
                self.update_callback("Done. No files found.", 100)
            
        except Exception as e:
            self.update_callback(f"Error: {e}", 0)
            print(f"Error details: {e}")

    def _copy_directory(self, source_dir, dest_root, scan_root):
        """Copies allowed files from a related directory, preserving the original path hierarchy."""
        try:
            copied_any = False
            for root, _, files in os.walk(source_dir):
                for file in files:
                    source_path = os.path.join(root, file)
                    if not self._should_copy_file(source_path):
                        continue
                    self._copy_file(source_path, dest_root, scan_root)
                    copied_any = True

            if not copied_any:
                return

            folder_name = os.path.basename(source_dir)
            self.update_callback(f"Found Folder: {folder_name}", 0)
            
        except Exception as e:
             print(f"Failed to copy dir {source_dir}: {e}")

    def _copy_file(self, source, dest_root, scan_root):
        try:
            # Preserve original path structure relative to the scan root
            rel_path = os.path.relpath(source, scan_root)
            dest_path = os.path.join(dest_root, rel_path)
            
            # Handle duplicates
            if os.path.exists(dest_path):
                base, ext = os.path.splitext(dest_path)
                dest_path = f"{base}_{uuid.uuid4().hex[:4]}{ext}"

            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy2(source, dest_path)
            self.files_found += 1
            if self.files_found % 5 == 0:
                self.update_callback(f"Found {self.files_found} files...", 0)
                
        except Exception as e:
            print(f"Failed to copy {source}: {e}")

    def _make_zip(self, source_dir, zip_path):
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(source_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, source_dir)
                    zipf.write(file_path, arcname)

    @staticmethod
    def _rm_readonly(func, path, _excinfo):
        """Handle read-only files on Windows when removing directories."""
        import stat
        os.chmod(path, stat.S_IWRITE)
        func(path)

    @staticmethod
    def _walk_error(error):
        """Silently skip directories we can't access (permission denied, etc)."""
        pass

    def _open_folder(self, path):
        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])
        except Exception as e:
            print(f"Could not open folder: {e}")
