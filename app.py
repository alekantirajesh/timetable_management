from flask import Flask, jsonify, request
from flask_cors import CORS
import json
import os
from datetime import datetime, timedelta
from scheduler.manager import TimetableManager
# Removed: from scheduler.csp_timetable import CSPTimetableGenerator, Faculty, Subject
import re
import traceback
from bson import ObjectId

# MongoDB imports
from db import connect_mongodb, disconnect_mongodb, find_many, find_one, insert_many, insert_one, update_one, update_many, delete_many, count_documents, clear_collection, create_indexes, load_collection_as_list, save_timetable_entries
from config import COLLECTIONS
from bson import ObjectId

app = Flask(__name__)
# Enhanced CORS configuration
CORS(app)
 
def remove_objectid_fields(obj):
    """Recursively remove MongoDB ObjectId fields and convert _id to id (string).
    Accepts dict or list and returns a cleaned copy.
    """
    if obj is None:
        return obj
    if isinstance(obj, list):
        return [remove_objectid_fields(item) for item in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == '_id':
                try:
                    out['id'] = str(v)
                except Exception:
                    out['id'] = v
            else:
                # convert ObjectId-like values to string
                if hasattr(v, '__class__') and v.__class__.__name__ == 'ObjectId':
                    out[k] = str(v)
                else:
                    out[k] = remove_objectid_fields(v) if isinstance(v, (dict, list)) else v
        return out
    return obj


def transform_timetable_entries(entries):
    """Normalize timetable DB documents to API format expected by frontend.
    - Ensures `faculty_id` and `faculty` keys exist
    - Normalizes `class` to "Class N" format where appropriate
    - Removes MongoDB _id fields
    """
    data = remove_objectid_fields(entries)
    if data is None:
        return data
    if isinstance(data, list):
        out = []
        for e in data:
            ee = dict(e)
            # unify faculty id
            if ee.get('faculty_id') is None and ee.get('teacher_id') is not None:
                ee['faculty_id'] = ee.get('teacher_id')
            # normalize faculty_id to int when possible for consistent comparisons
            fid = ee.get('faculty_id')
            try:
                if fid is not None and not isinstance(fid, int):
                    ee['faculty_id'] = int(fid)
            except Exception:
                # leave as-is if conversion fails
                pass
            # unify faculty name
            if ee.get('faculty') is None and ee.get('teacher_name') is not None:
                ee['faculty'] = ee.get('teacher_name')
            # normalize class display
            cls = ee.get('class')
            if cls is not None and not isinstance(cls, str):
                cls = str(cls)
            if isinstance(cls, str) and not cls.lower().startswith('class'):
                ee['class'] = cls
            out.append(ee)
        return out
    elif isinstance(data, dict):
        ee = dict(data)
        if ee.get('faculty_id') is None and ee.get('teacher_id') is not None:
            ee['faculty_id'] = ee.get('teacher_id')
        if ee.get('faculty') is None and ee.get('teacher_name') is not None:
            ee['faculty'] = ee.get('teacher_name')
        return ee
    return data


def format_leaves_for_response(leaves_list):
    """Format leave documents for API responses.
    - Converts _id to id
    - Adds faculty_name (looked up from faculty collection when possible)
    """
    leaves = remove_objectid_fields(leaves_list) or []
    out = []
    for l in leaves:
        item = dict(l)
        fac_id = item.get('faculty_id') or item.get('faculty') or item.get('teacher_id')
        faculty_name = None
        try:
            if fac_id is not None:
                fac = find_one(COLLECTIONS['faculty'], {'id': fac_id})
                if fac:
                    faculty_name = fac.get('name')
        except Exception:
            faculty_name = None
        item['faculty_name'] = faculty_name or item.get('faculty_name') or item.get('faculty')
        out.append(item)
    return out


def format_leave_for_response(leave_doc):
    """Compatibility wrapper for single leave document formatting."""
    if not leave_doc:
        return None
    formatted = format_leaves_for_response([leave_doc])
    return formatted[0] if formatted else None


def get_timetable_flat(filters=None):
    """Return flat list of timetable entries from DB respecting optional filters."""
    try:
        query = filters or {}
        docs = find_many(COLLECTIONS['timetables'], query)
        return docs or []
    except Exception as e:
        print(f"[GET_TIMETABLE_FLAT ERROR] {e}")
        return []


def timetable_exists_for_month(month, year):
    """Return True if any timetable entries exist for given month/year."""
    try:
        mm = int(month)
        yy = int(year)
        pattern = f'^{yy:04d}-{mm:02d}-'
        entries = find_many(COLLECTIONS['timetables'], {'date': {'$regex': pattern}})
        return bool(entries)
    except Exception as e:
        print(f"[TIMETABLE_EXISTS ERROR] {e}")
        return False

    

# Data files path - use absolute path based on app.py location (keep for backup)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
print(f"[INIT] DATA_DIR set to: {DATA_DIR}")
print(f"[INIT] DATA_DIR exists: {os.path.exists(DATA_DIR)}")

# Connect to MongoDB on startup — require MongoDB, do NOT fallback to JSON files
if not connect_mongodb():
    print("[FATAL] Failed to connect to MongoDB. Exiting — MongoDB is required.")
    raise SystemExit("[FATAL] MongoDB not available. Aborting.")
else:
    USING_JSON = False
    print("[SUCCESS] MongoDB connected and ready!")

# Users database - will be loaded from MongoDB (or username.json as fallback)
USERS_DB = {}

def load_json(filename):
    """Load data from JSON file (DEPRECATED - use MongoDB)"""
    filepath = os.path.join(DATA_DIR, filename)
    print(f"[DEBUG] Loading {filename} from: {filepath}")
    print(f"[DEBUG] File exists: {os.path.exists(filepath)}")
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                print(f"[DEBUG] Successfully loaded {filename}: {len(data) if isinstance(data, list) else len(data)} items")
                return data
        except Exception as e:
            print(f"[DEBUG] Error loading {filename}: {str(e)}")
            return [] if filename.endswith('_list.json') or filename in ['leaves.json', 'students.json'] else {}
    print(f"[DEBUG] File not found: {filepath}")
    return [] if filename.endswith('_list.json') or filename in ['leaves.json', 'students.json'] else {}


def load_users_db():
    """Load users from MongoDB and build USERS_DB dict"""
    global USERS_DB
    USERS_DB = {}
    try:
        users_list = find_many(COLLECTIONS['users'], {})
    except Exception:
        users_list = []

    # If MongoDB users collection is empty, do NOT fallback to local JSON files.
    if not users_list:
        print(f"[INIT] MongoDB users collection is empty; not falling back to username.json. USERS_DB will remain empty.")
        users_list = []

    for user in users_list:
        email = user.get('email')
        if email:
            USERS_DB[email] = {
                'password': user.get('password'),
                'role': user.get('role'),
                'name': user.get('name'),
                'id': user.get('id'),
                'status': user.get('status', 'active')
            }

    print(f"[INIT] Loaded {len(USERS_DB)} users from MongoDB/JSON")
    return USERS_DB


# Load users on startup
load_users_db()

# ===== TIMETABLE ADJUSTMENT HELPER FUNCTIONS (Using MongoDB) =====

def get_available_faculty_for_subject(subject, exclude_faculty_ids=None, date_str=None, check_workload=True):
    """
    Get list of available faculty who can teach a subject.
    Uses MongoDB to find faculty by subject.
    Excludes faculty who have leaves approved on the given date.
    Also validates workload constraints (daily 5-hr limit, no teaching at same time).
    Returns: [(faculty_id, faculty_name), ...] sorted by workload (ascending)
    """
    if exclude_faculty_ids is None:
        exclude_faculty_ids = []
    
    # ISSUE #3 FIX: Use exact subject matching instead of regex
    # If subject is None, return all faculty (used when substitutes may be any subject)
    if subject is None:
        faculty_data = find_many(COLLECTIONS['faculty'], {}) or []
    else:
        faculty_data = find_many(COLLECTIONS['faculty'], {'subject': subject}) or []
    available = []
    
    # If date is provided, get faculty with approved leaves on that date
    faculty_with_leave_on_date = set()
    if date_str:
        leaves_on_date = find_many(COLLECTIONS['leaves'], {'date': date_str, 'status': 'approved'})
        for leave in leaves_on_date:
            faculty_with_leave_on_date.add(leave.get('faculty_id'))
    
    for fac in faculty_data:
        fac_id = fac.get('id')
        # Exclude if in exclude list OR has approved leave on the date OR has personal holiday on the date
        if fac_id not in exclude_faculty_ids and fac_id not in faculty_with_leave_on_date:
            # Also check personal holidays
            fac_hol = find_one(COLLECTIONS['faculty_holidays'], {'faculty_id': fac_id})
            if date_str and fac_hol and date_str in fac_hol.get('dates', []):
                continue  # Skip if faculty has personal holiday on this date
            
            # ISSUE #1 FIX: Add workload constraint checking
            if check_workload and date_str:
                # Count existing timetable entries for this faculty on this date
                # Timetable documents historically used either 'faculty_id' or 'teacher_id'
                existing_entries = find_many(COLLECTIONS['timetables'], 
                    {'date': date_str, '$or': [{'faculty_id': fac_id}, {'teacher_id': fac_id}]})
                existing_count = len(existing_entries)
                
                # Skip if already at daily limit (5 hours = 5 periods)
                if existing_count >= 5:
                    print(f"[WORKLOAD CHECK] Skipping {fac.get('name')} - already at 5-hour daily limit")
                    continue
            
            available.append((fac_id, fac.get('name')))
    
    # Sort by workload (faculty with less classes come first - better distribution)
    if available and check_workload and date_str:
        availability_with_load = []
        for fac_id, fac_name in available:
            # consider both possible field names in stored timetable docs
            existing_entries = find_many(COLLECTIONS['timetables'], 
                {'date': date_str, '$or': [{'faculty_id': fac_id}, {'teacher_id': fac_id}]})
            workload = len(existing_entries)
            availability_with_load.append((fac_id, fac_name, workload))
        
        # Sort by workload ascending (prefer faculty with less work)
        availability_with_load.sort(key=lambda x: x[2])
        available = [(fac_id, fac_name) for fac_id, fac_name, _ in availability_with_load]
    
    return available

def get_faculty_unavailable_dates(faculty_id):
    """
    Get all dates when a faculty is unavailable (holidays + approved leaves).
    Uses MongoDB queries.
    Returns: set of date strings (YYYY-MM-DD format)
    """
    unavailable = set()
    
    # Add faculty holidays from faculty_holidays collection
    fac_hol = find_one(COLLECTIONS['faculty_holidays'], {'faculty_id': faculty_id})
    if fac_hol and fac_hol.get('dates'):
        unavailable.update(fac_hol['dates'])
    
    # Add approved leaves
    leaves_list = find_many(COLLECTIONS['leaves'], {'faculty_id': faculty_id, 'status': 'approved'})
    for leave in leaves_list:
        date = leave.get('date')
        if date:
            unavailable.add(date)
    
    return unavailable

def adjust_timetable_for_date_and_faculty(date_str, faculty_id):
    """
    Adjust timetable for a specific faculty on a specific date.
    Replaces the faculty with an available substitute for that day.
    Ensures substitute is not on leave or holiday themselves.
    Uses MongoDB for efficient querying and bulk update.
    """
    print(f"\n[ADJUST TIMETABLE] Starting adjustment for faculty_id={faculty_id}, date={date_str}")
    
    # Find all timetable entries for this faculty on this date using MongoDB
    entries = find_many(COLLECTIONS['timetables'], {'date': date_str, '$or': [{'faculty_id': faculty_id}, {'teacher_id': faculty_id}]})
    
    print(f"[ADJUST TIMETABLE] Found {len(entries)} entries for faculty_id={faculty_id} on date={date_str}")
    
    faculty_info = find_one(COLLECTIONS['faculty'], {'id': faculty_id})
    old_faculty_name = faculty_info.get('name', 'Unknown') if faculty_info else 'Unknown'
    
    adjustments_made = 0
    adjustment_log = []
    
    # Group entries by subject to get one substitute per subject
    subjects_seen = set()
    replacements = {}  # subject -> (new_faculty_id, new_faculty_name)
    
    for entry in entries:
        subject = entry.get('subject')
        class_name = entry.get('class')
        time_slot = entry.get('time')
        
        if subject not in subjects_seen:
            subjects_seen.add(subject)
            
            # Try to find same-subject substitutes first, then fall back to any available faculty
            available = get_available_faculty_for_subject(subject, [faculty_id], date_str, check_workload=True)
            if not available:
                # allow substitutes from any subject
                available = get_available_faculty_for_subject(None, [faculty_id], date_str, check_workload=True)

            if available:
                new_faculty_id, new_faculty_name = available[0]
                replacements[subject] = (new_faculty_id, new_faculty_name)
                print(f"[ADJUST TIMETABLE] Subject '{subject}' -> Substitute {new_faculty_name} (ID: {new_faculty_id})")
            else:
                print(f"[ADJUST TIMETABLE] ⚠️ No substitute available for {subject} on {date_str}")
        
        # Apply the replacement if one exists for this subject
        if subject in replacements:
            new_faculty_id, new_faculty_name = replacements[subject]
            
            adjustment_log.append({
                'date': date_str,
                'time': time_slot,
                'class': class_name,
                'subject': subject,
                'original_faculty_id': faculty_id,
                'original_faculty_name': old_faculty_name,
                'replacement_faculty_id': new_faculty_id,
                'replacement_faculty_name': new_faculty_name,
                'status': 'success'
            })
            adjustments_made += 1
        else:
            adjustment_log.append({
                'date': date_str,
                'time': time_slot,
                'class': class_name,
                'subject': subject,
                'original_faculty_id': faculty_id,
                'original_faculty_name': old_faculty_name,
                'replacement_faculty_id': None,
                'replacement_faculty_name': 'NO SUBSTITUTE AVAILABLE',
                'status': 'failed'
            })
    
    # Now perform bulk update for all entries with matching subjects
    if replacements:
        for subject, (new_faculty_id, new_faculty_name) in replacements.items():
            # Match either legacy `teacher_id` or newer `faculty_id` fields so we update all relevant docs
            query = {
                'date': date_str,
                'subject': subject,
                '$or': [
                    {'faculty_id': faculty_id},
                    {'teacher_id': faculty_id}
                ]
            }

            # Update both legacy and new fields to ensure UI and downstream code see the substitute
            update_fields = {
                'faculty_id': new_faculty_id,
                'teacher_id': new_faculty_id,
                'faculty': new_faculty_name,
                'teacher_name': new_faculty_name,
                'teacher': new_faculty_name
            }

            modified_count = update_many(COLLECTIONS['timetables'], query, {'$set': update_fields})
            print(f"[ADJUST TIMETABLE] Updated {modified_count} entries for subject '{subject}' with substitute ID {new_faculty_id}")
    
    print(f"[ADJUST TIMETABLE] ✓ Adjustment complete. {adjustments_made} classes assigned substitutes\n")
    
    return {
        "adjustments": adjustments_made,
        "log": adjustment_log
    }

def refresh_timetable_for_all_holidays():
    """
    Validate entire timetable against all faculty holidays.
    Uses MongoDB queries for efficiency.
    """
    total_adjustments = 0
    all_adjustment_logs = []
    
    # Get all faculty with holidays from MongoDB
    faculty_holidays_list = find_many(COLLECTIONS['faculty_holidays'])
    
    for fac_holiday in faculty_holidays_list:
        faculty_id = fac_holiday.get('faculty_id')
        holiday_dates = fac_holiday.get('dates', [])
        
        for date_str in holiday_dates:
            result = adjust_timetable_for_date_and_faculty(date_str, faculty_id)
            total_adjustments += result['adjustments']
            all_adjustment_logs.extend(result['log'])
    
    return {
        "total_adjustments": total_adjustments,
        "details": all_adjustment_logs,
        "message": f"✓ Timetable refreshed and verified. {total_adjustments} classes adjusted with substitutes."
    }

# ===== INITIALIZATION ENDPOINT =====
@app.route('/init-users', methods=['POST'])
def init_users():
    """Initialize MongoDB users collection from username.json"""
    try:
        # Load users from username.json
        username_file = os.path.join(DATA_DIR, 'username.json')
        if not os.path.exists(username_file):
            return jsonify({'message': 'username.json not found'}), 404
        
        with open(username_file, 'r') as f:
            users_from_json = json.load(f)
        
        if not isinstance(users_from_json, list):
            return jsonify({'message': 'username.json is not a list'}), 400
        
        # Clear existing users in MongoDB
        clear_collection(COLLECTIONS['users'])
        
        # Insert users into MongoDB
        if users_from_json:
            insert_many(COLLECTIONS['users'], users_from_json)
        
        # Reload USERS_DB
        load_users_db()
        
        return jsonify({
            'message': f'Successfully initialized {len(users_from_json)} users from username.json',
            'count': len(users_from_json)
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e), 'message': 'Failed to initialize users'}), 500

