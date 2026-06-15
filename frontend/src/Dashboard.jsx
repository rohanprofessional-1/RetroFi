import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import { fetchSolarActionSteps } from './api';

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
  const [solarSteps, setSolarSteps] = useState({ loading: true, steps: [], installers: [], error: false });

  useEffect(() => {
    if (!result) navigate('/');
  }, [navigate, result]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setSelectedOption(null); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Fetch solar steps once on mount — cached in Dashboard state so modal re-opens don't re-fetch
  useEffect(() => {
    if (!result?.solar_data) {
      setSolarSteps({ loading: false, steps: [], installers: [], error: false });
      return;
    }
    const solarOption = result.calculation.ranked_options?.find((o) => o.upgrade_key === 'solar');
    if (!solarOption) {
      setSolarSteps({ loading: false, steps: [], installers: [], error: false });
      return;
    }
    const matchedIncentives = solarOption.matched_incentives.map((inc) => ({
      name: inc.name,
      amount: inc.amount,
      amount_description: inc.amount_description,
    }));
    fetchSolarActionSteps(result.calculation.address, result.solar_data, matchedIncentives)
      .then((data) => setSolarSteps({ loading: false, steps: data.steps || [], installers: data.nearby_installers || [], error: false }))
      .catch(() => setSolarSteps({ loading: false, steps: [], installers: [], error: true }));
  }, []);

  if (!result) return null;

  const calculation = result.calculation;
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
        <h3>Recommendation Overview</h3>
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
        <UpgradeModal
          option={selectedOption}
          onClose={() => setSelectedOption(null)}
          solarSteps={solarSteps}
        />
      )}
    </div>
  );
}

function StepCard({ option, onClick }) {
  return (
    <div
      className="glass-panel"
      onClick={onClick}
      style={{ padding: '1.25rem', borderTop: '4px solid var(--accent-primary)', cursor: 'pointer', userSelect: 'none' }}
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
      <span style={{ fontSize: '0.78rem', color: 'var(--accent-primary)', fontWeight: 600 }}>View details →</span>
    </div>
  );
}

