import { useState, useEffect } from "react";
import api from "../api";

function HolidayCalendar({ leaveDates = [], facultyHolidays = [] }) {
    const [holidays, setHolidays] = useState([]);
    const [currentMonth, setCurrentMonth] = useState(new Date().getMonth());
    const [currentYear, setCurrentYear] = useState(new Date().getFullYear());

    useEffect(() => {
        fetchHolidays();
    }, []);

    const fetchHolidays = async () => {
        try {
            const response = await api.get("/holidays");
            setHolidays(response.data || []);
        } catch (error) {
            console.error("Error fetching holidays:", error);
        }
    };

    const getDaysInMonth = (month, year) => {
        return new Date(year, month + 1, 0).getDate();
    };

    const getFirstDayOfMonth = (month, year) => {
        return new Date(year, month, 1).getDay();
    };

    const isHoliday = (day) => {
        const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
        return holidays.some(h => h.date === dateStr);
    };

    const getHolidayName = (day) => {
        const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
        const holiday = holidays.find(h => h.date === dateStr);
        return holiday ? holiday.name : "";
    };

    const isLeaveDate = (day) => {
        const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
        return leaveDates.some(leave => {
            if (typeof leave === 'string') {
                return leave === dateStr;
            }
            return leave.date === dateStr;
        });
    };

    const isFacultyHoliday = (day) => {
        const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
        return facultyHolidays.some(fh => {
            if (typeof fh === 'string') {
                return fh === dateStr;
            }
            return fh.date === dateStr;
        });
    };

    const days = [];
    const daysInMonth = getDaysInMonth(currentMonth, currentYear);
    const firstDay = getFirstDayOfMonth(currentMonth, currentYear);

    for (let i = 0; i < firstDay; i++) {
        days.push(null);
    }
    for (let i = 1; i <= daysInMonth; i++) {
        days.push(i);
    }

    const monthNames = ["January", "February", "March", "April", "May", "June",
                       "July", "August", "September", "October", "November", "December"];
    const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

    const handlePrevMonth = () => {
        if (currentMonth === 0) {
            setCurrentMonth(11);
            setCurrentYear(currentYear - 1);
        } else {
            setCurrentMonth(currentMonth - 1);
        }
    };

    const handleNextMonth = () => {
        if (currentMonth === 11) {
            setCurrentMonth(0);
            setCurrentYear(currentYear + 1);
        } else {
            setCurrentMonth(currentMonth + 1);
        }
    };

    const getBackgroundColor = (day) => {
        if (!day) return "#fafafa";
        if (isLeaveDate(day)) return "#ffcdd2"; // Red for leaves
        if (isFacultyHoliday(day)) return "#fff9c4"; // Yellow for faculty holidays
        if (isHoliday(day)) return "#ffcdd2"; // Red for public holidays
        return "#fafafa";
    };

    const getIndicator = (day) => {
        if (isLeaveDate(day)) return "🔴"; // Red dot for leaves
        if (isFacultyHoliday(day)) return "🟡"; // Yellow dot for faculty holidays
        if (isHoliday(day)) return "🏖️"; // Holiday emoji
        return "";
    };

    return (
        <div style={{
            padding: "20px",
            backgroundColor: "#fff",
            borderRadius: "8px",
            boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
            maxWidth: "500px"
        }}>
            <h2 style={{ textAlign: "center", margin: "0 0 20px 0" }}>📅 Holiday Calendar</h2>
            
            {/* Month Navigation */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
                <button
                    onClick={handlePrevMonth}
                    style={{
                        padding: "8px 12px",
                        backgroundColor: "#2196F3",
                        color: "white",
                        border: "none",
                        borderRadius: "4px",
                        cursor: "pointer"
                    }}
                >
                    ← Prev
                </button>
                <h3 style={{ margin: 0, flex: 1, textAlign: "center" }}>
                    {monthNames[currentMonth]} {currentYear}
                </h3>
                <button
                    onClick={handleNextMonth}
                    style={{
                        padding: "8px 12px",
                        backgroundColor: "#2196F3",
                        color: "white",
                        border: "none",
                        borderRadius: "4px",
                        cursor: "pointer"
                    }}
                >
                    Next →
                </button>
            </div>

            {/* Calendar Grid */}
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                    <tr>
                        {dayNames.map(day => (
                            <th
                                key={day}
                                style={{
                                    padding: "10px",
                                    backgroundColor: "#f0f0f0",
                                    border: "1px solid #ddd",
                                    textAlign: "center",
                                    fontWeight: "bold",
                                    fontSize: "12px"
                                }}
                            >
                                {day}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {Array.from({ length: Math.ceil(days.length / 7) }).map((_, weekIdx) => (
                        <tr key={weekIdx}>
                            {days.slice(weekIdx * 7, weekIdx * 7 + 7).map((day, dayIdx) => (
                                <td
                                    key={dayIdx}
                                    style={{
                                        padding: "10px",
                                        border: "1px solid #ddd",
                                        textAlign: "center",
                                        height: "60px",
                                        backgroundColor: getBackgroundColor(day),
                                        cursor: day ? "pointer" : "default",
                                        position: "relative"
                                    }}
                                    title={day && getHolidayName(day) ? getHolidayName(day) : ""}
                                >
                                    {day && (
                                        <div>
                                            <div style={{ fontWeight: "bold", fontSize: "14px" }}>{day}</div>
                                            {getIndicator(day) && (
                                                <div style={{
                                                    fontSize: "14px",
                                                    marginTop: "4px",
                                                    fontWeight: "bold"
                                                }}>
                                                    {getIndicator(day)}
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>

            {/* Legend */}
            <div style={{ marginTop: "20px", padding: "12px", backgroundColor: "#f5f5f5", borderRadius: "4px", fontSize: "12px" }}>
                <div style={{ marginBottom: "8px" }}><strong>📅 Calendar Legend:</strong></div>
                <div style={{ marginBottom: "6px" }}>🔴 <strong>Leave</strong> - Your approved or pending leave</div>
                <div style={{ marginBottom: "6px" }}>🟡 <strong>Faculty Holiday</strong> - Personal holiday booked</div>
                <div>🏖️ <strong>Public Holiday</strong> - System public holiday</div>
            </div>
        </div>
    );
}

export default HolidayCalendar;
