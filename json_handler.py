import json
import os

def load(path):
    """
    Load JSON data from a file.

    Args:
        path: Relative path to the JSON file.

    Returns:
        Parsed JSON data.
    """
    absolute_path = os.path.join(os.path.dirname(__file__), '..', path)
    with open(absolute_path) as f:
        return json.load(f)
    
def save(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)