# ===== HEALTH CHECK ENDPOINT =====
@app.route('/', methods=['GET', 'OPTIONS'])
@app.route('/health', methods=['GET', 'OPTIONS'])
def health_check():
    """Health check endpoint to verify backend is running"""
    if request.method == 'OPTIONS':
        return '', 204
    
    return jsonify({
        'status': 'ok',
        'message': 'Timetable Management API is running',
        'timestamp': datetime.now().isoformat()
    }), 200

# ===== AUTHENTICATION ENDPOINTS =====
@app.route('/login', methods=['POST'])
def login():
    """Simple login endpoint - uses MongoDB"""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    user_type = data.get('user_type', 'student')
    
    if not email or not password:
        return jsonify({'message': 'Email and password are required'}), 400
    
    # Check user credentials from USERS_DB (loaded from MongoDB)
    user = USERS_DB.get(email)
    
    if not user or user['password'] != password:
        return jsonify({'message': 'Invalid email or password'}), 401
    
    # Verify user type matches
    if user['role'] != user_type:
        return jsonify({'message': f'This account is for {user["role"]}, not {user_type}'}), 403
    
    # Prepare response
    response_data = {
        'message': 'Login successful',
        'token': f'token_{user["id"]}_{email}',
        'role': user['role'],
        'user_id': user['id'],
        'name': user['name'],
        'email': email
    }
    
    # For students, add their class information from MongoDB
    if user_type == 'student':
        student = find_one(COLLECTIONS['students'], {'id': user['id']})
        if student:
            response_data['student_class'] = f"Class {student.get('class')}"

    # For faculty, include explicit faculty_id when available
    if user.get('role') == 'faculty':
        faculty_rec = find_one(COLLECTIONS['faculty'], {'email': email})
        if faculty_rec and faculty_rec.get('id'):
            response_data['faculty_id'] = faculty_rec.get('id')
    
    return jsonify(response_data), 200

@app.route('/register', methods=['POST'])
def register():
    """Register new user - public self-registration (optional) - uses MongoDB"""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')
    user_type = data.get('user_type', 'student')
    
    if not all([email, password, name]):
        return jsonify({'message': 'Email, password, and name are required'}), 400
    
    # Validate email format
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return jsonify({'message': 'Invalid email format'}), 400
    
    if email in USERS_DB:
        return jsonify({'message': 'Email already registered'}), 409
    
    # Get highest ID from MongoDB users collection
    users_list = load_collection_as_list(COLLECTIONS['users'])
    user_id = max([u.get('id', 0) for u in users_list], default=0) + 1
    
    # Create new user object
    new_user = {
        'email': email,
        'password': password,
        'role': user_type,
        'name': name,
        'id': user_id,
        'created_at': datetime.now().isoformat(),
        'status': 'active'
    }
    
    # Add to MongoDB
    insert_one(COLLECTIONS['users'], new_user)
    
    # Add to USERS_DB for immediate access
    USERS_DB[email] = {
        'password': password,
        'role': user_type,
        'name': name,
        'id': user_id,
        'status': 'active'
    }
    
    print(f"[REGISTER] New user registered: {email} (ID: {user_id})")
    
    # Return without exposing email
    return jsonify({
        'message': 'User registered successfully',
        'user_id': user_id,
        'role': user_type,
        'name': name
    }), 201

@app.route('/admin/create-user', methods=['POST'])
def admin_create_user():
    """Admin-only endpoint to create new users - uses MongoDB"""
    # Verify admin authentication
    auth_token = request.headers.get('Authorization', '')
    if not auth_token.startswith('Bearer '):
        return jsonify({'message': 'Unauthorized - Admin token required'}), 401
    
    # Verify admin token
    admin_email = None
    try:
        token_parts = auth_token.replace('Bearer ', '').split('_')
        if len(token_parts) >= 3:
            admin_email = '_'.join(token_parts[2:])
    except:
        pass
    
    # Check if user is admin
    if not admin_email or admin_email not in USERS_DB or USERS_DB[admin_email]['role'] != 'admin':
        return jsonify({'message': 'Unauthorized - Admin only'}), 403
    
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')
    role = data.get('role', 'student')
    
    # Validate required fields
    if not all([email, password, name]):
        return jsonify({'message': 'Email, password, and name are required'}), 400
    
    # Validate email format
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return jsonify({'message': 'Invalid email format'}), 400
    
    # Validate password strength
    if len(password) < 6:
        return jsonify({'message': 'Password must be at least 6 characters'}), 400
    
    # Validate role
    valid_roles = ['admin', 'faculty', 'student']
    if role not in valid_roles:
        return jsonify({'message': f'Invalid role. Must be one of: {", ".join(valid_roles)}'}), 400
    
    # Check if email already exists
    if email in USERS_DB:
        return jsonify({'message': 'Email already registered'}), 409
    
    # Get highest ID from MongoDB
    users_list = load_collection_as_list(COLLECTIONS['users'])
    user_id = max([u.get('id', 0) for u in users_list], default=0) + 1
    
    # Create new user object
    new_user = {
        'email': email,
        'password': password,
        'role': role,
        'name': name,
        'id': user_id,
        'created_at': datetime.now().isoformat(),
        'status': 'active'
    }
    
    # Add to MongoDB
    insert_one(COLLECTIONS['users'], new_user)
    
    # Add to USERS_DB
    USERS_DB[email] = {
        'password': password,
        'role': role,
        'name': name,
        'id': user_id,
        'status': 'active'
    }
    
    print(f"[ADMIN] Created new {role} user: {email} (ID: {user_id})")
    
    # Return without exposing email
    return jsonify({
        'message': f'{role.capitalize()} user created successfully',
        'user_id': user_id,
        'role': role,
        'name': name
    }), 201

@app.route('/admin/users', methods=['GET'])
def admin_get_users():
    """Admin endpoint to view all users - uses MongoDB"""
    # Verify admin authentication
    auth_token = request.headers.get('Authorization', '')
    if not auth_token.startswith('Bearer '):
        return jsonify({'message': 'Unauthorized - Admin token required'}), 401
    
    admin_email = None
    try:
        token_parts = auth_token.replace('Bearer ', '').split('_')
        if len(token_parts) >= 3:
            admin_email = '_'.join(token_parts[2:])
    except:
        pass
    
    if not admin_email or admin_email not in USERS_DB or USERS_DB[admin_email]['role'] != 'admin':
        return jsonify({'message': 'Unauthorized - Admin only'}), 403
    
    # Get all users from MongoDB
    users_list = load_collection_as_list(COLLECTIONS['users'])
    
    # Remove passwords and emails from response for security
    safe_users = [
        {
            'id': u.get('id'),
            'name': u.get('name'),
            'role': u.get('role'),
            'status': u.get('status')
        }
        for u in users_list
    ]
    return jsonify({
        'total': len(safe_users),
        'users': safe_users
    }), 200

@app.route('/admin/users/<int:user_id>', methods=['DELETE'])
def admin_delete_user(user_id):
    """Admin endpoint to delete a user - uses MongoDB"""
    # Verify admin authentication
    auth_token = request.headers.get('Authorization', '')
    if not auth_token.startswith('Bearer '):
        return jsonify({'message': 'Unauthorized - Admin token required'}), 401
    
    admin_email = None
    try:
        token_parts = auth_token.replace('Bearer ', '').split('_')
        if len(token_parts) >= 3:
            admin_email = '_'.join(token_parts[2:])
    except:
        pass
    
    if not admin_email or admin_email not in USERS_DB or USERS_DB[admin_email]['role'] != 'admin':
        return jsonify({'message': 'Unauthorized - Admin only'}), 403
    
    # Find user in MongoDB
    user_to_delete = find_one(COLLECTIONS['users'], {'id': user_id})
    if not user_to_delete:
        return jsonify({'message': 'User not found'}), 404
    
    deleted_email = user_to_delete.get('email')
    
    # Delete from MongoDB
    delete_many(COLLECTIONS['users'], {'id': user_id})
    
    # Remove from USERS_DB
    if deleted_email in USERS_DB:
        del USERS_DB[deleted_email]
    
    print(f"[ADMIN] Deleted user: {deleted_email} (ID: {user_id})")
    
    return jsonify({
        'message': 'User deleted successfully',
        'deleted_email': deleted_email,
        'user_id': user_id
    }), 200


@app.route('/admin/seed-missing-users', methods=['POST'])
def admin_seed_missing_users():
    """Admin endpoint: create `users` records for students and faculty without login accounts.
    Protect with admin token. Inserts minimal user docs with a default password and refreshes USERS_DB.
    """
    auth_token = request.headers.get('Authorization', '')
    if not auth_token.startswith('Bearer '):
        return jsonify({'message': 'Unauthorized - Admin token required'}), 401

    admin_email = None
    try:
        token_parts = auth_token.replace('Bearer ', '').split('_')
        if len(token_parts) >= 3:
            admin_email = '_'.join(token_parts[2:])
    except Exception:
        admin_email = None

    if not admin_email or admin_email not in USERS_DB or USERS_DB[admin_email]['role'] != 'admin':
        return jsonify({'message': 'Unauthorized - Admin only'}), 403

    try:
        students = load_collection_as_list(COLLECTIONS.get('students', 'students')) or []
        faculty = load_collection_as_list(COLLECTIONS.get('faculty', 'faculty')) or []
        existing_users = load_collection_as_list(COLLECTIONS.get('users', 'users')) or []

        existing_ids = set()
        existing_emails = set()
        existing_usernames = set()
        for u in existing_users:
            if u.get('id') is not None:
                try:
                    existing_ids.add(int(u.get('id')))
                except Exception:
                    existing_ids.add(u.get('id'))
            if u.get('email'):
                existing_emails.add(u.get('email'))
            if u.get('username'):
                existing_usernames.add(u.get('username'))

        to_insert = []

        # Seed students
        for s in students:
            sid = s.get('id')
            semail = s.get('email')
            susername = s.get('username') or semail
            already = False
            if sid is not None and sid in existing_ids:
                already = True
            if semail and semail in existing_emails:
                already = True
            if susername and susername in existing_usernames:
                already = True
            if not already:
                doc = {
                    'id': sid,
                    'name': s.get('name'),
                    'username': susername,
                    'email': semail,
                    'password': 'changeme123',
                    'role': 'student',
                    'created_at': datetime.now().isoformat()
                }
                to_insert.append(doc)

        # Seed faculty
        for f in faculty:
            fid = f.get('id')
            femail = f.get('email')
            funame = (f.get('email') or f.get('name'))
            already = False
            if fid is not None and fid in existing_ids:
                already = True
            if femail and femail in existing_emails:
                already = True
            if funame and funame in existing_usernames:
                already = True
            if not already:
                doc = {
                    'id': fid,
                    'name': f.get('name'),
                    'username': funame,
                    'email': femail,
                    'password': 'changeme123',
                    'role': 'faculty',
                    'created_at': datetime.now().isoformat()
                }
                to_insert.append(doc)

        inserted = 0
        inserted_usernames = []
        if to_insert:
            try:
                insert_many(COLLECTIONS.get('users', 'users'), to_insert)
                inserted = len(to_insert)
                inserted_usernames = [d.get('username') for d in to_insert]
                # Refresh in-memory mapping so endpoints see new users
                try:
                    load_users_db()
                except Exception:
                    pass
            except Exception as ie:
                print(f"[SEED-MISSING-USERS] Error inserting users: {str(ie)}")
                return jsonify({'message': 'Failed to insert users', 'error': str(ie)}), 500

        summary = {
            'students_scanned': len(students),
            'faculty_scanned': len(faculty),
            'created': inserted,
            'created_usernames': inserted_usernames
        }
        print(f"[SEED-MISSING-USERS] Summary: {summary}")
        return jsonify(summary), 200

    except Exception as e:
        print(f"[SEED-MISSING-USERS ERROR] {str(e)}")
        traceback.print_exc()
        return jsonify({'message': 'Error during seeding', 'error': str(e)}), 500

