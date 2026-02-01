
import os

def is_fantage_related(filepath, is_cache_dir=False):
    """
    Determines if a file is related to Fantage.
    
    Args:
        filepath (str): Full path to the file.
        is_cache_dir (bool): If True, implies we are in a known browser cache directory,
                             so we should be more aggressive (check content).
    
    Returns:
        bool: True if related, False otherwise.
    """
    try:
        filename = os.path.basename(filepath)
        
        # 1. Check Filename
        if "fantage" in filename.lower():
            return True
            
        # 2. Check Content (only if in cache dir or suspicious)
        if is_cache_dir:
            try:
                # Read first 10MB to be safe, usually cache files are small
                with open(filepath, 'rb') as f:
                    content = f.read(10 * 1024 * 1024) 
                    if b"fantage" in content.lower():
                        return True
            except (PermissionError, OSError):
                pass
                
        return False
        
    except Exception as e:
        # Fail safe to avoid crashing the scan
        return False
