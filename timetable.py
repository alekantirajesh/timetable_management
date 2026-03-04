from backend.db import load_collection_as_list

faculty_list = load_collection_as_list('faculty')

class Faculty:
    def __init__(self, id, name, subjects, max_daily, max_weekly, working_days, available_slots, leaves):
        self.id = id
        self.name = name
        self.subjects = subjects
        self.max_daily = max_daily
        self.max_weekly = max_weekly
        self.working_days = working_days
        self.available_slots = available_slots
        self.leaves = leaves

for f in faculty_list:
    dept = f.get("department", "general").strip().lower()
    # Process the department information as needed