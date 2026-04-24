import os
from datetime import datetime

def get_current_datetime():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def list_directory(path: str):
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