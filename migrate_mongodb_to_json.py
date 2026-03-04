"""
MongoDB Data Migration Script
Exports all MongoDB collections to JSON files for backup or data transfer
"""
import sys
import os
from datetime import datetime
import json

# Ensure backend package root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import connect_mongodb, disconnect_mongodb, find_many
from config import COLLECTIONS, MONGODB_DB_NAME
from bson import ObjectId


class ObjectIdEncoder(json.JSONEncoder):
    """JSON encoder for MongoDB ObjectId"""
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)


def migrate_all_collections():
    """
    Export all MongoDB collections to JSON files
    Creates timestamped directory in data/migrations/
    """
    print("[MIGRATION] Starting MongoDB data export...")
    
    if not connect_mongodb():
        print("[MIGRATION] ERROR: Could not connect to MongoDB")
        return False
    
    try:
        # Create timestamped migration directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        migration_dir = os.path.join('data', 'migrations', timestamp)
        os.makedirs(migration_dir, exist_ok=True)
        
        print(f"[MIGRATION] Export directory: {migration_dir}")
        print(f"[MIGRATION] Database: {MONGODB_DB_NAME}")
        print("-" * 60)
        
        migration_summary = {
            'timestamp': datetime.now().isoformat(),
            'database': MONGODB_DB_NAME,
            'collections': {}
        }
        
        # Export each collection
        for collection_key, collection_name in COLLECTIONS.items():
            try:
                print(f"[MIGRATION] Exporting {collection_name}...", end=" ")
                
                # Fetch all documents
                documents = find_many(collection_name)
                documents = documents or []
                
                # Convert to JSON-serializable format
                serialized_docs = []
                for doc in documents:
                    # Convert ObjectId fields to strings
                    if isinstance(doc, dict):
                        serialized_doc = {}
                        for key, value in doc.items():
                            if isinstance(value, ObjectId):
                                serialized_doc[key] = str(value)
                            else:
                                serialized_doc[key] = value
                        serialized_docs.append(serialized_doc)
                    else:
                        serialized_docs.append(doc)
                
                # Save to JSON file
                json_file = os.path.join(migration_dir, f'{collection_name}.json')
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(serialized_docs, f, indent=2, cls=ObjectIdEncoder, ensure_ascii=False)
                
                migration_summary['collections'][collection_name] = {
                    'status': 'success',
                    'count': len(serialized_docs),
                    'file': json_file
                }
                
                print(f"✓ {len(serialized_docs)} documents")
                
            except Exception as e:
                print(f"✗ ERROR: {str(e)}")
                migration_summary['collections'][collection_name] = {
                    'status': 'error',
                    'error': str(e)
                }
        
        print("-" * 60)
        
        # Save migration summary
        summary_file = os.path.join(migration_dir, '_migration_summary.json')
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(migration_summary, f, indent=2, ensure_ascii=False)
        
        print(f"[MIGRATION] ✓ Export completed successfully!")
        print(f"[MIGRATION] Files saved to: {migration_dir}")
        print(f"[MIGRATION] Summary: {summary_file}")
        
        return True
        
    finally:
        disconnect_mongodb()


def migrate_single_collection(collection_name, output_path=None):
    """
    Export a single collection to JSON
    
    Args:
        collection_name: Name of collection to export
        output_path: Optional custom output file path
    """
    print(f"[MIGRATION] Exporting collection: {collection_name}")
    
    if not connect_mongodb():
        print("[MIGRATION] ERROR: Could not connect to MongoDB")
        return False
    
    try:
        # Fetch documents
        documents = find_many(collection_name)
        documents = documents or []
        
        # Determine output file
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join('data', 'migrations', f'{collection_name}_{timestamp}.json')
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Convert to JSON-serializable format
        serialized_docs = []
        for doc in documents:
            if isinstance(doc, dict):
                serialized_doc = {}
                for key, value in doc.items():
                    if isinstance(value, ObjectId):
                        serialized_doc[key] = str(value)
                    else:
                        serialized_doc[key] = value
                serialized_docs.append(serialized_doc)
            else:
                serialized_docs.append(doc)
        
        # Save to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(serialized_docs, f, indent=2, cls=ObjectIdEncoder, ensure_ascii=False)
        
        print(f"[MIGRATION] ✓ Exported {len(serialized_docs)} documents to {output_path}")
        
        return True
        
    except Exception as e:
        print(f"[MIGRATION] ✗ Error: {str(e)}")
        return False
    
    finally:
        disconnect_mongodb()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Migrate MongoDB collections to JSON files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export all collections
  python migrate_mongodb_to_json.py

  # Export specific collection
  python migrate_mongodb_to_json.py --collection timetables

  # Export to custom location
  python migrate_mongodb_to_json.py --collection faculty --output ./backups/faculty.json
        """
    )
    
    parser.add_argument('--collection', type=str, help='Specific collection to export (optional)')
    parser.add_argument('--output', type=str, help='Output file path (optional)')
    
    args = parser.parse_args()
    
    if args.collection:
        # Export single collection
        success = migrate_single_collection(args.collection, args.output)
    else:
        # Export all collections
        success = migrate_all_collections()
    
    sys.exit(0 if success else 1)