# ===== FACULTY ENDPOINTS =====
@app.route('/faculty', methods=['GET', 'POST'])
def faculty_management():
    if request.method == 'GET':
        faculty_data = load_collection_as_list(COLLECTIONS['faculty'])
        print(f"[FACULTY GET] Loaded {len(faculty_data)} faculty members from MongoDB")
        return jsonify(remove_objectid_fields(faculty_data))
    elif request.method == 'POST':
        try:
            data = request.get_json()
            print(f"[FACULTY POST] Received data: {data}")
            
            if not data:
                print(f"[FACULTY POST] No JSON data provided")
                return jsonify({"error": "No JSON data provided"}), 400
            
            # Validate required fields
            if not data.get('name') or not data.get('email'):
                print(f"[FACULTY POST] Missing required fields")
                return jsonify({"error": "Missing required fields: name, email"}), 400
            
            print(f"[FACULTY POST] Validation passed, calculating new ID...")
            faculty_data = load_collection_as_list(COLLECTIONS['faculty'])
            # Ensure faculty IDs start from 100 — use 99 as default base so first assigned is 100
            data['id'] = max([f.get('id', 0) for f in faculty_data], default=99) + 1
            
            # Normalize subject field to lowercase to avoid case mismatches
            if data.get('subject') and isinstance(data.get('subject'), str):
                data['subject'] = data['subject'].strip().lower()

            # Insert to MongoDB
            print(f"[FACULTY POST] New faculty ID: {data['id']}, inserting into database...")
            insert_one(COLLECTIONS['faculty'], data)
            
            # Automatically add subject if it doesn't exist
            subject_name = data.get('subject')
            if subject_name:
                subjects_data = load_collection_as_list(COLLECTIONS['subjects'])
                # compare case-insensitively (subjects stored normalized lowercase)
                subject_exists = any((s.get('name') or '').lower() == subject_name.lower() for s in subjects_data)
                if not subject_exists:
                    new_subject = {
                        'id': max([s.get('id', 0) for s in subjects_data], default=0) + 1,
                        'name': subject_name.strip().lower(),
                        'classes': data.get('classes', [])
                    }
                    insert_one(COLLECTIONS['subjects'], new_subject)
            
            print(f"[FACULTY POST] ✓ Faculty added successfully")
            # Remove ObjectId fields before returning
            response_data = remove_objectid_fields(data)
            return jsonify({"message": "Faculty added successfully", "data": response_data}), 201
        except Exception as e:
            print(f"[FACULTY POST ERROR] Exception: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"{type(e).__name__}: {str(e)}"}), 400

@app.route('/faculty/<int:faculty_id>', methods=['GET', 'PUT', 'DELETE'])
def faculty_detail(faculty_id):
    faculty = find_one(COLLECTIONS['faculty'], {'id': faculty_id})
    
    if request.method == 'GET':
        return jsonify(remove_objectid_fields(faculty)) if faculty else jsonify({"error": "Faculty not found"}), 404
    elif request.method == 'PUT':
        try:
            data = request.get_json()
            # Normalize subject if present
            if data.get('subject') and isinstance(data.get('subject'), str):
                data['subject'] = data['subject'].strip().lower()

            # Update the faculty record
            update_one(COLLECTIONS['faculty'], {'id': faculty_id}, {"$set": data})
            return jsonify({"message": "Faculty updated successfully", "data": data}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    elif request.method == 'DELETE':
        delete_many(COLLECTIONS['faculty'], {'id': faculty_id})
        return jsonify({"message": "Faculty deleted successfully"})

# ===== SUBJECT ENDPOINTS =====
@app.route('/subjects', methods=['GET', 'POST'])
def subject_management():
    if request.method == 'GET':
        subject_data = load_collection_as_list(COLLECTIONS['subjects'])
        return jsonify(remove_objectid_fields(subject_data))
    elif request.method == 'POST':
        data = request.get_json()
        # Normalize subject name
        if data.get('name') and isinstance(data.get('name'), str):
            data['name'] = data['name'].strip().lower()

        subject_data = load_collection_as_list(COLLECTIONS['subjects'])
        data['id'] = max([s.get('id', 0) for s in subject_data], default=0) + 1
        insert_one(COLLECTIONS['subjects'], data)
        return jsonify({"message": "Subject added successfully", "data": data}), 201

# ===== STUDENT ENDPOINTS =====
@app.route('/students', methods=['GET', 'POST'])
def student_management():
    if request.method == 'GET':
        print(f"[STUDENTS GET] Fresh database query initiated...")
        student_data = load_collection_as_list(COLLECTIONS['students'])
        print(f"[STUDENTS GET] ✓ Successfully fetched {len(student_data)} student records from MongoDB database")
        if student_data:
            print(f"[STUDENTS GET] Sample student record: {student_data[0]}")
        return jsonify(remove_objectid_fields(student_data))
    elif request.method == 'POST':
        try:
            data = request.get_json()
            print(f"[STUDENTS POST] Received data: {data}")
            
            if not data:
                print(f"[STUDENTS POST] No JSON data provided")
                return jsonify({"error": "No JSON data provided"}), 400
            
            # Validate required fields
            if not data.get('name') or not data.get('rollno') or not data.get('class'):
                print(f"[STUDENTS POST] Missing required fields")
                return jsonify({"error": "Missing required fields: name, rollno, class"}), 400
            
            print(f"[STUDENTS POST] Validation passed, fetching student data...")
            student_data = load_collection_as_list(COLLECTIONS['students'])
            data['id'] = max([s.get('id', 0) for s in student_data], default=0) + 1
            print(f"[STUDENTS POST] New student ID: {data['id']}, inserting into database...")
            insert_one(COLLECTIONS['students'], data)
            print(f"[STUDENTS POST] ✓ Student added successfully")
            # Remove ObjectId fields before returning
            response_data = remove_objectid_fields(data)
            return jsonify({"message": "Student added successfully", "data": response_data}), 201
        except Exception as e:
            print(f"[STUDENTS POST ERROR] Exception: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"{type(e).__name__}: {str(e)}"}), 400

# ===== TIMETABLE ENDPOINTS =====
@app.route('/timetable', methods=['GET', 'POST'])
def timetable_management():
    if request.method == 'GET':
        try:
            print(f"[TIMETABLE GET] Fresh database query initiated...")
            # Get all timetable from MongoDB
            timetable_data = get_timetable_flat()
            
            print(f"[TIMETABLE GET] ✓ Successfully fetched {len(timetable_data)} entries from MongoDB database")
            
            # Clean ObjectId fields before returning
            timetable_data = remove_objectid_fields(timetable_data)
            
            # Transform field names: teacher_name -> faculty, teacher_id -> faculty_id
            timetable_data = transform_timetable_entries(timetable_data)
            
            # Optional filters
            faculty_id = request.args.get('faculty_id')
            class_name = request.args.get('class')
            
            if faculty_id:
                try:
                    fid_req = int(faculty_id)
                    timetable_data = [t for t in timetable_data if (lambda v: (int(v) if (v is not None and not isinstance(v, int)) else v)(t.get('faculty_id')) == fid_req)]
                except Exception:
                    # fallback: compare as string
                    timetable_data = [t for t in timetable_data if str(t.get('faculty_id')) == str(faculty_id)]
                print(f"[TIMETABLE GET] Filtered by faculty_id {faculty_id}: {len(timetable_data)} entries")
            
            if class_name:
                timetable_data = [t for t in timetable_data if t.get('class') == class_name]
                print(f"[TIMETABLE GET] Filtered by class {class_name}: {len(timetable_data)} entries")
            
            return jsonify(timetable_data), 200
        except Exception as e:
            print(f"[TIMETABLE GET ERROR] {str(e)}")
            return jsonify({"error": str(e)}), 500
            
    elif request.method == 'POST':
        try:
            data = request.get_json()
            
            # Validate and normalize timetable entry before insert
            if not data or not data.get('date') or not data.get('time') or not data.get('class') or not data.get('subject'):
                return jsonify({"error": "Missing required timetable fields: date, time, class, subject"}), 400

            # Normalize subject to lowercase and verify subject exists
            subj_name = data.get('subject')
            if isinstance(subj_name, str):
                subj_key = subj_name.strip().lower()
            else:
                subj_key = str(subj_name).strip().lower()

            subj_doc = find_one(COLLECTIONS['subjects'], {'name': {'$regex': f'^{subj_key}$', '$options': 'i'}})
            if not subj_doc:
                return jsonify({"error": f"Subject '{data.get('subject')}' not found in subjects collection"}), 400

            data['subject'] = subj_key

            # Insert to MongoDB timetables collection
            insert_one(COLLECTIONS['timetables'], data)
            
            print(f"[TIMETABLE POST] New entry added to MongoDB")
            return jsonify({"message": "Timetable entry added", "data": data}), 201
        except Exception as e:
            print(f"[TIMETABLE POST ERROR] {str(e)}")
            return jsonify({"error": str(e)}), 500

@app.route('/timetable/refresh', methods=['POST'])
def refresh_timetable():
    """
    Refresh and validate entire timetable against all faculty holidays.
    Automatically assigns substitutes for all classes where faculty are on holiday.
    """
    try:
        print("[TIMETABLE REFRESH] Starting timetable refresh...")
        result = refresh_timetable_for_all_holidays()
        print(f"[TIMETABLE REFRESH] Complete. {result['total_adjustments']} adjustments made.")
        
        return jsonify({
            "message": result['message'],
            "total_adjustments": result['total_adjustments'],
            "details": result['details']
        }), 200
    except Exception as e:
        print(f"[TIMETABLE REFRESH ERROR] {str(e)}")
        return jsonify({"error": str(e), "message": "Error refreshing timetable"}), 500

@app.route('/adjust-overload', methods=['POST'])
def adjust_overload():
    # Deprecated endpoint removed. Use /redistribute-workload instead.
    # Keep a minimal response for backward compatibility.
    try:
        return jsonify({
            "message": "This endpoint is deprecated. Use /redistribute-workload instead.",
            "deprecated": True
        }), 410
    except Exception:
        return '', 410

# ===== LEAVE ENDPOINTS =====
@app.route('/apply_leave', methods=['POST'])
def apply_leave():
    """Faculty requests leave (creates pending request)"""
    try:
        data = request.get_json()
        print(f"[APPLY LEAVE] Received data: {data}")
        
        # Validate required fields
        if not data.get('faculty_id') or not data.get('date'):
            return jsonify({"message": "faculty_id and date are required"}), 400
        
        # Check if faculty exists
        faculty = find_one(COLLECTIONS['faculty'], {'id': int(data.get('faculty_id'))})
        if not faculty:
            return jsonify({"error": "Faculty not found"}), 404
        
        print(f"[APPLY LEAVE] Found faculty: {faculty.get('name')}")
        
        # Check if leave request already exists for this date
        existing_leave = find_one(COLLECTIONS['leaves'], {
            'faculty_id': int(data.get('faculty_id')),
            'date': data.get('date'),
            'status': {'$in': ['pending', 'approved']}
        })
        
        if existing_leave:
            return jsonify({
                "message": "Leave request already exists for this date",
                "status": existing_leave.get('status')
            }), 409
        
        leave_request = {
            'faculty_id': int(data.get('faculty_id')),
            'faculty_name': faculty.get('name'),
            'date': data.get('date'),
            'reason': data.get('reason', ''),
            'status': 'pending',  # Always starts as pending
            'requested_at': datetime.now().isoformat(),
            'admin_action_at': None,
            'admin_notes': ''
        }
        
        result = insert_one(COLLECTIONS['leaves'], leave_request)
        print(f"[APPLY LEAVE] Insert result: {result}")
        
        # Fetch the created document to get _id
        created_leave = find_one(COLLECTIONS['leaves'], {
            'faculty_id': int(data.get('faculty_id')),
            'date': data.get('date')
        })
        
        print(f"[APPLY LEAVE] Created leave document: {created_leave}")
        
        if not created_leave:
            print(f"[APPLY LEAVE ERROR] Failed to retrieve created leave document")
            return jsonify({"error": "Failed to create leave request"}), 500
        
        formatted_leave = format_leave_for_response(created_leave)
        print(f"[APPLY LEAVE] Formatted leave response: {formatted_leave}")
        
        if not formatted_leave:
            print(f"[APPLY LEAVE ERROR] Failed to format leave response")
            return jsonify({"error": "Failed to format leave response"}), 500
        
        print(f"[APPLY LEAVE] Leave has id field: {'id' in formatted_leave}")
        
        return jsonify({
            "message": "Leave request submitted successfully. Awaiting admin approval.",
            "status": "pending",
            "data": formatted_leave
        }), 201
    
    except Exception as e:
        print(f"[APPLY LEAVE ERROR] Exception occurred: {str(e)}")
        print(f"[APPLY LEAVE ERROR] Exception type: {type(e).__name__}")
        import traceback
        print(f"[APPLY LEAVE ERROR] Traceback: {traceback.format_exc()}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/leaves', methods=['GET'])
def get_leaves():
    """Get leave requests with optional filters"""
    faculty_id = request.args.get('faculty_id')
    status_filter = request.args.get('status')  # pending, approved, rejected
    
    query = {}
    if faculty_id:
        query['faculty_id'] = int(faculty_id)
    if status_filter:
        query['status'] = status_filter
    
    leaves_data = find_many(COLLECTIONS['leaves'], query)
    print(f"[LEAVES GET] Retrieved {len(leaves_data)} leave requests with filters: {query}")
    
    return jsonify(format_leaves_for_response(leaves_data))


@app.route('/redistribute-workload', methods=['POST'])
def redistribute_workload():
    """Safer workload redistribution.
    Request JSON:
      - threshold: hours above which a faculty is considered overloaded (default 20)
      - apply: boolean (default False) - if True and authorized, changes are applied
      - confirm: boolean (default False) - must be True with apply to prevent accidents

    Returns a dry-run by default listing proposed adjustments. To apply, send
    Authorization: Bearer <token> where token indicates an admin (same logic as other admin endpoints),
    and set apply=true and confirm=true.
    """
    try:
        data = request.get_json() or {}
        # threshold: hours above which a faculty is considered overloaded (default 30)
        threshold = int(data.get('threshold', 30))
        # min_week_hours: below this faculty considered underloaded (default 25)
        min_week_hours = int(data.get('min_week_hours', 25))
        do_apply = bool(data.get('apply', False))
        confirm = bool(data.get('confirm', False))

        # simple admin check using existing token parsing
        auth_token = request.headers.get('Authorization', '')
        admin_email = None
        try:
            token_parts = auth_token.replace('Bearer ', '').split('_')
            if len(token_parts) >= 3:
                admin_email = '_'.join(token_parts[2:])
        except Exception:
            admin_email = None

        is_admin = admin_email and admin_email in USERS_DB and USERS_DB[admin_email]['role'] == 'admin'

        # Load data
        faculty_data = find_many(COLLECTIONS['faculty'], {})
        timetable_data = find_many(COLLECTIONS['timetables'], {})
        timetable_data_to_use = timetable_data if isinstance(timetable_data, list) else []

        # Build workload mapping (accept teacher_id legacy field too)
        faculty_workload = {}
        for entry in timetable_data_to_use:
            fid = entry.get('faculty_id') if entry.get('faculty_id') is not None else entry.get('teacher_id')
            faculty_workload.setdefault(fid, []).append(entry)

        proposals = []

        # Identify overloaded faculty
        overloaded = [f for f in faculty_data if len(faculty_workload.get(f.get('id'), [])) > threshold]

        for fac in overloaded:
            fac_id = fac.get('id')
            fac_name = fac.get('name')
            current_hours = len(faculty_workload.get(fac_id, []))
            entries = list(faculty_workload.get(fac_id, []))
            # propose to move up to min(30% of excess, len(entries))
            excess = current_hours - threshold
            if excess <= 0:
                continue
            num_to_move = max(1, (excess * 30) // 100)
            num_to_move = min(len(entries), num_to_move)

            moved = 0
            for entry in entries:
                if moved >= num_to_move:
                    break
                date_str = entry.get('date')
                subject = entry.get('subject', '').lower()
                class_name = entry.get('class')

                # find available faculty of same subject
                candidates = [o for o in faculty_data if o.get('id') != fac_id and o.get('subject', '').lower() == subject]
                # filter by availability and workload
                available = []
                for c in candidates:
                    cid = c.get('id')
                    if date_str in get_faculty_unavailable_dates(cid):
                        continue
                    c_hours = len(faculty_workload.get(cid, []))
                    if c_hours >= threshold:
                        continue
                    available.append((cid, c.get('name'), c_hours))

                if not available:
                    proposals.append({
                        'from': {'id': fac_id, 'name': fac_name},
                        'date': date_str,
                        'class': class_name,
                        'subject': subject,
                        'status': 'no_candidate'
                    })
                    continue

                available.sort(key=lambda x: x[2])
                new_cid, new_name, new_hours = available[0]

                proposals.append({
                    'from': {'id': fac_id, 'name': fac_name},
                    'to': {'id': new_cid, 'name': new_name},
                    'date': date_str,
                    'class': class_name,
                    'subject': subject,
                    'from_hours_before': current_hours,
                    'to_hours_before': new_hours,
                    'status': 'proposed'
                })
                moved += 1

        # If apply requested, require admin and confirm
        applied = 0
        if do_apply:
            if not is_admin or not confirm:
                return jsonify({
                    'error': 'apply_requires_admin_and_confirm',
                    'message': 'To apply changes you must be an admin and set confirm=true'
                }), 403

            # Backup timetable collection
            backup_path = os.path.join('data', 'backups', f'redistribute_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(timetable_data_to_use, f, indent=2, ensure_ascii=False)

            # apply proposals: update MongoDB entries matching date/class/subject
            for p in proposals:
                if p.get('status') != 'proposed':
                    continue
                q = {'date': p['date'], 'class': p['class'], 'subject': p['subject'], '$or': [{'faculty_id': p['from']['id']}, {'teacher_id': p['from']['id']}]}
                update_count = update_many(COLLECTIONS['timetables'], q, {'$set': {'faculty_id': p['to']['id'], 'faculty': p['to']['name']}})
                if update_count:
                    applied += update_count

        return jsonify({
            'threshold': threshold,
            'min_week_hours': min_week_hours,
            'proposals_count': len(proposals),
            'proposals': proposals[:200],
            'applied': applied
        }), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/leaves-pending', methods=['GET'])
def admin_get_pending_leaves():
    """Admin endpoint: Get all pending leave requests"""
    # Verify admin authentication
    auth_token = request.headers.get('Authorization', '')
    if not auth_token.startswith('Bearer '):
        return jsonify({'message': 'Unauthorized - Admin token required'}), 401
    
    admin_email = None
    try:
        token_parts = auth_token.replace('Bearer ', '').split('_')
        if len(token_parts) >= 3:
            admin_email = '_'.join(token_parts[2:])
    except:
        pass
    
    if not admin_email or admin_email not in USERS_DB or USERS_DB[admin_email]['role'] != 'admin':
        return jsonify({'message': 'Unauthorized - Admin only'}), 403
    
    # Get all pending leave requests
    pending_leaves = find_many(COLLECTIONS['leaves'], {'status': 'pending'})
    
    # Format leaves for response
    formatted = format_leaves_for_response(pending_leaves)
    
    return jsonify(formatted), 200

@app.route('/admin/leaves-history', methods=['GET'])
def admin_get_leaves_history():
    """Admin endpoint: Get all leave requests (approved, rejected, pending)"""
    # Verify admin authentication
    auth_token = request.headers.get('Authorization', '')
    if not auth_token.startswith('Bearer '):
        return jsonify({'message': 'Unauthorized - Admin token required'}), 401
    
    admin_email = None
    try:
        token_parts = auth_token.replace('Bearer ', '').split('_')
        if len(token_parts) >= 3:
            admin_email = '_'.join(token_parts[2:])
    except:
        pass
    
    if not admin_email or admin_email not in USERS_DB or USERS_DB[admin_email]['role'] != 'admin':
        return jsonify({'message': 'Unauthorized - Admin only'}), 403
    
    # Get all leave requests
    all_leaves = find_many(COLLECTIONS['leaves'])
    print(f"[ADMIN HISTORY] Retrieved {len(all_leaves)} total leave requests (all statuses)")
    
@app.route('/admin/notifications', methods=['GET'])
def admin_get_notifications():
    """Admin endpoint: List admin notification cards"""
    # Verify admin authentication
    auth = request.headers.get('Authorization')
    if not auth or not auth.startswith('Bearer '):
        return jsonify({'message': 'Unauthorized - Admin token required'}), 401
    token = auth.split(' ', 1)[1]
    admin_email = None
    try:
        token_parts = token.split('_')
        if len(token_parts) >= 3:
            admin_email = '_'.join(token_parts[2:])
    except Exception:
        admin_email = None

    if not admin_email or admin_email not in USERS_DB or USERS_DB[admin_email]['role'] != 'admin':
        return jsonify({'message': 'Unauthorized - Admin only'}), 403

    try:
        coll = COLLECTIONS.get('admin_notifications', 'admin_notifications')
        docs = find_many(coll, {})
        # map _id to id and return newest first
        cards = []
        for d in docs:
            card = d.copy()
            _id = card.pop('_id', None)
            card['id'] = str(_id) if _id is not None else None
            cards.append(card)
        # sort by created_at desc if present
        cards.sort(key=lambda c: c.get('created_at',''), reverse=True)
        return jsonify(cards), 200
    except Exception as ex:
        return jsonify({'message': 'Failed to fetch notifications', 'error': str(ex)}), 500


@app.route('/admin/notifications/<notif_id>/read', methods=['PUT'])
def admin_mark_notification_read(notif_id):
    """Mark a notification card as read"""
    auth = request.headers.get('Authorization')
    if not auth or not auth.startswith('Bearer '):
        return jsonify({'message': 'Unauthorized - Admin token required'}), 401
    token = auth.split(' ', 1)[1]
    admin_email = None
    try:
        token_parts = token.split('_')
        if len(token_parts) >= 3:
            admin_email = '_'.join(token_parts[2:])
    except Exception:
        admin_email = None

    if not admin_email or admin_email not in USERS_DB or USERS_DB[admin_email]['role'] != 'admin':
        return jsonify({'message': 'Unauthorized - Admin only'}), 403

    try:
        coll = COLLECTIONS.get('admin_notifications', 'admin_notifications')
        # update by ObjectId
        result = update_one(coll, {'_id': ObjectId(notif_id)}, {'$set': {'read': True}})
        if result:
            return jsonify({'message': 'Marked read'}), 200
        else:
            return jsonify({'message': 'Not found'}), 404
    except Exception as ex:
        return jsonify({'message': 'Failed to mark read', 'error': str(ex)}), 500

    return jsonify(format_leaves_for_response(all_leaves)), 200

@app.route('/admin/leave/<leave_id>/approve', methods=['PUT'])
def admin_approve_leave(leave_id):
    """Admin endpoint: Approve a leave request and adjust timetable"""
    # Verify admin authentication
    auth_token = request.headers.get('Authorization', '')
    if not auth_token.startswith('Bearer '):
        return jsonify({'message': 'Unauthorized - Admin token required'}), 401
    
    admin_email = None
    try:
        token_parts = auth_token.replace('Bearer ', '').split('_')
        if len(token_parts) >= 3:
            admin_email = '_'.join(token_parts[2:])
    except:
        pass
    
    if not admin_email or admin_email not in USERS_DB or USERS_DB[admin_email]['role'] != 'admin':
        return jsonify({'message': 'Unauthorized - Admin only'}), 403
    
    try:
        data = request.get_json() or {}
        admin_notes = data.get('notes', '')
        
        print(f"[ADMIN APPROVE] Received approval request for leave_id: {leave_id}")
        print(f"[ADMIN APPROVE] Admin notes: '{admin_notes}'")
        print(f"[ADMIN APPROVE] Leave ID type: {type(leave_id)}, Length: {len(leave_id) if leave_id else 0}")
        
        # Validate and convert string leave_id to MongoDB ObjectId
        if not leave_id or not isinstance(leave_id, str) or len(leave_id.strip()) == 0:
            print(f"[ADMIN APPROVE] Leave ID is empty or invalid")
            return jsonify({"error": "Invalid leave ID: ID cannot be empty", "received_id": leave_id}), 400
        
        try:
            leave_obj_id = ObjectId(leave_id.strip())
            print(f"[ADMIN APPROVE] Converted to ObjectId: {leave_obj_id}")
        except Exception as e:
            print(f"[ADMIN APPROVE] ObjectId conversion failed: {str(e)}")
            return jsonify({"error": f"Invalid leave ID format. Expected 24-char hex string, got: {leave_id}", "received_id": leave_id}), 400
        
        # Find leave request
        leave = find_one(COLLECTIONS['leaves'], {'_id': leave_obj_id})
        print(f"[ADMIN APPROVE] Found leave: {leave is not None}")
        
        if not leave:
            print(f"[ADMIN APPROVE] Leave not found for ObjectId: {leave_obj_id}")
            return jsonify({"error": "Leave request not found"}), 404
        
        print(f"[ADMIN APPROVE] Current leave status: {leave.get('status')}")
        
        if leave.get('status') != 'pending':
            print(f"[ADMIN APPROVE] Cannot approve - status is not pending")
            return jsonify({
                "error": f"Cannot approve leave with status '{leave.get('status')}'",
                "message": "Only pending leaves can be approved"
            }), 400
        
        faculty_id = leave.get('faculty_id')
        date_str = leave.get('date')
        
        # Update leave status to approved
        print(f"[ADMIN APPROVE] Updating leave status to 'approved'...")
        update_result = update_one(COLLECTIONS['leaves'],
                  {'_id': leave_obj_id},
                  {'$set': {
                      'status': 'approved',
                      'admin_action_at': datetime.now().isoformat(),
                      'admin_notes': admin_notes,
                      'approved_by': admin_email
                  }})
        
        print(f"[ADMIN APPROVE] Update result: {update_result} document(s) modified")
        
        # Verify the update
        updated_leave = find_one(COLLECTIONS['leaves'], {'_id': leave_obj_id})
        print(f"[ADMIN APPROVE] Verified status after update: {updated_leave.get('status')}")
        
        print(f"[ADMIN] Approved leave for faculty {faculty_id} on {date_str}")
        
        # 🔄 AUTO-ADJUST TIMETABLE FOR APPROVED LEAVE
        result = adjust_timetable_for_date_and_faculty(date_str, faculty_id)
        
        return jsonify({
            "message": "Leave approved successfully and timetable adjusted",
            "status": "approved",
            "faculty_id": faculty_id,
            "date": date_str,
            "timetable_adjustments": {
                "count": result['adjustments'],
                "details": result['log']
            }
        }), 200
    except Exception as e:
        print(f"[ADMIN LEAVE ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/admin/leave/<leave_id>/reject', methods=['PUT'])
def admin_reject_leave(leave_id):
    """Admin endpoint: Reject a leave request (no timetable change)"""
    # Verify admin authentication
    auth_token = request.headers.get('Authorization', '')
    if not auth_token.startswith('Bearer '):
        return jsonify({'message': 'Unauthorized - Admin token required'}), 401
    
    admin_email = None
    try:
        token_parts = auth_token.replace('Bearer ', '').split('_')
        if len(token_parts) >= 3:
            admin_email = '_'.join(token_parts[2:])
    except:
        pass
    
    if not admin_email or admin_email not in USERS_DB or USERS_DB[admin_email]['role'] != 'admin':
        return jsonify({'message': 'Unauthorized - Admin only'}), 403
    
    try:
        data = request.get_json() or {}
        rejection_reason = data.get('reason', 'Not specified')
        
        print(f"[ADMIN REJECT] Received rejection request for leave_id: {leave_id}")
        print(f"[ADMIN REJECT] Leave ID type: {type(leave_id)}, Length: {len(leave_id) if leave_id else 0}")
        
        # Validate and convert string leave_id to MongoDB ObjectId
        if not leave_id or not isinstance(leave_id, str) or len(leave_id.strip()) == 0:
            print(f"[ADMIN REJECT] Leave ID is empty or invalid")
            return jsonify({"error": "Invalid leave ID: ID cannot be empty", "received_id": leave_id}), 400
        
        try:
            leave_obj_id = ObjectId(leave_id.strip())
            print(f"[ADMIN REJECT] Converted to ObjectId: {leave_obj_id}")
        except Exception as e:
            print(f"[ADMIN REJECT] ObjectId conversion failed: {str(e)}")
            return jsonify({"error": f"Invalid leave ID format. Expected 24-char hex string, got: {leave_id}", "received_id": leave_id}), 400
        
        # Find leave request
        leave = find_one(COLLECTIONS['leaves'], {'_id': leave_obj_id})
        
        if not leave:
            return jsonify({"error": "Leave request not found"}), 404
        
        if leave.get('status') != 'pending':
            return jsonify({
                "error": f"Cannot reject leave with status '{leave.get('status')}'",
                "message": "Only pending leaves can be rejected"
            }), 400
        
        faculty_id = leave.get('faculty_id')
        date_str = leave.get('date')
        
        # Update leave status to rejected
        update_one(COLLECTIONS['leaves'],
                  {'_id': leave_obj_id},
                  {'$set': {
                      'status': 'rejected',
                      'admin_action_at': datetime.now().isoformat(),
                      'rejection_reason': rejection_reason,
                      'rejected_by': admin_email
                  }})
        
        print(f"[ADMIN] Rejected leave for faculty {faculty_id} on {date_str} - Reason: {rejection_reason}")
        
        # NO TIMETABLE ADJUSTMENT - Faculty still works
        return jsonify({
            "message": "Leave request rejected successfully. No timetable changes made.",
            "status": "rejected",
            "faculty_id": faculty_id,
            "date": date_str,
            "reason": rejection_reason
        }), 200
    except Exception as e:
        print(f"[ADMIN LEAVE ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# Keep old endpoint for backward compatibility but mark as deprecated
@app.route('/approve_leave/<int:leave_id>', methods=['PUT'])
def approve_leave(leave_id):
    """[DEPRECATED] Use /admin/leave/<leave_id>/approve instead"""
    return jsonify({"message": "This endpoint is deprecated. Use /admin/leave/<leave_id>/approve instead"}), 400

# ===== WORKLOAD ENDPOINTS =====
@app.route('/workload', methods=['GET', 'POST'])
def workload_management():
    if request.method == 'GET':
        faculty_id = request.args.get('faculty_id')
        # Calculate workload based on timetable entries from MongoDB
        
        if faculty_id:
            try:
                fid = int(faculty_id)
            except Exception:
                fid = faculty_id

            # Load public holidays and per-faculty holidays
            public_holidays = {h.get('date') for h in load_collection_as_list(COLLECTIONS.get('holidays', 'holidays')) if h.get('date')}
            fac_hol_list = load_collection_as_list(COLLECTIONS.get('faculty_holidays', 'faculty_holidays'))
            fac_hol_map = {fh.get('faculty_id'): set(fh.get('dates', [])) for fh in fac_hol_list}

            # Find timetable entries for this faculty (accept legacy teacher_id too)
            entries = find_many(COLLECTIONS['timetables'], {'$or': [{'faculty_id': fid}, {'teacher_id': fid}]})
            count = 0
            for e in entries:
                d = e.get('date')
                # skip counting on public holidays or this faculty's holiday dates
                if d and (d in public_holidays or d in fac_hol_map.get(fid, set())):
                    continue
                count += 1

            return jsonify({"faculty_id": faculty_id, "hours": count})
    
    elif request.method == 'POST':
        data = request.get_json()
        # Save workload limit
        return jsonify({"message": "Workload limit updated", "data": data}), 201

@app.route('/workload-limit', methods=['POST'])
def workload_limit():
    data = request.get_json()
    # Store workload limit (max hours per faculty)
    return jsonify({"message": "Workload limit set successfully", "max_hours": data.get('maxHours')}), 201

@app.route('/faculty-workload', methods=['GET'])
def faculty_workload():
    """Get workload for all faculty based on timetable entries from MongoDB"""
    try:
        faculty_data = load_collection_as_list(COLLECTIONS['faculty'])
        timetable_data = get_timetable_flat()
        timetable_data = remove_objectid_fields(timetable_data)
        timetable_data = transform_timetable_entries(timetable_data)
        
        # Load holidays once (public and per-faculty)
        public_holidays = {h.get('date') for h in load_collection_as_list(COLLECTIONS.get('holidays', 'holidays')) if h.get('date')}
        fac_hol_list = load_collection_as_list(COLLECTIONS.get('faculty_holidays', 'faculty_holidays'))
        fac_hol_map = {fh.get('faculty_id'): set(fh.get('dates', [])) for fh in fac_hol_list}

        workload_list = []
        for faculty in faculty_data:
            faculty_id = faculty.get('id')
            # normalize faculty id for comparison
            try:
                fid_norm = int(faculty_id) if faculty_id is not None else None
            except Exception:
                fid_norm = faculty_id

            faculty_hours = 0
            for t in timetable_data:
                try:
                    tfid = t.get('faculty_id')
                    tfid_norm = int(tfid) if tfid is not None else None
                except Exception:
                    tfid_norm = t.get('faculty_id')
                if tfid_norm == fid_norm:
                    # Exclude if date is a public holiday or this faculty's holiday
                    date_str = t.get('date')
                    if date_str and (date_str in public_holidays or date_str in fac_hol_map.get(fid_norm, set())):
                        continue
                    faculty_hours += 1
            
            workload_list.append({
                'id': faculty_id,
                'name': faculty.get('name'),
                'email': faculty.get('email'),
                'subject': faculty.get('subject'),
                'hours': faculty_hours,
                'classes': faculty_hours
            })
        
        return jsonify(workload_list), 200
    except Exception as e:
        print(f"[WORKLOAD ERROR] {str(e)}")
        return jsonify({"error": str(e)}), 500

# ===== HOLIDAYS ENDPOINTS =====
@app.route('/holidays', methods=['GET', 'POST'])
def holidays_management():
    if request.method == 'GET':
        holiday_data = load_collection_as_list(COLLECTIONS['holidays'])
        return jsonify(remove_objectid_fields(holiday_data))
    elif request.method == 'POST':
        try:
            data = request.get_json()
            print(f"[HOLIDAYS POST] Received data: {data}")
            
            if not data:
                print(f"[HOLIDAYS POST] No JSON data provided")
                return jsonify({"error": "No JSON data provided"}), 400
            
            # Validate required fields
            if not data.get('date') or not data.get('name'):
                print(f"[HOLIDAYS POST] Missing required fields")
                return jsonify({"error": "Missing required fields: date, name"}), 400
            
            # Check if holiday already exists on this date
            holiday_data = load_collection_as_list(COLLECTIONS['holidays'])
            existing_holiday = any(h.get('date') == data.get('date') for h in holiday_data)
            if existing_holiday:
                print(f"[HOLIDAYS POST] Holiday already exists on date: {data.get('date')}")
                return jsonify({"error": f"A holiday already exists on {data.get('date')}"}), 400
            
            print(f"[HOLIDAYS POST] Validation passed, creating holiday...")
            data['id'] = max([h.get('id', 0) for h in holiday_data], default=0) + 1
            insert_one(COLLECTIONS['holidays'], data)
            print(f"[HOLIDAYS POST] ✓ Holiday added successfully")
            # Remove ObjectId fields before returning
            response_data = remove_objectid_fields(data)
            return jsonify({"message": "Holiday added successfully", "data": response_data}), 201
        except Exception as e:
            print(f"[HOLIDAYS POST ERROR] Exception: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"{type(e).__name__}: {str(e)}"}), 400

@app.route('/holidays/<int:holiday_id>', methods=['DELETE'])
def delete_holiday(holiday_id):
    """Delete a holiday by ID"""
    try:
        print(f"[HOLIDAYS DELETE] Deleting holiday with ID: {holiday_id}")
        result = delete_many(COLLECTIONS['holidays'], {'id': holiday_id})
        
        if result == 0:
            print(f"[HOLIDAYS DELETE] Holiday not found with ID: {holiday_id}")
            return jsonify({"error": f"Holiday with ID {holiday_id} not found"}), 404
        
        print(f"[HOLIDAYS DELETE] ✓ Holiday deleted successfully")
        return jsonify({"message": "Holiday deleted successfully"}), 200
    except Exception as e:
        print(f"[HOLIDAYS DELETE ERROR] Exception: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"{type(e).__name__}: {str(e)}"}), 400

# ===== WORKING DAYS ENDPOINTS =====
@app.route('/working-days', methods=['GET', 'POST'])
def working_days_management():
    if request.method == 'GET':
        # Return default working days or saved config
        return jsonify({
            "monday": True,
            "tuesday": True,
            "wednesday": True,
            "thursday": True,
            "friday": True,
            "saturday": True,
            "sunday": False
        })
    elif request.method == 'POST':
        data = request.get_json()
        # Save working days configuration
        return jsonify({"message": "Working days updated successfully", "data": data}), 201


@app.route('/timetable-months', methods=['GET'])
def timetable_months():
    """Return list of available months from MongoDB timetables collection."""
    try:
        # Get all unique months from MongoDB
        timetable_data = get_timetable_flat()
        timetable_data = remove_objectid_fields(timetable_data)
        
        available_months = set()
        for entry in timetable_data:
            # Parse date field (format: "2026-04-01") to extract month and year
            date_str = entry.get('date')
            if date_str:
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    month_label = dt.strftime("%B %Y")
                    available_months.add(month_label)
                except (ValueError, TypeError):
                    continue
        
        # Sort and return (most recent first)
        sorted_months = sorted(list(available_months), reverse=True)
        print(f"[TIMETABLE MONTHS] Returning {len(sorted_months)} months from MongoDB: {sorted_months}")
        return jsonify(sorted_months), 200
    except Exception as e:
        print(f"[TIMETABLE MONTHS ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/classes', methods=['GET'])
def timetable_classes():
    """Return list of classes from MongoDB classes collection with a normalized `display` field."""
    try:
        docs = find_many(COLLECTIONS.get('classes'), {}) or []
        cleaned = remove_objectid_fields(docs)
        out = []
        for d in cleaned:
            item = dict(d)
            display = item.get('label') or item.get('name') or (f"Class {item.get('id')}" if item.get('id') is not None else None)
            item['display'] = display
            out.append(item)
        return jsonify(out), 200
    except Exception as e:
        print(f"[TIMETABLE CLASSES ERROR] {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/timetable/daily', methods=['GET'])
def timetable_daily():
    """Return timetable entries for a given class on a specific date.
    Query params: ?class=Class%20A&date=YYYY-MM-DD
    """
    class_name = request.args.get('class')
    date_str = request.args.get('date')
    if not class_name or not date_str:
        return jsonify({"error": "Missing required parameters: class and date (YYYY-MM-DD)"}), 400
    try:
        # Parse and validate date
        try:
            req_dt = datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

        # Load public holidays
        public_holidays = {h.get('date') for h in load_collection_as_list(COLLECTIONS.get('holidays', 'holidays')) if h.get('date')}

        # Load working days config if present in DB, otherwise use default (Sunday off)
        working_days_docs = load_collection_as_list(COLLECTIONS.get('working_days', 'working_days')) or []
        if working_days_docs and isinstance(working_days_docs, list) and len(working_days_docs) > 0:
            wd = working_days_docs[0]
            working_days = {
                'monday': bool(wd.get('monday', True)),
                'tuesday': bool(wd.get('tuesday', True)),
                'wednesday': bool(wd.get('wednesday', True)),
                'thursday': bool(wd.get('thursday', True)),
                'friday': bool(wd.get('friday', True)),
                'saturday': bool(wd.get('saturday', True)),
                'sunday': bool(wd.get('sunday', False)),
            }
        else:
            working_days = {
                'monday': True, 'tuesday': True, 'wednesday': True,
                'thursday': True, 'friday': True, 'saturday': True, 'sunday': False
            }

        # If requested date is a public holiday or non-working day, return empty list
        # weekday(): Monday=0 .. Sunday=6 -> map to keys order
        weekday_keys = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
        if date_str in public_holidays or not working_days.get(weekday_keys[req_dt.weekday()], True):
            return jsonify([]), 200

        entries = get_timetable_flat({'class': class_name, 'date': date_str})
        entries = remove_objectid_fields(entries)
        entries = transform_timetable_entries(entries)

        # Filter out any entries that fall on a public holiday or non-working day (safety)
        filtered = []
        for e in entries:
            d = e.get('date')
            if not d:
                continue
            if d in public_holidays:
                continue
            try:
                edt = datetime.strptime(d, "%Y-%m-%d")
            except Exception:
                continue
            if not working_days.get(weekday_keys[edt.weekday()], True):
                continue
            filtered.append(e)

        return jsonify(filtered), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/timetable/weekly', methods=['GET'])
def timetable_weekly():
    """Return timetable entries for a given class for a week.
    Query params: ?class=Class%20A&week_start=YYYY-MM-DD (week_start is Monday)
    """
    class_name = request.args.get('class')
    week_start = request.args.get('week_start')
    if not class_name or not week_start:
        return jsonify({"error": "Missing required parameters: class and week_start (YYYY-MM-DD)"}), 400
    try:
        start_dt = datetime.fromisoformat(week_start)
        end_dt = start_dt + timedelta(days=6)
    except Exception:
        return jsonify({"error": "Invalid week_start format. Use YYYY-MM-DD"}), 400

    try:
        entries = get_timetable_flat({'class': class_name})
        weekly = []
        for e in entries:
            d = e.get('date')
            if not d:
                continue
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
            except Exception:
                continue
            # Load public holidays once per loop and working days config
            public_holidays = {h.get('date') for h in load_collection_as_list(COLLECTIONS.get('holidays', 'holidays')) if h.get('date')}
            working_days_docs = load_collection_as_list(COLLECTIONS.get('working_days', 'working_days')) or []
            if working_days_docs and isinstance(working_days_docs, list) and len(working_days_docs) > 0:
                wd = working_days_docs[0]
                working_days = {
                    0: bool(wd.get('monday', True)),
                    1: bool(wd.get('tuesday', True)),
                    2: bool(wd.get('wednesday', True)),
                    3: bool(wd.get('thursday', True)),
                    4: bool(wd.get('friday', True)),
                    5: bool(wd.get('saturday', True)),
                    6: bool(wd.get('sunday', False)),
                }
            else:
                working_days = {0: True, 1: True, 2: True, 3: True, 4: True, 5: True, 6: False}

            if start_dt.date() <= dt.date() <= end_dt.date():
                if d in public_holidays:
                    continue
                if not working_days.get(dt.weekday(), True):
                    continue
                weekly.append(e)

        weekly = remove_objectid_fields(weekly)
        weekly = transform_timetable_entries(weekly)
        return jsonify(weekly), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/timetable-month/<path:month_label>', methods=['GET'])
def timetable_month(month_label):
    """Return entries for a specific month from MongoDB (e.g., 'February 2026')."""
    try:
        print(f"\n[TIMETABLE-MONTH] Requested month: {month_label}")
        
        # Parse month_label: "February 2026"
        try:
            dt = datetime.strptime(month_label, "%B %Y")
            month = dt.month
            year = dt.year
            print(f"[TIMETABLE-MONTH] Parsed as month={month}, year={year}")
        except ValueError:
            return jsonify({"error": f"Invalid month format. Use 'Month Year' (e.g., 'February 2026')"}), 400
        
        # Query MongoDB for timetables in this month/year by filtering date field
        timetable_data = get_timetable_flat()
        timetable_data = remove_objectid_fields(timetable_data)
        
        # Filter entries for the requested month/year
        monthly_data = []
        for entry in timetable_data:
            date_str = entry.get('date')
            if date_str:
                try:
                    entry_dt = datetime.strptime(date_str, "%Y-%m-%d")
                    if entry_dt.month == month and entry_dt.year == year:
                        monthly_data.append(entry)
                except (ValueError, TypeError):
                    continue
        
        # Transform field names: teacher_name -> faculty, teacher_id -> faculty_id
        monthly_data = transform_timetable_entries(monthly_data)
        
        if not monthly_data:
            print(f"[TIMETABLE-MONTH] No entries found for {month_label}")
            return jsonify({
                "error": "Month timetable not found", 
                "requested_month": month_label
            }), 404
        
        print(f"[TIMETABLE-MONTH] ✓ Successfully loaded {len(monthly_data)} entries for {month_label}")
        return jsonify(monthly_data), 200
    except Exception as e:
        print(f"[TIMETABLE-MONTH ERROR] Failed to load month {month_label}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Error loading timetable for month", "message": str(e)}), 500


@app.route('/faculty/<int:faculty_id>/holidays', methods=['GET', 'POST', 'DELETE'])
def faculty_holidays(faculty_id):
    """Manage per-faculty holidays stored in MongoDB
    GET: return list of dates
    POST: accept {"date":"YYYY-MM-DD"} or {"dates":[...]}
    DELETE: remove specific date via query ?date=YYYY-MM-DD or clear all if not provided
    """

    if request.method == 'GET':
        fac_hol = find_one(COLLECTIONS['faculty_holidays'], {'faculty_id': faculty_id})
        return jsonify(fac_hol.get('dates', []) if fac_hol else []), 200

    if request.method == 'POST':
        data = request.get_json() or {}
        dates = []
        if 'dates' in data and isinstance(data['dates'], list):
            dates = data['dates']
        elif 'date' in data:
            dates = [data['date']]
        if not dates:
            return jsonify({"message": "no dates provided"}), 400

        # Load public holidays from MongoDB
        holidays_data = load_collection_as_list(COLLECTIONS['holidays'])
        public_holiday_dates = {h.get('date') for h in holidays_data if h.get('date')}

        # Validate each date
        invalid_dates = []
        for date_str in dates:
            try:
                dt = datetime.fromisoformat(date_str)
                # Check if it's a public holiday
                if date_str in public_holiday_dates:
                    invalid_dates.append({
                        'date': date_str,
                        'reason': 'Already a public holiday'
                    })
                # Check if it's a weekend (Saturday=5, Sunday=6)
                elif dt.weekday() in [5, 6]:
                    invalid_dates.append({
                        'date': date_str,
                        'reason': 'Already a non-working day (weekend)'
                    })
            except ValueError:
                invalid_dates.append({
                    'date': date_str,
                    'reason': 'Invalid date format (use YYYY-MM-DD)'
                })

        # If there are invalid dates, return error
        if invalid_dates:
            return jsonify({
                "message": "Cannot book holidays for these dates",
                "invalid_dates": invalid_dates
            }), 400

        # Get existing dates or create new record
        fac_hol = find_one(COLLECTIONS['faculty_holidays'], {'faculty_id': faculty_id})
        if fac_hol:
            cur = set(fac_hol.get('dates', []))
            cur.update(dates)
            update_one(COLLECTIONS['faculty_holidays'],
                      {'faculty_id': faculty_id},
                      {'$set': {'dates': sorted(list(cur))}})
        else:
            insert_one(COLLECTIONS['faculty_holidays'], {
                'faculty_id': faculty_id,
                'dates': sorted(dates)
            })
        
        # 🔄 AUTO-ADJUST TIMETABLE FOR EACH HOLIDAY DATE
        adjustment_results = []
        for date_str in dates:
            result = adjust_timetable_for_date_and_faculty(date_str, faculty_id)
            if result['adjustments'] > 0:
                adjustment_results.extend(result['log'])
        
        response = {
            "message": "Holiday(s) booked successfully",
            "dates": sorted(dates),
            "timetable_adjustments": {
                "count": len(adjustment_results),
                "details": adjustment_results
            }
        }
        return jsonify(response), 200

    if request.method == 'DELETE':
        query_date = request.args.get('date')
        
        if query_date:
            # Remove specific date
            fac_hol = find_one(COLLECTIONS['faculty_holidays'], {'faculty_id': faculty_id})
            if fac_hol:
                dates = [d for d in fac_hol.get('dates', []) if d != query_date]
                if dates:
                    update_one(COLLECTIONS['faculty_holidays'],
                              {'faculty_id': faculty_id},
                              {'$set': {'dates': dates}})
                else:
                    delete_many(COLLECTIONS['faculty_holidays'], {'faculty_id': faculty_id})
            return jsonify({"message": f"Removed holiday: {query_date}"}), 200
        else:
            # Clear all holidays
            delete_many(COLLECTIONS['faculty_holidays'], {'faculty_id': faculty_id})
            return jsonify({"message": "All holidays cleared"}), 200

# ===== TIMETABLE CHECK ENDPOINT =====
@app.route('/check-timetable-exists', methods=['GET'])
def check_timetable_exists():
    """Check if a timetable already exists for the given month/year."""
    try:
        month = request.args.get('month', type=int)
        year = request.args.get('year', type=int)
        
        if not month or not year:
            return jsonify({"error": "Missing month or year parameter"}), 400
        
        exists = timetable_exists_for_month(month, year)
        print(f"[CHECK-TIMETABLE] Month: {month}, Year: {year}, Exists: {exists}")
        
        return jsonify({
            "exists": exists,
            "month": month,
            "year": year,
            "message": f"Timetable {'already exists' if exists else 'does not exist'} for {month}/{year}"
        }), 200
    except Exception as e:
        print(f"[CHECK-TIMETABLE ERROR] {str(e)}")
        return jsonify({"error": str(e)}), 500

# ===== TIMETABLE GENERATION ENDPOINTS =====
@app.route('/generate-timetable', methods=['POST'])
def generate_timetable():
    try:
        # Get parameters from request
        data = request.get_json()
        print(f"[GENERATE-TIMETABLE] Received data: {data}")
        
        month = int(data.get('month', 2))
        year = int(data.get('year', 2026))
        holidays_input = data.get('holidays', [])
        save = data.get('save', False)
        overwrite = data.get('overwrite', False)  # Flag to force regeneration
        
        print(f"[GENERATE-TIMETABLE] Month: {month} (type: {type(month)}), Year: {year} (type: {type(year)}), Holidays: {len(holidays_input)}, Overwrite: {overwrite}")
        
        # Check if timetable already exists for this month
        if not overwrite and timetable_exists_for_month(month, year):
            print(f"[GENERATE-TIMETABLE] Timetable already exists for {month}/{year}. Use overwrite=true to regenerate.")
            return jsonify({
                "message": "Timetable already exists for this month",
                "exists": True,
                "month": month,
                "year": year,
                "error": "Timetable already generated. Please use Update option to regenerate."
            }), 409  # 409 Conflict
        
        # Format: [{date: 'YYYY-MM-DD', name: 'Holiday Name'}, ...]
        # Or legacy: ['YYYY-MM-DD', 'YYYY-MM-DD-Holiday Name', ...]
        
        # Parse holidays - handle both formats
        holiday_dates = []
        holiday_names = {}
        
        for holiday in holidays_input:
            if isinstance(holiday, dict):
                # New format with date and name
                holiday_date = holiday.get('date', '')
                holiday_name = holiday.get('name', '')
            else:
                # Legacy string format
                holiday_date = holiday
                holiday_name = ''
            
            if holiday_date:
                holiday_dates.append(holiday_date)
                if holiday_name:
                    holiday_names[holiday_date] = holiday_name
        
        print(f"[GENERATE-TIMETABLE] Holiday dates: {holiday_dates}")
        print(f"[GENERATE-TIMETABLE] Holiday names: {holiday_names}")
        
        # Load data from MongoDB when available, otherwise fall back to JSON files
        if not USING_JSON:
            faculty_list = load_collection_as_list(COLLECTIONS['faculty'])
            subjects = load_collection_as_list(COLLECTIONS['subjects'])
            try:
                classrooms = load_collection_as_list(COLLECTIONS.get('classrooms', 'classrooms'))
            except Exception:
                classrooms = load_json('classrooms.json')
        else:
            faculty_list = load_json('faculty.json')
            subjects = load_json('subjects.json')
            classrooms = load_json('classrooms.json')
        
        if not faculty_list or not subjects:
            return jsonify({"message": "Failed to generate timetable", "error": "Missing faculty or subjects data"}), 400




        # Prepare data for TimetableManager
        # faculty.json format: {id, name, subject: 'Physics', email, classes: ['6','7'], ...}
        # Convert to TimetableManager format: {id, name, subjects: [list], classes: [list], ...}
        teachers = [
            {
                "id": f["id"],
                "name": f["name"],
                "subjects": [f["subject"]] if f.get("subject") else [],  # Convert single subject to list
                "classes": f.get("classes", []),  # Classes this faculty is assigned to
                "max_daily": f.get("max_daily", 5),
                "max_weekly": f.get("max_weekly", 30)
            }
            for f in faculty_list
        ]

        # Build subjects_per_class from subjects data
        # subjects.json format: [{id: 1, name: 'Physics', classes: ['6', '7', '8']}, ...]
        subjects_per_class = {}
        for subject in subjects:
            subject_name = subject.get('name', '')
            for class_id in subject.get('classes', []):
                if class_id not in subjects_per_class:
                    subjects_per_class[class_id] = []
                subjects_per_class[class_id].append(subject_name)
        
        classes = list(subjects_per_class.keys())

        # Also include classes defined in `classes` collection (e.g., Class 6..10)
        try:
            db_classes = load_collection_as_list(COLLECTIONS.get('classes', 'classes'))
        except Exception:
            db_classes = []

        for c in db_classes:
            # Prefer numeric id, then name/label
            cid = c.get('id') if c.get('id') is not None else (c.get('name') or c.get('label'))
            if cid is None:
                continue
            cid_str = str(cid)
            if cid_str not in classes:
                classes.append(cid_str)
            # Ensure subjects_per_class has an entry for this class (may be empty)
            if cid_str not in subjects_per_class:
                subjects_per_class[cid_str] = []

        # Fallback: if any class has no subjects, try to copy subjects from nearest numeric class
        def fill_subjects_from_nearest(subjects_map):
            keys = list(subjects_map.keys())
            # collect numeric keys that have subjects
            numeric_with_subjects = [int(k) for k in keys if k.isdigit() and subjects_map.get(k)]
            if not numeric_with_subjects:
                return
            for k in keys:
                if subjects_map.get(k):
                    continue
                # try numeric fallback
                try:
                    kn = int(k)
                except Exception:
                    continue
                # search nearest
                nearest = None
                bestd = None
                for n in numeric_with_subjects:
                    d = abs(n - kn)
                    if bestd is None or d < bestd:
                        bestd = d
                        nearest = n
                if nearest is not None:
                    subjects_map[k] = list(subjects_map.get(str(nearest), []))

        fill_subjects_from_nearest(subjects_per_class)

        # Initialize TimetableManager and generate
        print("[GENERATE-TIMETABLE] Initializing TimetableManager...")
        # Normalize subjects_per_class keys/values to lowercase for manager input
        subjects_per_class_norm = {str(k): [ (s or '').strip().lower() for s in v ] for k,v in subjects_per_class.items()}
        teachers_norm = []
        for t in teachers:
            subs = t.get('subjects', [])
            subs_norm = [(s or '').strip().lower() for s in subs]
            # Normalize classes to strings
            assigned_classes = t.get('classes', [])
            classes_norm = [str(c) for c in assigned_classes] if assigned_classes else []
            tcopy = t.copy()
            tcopy['subjects'] = subs_norm
            tcopy['classes'] = classes_norm
            teachers_norm.append(tcopy)

        mgr = TimetableManager(teachers_norm, classes, subjects_per_class_norm)
        print(f"[GENERATE-TIMETABLE] Generating timetable for month {month}, year {year}...")
        timetable = mgr.generate_month(month, year)
        print(f"[GENERATE-TIMETABLE] Generated {len(timetable)} timetable entries")

        # Create set of holiday dates for quick lookup
        holiday_date_set = set(holiday_dates)
        print(f"[GENERATE-TIMETABLE] Holiday date set: {holiday_date_set}")

        # Filter out classes scheduled on holiday dates AND lunch (12:00-13:00)
        print("[GENERATE-TIMETABLE] Filtering out classes on holiday dates and lunch hours (12:00-13:00)...")
        import re
        def parse_time_range_to_minutes(ts):
            """Return (start_min, end_min) from a time string. If unable, return (None, None)."""
            if not ts:
                return (None, None)
            s = str(ts).strip()
            # HH:MM - HH:MM
            m = re.match(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$", s)
            if m:
                start = int(m.group(1)) * 60 + int(m.group(2))
                end = int(m.group(3)) * 60 + int(m.group(4))
                return (start, end)
            # H - H  (e.g., 12-1)
            m = re.match(r"^(\d{1,2})\s*-\s*(\d{1,2})$", s)
            if m:
                start = int(m.group(1)) * 60
                end = int(m.group(2)) * 60
                # if end <= start, assume end is next hour
                if end <= start:
                    end = start + 60
                return (start, end)
            # HH:MM single
            m = re.match(r"^(\d{1,2}):(\d{2})$", s)
            if m:
                start = int(m.group(1)) * 60 + int(m.group(2))
                return (start, start + 60)
            # single hour like '12' or '12pm'
            m = re.match(r"^(\d{1,2})\b", s)
            if m:
                start = int(m.group(1)) * 60
                return (start, start + 60)
            return (None, None)

        LUNCH_START = 12 * 60
        LUNCH_END = 13 * 60

        timetable_filtered = []
        removed_holiday = 0
        removed_lunch = 0
        for entry in timetable:
            entry_date = entry.get('date', '')
            if entry_date in holiday_date_set:
                removed_holiday += 1
                continue

            time_str = entry.get('time') or entry.get('slot') or entry.get('start') or ''
            start_min, end_min = parse_time_range_to_minutes(time_str)
            if start_min is None:
                # fallback: if string contains '12' assume lunch and skip
                if re.search(r"\b12\b", str(time_str)):
                    removed_lunch += 1
                    continue
                # unknown format - keep the entry
                timetable_filtered.append(entry)
            else:
                # skip if overlaps lunch window
                if not (start_min < LUNCH_END and end_min > LUNCH_START):
                    timetable_filtered.append(entry)
                else:
                    removed_lunch += 1

        print(f"[GENERATE-TIMETABLE] Removed {removed_holiday} classes on {len(holiday_date_set)} holiday dates")
        print(f"[GENERATE-TIMETABLE] Removed {removed_lunch} classes overlapping lunch (12:00-13:00)")
        print(f"[GENERATE-TIMETABLE] Final count: {len(timetable_filtered)} entries")

        # Add holiday name to any remaining entries on non-holiday dates for reference
        for entry in timetable_filtered:
            entry_date = entry.get('date', '')
            if entry_date in holiday_names:
                entry['holiday_name'] = holiday_names[entry_date]

        # Save timetable to MongoDB if required
        if save:
            try:
                # Validate generated timetable: check unassigned slots
                unassigned_count = len(getattr(mgr, 'unassigned_slots', []))
                print(f"[GENERATE-TIMETABLE] Unassigned slots found: {unassigned_count}")
                force_save = bool(data.get('force_save', False))
                if unassigned_count > 0 and not force_save:
                    print("[GENERATE-TIMETABLE] Aborting save due to unassigned slots (use force_save=true to override)")
                    return jsonify({
                        "message": "Timetable generated but has unassigned slots. Save aborted.",
                        "unassigned_count": unassigned_count,
                        "sample_unassigned": mgr.unassigned_slots[:20]
                    }), 409

                print("[GENERATE-TIMETABLE] Saving to MongoDB...")
                # Pass month/year so only this month's data is replaced, not all months
                save_timetable_entries(timetable_filtered, month=month, year=year)
                print(f"[GENERATE-TIMETABLE] Saved {len(timetable_filtered)} entries to MongoDB")
                # --- Compute and persist monthly workload into DB ---
                try:
                    coll_name = COLLECTIONS.get('workload', 'workload')
                    # Build workload per faculty for this month/year
                    workload_map = {}
                    for e in timetable_filtered:
                        fid = None
                        if e.get('faculty_id') is not None:
                            fid = e.get('faculty_id')
                        elif e.get('teacher_id') is not None:
                            fid = e.get('teacher_id')
                        # normalize to int when possible
                        try:
                            fid = int(fid) if fid is not None else None
                        except Exception:
                            pass
                        if fid is None:
                            continue
                        entry = workload_map.setdefault(fid, {'faculty_id': fid, 'hours': 0, 'classes': set()})
                        entry['hours'] += 1
                        cls = e.get('class') or e.get('class_name') or e.get('classroom')
                        if cls:
                            entry['classes'].add(cls)

                    # remove any existing workload docs for this month/year and insert fresh ones
                    delete_many(coll_name, {'month': month, 'year': year})
                    docs = []
                    for fid, v in workload_map.items():
                        docs.append({
                            'faculty_id': v['faculty_id'],
                            'month': month,
                            'year': year,
                            'hours': v['hours'],
                            'classes': list(v['classes']),
                            'created_at': datetime.now().isoformat()
                        })
                    if docs:
                        insert_many(coll_name, docs)
                        print(f"[GENERATE-TIMETABLE] Workload collection '{coll_name}' updated for {month}/{year} with {len(docs)} records")
                    else:
                        print(f"[GENERATE-TIMETABLE] No workload records to insert for {month}/{year}")
                except Exception as werr:
                    print(f"[GENERATE-TIMETABLE] Warning: failed to update workload collection: {str(werr)}")
            except Exception as save_error:
                print(f"[GENERATE-TIMETABLE] Error saving timetable: {str(save_error)}")
                import traceback
                print(f"[GENERATE-TIMETABLE] Save trace: {traceback.format_exc()}")
                raise save_error
            
            # Also save holidays to holiday collection if they have names
            if holiday_names:
                for holiday_date, holiday_name in holiday_names.items():
                    try:
                        existing = find_one(COLLECTIONS['holidays'], {'date': holiday_date})
                        if not existing:
                            insert_one(COLLECTIONS['holidays'], {'date': holiday_date, 'name': holiday_name})
                            print(f"[GENERATE-TIMETABLE] Added holiday: {holiday_date} - {holiday_name}")
                    except Exception as e:
                        print(f"[GENERATE-TIMETABLE] Warning: Could not save holiday {holiday_date}: {str(e)}")

        # Remove ObjectId fields before returning response
        response_data = remove_objectid_fields(timetable_filtered)
        
        # Transform field names: teacher_name -> faculty, teacher_id -> faculty_id
        response_data = transform_timetable_entries(response_data)
        
        return jsonify({
            "message": "Timetable generated successfully",
            "count": len(response_data),
            "data": response_data,
            "holidays": holidays_input
        }), 200

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[GENERATE-TIMETABLE ERROR] {str(e)}")
        print(f"[GENERATE-TIMETABLE TRACE] {error_trace}")
        return jsonify({"message": "Failed to generate timetable", "error": str(e)}), 500


@app.route('/generate-timetable-optimized', methods=['POST'])
def generate_timetable_optimized():
    """Generate timetable using optimized scheduler (min-cost flow) and save to MongoDB if requested.
    Expects JSON: { month, year, holidays:[...], save:bool, overwrite:bool, allow_cross_training:bool }
    Uses MongoDB only for faculty, subjects, classrooms, and faculty_holidays.
    """
    try:
        data = request.get_json() or {}
        month = int(data.get('month', 2))
        year = int(data.get('year', 2026))
        holidays_input = data.get('holidays', [])
        save = bool(data.get('save', False))
        overwrite = bool(data.get('overwrite', False))
        allow_cross_training = bool(data.get('allow_cross_training', False))

        # check existing
        if not overwrite and timetable_exists_for_month(month, year):
            return jsonify({
                'message': 'Timetable already exists for this month',
                'exists': True,
                'month': month,
                'year': year
            }), 409

        # load data from MongoDB (DB-only)
        faculty_list = load_collection_as_list(COLLECTIONS['faculty'])
        subjects_list = load_collection_as_list(COLLECTIONS['subjects'])
        classrooms = load_collection_as_list(COLLECTIONS.get('classrooms', 'classrooms'))

        if not faculty_list or not subjects_list:
            return jsonify({'message': 'Missing faculty or subjects data'}), 400

        # build teachers input for manager
        teachers = []
        # fetch faculty holidays mapping
        fac_hol_list = load_collection_as_list(COLLECTIONS.get('faculty_holidays', 'faculty_holidays'))
        fac_hol_map = {fh.get('faculty_id'): fh.get('dates', []) for fh in fac_hol_list}

        for f in faculty_list:
            subj_field = f.get('subject')
            if isinstance(subj_field, str) and subj_field.strip():
                subs = [s.strip().lower() for s in subj_field.split(',') if s.strip()]
            else:
                subs = [s.lower() for s in (f.get('subjects') or [])]
            teachers.append({
                'id': int(f.get('id')),
                'name': f.get('name'),
                'subjects': subs,
                'max_daily': f.get('max_daily', 5),
                'max_weekly': f.get('max_weekly', 30),
                'holidays': fac_hol_map.get(f.get('id'), [])
            })

        # Build subjects_per_class from subjects list
        subjects_per_class = {}
        for subject in subjects_list:
            subject_name = subject.get('name', '')
            for class_id in subject.get('classes', []):
                if class_id not in subjects_per_class:
                    subjects_per_class[class_id] = []
                subjects_per_class[class_id].append(subject_name)

        classes = list(subjects_per_class.keys())

        # Also include classes defined in `classes` collection (e.g., Class 6..10)
        try:
            db_classes = load_collection_as_list(COLLECTIONS.get('classes', 'classes'))
        except Exception:
            db_classes = []

        for c in db_classes:
            cid = c.get('id') if c.get('id') is not None else (c.get('name') or c.get('label'))
            if cid is None:
                continue
            cid_str = str(cid)
            if cid_str not in classes:
                classes.append(cid_str)
            if cid_str not in subjects_per_class:
                subjects_per_class[cid_str] = []

        # build subjects_per_class mapping from subjects_list
        subjects_per_class = {}
        classes_set = set()
        for s in subjects_list:
            name = (s.get('name') or '').lower()
            classes = s.get('classes', [])
            for c in classes:
                classes_set.add(str(c))
                subjects_per_class.setdefault(str(c), []).append(name)

        classes = sorted(list(classes_set))

        # Ensure DB classes are included after rebuild and add empty subject lists
        try:
            db_classes = db_classes if 'db_classes' in locals() else load_collection_as_list(COLLECTIONS.get('classes', 'classes'))
        except Exception:
            db_classes = []

        for c in db_classes:
            cid = c.get('id') if c.get('id') is not None else (c.get('name') or c.get('label'))
            if cid is None:
                continue
            cid_str = str(cid)
            if cid_str not in classes:
                classes.append(cid_str)
            if cid_str not in subjects_per_class:
                subjects_per_class[cid_str] = []

        # Fallback: fill empty class subject lists by copying from nearest numeric class
        def fill_subjects_from_nearest_opt(subjects_map):
            keys = list(subjects_map.keys())
            numeric_with_subjects = [int(k) for k in keys if k.isdigit() and subjects_map.get(k)]
            if not numeric_with_subjects:
                return
            for k in keys:
                if subjects_map.get(k):
                    continue
                try:
                    kn = int(k)
                except Exception:
                    continue
                nearest = None
                bestd = None
                for n in numeric_with_subjects:
                    d = abs(n - kn)
                    if bestd is None or d < bestd:
                        bestd = d
                        nearest = n
                if nearest is not None:
                    subjects_map[k] = list(subjects_map.get(str(nearest), []))

        fill_subjects_from_nearest_opt(subjects_per_class)

        # instantiate manager
        mgr = TimetableManager(teachers, classes, subjects_per_class)

        # parse holidays_input into list of date strings
        parsed_holidays = []
        for h in holidays_input:
            if isinstance(h, dict) and h.get('date'):
                parsed_holidays.append(h.get('date'))
            elif isinstance(h, str):
                parsed_holidays.append(h)

        # run optimized generator (dry-run)
        generated = mgr.generate_month_optimized(month, year, holidays=parsed_holidays, allow_cross_training=allow_cross_training)

        result = {
            'generated_count': len(generated),
            'unassigned_slots': len(mgr.unassigned_slots),
            'shortage_by_subject': dict(mgr.subject_shortage),
        }

        if save:
            # save to MongoDB (this will replace month entries)
            from db import save_timetable_entries as db_save
            success = db_save(generated, month=month, year=year)
            result['saved'] = bool(success)

        return jsonify(result), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ===== WORKLOAD REPORT ENDPOINTS =====
@app.route('/workload-report', methods=['GET'])
def workload_report():
    faculty_data = load_collection_as_list(COLLECTIONS['faculty'])
    timetable_data = get_timetable_flat()
    timetable_data = remove_objectid_fields(timetable_data)
    
    report = []
    for faculty in faculty_data:
        faculty_id = faculty.get('id')
        faculty_hours = len([t for t in timetable_data if t.get('faculty_id') == faculty_id])
        
        report.append({
            'id': faculty_id,
            'name': faculty.get('name'),
            'subject': faculty.get('subject'),
            'hours': faculty_hours
        })
    
    return jsonify(report)

# ===== MONTH-WISE WORKLOAD ENDPOINTS =====
@app.route('/workload-months', methods=['GET'])
def workload_months():
    """Get list of available months with workload data"""
    try:
        timetable_data = get_timetable_flat()
        timetable_data = remove_objectid_fields(timetable_data)
        
        available_months = {}
        for entry in timetable_data:
            date_str = entry.get('date')
            if date_str:
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    month_label = dt.strftime("%B %Y")
                    
                    if month_label not in available_months:
                        available_months[month_label] = {'entries': 0}
                    available_months[month_label]['entries'] += 1
                except (ValueError, TypeError):
                    continue
        
        # Sort and return (most recent first)
        sorted_months = sorted(list(available_months.keys()), reverse=True)
        result = [
            {
                'month': m,
                'total_entries': available_months[m]['entries']
            }
            for m in sorted_months
        ]
        
        print(f"[WORKLOAD MONTHS] Returning {len(result)} months with workload data")
        return jsonify(result), 200
    except Exception as e:
        print(f"[WORKLOAD MONTHS ERROR] {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/faculty-workload-month/<path:month_label>', methods=['GET'])
def faculty_workload_month(month_label):
    """Get workload for all faculty in a specific month"""
    try:
        print(f"\n[FACULTY-WORKLOAD-MONTH] Requested: {month_label}")
        
        # Parse month_label: "February 2026"
        try:
            dt = datetime.strptime(month_label, "%B %Y")
            month = dt.month
            year = dt.year
            print(f"[FACULTY-WORKLOAD-MONTH] Parsed as month={month}, year={year}")
        except ValueError:
            return jsonify({"error": f"Invalid month format. Use 'Month Year' (e.g., 'February 2026')"}), 400
        
        # Get timetable data for this month
        timetable_data = get_timetable_flat()
        timetable_data = remove_objectid_fields(timetable_data)
        
        # Filter entries for the requested month/year
        monthly_timetable = []
        for entry in timetable_data:
            date_str = entry.get('date')
            if date_str:
                try:
                    entry_dt = datetime.strptime(date_str, "%Y-%m-%d")
                    if entry_dt.month == month and entry_dt.year == year:
                        monthly_timetable.append(entry)
                except (ValueError, TypeError):
                    continue

        # Normalize fields and ids for accurate matching
        monthly_timetable = transform_timetable_entries(monthly_timetable)
        
        # Load holidays once (public and per-faculty)
        public_holidays = {h.get('date') for h in load_collection_as_list(COLLECTIONS.get('holidays', 'holidays')) if h.get('date')}
        fac_hol_list = load_collection_as_list(COLLECTIONS.get('faculty_holidays', 'faculty_holidays'))
        fac_hol_map = {fh.get('faculty_id'): set(fh.get('dates', [])) for fh in fac_hol_list}

        # Get faculty data
        faculty_data = load_collection_as_list(COLLECTIONS['faculty'])
        faculty_data = remove_objectid_fields(faculty_data)
        
        # Calculate workload per faculty for this month
        workload_list = []
        for faculty in faculty_data:
            faculty_id = faculty.get('id')
            try:
                fid_norm = int(faculty_id) if faculty_id is not None else None
            except Exception:
                fid_norm = faculty_id

            faculty_hours = 0
            subjects_taught = set()
            for entry in monthly_timetable:
                try:
                    tfid = entry.get('faculty_id')
                    tfid_norm = int(tfid) if tfid is not None else None
                except Exception:
                    tfid_norm = entry.get('faculty_id')
                if tfid_norm == fid_norm:
                    # Exclude if the date is a public holiday or this faculty's holiday
                    date_str = entry.get('date')
                    if date_str and (date_str in public_holidays or date_str in fac_hol_map.get(fid_norm, set())):
                        continue
                    faculty_hours += 1
                    subjects_taught.add(entry.get('subject'))
            
            workload_list.append({
                'id': faculty_id,
                'name': faculty.get('name'),
                'email': faculty.get('email'),
                'subject': faculty.get('subject'),
                'hours': faculty_hours,
                'classes': faculty_hours,
                'subjects_taught': list(subjects_taught) if subjects_taught else [],
                'month': month_label
            })
        
        print(f"[FACULTY-WORKLOAD-MONTH] ✓ Loaded workload for {len(workload_list)} faculty in {month_label}")
        return jsonify(workload_list), 200
    except Exception as e:
        print(f"[FACULTY-WORKLOAD-MONTH ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/faculty/<int:faculty_id>/workload-by-month', methods=['GET'])
def faculty_workload_by_month(faculty_id):
    """Get workload for a specific faculty broken down by month"""
    try:
        print(f"\n[FACULTY-WORKLOAD-BY-MONTH] Faculty ID: {faculty_id}")
        
        # Check if faculty exists
        faculty = find_one(COLLECTIONS['faculty'], {'id': faculty_id})
        if not faculty:
            return jsonify({"error": "Faculty not found"}), 404
        
        faculty = remove_objectid_fields(faculty)
        
        # Get timetable data for this faculty
        timetable_data = get_timetable_flat()
        timetable_data = remove_objectid_fields(timetable_data)
        
        faculty_entries = [t for t in timetable_data if t.get('faculty_id') == faculty_id]
        
        # Group by month
        monthly_workload = {}
        for entry in faculty_entries:
            date_str = entry.get('date')
            if date_str:
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    month_label = dt.strftime("%B %Y")
                    
                    if month_label not in monthly_workload:
                        monthly_workload[month_label] = {
                            'hours': 0,
                            'classes': [],
                            'subjects': set(),
                            'dates': set()
                        }
                    
                    monthly_workload[month_label]['hours'] += 1
                    monthly_workload[month_label]['classes'].append(entry.get('class'))
                    monthly_workload[month_label]['subjects'].add(entry.get('subject'))
                    monthly_workload[month_label]['dates'].add(date_str)
                except (ValueError, TypeError):
                    continue
        
        # Format response
        result = {
            'faculty_id': faculty_id,
            'faculty_name': faculty.get('name'),
            'faculty_email': faculty.get('email'),
            'faculty_subject': faculty.get('subject'),
            'total_hours': sum([v['hours'] for v in monthly_workload.values()]),
            'months': []
        }
        
        # Sort months and add to result
        for month_label in sorted(monthly_workload.keys(), reverse=True):
            data = monthly_workload[month_label]
            result['months'].append({
                'month': month_label,
                'hours': data['hours'],
                'classes': list(set(data['classes'])),
                'subjects': list(data['subjects']),
                'working_days': len(data['dates'])
            })
        
        print(f"[FACULTY-WORKLOAD-BY-MONTH] ✓ Loaded {len(result['months'])} months for faculty {faculty.get('name')}")
        return jsonify(result), 200
    except Exception as e:
        print(f"[FACULTY-WORKLOAD-BY-MONTH ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/workload-summary-by-month', methods=['GET'])
def workload_summary_by_month():
    """Get overall workload summary grouped by month"""
    try:
        print("[WORKLOAD-SUMMARY-BY-MONTH] Generating summary...")
        
        faculty_data = load_collection_as_list(COLLECTIONS['faculty'])
        faculty_data = remove_objectid_fields(faculty_data)
        
        timetable_data = get_timetable_flat()
        timetable_data = remove_objectid_fields(timetable_data)
        
        # Group by month
        monthly_summary = {}
        for entry in timetable_data:
            date_str = entry.get('date')
            if date_str:
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    month_label = dt.strftime("%B %Y")
                    
                    if month_label not in monthly_summary:
                        monthly_summary[month_label] = {
                            'total_classes': 0,
                            'assigned_classes': 0,
                            'unassigned_classes': 0,
                            'faculty_count': 0,
                            'subjects': set(),
                            'faculty_workload': {}
                        }
                    
                    monthly_summary[month_label]['total_classes'] += 1
                    
                    if entry.get('faculty_id'):
                        monthly_summary[month_label]['assigned_classes'] += 1
                        fac_id = entry.get('faculty_id')
                        if fac_id not in monthly_summary[month_label]['faculty_workload']:
                            monthly_summary[month_label]['faculty_workload'][fac_id] = 0
                        monthly_summary[month_label]['faculty_workload'][fac_id] += 1
                    else:
                        monthly_summary[month_label]['unassigned_classes'] += 1
                    
                    monthly_summary[month_label]['subjects'].add(entry.get('subject'))
                except (ValueError, TypeError):
                    continue
        
        # Calculate faculty count per month (distinct faculty with assignments)
        for month_label in monthly_summary:
            monthly_summary[month_label]['faculty_count'] = len(
                [f for f in faculty_data if any(
                    t.get('faculty_id') == f.get('id') and 
                    datetime.strptime(t.get('date'), "%Y-%m-%d").strftime("%B %Y") == month_label
                    for t in timetable_data if t.get('date')
                )]
            )
        
        # Format response
        result = []
        for month_label in sorted(monthly_summary.keys(), reverse=True):
            data = monthly_summary[month_label]
            workload_dist = data['faculty_workload']
            hours_list = list(workload_dist.values()) if workload_dist else [0]
            
            result.append({
                'month': month_label,
                'total_classes': data['total_classes'],
                'assigned_classes': data['assigned_classes'],
                'unassigned_classes': data['unassigned_classes'],
                'assignment_rate': round(100 * data['assigned_classes'] / max(1, data['total_classes']), 2),
                'faculty_active': data['faculty_count'],
                'subjects_count': len(data['subjects']),
                'avg_workload_per_faculty': round(sum(hours_list) / max(1, len(hours_list)), 2),
                'max_workload': max(hours_list) if hours_list else 0,
                'min_workload': min(hours_list) if hours_list else 0
            })
        
        print(f"[WORKLOAD-SUMMARY-BY-MONTH] ✓ Generated summary for {len(result)} months")
        return jsonify(result), 200
    except Exception as e:
        print(f"[WORKLOAD-SUMMARY-BY-MONTH ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ===== CLASSES MANAGEMENT ENDPOINTS =====
@app.route('/classes', methods=['GET', 'POST'])
def classes_management():
    if request.method == 'GET':
        classes_data = load_collection_as_list(COLLECTIONS['classes'])
        return jsonify(remove_objectid_fields(classes_data))
    elif request.method == 'POST':
        try:
            data = request.get_json()
            classes_data = load_collection_as_list(COLLECTIONS['classes'])
            data['id'] = max([c.get('id', 0) for c in classes_data], default=0) + 1
            insert_one(COLLECTIONS['classes'], data)
            return jsonify({"message": "Class added successfully", "data": data}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 400

@app.route('/classes/<int:class_id>', methods=['GET', 'DELETE'])
def class_detail(class_id):
    if request.method == 'GET':
        class_data = find_one(COLLECTIONS['classes'], {'id': class_id})
        if class_data:
            return jsonify(remove_objectid_fields(class_data))
        return jsonify({"error": "Class not found"}), 404
    elif request.method == 'DELETE':
        try:
            delete_many(COLLECTIONS['classes'], {'id': class_id})
            return jsonify({"message": "Class deleted successfully"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 400

# ===== SUBJECTS MANAGEMENT ENDPOINTS =====
@app.route('/subjects/<int:subject_id>', methods=['DELETE'])
def subject_delete(subject_id):
    try:
        delete_many(COLLECTIONS['subjects'], {'id': subject_id})
        return jsonify({"message": "Subject deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ===== TIME SLOTS MANAGEMENT ENDPOINTS =====
@app.route('/time-slots', methods=['GET', 'POST'])
def time_slots_management():
    if request.method == 'GET':
        slots_data = load_collection_as_list(COLLECTIONS['time_slots'])
        return jsonify(remove_objectid_fields(slots_data))
    elif request.method == 'POST':
        try:
            data = request.get_json()
            slots_data = load_collection_as_list(COLLECTIONS['time_slots'])
            data['id'] = max([s.get('id', 0) for s in slots_data], default=0) + 1
            insert_one(COLLECTIONS['time_slots'], data)
            return jsonify({"message": "Time slot added successfully", "data": data}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 400

@app.route('/time-slots/<int:slot_id>', methods=['GET', 'DELETE'])
def time_slot_detail(slot_id):
    if request.method == 'GET':
        slot_data = find_one(COLLECTIONS['time_slots'], {'id': slot_id})
        if slot_data:
            return jsonify(remove_objectid_fields(slot_data))
        return jsonify({"error": "Time slot not found"}), 404
    elif request.method == 'DELETE':
        try:
            delete_many(COLLECTIONS['time_slots'], {'id': slot_id})
            return jsonify({"message": "Time slot deleted successfully"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 400

# ===== ADMIN LEAVES ENDPOINT =====
@app.route('/admin/leaves', methods=['GET'])
def admin_leaves():
    try:
        print("[ADMIN/LEAVES] Fetching all leaves...")
        leaves_data = find_many(COLLECTIONS['leaves'])
        print(f"[ADMIN/LEAVES] Found {len(leaves_data) if leaves_data else 0} leaves")
        
        # Ensure leaves_data is a list
        if leaves_data is None:
            leaves_data = []
        elif not isinstance(leaves_data, list):
            leaves_data = list(leaves_data)
        
        # Format each leave properly
        formatted_leaves = format_leaves_for_response(leaves_data)
        print(f"[ADMIN/LEAVES] Formatted {len(formatted_leaves)} leaves for response")
        
        # Log first leave for debugging
        if formatted_leaves and len(formatted_leaves) > 0:
            print(f"[ADMIN/LEAVES] First leave ID: {formatted_leaves[0].get('id')}")
        
        return jsonify(formatted_leaves), 200
    except Exception as e:
        print(f"[ADMIN/LEAVES ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ===== SYSTEM SETTINGS ENDPOINTS =====
@app.route('/system-settings', methods=['GET', 'POST'])
def system_settings():
    if request.method == 'GET':
        try:
            settings = find_one(COLLECTIONS['system_settings'], {})
            if settings:
                return jsonify(remove_objectid_fields(settings)), 200
            return jsonify({"academicYear": "2025-2026", "semester": "1", "leavePolicyDays": "20", "maxClassesPerDay": "5"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    elif request.method == 'POST':
        try:
            data = request.get_json()
            # Clear existing settings and insert new ones
            clear_collection(COLLECTIONS['system_settings'])
            insert_one(COLLECTIONS['system_settings'], data)
            return jsonify({"message": "Settings saved successfully", "data": data}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True, port=5000)
