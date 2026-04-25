import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def get_current_datetime():
    logging.debug("get_current_datetime called")
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def list_directory(path: str):
    logging.debug("list_directory called")
    
    if not os.path.exists(path):
        return f"Error: Path '{path}' does not exist."
    if not os.path.isdir(path):
        return f"Error: Path '{path}' is not a folder."
    
    try:
        items = os.listdir(path)
        if not items:
            return f"'{path}' is empty."
        
        result=[f"Folder '{path}' contains:"]
        for item in items:
            full_path=os.path.join(path,item)
            item_type="[DIR]" if os.path.isdir(full_path) else "[FILE]"
            result.append(f"- {item_type} {item}")

        return "\n".join(result)
    except Exception as e:
        return f"Error reading folder: {str(e)}"
    
def read_file(file_path: str):
    logging.debug("read_file called")
    if not os.path.exists(file_path):
        return f"Error: File '{file_path}' doesn't exist."
    if not os.path.isfile(file_path):
        return f"Error: Path '{file_path}' is not a file."
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content.strip():
                return f"File '{file_path}' is empty"
            return f"--- Beginning of file {file_path} ---\n{content}\n--- End of file ---"
    except UnicodeDecodeError:
        return f"Error: File '{file_path}' is probably a binary file, not text file."
    except Exception as e:
        return f"Error reading file: {str(e)}"