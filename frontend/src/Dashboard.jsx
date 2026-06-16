import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';

const currency = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

function Dashboard() {
  const location = useLocation();
  const navigate = useNavigate();
  const result = location.state?.result;
  const [selectedOption, setSelectedOption] = useState(null);

  useEffect(() => {
    if (!result) navigate('/');
  }, [navigate, result]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setSelectedOption(null); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  if (!result) return null;

  const calculation = result.calculation;
  const totals = calculation.totals;
  const allOptions = calculation.ranked_options || [];

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }} className="animate-fade-in">
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h2><span className="text-gradient">RetroFi</span></h2>
        <button
          onClick={() => navigate('/')}
          style={{
            background: '#22c55e',
            color: '#071810',
            border: 'none',
            padding: '0.5rem 1.25rem',
            borderRadius: '8px',
            fontWeight: 700,
            fontSize: '0.9rem',
            cursor: 'pointer',
            fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
            boxShadow: '0 4px 14px rgba(34,197,94,0.35)',
            transition: 'background 0.2s ease',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = '#16a34a'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = '#22c55e'; }}
        >
          New Search
        </button>
      </header>

      <div style={{ marginBottom: '2rem' }}>
        <h1>Your Home Retrofit Roadmap</h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '1.1rem', maxWidth: '850px', marginTop: '1rem' }}>
          We analyzed {calculation.address} and ranked the upgrades that can lower bills, reduce carbon, and take advantage of available incentives.
        </p>
      </div>

      {/* AI Summary */}
      <div className="glass-panel" style={{ padding: '1.5rem', marginBottom: '2rem', borderLeft: '4px solid var(--accent-primary)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
          <h3 style={{ margin: 0 }}>Recommendation Overview</h3>
          {result.summary_source === 'local_llm' && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              background: 'rgba(34, 197, 94, 0.1)',
              border: '1px solid rgba(34, 197, 94, 0.25)',
              color: '#4ade80',
              padding: '0.25rem 0.6rem',
              borderRadius: '9999px',
              fontSize: '0.75rem',
              fontWeight: 600,
              letterSpacing: '0.025em',
            }}>
              <span style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                background: '#4ade80',
                display: 'inline-block',
                boxShadow: '0 0 8px #4ade80',
              }} />
              <span>Ollama: {result.model || 'qwen2.5:0.5b'}</span>
            </div>
          )}
          {result.summary_source === 'fallback' && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              background: 'rgba(239, 68, 68, 0.08)',
              border: '1px solid rgba(239, 68, 68, 0.2)',
              color: '#f87171',
              padding: '0.25rem 0.6rem',
              borderRadius: '9999px',
              fontSize: '0.75rem',
              fontWeight: 600,
              letterSpacing: '0.025em',
            }}>
              <span style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                background: '#f87171',
                display: 'inline-block',
                boxShadow: '0 0 8px #f87171',
              }} />
              <span>Fallback Engine (Local Model Offline)</span>
            </div>
          )}
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '1.05rem', lineHeight: 1.7, marginTop: '1rem', whiteSpace: 'pre-wrap' }}>
          {result.llm_summary}
        </p>
      </div>


      {/* Step cards — click to open modal */}
      <section style={{ marginBottom: '3rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem' }}>
          {allOptions.map((option) => (
            <StepCard key={option.upgrade_key} option={option} onClick={() => setSelectedOption(option)} />
          ))}
        </div>
      </section>

      {/* Modal */}
      {selectedOption && (
        <UpgradeModal option={selectedOption} onClose={() => setSelectedOption(null)} />
      )}
    </div>
  );
}

