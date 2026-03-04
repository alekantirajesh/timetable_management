"""
Timetable manager
- Generate month-long timetables with constraints
- Prevent same teacher assigned to multiple classes at same time
- Enforce daily and weekly hour limits per teacher
- Handle apply_leave with substitution and workload balancing

Usage:
  Provide `teachers` as list of dicts: {"id":1, "name":"Ravi", "subjects":["Math","Physics"], "max_daily":5, "max_weekly":30}
  Provide `classes` as list of class labels or integers
  Provide `subjects_per_class` as dict: {class_label: ["Math","Science",...]}

Call:
  mgr = TimetableManager(teachers, classes, subjects_per_class)
  tt = mgr.generate_month(month, year)
  mgr.apply_leave(teacher_id, date_str)
  mgr.save_json("data/timetable.generated.json")

This is a self-contained module; adapt integration as needed.
"""

from datetime import datetime, timedelta
import calendar
import random
import json
import os
from collections import defaultdict
import heapq

DEFAULT_PERIOD_TIMES = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00"]

class TimetableManager:
    def __init__(self, teachers, classes, subjects_per_class,
                 period_times=None, working_days=None,
                 default_max_daily=5, default_max_weekly=30,
                 room_prefix="Room ", required_hours=None,
                 games_alternate_days=False, games_start_parity=0,
                 games_room="Playground"):
        """
        teachers: list of dicts with keys: id, name, subjects (list), optional max_daily, max_weekly
        classes: list of class labels (e.g., [6,7,8]) or strings
        subjects_per_class: dict mapping class -> list of subjects
        working_days: list of weekday numbers allowed (0=Mon..6=Sun). Default Mon-Fri [0..4]
        """
        # Normalize subject names to lowercase for case-insensitive matching
        self.teachers = {t['id']: {
            'id': t['id'],
            'name': t.get('name'),
            'subjects': [s.lower() for s in list(t.get('subjects', []))],
            'max_daily': t.get('max_daily', default_max_daily),
            'max_weekly': t.get('max_weekly', default_max_weekly),
            'holidays': set(t.get('holidays', []))
        } for t in teachers}

        # helper maps
        self.teacher_ids = list(self.teachers.keys())

        self.classes = [str(c) for c in classes]
        self.subjects_per_class = {str(k): list(v) for k, v in subjects_per_class.items()}

        self.period_times = period_times or DEFAULT_PERIOD_TIMES
        self.periods_per_day = len(self.period_times)
        # include Saturday by default (0=Mon .. 6=Sun)
        self.working_days = working_days if working_days is not None else [0,1,2,3,4,5]
        self.room_prefix = room_prefix
        # required_hours: optional mapping: { 'class': { 'Subject': hours_required, ... }, ... }
        # used to decide whether to allot a Games period without breaking subject requirements
        self.required_hours = required_hours or {}
        # Games scheduling options
        self.games_alternate_days = games_alternate_days
        # parity for day selection: day.day % 2 == games_start_parity
        self.games_start_parity = games_start_parity
        self.games_room = games_room
        # store defaults
        self.default_max_daily = default_max_daily
        self.default_max_weekly = default_max_weekly

        # runtime state
        self.timetable = []  # list of entries
        # per-date, per-period assigned teacher ids set for conflict checking
        # key: (date_str, time) -> set of teacher_ids
        self.slot_busy = defaultdict(set)
        # CLASS-SUBJECT-TIME TRACKING: Prevent multiple subjects in same class/time slot
        # key: (date_str, time) -> {class: subject}
        self.class_busy = defaultdict(dict)
        # per-date teacher daily count: date_str -> {teacher_id: count}
        self.daily_count = defaultdict(lambda: defaultdict(int))
        # per-week teacher weekly count: week_key -> {teacher_id: count}
        self.weekly_count = defaultdict(lambda: defaultdict(int))
        
        # Track shortages and warnings
        self.unassigned_slots = []  # [(date, time, class, subject), ...]
        self.subject_shortage = {}  # {subject: count_of_unassigned}
        self.faculty_shortage_warnings = []  # ["Subject X needs Y more faculty", ...]

    def _week_key(self, dt: datetime):
        return (dt.isocalendar().year, dt.isocalendar().week)

    def find_teacher_for_subject(self, subject, date_str, time, cls=None):
        """Return teacher_id or None respecting availability and limits.
        
        Priority:
        1. Faculty assigned to this class AND teach this subject
        2. Primary candidates (single-subject teachers) 
        3. Fallback candidates (multi-subject teachers)
        """
        # candidate teachers who can teach subject
        # case-insensitive subject match
        subject_key = (subject or '').lower()
        
        # Split candidates by class assignment
        assigned_to_class = []  # Teachers assigned to this class
        primary_candidates = []
        fallback_candidates = []
        
        for tid, t in self.teachers.items():
            if subject_key in t['subjects']:
                # Check if teacher is assigned to this class
                if cls and cls in t.get('classes', []):
                    assigned_to_class.append(tid)
                elif len(t['subjects']) == 1:
                    primary_candidates.append(tid)
                else:
                    fallback_candidates.append(tid)
        
        # Priority order: assigned_to_class > primary > fallback
        candidates_list = [assigned_to_class, primary_candidates, fallback_candidates]
        
        for candidates in candidates_list:
            if not candidates:
                continue
                
            # sort candidates by current weekly load (ascending) for balancing
            random.shuffle(candidates)
            # compute week key
            dt = datetime.fromisoformat(date_str)
            wk = self._week_key(dt)

            def score(tid):
                return self.weekly_count[wk].get(tid, 0)

            candidates.sort(key=score)

            for tid in candidates:
                # skip if teacher has personal holiday on this date
                if date_str in self.teachers[tid].get('holidays', set()):
                    continue
                # not already busy in this timeslot
                if tid in self.slot_busy[(date_str, time)]:
                    continue
                # check daily
                if self.daily_count[date_str].get(tid, 0) >= self.teachers[tid]['max_daily']:
                    continue
                # check weekly
                if self.weekly_count[wk].get(tid, 0) >= self.teachers[tid]['max_weekly']:
                    continue
                return tid
        
        return None

    def _allocate_teacher(self, tid, date_str, time, cls=None, subject=None):
        """Allocate teacher for time slot. Also tracks class-subject assignment if provided."""
        self.slot_busy[(date_str, time)].add(tid)
        # Track class-subject assignment to prevent multiple subjects in same period
        if cls is not None and subject is not None:
            self.class_busy[(date_str, time)][cls] = subject
        self.daily_count[date_str][tid] += 1
        dt = datetime.fromisoformat(date_str)
        self.weekly_count[self._week_key(dt)][tid] += 1

    def is_class_available_for_subject(self, cls, subject, date_str, time):
        """Check if class can be assigned this subject at this time slot.
        Returns True if:
        - Class has no assignment at this time, OR
        - Class is already assigned the same subject at this time
        Returns False if:
        - Class is already assigned a different subject at this time
        """
        key = (date_str, time)
        if key in self.class_busy:
            if cls in self.class_busy[key]:
                assigned_subject = self.class_busy[key][cls]
                # Class can only take one subject per time slot
                if assigned_subject != subject:
                    return False  # Different subject already assigned
        return True  # Class is available OR already has same subject

    def _find_any_available_teacher(self, date_str, time):
        """Find ANY available teacher (cross-training/flexible assignment)"""
        dt = datetime.fromisoformat(date_str)
        wk = self._week_key(dt)
        
        # Try all teachers sorted by weekly load
        candidates = list(self.teachers.keys())
        candidates.sort(key=lambda tid: self.weekly_count[wk].get(tid, 0))
        
        for tid in candidates:
            # skip if teacher has personal holiday
            if date_str in self.teachers[tid].get('holidays', set()):
                continue
            # not already busy in this timeslot
            if tid in self.slot_busy[(date_str, time)]:
                continue
            # check daily
            if self.daily_count[date_str].get(tid, 0) >= self.teachers[tid]['max_daily']:
                continue
            # check weekly
            if self.weekly_count[wk].get(tid, 0) >= self.teachers[tid]['max_weekly']:
                continue
            return tid
        return None
    
    def get_shortage_report(self):
        """
        Return detailed report of faculty shortages.
        Returns dict with:
            - total_unassigned: count of unassigned slots
            - shortage_by_subject: {subject: unassigned_count}
            - unassigned_slots: list of unassigned slot details
            - warnings: list of warning messages
        """
        self.faculty_shortage_warnings = []
        
        # Calculate estimated faculty needed per subject
        if not self.subjects_per_class:
            return {
                'total_unassigned': len(self.unassigned_slots),
                'shortage_by_subject': dict(self.subject_shortage),
                'unassigned_slots': self.unassigned_slots,
                'warnings': self.faculty_shortage_warnings
            }
        
        for subject in self.subject_shortage:
            count = self.subject_shortage[subject]
            if count > 0:
                # Get faculty teaching this subject
                faculty_for_subject = [t for t in self.teachers.values() if subject in t['subjects']]
                faculty_count = len(faculty_for_subject)
                
                warning = f"⚠️  {subject}: {count} unassigned slots. Currently {faculty_count} faculty. Consider adding 1-2 more faculty for {subject}."
                self.faculty_shortage_warnings.append(warning)
        
        return {
            'total_unassigned': len(self.unassigned_slots),
            'shortage_by_subject': dict(self.subject_shortage),
            'unassigned_slots': self.unassigned_slots,
            'warnings': self.faculty_shortage_warnings
        }

    def generate_month(self, month, year, start_day=1, holidays=None, allow_cross_training=False):
        """
        Generate timetable for the given month/year.
        Returns list of entries.
        Each entry: {id, date, time, class, subject, teacher_id, teacher_name, room}
        
        Args:
            allow_cross_training: If True, allow teachers from other subjects to fill gaps
        
        ✅ CONSTRAINT CHECKS ENFORCED:
        - Faculty time conflict: No faculty teaches multiple classes at same time
        - Daily workload: Faculty max 5 hours/day
        - Weekly workload: Faculty max 30 hours/week
        - Class-subject uniqueness: Each class has max 1 subject per time slot
        - Leave coverage: Faculty on holiday not assigned
        """
        self.timetable = []
        self.slot_busy.clear()
        self.class_busy.clear()  # Clear class-subject tracking
        self.daily_count.clear()
        self.weekly_count.clear()
        self.unassigned_slots = []
        self.subject_shortage = defaultdict(int)
        self.faculty_shortage_warnings = []

        # build holidays set (ISO date strings)
        holidays_set = set()
        if holidays is None:
            # try to read data/holidays.json if present (accept list of strings or list of dicts with 'date')
            try:
                if os.path.exists('data/holidays.json'):
                    with open('data/holidays.json') as hf:
                        raw = json.load(hf)
                        if isinstance(raw, list):
                            for it in raw:
                                if isinstance(it, str):
                                    holidays_set.add(it)
                                elif isinstance(it, dict) and it.get('date'):
                                    holidays_set.add(it.get('date'))
            except Exception:
                holidays_set = set()
        else:
            for it in holidays:
                if isinstance(it, str):
                    holidays_set.add(it)
                elif isinstance(it, dict) and it.get('date'):
                    holidays_set.add(it.get('date'))

        # keep for other operations
        self.holidays = holidays_set

        entry_id = 1
        cal = calendar.Calendar()
        for day in cal.itermonthdates(year, month):
            if day.month != month:
                continue
            if day.weekday() not in self.working_days:
                continue
            date_str = day.isoformat()
            if date_str in holidays_set:
                # skip holiday dates - do not schedule or count hours
                continue
            # for each class, schedule periods
            for cls in self.classes:
                subjects = self.subjects_per_class.get(cls)
                if not subjects:
                    # skip if class has no subjects
                    continue
                # simple round-robin index per class per date to vary subjects
                start_idx = (day.day + hash(cls)) % len(subjects)
                for pidx, time in enumerate(self.period_times):
                    subject = subjects[(start_idx + pidx) % len(subjects)]
                    
                    # ✅ CHECK: Class cannot have multiple subjects at same time
                    if not self.is_class_available_for_subject(cls, subject, date_str, time):
                        # Class already has different subject at this time, skip
                        self.unassigned_slots.append((date_str, time, cls, subject))
                        self.subject_shortage[subject] += 1
                        continue
                    
                    # find teacher (with preference for faculty assigned to this class)
                    tid = self.find_teacher_for_subject(subject, date_str, time, cls=cls)
                    
                    # If no teacher found and cross-training enabled, try other teachers
                    if tid is None and allow_cross_training:
                        tid = self._find_any_available_teacher(date_str, time)
                    
                    if tid is None:
                        teacher_name = None
                        teacher_id = None
                        # Track unassigned slot
                        self.unassigned_slots.append((date_str, time, cls, subject))
                        self.subject_shortage[subject] += 1
                    else:
                        teacher_id = tid
                        teacher_name = self.teachers[tid]['name']
                        self._allocate_teacher(tid, date_str, time, cls=cls, subject=subject)

                    entry = {
                        'id': entry_id,
                        'date': date_str,
                        'time': time,
                        'class': cls,
                        'subject': subject,
                        'teacher_id': teacher_id,
                        'teacher_name': teacher_name,
                        'room': f"{self.room_prefix}{100 + int(cls) if cls.isdigit() else 0}"
                    }
                    self.timetable.append(entry)
                    entry_id += 1
        # After initial generation, optionally convert last-period slots to Games on alternate days
        if self.games_alternate_days:
            # compute assigned counts per class->subject
            assigned = defaultdict(lambda: defaultdict(int))
            for e in self.timetable:
                cls = str(e.get('class'))
                subj = e.get('subject')
                if subj:
                    assigned[cls][subj] += 1

            # helper to check whether converting slot e is safe (won't drop any subject below required)
            def safe_to_convert(e):
                cls = str(e.get('class'))
                subj = e.get('subject')
                req_map = self.required_hours.get(cls, {})
                # if no requirements specified, treat as safe
                if not req_map:
                    return True
                # compute resulting counts if we remove this slot
                for s, req in req_map.items():
                    cur = assigned[cls].get(s, 0)
                    after = cur - (1 if s == subj else 0)
                    if after < req:
                        return False
                return True

            # iterate again over dates and classes and convert last-period where allowed
            last_time = self.period_times[-1]
            # collect indices to modify to avoid mutating while iterating
            for e in list(self.timetable):
                try:
                    dt = datetime.fromisoformat(e.get('date'))
                except Exception:
                    continue
                if dt.month != month or dt.year != year:
                    continue
                if dt.weekday() not in self.working_days:
                    continue
                # alternate day check
                if (dt.day % 2) != (self.games_start_parity % 2):
                    continue
                if e.get('time') != last_time:
                    continue
                # ensure not a holiday
                if e.get('date') in getattr(self, 'holidays', set()):
                    continue
                # only convert if safe
                if safe_to_convert(e):
                    # decrement assigned count for that subject
                    cls = str(e.get('class'))
                    subj = e.get('subject')
                    if subj and assigned[cls].get(subj, 0) > 0:
                        assigned[cls][subj] -= 1
                    # replace with Games slot
                    e['subject'] = 'Games'
                    e['teacher_id'] = None
                    e['teacher_name'] = None
                    e['room'] = self.games_room

        return self.timetable

    # ------------------ Optimized generator using Min-Cost Max-Flow ------------------
    class _MCMF:
        def __init__(self, n):
            self.n = n
            self.adj = [[] for _ in range(n)]

        def add_edge(self, u, v, cap, cost):
            self.adj[u].append([v, cap, cost, len(self.adj[v])])
            self.adj[v].append([u, 0, -cost, len(self.adj[u]) - 1])

        def min_cost_flow(self, s, t, maxf=10**9):
            n = self.n
            prevv = [0]*n
            preve = [0]*n
            INF = 10**12
            res_cost = 0
            flow = 0
            h = [0]*n  # potentials

            while flow < maxf:
                dist = [INF]*n
                dist[s] = 0
                pq = [(0, s)]
                while pq:
                    d, v = heapq.heappop(pq)
                    if dist[v] < d:
                        continue
                    for i, e in enumerate(self.adj[v]):
                        to, cap, cost, rev = e
                        if cap > 0 and dist[to] > dist[v] + cost + h[v] - h[to]:
                            dist[to] = dist[v] + cost + h[v] - h[to]
                            prevv[to] = v
                            preve[to] = i
                            heapq.heappush(pq, (dist[to], to))
                if dist[t] == INF:
                    break
                for v in range(n):
                    if dist[v] < INF:
                        h[v] += dist[v]
                d = maxf - flow
                v = t
                while v != s:
                    d = min(d, self.adj[prevv[v]][preve[v]][1])
                    v = prevv[v]
                flow += d
                res_cost += d * h[t]
                v = t
                while v != s:
                    e = self.adj[prevv[v]][preve[v]]
                    e[1] -= d
                    rev = self.adj[v][e[3]]
                    rev[1] += d
                    v = prevv[v]
            return flow, res_cost

    def generate_month_optimized(self, month, year, holidays=None, allow_cross_training=False):
        """
        Optimized generator that uses a min-cost max-flow per day to assign teachers to class-period slots.
        Respects daily/weekly limits, teacher holidays, subject qualifications, and allows controlled cross-training.
        Returns generated timetable entries list (same schema as `generate_month`).
        """
        # reset state
        self.timetable = []
        self.slot_busy.clear()
        self.class_busy.clear()
        self.daily_count.clear()
        self.weekly_count.clear()
        self.unassigned_slots = []
        self.subject_shortage = defaultdict(int)

        # build holidays set
        holidays_set = set()
        if holidays is None:
            try:
                if os.path.exists('data/holidays.json'):
                    with open('data/holidays.json') as hf:
                        raw = json.load(hf)
                        if isinstance(raw, list):
                            for it in raw:
                                if isinstance(it, str):
                                    holidays_set.add(it)
                                elif isinstance(it, dict) and it.get('date'):
                                    holidays_set.add(it.get('date'))
            except Exception:
                holidays_set = set()
        else:
            for it in holidays:
                if isinstance(it, str):
                    holidays_set.add(it)
                elif isinstance(it, dict) and it.get('date'):
                    holidays_set.add(it.get('date'))
        self.holidays = holidays_set

        entry_id = 1
        cal = calendar.Calendar()

        for day in cal.itermonthdates(year, month):
            if day.month != month:
                continue
            if day.weekday() not in self.working_days:
                continue
            date_str = day.isoformat()
            if date_str in holidays_set:
                continue

            # build day's slots: list of (cls, time, subject)
            day_slots = []
            for cls in self.classes:
                subjects = self.subjects_per_class.get(cls)
                if not subjects:
                    continue
                start_idx = (day.day + hash(cls)) % len(subjects)
                for pidx, time in enumerate(self.period_times):
                    subject = subjects[(start_idx + pidx) % len(subjects)]
                    # enforce class uniqueness: if class already has assignment for time, skip slot
                    if not self.is_class_available_for_subject(cls, subject, date_str, time):
                        self.unassigned_slots.append((date_str, time, cls, subject))
                        self.subject_shortage[subject] += 1
                        continue
                    day_slots.append((cls, time, subject))

            if not day_slots:
                continue

            # Build flow graph for the day
            S = 0
            slot_start = 1
            slot_nodes = {}
            for i, slot in enumerate(day_slots):
                slot_nodes[i] = slot_start + i
            teacher_start = slot_start + len(day_slots)
            teacher_nodes = {tid: teacher_start + idx for idx, tid in enumerate(self.teacher_ids)}
            T = teacher_start + len(self.teacher_ids)
            mcmf = self._MCMF(T+1)

            # Source -> slot edges
            for i, (cls, time, subject) in enumerate(day_slots):
                mcmf.add_edge(S, slot_nodes[i], 1, 0)

            # slot -> teacher edges
            dt = day
            wk = self._week_key(datetime.fromisoformat(date_str))
            for i, (cls, time, subject) in enumerate(day_slots):
                for tid in self.teacher_ids:
                    # skip teacher if on holiday
                    if date_str in self.teachers[tid].get('holidays', set()):
                        continue
                    # skip if teacher already busy this slot by earlier allocations
                    if tid in self.slot_busy[(date_str, time)]:
                        continue
                    # skip if daily/weekly caps reached
                    if self.daily_count[date_str].get(tid, 0) >= self.teachers[tid]['max_daily']:
                        continue
                    if self.weekly_count[wk].get(tid, 0) >= self.teachers[tid]['max_weekly']:
                        continue

                    # compute cost: prefer teachers with lower weekly load
                    base_load = self.weekly_count[wk].get(tid, 0)
                    daily_load = self.daily_count[date_str].get(tid, 0)
                    # subject match penalty
                    teaches = (subject.lower() in self.teachers[tid]['subjects'])
                    if teaches:
                        subject_penalty = 0
                    else:
                        if allow_cross_training:
                            subject_penalty = 200  # allow but penalize
                        else:
                            continue

                    cost = base_load * 100 + daily_load * 10 + subject_penalty
                    mcmf.add_edge(slot_nodes[i], teacher_nodes[tid], 1, cost)

            # teacher -> sink edges with capacity = remaining daily capacity
            for tid in self.teacher_ids:
                cap = max(0, self.teachers[tid]['max_daily'] - self.daily_count[date_str].get(tid, 0))
                if cap > 0:
                    mcmf.add_edge(teacher_nodes[tid], T, cap, 0)

            # compute flow
            flow, cost = mcmf.min_cost_flow(S, T, maxf=len(day_slots))

            # now read assignments from slot->teacher edges where flow used
            # iterate over slot edges
            for i in range(len(day_slots)):
                u = slot_nodes[i]
                assigned_tid = None
                for e in mcmf.adj[u]:
                    v, cap, ecost, rev = e
                    # original capacity was 1; if cap == 0 then flow used
                    # edge to teacher nodes are in range teacher_start..teacher_start+N
                    if teacher_start <= v < teacher_start + len(self.teacher_ids):
                        if cap == 0:
                            # find teacher by node
                            # map v back to tid
                            for tid, node in teacher_nodes.items():
                                if node == v:
                                    assigned_tid = tid
                                    break
                            break

                cls, time, subject = day_slots[i]
                if assigned_tid is None:
                    # unassigned
                    self.unassigned_slots.append((date_str, time, cls, subject))
                    self.subject_shortage[subject] += 1
                    teacher_id = None
                    teacher_name = None
                else:
                    teacher_id = assigned_tid
                    teacher_name = self.teachers[assigned_tid]['name']
                    self._allocate_teacher(assigned_tid, date_str, time, cls=cls, subject=subject)

                entry = {
                    'id': entry_id,
                    'date': date_str,
                    'time': time,
                    'class': cls,
                    'subject': subject,
                    'teacher_id': teacher_id,
                    'teacher_name': teacher_name,
                    'room': f"{self.room_prefix}{100 + int(cls) if cls.isdigit() else 0}"
                }
                self.timetable.append(entry)
                entry_id += 1

        return self.timetable

    def load_mapped_entries(self, mapped_entries):
        """
        Load timetable entries from mapped API format (list of dicts saved in timetable.json)
        Expected mapped entry keys: id, faculty_id, class (e.g. 'Class 6'), subject, date, time, room, faculty
        This rebuilds internal `timetable`, `slot_busy`, `daily_count`, `weekly_count`, and `class_busy`.
        """
        self.timetable = []
        self.slot_busy.clear()
        self.class_busy.clear()  # Also clear class-subject tracking
        self.daily_count.clear()
        self.weekly_count.clear()

        entry_id = 1
        for e in mapped_entries:
            cls = e.get('class')
            # normalize class label
            if isinstance(cls, str) and cls.lower().startswith('class'):
                cls_val = cls.split(' ', 1)[1].strip()
            else:
                cls_val = str(cls)

            teacher_id = e.get('faculty_id')
            date_str = e.get('date')
            time = e.get('time')
            subject = e.get('subject')

            # build manager-format entry
            entry = {
                'id': entry_id,
                'date': date_str,
                'time': time,
                'class': cls_val,
                'subject': subject,
                'teacher_id': teacher_id,
                'teacher_name': e.get('faculty'),
                'room': e.get('room')
            }
            self.timetable.append(entry)

            # if teacher assigned, mark allocations with class-subject tracking
            if teacher_id is not None:
                try:
                    tid = int(teacher_id)
                except Exception:
                    tid = teacher_id
                # Pass class and subject to track class-subject assignment
                self._allocate_teacher(tid, date_str, time, cls=cls_val, subject=subject)

            entry_id += 1

        return self.timetable

    def export_mapped(self):
        """Export current manager timetable into mapped API format used by frontend/backend storage."""
        mapped = []
        for e in self.timetable:
            mapped.append({
                'id': e.get('id'),
                'faculty_id': e.get('teacher_id'),
                'class': f"Class {e.get('class')}",
                'subject': e.get('subject'),
                'date': e.get('date'),
                'time': e.get('time'),
                'room': e.get('room'),
                'faculty': e.get('teacher_name') or 'Unassigned'
            })
        return mapped

    def get_summary(self):
        """Return a summary dict: teacher_count, hours_per_day, hours_per_week, classes_count"""
        return {
            'teacher_count': len(self.teachers),
            'hours_per_day': self.default_max_daily,
            'hours_per_week': self.default_max_weekly,
            'classes_count': len(self.classes)
        }

    def apply_leave(self, teacher_id, date_str):
        """
        Replace allocations for teacher_id on given date (ISO string) with substitutes.
        Respects class-subject uniqueness constraint when assigning substitutes.
        Returns number of replaced slots.
        """
        replaced = 0
        # find timetable entries for that teacher and date
        for entry in list(self.timetable):
            if entry.get('teacher_id') != teacher_id:
                continue
            if entry.get('date') != date_str:
                continue
            time = entry.get('time')
            subject = entry.get('subject')
            cls = entry.get('class')
            # remove previous allocation
            if teacher_id in self.slot_busy[(date_str, time)]:
                self.slot_busy[(date_str, time)].remove(teacher_id)
            if self.daily_count[date_str].get(teacher_id, 0) > 0:
                self.daily_count[date_str][teacher_id] -= 1
            wk = self._week_key(datetime.fromisoformat(date_str))
            if self.weekly_count[wk].get(teacher_id, 0) > 0:
                self.weekly_count[wk][teacher_id] -= 1
            # Remove class-subject assignment for this slot
            if (date_str, time) in self.class_busy and cls in self.class_busy[(date_str, time)]:
                del self.class_busy[(date_str, time)][cls]

            # find substitute (with preference for faculty assigned to this class)
            sub_tid = self.find_teacher_for_subject(subject, date_str, time, cls=cls)
            if sub_tid is not None:
                entry['teacher_id'] = sub_tid
                entry['teacher_name'] = self.teachers[sub_tid]['name']
                # Allocate substitute with class-subject tracking
                self._allocate_teacher(sub_tid, date_str, time, cls=cls, subject=subject)
                replaced += 1
            else:
                entry['teacher_id'] = None
                entry['teacher_name'] = None
        return replaced

    def save_json(self, path):
        dirp = os.path.dirname(path)
        if dirp and not os.path.exists(dirp):
            os.makedirs(dirp)
        with open(path, 'w') as f:
            json.dump(self.timetable, f, indent=2)

    def load_json(self, path):
        with open(path) as f:
            self.timetable = json.load(f)
        return self.timetable


