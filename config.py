"""
MongoDB Configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()

# MongoDB Connection String
# Local: mongodb://localhost:27017/timetable_management
# Cloud (MongoDB Atlas): mongodb+srv://username:password@cluster.mongodb.net/timetable_management
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/timetable_management')
MONGODB_DB_NAME = 'timetable_management'

# Collections
COLLECTIONS = {
    'users': 'users',
    'faculty': 'faculty',
    'students': 'students',
    'subjects': 'subjects',
    'classes': 'classes',
    'time_slots': 'time_slots',
    'timetables': 'timetables',
    'leaves': 'leaves',
    'holidays': 'holidays',
    'faculty_holidays': 'faculty_holidays',
    'system_settings': 'system_settings'
}

print(f"[CONFIG] MongoDB URI: {MONGODB_URI}")
print(f"[CONFIG] Database: {MONGODB_DB_NAME}")
