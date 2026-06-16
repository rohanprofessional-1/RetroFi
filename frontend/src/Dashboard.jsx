import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import { sequenceRetrofit, fetchSolarActionSteps, getGoogleMapsConfig } from './api';

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
  const [mapsApiKey, setMapsApiKey] = useState(null);

  const [rankedOptions, setRankedOptions] = useState(result?.calculation?.ranked_options || []);
  const [focus, setFocus] = useState(result?.calculation?.sequencing_focus || 'balanced');
  const [isResequencing, setIsResequencing] = useState(false);

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
    getGoogleMapsConfig().then((cfg) => setMapsApiKey(cfg.api_key)).catch(() => {});
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
  const sequencedOptions = [...rankedOptions].sort(
    (a, b) => a.recommended_sequence - b.recommended_sequence
  );

  const handleFocusChange = async (newFocus) => {
    if (newFocus === focus || isResequencing) {
      return;
    }
    setIsResequencing(true);
    try {
      const response = await sequenceRetrofit(rankedOptions, newFocus);
      setRankedOptions(response.ranked_options);
      setFocus(response.sequencing_focus);
    } catch (error) {
      console.error('Failed to re-sequence upgrades', error);
    } finally {
      setIsResequencing(false);
    }
  };

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
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--card-border)', paddingBottom: '0.5rem' }}>
          <h3 style={{ margin: 0 }}>What To Do First</h3>
          <FocusToggle focus={focus} onChange={handleFocusChange} disabled={isResequencing} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem', opacity: isResequencing ? 0.6 : 1, transition: 'opacity 0.15s ease' }}>
          {sequencedOptions.map((option) => (
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
          mapsApiKey={mapsApiKey}
          propertyCoords={result.solar_data?.coordinates}
        />
      )}
    </div>
  );
}

const FOCUS_OPTIONS = [
  { key: 'balanced', label: 'Balanced' },
  { key: 'cost', label: 'Lower Cost' },
  { key: 'carbon', label: 'Lower Carbon' },
];

