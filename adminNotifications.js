import { useState, useEffect } from "react";
import api from "../api";

export default function AdminNotifications() {
    const [cards, setCards] = useState([]);
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState("");

    useEffect(() => { fetchCards(); }, []);

    const fetchCards = async () => {
        try {
            setLoading(true);
            const res = await api.get('/admin/notifications');
            setCards(res.data || []);
        } catch (err) {
            console.error(err);
            setMessage('❌ Failed to load notifications');
            setCards([]);
        } finally { setLoading(false); }
    };

    const markRead = async (id) => {
        try {
            setLoading(true);
            await api.put(`/admin/notifications/${id}/read`);
            setMessage('✅ Marked read');
            fetchCards();
        } catch (err) {
            console.error(err);
            setMessage('❌ Failed to mark read');
        } finally { setLoading(false); }
    };

    const severityColor = (sev) => {
        if (sev === 'critical') return '#f8d7da';
        if (sev === 'warning') return '#fff3cd';
        return '#e2f0ff';
    };

    return (
        <div style={{ padding: 16 }}>
            <h2>Admin Notifications</h2>
            {message && <div style={{ marginBottom: 12 }}>{message}</div>}
            {loading && <div>Loading...</div>}
            {!loading && cards.length === 0 && <div>No notifications</div>}
            <div style={{ display: 'grid', gap: 12 }}>
                {cards.map(card => (
                    <div key={card.id} style={{ padding: 12, borderRadius: 6, backgroundColor: severityColor(card.severity), border: card.read ? '1px solid #ccc' : '2px solid #1976d2' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div>
                                <strong style={{ fontSize: 16 }}>{card.title}</strong>
                                <div style={{ fontSize: 12, color: '#555' }}>{card.summary}</div>
                            </div>
                            <div style={{ textAlign: 'right' }}>
                                <div style={{ fontSize: 12 }}>{new Date(card.created_at).toLocaleString()}</div>
                                {!card.read && <button onClick={() => markRead(card.id)} style={{ marginTop: 8, padding: '6px 10px' }}>Mark read</button>}
                            </div>
                        </div>
                        {card.details && card.details.length > 0 && (
                            <ul style={{ marginTop: 10 }}>
                                {card.details.map((d, i) => <li key={i} style={{ fontSize: 13 }}>{d}</li>)}
                            </ul>
                        )}
                        {card.related && Object.keys(card.related).length > 0 && (
                            <div style={{ marginTop: 8, fontSize: 13, color: '#333' }}>
                                <strong>Related:</strong> {JSON.stringify(card.related)}
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
