import { useState, useEffect, useMemo } from "react";
import api from "../api";

function StudentDashboard() {
    const [timetable, setTimetable] = useState([]);
    const [todayClasses, setTodayClasses] = useState([]);
    const [studentDetails, setStudentDetails] = useState({});
    const [currentWeekStart, setCurrentWeekStart] = useState(() => {
        const d = new Date();
        const day = d.getDay();
        const diff = d.getDate() - day + (day === 0 ? -6 : 1); // Monday as week start
        return new Date(d.setDate(diff));
    });
    const [weeklyClasses, setWeeklyClasses] = useState({});
    const [selectedDate, setSelectedDate] = useState(new Date());
    const [loading, setLoading] = useState(false);
    const [lastUpdated, setLastUpdated] = useState(new Date());
    const [holidayList, setHolidayList] = useState([]);
    const [studentClass, setStudentClass] = useState(localStorage.getItem("student_class") || "");
    const [selectedMonth, setSelectedMonth] = useState("");
    const months = useMemo(() => {
        const m = Array.from(new Set((timetable || []).map(e => e.date && e.date.slice(0,7)).filter(Boolean)));
        m.sort();
        return m.length ? m : [new Date().toISOString().slice(0,7)];
    }, [timetable]);

    const holidayMap = useMemo(() => {
        const m = {};
        (holidayList || []).forEach(h => { if (h && h.date) m[h.date] = h.name || true; });
        return m;
    }, [holidayList]);

    useEffect(() => {
        // If previously selected month is no longer available, clear selection
        if (selectedMonth && months.length && !months.includes(selectedMonth)) {
            setSelectedMonth("");
        }
    }, [months]);

    // Debug: log timetable counts when month/class/selectedMonth changes
    useEffect(() => {
        try {
            const cls = normalizeClassVal(studentClass);
            const grouped = {};
            (timetable || []).forEach(e => {
                if (!e || !e.date) return;
                if (normalizeClassVal(e.class) !== cls) return;
                const m = e.date.slice(0,7);
                grouped[m] = (grouped[m] || 0) + 1;
            });
            console.log('[TIMETABLE DEBUG] studentClass=', studentClass, 'selectedMonth=', selectedMonth);
            console.log('[TIMETABLE DEBUG] counts per month for this class:', grouped);
            if (selectedMonth) {
                const filtered = (timetable || []).filter(e => normalizeClassVal(e.class) === cls && e.date && e.date.startsWith(selectedMonth));
                console.log('[TIMETABLE DEBUG] entries for selectedMonth sample:', filtered.slice(0,5));
            }
        } catch (e) {
            console.warn('Timetable debug log failed', e);
        }
    }, [timetable, studentClass, selectedMonth]);
    const studentId = localStorage.getItem("user_id");
    
    // Fetch holidays
    useEffect(() => {
        const fetchHolidays = async () => {
            try {
                console.log('📡 Fetching holidays...');
                const response = await api.get("/holidays");
                console.log(`✓ Received ${response.data.length} holidays from database`);
                setHolidayList(response.data || []);
            } catch (error) {
                console.error("Error fetching holidays:", error);
                setHolidayList([]);
            }
        };
        fetchHolidays();
    }, []);

    // Debug: Log what's in localStorage
    console.log('🔍 localStorage values:');
    console.log(`   user_id: ${studentId}`);
    console.log(`   student_class: ${studentClass}`);

    // Fetch student details
    useEffect(() => {
        const fetchStudentDetails = async () => {
            try {
                if (!studentId) {
                    console.warn('⚠️ No student ID found in localStorage');
                    return;
                }
                console.log(`👤 Fetching student details for ID: ${studentId}`);
                const response = await api.get(`/students?_t=${Date.now()}`);
                console.log(`✓ Received ${response.data.length} students from database`);
                console.log('📋 All students:', response.data);
                
                const students = response.data || [];
                const student = students.find(s => {
                    console.log(`Checking student ID: ${s.id} (type: ${typeof s.id}) vs searchId: ${studentId} (type: ${typeof studentId})`);
                    return s.id === parseInt(studentId);
                });
                
                if (student) {
                    console.log(`✓ FOUND STUDENT:`, student);
                    console.log(`   Name: ${student.name}`);
                    console.log(`   Email: ${student.email}`);
                    console.log(`   Roll No: ${student.rollno}`);
                    setStudentDetails(student);
                    // ensure studentClass is derived from student record (DB may store class as '6' etc.)
                    if (student.class) {
                        const cls = String(student.class).trim();
                        setStudentClass(cls);
                        try { localStorage.setItem('student_class', cls); } catch (e) {}
                    }
                } else {
                    console.warn(`⚠️ Student with ID ${studentId} not found in database`);
                    console.log('📊 Available IDs:', students.map(s => `${s.id}(${typeof s.id})`));
                }
            } catch (error) {
                console.error("❌ Error fetching student details:", error);
            }
        };
        if (studentId) {
            fetchStudentDetails();
        }
    }, [studentId]);

    // Fetch timetable with real-time updates
    useEffect(() => {
        const fetchTimetable = async () => {
            try {
                setLoading(true);
                console.log('📡 Auto-refresh: Fetching timetable from database...');
                const response = await api.get(`/timetable?_t=${Date.now()}`);
                console.log(`✓ Auto-refresh: Got ${response.data.length} entries from database`);
                const classData = (response.data || []).filter(entry => normalizeClassVal(entry.class) === normalizeClassVal(studentClass));
                setTimetable(classData);
                setLastUpdated(new Date());
                
                const selectedDateStr = formatDate(selectedDate);
                const selectedDateEntries = classData.filter(entry => entry.date === selectedDateStr);
                setTodayClasses(selectedDateEntries);
            } catch (error) {
                console.error("Error fetching timetable:", error);
                setTimetable([]);
                setTodayClasses([]);
            } finally {
                setLoading(false);
            }
        };

        fetchTimetable();
        
        const interval = setInterval(() => {
            console.log('⏱️ 30-second auto-refresh triggered...');
            fetchTimetable();
        }, 30000);

        return () => clearInterval(interval);
    }, [studentClass, selectedDate]);

    const getWeekStart = (date) => {
        const d = new Date(date);
        const day = d.getDay();
        const diff = d.getDate() - day + (day === 0 ? -6 : 1);
        return new Date(d.setDate(diff));
    };

    useEffect(() => {
        if (!selectedMonth) return;
        const parts = selectedMonth.split('-');
        if (parts.length !== 2) return;
        const y = parseInt(parts[0], 10);
        const m = parseInt(parts[1], 10);
        if (Number.isNaN(y) || Number.isNaN(m)) return;
        const firstOfMonth = new Date(y, m - 1, 1);
        setSelectedDate(firstOfMonth);
        setCurrentWeekStart(getWeekStart(firstOfMonth));
    }, [selectedMonth]);

    const formatDate = (date) => {
        const d = new Date(date);
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        return `${yyyy}-${mm}-${dd}`;
    };

    const getDayName = (date) => {
        return date.toLocaleString('default', { weekday: 'short' });
    };

    const normalizeClassVal = (v) => {
        if (v === undefined || v === null) return '';
        let s = String(v).toLowerCase().trim();
        s = s.replace(/^class\s*/i, '').trim();
        return s;
    };

    // Parse various time formats and return start time {hh, mm} or null
    const parseStartTime = (timeStr) => {
        if (!timeStr) return null;
        // Examples supported: "HH:MM", "HH:MM-HH:MM", "HH-HH", "12-1", "12:00 - 13:00"
        try {
            // extract first occurrence of hours and optional minutes
            const m = timeStr.match(/(\d{1,2})(?::(\d{2}))?/);
            if (!m) return null;
            const hh = parseInt(m[1], 10);
            const mm = m[2] ? parseInt(m[2], 10) : 0;
            // normalize 12-hour shorthand like "1" -> 13? We assume 24h input or school uses 8-17
            return { hh, mm };
        } catch (e) {
            return null;
        }
    };

    const formatTime = ({ hh, mm }) => {
        if (hh === undefined || mm === undefined) return '';
        return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`;
    };

    const handlePreviousWeek = () => {
        const newDate = new Date(currentWeekStart);
        newDate.setDate(newDate.getDate() - 7);
        setCurrentWeekStart(newDate);
    };

    const handleNextWeek = () => {
        const newDate = new Date(currentWeekStart);
        newDate.setDate(newDate.getDate() + 7);
        setCurrentWeekStart(newDate);
    };

    const handleCurrentWeek = () => {
        setCurrentWeekStart(getWeekStart(new Date()));
    };

    const handlePreviousDay = () => {
        const newDate = new Date(selectedDate);
        newDate.setDate(newDate.getDate() - 1);
        setSelectedDate(newDate);
    };

    const handleToday = () => {
        setSelectedDate(new Date());
    };

    const handleNextDay = () => {
        const newDate = new Date(selectedDate);
        newDate.setDate(newDate.getDate() + 1);
        setSelectedDate(newDate);
    };

    const handleRefresh = async () => {
        try {
            setLoading(true);
            console.log('🔄 Refresh: Calling API to fetch fresh timetable from database...');
            const response = await api.get(`/timetable?_t=${Date.now()}`);
            console.log(`✓ Refresh: Received ${response.data.length} entries from database`);
            const classData = (response.data || []).filter(entry => normalizeClassVal(entry.class) === normalizeClassVal(studentClass));
            setTimetable(classData);
            setLastUpdated(new Date());
            console.log(`✓ Refresh: Filtered to ${classData.length} entries for class ${studentClass}`);
            
            const selectedDateStr = formatDate(selectedDate);
            const selectedDateEntries = classData.filter(entry => entry.date === selectedDateStr);
            setTodayClasses(selectedDateEntries);
            console.log(`✓ Refresh: Found ${selectedDateEntries.length} classes for selected date`);
        } catch (error) {
            console.error("Error fetching timetable:", error);
        } finally {
            setLoading(false);
        }
    };

    // Listen for admin-triggered updates and refresh immediately
    useEffect(() => {
        const onDataUpdated = () => {
            console.log('🔔 Student dashboard received data-updated; refreshing timetable now');
            try { handleRefresh(); } catch (e) { console.warn('Refresh failed', e); }
        };
        window.addEventListener('data-updated', onDataUpdated);
        return () => window.removeEventListener('data-updated', onDataUpdated);
    }, [handleRefresh]);

    const isClassUpcoming = (classTime) => {
        try {
            const parsed = parseStartTime(classTime);
            if (!parsed) return false;
            const now = new Date();
            const classDateTime = new Date();
            classDateTime.setHours(parsed.hh, parsed.mm || 0, 0, 0);
            return classDateTime > now && classDateTime - now <= 3600000;
        } catch (e) {
            return false;
        }
    };

    return (
        <div style={{ padding: "20px", fontFamily: "Arial, sans-serif", backgroundColor: "#f5f5f5", minHeight: "100vh" }}>
            {/* Top Header with Student Info */}
            <div style={{ backgroundColor: "#fff", padding: "10px 16px", marginBottom: "20px", borderRadius: "8px", boxShadow: "0 2px 8px rgba(0,0,0,0.1)", background: 'linear-gradient(135deg, #2196F3 0%, #1976D2 100%)', color: 'white' }}>
                {/* Top navbar: show only student email and logout button */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ fontSize: '14px', opacity: 0.95 }}>📧 {studentDetails?.email || '...'}</div>
                    <div>
                        <button
                            onClick={() => {
                                try { localStorage.clear(); } catch (e) {}
                                window.location.href = '/login';
                            }}
                            style={{
                                padding: '8px 12px',
                                backgroundColor: '#fff',
                                color: '#1976D2',
                                border: 'none',
                                borderRadius: '6px',
                                cursor: 'pointer',
                                fontWeight: '700'
                            }}
                        >
                            🔒 Logout
                        </button>
                    </div>
                </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '30px' }}>
                <div>
                    <h2 style={{ color: "#333", margin: 0, marginBottom: '5px' }}>📚 Your Schedule</h2>
                    <p style={{ color: '#999', margin: 0 }}>Daily schedule & timetable management</p>
                </div>
                <button 
                    onClick={handleRefresh}
                    style={{ 
                        padding: "10px 16px", 
                        backgroundColor: "#2196F3", 
                        color: "white", 
                        border: "none", 
                        borderRadius: "6px", 
                        cursor: "pointer",
                        fontWeight: "bold",
                        fontSize: '14px'
                    }}
                >
                    🔄 Refresh Now
                </button>
            </div>

            {/* Student Profile Card */}
            {Object.keys(studentDetails).length > 0 && (
                <div style={{ backgroundColor: "#fff", padding: "20px", marginBottom: "20px", borderRadius: "8px", boxShadow: "0 2px 8px rgba(0,0,0,0.1)", background: 'linear-gradient(135deg, #4CAF50 0%, #45a049 100%)', color: 'white' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '20px' }}>
                        <div>
                            <div style={{ fontSize: '12px', opacity: '0.9', marginBottom: '4px' }}>Student Name</div>
                            <div style={{ fontSize: '20px', fontWeight: '700' }}>{studentDetails.name}</div>
                        </div>
                        <div>
                            <div style={{ fontSize: '12px', opacity: '0.9', marginBottom: '4px' }}>Class</div>
                            <div style={{ fontSize: '20px', fontWeight: '700' }}>{studentClass}</div>
                        </div>
                        <div>
                            <div style={{ fontSize: '12px', opacity: '0.9', marginBottom: '4px' }}>Roll Number</div>
                            <div style={{ fontSize: '20px', fontWeight: '700' }}>{studentDetails.rollno}</div>
                        </div>
                    </div>
                    <div style={{ marginTop: '15px', borderTop: '1px solid rgba(255,255,255,0.3)', paddingTop: '15px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                        <div>
                            <div style={{ fontSize: '12px', opacity: '0.9' }}>📧 Email</div>
                            <div style={{ fontSize: '14px' }}>{studentDetails.email}</div>
                        </div>
                        <div>
                            <div style={{ fontSize: '12px', opacity: '0.9' }}>🆔 Student ID</div>
                            <div style={{ fontSize: '14px' }}>ID: {studentDetails.id}</div>
                        </div>
                    </div>
                </div>
            )}

            {/* Last Updated and Info */}
            <div style={{ backgroundColor: "#e3f2fd", padding: "12px 16px", borderRadius: "6px", marginBottom: "20px", display: "flex", justifyContent: "space-between", alignItems: "center", border: '1px solid #90caf9' }}>
                <div>
                    <span style={{ fontWeight: '600' }}>⏱️ Last Updated:</span> {lastUpdated.toLocaleTimeString()}
                </div>
            </div>

            {/* Day-wise Classes Section */}
            <div style={{ backgroundColor: "#fff", padding: "20px", marginBottom: "20px", borderRadius: "8px", boxShadow: "0 2px 8px rgba(0,0,0,0.1)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px", flexWrap: 'wrap', gap: '15px' }}>
                    <h2 style={{ color: "#2196F3", margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>📅 {new Date(selectedDate).toLocaleString('default', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</h2>
                    <div style={{ display: 'flex', gap: '8px' }}>
                        <button onClick={handlePreviousDay} style={{ padding: "8px 12px", borderRadius: "6px", border: "2px solid #2196F3", backgroundColor: "#fff", color: "#2196F3", cursor: "pointer", fontWeight: '600' }}>← Yesterday</button>
                        <button onClick={handleToday} style={{ padding: "8px 12px", borderRadius: "6px", border: "2px solid #4CAF50", backgroundColor: "#fff", color: "#4CAF50", cursor: "pointer", fontWeight: '600' }}>📍 Today</button>
                        <button onClick={handleNextDay} style={{ padding: "8px 12px", borderRadius: "6px", border: "2px solid #2196F3", backgroundColor: "#fff", color: "#2196F3", cursor: "pointer", fontWeight: '600' }}>Tomorrow →</button>
                    </div>
                </div>
                
                {/* Render fixed hourly slots for the day and show Break/Free when no entry */}
                {(() => {
                    if (!selectedMonth) {
                        return (
                            <div style={{ padding: '20px', textAlign: 'center', color: '#666', backgroundColor: '#fafafa', borderRadius: '6px', border: '1px dashed #e0e0e0' }}>Please select a month to view the timetable.</div>
                        );
                    }
                    const selDateStr = formatDate(selectedDate);
                    const selDateObj = new Date(selDateStr);
                    if (selDateObj.getDay() === 0) {
                        return (
                            <div style={{ padding: '20px', textAlign: 'center', color: '#333', backgroundColor: '#fff3e0', borderRadius: '6px', border: '2px solid #FF9800' }}>No classes — Sunday</div>
                        );
                    }
                    if (holidayMap[selDateStr]) {
                        return (
                            <div style={{ padding: '20px', textAlign: 'center', color: '#333', backgroundColor: '#fff3e0', borderRadius: '6px', border: '2px solid #FF9800' }}>No classes — Holiday: {holidayMap[selDateStr] === true ? 'Holiday' : holidayMap[selDateStr]}</div>
                        );
                    }
                    const SLOTS = ['08:00','09:00','10:00','11:00','12:00','13:00','14:00','15:00'];
                    const classData = (timetable || []).filter(entry => normalizeClassVal(entry.class) === normalizeClassVal(studentClass) && entry.date === selDateStr && entry.date && entry.date.startsWith(selectedMonth));
                    const slotRows = SLOTS.map(slot => {
                        const match = classData.find(e => {
                            const parsed = parseStartTime(e.time);
                            if (!parsed) return false;
                            const t = `${String(parsed.hh).padStart(2,'0')}:${String(parsed.mm || 0).padStart(2,'0')}`;
                            return t === slot;
                        });
                        return { slot, entry: match };
                    });

                    return (
                        <div>
                            {slotRows.map((row, idx) => (
                                <div key={idx} style={{ padding: '12px', marginBottom: '10px', backgroundColor: row.entry ? (isClassUpcoming(row.entry.time) ? '#fff3e0' : '#fff') : '#f9f9f9', borderRadius: '8px', border: '1px solid #e0e0e0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <div>
                                        <strong style={{ fontSize: '15px', color: '#333' }}>{row.entry ? `📚 ${row.entry.subject}` : (row.slot === '12:00' ? '☕ Break' : '— Free')}</strong>
                                        <div style={{ color: '#666', marginTop: '6px', fontSize: '13px' }}>{row.entry ? `⏰ ${row.entry.time} • 📍 ${row.entry.room || row.entry.classroom || '—'} • 👨‍🏫 ${row.entry.faculty || row.entry.teacher_name || '—'}` : `${row.slot}`}</div>
                                    </div>
                                    {row.entry && isClassUpcoming(row.entry.time) && (
                                        <span style={{ backgroundColor: '#FF9800', color: 'white', padding: '8px 12px', borderRadius: '6px', fontWeight: '700' }}>⚡ UPCOMING</span>
                                    )}
                                </div>
                            ))}
                        </div>
                    );
                })()}
            </div>

            {/* Weekly Timetable */}
            <div style={{ backgroundColor: "#fff", padding: "20px", borderRadius: "8px", boxShadow: "0 2px 8px rgba(0,0,0,0.1)", marginBottom: "20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px", flexWrap: 'wrap', gap: '15px' }}>
                    <h2 style={{ color: "#2196F3", margin: 0 }}>📅 Weekly Timetable</h2>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <select value={selectedMonth} onChange={(e) => setSelectedMonth(e.target.value)} style={{ padding: '8px 10px', borderRadius: '6px', border: '1px solid #ccc', backgroundColor: '#fff', cursor: 'pointer' }}>
                            <option value="">Select month</option>
                            {months.map(m => (
                                <option key={m} value={m}>{new Date(m + '-01').toLocaleString('default', { month: 'long', year: 'numeric' })}</option>
                            ))}
                        </select>
                        <button onClick={handlePreviousWeek} style={{ padding: "8px 12px", borderRadius: "6px", border: "2px solid #2196F3", backgroundColor: "#fff", color: "#2196F3", cursor: "pointer", fontWeight: '600' }}>← Previous Week</button>
                        <button onClick={handleCurrentWeek} style={{ padding: "8px 12px", borderRadius: "6px", border: "2px solid #4CAF50", backgroundColor: "#fff", color: "#4CAF50", cursor: "pointer", fontWeight: '600' }}>📍 This Week</button>
                        <button onClick={handleNextWeek} style={{ padding: "8px 12px", borderRadius: "6px", border: "2px solid #2196F3", backgroundColor: "#fff", color: "#2196F3", cursor: "pointer", fontWeight: '600' }}>Next Week →</button>
                    </div>
                </div>
                
                {(!selectedMonth) ? (
                    <p style={{ textAlign: 'center', color: '#999', padding: '20px' }}>Please select a month to view the weekly timetable.</p>
                ) : loading ? (
                    <p style={{ textAlign: "center", color: "#999", padding: '20px' }}>⏳ Loading timetable...</p>
                ) : timetable.length > 0 ? (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(120px, 1fr))', gap: '8px', paddingBottom: '12px' }}>
                        {Array.from({ length: 7 }).map((_, dayIndex) => {
                            const dayDate = new Date(currentWeekStart);
                            dayDate.setDate(dayDate.getDate() + dayIndex);
                            const dayDateStr = formatDate(dayDate);
                            const today = formatDate(new Date());
                            const isSunday = dayDate.getDay() === 0;
                            const isHoliday = Boolean(holidayMap[dayDateStr]);
                            let dayClasses = [];
                            if (!isSunday && !isHoliday) {
                                // Show classes for the exact day regardless of selectedMonth so week columns are complete
                                dayClasses = (timetable || []).filter(entry => normalizeClassVal(entry.class) === normalizeClassVal(studentClass) && entry.date === dayDateStr);
                            }
                            
                            return (
                                <div
                                    key={dayIndex}
                                    style={{
                                            width: '100%',
                                            backgroundColor: isHoliday || isSunday ? '#fff3e0' : (dayDateStr === today ? '#fff3e0' : '#f9f9f9'),
                                            border: isHoliday || isSunday ? '2px solid #FF9800' : (dayDateStr === today ? '2px solid #FF9800' : '1px solid #e0e0e0'),
                                            borderRadius: '8px',
                                            padding: '15px',
                                            boxShadow: '0 2px 4px rgba(0,0,0,0.05)'
                                        }}
                                >
                                    <h3 style={{ margin: '0 0 6px 0', color: '#333', fontSize: '16px', fontWeight: '700', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        {getDayName(dayDate)}, {dayDate.getDate()}
                                        {dayDateStr === today && <span style={{ backgroundColor: '#FF9800', color: 'white', padding: '4px 8px', borderRadius: '4px', fontSize: '12px', fontWeight: '600' }}>📌 Today</span>}
                                    </h3>
                                    {isHoliday && (
                                        <div style={{ margin: '0 0 8px 0', color: '#bf360c', fontWeight: '700', fontSize: '13px' }}>🏖️ {holidayMap[dayDateStr] === true ? 'Holiday' : holidayMap[dayDateStr]}</div>
                                    )}
                                    {dayClasses.length > 0 ? (
                                        <div>
                                            {dayClasses.map((classEntry, idx) => (
                                                <div 
                                                    key={idx}
                                                    style={{ 
                                                        padding: '10px', 
                                                        marginBottom: '10px', 
                                                        backgroundColor: '#fff',
                                                        borderLeft: '4px solid #2196F3',
                                                        borderRadius: '4px',
                                                        fontSize: '13px'
                                                    }}
                                                >
                                                    <strong style={{ color: '#333' }}>{classEntry.subject}</strong>
                                                    <div style={{ color: '#666', marginTop: '4px' }}>⏰ {classEntry.time}</div>
                                                    <div style={{ color: '#666', marginTop: '2px' }}>👨‍🏫 {classEntry.faculty}</div>
                                                    <div style={{ color: '#666', marginTop: '2px' }}>📍 {classEntry.room}</div>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <p style={{ color: '#999', fontSize: '13px', margin: 0, fontStyle: 'italic' }}>No classes</p>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                ) : (
                    <p style={{ textAlign: "center", color: "#999", fontStyle: "italic", padding: '20px', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>No timetable entries for this week</p>
                )}
            </div>

            {/* Live Update Indicator */}
            <div style={{ textAlign: "center", marginTop: "20px", color: "#999", fontSize: "12px" }}>
                <p>🔄 Timetable updates automatically every 30 seconds</p>
            </div>

            {/* Holidays List */}
            <div style={{ backgroundColor: "#fff", padding: "20px", borderRadius: "8px", boxShadow: "0 2px 8px rgba(0,0,0,0.1)", marginBottom: "20px", marginTop: "30px" }}>
                <h2 style={{ color: "#FF6F00", margin: "0 0 20px 0" }}>🏖️ School Holidays</h2>
                {holidayList.length > 0 ? (
                    <div style={{ overflowX: "auto" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse" }}>
                            <thead>
                                <tr style={{ backgroundColor: "#FF6F00", color: "white" }}>
                                    <th style={{ padding: "12px", textAlign: "left", border: "1px solid #ddd" }}>Date</th>
                                    <th style={{ padding: "12px", textAlign: "left", border: "1px solid #ddd" }}>Holiday Name</th>
                                </tr>
                            </thead>
                            <tbody>
                                {holidayList.map((holiday, idx) => {
                                    const holidayDate = new Date(holiday.date);
                                    const today = new Date();
                                    const isOncoming = holidayDate > today && holidayDate - today <= 7 * 24 * 60 * 60 * 1000;
                                    
                                    return (
                                        <tr key={idx} style={{ backgroundColor: isOncoming ? "#fff3e0" : idx % 2 === 0 ? "#fff" : "#f9f9f9" }}>
                                            <td style={{ padding: "12px", border: "1px solid #ddd" }}>🗓️ {holiday.date}</td>
                                            <td style={{ padding: "12px", border: "1px solid #ddd" }}>
                                                {holiday.name}
                                                {isOncoming && <span style={{ color: "#FF6F00", fontWeight: "bold", marginLeft: "10px" }}>(Upcoming!)</span>}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <p style={{ color: "#999", fontStyle: "italic", padding: "20px", textAlign: "center", backgroundColor: "#f5f5f5", borderRadius: "4px" }}>No holidays scheduled</p>
                )}
            </div>
        </div>
    );
}

export default StudentDashboard;
