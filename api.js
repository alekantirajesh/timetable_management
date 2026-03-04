import axios from 'axios';

const api = axios.create({
    baseURL: "http://localhost:5000",
    headers: {
        'Content-Type': 'application/json'
    }
});

// Add token to requests if available
api.interceptors.request.use(config => {
    const token = localStorage.getItem('auth_token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Handle responses
api.interceptors.response.use(
    response => response,
    error => {
        try {
            const status = error.response?.status;
            const url = error.config?.url || error.response?.config?.url || 'unknown';
            const method = error.config?.method || 'unknown';
            console.error(`[API] Request failed: ${method.toUpperCase()} ${url} -> ${status}`, error.response?.data || error.message);

            if (status === 401) {
                // Remove token to avoid reuse
                localStorage.removeItem('auth_token');
                // Avoid redirect loop if already on login page
                if (typeof window !== 'undefined' && window.location && window.location.pathname !== '/login') {
                    window.location.href = '/login';
                }
            }
        } catch (ex) {
            console.error('[API] Error in response interceptor logging', ex);
        }
        return Promise.reject(error);
    }
);

export default api;