# ---------------- Example usage ----------------
if __name__ == '__main__':
    # demo data
    teachers = [
        {'id': 1, 'name': 'Ravi', 'subjects': ['Math'], 'max_daily': 5, 'max_weekly': 30},
        {'id': 2, 'name': 'Sita', 'subjects': ['Math','Physics'], 'max_daily': 5, 'max_weekly': 30},
        {'id': 3, 'name': 'Arun', 'subjects': ['CS'], 'max_daily': 5, 'max_weekly': 30},
        {'id': 4, 'name': 'Kavya', 'subjects': ['English','Physics'], 'max_daily': 5, 'max_weekly': 30}
    ]

    classes = [6,7]
    subjects_per_class = {
        '6': ['Math','Physics','CS','English'],
        '7': ['Math','Physics','CS','English']
    }

    mgr = TimetableManager(teachers, classes, subjects_per_class)
    t = mgr.generate_month(month=datetime.today().month, year=datetime.today().year)
    print(f"Generated {len(t)} entries")
    # apply leave example: teacher 1 on today's date
    today = datetime.today().date().isoformat()
    replaced = mgr.apply_leave(1, today)
    print(f"Replaced {replaced} slots for leave on {today}")
    mgr.save_json('data/timetable.generated.json')
    print('Saved to data/timetable.generated.json')
