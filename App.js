import { useState, useEffect } from 'react';
import './App.css';
import api from './api';
import Login from './pages/Login';
import AdminDashboard from './pages/adminDashboard';
import FacultyDashboard from './pages/facultyDashboard';
import StudentDashboard from './pages/studentDashboard';

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if user is already logged in by checking localStorage
    const token = localStorage.getItem('auth_token');
    const role = localStorage.getItem('user_role');
    
    if (token && role) {
      // User is already logged in
      setUser({ role });
    }
    
    setLoading(false);
  }, []);

  if (loading) {
    return <div>Loading...</div>;
  }

  if (!user) {
    return <Login onLoginSuccess={(role) => setUser({ role })} />;
  }

  switch (user.role) {
    case 'admin':
      return <AdminDashboard />;
    case 'faculty':
      return <FacultyDashboard />;
    case 'student':
      return <StudentDashboard />;
    default:
      return <div>Unknown role</div>;
  }
}

export default App;

