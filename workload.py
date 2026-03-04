try:
    # Prefer MongoDB collection loader when available
    from backend.db import load_collection_as_list
    db_available = True
except Exception:
    from backend.utils.json_handler import load, save
    load_collection_as_list = None
    db_available = False


def allocate():
    """Allocate subjects to faculty.

    Uses MongoDB `faculty` and `subjects` collections when available,
    otherwise falls back to local JSON files in `data/`.
    """
    if db_available and load_collection_as_list:
        faculty = load_collection_as_list('faculty')
        subjects = load_collection_as_list('subjects')
    else:
        faculty = load('data/faculty.json')
        subjects = load('data/subjects.json')

    # Ensure allocation fields exist
    for f in faculty:
        if 'allocated' not in f:
            f['allocated'] = 0

    for sub in subjects:
        hours = sub.get('hoursPerWeek', 0)
        # try to find a faculty who can take this subject
        for f in faculty:
            max_hours = f.get('maxHours', f.get('max_weekly', 30))
            if f.get('allocated', 0) + hours * 4 <= max_hours:
                sub['faculty'] = f.get('id')
                f['allocated'] = f.get('allocated', 0) + hours * 4
                break

    # Persist changes back to JSON files when not using DB. If DB is used,
    # this function currently does not write back to MongoDB (to avoid
    # accidental mutations) — consider implementing an update path if needed.
    if not db_available:
        save('data/faculty.json', faculty)
        save('data/subjects.json', subjects)