function UpgradeModal({ option, onClose, solarSteps }) {
  const topIncentives = option.matched_incentives?.slice(0, 3) || [];
  const isSolar = option.upgrade_key === 'solar';

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
          maxWidth: '640px',
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
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.75rem', marginBottom: '1.5rem' }}>
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
        <div style={{ marginBottom: '1.5rem' }}>
          {isSolar
            ? <SolarActionList solarSteps={solarSteps} />
            : (
              <>
                <h4 style={{ marginBottom: '0.75rem' }}>Next Steps</h4>
                <ol style={{ color: 'var(--text-secondary)', paddingLeft: '1.25rem', lineHeight: 1.7 }}>
                  <li>Ask a qualified contractor for a quote for {option.name.toLowerCase()}.</li>
                  <li>Confirm the equipment meets the incentive requirements before signing.</li>
                  <li>Keep receipts, model numbers, and photos for rebate or tax credit paperwork.</li>
                </ol>
              </>
            )}
        </div>

        {/* Incentives — shown for non-solar (solar steps include incentive guidance inline) */}
        {!isSolar && topIncentives.length > 0 && (
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

function SolarActionList({ solarSteps }) {
  const { loading, steps, installers, error } = solarSteps;

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
        <h4 style={{ marginBottom: '0.25rem' }}>Your Personalized Next Steps</h4>
        {[...Array(6)].map((_, i) => (
          <div key={i} style={{
            height: '72px',
            borderRadius: '10px',
            background: 'rgba(34,197,94,0.05)',
            border: '1px solid rgba(34,197,94,0.1)',
            animation: 'pulse 1.5s ease-in-out infinite',
            opacity: 1 - i * 0.1,
          }} />
        ))}
      </div>
    );
  }

  if (error || steps.length === 0) {
    return (
      <>
        <h4 style={{ marginBottom: '0.75rem' }}>Next Steps</h4>
        <ol style={{ color: 'var(--text-secondary)', paddingLeft: '1.25rem', lineHeight: 1.7 }}>
          <li>Ask a qualified contractor for a quote for rooftop solar PV.</li>
          <li>Confirm the equipment meets the incentive requirements before signing.</li>
          <li>Keep receipts, model numbers, and photos for rebate or tax credit paperwork.</li>
        </ol>
      </>
    );
  }

  return (
    <>
      <h4 style={{ marginBottom: '0.75rem' }}>Your Personalized Next Steps</h4>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
        {steps.map((step, i) => (
          <div
            key={i}
            style={{
              background: 'rgba(34,197,94,0.05)',
              border: '1px solid rgba(34,197,94,0.15)',
              borderRadius: '10px',
              padding: '0.875rem 1rem',
            }}
          >
            {/* Title row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.35rem' }}>
              <span style={{
                background: 'rgba(34,197,94,0.15)',
                color: 'var(--accent-primary)',
                fontWeight: 700,
                fontSize: '0.78rem',
                borderRadius: '50%',
                minWidth: '24px',
                height: '24px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}>
                {i + 1}
              </span>
              <p style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.93rem' }}>
                {step.title}
              </p>
            </div>
            {/* Summary */}
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', lineHeight: 1.5, marginBottom: '0.5rem', paddingLeft: '2.1rem', fontStyle: 'italic' }}>
              {step.summary}
            </p>
            {/* Bullets */}
            <ul style={{ paddingLeft: '2.1rem', listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
              {(step.bullets || []).map((bullet, j) => (
                <li key={j} style={{ display: 'flex', alignItems: 'flex-start', gap: '0.4rem', color: 'var(--text-secondary)', fontSize: '0.82rem', lineHeight: 1.55 }}>
                  <span style={{ color: 'var(--accent-primary)', fontWeight: 700, flexShrink: 0, marginTop: '0.05rem' }}>›</span>
                  {bullet}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {installers.length > 0 && (
        <div style={{ marginTop: '1.25rem' }}>
          <h4 style={{ marginBottom: '0.75rem' }}>Nearby Solar Installers</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {installers.map((ins) => (
              <a
                key={ins.place_id}
                href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(ins.name)}&query_place_id=${ins.place_id}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  background: 'rgba(34,197,94,0.05)',
                  border: '1px solid rgba(34,197,94,0.15)',
                  borderRadius: '8px',
                  padding: '0.6rem 0.875rem',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: '0.5rem',
                  textDecoration: 'none',
                  cursor: 'pointer',
                  transition: 'border-color 0.15s ease, background 0.15s ease',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'rgba(34,197,94,0.4)'; e.currentTarget.style.background = 'rgba(34,197,94,0.09)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'rgba(34,197,94,0.15)'; e.currentTarget.style.background = 'rgba(34,197,94,0.05)'; }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                    <span style={{ fontWeight: 600, color: 'var(--accent-primary)', fontSize: '0.9rem' }}>{ins.name}</span>
                    <svg width="11" height="11" viewBox="0 0 12 12" fill="none" style={{ flexShrink: 0, opacity: 0.7 }}>
                      <path d="M2.5 1.5H10.5V9.5" stroke="#22c55e" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                      <path d="M10.5 1.5L1.5 10.5" stroke="#22c55e" strokeWidth="1.5" strokeLinecap="round"/>
                    </svg>
                  </div>
                  <span style={{ color: 'var(--text-secondary)', fontSize: '0.78rem' }}>
                    <span style={{ color: 'var(--accent-primary)', fontWeight: 600 }}>{ins.rating}★</span>
                    {' '}({ins.ratings_count} reviews) · {ins.vicinity}
                  </span>
                </div>
                <span style={{ fontSize: '0.72rem', color: 'var(--accent-primary)', fontWeight: 600, whiteSpace: 'nowrap', opacity: 0.8 }}>
                  View on Maps →
                </span>
              </a>
            ))}
          </div>
        </div>
      )}
    </>
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
