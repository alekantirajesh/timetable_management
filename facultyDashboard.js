import { useState, useEffect, useCallback } from "react";
import api from "../api";

function FacultyDashboard() {
    const [timetable, setTimetable] = useState([]);
    const [workloadHours, setWorkloadHours] = useState(0);
    const [selectedMonthWorkload, setSelectedMonthWorkload] = useState(0);
    const [facultyHolidays, setFacultyHolidays] = useState([]);
    const [publicHolidays, setPublicHolidays] = useState([]);
    const [facultyDetails, setFacultyDetails] = useState({});
    const [facultyEmail, setFacultyEmail] = useState("");
    const [currentWeekStart, setCurrentWeekStart] = useState(new Date());
    const [availableMonths, setAvailableMonths] = useState([]);
    const [selectedMonth, setSelectedMonth] = useState(null);
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState("");
    const [leaveRequests, setLeaveRequests] = useState([]);
    const [leaveDate, setLeaveDate] = useState("");
    const [leaveReason, setLeaveReason] = useState("");
    // Prefer explicit `faculty_id` stored at login; fall back to `user_id` for backward compatibility
    const facultyId = localStorage.getItem("faculty_id") || localStorage.getItem("user_id");
    const WORKLOAD_LOW = 50; // Below this is low workload
    const WORKLOAD_HIGH = 120; // Above this is high workload
    const WORKLOAD_AVG = 75; // Average workload target

    // Fetch faculty details
    const fetchFacultyDetails = useCallback(async () => {
        try {
            if (!facultyId) return;
            const response = await api.get(`/faculty`);
            const facultyList = response.data || [];
            const faculty = facultyList.find(f => f.id === parseInt(facultyId));
            if (faculty) {
                setFacultyDetails(faculty);
                if (faculty.email) {
                    setFacultyEmail(faculty.email);
                }
            }
        } catch (error) {
            console.error("Error fetching faculty details:", error);
        }
    }, [facultyId]);

    const fetchTimetable = useCallback(async () => {
        try {
            if (!facultyId) return;
            setLoading(true);
            console.log('🔄 Refreshing timetable from database...');
            const response = await api.get(`/timetable?_t=${Date.now()}`);
            const raw = response.data || [];
            // Filter entries to only those that belong to this faculty (robust to id types/fields)
            const fidStr = String(facultyId);
            const filtered = raw.filter(e => {
                if (!e) return false;
                try {
                    // check numeric id fields first
                    if (e.faculty_id !== undefined && e.faculty_id !== null) {
                        if (String(e.faculty_id) === fidStr) return true;
                    }
                    if (e.teacher_id !== undefined && e.teacher_id !== null) {
                        if (String(e.teacher_id) === fidStr) return true;
                    }
                } catch (ex) {
                    // ignore
                }
                // fallback to matching by name if faculty details available
                if (facultyDetails && facultyDetails.name) {
                    const name = (facultyDetails.name || '').toLowerCase();
                    if ((e.faculty || e.teacher_name || '').toLowerCase() === name) return true;
                }
                return false;
            });
            console.log(`[FAC-TIMETABLE] fetched ${raw.length} entries, filtered to ${filtered.length} for faculty ${fidStr}`);
            setTimetable(filtered);
            console.log(`✓ Timetable refreshed: ${filtered.length} entries loaded`);
            try {
                // Log filtered DB sample and counts per month for this faculty
                const sample = (filtered || []).slice(0, 20);
                const counts = {};
                (filtered || []).forEach(e => {
                    if (!e || !e.date) return;
                    const m = e.date.slice(0,7);
                    counts[m] = (counts[m] || 0) + 1;
                });
                console.log('[FAC-TIMETABLE-DEBUG] filtered entries sample (first 20):', sample);
                console.log('[FAC-TIMETABLE-DEBUG] counts per month for this faculty:', counts);
            } catch (ex) {
                console.warn('[FAC-TIMETABLE-DEBUG] failed to compute timetable debug info', ex);
            }
        } catch (error) {
            console.error("Error fetching timetable:", error);
            setTimetable([]);
        } finally {
            setLoading(false);
        }
    }, [facultyId, facultyDetails]);

    // Compare frontend-counted hours vs backend workload when both available
    useEffect(() => {
        try {
            const entries = timetable || [];
            const counts = {};
            entries.forEach(e => {
                if (!e || !e.date) return;
                const m = e.date.slice(0,7);
                counts[m] = (counts[m] || 0) + 1;
            });
                const thisMonthKey = formatDate(new Date()).slice(0,7);
            const frontendThisMonth = counts[thisMonthKey] || 0;
            console.log('[FAC-TIMETABLE-COMPARE] frontend counted hours for', thisMonthKey, ':', frontendThisMonth, 'backend workloadHours:', workloadHours);
            if (workloadHours !== null && workloadHours !== undefined) {
                if (frontendThisMonth !== workloadHours) {
                    console.warn('[FAC-TIMETABLE-COMPARE] MISMATCH detected: frontend entries count !== backend workloadHours');
                } else {
                    console.log('[FAC-TIMETABLE-COMPARE] frontend and backend workload match');
                }
            }
        } catch (e) {
            console.warn('Failed to compare timetable vs workload', e);
        }
    }, [timetable, workloadHours]);

    const fetchWorkloadHours = useCallback(async () => {
        try {
            const response = await api.get(`/faculty-workload`);
            const allWorkload = response.data || [];
            const myWorkload = allWorkload.find(w => String(w.id) === String(facultyId) || Number(w.id) === Number(facultyId));
            if (myWorkload) {
                setWorkloadHours(myWorkload.hours);
            }
        } catch (error) {
            console.error("Error fetching workload:", error);
        }
    }, [facultyId]);

    const fetchFacultyHolidays = useCallback(async () => {
        try {
            if (!facultyId) return;
            const res = await api.get(`/faculty/${facultyId}/holidays`);
            setFacultyHolidays(res.data || []);
        } catch (err) {
            console.error('Failed to load faculty holidays', err);
            setFacultyHolidays([]);
        }
    }, [facultyId]);

    const fetchPublicHolidays = useCallback(async () => {
        try {
            const res = await api.get('/holidays');
            setPublicHolidays(Array.isArray(res.data) ? res.data : []);
        } catch (e) {
            console.warn('Failed to load public holidays', e);
            setPublicHolidays([]);
        }
    }, []);

    // Leave Request Functions
    const fetchLeaveRequests = useCallback(async () => {
        try {
            setLoading(true);
            const response = await api.get(`/leaves?faculty_id=${facultyId}`);
            setLeaveRequests(response.data || []);
            setMessage("✓ Leave requests loaded");
        } catch (error) {
            console.error("Error fetching leave requests:", error);
            setMessage("Error fetching leave requests: " + error.message);
        } finally {
            setLoading(false);
        }
    });

    // Refresh weekly timetable and related data from DB
    const refreshWeeklyTimetable = async () => {
        try {
            setLoading(true);
            console.log('🔄 Manual refresh: fetching latest timetable, workload, holidays, and leaves from DB...');
            await Promise.all([
                fetchTimetable(),
                fetchWorkloadHours(),
                fetchFacultyHolidays(),
                fetchLeaveRequests()
            ]);
            setMessage('✓ Weekly timetable refreshed from database');
        } catch (e) {
            console.warn('Refresh failed', e);
            setMessage('❌ Failed to refresh timetable: ' + (e?.message || e));
        } finally {
            setLoading(false);
        }
    };

    // Load data on mount only (when facultyId changes)
    useEffect(() => {
        if (!facultyId) return;
        
        fetchFacultyDetails();
        fetchTimetable();
        fetchWorkloadHours();
        fetchFacultyHolidays();
        fetchPublicHolidays();
        fetchAvailableMonths();
        fetchLeaveRequests();
    }, [facultyId]);

    // Refresh when admin or other actions update data
    useEffect(() => {
        const onDataUpdated = () => {
            console.log('🔔 Faculty dashboard received data-updated; refreshing timetable and workload');
            fetchTimetable();
            fetchWorkloadHours();
            fetchFacultyHolidays();
            // Also refresh faculty's own leave requests so approved leaves become visible
            try { fetchLeaveRequests(); } catch (e) { console.warn('Failed to refresh leave requests', e); }
        };
        window.addEventListener('data-updated', onDataUpdated);
        return () => window.removeEventListener('data-updated', onDataUpdated);
    }, [fetchTimetable, fetchWorkloadHours, fetchFacultyHolidays]);

    useEffect(() => {
        if (message) {
            const timer = setTimeout(() => {
                setMessage("");
            }, 5000);
            return () => clearTimeout(timer);
        }
    }, [message]);

    const applyLeave = async () => {
        if (!leaveDate || !leaveReason) {
            setMessage("⚠️ Please enter date and reason");
            return;
        }
        try {
            setLoading(true);
            const response = await api.post("/apply_leave", {
                faculty_id: parseInt(facultyId),
                date: leaveDate,
                reason: leaveReason
            });
            if (response.status === 201) {
                setMessage("✓ Leave request submitted successfully!");
                setLeaveDate("");
                setLeaveReason("");
                await fetchLeaveRequests();
            }
        } catch (error) {
            if (error.response?.status === 409) {
                setMessage("⚠️ Leave request already exists for this date");
            } else {
                setMessage("❌ Error: " + (error.response?.data?.message || error.message));
            }
        } finally {
            setLoading(false);
        }
    };

    // Week management functions
    const getWeekStart = (date) => {
        const d = new Date(date);
        const day = d.getDay();
        const diff = d.getDate() - day + (day === 0 ? -6 : 1);
        return new Date(d.setDate(diff));
    };

    const formatDate = (date) => {
        if (!date) return '';
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        return `${y}-${m}-${d}`;
    };

    const getDayName = (date) => {
        return date.toLocaleString('default', { weekday: 'short' });
    };

    const handlePreviousWeek = () => {
        const prev = new Date(currentWeekStart);
        prev.setDate(prev.getDate() - 7);

        // If a month is selected, ensure we stay within it
        if (selectedMonth) {
            const firstWeek = getFirstWeekOfMonth(selectedMonth);
            if (firstWeek) {
                // If previous week would go before the first week start, snap to firstWeek
                if (prev.getTime() < firstWeek.getTime()) {
                    setCurrentWeekStart(firstWeek);
                    return;
                }
            }
        }

        setCurrentWeekStart(prev);
    };

    const handleCurrentWeek = () => {
        setCurrentWeekStart(getWeekStart(new Date()));
        setSelectedMonth(null);
    };

    const handleNextWeek = () => {
        const next = new Date(currentWeekStart);
        next.setDate(next.getDate() + 7);

        if (selectedMonth) {
            const monthYearData = getMonthYearFromString(selectedMonth);
            if (monthYearData) {
                const lastDayOfMonth = new Date(monthYearData.year, monthYearData.month, 0);
                if (next > lastDayOfMonth) return;
            }
        }

        setCurrentWeekStart(next);
    };

    // Month helpers (match admin Timetable behaviour)
    const fetchAvailableMonths = async () => {
        try {
            const res = await api.get('/timetable-months');
            setAvailableMonths(res.data || []);
        } catch (err) {
            console.error('Failed to load available months', err);
            setAvailableMonths([]);
        }
    };

    const getFirstWeekOfMonth = (yearMonth) => {
        if (!yearMonth) return null;
        const monthNameMap = {
            'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
            'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12
        };
        const parts = yearMonth.split(' ');
        const monthName = parts[0];
        const year = parseInt(parts[1]);
        const month = monthNameMap[monthName];
        if (!month || !year) return null;
        const firstDay = new Date(year, month - 1, 1);
        const dayOfWeek = firstDay.getDay();
        const diff = -dayOfWeek; // Sunday-based week start
        firstDay.setDate(1 + diff);
        firstDay.setHours(0,0,0,0);
        return firstDay;
    };

    const getMonthYearFromString = (yearMonth) => {
        if (!yearMonth) return null;
        const monthNameMap = {
            'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
            'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12
        };
        const parts = yearMonth.split(' ');
        const monthName = parts[0];
        const year = parseInt(parts[1]);
        const month = monthNameMap[monthName];
        return month && year ? { month, year } : null;
    };

    // Calculate workload for the selected month
    const calculateSelectedMonthWorkload = useCallback(() => {
        if (!selectedMonth || !timetable || timetable.length === 0) {
            setSelectedMonthWorkload(0);
            return;
        }
        
        const monthYearData = getMonthYearFromString(selectedMonth);
        if (!monthYearData) {
            setSelectedMonthWorkload(0);
            return;
        }
        
        const { month, year } = monthYearData;
        let totalHours = 0;
        
        timetable.forEach(entry => {
            if (!entry || !entry.date) return;
            const [entryYear, entryMonth] = entry.date.split('-').map(Number);
            if (entryYear === year && entryMonth === month) {
                totalHours += 1; // Each entry is 1 hour
            }
        });
        
        setSelectedMonthWorkload(totalHours);
    }, [selectedMonth, timetable]);

    useEffect(() => {
        calculateSelectedMonthWorkload();
    }, [calculateSelectedMonthWorkload]);

    const isPreviousWeekDisabled = () => {
        if (!selectedMonth) return false;
        const monthYearData = getMonthYearFromString(selectedMonth);
        if (!monthYearData) return false;
        // Get the actual first week of the month (may be partial)
        const firstWeek = getFirstWeekOfMonth(selectedMonth);
        if (!firstWeek) return false;
        // Only disable if we're already at the first week (exact match)
        return currentWeekStart.getTime() === firstWeek.getTime();
    };

    const isNextWeekDisabled = () => {
        if (!selectedMonth) return false;
        const monthYearData = getMonthYearFromString(selectedMonth);
        if (!monthYearData) return false;
        const lastDayOfMonth = new Date(monthYearData.year, monthYearData.month, 0);
        const nextWeekStart = new Date(currentWeekStart);
        nextWeekStart.setDate(currentWeekStart.getDate() + 7);
        return nextWeekStart > lastDayOfMonth;
    };

    return (
        <div className="container">
            {/* Top navbar: faculty email + logout */}
            <div style={{ backgroundColor: "#fff", padding: "10px 16px", marginBottom: "12px", borderRadius: "8px", boxShadow: "0 2px 6px rgba(0,0,0,0.08)", background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: 'white' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ fontSize: '14px', opacity: 0.95 }}>📧 {facultyEmail || '...'}</div>
                    <div>
                        <button
                            onClick={() => { try { localStorage.clear(); } catch (e) {} ; window.location.href = '/login'; }}
                            style={{ padding: '8px 12px', backgroundColor: '#fff', color: '#5b3cc4', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: '700' }}
                        >
                            🔒 Logout
                        </button>
                    </div>
                </div>
            </div>

            <div className="page-header">
                <div>
                    <div className="page-title">👨‍🏫 Faculty Dashboard</div>
                    <div className="page-sub">Overview of your workload and timetable</div>
                </div>
                <div className="card-actions">
                    <button className="btn btn-ghost" onClick={refreshWeeklyTimetable} disabled={loading}>🔄 Refresh</button>
                </div>
            </div>

            {/* Faculty Profile Card */}
            {Object.keys(facultyDetails).length > 0 && (
                <div className="card" style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: 'white', marginBottom: '20px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                        <div>
                            <div style={{ fontSize: '12px', opacity: '0.9', marginBottom: '4px' }}>Faculty Name</div>
                            <div style={{ fontSize: '24px', fontWeight: '700', marginBottom: '15px' }}>{facultyDetails.name}</div>
                            <div style={{ fontSize: '12px', opacity: '0.9', marginBottom: '4px' }}>Subject</div>
                            <div style={{ fontSize: '16px', fontWeight: '600' }}>📚 {facultyDetails.subject}</div>
                        </div>
                        <div style={{ borderLeft: '2px solid rgba(255,255,255,0.2)', paddingLeft: '20px' }}>
                            <div style={{ fontSize: '12px', opacity: '0.9', marginBottom: '4px' }}>Email</div>
                            <div style={{ fontSize: '14px', marginBottom: '15px', wordBreak: 'break-all' }}>{facultyEmail || 'Loading...'}</div>
                            <div style={{ fontSize: '12px', opacity: '0.9', marginBottom: '4px' }}>Faculty ID</div>
                            <div style={{ fontSize: '16px', fontWeight: '600' }}>ID: {facultyDetails.id}</div>
                        </div>
                    </div>
                </div>
            )}

            {/* Message Display */}
            {message && (
                <div style={{
                    padding: "12px",
                    marginBottom: "20px",
                    backgroundColor: (message.includes("Error") || message.includes("❌") || message.includes("⚠️")) ? "#fff3cd" : "#d4edda",
                    color: (message.includes("Error") || message.includes("❌")) ? "#721c24" : (message.includes("⚠️") ? "#856404" : "#155724"),
                    borderRadius: "4px",
                    border: "1px solid " + ((message.includes("Error") || message.includes("❌")) ? "#f5c6cb" : (message.includes("⚠️") ? "#ffeaa7" : "#c3e6cb")),
                    fontSize: "14px"
                }}>
                    {message}
                </div>
            )}

            <div className="card">
                <div className="card-header">
                    <div>
                        <strong>⏱️ Your Workload</strong>
                        <div className="muted">{selectedMonth ? `Total hours in ${selectedMonth}` : 'Total hours this month'}</div>
                    </div>
                    <div style={{fontSize:24,fontWeight:700,color:'#4CAF50'}}>{selectedMonth ? selectedMonthWorkload : workloadHours} hrs</div>
                </div>
                <div style={{ padding: "15px" }}>
                    {(() => {
                        const displayHours = selectedMonth ? selectedMonthWorkload : workloadHours;
                        const getStatusColor = (hours) => {
                            return hours > WORKLOAD_HIGH ? "#d32f2f" : (hours < WORKLOAD_LOW ? "#ff9800" : "#4CAF50");
                        };
                        const getStatusText = (hours) => {
                            return hours > WORKLOAD_HIGH ? "🔴 High" : (hours < WORKLOAD_LOW ? "🟡 Low" : "🟢 Average");
                        };
                        return (
                            <>
                                <div style={{ marginBottom: "10px", display: "flex", justifyContent: "space-between", fontSize: "14px" }}>
                                    <span>Workload Status:</span>
                                    <span style={{ 
                                        fontWeight: "bold", 
                                        color: getStatusColor(displayHours)
                                    }}>
                                        {getStatusText(displayHours)}
                                    </span>
                                </div>
                                <div style={{ 
                                    width: "100%", 
                                    height: "20px", 
                                    backgroundColor: "#e0e0e0", 
                                    borderRadius: "10px", 
                                    overflow: "hidden",
                                    border: "1px solid #ddd"
                                }}>
                                    <div style={{
                                        width: `${Math.min((displayHours / WORKLOAD_HIGH) * 100, 100)}%`,
                                        height: "100%",
                                        backgroundColor: getStatusColor(displayHours),
                                        transition: "width 0.3s ease",
                                        display: "flex",
                                        alignItems: "center",
                                        justifyContent: "center",
                                        color: "white",
                                        fontSize: "12px",
                                        fontWeight: "bold"
                                    }}>
                                        {displayHours > 10 && `${Math.round((displayHours / WORKLOAD_HIGH) * 100)}%`}
                                    </div>
                                </div>
                            </>
                        );
                    })()}
                    <div style={{ marginTop: "8px", fontSize: "12px", color: "#666" }}>
                        Target: {WORKLOAD_LOW}-{WORKLOAD_HIGH} hours | Avg: {WORKLOAD_AVG} hrs
                    </div>
                </div>
            </div>

            <div className="card">
                <div className="card-header">
                    <div>
                        <strong>📅 Weekly Timetable</strong>
                        <div className="muted">
                            {(() => {
                                const weekEnd = new Date(currentWeekStart);
                                weekEnd.setDate(weekEnd.getDate() + 6);
                                const startMonth = currentWeekStart.toLocaleString('default', { month: 'long' });
                                const endMonth = weekEnd.toLocaleString('default', { month: 'long' });
                                const year = currentWeekStart.getFullYear();
                                
                                if (startMonth === endMonth) {
                                    return `${startMonth} ${year} • Week of ${currentWeekStart.getDate()} - ${weekEnd.getDate()}`;
                                } else {
                                    return `${startMonth} ${currentWeekStart.getDate()} - ${endMonth} ${weekEnd.getDate()}, ${year}`;
                                }
                            })()}
                        </div>
                    </div>
                    <div className="card-actions">
                        <select
                            value={selectedMonth || ""}
                            onChange={(e) => {
                                const month = e.target.value;
                                setSelectedMonth(month || null);
                                if (month) {
                                    const firstWeekStart = getFirstWeekOfMonth(month);
                                    if (firstWeekStart) setCurrentWeekStart(firstWeekStart);
                                }
                            }}
                            style={{ marginRight: '8px', padding: '8px', borderRadius: '6px' }}
                        >
                            <option value="">-- Select month --</option>
                            {availableMonths.map(m => (
                                <option key={m} value={m}>{m}</option>
                            ))}
                        </select>

                        <button className="btn" onClick={handlePreviousWeek} disabled={isPreviousWeekDisabled()}>← Previous Week</button>
                        <button className="btn" onClick={handleCurrentWeek}>📍 This Week</button>
                        <button className="btn" onClick={handleNextWeek} disabled={isNextWeekDisabled()}>Next Week →</button>
                        <button className="btn btn-primary" onClick={fetchTimetable} disabled={loading} style={{ marginLeft: '10px' }}>
                            🔄 {loading ? 'Refreshing...' : 'Refresh'}
                        </button>
                    </div>
                </div>

                {loading ? (
                    <p className="muted">Loading weekly timetable...</p>
                ) : !selectedMonth ? (
                    <div style={{ 
                        position: "relative", 
                        height: "300px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        marginBottom: '15px'
                    }}>
                        <div style={{
                            fontSize: "120px",
                            fontWeight: "bold",
                            color: "rgba(0, 0, 0, 0.08)",
                            whiteSpace: "nowrap",
                            letterSpacing: "20px",
                            textAlign: "center"
                        }}>
                            timetable
                        </div>
                    </div>
                ) : timetable.length > 0 ? (
                    <div style={{ overflowX: 'hidden', marginBottom: '15px' }}>
                        <table style={{
                            width: '100%',
                            borderCollapse: 'collapse',
                            fontSize: '12px',
                            tableLayout: 'fixed'
                        }}>
                            <thead>
                                <tr style={{ backgroundColor: '#f0f0f0', borderBottom: '2px solid #2196F3' }}>
                                    <th style={{ padding: '10px', textAlign: 'center', fontWeight: 'bold', minWidth: '60px', borderRight: '1px solid #ddd' }}>Time</th>
                                    {Array.from({ length: 7 }).map((_, dayIndex) => {
                                        const dayDate = new Date(currentWeekStart);
                                        dayDate.setDate(dayDate.getDate() + dayIndex);
                                        const today = formatDate(new Date());
                                        const dayDateStr = formatDate(dayDate);
                                        const isToday = dayDateStr === today;
                                        const holidayObj = publicHolidays.find(h => h.date === dayDateStr) || null;
                                        const holidayName = holidayObj ? holidayObj.name : null;
                                        const isSunday = dayDate.getDay() === 0;
                                        const isHolidayCell = isSunday || Boolean(holidayName);

                                        return (
                                            <th 
                                                key={dayIndex}
                                                style={{
                                                    padding: '10px',
                                                    textAlign: 'center',
                                                    fontWeight: 'bold',
                                                    width: `${Math.floor(100/7)}%`,
                                                    borderRight: '1px solid #ddd',
                                                    backgroundColor: isHolidayCell ? '#FFEBEE' : (isToday ? '#fff3e0' : 'transparent'),
                                                    borderBottom: isToday ? '3px solid #FF9800' : '1px solid #ddd'
                                                }}
                                            >
                                                <div>{getDayName(dayDate)}</div>
                                                <div style={{ fontSize: '11px', color: '#666', marginTop: '2px' }}>
                                                    {dayDate.getDate()} {dayDate.toLocaleString('default', { month: 'short' })} {isToday && '📌'}
                                                </div>
                                                {isHolidayCell && (
                                                    <div style={{ fontSize: '11px', color: '#e65100', fontWeight: '700', marginTop: '4px' }}>
                                                        {holidayName ? holidayName : 'Sunday'}
                                                    </div>
                                                )}
                                            </th>
                                        );
                                    })}
                                </tr>
                            </thead>
                            <tbody>
                                {Array.from([9,10,11,12,13,14,15,16]).map((hours, timeIndex) => {
                                    const timeSlot = `${hours.toString().padStart(2, '0')}:00`;
                                    const displayTime = (() => {
                                        const h = hours;
                                        const ampm = h >= 12 ? 'PM' : 'AM';
                                        const hh = h % 12 === 0 ? 12 : h % 12;
                                        return `${hh}:00 ${ampm}`;
                                    })();
                                    
                                    return (
                                        <tr key={hours} style={{ borderBottom: '1px solid #e0e0e0' }}>
                                            <td style={{
                                                padding: '10px',
                                                textAlign: 'center',
                                                fontWeight: '600',
                                                color: '#2196F3',
                                                borderRight: '1px solid #ddd',
                                                backgroundColor: '#f9f9f9'
                                            }}>
                                                {displayTime}
                                            </td>
                                            {Array.from({ length: 7 }).map((_, dayIndex) => {
                                                const dayDate = new Date(currentWeekStart);
                                                dayDate.setDate(dayDate.getDate() + dayIndex);
                                                const dayDateStr = formatDate(dayDate);
                                                const today = formatDate(new Date());

                                                const holidayObj = publicHolidays.find(h => h.date === dayDateStr) || null;
                                                const holidayName = holidayObj ? holidayObj.name : null;
                                                const isSunday = dayDate.getDay() === 0;
                                                const isHolidayCell = isSunday || Boolean(holidayName);

                                                // Reserve 12:00 for lunch — always show a lunch block
                                                if (hours === 12) {
                                                    return (
                                                        <td
                                                            key={dayIndex}
                                                            style={{
                                                                padding: '8px',
                                                                textAlign: 'center',
                                                                borderRight: '1px solid #ddd',
                                                                backgroundColor: isHolidayCell ? '#fff3e0' : (dayDateStr === today ? '#fff8e1' : '#fff'),
                                                                minHeight: '60px',
                                                                verticalAlign: 'middle'
                                                            }}
                                                        >
                                                            <div style={{
                                                                backgroundColor: '#ffeb3b',
                                                                color: '#333',
                                                                padding: '10px',
                                                                borderRadius: '6px',
                                                                fontSize: '12px',
                                                                fontWeight: '700'
                                                            }}>
                                                                LUNCH
                                                            </div>
                                                        </td>
                                                    );
                                                }

                                                // Find classes for this day and time (match hour prefix)
                                                const classAtTime = timetable.find(entry => 
                                                    entry.date === dayDateStr && entry.time && entry.time.startsWith(timeSlot.substring(0, 2))
                                                );
                                                
                                                return (
                                                    <td
                                                        key={dayIndex}
                                                        style={{
                                                            padding: '8px',
                                                            textAlign: 'center',
                                                            borderRight: '1px solid #ddd',
                                                            backgroundColor: isHolidayCell ? '#fff3e0' : (dayDateStr === today ? '#fffbf0' : '#fff'),
                                                            minHeight: '60px',
                                                            verticalAlign: 'middle'
                                                        }}
                                                    >
                                                        {classAtTime ? (
                                                            <div style={{
                                                                backgroundColor: '#2196F3',
                                                                color: 'white',
                                                                padding: '8px',
                                                                borderRadius: '4px',
                                                                fontSize: '11px',
                                                                lineHeight: '1.3'
                                                            }}>
                                                                <strong>{classAtTime.subject}</strong>
                                                                <p style={{ margin: '3px 0', fontSize: '10px' }}>📚 {classAtTime.class}</p>
                                                                <p style={{ margin: '3px 0', fontSize: '10px' }}>⏰ {classAtTime.time}</p>
                                                                <p style={{ margin: '3px 0', fontSize: '10px' }}>👨‍🏫 {classAtTime.faculty || classAtTime.teacher_name || '—'}</p>
                                                            </div>
                                                        ) : (
                                                            <span style={{ color: '#ccc', fontSize: '11px' }}>—</span>
                                                        )}
                                                    </td>
                                                );
                                            })}
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <p className="muted">No timetable entries to display</p>
                )}
            </div>




            <div className="card">
                <div className="card-header">
                    <div>
                        <strong>Leave Request Management</strong>
                        <div className="muted">Apply for leave and track your requests</div>
                    </div>
                </div>

                {/* Leave Application Form */}
                <div style={{padding: "12px", backgroundColor: "#f0f4ff", border: "1px solid #d0deff", borderRadius: "4px", marginBottom: "12px"}}>
                    <h4 style={{margin: "0 0 12px 0", color: "#1976d2"}}>📝 Apply for Leave</h4>
                    <div style={{display: "flex", gap: "10px", alignItems: "flex-start", flexWrap: "wrap"}}>
                        <input
                            className="input"
                            type="date"
                            value={leaveDate}
                            onChange={(e) => setLeaveDate(e.target.value)}
                            style={{flex: 1, minWidth: "150px"}}
                        />
                        <input
                            className="input"
                            type="text"
                            placeholder="Reason for leave..."
                            value={leaveReason}
                            onChange={(e) => setLeaveReason(e.target.value)}
                            style={{flex: 1, minWidth: "200px"}}
                        />
                        <button
                            className="btn btn-primary"
                            onClick={applyLeave}
                            disabled={loading || !leaveDate || !leaveReason}
                            style={{width: "auto"}}
                        >
                            Submit Request
                        </button>
                    </div>
                </div>

                {/* Leave History */}
                <div style={{marginTop: "12px"}}>
                    <div style={{display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px"}}>
                        <h4 style={{margin: 0}}>📋 Your Leave Requests</h4>
                        <button
                            className="btn"
                            onClick={fetchLeaveRequests}
                            disabled={loading}
                            style={{width: "auto"}}
                        >
                            🔄 Refresh
                        </button>
                    </div>

                    {leaveRequests.length > 0 ? (
                        <div style={{overflowX: "auto", border: "1px solid #ddd", borderRadius: "4px"}}>
                            <table className="timetable">
                                <thead>
                                    <tr style={{backgroundColor: "#1976d2", color: "white"}}>
                                        <th>Date</th>
                                        <th>Reason</th>
                                        <th>Status</th>
                                        <th>Applied On</th>
                                        <th>Admin Notes</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {leaveRequests.map((leave, idx) => {
                                        let statusColor = "#ff9800";
                                        let statusBg = "#fff3e0";
                                        if (leave.status === "approved") {
                                            statusColor = "#2e7d32";
                                            statusBg = "#e8f5e9";
                                        }
                                        if (leave.status === "rejected") {
                                            statusColor = "#d32f2f";
                                            statusBg = "#ffebee";
                                        }

                                        return (
                                            <tr key={idx} style={{backgroundColor: idx % 2 === 0 ? "#fff" : "#f9f9f9"}}>
                                                <td><strong>{leave.date}</strong></td>
                                                <td>{leave.reason}</td>
                                                <td style={{
                                                    color: statusColor,
                                                    fontWeight: "bold",
                                                    backgroundColor: statusBg,
                                                    padding: "6px 10px",
                                                    borderRadius: "4px",
                                                    display: "inline-block"
                                                }}>
                                                    {leave.status === "pending" && "⏳ PENDING"}
                                                    {leave.status === "approved" && "✓ APPROVED"}
                                                    {leave.status === "rejected" && "✗ REJECTED"}
                                                </td>
                                                <td style={{fontSize: "12px"}}>
                                                    {new Date(leave.requested_at).toLocaleDateString()}
                                                </td>
                                                <td style={{fontSize: "12px", color: "#666"}}>
                                                    {leave.status === "approved" && leave.admin_notes && `📝 ${leave.admin_notes}`}
                                                    {leave.status === "rejected" && leave.rejection_reason && `❌ ${leave.rejection_reason}`}
                                                    {leave.status === "pending" && "—"}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    ) : (
                        <p className="muted">No leave requests yet. Submit one above!</p>
                    )}
                </div>
            </div>
        </div>
    );
}

export default FacultyDashboard;
