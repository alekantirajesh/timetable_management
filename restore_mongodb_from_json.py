"""
MongoDB Data Restore Script
Imports JSON files back into MongoDB collections
"""
import sys
import os
import json
from datetime import datetime

# Ensure backend package root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import connect_mongodb, disconnect_mongodb, insert_many, clear_collection, insert_one
from config import COLLECTIONS, MONGODB_DB_NAME


def restore_from_directory(directory, clear_first=True):
    """
    Restore MongoDB collections from JSON files in directory
    
    Args:
        directory: Directory containing JSON files
        clear_first: Clear collections before inserting (default: True)
    """
    print(f"[RESTORE] Starting data restore from: {directory}")
    
    if not os.path.isdir(directory):
        print(f"[RESTORE] ERROR: Directory not found: {directory}")
        return False
    
    if not connect_mongodb():
        print("[RESTORE] ERROR: Could not connect to MongoDB")
        return False
    
    try:
        # Get all JSON files (excluding summary)
        json_files = [f for f in os.listdir(directory) 
                     if f.endswith('.json') and not f.startswith('_')]
        
        if not json_files:
            print(f"[RESTORE] ERROR: No JSON files found in {directory}")
            return False
        
        print(f"[RESTORE] Found {len(json_files)} collection files")
        print(f"[RESTORE] Database: {MONGODB_DB_NAME}")
        print("-" * 60)
        
        restore_summary = {
            'timestamp': datetime.now().isoformat(),
            'database': MONGODB_DB_NAME,
            'collections': {}
        }
        
        # Restore each collection
        for json_file in json_files:
            collection_name = json_file.replace('.json', '')
            json_path = os.path.join(directory, json_file)
            
            try:
                print(f"[RESTORE] Importing {collection_name}...", end=" ")
                
                # Load JSON file
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Ensure data is a list
                if not isinstance(data, list):
                    data = [data] if isinstance(data, dict) else []
                
                # Clear collection if requested
                if clear_first and data:
                    clear_collection(collection_name)
                
                # Insert documents
                if data:
                    insert_many(collection_name, data)
                    restore_summary['collections'][collection_name] = {
                        'status': 'success',
                        'count': len(data)
                    }
                    print(f"✓ {len(data)} documents")
                else:
                    restore_summary['collections'][collection_name] = {
                        'status': 'empty',
                        'count': 0
                    }
                    print(f"✓ Empty")
                
            except json.JSONDecodeError:
                print(f"✗ Invalid JSON")
                restore_summary['collections'][collection_name] = {
                    'status': 'error',
                    'error': 'Invalid JSON format'
                }
            except Exception as e:
                print(f"✗ ERROR: {str(e)}")
                restore_summary['collections'][collection_name] = {
                    'status': 'error',
                    'error': str(e)
                }
        
        print("-" * 60)
        print(f"[RESTORE] ✓ Restore completed!")
        
        return True
        
    finally:
        disconnect_mongodb()


def restore_single_collection(json_file, collection_name, clear_first=True):
    """
    Restore a single collection from JSON file
    
    Args:
        json_file: Path to JSON file
        collection_name: Target MongoDB collection name
        clear_first: Clear collection before inserting (default: True)
    """
    print(f"[RESTORE] Importing {json_file} to {collection_name}")
    
    if not os.path.exists(json_file):
        print(f"[RESTORE] ERROR: File not found: {json_file}")
        return False
    
    if not connect_mongodb():
        print("[RESTORE] ERROR: Could not connect to MongoDB")
        return False
    
    try:
        # Load JSON file
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Ensure data is a list
        if not isinstance(data, list):
            data = [data] if isinstance(data, dict) else []
        
        # Clear collection if requested
        if clear_first and data:
            clear_collection(collection_name)
        
        # Insert documents
        if data:
            insert_many(collection_name, data)
            print(f"[RESTORE] ✓ Restored {len(data)} documents to {collection_name}")
        else:
            print(f"[RESTORE] ⚠ No documents to restore")
        
        return True
        
    except json.JSONDecodeError:
        print(f"[RESTORE] ERROR: Invalid JSON in {json_file}")
        return False
    except Exception as e:
        print(f"[RESTORE] ERROR: {str(e)}")
        return False
    
    finally:
        disconnect_mongodb()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Restore MongoDB collections from JSON files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Restore all collections from directory
  python restore_mongodb_from_json.py --directory data/migrations/20260304_120000

  # Restore single collection
  python restore_mongodb_from_json.py --file data/migrations/timetables.json --collection timetables

  # Restore without clearing existing data
  python restore_mongodb_from_json.py --directory data/migrations/20260304_120000 --keep
        """
    )
    
    parser.add_argument('--directory', '-d', type=str, help='Directory with JSON files to restore')
    parser.add_argument('--file', '-f', type=str, help='Single JSON file to restore')
    parser.add_argument('--collection', '-c', type=str, help='Collection name (required with --file)')
    parser.add_argument('--keep', action='store_true', help='Keep existing data (do not clear collections)')
    
    args = parser.parse_args()
    
    if args.file and args.collection:
        # Restore single file
        success = restore_single_collection(args.file, args.collection, clear_first=not args.keep)
    elif args.directory:
        # Restore from directory
        success = restore_from_directory(args.directory, clear_first=not args.keep)
    else:
        parser.print_help()
        sys.exit(1)
    
    sys.exit(0 if success else 1)
