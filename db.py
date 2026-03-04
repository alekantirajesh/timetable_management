"""
MongoDB Data Access Layer
Replaces load_json() and save_json() functions
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError
from config import MONGODB_URI, MONGODB_DB_NAME, COLLECTIONS
import os

# Global MongoDB client and database
client = None
db = None


def connect_mongodb():
    """
    Connect to MongoDB
    """
    global client, db
    try:
        print(f"[MongoDB] Connecting to {MONGODB_URI}...")
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        
        # Verify connection
        client.admin.command('ping')
        db = client[MONGODB_DB_NAME]
        print(f"[MongoDB] [OK] Connected to database: {MONGODB_DB_NAME}")
        return True
    except Exception as e:
        print(f"[MongoDB] [ERROR] Connection failed: {str(e)}")
        print(f"[MongoDB] Make sure MongoDB server is running on localhost:27017")
        return False


def disconnect_mongodb():
    """Disconnect from MongoDB"""
    global client
    if client:
        client.close()
        print("[MongoDB] Disconnected")


def create_indexes():
    """
    Create indexes for efficient querying
    """
    try:
        if db is None:
            print("[Indexes] Database not connected")
            return
        
        print("[Indexes] Creating indexes...")
        
        # Timetable indexes - Most important for performance
        db[COLLECTIONS['timetables']].create_index([('faculty_id', ASCENDING)])
        db[COLLECTIONS['timetables']].create_index([('class', ASCENDING)])
        db[COLLECTIONS['timetables']].create_index([('date', ASCENDING)])
        db[COLLECTIONS['timetables']].create_index([('month', ASCENDING), ('year', ASCENDING)])
        db[COLLECTIONS['timetables']].create_index([('faculty_id', ASCENDING), ('date', ASCENDING)])
        db[COLLECTIONS['timetables']].create_index([('class', ASCENDING), ('date', ASCENDING)])
        
        # Users indexes
        db[COLLECTIONS['users']].create_index([('email', ASCENDING)], unique=True)
        db[COLLECTIONS['users']].create_index([('role', ASCENDING)])
        
        # Faculty indexes
        db[COLLECTIONS['faculty']].create_index([('id', ASCENDING)], unique=True)
        db[COLLECTIONS['faculty']].create_index([('subject', ASCENDING)])
        
        # Students indexes
        db[COLLECTIONS['students']].create_index([('id', ASCENDING)], unique=True)
        db[COLLECTIONS['students']].create_index([('class', ASCENDING)])
        
        # Leaves indexes
        db[COLLECTIONS['leaves']].create_index([('faculty_id', ASCENDING), ('status', ASCENDING)])
        db[COLLECTIONS['leaves']].create_index([('date', ASCENDING)])
        
        # Faculty holidays indexes
        db[COLLECTIONS['faculty_holidays']].create_index([('faculty_id', ASCENDING)])
        
        print("[Indexes] [OK] All indexes created successfully")
        
    except PyMongoError as e:
        print(f"[Indexes] ⚠️  Error creating indexes: {str(e)}")


# ============ BASIC CRUD OPERATIONS ============

def find_one(collection_name, query=None):
    """
    Find single document
    
    Args:
        collection_name: Name of collection
        query: MongoDB query dict (e.g., {'email': 'test@gmail.com'})
    
    Returns:
        Document dict or None
    """
    if db is None:
        print(f"[DB] Database not connected")
        return None
    
    try:
        query = query or {}
        result = db[collection_name].find_one(query)
        if result:
            # Remove MongoDB's internal _id if needed
            result.pop('_id', None)
        return result
    except PyMongoError as e:
        print(f"[DB] Error in find_one({collection_name}): {str(e)}")
        return None


def find_many(collection_name, query=None, limit=None, sort=None):
    """
    Find multiple documents
    
    Args:
        collection_name: Name of collection
        query: MongoDB query dict
        limit: Limit number of results
        sort: Sort specification (e.g., [('date', ASCENDING)])
    
    Returns:
        List of documents
    """
    if db is None:
        print(f"[DB] Database not connected")
        return []
    
    try:
        query = query or {}
        cursor = db[collection_name].find(query)
        
        if sort:
            cursor = cursor.sort(sort)
        
        if limit:
            cursor = cursor.limit(limit)
        
        results = []
        for doc in cursor:
            # Don't remove _id - it's needed for API formatting
            # The format functions will handle converting _id to id as needed
            results.append(doc)
        
        return results
    except PyMongoError as e:
        print(f"[DB] Error in find_many({collection_name}): {str(e)}")
        return []


def insert_one(collection_name, document):
    """
    Insert single document
    
    Args:
        collection_name: Name of collection
        document: Document dict
    
    Returns:
        Document ID or None
    """
    if db is None:
        print(f"[DB] Database not connected")
        return None
    
    try:
        result = db[collection_name].insert_one(document)
        return str(result.inserted_id)
    except DuplicateKeyError:
        print(f"[DB] Duplicate key in {collection_name}")
        return None
    except PyMongoError as e:
        print(f"[DB] Error in insert_one({collection_name}): {str(e)}")
        return None


def insert_many(collection_name, documents):
    """
    Insert multiple documents
    
    Args:
        collection_name: Name of collection
        documents: List of document dicts
    
    Returns:
        List of inserted IDs
    """
    if db is None:
        print(f"[DB] Database not connected")
        return []
    
    try:
        result = db[collection_name].insert_many(documents, ordered=False)
        return [str(id) for id in result.inserted_ids]
    except PyMongoError as e:
        print(f"[DB] Error in insert_many({collection_name}): {str(e)}")
        return []


def update_one(collection_name, query, update_data):
    """
    Update single document
    
    Args:
        collection_name: Name of collection
        query: Query to find document
        update_data: Data to update (e.g., {'$set': {'status': 'approved'}})
    
    Returns:
        Number of modified documents
    """
    if db is None:
        print(f"[DB] Database not connected")
        return 0
    
    try:
        result = db[collection_name].update_one(query, update_data)
        return result.modified_count
    except PyMongoError as e:
        print(f"[DB] Error in update_one({collection_name}): {str(e)}")
        return 0


def update_many(collection_name, query, update_data):
    """
    Update multiple documents
    
    Args:
        collection_name: Name of collection
        query: Query to find documents
        update_data: Data to update
    
    Returns:
        Number of modified documents
    """
    if db is None:
        print(f"[DB] Database not connected")
        return 0
    
    try:
        result = db[collection_name].update_many(query, update_data)
        return result.modified_count
    except PyMongoError as e:
        print(f"[DB] Error in update_many({collection_name}): {str(e)}")
        return 0


def delete_one(collection_name, query):
    """Delete single document"""
    if db is None:
        return 0
    
    try:
        result = db[collection_name].delete_one(query)
        return result.deleted_count
    except PyMongoError as e:
        print(f"[DB] Error in delete_one({collection_name}): {str(e)}")
        return 0


def delete_many(collection_name, query):
    """Delete multiple documents"""
    if db is None:
        return 0
    
    try:
        result = db[collection_name].delete_many(query)
        return result.deleted_count
    except PyMongoError as e:
        print(f"[DB] Error in delete_many({collection_name}): {str(e)}")
        return 0


def count_documents(collection_name, query=None):
    """Count documents matching query"""
    if db is None:
        return 0
    
    try:
        query = query or {}
        return db[collection_name].count_documents(query)
    except PyMongoError as e:
        print(f"[DB] Error in count_documents({collection_name}): {str(e)}")
        return 0


def clear_collection(collection_name):
    """Delete all documents in collection (for testing)"""
    if db is None:
        return 0
    
    try:
        result = db[collection_name].delete_many({})
        return result.deleted_count
    except PyMongoError as e:
        print(f"[DB] Error clearing collection {collection_name}: {str(e)}")
        return 0


# ============ TIMETABLE SPECIFIC OPERATIONS ============

def get_timetable(filters=None):
    """
    Get timetable entries with optional filters
    
    Args:
        filters: dict with keys like 'faculty_id', 'class', 'month', 'year', 'date'
    
    Returns:
        List of timetable entries
    """
    query = filters or {}
    return find_many(COLLECTIONS['timetables'], query)


def save_timetable(timetable_entries):
    """
    Save/replace all timetable entries
    
    Args:
        timetable_entries: List of timetable dicts
    """
    try:
        # Clear existing timetables
        db[COLLECTIONS['timetables']].delete_many({})
        
        # Insert new ones
        if timetable_entries:
            insert_many(COLLECTIONS['timetables'], timetable_entries)
            print(f"[DB] Saved {len(timetable_entries)} timetable entries")
        
        return True
    except PyMongoError as e:
        print(f"[DB] Error saving timetable: {str(e)}")
        return False


def save_timetable_entries(entries, month=None, year=None):
    """
    Save timetable entries to the MongoDB collection.
    If month/year provided, only deletes entries for that specific month before inserting.
    Otherwise, inserts entries without clearing old data.

    Args:
        entries: List of timetable entries to save.
        month: Optional month number (1-12) to identify which month's data to replace.
        year: Optional year to identify which month's data to replace.

    Returns:
        True if successful, False otherwise.
    """
    if db is None:
        print(f"[DB] Database not connected")
        return False

    try:
        # If month/year specified, only delete entries for that month
        if month and year:
            delete_query = {
                'date': {
                    '$regex': f'^{year:04d}-{month:02d}-'
                }
            }
            result = db[COLLECTIONS['timetables']].delete_many(delete_query)
            print(f"[DB] Deleted {result.deleted_count} old entries for {month}/{year}")
        
        # Insert new entries
        if entries:
            db[COLLECTIONS['timetables']].insert_many(entries)
            print(f"[DB] Timetable entries saved successfully ({len(entries)} entries)")
        
        return True
    except PyMongoError as e:
        print(f"[DB] Error saving timetable entries: {str(e)}")
        return False



# ============ DATABASE INFO ============

def get_database_info():
    """Get info about all collections"""
    if db is None:
        return {}
    
    info = {}
    for collection_name in db.list_collection_names():
        count = db[collection_name].count_documents({})
        indexes = len(db[collection_name].list_indexes()) if count > 0 else 0
        info[collection_name] = {
            'count': count,
            'indexes': indexes
        }
    
    return info


def load_collection_as_list(collection_name):
    """
    Load all documents from a MongoDB collection as a list.

    Args:
        collection_name: Name of the collection to load.

    Returns:
        List of documents from the collection.
    """
    if db is None:
        print(f"[DB] Database not connected")
        return []

    try:
        documents = list(db[collection_name].find())
        for doc in documents:
            doc.pop('_id', None)  # Remove MongoDB's internal _id field
        return documents
    except PyMongoError as e:
        print(f"[DB] Error loading collection {collection_name}: {str(e)}")
        return []
