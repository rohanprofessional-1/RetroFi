import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

function LandingPage() {
  const [address, setAddress] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleSearch = async (e) => {
    e.preventDefault();
    const trimmed = address.trim();
    if (!trimmed) return;

    setLoading(true);
    setError('');

    try {
      const res = await fetch('/api/property-lookup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address: trimmed }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Server error: ${res.status}`);
      }

      const { pre_filled, meta } = await res.json();
      navigate('/verify', { state: { pre_filled, meta, address: trimmed } });
    } catch (err) {
      setError(err.message || 'Could not find that address. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '2rem',
      background: 'radial-gradient(circle at 50% -20%, #1e293b, #0f172a)',
    }}>
      <div className="glass-panel animate-fade-in" style={{ maxWidth: '600px', width: '100%', textAlign: 'center' }}>
        <h1 style={{ fontSize: '3rem', marginBottom: '1rem' }}>
          <span className="text-gradient">RetroFi ATL</span>
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '1.25rem', marginBottom: '2rem' }}>
          Instantly discover how to cut your energy bills and carbon footprint. Enter your Atlanta home address to get your AI-powered retrofit plan.
        </p>

        <form onSubmit={handleSearch} style={{ display: 'flex', gap: '1rem', flexDirection: 'column' }}>
          <input
            type="text"
            className="input-premium"
            placeholder="Enter your address (e.g. 123 Peachtree St NE, Atlanta, GA)"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            disabled={loading}
            required
          />

          {error && (
            <p style={{ color: '#f87171', fontSize: '0.9rem', textAlign: 'left', margin: 0 }}>
              {error}
            </p>
          )}

          <button
            type="submit"
            className="btn-primary"
            style={{ padding: '1rem', fontSize: '1.1rem', opacity: loading ? 0.7 : 1 }}
            disabled={loading}
          >
            {loading ? 'Looking up your property…' : 'Get Retrofit Plan'}
          </button>
        </form>
      </div>

      <div style={{
        position: 'absolute', top: '20%', left: '10%',
        width: '300px', height: '300px',
        background: 'var(--accent-primary)', filter: 'blur(150px)',
        opacity: '0.15', zIndex: -1, borderRadius: '50%',
      }} />
      <div style={{
        position: 'absolute', bottom: '20%', right: '10%',
        width: '400px', height: '400px',
        background: '#8b5cf6', filter: 'blur(150px)',
        opacity: '0.15', zIndex: -1, borderRadius: '50%',
      }} />
    </div>
  );
}

export default LandingPage;