function StepCard({ option, onClick }) {
  return (
    <div
      className="glass-panel"
      onClick={onClick}
      style={{
        padding: '1.25rem',
        borderTop: '4px solid var(--accent-primary)',
        cursor: 'pointer',
        userSelect: 'none',
      }}
    >
      <span style={{ color: 'var(--accent-primary)', fontWeight: 700, fontSize: '0.8rem', letterSpacing: '0.05em' }}>
        STEP {option.rank}
      </span>
      <h4 style={{ marginTop: '0.4rem', marginBottom: '0.75rem' }}>{option.name}</h4>
      <div style={{ display: 'grid', gap: '0.4rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
        <span>Net cost: <strong style={{ color: 'var(--text-primary)' }}>{currency.format(option.net_cost)}</strong></span>
        <span>Saves: <strong style={{ color: 'var(--success)' }}>{currency.format(option.annual_savings)}/yr</strong></span>
        <span>Payback: <strong style={{ color: 'var(--text-primary)' }}>{option.payback_years ?? 'N/A'} years</strong></span>
      </div>
      <span style={{ fontSize: '0.78rem', color: 'var(--accent-primary)', fontWeight: 600 }}>
        View details →
      </span>
    </div>
  );
}

function UpgradeModal({ option, onClose }) {
  const topIncentives = option.matched_incentives?.slice(0, 3) || [];

  return createPortal(
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(4px)',
        zIndex: 100,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1.5rem',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="glass-panel"
        style={{
          maxWidth: '620px',
          width: '100%',
          maxHeight: '85vh',
          overflowY: 'auto',
          padding: '2rem',
          borderTop: '4px solid var(--accent-primary)',
          position: 'relative',
        }}
      >
        {/* Close */}
        <button
          onClick={onClose}
          aria-label="Close"
          style={{
            position: 'absolute',
            top: '1rem',
            right: '1rem',
            background: 'rgba(34,197,94,0.08)',
            border: '1px solid rgba(34,197,94,0.2)',
            color: 'var(--text-secondary)',
            borderRadius: '50%',
            width: '32px',
            height: '32px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            fontSize: '1rem',
            lineHeight: 1,
            transition: 'color 0.15s ease, border-color 0.15s ease',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = '#f0fdf4'; e.currentTarget.style.borderColor = 'rgba(34,197,94,0.5)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-secondary)'; e.currentTarget.style.borderColor = 'rgba(34,197,94,0.2)'; }}
        >
          ✕
        </button>

        {/* Header */}
        <span style={{ color: 'var(--accent-primary)', fontWeight: 700, fontSize: '0.8rem', letterSpacing: '0.05em' }}>
          STEP {option.rank}
        </span>
        <h3 style={{ marginTop: '0.4rem', marginBottom: '0.5rem' }}>{option.name}</h3>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem', lineHeight: 1.6 }}>
          {option.description}
        </p>

        {/* Financials */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(2, 1fr)',
          gap: '0.75rem',
          marginBottom: '1.5rem',
        }}>
          {[
            { label: 'Net Cost', value: currency.format(option.net_cost), color: 'var(--text-primary)' },
            { label: 'Incentives', value: currency.format(option.incentive_total), color: 'var(--success)' },
            { label: 'Annual Savings', value: `${currency.format(option.annual_savings)}/yr`, color: 'var(--success)' },
            { label: 'Payback Period', value: `${option.payback_years ?? 'N/A'} years`, color: 'var(--accent-primary)' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ background: 'rgba(34,197,94,0.05)', border: '1px solid rgba(34,197,94,0.15)', borderRadius: '10px', padding: '0.75rem 1rem' }}>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.75rem', marginBottom: '0.25rem' }}>{label}</p>
              <p style={{ color, fontWeight: 700, fontSize: '1.05rem' }}>{value}</p>
            </div>
          ))}
        </div>

        {/* Next steps */}
        <div style={{ marginBottom: topIncentives.length > 0 ? '1.5rem' : 0 }}>
          <h4 style={{ marginBottom: '0.6rem' }}>Simple Next Steps</h4>
          <ol style={{ color: 'var(--text-secondary)', paddingLeft: '1.25rem', lineHeight: 1.7 }}>
            <li>Ask a qualified contractor for a quote for {option.name.toLowerCase()}.</li>
            <li>Confirm the equipment meets the incentive requirements before signing.</li>
            <li>Keep receipts, model numbers, and photos for rebate or tax credit paperwork.</li>
          </ol>
        </div>

        {/* Incentives */}
        {topIncentives.length > 0 && (
          <div>
            <h4 style={{ marginBottom: '0.6rem' }}>Likely Incentives to Check</h4>
            <ul style={{ color: 'var(--text-secondary)', paddingLeft: '1.25rem', lineHeight: 1.7 }}>
              {topIncentives.map((incentive) => (
                <li key={incentive.id}>
                  {incentive.name}: <strong style={{ color: 'var(--success)' }}>{currency.format(incentive.amount)}</strong>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}

function Metric({ label, value, accent = 'var(--text-primary)' }) {
  return (
    <div className="glass-panel" style={{ padding: '1.5rem', textAlign: 'center' }}>
      <h4 style={{ color: 'var(--text-secondary)' }}>{label}</h4>
      <p style={{ fontSize: '1.8rem', fontWeight: 'bold', color: accent }}>{value}</p>
    </div>
  );
}

export default Dashboard;