function FocusToggle({ focus, onChange, disabled }) {
  return (
    <div style={{ display: 'inline-flex', gap: '0.5rem', padding: '0.25rem', borderRadius: '999px', background: 'var(--card-bg)', border: '1px solid var(--card-border)' }}>
      {FOCUS_OPTIONS.map((option) => {
        const isActive = option.key === focus;
        return (
          <button
            key={option.key}
            type="button"
            onClick={() => onChange(option.key)}
            disabled={disabled}
            style={{
              padding: '0.4rem 1rem',
              borderRadius: '999px',
              border: 'none',
              fontSize: '0.9rem',
              fontWeight: 600,
              cursor: disabled ? 'wait' : 'pointer',
              background: isActive ? 'var(--accent-gradient)' : 'transparent',
              color: isActive ? '#fff' : 'var(--text-secondary)',
              transition: 'background 0.15s ease, color 0.15s ease',
            }}
          >
            {option.label}
          </button>
        );
      })}
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
        STEP {option.recommended_sequence}
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

function UpgradeModal({ option, onClose, solarSteps, mapsApiKey, propertyCoords }) {
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
          STEP {option.recommended_sequence}
        </span>
        <h3 style={{ marginTop: '0.4rem', marginBottom: '0.5rem' }}>{option.name}</h3>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem', lineHeight: 1.6 }}>
          {option.description}
        </p>

        {/* Cost waterfall */}
        <div style={{ background: 'rgba(34,197,94,0.04)', border: '1px solid rgba(34,197,94,0.15)', borderRadius: '10px', padding: '1rem 1.1rem', marginBottom: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.55rem' }}>
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.87rem' }}>Gross Install Cost</span>
            <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{currency.format(option.gross_cost)}</span>
          </div>
          {option.matched_incentives.map((incentive) => (
            <div key={incentive.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.4rem' }}>
              <span style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', maxWidth: '72%' }}>
                <span style={{ color: 'var(--success)', fontWeight: 700, marginRight: '0.3rem' }}>−</span>
                {incentive.name}
              </span>
              <span style={{ color: 'var(--success)', fontWeight: 600, fontSize: '0.9rem' }}>−{currency.format(incentive.amount)}</span>
            </div>
          ))}
          {option.matched_incentives.length === 0 && (
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.4rem' }}>
              <span style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', fontStyle: 'italic' }}>No incentives applied</span>
              <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>−$0</span>
            </div>
          )}
          <div style={{ borderTop: '1px solid rgba(34,197,94,0.25)', margin: '0.6rem 0' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <span style={{ color: 'var(--text-primary)', fontWeight: 700 }}>Net Cost</span>
            <span style={{ color: 'var(--text-primary)', fontWeight: 700, fontSize: '1.15rem' }}>{currency.format(option.net_cost)}</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginTop: '0.8rem', paddingTop: '0.7rem', borderTop: '1px solid rgba(34,197,94,0.1)' }}>
            <div>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.72rem', marginBottom: '0.15rem' }}>Annual Savings</p>
              <p style={{ color: 'var(--success)', fontWeight: 700 }}>{currency.format(option.annual_savings)}/yr</p>
            </div>
            <div>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.72rem', marginBottom: '0.15rem' }}>Payback Period</p>
              <p style={{ color: 'var(--accent-primary)', fontWeight: 700 }}>{option.payback_years ?? 'N/A'} years</p>
            </div>
          </div>
        </div>

        {/* Next steps */}
        <div style={{ marginBottom: '1.5rem' }}>
          {isSolar
            ? <SolarActionList solarSteps={solarSteps} mapsApiKey={mapsApiKey} propertyCoords={propertyCoords} />
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

      </div>
    </div>,
    document.body
  );
}

function SolarActionList({ solarSteps, mapsApiKey, propertyCoords }) {
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
          <InstallerMap propertyCoords={propertyCoords} installers={installers} apiKey={mapsApiKey} />
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

function InstallerMap({ propertyCoords, installers, apiKey }) {
  if (!apiKey || !propertyCoords?.lat || !propertyCoords?.lng) return null;
  const withCoords = installers.filter((ins) => ins.lat != null && ins.lng != null);
  if (withCoords.length === 0) return null;
  const { lat, lng } = propertyCoords;
  const darkStyles = [
    'feature:all|element:geometry|color:0x0d1b0d',
    'feature:road|element:geometry|color:0x1c301c',
    'feature:road.arterial|element:geometry.fill|color:0x243824',
    'feature:road.highway|element:geometry.fill|color:0x2a4a2a',
    'feature:water|element:geometry|color:0x061206',
    'feature:poi|visibility:off',
    'feature:transit|visibility:off',
    'feature:all|element:labels.text.fill|color:0x7a7a7a',
    'feature:all|element:labels.text.stroke|color:0x0d1b0d',
    'feature:administrative|element:geometry.stroke|color:0x1e3a1e',
  ].map((s) => `style=${encodeURIComponent(s)}`).join('&');
  const homeMarker = `markers=size:mid|color:0x3b82f6|label:H|${lat},${lng}`;
  const installerMarkers = withCoords
    .map((ins, i) => `markers=size:mid|color:0x22c55e|label:${i + 1}|${ins.lat},${ins.lng}`)
    .join('&');
  const src = `https://maps.googleapis.com/maps/api/staticmap?size=560x220&scale=2&${darkStyles}&${homeMarker}&${installerMarkers}&key=${apiKey}`;
  return (
    <div style={{ borderRadius: '10px', overflow: 'hidden', border: '1px solid rgba(34,197,94,0.2)', marginBottom: '0.75rem' }}>
      <img
        src={src}
        alt="Map showing your property (blue) and nearby solar installers (green)"
        style={{ width: '100%', display: 'block' }}
        onError={(e) => { e.currentTarget.parentElement.style.display = 'none'; }}
      />
      <div style={{ padding: '0.4rem 0.75rem', background: 'rgba(34,197,94,0.04)', display: 'flex', gap: '1.25rem', fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
        <span><span style={{ color: '#3b82f6', fontWeight: 700 }}>H</span> Your property</span>
        {withCoords.map((ins, i) => (
          <span key={ins.place_id}><span style={{ color: '#22c55e', fontWeight: 700 }}>{i + 1}</span> {ins.name}</span>
        ))}
      </div>
    </div>
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
