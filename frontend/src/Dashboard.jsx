import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { sequenceRetrofit, fetchSolarActionSteps, fetchActionSteps, getGoogleMapsConfig } from './api';

const currency = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

function Dashboard() {
  const location = useLocation();
  const navigate = useNavigate();
  const result = location.state?.result;
  const [solarSteps, setSolarSteps] = useState({ loading: true, steps: [], installers: [], error: false });
  const [mapsApiKey, setMapsApiKey] = useState(null);
  const [upgradeSteps, setUpgradeSteps] = useState({});

  const [rankedOptions, setRankedOptions] = useState(result?.calculation?.ranked_options || []);
  const [focus, setFocus] = useState(result?.calculation?.sequencing_focus || 'balanced');
  const [isResequencing, setIsResequencing] = useState(false);

  useEffect(() => {
    if (!result) navigate('/');
  }, [navigate, result]);

  // Pre-fetch all upgrade steps in parallel on mount so modals open instantly.
  // Results are cached in sessionStorage keyed by address so refreshes are instant.
  useEffect(() => {
    if (!result) return;

    getGoogleMapsConfig().then((cfg) => setMapsApiKey(cfg.api_key)).catch(() => {});

    const address = result.calculation.address;
    const coords = result.solar_data?.coordinates ?? null;
    const assumptions = result.calculation.assumptions ?? {};
    const profile = {
      square_footage: assumptions.square_footage ?? null,
      home_type: assumptions.home_type ?? null,
      ...(result.property_profile ?? {}),
    };
    const options = result.calculation.ranked_options ?? [];

    const cacheKey = (key) => `retrofi_steps__${key}__${address}`;

    const readCache = (key) => {
      try { return JSON.parse(sessionStorage.getItem(cacheKey(key))); } catch { return null; }
    };
    const writeCache = (key, data) => {
      try { sessionStorage.setItem(cacheKey(key), JSON.stringify(data)); } catch {}
    };

    // Solar
    const solarOption = options.find((o) => o.upgrade_key === 'solar');
    if (result.solar_data && solarOption) {
      const cached = readCache('solar');
      if (cached) {
        setSolarSteps(cached);
      } else {
        const incentives = solarOption.matched_incentives.map((inc) => ({
          name: inc.name, amount: inc.amount, amount_description: inc.amount_description,
        }));
        fetchSolarActionSteps(address, result.solar_data, incentives)
          .then((data) => {
            const state = { loading: false, steps: data.steps || [], installers: data.nearby_installers || [], error: false };
            writeCache('solar', state);
            setSolarSteps(state);
          })
          .catch(() => setSolarSteps({ loading: false, steps: [], installers: [], error: true }));
      }
    } else {
      setSolarSteps({ loading: false, steps: [], installers: [], error: false });
    }

    // All non-solar upgrades — serve from cache or fetch in parallel
    const nonSolarOptions = options.filter((o) => o.upgrade_key !== 'solar');
    if (nonSolarOptions.length === 0) return;

    const initialState = Object.fromEntries(
      nonSolarOptions.map((o) => {
        const cached = readCache(o.upgrade_key);
        return [o.upgrade_key, cached ?? { loading: true, steps: [], contractors: [], error: false }];
      })
    );
    setUpgradeSteps(initialState);

    nonSolarOptions.forEach((option) => {
      const key = option.upgrade_key;
      if (readCache(key)) return; // already hydrated from cache above

      const incentives = (option.matched_incentives || []).map((inc) => ({
        name: inc.name, amount: inc.amount, amount_description: inc.amount_description, eligibility_notes: inc.eligibility_notes,
      }));
      fetchActionSteps(key, address, coords, profile, incentives, option)
        .then((data) => {
          const state = { loading: false, steps: data.steps || [], contractors: data.nearby_contractors || [], error: false };
          writeCache(key, state);
          setUpgradeSteps((prev) => ({ ...prev, [key]: state }));
        })
        .catch(() => setUpgradeSteps((prev) => ({
          ...prev,
          [key]: { loading: false, steps: [], contractors: [], error: true },
        })));
    });
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
            <StepCard
              key={option.upgrade_key}
              option={option}
              onClick={() => navigate('/upgrade', {
                state: {
                  option,
                  upgradeSteps: upgradeSteps[option.upgrade_key],
                  solarSteps,
                  mapsApiKey,
                  propertyCoords: result.solar_data?.coordinates,
                },
              })}
            />
          ))}
        </div>
      </section>
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

function Metric({ label, value, accent = 'var(--text-primary)' }) {
  return (
    <div className="glass-panel" style={{ padding: '1.5rem', textAlign: 'center' }}>
      <h4 style={{ color: 'var(--text-secondary)' }}>{label}</h4>
      <p style={{ fontSize: '1.8rem', fontWeight: 'bold', color: accent }}>{value}</p>
    </div>
  );
}

export default Dashboard;
