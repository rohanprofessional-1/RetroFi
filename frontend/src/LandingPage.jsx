import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

function LandingPage() {
  const [address, setAddress] = useState('');
  const navigate = useNavigate();

  const handleSearch = (e) => {
    e.preventDefault();
    if (address.trim()) {
      // Pass the address to the dashboard route
      navigate(`/dashboard?address=${encodeURIComponent(address)}`);
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
      background: 'radial-gradient(circle at 50% -20%, #1e293b, #0f172a)'
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
            placeholder="Enter your address (e.g. 123 Peachtree St)"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            required
          />
          <button type="submit" className="btn-primary" style={{ padding: '1rem', fontSize: '1.1rem' }}>
            Get Retrofit Plan
          </button>
        </form>
      </div>

      {/* Decorative background elements */}
      <div style={{
        position: 'absolute',
        top: '20%',
        left: '10%',
        width: '300px',
        height: '300px',
        background: 'var(--accent-primary)',
        filter: 'blur(150px)',
        opacity: '0.15',
        zIndex: -1,
        borderRadius: '50%'
      }}></div>
      <div style={{
        position: 'absolute',
        bottom: '20%',
        right: '10%',
        width: '400px',
        height: '400px',
        background: '#8b5cf6',
        filter: 'blur(150px)',
        opacity: '0.15',
        zIndex: -1,
        borderRadius: '50%'
      }}></div>
    </div>
  );
}

export default LandingPage;
