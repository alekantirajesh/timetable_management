import { useState } from 'react';
import api from '../api';

function Login({ onLoginSuccess }) {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [userType, setUserType] = useState('student');
    const [showPassword, setShowPassword] = useState(false);

    const handleLogin = async (e) => {
        e.preventDefault();
        try {
            setLoading(true);
            setError('');

            if (!email || !password) {
                setError('Please enter email and password');
                setLoading(false);
                return;
            }

            // Call backend login endpoint
            const response = await api.post('/login', {
                email,
                password,
                user_type: userType
            });

            if (response.data && response.data.token) {
                localStorage.setItem('auth_token', response.data.token);
                localStorage.setItem('user_role', response.data.role);
                localStorage.setItem('user_id', response.data.user_id);
                // store explicit faculty_id when backend provided one
                if (response.data.faculty_id) {
                    localStorage.setItem('faculty_id', response.data.faculty_id);
                }
                if (response.data.student_class) {
                    localStorage.setItem('student_class', response.data.student_class);
                }
                
                onLoginSuccess(response.data.role);
                // Ensure browser address bar shows root after login (no router used)
                if (typeof window !== 'undefined' && window.history && window.history.replaceState) {
                    window.history.replaceState({}, '', '/');
                }
            }
        } catch (err) {
            setError(err.response?.data?.message || 'Login failed. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const userRoles = {
        student: { emoji: '👨‍🎓', label: 'Student', color: '#4CAF50' },
        faculty: { emoji: '👨‍🏫', label: 'Faculty', color: '#2196F3' },
        admin: { emoji: '⚙️', label: 'Admin', color: '#FF9800' }
    };

    return (
        <div style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            minHeight: '100vh',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            fontFamily: '"Segoe UI", Tahoma, Geneva, Verdana, sans-serif',
            padding: '20px'
        }}>
            {/* Decorative Background */}
            <div style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                opacity: 0.1,
                background: 'url("data:image/svg+xml,%3Csvg width="60" height="60" viewBox="0 0 60 60"%3E%3Cg fill="white"%3E%3Ccircle cx="30" cy="30" r="20"/%3E%3Ccircle cx="10" cy="10" r="8"/%3E%3Ccircle cx="50" cy="50" r="12"/%3E%3C/g%3E%3C/svg%3E")',
                pointerEvents: 'none'
            }} />

            <div style={{
                backgroundColor: '#fff',
                padding: '50px 40px',
                borderRadius: '16px',
                boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
                width: '100%',
                maxWidth: '420px',
                position: 'relative',
                zIndex: 1,
                animation: 'slideUp 0.5s ease-out'
            }}>
                {/* Header */}
                <div style={{ textAlign: 'center', marginBottom: '40px' }}>
                    <div style={{ fontSize: '48px', marginBottom: '15px' }}>📚</div>
                    <h1 style={{ 
                        textAlign: 'center', 
                        color: '#333', 
                        marginBottom: '8px',
                        fontSize: '28px',
                        fontWeight: '700'
                    }}>
                        Smart Faculty Workload and Timetable Management System
                    </h1>
                    <p style={{ 
                        textAlign: 'center', 
                        color: '#999', 
                        fontSize: '14px'
                    }}>
                        Intelligent scheduling and workload distribution
                    </p>
                </div>

                {error && (
                    <div style={{
                        backgroundColor: '#ffebee',
                        color: '#c62828',
                        padding: '12px 16px',
                        borderRadius: '8px',
                        marginBottom: '20px',
                        border: '1px solid #ef5350',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        fontSize: '14px'
                    }}>
                        ❌ {error}
                    </div>
                )}

                <form onSubmit={handleLogin}>
                    {/* User Type Selection */}
                    <div style={{ marginBottom: '30px' }}>
                        <label style={{ display: 'block', marginBottom: '12px', fontWeight: '600', color: '#333', fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                            Login As
                        </label>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
                            {['student', 'faculty', 'admin'].map(type => (
                                <button
                                    key={type}
                                    type="button"
                                    onClick={() => setUserType(type)}
                                    style={{
                                        padding: '12px',
                                        border: userType === type ? `2px solid ${userRoles[type].color}` : '2px solid #e0e0e0',
                                        borderRadius: '8px',
                                        backgroundColor: userType === type ? `${userRoles[type].color}15` : '#f8f8f8',
                                        color: userType === type ? userRoles[type].color : '#666',
                                        cursor: 'pointer',
                                        fontWeight: '600',
                                        fontSize: '12px',
                                        transition: 'all 0.3s ease',
                                        display: 'flex',
                                        flexDirection: 'column',
                                        alignItems: 'center',
                                        gap: '4px'
                                    }}
                                    onMouseEnter={(e) => e.target.style.transform = 'translateY(-2px)'}
                                    onMouseLeave={(e) => e.target.style.transform = 'translateY(0)'}
                                >
                                    <span style={{ fontSize: '20px' }}>{userRoles[type].emoji}</span>
                                    {userRoles[type].label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Email */}
                    <div style={{ marginBottom: '20px' }}>
                        <label style={{ display: 'block', marginBottom: '8px', fontWeight: '600', color: '#333', fontSize: '13px' }}>
                            📧 Email Address
                        </label>
                        <input
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            placeholder="Enter your email"
                            style={{
                                width: '100%',
                                padding: '12px 14px',
                                border: '2px solid #e0e0e0',
                                borderRadius: '8px',
                                fontSize: '14px',
                                boxSizing: 'border-box',
                                transition: 'all 0.3s ease',
                                outline: 'none'
                            }}
                            onFocus={(e) => e.target.style.borderColor = '#667eea'}
                            onBlur={(e) => e.target.style.borderColor = '#e0e0e0'}
                        />
                    </div>

                    {/* Password */}
                    <div style={{ marginBottom: '25px' }}>
                        <label style={{ display: 'block', marginBottom: '8px', fontWeight: '600', color: '#333', fontSize: '13px' }}>
                            🔐 Password
                        </label>
                        <div style={{ position: 'relative' }}>
                            <input
                                type={showPassword ? 'text' : 'password'}
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="Enter your password"
                                style={{
                                    width: '100%',
                                    padding: '12px 14px 12px 14px',
                                    border: '2px solid #e0e0e0',
                                    borderRadius: '8px',
                                    fontSize: '14px',
                                    boxSizing: 'border-box',
                                    transition: 'all 0.3s ease',
                                    outline: 'none',
                                    paddingRight: '40px'
                                }}
                                onFocus={(e) => e.target.style.borderColor = '#667eea'}
                                onBlur={(e) => e.target.style.borderColor = '#e0e0e0'}
                            />
                            <button
                                type="button"
                                onClick={() => setShowPassword(!showPassword)}
                                style={{
                                    position: 'absolute',
                                    right: '12px',
                                    top: '50%',
                                    transform: 'translateY(-50%)',
                                    border: 'none',
                                    background: 'none',
                                    cursor: 'pointer',
                                    fontSize: '16px'
                                }}
                            >
                                {showPassword ? '👁️' : '👁️‍🗨️'}
                            </button>
                        </div>
                    </div>

                    {/* Login Button */}
                    <button
                        type="submit"
                        disabled={loading}
                        style={{
                            width: '100%',
                            padding: '13px',
                            background: loading ? '#ccc' : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                            color: 'white',
                            border: 'none',
                            borderRadius: '8px',
                            fontSize: '15px',
                            fontWeight: '700',
                            cursor: loading ? 'not-allowed' : 'pointer',
                            transition: 'all 0.3s ease',
                            boxShadow: loading ? 'none' : '0 4px 15px rgba(102, 126, 234, 0.4)',
                            letterSpacing: '0.5px'
                        }}
                        onMouseEnter={(e) => !loading && (e.target.style.transform = 'translateY(-2px)')}
                        onMouseLeave={(e) => !loading && (e.target.style.transform = 'translateY(0)')}
                    >
                        {loading ? '🔄 Logging in...' : '✨ Login'}
                    </button>
                </form>
            </div>

            <style>{`
                @keyframes slideUp {
                    from {
                        opacity: 0;
                        transform: translateY(20px);
                    }
                    to {
                        opacity: 1;
                        transform: translateY(0);
                    }
                }
            `}</style>
        </div>
    );
}

export default Login;

