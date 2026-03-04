import { useState, useEffect } from "react";
import api from "../api";
import Timetable from "./timetable";
import AdminNotifications from "./adminNotifications";

function AdminDashboard() {
    const [activeTab, setActiveTab] = useState("dashboard");
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState("");

    // Faculty Management
    const [facultyForm, setFacultyForm] = useState({ name: "", email: "", subject: "", classes: [], photo: "" });
    const [facultyList, setFacultyList] = useState([]);
    const [editingFaculty, setEditingFaculty] = useState(null);
    const [editForm, setEditForm] = useState({ id: "", name: "", email: "", subject: "", classes: [], photo: "" });

    // Student Management
    const [studentForm, setStudentForm] = useState({ name: "", rollno: "", class: "", email: "" });
    const [studentList, setStudentList] = useState([]);
    const [studentSearch, setStudentSearch] = useState("");

    // Faculty Search
    const [facultySearch, setFacultySearch] = useState("");

    // Holidays
    const [holidayForm, setHolidayForm] = useState({ date: "", name: "" });
    const [holidayList, setHolidayList] = useState([]);



    // Workload
    const [facultyWorkloadData, setFacultyWorkloadData] = useState([]);
    const [availableMonths, setAvailableMonths] = useState([]);
    const [selectedMonth, setSelectedMonth] = useState("");
    const [adjustmentResults, setAdjustmentResults] = useState([]);
    const [showAdjustmentResults, setShowAdjustmentResults] = useState(false);

    // Leave Management
    const [leaves, setLeaves] = useState([]);
    const [adminEmail, setAdminEmail] = useState("");

    useEffect(()=> {
        fetchAllData();
        fetchMonths();
        fetchLeaves();
        // Derive admin email from stored auth token (format: token_<id>_<email>)
        try {
            const token = localStorage.getItem('auth_token') || '';
            if (token && token.startsWith('token_')) {
                const parts = token.split('_');
                if (parts.length >= 3) {
                    const email = parts.slice(2).join('_');
                    setAdminEmail(email);
                }
            }
        } catch (e) {
            console.warn('Failed to parse auth token for admin email:', e);
        }
    }, []);

    // When user opens Workload tab or changes selectedMonth, refresh months and workload
    useEffect(() => {
        if (activeTab === 'workload') {
            // Refresh months (in case timetables were generated elsewhere)
            fetchMonths();
            // Do not auto-load workload until a month is explicitly selected
            setFacultyWorkloadData([]);
        }
        // only run when activeTab or selectedMonth changes
    }, [activeTab]);

    // When selectedMonth changes while on workload tab, load workload for that month
    useEffect(() => {
        if (activeTab === 'workload') {
            if (selectedMonth) {
                fetchFacultyWorkload(selectedMonth);
            } else {
                setFacultyWorkloadData([]);
            }
        }
    }, [activeTab, selectedMonth]);

    useEffect(() => {
        if (message) {
            const timer = setTimeout(() => setMessage(""), 5000);
            return () => clearTimeout(timer);
        }
    }, [message]);

    // Fetch All Data
    const fetchAllData = async () => {
        try {
            setLoading(true);
            console.log("Fetching faculty, students, and holidays...");
            const [faculties, students, holidays] = await Promise.all([
                api.get("/faculty"),
                api.get("/students"),
                api.get("/holidays")
            ]);
            console.log("Faculty data:", faculties.data);
            console.log("Students data:", students.data);
            console.log("Holidays data:", holidays.data);
            setFacultyList(faculties.data || []);
            setStudentList(students.data || []);
            setHolidayList(holidays.data || []);
        } catch (error) {
            console.error("Error fetching data:", error);
            const errorMsg = error.response?.data?.error || error.message || "Unknown error";
            setMessage("❌ Error fetching data: " + errorMsg);
        } finally {
            setLoading(false);
        }
    };

    // Faculty Management
    const handlePhotoUpload = (e) => {
        const file = e.target.files[0];
        if (file) {
            // Check file size (max 5MB)
            if (file.size > 5 * 1024 * 1024) {
                setMessage("❌ File size too large. Max 5MB allowed");
                return;
            }

            // Check file type
            if (!file.type.startsWith('image/')) {
                setMessage("❌ Please select a valid image file");
                return;
            }

            // Convert file to base64
            const reader = new FileReader();
            reader.onload = (event) => {
                setFacultyForm({ ...facultyForm, photo: event.target.result });
                setMessage("✅ Photo uploaded successfully");
            };
            reader.onerror = () => {
                setMessage("❌ Error reading file");
            };
            reader.readAsDataURL(file);
        }
    };

    const handleAddFaculty = async () => {
        if (!facultyForm.name || !facultyForm.email) {
            setMessage("❌ Please fill all faculty fields");
            return;
        }
        try {
            setLoading(true);
            console.log("Sending faculty data:", facultyForm);
            const response = await api.post("/faculty", facultyForm);
            console.log("Faculty added response:", response.data);
            setMessage("✅ Faculty added successfully");
            setFacultyForm({ name: "", email: "", subject: "", classes: [], photo: "" });
            await fetchAllData();
        } catch (error) {
            console.error("Error adding faculty:", error);
            console.error("Error response:", error.response);
            const errorMsg = error.response?.data?.error || error.message || "Unknown error";
            setMessage("❌ Error adding faculty: " + errorMsg);
        } finally {
            setLoading(false);
        }
    };

    const handleEditFaculty = (faculty) => {
        setEditingFaculty(faculty.id);
        setEditForm({ ...faculty });
    };

    const handlePhotoUploadEdit = (e) => {
        const file = e.target.files[0];
        if (file) {
            if (file.size > 5 * 1024 * 1024) {
                setMessage("❌ File size too large. Max 5MB allowed");
                return;
            }
            if (!file.type.startsWith('image/')) {
                setMessage("❌ Please select a valid image file");
                return;
            }
            const reader = new FileReader();
            reader.onload = (event) => {
                setEditForm({ ...editForm, photo: event.target.result });
                setMessage("✅ Photo updated successfully");
            };
            reader.onerror = () => {
                setMessage("❌ Error reading file");
            };
            reader.readAsDataURL(file);
        }
    };

    const handleUpdateFaculty = async () => {
        if (!editForm.name || !editForm.email) {
            setMessage("❌ Please fill all faculty fields");
            return;
        }
        try {
            setLoading(true);
            await api.put(`/faculty/${editForm.id}`, editForm);
            setMessage("✅ Faculty updated successfully");
            setEditingFaculty(null);
            setEditForm({ id: "", name: "", email: "", subject: "", photo: "" });
            await fetchAllData();
        } catch (error) {
            setMessage("❌ Error updating faculty: " + error.message);
        } finally {
            setLoading(false);
        }
    };

    const handleCancelEdit = () => {
        setEditingFaculty(null);
        setEditForm({ id: "", name: "", email: "", subject: "", classes: [], photo: "" });
    };

    const handleDeleteFaculty = async (facultyId) => {
        if (!window.confirm("Are you sure you want to delete this faculty?")) return;
        try {
            setLoading(true);
            await api.delete(`/faculty/${facultyId}`);
            setMessage("✅ Faculty deleted successfully");
            await fetchAllData();
        } catch (error) {
            setMessage("❌ Error deleting faculty: " + error.message);
        } finally {
            setLoading(false);
        }
    };

    // Student Management
    const handleAddStudent = async () => {
        if (!studentForm.name || !studentForm.rollno || !studentForm.class) {
            setMessage("❌ Please fill all student fields");
            return;
        }
        try {
            setLoading(true);
            console.log("Sending student data:", studentForm);
            const response = await api.post("/students", studentForm);
            console.log("Student added response:", response.data);
            setMessage("✅ Student added successfully");
            setStudentForm({ name: "", rollno: "", class: "", email: "" });
            await fetchAllData();
        } catch (error) {
            console.error("Error adding student:", error);
            console.error("Error response:", error.response);
            const errorMsg = error.response?.data?.error || error.message || "Unknown error";
            setMessage("❌ Error adding student: " + errorMsg);
        } finally {
            setLoading(false);
        }
    };

    // Holidays
    const handleAddHoliday = async () => {
        if (!holidayForm.date || !holidayForm.name) {
            setMessage("❌ Please fill all holiday fields");
            return;
        }
        
        // Check if holiday already exists on this date
        const holidayExists = holidayList.some(h => h.date === holidayForm.date);
        if (holidayExists) {
            setMessage("❌ A holiday already exists on this date");
            return;
        }
        
        try {
            setLoading(true);
            console.log("Sending holiday data:", holidayForm);
            const response = await api.post("/holidays", holidayForm);
            console.log("Holiday added response:", response.data);
            setMessage("✅ Holiday added successfully");
            setHolidayForm({ date: "", name: "" });
            await fetchAllData();
            // Notify other views (timetable/faculty/student) to refresh live data
            try { window.dispatchEvent(new Event('data-updated')); } catch (e) { console.warn('Event dispatch failed', e); }
        } catch (error) {
            console.error("Error adding holiday:", error);
            const errorMsg = error.response?.data?.error || error.message || "Unknown error";
            setMessage("❌ Error adding holiday: " + errorMsg);
        } finally {
            setLoading(false);
        }
    };

    const handleDeleteHoliday = async (holidayId) => {
        if (!window.confirm("Are you sure you want to delete this holiday?")) return;
        try {
            setLoading(true);
            await api.delete(`/holidays/${holidayId}`);
            setMessage("✅ Holiday deleted successfully");
            await fetchAllData();
            // Notify other views to refresh live data
            try { window.dispatchEvent(new Event('data-updated')); } catch (e) { console.warn('Event dispatch failed', e); }
        } catch (error) {
            console.error("Error deleting holiday:", error);
            const errorMsg = error.response?.data?.error || error.message || "Unknown error";
            setMessage("❌ Error deleting holiday: " + errorMsg);
        } finally {
            setLoading(false);
        }
    };

    // Workload Management
    const fetchFacultyWorkload = async (monthLabel) => {
        try {
            setLoading(true);
            // Only fetch for a specific month — do nothing when monthLabel is empty
            if (!monthLabel) {
                setFacultyWorkloadData([]);
                return;
            }
            const ts = Date.now();
            if (monthLabel) {
                const resp = await api.get(`/faculty-workload-month/${encodeURIComponent(monthLabel)}?ts=${ts}`);
                setFacultyWorkloadData(resp.data || []);
            } else {
                // fallback (shouldn't reach here) — keep empty
                setFacultyWorkloadData([]);
            }
        } catch (error) {
            setMessage("❌ Error fetching workload: " + (error.response?.data?.error || error.message));
        } finally {
            setLoading(false);
        }
    };

    const fetchMonths = async () => {
        try {
            const resp = await api.get('/timetable-months');
            const months = Array.isArray(resp.data) ? resp.data : [];
            setAvailableMonths(months);
            // Do not auto-select any month; let user choose explicitly
        } catch (e) {
            console.warn('Failed to load months:', e);
        }
    };

    // Adjust overload removed: endpoint deprecated and button removed from UI

    // Leave Management
    const fetchLeaves = async (showNotification = false) => {
        try {
            setLoading(true);
            const response = await api.get("/admin/leaves");
            const leaveData = Array.isArray(response.data) ? response.data : [];
            setLeaves(leaveData);
            // Only show message if explicitly requested (like on manual refresh)
            if (showNotification) {
                setMessage(`✅ Loaded ${leaveData.length} leave(s)`);
            }
        } catch (error) {
            setMessage("❌ Error fetching leaves: " + error.message);
            setLeaves([]);
        } finally {
            setLoading(false);
        }
    };

    const approveLeave = async (leaveId) => {
        try {
            // Validate leave ID
            if (!leaveId) {
                setMessage("❌ Error: Leave ID is missing or invalid");
                console.error("Leave ID is empty:", leaveId);
                return;
            }
            
            setLoading(true);
            console.log("Approving leave with ID:", leaveId, "Type:", typeof leaveId);
            await api.put(`/admin/leave/${leaveId}/approve`, {});
            setMessage("✅ Leave approved successfully! Updating list...");
            await fetchLeaves();
            setMessage("✅ Leave approved and list updated");
            // Notify other views (timetable, faculty, student) to refresh immediately
            try { window.dispatchEvent(new Event('data-updated')); } catch (e) { console.warn('Event dispatch failed', e); }
        } catch (error) {
            console.error("Leave approval error:", error.response?.data || error.message);
            setMessage("❌ Error approving leave: " + (error.response?.data?.error || error.message));
        } finally {
            setLoading(false);
        }
    };

    const rejectLeave = async (leaveId, reason = "") => {
        try {
            // Validate leave ID
            if (!leaveId) {
                setMessage("❌ Error: Leave ID is missing or invalid");
                console.error("Leave ID is empty:", leaveId);
                return;
            }
            
            setLoading(true);
            console.log("Rejecting leave with ID:", leaveId, "Type:", typeof leaveId);
            await api.put(`/admin/leave/${leaveId}/reject`, { reason });
            setMessage("✅ Leave rejected successfully! Updating list...");
            await fetchLeaves();
            setMessage("✅ Leave rejected and list updated");
            // Notify other views to refresh
            try { window.dispatchEvent(new Event('data-updated')); } catch (e) { console.warn('Event dispatch failed', e); }
        } catch (error) {
            console.error("Leave rejection error:", error.response?.data || error.message);
            setMessage("❌ Error rejecting leave: " + (error.response?.data?.error || error.message));
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

    return (
        <div style={{ padding: "20px", fontFamily: "Arial, sans-serif", backgroundColor: "#f5f5f5", minHeight: "100vh" }}>
            {/* Top navbar: admin email + logout */}
            <div style={{ backgroundColor: "#fff", padding: "10px 16px", marginBottom: "20px", borderRadius: "8px", boxShadow: "0 2px 8px rgba(0,0,0,0.1)", background: 'linear-gradient(135deg, #FF9800 0%, #FB8C00 100%)', color: 'white' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ fontSize: '14px', opacity: 0.95 }}>📧 {adminEmail || '...'}</div>
                    <div>
                        <button
                            onClick={() => { try { localStorage.clear(); } catch (e) {} window.location.href = '/login'; }}
                            style={{
                                padding: '8px 12px',
                                backgroundColor: '#fff',
                                color: '#FB8C00',
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
            <h1 style={{ color: "#333", marginBottom: "20px" }}>⚙️ Admin Dashboard</h1>

            {/* Tab Navigation */}
            <div style={{ display: "flex", gap: "10px", marginBottom: "20px", flexWrap: "wrap" }}>
                 {["dashboard", "faculty", "student", "holidays", "workload", "timetable", "notifications", "leaves"].map(tab => (
                    <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        style={{
                            ...buttonStyle,
                            backgroundColor: activeTab === tab ? "#2196F3" : "#e0e0e0",
                            color: activeTab === tab ? "white" : "#333",
                            width: "auto"
                        }}
                    >
                        {tab.charAt(0).toUpperCase() + tab.slice(1)}
                    </button>
                ))}
            </div>

            {/* Message Display */}
            {message && (
                <div style={{
                    padding: "12px",
                    marginBottom: "20px",
                    backgroundColor: message.includes("❌") ? "#fff3cd" : "#d4edda",
                    color: message.includes("❌") ? "#721c24" : "#155724",
                    borderRadius: "4px",
                    border: "1px solid " + (message.includes("❌") ? "#f5c6cb" : "#c3e6cb"),
                    fontSize: "14px"
                }}>
                    {message}
                </div>
            )}

            {/* Dashboard Tab */}
            {activeTab === "dashboard" && (
                <div style={tabStyle}>
                    <h2>Dashboard Overview</h2>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: "15px" }}>
                        <div style={{ backgroundColor: "#e3f2fd", padding: "20px", borderRadius: "4px", textAlign: "center" }}>
                            <h3 style={{ color: "#2196F3" }}>👨‍🏫 Total Faculty</h3>
                            <p style={{ fontSize: "28px", fontWeight: "bold", color: "#2196F3" }}>{facultyList.length}</p>
                        </div>
                        <div style={{ backgroundColor: "#e8f5e9", padding: "20px", borderRadius: "4px", textAlign: "center" }}>
                            <h3 style={{ color: "#4caf50" }}>👨‍🎓 Total Students</h3>
                            <p style={{ fontSize: "28px", fontWeight: "bold", color: "#4caf50" }}>{studentList.length}</p>
                        </div>
                        <div style={{ backgroundColor: "#fff3e0", padding: "20px", borderRadius: "4px", textAlign: "center" }}>
                            <h3 style={{ color: "#ff9800" }}>🏖️ Total Holidays</h3>
                            <p style={{ fontSize: "28px", fontWeight: "bold", color: "#ff9800" }}>{holidayList.length}</p>
                        </div>
                    </div>
                </div>
            )}

            {/* Faculty Management Tab */}
            {activeTab === "faculty" && (
                <div style={tabStyle}>
                    <h2>👨‍🏫 Manage Faculty</h2>
                    <div style={{ marginBottom: "20px", padding: "15px", backgroundColor: "#f9f9f9", borderRadius: "4px" }}>
                        <h3>Add New Faculty</h3>
                        <input
                            type="text"
                            placeholder="Faculty Name"
                            value={facultyForm.name}
                            onChange={(e) => setFacultyForm({ ...facultyForm, name: e.target.value })}
                            style={inputStyle}
                        />
                        <input
                            type="email"
                            placeholder="Email"
                            value={facultyForm.email}
                            onChange={(e) => setFacultyForm({ ...facultyForm, email: e.target.value })}
                            style={inputStyle}
                        />
                        <input
                            type="text"
                            placeholder="Subject"
                            value={facultyForm.subject}
                            onChange={(e) => setFacultyForm({ ...facultyForm, subject: e.target.value })}
                            style={inputStyle}
                        />

                        {/* Classes Assignment Section */}
                        <div style={{ marginBottom: "15px" }}>
                            <label style={{ display: "block", marginBottom: "8px", fontWeight: "600", color: "#333" }}>
                                📚 Assign Classes (Select one or more)
                            </label>
                            <div style={{
                                display: "grid",
                                gridTemplateColumns: "repeat(auto-fit, minmax(80px, 1fr))",
                                gap: "10px",
                                padding: "10px",
                                backgroundColor: "#f9f9f9",
                                borderRadius: "6px",
                                border: "1px solid #ddd"
                            }}>
                                {["6", "7", "8", "9", "10", "11", "12"].map((cls) => (
                                    <label key={cls} style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: "6px",
                                        cursor: "pointer",
                                        padding: "8px",
                                        backgroundColor: facultyForm.classes.includes(cls) ? "#e3f2fd" : "white",
                                        borderRadius: "4px",
                                        border: facultyForm.classes.includes(cls) ? "2px solid #2196F3" : "1px solid #ddd"
                                    }}>
                                        <input
                                            type="checkbox"
                                            checked={facultyForm.classes.includes(cls)}
                                            onChange={(e) => {
                                                if (e.target.checked) {
                                                    setFacultyForm({ 
                                                        ...facultyForm, 
                                                        classes: [...facultyForm.classes, cls] 
                                                    });
                                                } else {
                                                    setFacultyForm({ 
                                                        ...facultyForm, 
                                                        classes: facultyForm.classes.filter(c => c !== cls) 
                                                    });
                                                }
                                            }}
                                            style={{ cursor: "pointer" }}
                                        />
                                        <span style={{ userSelect: "none" }}>Class {cls}</span>
                                    </label>
                                ))}
                            </div>
                        </div>
                        
                        {/* Photo Upload Section */}
                        <div style={{ marginBottom: "15px" }}>
                            <label style={{ display: "block", marginBottom: "8px", fontWeight: "600", color: "#333" }}>
                                📸 Upload Faculty Photo (Optional)
                            </label>
                            <div style={{
                                display: "flex",
                                gap: "12px",
                                alignItems: "flex-start"
                            }}>
                                <div style={{ flex: 1 }}>
                                    <input
                                        type="file"
                                        accept="image/*"
                                        onChange={handlePhotoUpload}
                                        style={{
                                            width: "100%",
                                            padding: "10px",
                                            border: "2px dashed #2196F3",
                                            borderRadius: "6px",
                                            cursor: "pointer",
                                            backgroundColor: "#f8f9fa"
                                        }}
                                    />
                                    <p style={{ fontSize: "12px", color: "#666", margin: "6px 0 0 0" }}>
                                        Max 5MB. Supported: JPG, PNG, GIF, WebP
                                    </p>
                                </div>
                                
                                {/* Photo Preview */}
                                {facultyForm.photo && (
                                    <div style={{
                                        width: "80px",
                                        height: "80px",
                                        borderRadius: "6px",
                                        overflow: "hidden",
                                        border: "2px solid #2196F3",
                                        display: "flex",
                                        alignItems: "center",
                                        justifyContent: "center",
                                        backgroundColor: "#f0f0f0",
                                        flexShrink: 0
                                    }}>
                                        <img 
                                            src={facultyForm.photo}
                                            alt="Preview"
                                            style={{
                                                width: "100%",
                                                height: "100%",
                                                objectFit: "cover"
                                            }}
                                        />
                                    </div>
                                )}
                            </div>
                        </div>

                        <button
                            onClick={handleAddFaculty}
                            disabled={loading}
                            style={{ ...buttonStyle, backgroundColor: "#4CAF50", color: "white" }}
                        >
                            Add Faculty
                        </button>
                    </div>
                    <h3 style={{ marginTop: "30px", marginBottom: "20px" }}>Faculty List</h3>
                    <input 
                        type="text"
                        placeholder="🔍 Search faculty by name, email, or subject..."
                        value={facultySearch}
                        onChange={(e) => setFacultySearch(e.target.value)}
                        style={{
                            width: "100%",
                            padding: "12px",
                            marginBottom: "20px",
                            border: "1px solid #ddd",
                            borderRadius: "6px",
                            fontSize: "14px",
                            boxSizing: "border-box"
                        }}
                    />
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "20px" }}>
                        {facultyList
                            .filter(faculty => 
                                (faculty.name && faculty.name.toLowerCase().includes(facultySearch.toLowerCase())) ||
                                (faculty.email && faculty.email.toLowerCase().includes(facultySearch.toLowerCase())) ||
                                (faculty.subject && faculty.subject.toLowerCase().includes(facultySearch.toLowerCase()))
                            )
                            .map((faculty, idx) => (
                            <div 
                                key={idx}
                                style={{
                                    backgroundColor: "#ffffff",
                                    border: "1px solid #e0e0e0",
                                    borderRadius: "12px",
                                    padding: "0",
                                    boxShadow: "0 4px 6px rgba(0, 0, 0, 0.1)",
                                    transition: "all 0.3s ease",
                                    overflow: "hidden"
                                }}
                                onMouseEnter={(e) => {
                                    e.currentTarget.style.boxShadow = "0 8px 12px rgba(0, 0, 0, 0.15)";
                                    e.currentTarget.style.transform = "translateY(-4px)";
                                }}
                                onMouseLeave={(e) => {
                                    e.currentTarget.style.boxShadow = "0 4px 6px rgba(0, 0, 0, 0.1)";
                                    e.currentTarget.style.transform = "translateY(0)";
                                }}
                            >
                                {/* Faculty Photo */}
                                <div style={{
                                    width: "100%",
                                    height: "200px",
                                    backgroundColor: "#f0f0f0",
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    overflow: "hidden",
                                    position: "relative"
                                }}>
                                    {faculty.photo ? (
                                        <img 
                                            src={faculty.photo} 
                                            alt={faculty.name}
                                            style={{
                                                width: "100%",
                                                height: "100%",
                                                objectFit: "cover"
                                            }}
                                            onError={(e) => {
                                                e.target.style.display = "none";
                                                e.target.nextElementSibling.style.display = "flex";
                                            }}
                                        />
                                    ) : null}
                                    <div 
                                        style={{
                                            width: "100%",
                                            height: "100%",
                                            display: faculty.photo ? "none" : "flex",
                                            alignItems: "center",
                                            justifyContent: "center",
                                            backgroundColor: "#e3f2fd",
                                            fontSize: "60px"
                                        }}
                                    >
                                        👨‍🏫
                                    </div>
                                </div>

                                {/* Card Content */}
                                <div style={{ padding: "20px" }}>
                                    {/* Faculty Header */}
                                    <div style={{ 
                                        display: "flex", 
                                        alignItems: "center", 
                                        marginBottom: "15px",
                                        borderBottom: "2px solid #2196F3",
                                        paddingBottom: "12px"
                                    }}>
                                        <div style={{ flex: 1 }}>
                                            <h3 style={{ margin: "0", color: "#333", fontSize: "18px", fontWeight: "600" }}>
                                                {faculty.name}
                                            </h3>
                                            <p style={{ margin: "4px 0 0 0", color: "#666", fontSize: "12px" }}>
                                                ID: {faculty.id}
                                            </p>
                                        </div>
                                    </div>

                                    {/* Faculty Details */}
                                    <div style={{ marginBottom: "15px" }}>
                                        <div style={{ marginBottom: "12px" }}>
                                            <label style={{ display: "block", fontSize: "12px", color: "#999", textTransform: "uppercase", fontWeight: "600", marginBottom: "4px" }}>
                                                📧 Email
                                            </label>
                                            <p style={{ margin: "0", color: "#333", fontSize: "14px", wordBreak: "break-all" }}>
                                                {faculty.email}
                                            </p>
                                        </div>
                                        <div>
                                        <label style={{ display: "block", fontSize: "12px", color: "#999", textTransform: "uppercase", fontWeight: "600", marginBottom: "4px" }}>
                                            📚 Subject
                                        </label>
                                        <p style={{ margin: "0", color: "#2196F3", fontSize: "14px", fontWeight: "500", backgroundColor: "#e3f2fd", padding: "6px 10px", borderRadius: "4px", display: "inline-block" }}>
                                            {faculty.subject || "N/A"}
                                        </p>
                                    </div>
                                    <div style={{ marginTop: "12px" }}>
                                        <label style={{ display: "block", fontSize: "12px", color: "#999", textTransform: "uppercase", fontWeight: "600", marginBottom: "6px" }}>
                                            🎓 Assigned Classes
                                        </label>
                                        {faculty.classes && faculty.classes.length > 0 ? (
                                            <div style={{
                                                display: "flex",
                                                flexWrap: "wrap",
                                                gap: "6px"
                                            }}>
                                                {faculty.classes.map((cls) => (
                                                    <span key={cls} style={{
                                                        backgroundColor: "#81c784",
                                                        color: "white",
                                                        padding: "4px 10px",
                                                        borderRadius: "12px",
                                                        fontSize: "12px",
                                                        fontWeight: "500"
                                                    }}>
                                                        Class {cls}
                                                    </span>
                                                ))}
                                            </div>
                                        ) : (
                                            <p style={{ margin: "0", color: "#999", fontSize: "13px" }}>No classes assigned</p>
                                        )}
                                    </div>
                                </div>

                                {/* Action Button */}
                                <div style={{ display: "flex", gap: "10px", marginTop: "15px", padding: "0 20px 20px 20px" }}>
                                    <button
                                        onClick={() => handleEditFaculty(faculty)}
                                        disabled={loading}
                                        style={{
                                            flex: 1,
                                            padding: "10px 12px",
                                            backgroundColor: "#2196F3",
                                            color: "white",
                                            border: "none",
                                            borderRadius: "6px",
                                            cursor: "pointer",
                                            fontSize: "13px",
                                            fontWeight: "600",
                                            transition: "all 0.2s ease",
                                            opacity: loading ? 0.6 : 1
                                        }}
                                        onMouseEnter={(e) => {
                                            e.target.style.backgroundColor = "#1976D2";
                                        }}
                                        onMouseLeave={(e) => {
                                            e.target.style.backgroundColor = "#2196F3";
                                        }}
                                    >
                                        ✏️ Edit
                                    </button>
                                    <button
                                        onClick={() => handleDeleteFaculty(faculty.id)}
                                        disabled={loading}
                                        style={{
                                            flex: 1,
                                            padding: "10px 12px",
                                            backgroundColor: "#f44336",
                                            color: "white",
                                            border: "none",
                                            borderRadius: "6px",
                                            cursor: "pointer",
                                            fontSize: "13px",
                                            fontWeight: "600",
                                            transition: "all 0.2s ease",
                                            opacity: loading ? 0.6 : 1
                                        }}
                                        onMouseEnter={(e) => {
                                            e.target.style.backgroundColor = "#d32f2f";
                                        }}
                                        onMouseLeave={(e) => {
                                            e.target.style.backgroundColor = "#f44336";
                                        }}
                                    >
                                        🗑️ Delete
                                    </button>
                                </div>
                                </div>
                            </div>
                        ))}
                    </div>

                    {facultyList.length === 0 && (
                        <div style={{ 
                            textAlign: "center", 
                            padding: "40px 20px", 
                            color: "#999",
                            backgroundColor: "#f5f5f5",
                            borderRadius: "8px",
                            marginTop: "20px"
                        }}>
                            <p style={{ fontSize: "16px" }}>No faculty members added yet</p>
                        </div>
                    )}

                    {/* Edit Faculty Modal */}
                    {editingFaculty && (
                        <div style={{
                            position: "fixed",
                            top: 0,
                            left: 0,
                            right: 0,
                            bottom: 0,
                            backgroundColor: "rgba(0, 0, 0, 0.5)",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            zIndex: 1000
                        }}>
                            <div style={{
                                backgroundColor: "#ffffff",
                                padding: "30px",
                                borderRadius: "12px",
                                maxWidth: "500px",
                                width: "90%",
                                maxHeight: "85vh",
                                overflowY: "auto",
                                boxShadow: "0 10px 40px rgba(0, 0, 0, 0.3)"
                            }}>
                                <h2 style={{ marginTop: 0, color: "#333", marginBottom: "20px" }}>✏️ Edit Faculty</h2>
                                
                                <input
                                    type="text"
                                    placeholder="Faculty Name"
                                    value={editForm.name}
                                    onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                                    style={{
                                        width: "100%",
                                        padding: "12px",
                                        marginBottom: "12px",
                                        border: "1px solid #ddd",
                                        borderRadius: "6px",
                                        fontSize: "14px",
                                        boxSizing: "border-box"
                                    }}
                                />

                                <input
                                    type="email"
                                    placeholder="Email"
                                    value={editForm.email}
                                    onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                                    style={{
                                        width: "100%",
                                        padding: "12px",
                                        marginBottom: "12px",
                                        border: "1px solid #ddd",
                                        borderRadius: "6px",
                                        fontSize: "14px",
                                        boxSizing: "border-box"
                                    }}
                                />

                                <input
                                    type="text"
                                    placeholder="Subject"
                                    value={editForm.subject}
                                    onChange={(e) => setEditForm({ ...editForm, subject: e.target.value })}
                                    style={{
                                        width: "100%",
                                        padding: "12px",
                                        marginBottom: "12px",
                                        border: "1px solid #ddd",
                                        borderRadius: "6px",
                                        fontSize: "14px",
                                        boxSizing: "border-box"
                                    }}
                                />

                                {/* Classes Assignment Section */}
                                <div style={{ marginBottom: "15px" }}>
                                    <label style={{ display: "block", marginBottom: "8px", fontWeight: "600", color: "#333" }}>
                                        📚 Assign Classes
                                    </label>
                                    <div style={{
                                        display: "grid",
                                        gridTemplateColumns: "repeat(auto-fit, minmax(80px, 1fr))",
                                        gap: "8px",
                                        padding: "10px",
                                        backgroundColor: "#f9f9f9",
                                        borderRadius: "6px",
                                        border: "1px solid #ddd"
                                    }}>
                                        {["6", "7", "8", "9", "10", "11", "12"].map((cls) => (
                                            <label key={cls} style={{
                                                display: "flex",
                                                alignItems: "center",
                                                gap: "6px",
                                                cursor: "pointer",
                                                padding: "8px",
                                                backgroundColor: editForm.classes.includes(cls) ? "#e3f2fd" : "white",
                                                borderRadius: "4px",
                                                border: editForm.classes.includes(cls) ? "2px solid #2196F3" : "1px solid #ddd"
                                            }}>
                                                <input
                                                    type="checkbox"
                                                    checked={editForm.classes.includes(cls)}
                                                    onChange={(e) => {
                                                        if (e.target.checked) {
                                                            setEditForm({ 
                                                                ...editForm, 
                                                                classes: [...editForm.classes, cls] 
                                                            });
                                                        } else {
                                                            setEditForm({ 
                                                                ...editForm, 
                                                                classes: editForm.classes.filter(c => c !== cls) 
                                                            });
                                                        }
                                                    }}
                                                    style={{ cursor: "pointer" }}
                                                />
                                                <span style={{ userSelect: "none" }}>Class {cls}</span>
                                            </label>
                                        ))}
                                    </div>
                                </div>

                                {/* Photo Upload in Edit Modal */}
                                <div style={{ marginBottom: "15px" }}>
                                    <label style={{ display: "block", marginBottom: "8px", fontWeight: "600", color: "#333" }}>
                                        📸 Update Faculty Photo
                                    </label>
                                    <div style={{ display: "flex", gap: "12px", alignItems: "flex-start" }}>
                                        <div style={{ flex: 1 }}>
                                            <input
                                                type="file"
                                                accept="image/*"
                                                onChange={handlePhotoUploadEdit}
                                                style={{
                                                    width: "100%",
                                                    padding: "10px",
                                                    border: "2px dashed #2196F3",
                                                    borderRadius: "6px",
                                                    cursor: "pointer",
                                                    backgroundColor: "#f8f9fa",
                                                    boxSizing: "border-box"
                                                }}
                                            />
                                        </div>
                                        {editForm.photo && (
                                            <div style={{
                                                width: "80px",
                                                height: "80px",
                                                borderRadius: "6px",
                                                overflow: "hidden",
                                                border: "2px solid #2196F3",
                                                display: "flex",
                                                alignItems: "center",
                                                justifyContent: "center",
                                                backgroundColor: "#f0f0f0",
                                                flexShrink: 0
                                            }}>
                                                <img 
                                                    src={editForm.photo}
                                                    alt="Preview"
                                                    style={{
                                                        width: "100%",
                                                        height: "100%",
                                                        objectFit: "cover"
                                                    }}
                                                />
                                            </div>
                                        )}
                                    </div>
                                </div>

                                {/* Modal Action Buttons */}
                                <div style={{ display: "flex", gap: "10px", marginTop: "20px" }}>
                                    <button
                                        onClick={handleUpdateFaculty}
                                        disabled={loading}
                                        style={{
                                            flex: 1,
                                            padding: "12px",
                                            backgroundColor: "#4CAF50",
                                            color: "white",
                                            border: "none",
                                            borderRadius: "6px",
                                            cursor: "pointer",
                                            fontSize: "14px",
                                            fontWeight: "600",
                                            transition: "all 0.2s ease"
                                        }}
                                    >
                                        💾 Save Changes
                                    </button>
                                    <button
                                        onClick={handleCancelEdit}
                                        disabled={loading}
                                        style={{
                                            flex: 1,
                                            padding: "12px",
                                            backgroundColor: "#757575",
                                            color: "white",
                                            border: "none",
                                            borderRadius: "6px",
                                            cursor: "pointer",
                                            fontSize: "14px",
                                            fontWeight: "600",
                                            transition: "all 0.2s ease"
                                        }}
                                    >
                                        ✕ Cancel
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}

                </div>
            )}

            {/* Student Management Tab */}
            {activeTab === "student" && (
                <div style={tabStyle}>
                    <h2>👨‍🎓 Manage Students</h2>
                    <div style={{ marginBottom: "20px", padding: "15px", backgroundColor: "#f9f9f9", borderRadius: "4px" }}>
                        <h3>Add New Student</h3>
                        <input
                            type="text"
                            placeholder="Student Name"
                            value={studentForm.name}
                            onChange={(e) => setStudentForm({ ...studentForm, name: e.target.value })}
                            style={inputStyle}
                        />
                        <input
                            type="text"
                            placeholder="Roll Number"
                            value={studentForm.rollno}
                            onChange={(e) => setStudentForm({ ...studentForm, rollno: e.target.value })}
                            style={inputStyle}
                        />
                        <input
                            type="text"
                            placeholder="Class"
                            value={studentForm.class}
                            onChange={(e) => setStudentForm({ ...studentForm, class: e.target.value })}
                            style={inputStyle}
                        />
                        <input
                            type="email"
                            placeholder="Email"
                            value={studentForm.email}
                            onChange={(e) => setStudentForm({ ...studentForm, email: e.target.value })}
                            style={inputStyle}
                        />
                        <button
                            onClick={handleAddStudent}
                            disabled={loading}
                            style={{ ...buttonStyle, backgroundColor: "#4CAF50", color: "white" }}
                        >
                            Add Student
                        </button>
                    </div>
                    <h3>Students List</h3>
                    <input 
                        type="text"
                        placeholder="🔍 Search students by name, roll no, class, or email..."
                        value={studentSearch}
                        onChange={(e) => setStudentSearch(e.target.value)}
                        style={{
                            width: "100%",
                            padding: "12px",
                            marginBottom: "20px",
                            border: "1px solid #ddd",
                            borderRadius: "6px",
                            fontSize: "14px",
                            boxSizing: "border-box"
                        }}
                    />
                    <div style={{ 
                        maxHeight: "600px", 
                        overflowY: "auto", 
                        border: "1px solid #ddd", 
                        borderRadius: "4px",
                        boxShadow: "0 2px 4px rgba(0,0,0,0.1)"
                    }}>
                        <table style={{ width: "100%", borderCollapse: "collapse" }}>
                            <thead style={{ position: "sticky", top: 0, zIndex: 10 }}>
                                <tr style={{ backgroundColor: "#2196F3", color: "white" }}>
                                    <th style={{ padding: "10px", textAlign: "left", border: "1px solid #ddd" }}>Name</th>
                                    <th style={{ padding: "10px", textAlign: "left", border: "1px solid #ddd" }}>Roll No</th>
                                    <th style={{ padding: "10px", textAlign: "left", border: "1px solid #ddd" }}>Class</th>
                                    <th style={{ padding: "10px", textAlign: "left", border: "1px solid #ddd" }}>Email</th>
                                </tr>
                            </thead>
                            <tbody>
                                {!studentList || studentList.length === 0 ? (
                                    <tr>
                                        <td colSpan="4" style={{ padding: "20px", textAlign: "center", color: "#666" }}>
                                            No students found. Add a new student to get started.
                                        </td>
                                    </tr>
                                ) : (
                                    studentList
                                        .filter(student => 
                                            (student.name && student.name.toLowerCase().includes(studentSearch.toLowerCase())) ||
                                            (student.rollno && student.rollno.toString().toLowerCase().includes(studentSearch.toLowerCase())) ||
                                            (student.class && student.class.toLowerCase().includes(studentSearch.toLowerCase())) ||
                                            (student.email && student.email.toLowerCase().includes(studentSearch.toLowerCase()))
                                        )
                                        .map((student, idx) => (
                                        <tr key={idx} style={{ backgroundColor: idx % 2 === 0 ? "#fff" : "#f5f5f5" }}>
                                            <td style={{ padding: "10px", border: "1px solid #ddd" }}>{student.name || '-'}</td>
                                            <td style={{ padding: "10px", border: "1px solid #ddd" }}>{student.rollno || '-'}</td>
                                            <td style={{ padding: "10px", border: "1px solid #ddd" }}>{student.class || '-'}</td>
                                            <td style={{ padding: "10px", border: "1px solid #ddd" }}>{student.email || '-'}</td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* Holidays Tab */}
            {activeTab === "holidays" && (
                <div style={tabStyle}>
                    <h2>🏖️ Manage Holidays</h2>
                    <div style={{ marginBottom: "20px", padding: "15px", backgroundColor: "#f9f9f9", borderRadius: "4px" }}>
                        <h3>Add Holiday</h3>
                        <input
                            type="date"
                            value={holidayForm.date}
                            onChange={(e) => setHolidayForm({ ...holidayForm, date: e.target.value })}
                            style={inputStyle}
                        />
                        <input
                            type="text"
                            placeholder="Holiday Name"
                            value={holidayForm.name}
                            onChange={(e) => setHolidayForm({ ...holidayForm, name: e.target.value })}
                            style={inputStyle}
                        />
                        <button
                            onClick={handleAddHoliday}
                            disabled={loading}
                            style={{ ...buttonStyle, backgroundColor: "#4CAF50", color: "white" }}
                        >
                            Add Holiday
                        </button>
                    </div>
                    <h3>Holidays List</h3>
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                        <thead>
                            <tr style={{ backgroundColor: "#2196F3", color: "white" }}>
                                <th style={{ padding: "10px", textAlign: "left", border: "1px solid #ddd" }}>Date</th>
                                <th style={{ padding: "10px", textAlign: "left", border: "1px solid #ddd" }}>Name</th>
                                <th style={{ padding: "10px", textAlign: "center", border: "1px solid #ddd", width: "80px" }}>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {holidayList.map((holiday, idx) => (
                                <tr key={idx} style={{ backgroundColor: idx % 2 === 0 ? "#fff" : "#f5f5f5" }}>
                                    <td style={{ padding: "10px", border: "1px solid #ddd" }}>{holiday.date}</td>
                                    <td style={{ padding: "10px", border: "1px solid #ddd" }}>{holiday.name}</td>
                                    <td style={{ padding: "10px", border: "1px solid #ddd", textAlign: "center" }}>
                                        <button
                                            onClick={() => handleDeleteHoliday(holiday.id)}
                                            disabled={loading}
                                            style={{
                                                padding: "6px 12px",
                                                backgroundColor: "#f44336",
                                                color: "white",
                                                border: "none",
                                                borderRadius: "4px",
                                                cursor: "pointer",
                                                fontSize: "12px"
                                            }}
                                        >
                                            🗑️ Delete
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Workload Management Tab */}
            {activeTab === "workload" && (
                <div style={tabStyle}>
                    <h2>⏱️ Faculty Workload Management</h2>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center', marginBottom: '12px' }}>
                        <label style={{ marginRight: '8px', fontWeight: 600 }}>Month:</label>
                        <select
                            value={selectedMonth}
                            onChange={(e) => setSelectedMonth(e.target.value)}
                            style={{ padding: '8px', borderRadius: '6px', border: '1px solid #ddd', minWidth: '220px' }}
                        >
                            <option value="">-- Select month (or leave blank for all-time) --</option>
                            {availableMonths.map((m, i) => (
                                <option key={i} value={m}>{m}</option>
                            ))}
                        </select>
                    </div>
                    <button
                        onClick={() => fetchFacultyWorkload(selectedMonth)}
                        disabled={loading || !selectedMonth}
                        style={{ ...buttonStyle, backgroundColor: "#2196F3", color: "white" }}
                    >
                        🔄 Refresh Workload
                    </button>
                    {!selectedMonth && (
                        <div style={{ marginTop: 28, padding: 40, textAlign: 'center', color: '#9e9e9e', border: '2px dashed #eee', borderRadius: 8 }}>
                            <div style={{ fontSize: 20, marginBottom: 8 }}>📅 Select a month to view workload</div>
                            <div style={{ fontSize: 14 }}>No month selected — workload will appear here once you choose a month.</div>
                        </div>
                    )}
                    {/* Adjust Overload removed */}
                    {facultyWorkloadData.length > 0 && (
                        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "20px" }}>
                            <thead>
                                <tr style={{ backgroundColor: "#2196F3", color: "white" }}>
                                    <th style={{ padding: "12px", textAlign: "left", border: "1px solid #ddd" }}>Faculty</th>
                                    <th style={{ padding: "12px", textAlign: "left", border: "1px solid #ddd" }}>Subject</th>
                                    <th style={{ padding: "12px", textAlign: "left", border: "1px solid #ddd" }}>Hours</th>
                                </tr>
                            </thead>
                            <tbody>
                                {facultyWorkloadData.map((faculty, idx) => {
                                    const isOverloaded = faculty.hours > 20;
                                    return (
                                        <tr key={idx} style={{ backgroundColor: idx % 2 === 0 ? "#fff" : "#f5f5f5" }}>
                                            <td style={{ padding: "12px", border: "1px solid #ddd" }}>{faculty.name}</td>
                                            <td style={{ padding: "12px", border: "1px solid #ddd" }}>{faculty.subject}</td>
                                            <td style={{ padding: "12px", border: "1px solid #ddd", fontWeight: "bold" }}>{faculty.hours}</td>
                                            
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    )}
                    {showAdjustmentResults && adjustmentResults.length > 0 && (
                        <div style={{ marginTop: "30px", padding: "15px", backgroundColor: "#e8f5e9", border: "2px solid #4CAF50", borderRadius: "4px" }}>
                            <h3>✓ Adjustment Results</h3>
                            <table style={{ width: "100%", borderCollapse: "collapse" }}>
                                <thead>
                                    <tr style={{ backgroundColor: "#4CAF50", color: "white" }}>
                                        <th style={{ padding: "10px", textAlign: "left", border: "1px solid #4CAF50" }}>Date</th>
                                        <th style={{ padding: "10px", textAlign: "left", border: "1px solid #4CAF50" }}>Class</th>
                                        <th style={{ padding: "10px", textAlign: "left", border: "1px solid #4CAF50" }}>From → To</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {adjustmentResults.map((adj, idx) => (
                                        <tr key={idx} style={{ backgroundColor: "#f1f8e9" }}>
                                            <td style={{ padding: "10px", border: "1px solid #c8e6c9" }}>{adj.date}</td>
                                            <td style={{ padding: "10px", border: "1px solid #c8e6c9" }}>{adj.class}</td>
                                            <td style={{ padding: "10px", border: "1px solid #c8e6c9" }}>{adj.from_faculty_name} → {adj.to_faculty_name}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}

            {/* Timetable Tab */}
            {activeTab === "timetable" && <Timetable />}

            {/* Leave Management Tab */}
            {activeTab === "leaves" && (
                <div style={tabStyle}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
                        <h2 style={{ margin: 0 }}>📋 Leave Management</h2>
                        <button
                            onClick={() => fetchLeaves(true)}
                            disabled={loading}
                            style={{ ...buttonStyle, backgroundColor: "#2196F3", color: "white", marginBottom: 0 }}
                        >
                            🔄 Refresh Leaves
                        </button>
                    </div>

                    {/* Pending Leave Requests */}
                    <div style={{ marginBottom: "40px" }}>
                        <h3 style={{ color: "#d32f2f", borderBottom: "3px solid #d32f2f", paddingBottom: "10px" }}>
                            ⏳ Pending Leave Requests ({leaves.filter(l => l.status === "pending").length})
                        </h3>
                        {leaves.filter(l => l.status === "pending").length > 0 ? (
                            <div style={{ overflowX: "auto", border: "1px solid #ddd", borderRadius: "4px", marginTop: "15px" }}>
                                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                                    <thead>
                                        <tr style={{ backgroundColor: "#ffebee", borderBottom: "2px solid #d32f2f" }}>
                                            <th style={{ padding: "12px", textAlign: "left", border: "1px solid #ddd", fontWeight: "bold", color: "#d32f2f" }}>Faculty Name</th>
                                            <th style={{ padding: "12px", textAlign: "left", border: "1px solid #ddd", fontWeight: "bold", color: "#d32f2f" }}>Leave Date</th>
                                            <th style={{ padding: "12px", textAlign: "left", border: "1px solid #ddd", fontWeight: "bold", color: "#d32f2f" }}>Reason</th>
                                            <th style={{ padding: "12px", textAlign: "center", border: "1px solid #ddd", fontWeight: "bold", color: "#d32f2f" }}>Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {leaves.filter(l => l.status === "pending").map((leave, idx) => (
                                            <tr key={idx} style={{ backgroundColor: idx % 2 === 0 ? "#fff" : "#fafafa" }}>
                                                <td style={{ padding: "12px", border: "1px solid #ddd", fontWeight: "500" }}>
                                                    {leave.faculty_name || "N/A"}
                                                </td>
                                                <td style={{ padding: "12px", border: "1px solid #ddd" }}>
                                                    {leave.date || "N/A"}
                                                </td>
                                                <td style={{ padding: "12px", border: "1px solid #ddd" }}>
                                                    {leave.reason || "-"}
                                                </td>
                                                <td style={{ padding: "12px", border: "1px solid #ddd", textAlign: "center" }}>
                                                    <div style={{ display: "flex", gap: "8px", justifyContent: "center" }}>
                                                        <button
                                                            onClick={() => approveLeave(leave.id || leave._id)}
                                                            disabled={loading}
                                                            style={{
                                                                padding: "8px 16px",
                                                                backgroundColor: "#4CAF50",
                                                                color: "white",
                                                                border: "none",
                                                                borderRadius: "4px",
                                                                cursor: "pointer",
                                                                fontSize: "12px",
                                                                fontWeight: "bold"
                                                            }}
                                                        >
                                                            ✓ Approve
                                                        </button>
                                                        <button
                                                            onClick={() => {
                                                                const reason = prompt("Enter rejection reason:");
                                                                if (reason) rejectLeave(leave.id || leave._id, reason);
                                                            }}
                                                            disabled={loading}
                                                            style={{
                                                                padding: "8px 16px",
                                                                backgroundColor: "#d32f2f",
                                                                color: "white",
                                                                border: "none",
                                                                borderRadius: "4px",
                                                                cursor: "pointer",
                                                                fontSize: "12px",
                                                                fontWeight: "bold"
                                                            }}
                                                        >
                                                            ✗ Reject
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        ) : (
                            <div style={{ padding: "20px", textAlign: "center", color: "#999", backgroundColor: "#f5f5f5", borderRadius: "4px", marginTop: "15px" }}>
                                <p>✓ No pending requests</p>
                            </div>
                        )}
                    </div>

                    {/* Leave History (Approved & Rejected) */}
                    <div>
                        <h3 style={{ color: "#2196F3", borderBottom: "3px solid #2196F3", paddingBottom: "10px" }}>
                            📊 Leave History ({leaves.filter(l => l.status !== "pending").length})
                        </h3>
                        {leaves.filter(l => l.status !== "pending").length > 0 ? (
                            <div style={{ overflowX: "auto", border: "1px solid #ddd", borderRadius: "4px", marginTop: "15px" }}>
                                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                                    <thead>
                                        <tr style={{ backgroundColor: "#e3f2fd", borderBottom: "2px solid #2196F3" }}>
                                            <th style={{ padding: "12px", textAlign: "left", border: "1px solid #ddd", fontWeight: "bold", color: "#2196F3" }}>Faculty Name</th>
                                            <th style={{ padding: "12px", textAlign: "left", border: "1px solid #ddd", fontWeight: "bold", color: "#2196F3" }}>Leave Date</th>
                                            <th style={{ padding: "12px", textAlign: "left", border: "1px solid #ddd", fontWeight: "bold", color: "#2196F3" }}>Reason</th>
                                            <th style={{ padding: "12px", textAlign: "center", border: "1px solid #ddd", fontWeight: "bold", color: "#2196F3" }}>Status</th>
                                            <th style={{ padding: "12px", textAlign: "left", border: "1px solid #ddd", fontWeight: "bold", color: "#2196F3" }}>Note</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {leaves.filter(l => l.status !== "pending").map((leave, idx) => {
                                            const isApproved = leave.status === "approved";
                                            const statusColor = isApproved ? "#4CAF50" : "#d32f2f";
                                            const statusText = isApproved ? "✓ APPROVED" : "✗ REJECTED";
                                            const rowBg = isApproved ? "#f1f8e9" : "#ffebee";
                                            
                                            return (
                                                <tr key={idx} style={{ backgroundColor: rowBg }}>
                                                    <td style={{ padding: "12px", border: "1px solid #ddd", fontWeight: "500" }}>
                                                        {leave.faculty_name || "N/A"}
                                                    </td>
                                                    <td style={{ padding: "12px", border: "1px solid #ddd" }}>
                                                        {leave.date || "N/A"}
                                                    </td>
                                                    <td style={{ padding: "12px", border: "1px solid #ddd" }}>
                                                        {leave.reason || "-"}
                                                    </td>
                                                    <td style={{ padding: "12px", border: "1px solid #ddd", textAlign: "center" }}>
                                                        <span style={{
                                                            backgroundColor: statusColor,
                                                            color: "white",
                                                            padding: "6px 12px",
                                                            borderRadius: "4px",
                                                            fontSize: "12px",
                                                            fontWeight: "bold"
                                                        }}>
                                                            {statusText}
                                                        </span>
                                                    </td>
                                                    <td style={{ padding: "12px", border: "1px solid #ddd", fontSize: "12px", color: "#666" }}>
                                                        {leave.rejection_reason || "-"}
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        ) : (
                            <div style={{ padding: "20px", textAlign: "center", color: "#999", backgroundColor: "#f5f5f5", borderRadius: "4px", marginTop: "15px" }}>
                                <p>No processed requests</p>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

export default AdminDashboard;
