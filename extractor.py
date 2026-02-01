
import os
import shutil
import platform
import zipfile
import threading
from scanner_utils import is_fantage_related

class FantageExtractor:
    def __init__(self, output_dir, update_callback, search_path=None):
        self.output_dir = output_dir
        self.update_callback = update_callback  # Function to call with status updates (msg, progress_increment)
        self.search_path = search_path
        self.stop_event = threading.Event()
        self.files_found = 0

    def get_search_roots(self):
        if self.search_path:
            return [self.search_path]

        system = platform.system()
        roots = []
        
        if system == "Windows":
            # Detect available drives
            import string
            from ctypes import windll
            drives = []
            bitmask = windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & 1:
                    drives.append(f"{letter}:\\")
                bitmask >>= 1
            roots = drives
        else:
            # Linux / Mac
            # Scan home directory and root (but be careful with root)
            user_home = os.path.expanduser("~")
            roots.append(user_home)
            
            # Add root "/" but we will need to exclude /proc etc in the walk
            roots.append("/")
            
        return list(set(roots)) # unique

    def get_browser_cache_paths(self):
        """
        Returns a list of common browser cache directories for the platform.
        """
        paths = []
        system = platform.system()
        user_home = os.path.expanduser("~")

        if system == "Windows":
            # AppData locations
            local_appdata = os.environ.get('LOCALAPPDATA', os.path.join(user_home, 'AppData', 'Local'))
            roaming_appdata = os.environ.get('APPDATA', os.path.join(user_home, 'AppData', 'Roaming'))
            
            paths.extend([
                os.path.join(local_appdata, 'Google', 'Chrome', 'User Data', 'Default', 'Cache'),
                os.path.join(local_appdata, 'Google', 'Chrome', 'User Data', 'Default', 'Code Cache'),
                os.path.join(local_appdata, 'Mozilla', 'Firefox', 'Profiles'), # Search all profiles
                os.path.join(local_appdata, 'Microsoft', 'Edge', 'User Data', 'Default', 'Cache'),
                os.path.join(local_appdata, 'Microsoft', 'Windows', 'INetCache'), # IE/Edge Legacy
            ])
            
        elif system == "Darwin": # Mac
            library = os.path.join(user_home, 'Library')
            paths.extend([
                os.path.join(library, 'Caches', 'Google', 'Chrome'),
                os.path.join(library, 'Caches', 'Firefox', 'Profiles'),
                os.path.join(library, 'Caches', 'Safari'),
            ])
            
        elif system == "Linux":
            cache_home = os.environ.get('XDG_CACHE_HOME', os.path.join(user_home, '.cache'))
            paths.extend([
                os.path.join(cache_home, 'google-chrome'),
                os.path.join(cache_home, 'mozilla', 'firefox'),
                os.path.join(cache_home, 'chromium'),
                os.path.join(user_home, '.mozilla', 'firefox'), # sometimes here
            ])
            
        # Filter existing paths
        return [p for p in paths if os.path.exists(p)]

    def run(self):
        try:
            self.files_found = 0
            roots = self.get_search_roots()
            
            # Setup extraction folder
            extract_base = os.path.join(self.output_dir, "Fantage_Extraction")
            if os.path.exists(extract_base):
                shutil.rmtree(extract_base)
            os.makedirs(extract_base)
            
            processed_files = set()

            # Priority Scan: Browser Caches (Only if no specific path is set)
            if not self.search_path:
                browser_paths = self.get_browser_cache_paths()
                self.update_callback("Scanning Browser Caches...", 0)
                for cache_path in browser_paths:
                    if self.stop_event.is_set(): return
                    
                    self.update_callback(f"Checking cache: {cache_path}", 0)
                    for root, dirs, files in os.walk(cache_path):
                        for file in files:
                            if self.stop_event.is_set(): return
                            
                            full_path = os.path.join(root, file)
                            # Helper check with Content Check enabled
                            if is_fantage_related(full_path, is_cache_dir=True):
                                self._copy_file(full_path, extract_base)
                                processed_files.add(full_path)

            # Deep Scan: Entire System (or selected directory)
            if self.search_path:
                self.update_callback(f"Scanning Selected Directory: {self.search_path}", 20)
            else:
                self.update_callback("Starting Full System Scan...", 20)
            
            skip_dirs = {
                '/proc', '/sys', '/dev', '/run', '/tmp', '/var/run', '/var/lock',
                'C:\\Windows', 'C:\\Program Files', 'C:\\Program Files (x86)' # Optional: skip sys dirs to speed up?
                # User asked for "Every drive", so we shouldn't skip Program Files necessarily, 
                # but /proc etc are effectively infinite loops or virtual files on Linux.
            }
            
            for drive_root in roots:
                self.update_callback(f"Scanning Drive: {drive_root}", 0)
                for root, dirs, files in os.walk(drive_root, topdown=True):
                    if self.stop_event.is_set(): return
                    
                    # Modifying dirs in-place to prune search
                    dirs[:] = [d for d in dirs if os.path.join(root, d) not in skip_dirs]
                    
                    # Optimization: If folder name has "fantage", take everything inside?
                    # Plan says: search for any file or directory containing "fantage"
                    
                    is_fantage_folder = "fantage" in os.path.basename(root).lower()
                    
                    for file in files:
                        full_path = os.path.join(root, file)
                        if full_path in processed_files: 
                            continue
                            
                        # If folder is fantage, verify user wants ALL content? "compiles every trace" -> Yes.
                        # If not, check file individually.
                        # For general files, we do NOT deep read content to safe time, unless filename matches.
                        
                        should_copy = False
                        if is_fantage_folder:
                             should_copy = True
                        elif is_fantage_related(full_path, is_cache_dir=False):
                             should_copy = True

                        if should_copy:
                             self._copy_file(full_path, extract_base)

            # Zip Phase
            self.update_callback("Zipping files...", 90)
            zip_path = os.path.join(self.output_dir, "Fantage_Cache_Extracted.zip")
            self._make_zip(extract_base, zip_path)
            
            self.update_callback("Done!", 100)
            self._open_folder(self.output_dir)
            
        except Exception as e:
            self.update_callback(f"Error: {e}", 0)
            print(f"Error details: {e}")

    def _copy_file(self, source, dest_root):
        try:
            # Recreate folder structure
            # e.g. source: /home/user/cache/foo
            # dest: dest_root/home/user/cache/foo
            
            # Remove drive colon for Windows paths to make them valid folder names
            clean_source = os.path.normpath(source)
            if platform.system() == "Windows":
                 drive, tail = os.path.splitdrive(clean_source)
                 clean_source = os.path.join(drive.replace(':', '_Drive'), tail.lstrip(os.sep))
            else:
                 clean_source = clean_source.lstrip(os.sep)

            dest_path = os.path.join(dest_root, clean_source)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy2(source, dest_path)
            self.files_found += 1
            if self.files_found % 10 == 0:
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
