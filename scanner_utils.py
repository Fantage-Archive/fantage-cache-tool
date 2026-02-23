
import os

def is_related(filepath, keyword="fantage"):
    """
    Determines if a file is related based on the keyword.
    
    Args:
        filepath (str): Full path to the file.
        keyword (str): The keyword to search for.
    
    Returns:
        bool: True if related, False otherwise.
    """
    try:
        filename = os.path.basename(filepath)
        return keyword.lower() in filename.lower()
    except Exception:
        return False
