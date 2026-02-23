
import os
import shutil
import platform
import zipfile
import threading
from scanner_utils import is_related

class FantageExtractor:
    def __init__(self, output_dir, update_callback, search_path=None, keyword="fantage"):
        self.output_dir = output_dir
        self.update_callback = update_callback
        self.search_path = search_path
        self.keyword = keyword
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
            
            # 1. Flash Shared Objects (The Holy Grail for Fantage)
            # Standard Macromedia paths
            add(os.path.join(roaming_appdata, 'Macromedia', 'Flash Player', '#SharedObjects'))
            add(os.path.join(roaming_appdata, 'Macromedia', 'Flash Player', 'macromedia.com', 'support', 'flashplayer', 'sys'))
            
            # Chrome/PepperFlash specific paths (Very important for later years of Fantage)
            # Check Default and Profile 1-10
            chrome_user_data = os.path.join(local_appdata, 'Google', 'Chrome', 'User Data')
            if os.path.exists(chrome_user_data):
                add(chrome_user_data) # Scan root to cover all profiles
                # Specifically target Pepper Data just in case
                add(os.path.join(chrome_user_data, 'Default', 'Pepper Data', 'Shockwave Flash', 'WritableRoot', '#SharedObjects'))
            
            # other chromium based browsers often use similar structures
            edge_user_data = os.path.join(local_appdata, 'Microsoft', 'Edge', 'User Data')
            if os.path.exists(edge_user_data): add(edge_user_data)
            
            brave_user_data = os.path.join(local_appdata, 'BraveSoftware', 'Brave-Browser', 'User Data')
            if os.path.exists(brave_user_data): add(brave_user_data)

            # 2. Browser Caches
            add(os.path.join(local_appdata, 'Mozilla', 'Firefox', 'Profiles'))
            add(os.path.join(local_appdata, 'Waterfox', 'Profiles'))
            add(os.path.join(local_appdata, 'Moonchild Productions', 'Pale Moon', 'Profiles'))
            add(os.path.join(local_appdata, 'Microsoft', 'Windows', 'INetCache')) # IE / Legacy Edge
            add(os.path.join(local_appdata, 'Opera Software')) # Opera / GX
            add(os.path.join(local_appdata, 'Vivaldi'))
            add(os.path.join(local_appdata, 'Yandex', 'YandexBrowser', 'User Data'))
            
            # Safari on Windows (Rare but possible)
            add(os.path.join(local_appdata, 'Apple Computer', 'Safari')) 

            # 3. Generic Temporary Files (Installers or loose cache)
            add(temp_dir)
            
            # 4. LocalLow (Unity Web Player and others often live here)
            add(local_low)
            
        elif system == "Darwin": # Mac
            library = os.path.join(user_home, 'Library')
            preferences = os.path.join(library, 'Preferences')
            caches = os.path.join(library, 'Caches')
            app_support = os.path.join(library, 'Application Support')
            
            # Flash
            add(os.path.join(preferences, 'Macromedia', 'Flash Player', '#SharedObjects'))
            add(os.path.join(app_support, 'Google', 'Chrome', 'Default', 'Pepper Data', 'Shockwave Flash', 'WritableRoot', '#SharedObjects'))

            # Browsers (Broad scan of Caches and App Support)
            add(caches) 
            add(app_support) # Chrome/Firefox profiles often live here

        elif system == "Linux":
            cache_home = os.environ.get('XDG_CACHE_HOME', os.path.join(user_home, '.cache'))
            config_home = os.environ.get('XDG_CONFIG_HOME', os.path.join(user_home, '.config'))
            
            # Flash
            add(os.path.join(user_home, '.macromedia', 'Flash_Player', '#SharedObjects'))
            add(os.path.join(config_home, 'google-chrome', 'Default', 'Pepper Data', 'Shockwave Flash', 'WritableRoot', '#SharedObjects'))
            
            # Browsers
            add(cache_home) 
            add(config_home) # Sometimes profiles are here
            add(os.path.join(user_home, '.mozilla'))
            add(os.path.join(user_home, '.config', 'chromium'))
            
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

            # Setup extraction folder
            extract_base = os.path.join(self.output_dir, "Fantage_Extraction")
            if os.path.exists(extract_base):
                shutil.rmtree(extract_base)
            os.makedirs(extract_base)
            
            processed_paths = set() # Track copied potential folders to avoid duplicates
            
            total_roots = len(scan_roots)
            for i, root_path in enumerate(scan_roots):
                if self.stop_event.is_set(): return
                
                self.update_callback(f"Scanning: {root_path}", int((i / total_roots) * 80))
                
                for root, dirs, files in os.walk(root_path):
                    if self.stop_event.is_set(): return
                    
                    # 1. Check Directory Name
                    # If directory name matches, copy the WHOLE directory and skip walking into it
                    dir_name = os.path.basename(root)
                    if self.keyword.lower() in dir_name.lower():
                        # We found a folder!
                        self._copy_directory(root, extract_base)
                        # We don't need to traverse subdirs of this folder since we copied it all
                        dirs[:] = [] 
                        continue

                    # 2. Check Files
                    for file in files:
                        if is_related(file, self.keyword):
                            full_path = os.path.join(root, file)
                            self._copy_file(full_path, extract_base)

            # Zip it
            if self.files_found > 0:
                self.update_callback("Zipping files...", 90)
                zip_path = os.path.join(self.output_dir, "Fantage_Cache_Extracted.zip")
                self._make_zip(extract_base, zip_path)
                self.update_callback("Done!", 100)
                self._open_folder(self.output_dir)
            else:
                self.update_callback("Done. No files found.", 100)
            
        except Exception as e:
            self.update_callback(f"Error: {e}", 0)
            print(f"Error details: {e}")

    def _copy_directory(self, source_dir, dest_root):
        """Copies an entire directory structure."""
        try:
            # Create a unique name for the folder in destination to avoid collisions
            # e.g. /path/to/my_fantage_folder -> dest_root/my_fantage_folder_hash
            folder_name = os.path.basename(source_dir)
            
            # Simple way to make unique path roughly
            import hashlib
            h = hashlib.md5(source_dir.encode()).hexdigest()[:6]
            dest_dir_name = f"{folder_name}_{h}"
            dest_path = os.path.join(dest_root, dest_dir_name)
            
            if os.path.exists(dest_path): return # Already copied
            
            shutil.copytree(source_dir, dest_path, dirs_exist_ok=True)
            self.files_found += 1 # Count folder as one "find" or maybe count files inside?
            # Let's count files inside for better feeling
            for _, _, files in os.walk(dest_path):
                self.files_found += len(files)
            
            self.update_callback(f"Found Folder: {folder_name}", 0)
            
        except Exception as e:
             print(f"Failed to copy dir {source_dir}: {e}")

    def _copy_file(self, source, dest_root):
        try:
            filename = os.path.basename(source)
            # Just dump files in a 'Files' folder if they were found individually
            dest_path = os.path.join(dest_root, "Individual_Files", filename)
            
            # Handle duplicates
            if os.path.exists(dest_path):
                base, ext = os.path.splitext(filename)
                import uuid
                dest_path = os.path.join(dest_root, "Individual_Files", f"{base}_{uuid.uuid4().hex[:4]}{ext}")

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

    def _open_folder(self, path):
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            os.system(f"open '{path}'")
        else:
            os.system(f"xdg-open '{path}'")
