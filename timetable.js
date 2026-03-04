import { useState, useEffect, useCallback } from "react";
import api from "../api";

function Timetable() {
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState("");

    // Timetable Generation
    const [timetableMonth, setTimetableMonth] = useState(new Date().getMonth() + 1);
    const [timetableYear, setTimetableYear] = useState(new Date().getFullYear());
    const [timetableGenerated, setTimetableGenerated] = useState(false);
    const [timetableExists, setTimetableExists] = useState(false); // Track if timetable exists for this month

    // Holidays Management
    const [allHolidays, setAllHolidays] = useState([]); // All holidays from admin dashboard
    const [selectedHolidayIds, setSelectedHolidayIds] = useState(new Set()); // Selected holiday checkboxes
    const [previewHolidays, setPreviewHolidays] = useState([]);
    const [unassignedInfo, setUnassignedInfo] = useState(null); // {unassigned_count, sample_unassigned}

    // Timetable List
    const [timetableList, setTimetableList] = useState([]);
    const [timetableClassFilter, setTimetableClassFilter] = useState("");
    const [classesList, setClassesList] = useState([]);
    const [selectedMonth, setSelectedMonth] = useState(null); // For month dropdown
    const [availableMonths, setAvailableMonths] = useState([]); // Available months from backend
    // Normalize a date to midnight (date-only) for reliable comparisons
    const normalizeDate = (d) => {
        if (!d) return d;
        const n = new Date(d);
        n.setHours(0, 0, 0, 0);
        n.setMilliseconds(0);
        return n;
    };

    const [weekStart, setWeekStart] = useState(() => {
        const today = new Date();
        const day = today.getDay();
        const diff = -day; // Sunday as start
        const start = new Date(today);
        start.setDate(today.getDate() + diff);
        start.setHours(0, 0, 0, 0);
        return normalizeDate(start);
    });

    const fetchAvailableMonths = async () => {
        try {
            const response = await api.get("/timetable-months");
            setAvailableMonths(response.data || []);
            console.log("✓ Available months loaded:", response.data);
        } catch (error) {
            console.error("❌ Error fetching available months:", error);
            setAvailableMonths([]);
        }
    };

    const fetchHolidays = async () => {
        try {
            console.log("📡 Fetching holidays...");
            const response = await api.get("/holidays");
            setAllHolidays(response.data || []);
            console.log("✓ Holidays loaded:", response.data);
        } catch (error) {
            console.error("❌ Error fetching holidays:", error);
            setAllHolidays([]);
        }
    };

    const fetchTimetable = async () => {
        try {
            const response = await api.get("/timetable");
            setTimetableList(response.data || []);
            console.log("✓ Timetable data loaded:", response.data);
            // Refresh available months after fetching timetable
            await fetchAvailableMonths();
        } catch (error) {
            console.error("❌ Error fetching timetable:", error);
            setMessage("Error loading timetable: " + error.message);
            setTimetableList([]);
        }
    };

    const fetchClasses = async () => {
        try {
            const response = await api.get('/classes');
            setClassesList(response.data || []);
            console.log('✓ Classes loaded:', response.data);
        } catch (error) {
            console.error('❌ Error fetching classes:', error);
            setClassesList([]);
        }
    };
    useEffect(() => {
        fetchTimetable();
        fetchAvailableMonths();
        fetchHolidays();
        fetchClasses();
    }, []);

    // Listen for global updates (admin actions) and refresh timetable/holidays accordingly
    useEffect(() => {
        const handler = () => {
            console.log('🔔 Received global data-updated event, refreshing timetable and holidays...');
            if (selectedMonth) {
                fetchMonthTimetable(selectedMonth).catch(() => {});
            } else {
                fetchTimetable().catch(() => {});
            }
            fetchHolidays().catch(() => {});
        };
        window.addEventListener('data-updated', handler);
        return () => window.removeEventListener('data-updated', handler);
    }, [selectedMonth]);

    // Auto-clear messages after 5 seconds
    useEffect(() => {
        if (message) {
            const timer = setTimeout(() => {
                setMessage("");
            }, 5000);
            return () => clearTimeout(timer);
        }
    }, [message]);

    const formatDate = (date) => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, "0");
        const day = String(date.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    };

    // Helper function to get month-year key from date
    const getMonthKey = (date) => {
        const months = ["January", "February", "March", "April", "May", "June", 
                        "July", "August", "September", "October", "November", "December"];
        return `${months[date.getMonth()]} ${date.getFullYear()}`;
    };

    // Helper function to handle week navigation while preserving month selection
    const handleWeekNavigation = (newWeekStart) => {
        const normalized = normalizeDate(newWeekStart);
        setWeekStart(normalized);
        // Only clear selectedMonth if we're moving to a different month
        const newMonthKey = getMonthKey(normalized);
        if (selectedMonth && newMonthKey !== selectedMonth) {
            setSelectedMonth(null);
        }
    };

    const fetchMonthTimetable = async (monthLabel) => {
        try {
            console.log("📂 Fetching timetable for month:", monthLabel);
            const response = await api.get(`/timetable-month/${encodeURIComponent(monthLabel)}`);
            const data = response.data;
            
            // Handle both array and dict responses
            let timetableData = Array.isArray(data) ? data : (data && typeof data === 'object' ? Object.values(data) : []);
            
            // Normalize class labels in timetable entries to match dropdown format
            const normalizeLocal = (val) => {
                if (val === null || val === undefined) return null;
                const s = String(val).trim();
                const m = s.match(/^\s*class\s*(\d+)\s*$/i);
                if (m) return `Class ${m[1]}`;
                const m2 = s.match(/^(\d+)$/);
                if (m2) return `Class ${m2[1]}`;
                return s || null;
            };

            const normalizedData = timetableData.map(e => ({ ...e, class: normalizeLocal(e.class) }));
            setTimetableList(normalizedData);
            console.log("✓ Month timetable loaded:", monthLabel, "Entries:", timetableData.length);
            setMessage(`✓ Loaded ${timetableData.length} entries for ${monthLabel}`);
            // If no class filter selected, default to first available class for this month
            if ((!timetableClassFilter || timetableClassFilter === "") && normalizedData.length > 0) {
                const firstCls = normalizedData.map(x => x.class).find(Boolean);
                if (firstCls) setTimetableClassFilter(firstCls);
            }
        } catch (error) {
            console.error("❌ Error fetching month timetable:", error);
            const errorMsg = error.response?.data?.error || error.message;
            const availableFiles = error.response?.data?.available_files;
            let fullMsg = `Error loading timetable for ${monthLabel}: ${errorMsg}`;
            if (availableFiles && availableFiles.length > 0) {
                fullMsg += ` (Available: ${availableFiles.join(", ")})`;
            }
            setMessage(fullMsg);
            setTimetableList([]);
        }
    };

    const refreshTimetableHolidays = async () => {
        try {
            setLoading(true);
            console.log("🔄 Refreshing timetable and verifying holidays...");
            const response = await api.post("/timetable/refresh");
            setMessage(`✓ ${response.data.message} ${response.data.total_adjustments > 0 ? `(${response.data.total_adjustments} classes adjusted)` : ''}`);
            // Reload timetable: if a month is selected, reload that month specifically
            if (selectedMonth) {
                await fetchMonthTimetable(selectedMonth);
            } else {
                await fetchTimetable();
            }
        } catch (error) {
            console.error("❌ Error refreshing timetable:", error);
            setMessage("Error refreshing timetable: " + (error.response?.data?.message || error.message));
        } finally {
            setLoading(false);
        }
    };

    // Filter holidays by selected month and year
    const getFilteredHolidaysForMonth = () => {
        return allHolidays.filter(holiday => {
            if (!holiday.date) return false;
            // Extract YYYY-MM from date
            const [year, month] = holiday.date.split('-');
            return parseInt(year) === parseInt(timetableYear) && parseInt(month) === parseInt(timetableMonth);
        });
    };
    // Get selected holidays for generation
    const getSelectedHolidaysForGeneration = () => {
        const filteredHolidays = getFilteredHolidaysForMonth();
        const holidays = [];
        selectedHolidayIds.forEach(uniqueId => {
            // Try to find by _id or id first
            let holiday = filteredHolidays.find(h => h._id === uniqueId || h.id === uniqueId);
            
            // If not found, try to extract date from the uniqueId (format: holiday-YYYY-MM-DD-index)
            if (!holiday && uniqueId.startsWith('holiday-')) {
                const dateMatch = uniqueId.match(/holiday-([\d-]+)-\d+$/);
                if (dateMatch) {
                    const dateStr = dateMatch[1];
                    holiday = filteredHolidays.find(h => h.date === dateStr);
                }
            }
            
            if (holiday) {
                holidays.push({
                    date: holiday.date,
                    name: holiday.name || 'Holiday'
                });
            }
        });
        return holidays;
    };

    // Check if timetable exists for the selected month
    const checkTimetableExists = useCallback(async () => {
        try {
            const response = await api.get(`/check-timetable-exists?month=${timetableMonth}&year=${timetableYear}`);
            console.log("📊 Timetable existence check:", response.data);
            setTimetableExists(response.data.exists);
            return response.data.exists;
        } catch (error) {
            console.error("❌ Error checking timetable existence:", error);
            setTimetableExists(false);
            return false;
        }
    }, [timetableMonth, timetableYear]);

    // Check timetable existence when month/year changes
    useEffect(() => {
        checkTimetableExists();
    }, [checkTimetableExists]);

    // Generate timetable (if save=true will persist grouped by month)
    const handleGenerateTimetable = async (save = false, overwrite = false) => {
        try {
            setLoading(true);
            const holidays = getSelectedHolidaysForGeneration();
            console.log("🎓 Generating timetable with holidays:", holidays, "Overwrite:", overwrite);
            const response = await api.post("/generate-timetable", { 
                month: timetableMonth, 
                year: timetableYear, 
                holidays, 
                save,
                overwrite
            });
            // Clear any previous unassigned info
            setUnassignedInfo(null);
            let msg = "✓ Timetable " + (overwrite ? "updated" : "generated") + " successfully! (" + response.data?.count + " entries)";
            if (response.data?.monthly_file_saved) {
                msg += " - Monthly file saved as " + response.data.monthly_file_saved;
            }
            setMessage(msg);
            setTimetableGenerated(true);
            setTimetableList(response.data?.data || []);
            setPreviewHolidays(response.data?.holidays || holidays);
            // If saved to main timetable, refresh server-side lists
            if (save) {
                setMessage("✓ Timetable saved successfully as " + response.data?.saved_as + " (and monthly file: " + response.data?.monthly_file_saved + ")");
                await fetchTimetable();
                setTimetableExists(true); // Mark as existing after generation
            }
        } catch (error) {
            // Check if it's a 409 Conflict (timetable already exists or unassigned slots)
            if (error.response?.status === 409) {
                // If backend returned unassigned info, surface it to user
                const data = error.response?.data || {};
                if (data.unassigned_count !== undefined) {
                    setUnassignedInfo({
                        unassigned_count: data.unassigned_count,
                        sample_unassigned: data.sample_unassigned || []
                    });
                    setMessage(`⚠️ Generated timetable has ${data.unassigned_count} unassigned slots — save aborted.`);
                } else {
                    setMessage("⚠️ Timetable already exists for this month. Use the Update button to regenerate it.");
                }
            } else {
                setMessage("❌ Error generating timetable: " + (error.message || error));
            }
        } finally {
            setLoading(false);
        }
    };

    const tabStyle = {
        padding: "20px",
        backgroundColor: "#fff",
        borderRadius: "8px",
        marginBottom: "20px",
        boxShadow: "0 2px 4px rgba(0,0,0,0.1)"
    };

    

    // Normalize and merge classes from DB collection and timetable entries to avoid duplicates
    const normalizeClassLabel = (val) => {
        if (val === null || val === undefined) return null;
        const s = String(val).trim();
        const m = s.match(/^\s*class\s*(\d+)\s*$/i);
        if (m) return `Class ${m[1]}`;
        const m2 = s.match(/^(\d+)$/);
        if (m2) return `Class ${m2[1]}`;
        return s || null;
    };

    const classesFromTimetable = Array.isArray(timetableList)
        ? Array.from(new Set(timetableList.map(t => normalizeClassLabel(t.class)).filter(Boolean)))
        : [];

    const classesFromCollection = Array.isArray(classesList)
        ? Array.from(new Set(classesList.map(c => normalizeClassLabel(c.display || c.label || c.name)).filter(Boolean)))
        : [];

    const mergedClasses = Array.from(new Set([...classesFromCollection, ...classesFromTimetable]));
    // Sort numerically when possible (Class 6, Class 7, ...), otherwise alphabetically
    mergedClasses.sort((a, b) => {
        const na = (a.match(/Class\s*(\d+)/i) || [null, null])[1];
        const nb = (b.match(/Class\s*(\d+)/i) || [null, null])[1];
        if (na && nb) return parseInt(na, 10) - parseInt(nb, 10);
        if (na) return -1;
        if (nb) return 1;
        return a.localeCompare(b);
    });

    // Get first week of selected month (Sunday-based)
    const getFirstWeekOfMonth = (yearMonth) => {
        if (!yearMonth) return null;
        // Parse "Month Year" format from the backend
        const monthNameMap = {
            'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
            'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12
        };
        
        const parts = yearMonth.split(' ');
        const monthName = parts[0];
        const year = parseInt(parts[1]);
        const month = monthNameMap[monthName];
        
        if (!month || !year) return null;
        
        // Get the 1st of the month, then find the Sunday of that week
        const firstDay = new Date(year, month - 1, 1);
        const dayOfWeek = firstDay.getDay();
        const diff = -dayOfWeek; // Get to Sunday of that week
        firstDay.setDate(1 + diff);
        firstDay.setHours(0, 0, 0, 0);
        return firstDay;
    };

    // Helper: Extract month/year from selected month string "Month Year"
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

    // Helper: Navigate to previous week while staying in selected month
    const navigateToPreviousWeek = () => {
        const prev = normalizeDate(new Date(weekStart));
        prev.setDate(prev.getDate() - 7);

        // If a month is selected, ensure we stay within it
        if (selectedMonth) {
            const firstWeekRaw = getFirstWeekOfMonth(selectedMonth);
            const firstWeek = firstWeekRaw ? normalizeDate(firstWeekRaw) : null;
            if (firstWeek) {
                // If previous week would go before the first_week start, snap to firstWeek
                if (prev.getTime() < firstWeek.getTime()) {
                    handleWeekNavigation(firstWeek);
                    return;
                }
            }
        }
        handleWeekNavigation(prev);
    };

    // Helper: Navigate to next week while staying in selected month
    const navigateToNextWeek = () => {
        const next = normalizeDate(new Date(weekStart));
        next.setDate(next.getDate() + 7);

        // If a month is selected, ensure the new week starts within it
        if (selectedMonth) {
            const monthYearData = getMonthYearFromString(selectedMonth);
            if (monthYearData) {
                const lastDayOfMonth = new Date(monthYearData.year, monthYearData.month, 0);
                const lastDayNorm = normalizeDate(lastDayOfMonth);
                // Only prevent if the new week starts after the month ends
                if (next.getTime() > lastDayNorm.getTime()) {
                    return;
                }
            }
        }
        handleWeekNavigation(next);
    };

    // Helper: Get the actual week end, capped at month boundary if month is selected
    const getActualWeekEnd = () => {
        let weekEnd = normalizeDate(new Date(weekStart));
        weekEnd.setDate(weekEnd.getDate() + 6);

        if (selectedMonth) {
            const monthYearData = getMonthYearFromString(selectedMonth);
            if (monthYearData) {
                // Month from getMonthYearFromString is 1-12, but Date constructor needs 0-11
                const lastDayOfMonth = normalizeDate(new Date(monthYearData.year, monthYearData.month, 0));
                if (weekEnd.getTime() > lastDayOfMonth.getTime()) {
                    weekEnd = lastDayOfMonth;
                }
            }
        }
        return weekEnd;
    };

    // Helper: Check if previous week button should be disabled
    const isPreviousWeekDisabled = () => {
        if (!selectedMonth) return false;
        const monthYearData = getMonthYearFromString(selectedMonth);
        if (!monthYearData) return false;
        // Use the computed first week-start (Sunday) so partial first weeks are reachable
        const firstWeekRaw = getFirstWeekOfMonth(selectedMonth);
        if (!firstWeekRaw) return false;
        const firstWeek = normalizeDate(firstWeekRaw);
        const current = normalizeDate(weekStart);
        // Only disable when we're already at the first week (exact match)
        return current.getTime() === firstWeek.getTime();
    };

    // Helper: Check if next week button should be disabled
    const isNextWeekDisabled = () => {
        if (!selectedMonth) return false;
        const monthYearData = getMonthYearFromString(selectedMonth);
        if (!monthYearData) return false;

        const lastDayOfMonth = normalizeDate(new Date(monthYearData.year, monthYearData.month, 0));
        const nextWeekStart = normalizeDate(new Date(weekStart));
        nextWeekStart.setDate(nextWeekStart.getDate() + 7); // Next week's start date
        return nextWeekStart.getTime() > lastDayOfMonth.getTime();
    };

    const buttonStyle = {
        padding: "10px 16px",
        marginRight: "10px",
        borderRadius: "4px",
        border: "none",
        cursor: "pointer",
        fontWeight: "bold",
        marginBottom: "10px"
    };

    const inputStyle = {
        padding: "10px",
        marginRight: "10px",
        marginBottom: "10px",
        border: "1px solid #ddd",
        borderRadius: "4px",
        width: "200px"
    };

    useEffect(() => {
        // Clear timetableClassFilter to show all classes by default
        setTimetableClassFilter("");
    }, []);

    return (
        <div style={{ padding: "20px", fontFamily: "Arial, sans-serif", backgroundColor: "#f5f5f5", minHeight: "100vh" }}>
            <h1 style={{ color: "#333", marginBottom: "20px" }}>📅 Timetable Management</h1>

            {/* Message Display */}
            {message && (
                <div style={{
                    padding: "12px",
                    marginBottom: "20px",
                    backgroundColor: (message.includes("Error") || message.includes("❌")) ? "#f8d7da" : "#d4edda",
                    color: (message.includes("Error") || message.includes("❌")) ? "#721c24" : "#155724",
                    borderRadius: "4px",
                    border: "1px solid " + ((message.includes("Error") || message.includes("❌")) ? "#f5c6cb" : "#c3e6cb"),
                    fontSize: "14px"
                }}>
                    {message}
                </div>
            )}

            {/* Unassigned Slots Warning */}
            {unassignedInfo && (
                <div style={{
                    padding: "15px",
                    marginBottom: "20px",
                    backgroundColor: "#fff3cd",
                    color: "#856404",
                    borderRadius: "4px",
                    border: "1px solid #ffeeba",
                    fontSize: "14px"
                }}>
                    <h3 style={{ margin: "0 0 10px 0", color: "#856404" }}>⚠️ Unassigned Slots Detected</h3>
                    <p style={{ margin: "0 0 10px 0" }}>
                        <strong>Total unassigned slots: {unassignedInfo.unassigned_count}</strong>
                    </p>
                    {unassignedInfo.sample_unassigned && unassignedInfo.sample_unassigned.length > 0 && (
                        <div>
                            <strong>Sample unassigned slots:</strong>
                            <ul style={{ margin: "8px 0 0 0", paddingLeft: "20px" }}>
                                {unassignedInfo.sample_unassigned.map((slot, idx) => (
                                    <li key={idx} style={{ marginBottom: "4px" }}>
                                        {slot.date} at {slot.time} - {slot.subject} ({slot.class})
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                    <p style={{ margin: "10px 0 0 0", fontSize: "12px", fontStyle: "italic" }}>
                        Please adjust class subjects, faculties, or holidays to resolve unassigned slots before saving.
                    </p>
                </div>
            )}

            {/* Generate Monthly Timetable Section */}
            <div id="generateMonthlySection" style={tabStyle}>
                <h2>📆 Generate Monthly Timetable</h2>
                <div style={{ padding: "15px", backgroundColor: "#f9f9f9", borderRadius: "4px" }}>
                    <h3>Select Month and Year</h3>
                    <select
                        value={timetableMonth}
                        onChange={(e) => {
                            setTimetableMonth(e.target.value);
                            setSelectedHolidayIds(new Set()); // Clear selected holidays when month changes
                        }}
                        style={inputStyle}
                    >
                        {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(m => (
                            <option key={m} value={m}>{new Date(2026, m - 1).toLocaleString('default', { month: 'long' })}</option>
                        ))}
                    </select>
                    <select
                        value={timetableYear}
                        onChange={(e) => {
                            setTimetableYear(e.target.value);
                            setSelectedHolidayIds(new Set()); // Clear selected holidays when year changes
                        }}
                        style={inputStyle}
                    >
                        {[2024, 2025, 2026, 2027, 2028].map(y => (
                            <option key={y} value={y}>{y}</option>
                        ))}
                    </select>
                    <br />
                    {/* Holiday Selection */}
                    <div style={{ marginTop: "15px", padding: "15px", backgroundColor: "#f9f9f9", borderRadius: "4px" }}>
                        <h3 style={{ margin: "0 0 15px 0", color: "#333" }}>📅 Select Holidays for {new Date(2026, timetableMonth - 1).toLocaleString('default', { month: 'long' })} {timetableYear}</h3>
                        {getFilteredHolidaysForMonth().length > 0 ? (
                            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))", gap: "10px" }}>
                                {getFilteredHolidaysForMonth().map((holiday, idx) => {
                                    // Create unique identifier using date since _id might not be unique
                                    const uniqueId = holiday._id || holiday.id || `holiday-${holiday.date}-${idx}`;
                                    return (
                                    <div key={uniqueId} style={{ display: "flex", alignItems: "center", gap: "8px", padding: "10px", backgroundColor: "#fff", border: "1px solid #ddd", borderRadius: "4px" }}>
                                        <input
                                            type="checkbox"
                                            id={`holiday-${uniqueId}`}
                                            checked={selectedHolidayIds.has(uniqueId)}
                                            onChange={(e) => {
                                                const newSelected = new Set(selectedHolidayIds);
                                                if (e.target.checked) {
                                                    newSelected.add(uniqueId);
                                                } else {
                                                    newSelected.delete(uniqueId);
                                                }
                                                setSelectedHolidayIds(newSelected);
                                            }}
                                            style={{ cursor: "pointer", width: "18px", height: "18px" }}
                                        />
                                        <label htmlFor={`holiday-${uniqueId}`} style={{ cursor: "pointer", flex: 1, margin: 0 }}>
                                            <span style={{ fontWeight: "600", color: "#333" }}>{holiday.name}</span>
                                            <br />
                                            <span style={{ fontSize: "12px", color: "#666" }}>📅 {holiday.date}</span>
                                        </label>
                                    </div>
                                    );
                                })}
                            </div>
                        ) : (
                            <p style={{ color: "#999", fontStyle: "italic" }}>No holidays for {new Date(2026, timetableMonth - 1).toLocaleString('default', { month: 'long' })} {timetableYear}. Add holidays in Holiday Management tab.</p>
                        )}
                        <p style={{ color: "#666", fontSize: "12px", marginTop: "10px" }}>
                            ✓ Selected: {selectedHolidayIds.size} holiday(ies)
                        </p>
                    </div>

                    {/* Buttons */}
                    <div style={{ display: 'flex', gap: 10, marginTop: 15, flexWrap: 'wrap' }}>
                        {!timetableExists ? (
                            <button
                                onClick={() => handleGenerateTimetable(true, false)}
                                disabled={loading}
                                style={{ ...buttonStyle, backgroundColor: "#FF9800", color: "white", width: "auto" }}
                            >
                                Generate & Save
                            </button>
                        ) : (
                            <button
                                onClick={() => handleGenerateTimetable(true, true)}
                                disabled={loading}
                                style={{ ...buttonStyle, backgroundColor: "#4CAF50", color: "white", width: "auto" }}
                            >
                                ♻️ Update Timetable
                            </button>
                        )}
                    </div>
                    {timetableExists && (
                        <p style={{ color: "#FF9800", marginTop: "10px", fontWeight: "bold" }}>📌 Timetable already exists for this month. Click "Update Timetable" to regenerate.</p>
                    )}
                    {timetableGenerated && !timetableExists && (
                        <p style={{ color: "#4CAF50", marginTop: "10px", fontWeight: "bold" }}>✓ Timetable generated successfully!</p>
                    )}
                    {previewHolidays.length > 0 && (
                        <div style={{ marginTop: "8px", color: "#555", fontSize: "12px" }}>
                            <strong>Holidays used:</strong> {previewHolidays.map(h => {
                                if (!h) return '';
                                if (typeof h === 'string') return h;
                                if (h.date) return `${h.date}${h.name ? ' (' + h.name + ')' : ''}`;
                                return JSON.stringify(h);
                            }).filter(Boolean).join(', ')}
                        </div>
                    )}
                </div>
            </div>

            {/* Weekly Timetable View Section */}
            <div id="weeklyViewSection" style={tabStyle}>
                <h2>📆 Weekly Timetable View</h2>
                
                {/* Month Dropdown */}
                <div style={{ marginBottom: "15px", padding: "15px", backgroundColor: "#f0f7ff", borderRadius: "4px", border: "1px solid #90caf9" }}>
                    <label style={{ fontWeight: "bold", color: "#1976d2", marginRight: "10px", display: "block", marginBottom: "8px" }}>
                        📅 Select Month to View First Week:
                    </label>
                    <select
                        value={selectedMonth || ""}
                        onChange={(e) => {
                            const month = e.target.value;
                            setSelectedMonth(month);
                            if (month) {
                                // Fetch timetable for selected month from timetables folder
                                fetchMonthTimetable(month);
                                        const firstWeekStart = getFirstWeekOfMonth(month);
                                        if (firstWeekStart) {
                                            handleWeekNavigation(firstWeekStart);
                                        }
                            }
                        }}
                        style={{
                            ...inputStyle,
                            width: "250px",
                            padding: "10px",
                            fontSize: "14px",
                            borderColor: selectedMonth ? "#1976d2" : "#ddd",
                            borderWidth: selectedMonth ? "2px" : "1px"
                        }}
                    >
                        <option value="">-- Select a month --</option>
                        {availableMonths.map(monthStr => (
                            <option key={monthStr} value={monthStr}>
                                {monthStr}
                            </option>
                        ))}
                    </select>
                    {selectedMonth && (
                        <div style={{ marginTop: "8px", color: "#1565c0", fontSize: "13px" }}>
                            ✓ Showing first week of the selected month
                        </div>
                    )}
                </div>
                
                {/* Week Navigation and Class Filter */}
                <div style={{ marginBottom: "20px", padding: "15px", backgroundColor: "#f9f9f9", borderRadius: "4px" }}>
                    {/* Week Navigation */}
                    <div style={{ display: "flex", gap: "10px", alignItems: "center", marginBottom: "15px", flexWrap: "wrap" }}>
                        <button
                            onClick={navigateToPreviousWeek}
                            disabled={isPreviousWeekDisabled() || loading}
                            style={{ ...buttonStyle, backgroundColor: "#2196F3", color: "white", width: "auto", opacity: isPreviousWeekDisabled() ? 0.5 : 1, cursor: isPreviousWeekDisabled() ? "not-allowed" : "pointer" }}
                        >
                            ← Previous Week
                        </button>
                        
                        <button
                            onClick={() => {
                                const today = new Date();
                                const day = today.getDay();
                                const diff = (day === 0 ? -6 : 1) - day;
                                const start = new Date(today);
                                start.setDate(today.getDate() + diff);
                                start.setHours(0, 0, 0, 0);
                                handleWeekNavigation(start);
                                setSelectedMonth(null); // Clear month selection for "This Week"
                            }}
                            style={{ ...buttonStyle, backgroundColor: "#4CAF50", color: "white", width: "auto" }}
                        >
                            📍 This Week
                        </button>

                        <button
                            onClick={navigateToNextWeek}
                            disabled={isNextWeekDisabled() || loading}
                            style={{ ...buttonStyle, backgroundColor: "#2196F3", color: "white", width: "auto", opacity: isNextWeekDisabled() ? 0.5 : 1, cursor: isNextWeekDisabled() ? "not-allowed" : "pointer" }}
                        >
                            Next Week →
                        </button>

                        <span style={{ color: "#555", fontWeight: "bold" }}>
                            📅 {formatDate(weekStart)} to {formatDate(getActualWeekEnd())}
                        </span>
                        {selectedMonth && (isPreviousWeekDisabled() || isNextWeekDisabled()) && (
                            <span style={{ color: "#FF9800", fontWeight: "bold", fontSize: "12px" }}>
                                ⏹️ {isPreviousWeekDisabled() ? "First week" : ""} {isNextWeekDisabled() ? "Last week" : ""} of month
                            </span>
                        )}
                    </div>

                    {/* Class Filter */}
                    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                        <label style={{ fontWeight: "bold", color: "#333" }}>Filter by Class:</label>
                        <select
                            value={timetableClassFilter}
                            onChange={(e) => setTimetableClassFilter(e.target.value)}
                            style={{ ...inputStyle, width: "200px" }}
                        >
                            <option value="">All Classes</option>
                            {mergedClasses.map(cls => (
                                <option key={cls} value={cls}>{cls}</option>
                            ))}
                        </select>

                        <button
                            onClick={refreshTimetableHolidays}
                            disabled={loading}
                            style={{
                                ...buttonStyle,
                                backgroundColor: loading ? "#ccc" : "#FF5722",
                                color: "white",
                                width: "auto",
                                cursor: loading ? "not-allowed" : "pointer"
                            }}
                        >
                            {loading ? "🔄 Refreshing..." : "🔄 Refresh & Verify Holidays"}
                        </button>
                    </div>
                </div>

                {/* Weekly Grid */}
                {(() => {
                    // Get the actual week end, respecting month boundaries
                    const weekEnd = getActualWeekEnd();

                    // Ensure 6 classes per day by filtering timetable entries
                    const enforceSixClassesPerDay = (entries) => {
                        const groupedByDate = entries.reduce((acc, entry) => {
                            acc[entry.date] = acc[entry.date] || [];
                            acc[entry.date].push(entry);
                            return acc;
                        }, {});

                        return Object.values(groupedByDate).flatMap((dayEntries) => {
                            // Allow up to 7 periods (supports added 15:00 slot)
                            if (dayEntries.length > 7) {
                                return dayEntries.slice(0, 7);
                            }
                            return dayEntries;
                        });
                    };

                    const filteredWeeklyData = enforceSixClassesPerDay(
                        timetableList.filter(entry => {
                            if (timetableClassFilter && entry.class !== timetableClassFilter) return false;
                            if (!entry || !entry.date) return false;
                            // Parse date as local date to avoid timezone/UTC shifts
                            const parts = String(entry.date).split('-');
                            if (parts.length < 3) return false;
                            const y = parseInt(parts[0], 10);
                            const m = parseInt(parts[1], 10);
                            const d = parseInt(parts[2], 10);
                            const entryDate = new Date(y, m - 1, d);
                            entryDate.setHours(0, 0, 0, 0);

                            // Filter by date range (week boundaries)
                            if (entryDate < weekStart || entryDate > weekEnd) return false;
                            
                            // If a month is selected, only show entries from that month
                            if (selectedMonth) {
                                const monthYearMap = {
                                    'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
                                    'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12
                                };
                                const parts = selectedMonth.split(' ');
                                const monthName = parts[0];
                                const year = parseInt(parts[1]);
                                const selectedMonthNum = monthYearMap[monthName];
                                
                                // Check if entry belongs to selected month
                                if (entryDate.getMonth() + 1 !== selectedMonthNum || entryDate.getFullYear() !== year) {
                                    return false;
                                }
                            }
                            
                            return true;
                        })
                    );

                    const uniqueTimes = [...new Set(filteredWeeklyData.map(e => e.time).concat([lunchBreakTime]))].sort();

                    // Generate week days, but only up to weekEnd AND only for selected month (respects month boundaries)
                    const weekDays = [];
                    const monthYearMap = {
                        'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
                        'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12
                    };
                    
                    let currentDay = new Date(weekStart);
                    // Loop through all days from weekStart until we pass weekEnd
                    while (currentDay <= weekEnd) {
                        // If a month is selected, only add dates from that month
                        if (selectedMonth) {
                            const parts = selectedMonth.split(' ');
                            const monthName = parts[0];
                            const year = parseInt(parts[1]);
                            const selectedMonthNum = monthYearMap[monthName];
                            
                            if (currentDay.getMonth() + 1 === selectedMonthNum && currentDay.getFullYear() === year) {
                                weekDays.push(new Date(currentDay));
                            }
                        } else {
                            weekDays.push(new Date(currentDay));
                        }
                        
                        currentDay.setDate(currentDay.getDate() + 1);
                    }

                    const getDayName = (date) => {
                        const days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
                        return days[date.getDay()];
                    };

                    const getTimetableEntry = (dateStr, time) => {
                        return filteredWeeklyData.find(entry => entry.date === dateStr && entry.time === time);
                    };

                    if (uniqueTimes.length === 0) {
                        return (
                            <div style={{ textAlign: "center", padding: "40px", color: "#999" }}>
                                <p>📭 No timetable entries found for {timetableClassFilter ? timetableClassFilter : "this week"}</p>
                            </div>
                        );
                    }

                    // If no month is selected OR no class is selected, show only watermark
                    if (!selectedMonth || !timetableClassFilter) {
                        return (
                            <div style={{ 
                                position: "relative", 
                                height: "500px",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center"
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
                        );
                    }

                    return (
                        <div style={{ overflowX: "auto", position: "relative" }}>
                            <table style={{
                                width: "100%",
                                borderCollapse: "collapse",
                                minWidth: "1200px"
                            }}>
                                <thead>
                                    <tr style={{ backgroundColor: "#1976d2", color: "white" }}>
                                        <th style={{
                                            padding: "12px",
                                            textAlign: "center",
                                            fontSize: "13px",
                                            fontWeight: "bold",
                                            minWidth: "80px",
                                            borderRight: "1px solid #1565c0"
                                        }}>⏰ Time</th>
                                        {weekDays.map((day) => {
                                            const isSunday = day.getDay() === 0;
                                            const dateStr = formatDate(day);
                                            const holidayName = allHolidays.find(h => h.date === dateStr)?.name || null;
                                            const isHoliday = holidayName !== null;
                                            return (
                                            <th
                                                key={formatDate(day)}
                                                style={{
                                                    padding: "12px",
                                                    textAlign: "center",
                                                    fontSize: "12px",
                                                    fontWeight: "bold",
                                                    minWidth: "140px",
                                                    borderRight: isSunday ? "1px solid #1565c0" : isHoliday ? "1px solid #1565c0" : "1px solid #1565c0",
                                                    backgroundColor: isHoliday ? "#FF6F00" : isSunday ? "#FF6F00" : "#1976d2",
                                                    position: "relative"
                                                }}
                                            >
                                                {isSunday && (
                                                    <div style={{
                                                        position: "absolute",
                                                        left: "-20px",
                                                        top: "0",
                                                        height: "100%",
                                                        fontSize: "10px",
                                                        fontWeight: "bold",
                                                        color: "#FF6F00",
                                                        writingMode: "vertical-rl",
                                                        textOrientation: "mixed",
                                                        display: "flex",
                                                        alignItems: "center",
                                                        justifyContent: "center"
                                                    }}>
                                                        SUNDAY
                                                    </div>
                                                )}
                                                {isHoliday && (
                                                    <div style={{
                                                        position: "absolute",
                                                        right: "-20px",
                                                        top: "0",
                                                        height: "100%",
                                                        fontSize: "9px",
                                                        fontWeight: "bold",
                                                        color: "#FF6F00",
                                                        writingMode: "vertical-rl",
                                                        textOrientation: "mixed",
                                                        transform: "rotate(180deg)",
                                                        display: "flex",
                                                        alignItems: "center",
                                                        justifyContent: "center"
                                                    }}>
                                                        {holidayName}
                                                    </div>
                                                )}
                                                <div>{getDayName(day)}</div>
                                                <div style={{ fontSize: "11px", fontWeight: "normal", color: (isSunday || isHoliday) ? "#ffffff" : "#e0e0e0" }}>
                                                    {formatDate(day)}
                                                </div>
                                            </th>
                                            );
                                        })}
                                    </tr>
                                </thead>
                                <tbody>
                                    {uniqueTimes.map((time, timeIdx) => {
                                            const isLunchBreak = time === lunchBreakTime; // Check if the current row is the lunch break

                                        return (
                                            <tr key={time} style={{ backgroundColor: isLunchBreak ? "#ffecb3" : timeIdx % 2 === 0 ? "#fafafa" : "#fff" }}>
                                                <td style={{
                                                    padding: "10px",
                                                    textAlign: "center",
                                                    fontWeight: "bold",
                                                    backgroundColor: isLunchBreak ? "#ffe082" : "#f0f0f0",
                                                    borderRight: "1px solid #ddd",
                                                    borderBottom: "1px solid #ddd",
                                                    color: isLunchBreak ? "#bf360c" : "#333"
                                                }}>
                                                    {time}
                                                </td>
                                                {weekDays.map((day) => {
                                                    const dateStr = formatDate(day);
                                                    const isSunday = day.getDay() === 0;
                                                    
                                                    // Check if date is a holiday
                                                    const holidayName = allHolidays.find(h => h.date === dateStr)?.name || null;
                                                    const isHoliday = holidayName !== null;
                                                    
                                                    const entry = getTimetableEntry(dateStr, time);
                                                    const today = new Date();
                                                    today.setHours(0, 0, 0, 0);
                                                    const isToday = dateStr === formatDate(today);

                                                    return (
                                                        <td
                                                            key={`${dateStr}-${time}`}
                                                            style={{
                                                                padding: "8px",
                                                                borderRight: isSunday ? "3px solid #FF6F00" : isHoliday ? "3px solid #FF6F00" : "1px solid #ddd",
                                                                borderBottom: "1px solid #ddd",
                                                                backgroundColor: isHoliday ? (isLunchBreak ? "#ffe8d6" : isToday ? "#ffccb3" : (entry ? "#ffd9b3" : "#ffe8d6")) : isSunday ? (isLunchBreak ? "#ffe8d6" : isToday ? "#ffccb3" : (entry ? "#ffd9b3" : "#ffe8d6")) : (isLunchBreak ? "#fff8e1" : isToday ? "#fff9c4" : (entry ? "#e3f2fd" : "#fff")),
                                                                minHeight: "80px",
                                                                verticalAlign: "top",
                                                                fontSize: "11px",
                                                                color: isLunchBreak ? "#bf360c" : "inherit",
                                                                position: "relative"
                                                            }}
                                                        >
                                                            {isHoliday && (
                                                                <div style={{
                                                                    position: "absolute",
                                                                    right: "-22px",
                                                                    top: "0",
                                                                    height: "100%",
                                                                    fontSize: "9px",
                                                                    fontWeight: "bold",
                                                                    color: "#FF6F00",
                                                                    writingMode: "vertical-rl",
                                                                    textOrientation: "mixed",
                                                                    transform: "rotate(180deg)",
                                                                    display: "flex",
                                                                    alignItems: "center",
                                                                    justifyContent: "center",
                                                                    maxWidth: "80px"
                                                                }}>
                                                                    {holidayName}
                                                                </div>
                                                            )}
                                                            {isLunchBreak ? (
                                                                <div style={{ fontWeight: "bold", textAlign: "center" }}>Lunch Break</div>
                                                            ) : entry ? (
                                                                                            <div>
                                                                                                <div style={{
                                                                                                    fontWeight: "bold",
                                                                                                    color: entry.subject === 'Games' ? "#2e7d32" : "#1565c0",
                                                                                                    marginBottom: "3px",
                                                                                                    fontSize: "12px"
                                                                                                }}>
                                                                                                {entry.subject}
                                                                                            </div>
                                                                                                <div style={{
                                                                                                    fontSize: "10px",
                                                                                                    color: "#555",
                                                                                                    marginBottom: "1px"
                                                                                                }}>
                                                                                                    👥 {entry.class}
                                                                                                </div>
                                                                                                <div style={{
                                                                                                    fontSize: "10px",
                                                                                                    color: entry.faculty ? "#666" : "#c62828",
                                                                                                    fontWeight: entry.faculty ? "normal" : "bold"
                                                                                                }}>
                                                                                                    👨‍🏫 {entry.faculty ? entry.faculty : 'Unassigned'}
                                                                                                </div>
                                                                                                <div style={{
                                                                                                    fontSize: "10px",
                                                                                                    color: "#e65100",
                                                                                                    marginTop: "1px"
                                                                                                }}>
                                                                                                    📍 {entry.room}
                                                                                                </div>
                                                                                            </div>
                                                        ) : (
                                                            <div style={{ color: "#ccc" }}>-</div>
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
                    );
                })()}
            </div>
        </div>
    );
}

export default Timetable;

// Add a dedicated row for the lunch break in the timetable grid
const lunchBreakTime = "12:00 PM - 1:00 PM"; // Define the lunch break time
