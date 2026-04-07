import os
import re
import shutil
import platform
import subprocess
import uuid
import zipfile
import threading
try:
    from scanner_utils import is_related
except ImportError:
    from src.scanner_utils import is_related

class FantageExtractor:
    def __init__(self, output_dir, update_callback, search_path=None, keyword="fantage", username=""):
        self.output_dir = output_dir
        self.update_callback = update_callback
        self.search_path = search_path
        self.keyword = keyword
        self.username = username
        self.stop_event = threading.Event()
        self.files_found = 0

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
                os.path.join(local_appdata, 'Microsoft', 'Edge', 'User Data'),
                os.path.join(local_appdata, 'BraveSoftware', 'Brave-Browser', 'User Data'),
                os.path.join(local_appdata, 'Vivaldi', 'User Data'),
                os.path.join(local_appdata, 'Yandex', 'YandexBrowser', 'User Data'),
                os.path.join(local_appdata, 'Chromium', 'User Data'),
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

            # Also specifically target PepperFlash SharedObjects in Default profile
            for browser_path in chromium_browsers:
                if os.path.exists(browser_path):
                    add(browser_path)
                    pepper_path = os.path.join(browser_path, 'Default', 'Pepper Data',
                                               'Shockwave Flash', 'WritableRoot', '#SharedObjects')
                    add(pepper_path)

            # ============================================================
            # 3. Firefox family Browsers
            # ============================================================
            add(os.path.join(local_appdata, 'Mozilla', 'Firefox', 'Profiles'))
            add(os.path.join(roaming_appdata, 'Mozilla', 'Firefox', 'Profiles'))
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
                'Chromium',
                'Vivaldi',
                os.path.join('BraveSoftware', 'Brave-Browser'),
                'Microsoft Edge',
                os.path.join('Yandex', 'YandexBrowser'),
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

        elif system == "Linux":
            cache_home = os.environ.get('XDG_CACHE_HOME', os.path.join(user_home, '.cache'))
            config_home = os.environ.get('XDG_CONFIG_HOME', os.path.join(user_home, '.config'))
            
            # Flash
            add(os.path.join(user_home, '.macromedia', 'Flash_Player', '#SharedObjects'))
            add(os.path.join(user_home, '.macromedia', 'Flash_Player'))
            add(os.path.join(user_home, '.adobe', 'Flash_Player'))

            # PepperFlash across Chromium browsers
            for browser_dir in [
                'google-chrome',
                'chromium',
                'vivaldi',
                os.path.join('BraveSoftware', 'Brave-Browser'),
                'microsoft-edge',
                'yandex-browser',
                'opera',
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
            add(os.path.join(config_home, 'vivaldi'))
            add(os.path.join(config_home, 'opera'))
            add(os.path.join(config_home, 'brave'))
            add(os.path.join(user_home, '.config', 'waterfox'))
            add(os.path.join(user_home, '.moonchild productions', 'pale moon'))
            
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
            extract_base = os.path.join(self.output_dir, folder_name)
            if os.path.exists(extract_base):
                shutil.rmtree(extract_base, onerror=self._rm_readonly)
            os.makedirs(extract_base)
            
            processed_paths = set() # Track copied potential folders to avoid duplicates
            
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
                    
                    # 1. Check Directory Name
                    # If directory name matches, copy the WHOLE directory and skip walking into it
                    dir_name = os.path.basename(root)
                    if self.keyword.lower() in dir_name.lower():
                        # We found a folder!
                        self._copy_directory(root, extract_base, root_path)
                        # We don't need to traverse subdirs of this folder since we copied it all
                        dirs[:] = [] 
                        continue

                    # 2. Check Files
                    for file in files:
                        if is_related(file, self.keyword):
                            full_path = os.path.join(root, file)
                            self._copy_file(full_path, extract_base, root_path)
                
                if stopped:
                    break

            # Zip whatever was found (even if stopped early)
            if self.files_found > 0:
                self.update_callback("Zipping files...", 90)
                zip_name = f"Fantage_Cache_{safe_name}.zip" if self.username and safe_name else "Fantage_Cache_Extracted.zip"
                zip_path = os.path.join(self.output_dir, zip_name)
                # Remove existing zip to avoid appending/corruption
                if os.path.exists(zip_path):
                    try:
                        os.remove(zip_path)
                    except OSError:
                        pass
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
        """Copies an entire directory structure, preserving the original path hierarchy."""
        try:
            # Preserve original folder structure relative to the scan root
            rel_path = os.path.relpath(source_dir, scan_root)
            dest_path = os.path.join(dest_root, rel_path)
            
            if os.path.exists(dest_path): return # Already copied
            
            shutil.copytree(source_dir, dest_path, dirs_exist_ok=True)
            # Count files inside
            for _, _, files in os.walk(dest_path):
                self.files_found += len(files)
            
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