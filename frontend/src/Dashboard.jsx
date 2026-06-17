import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { fetchSolarActionSteps, fetchActionSteps, getGoogleMapsConfig, calculateRetrofit } from './api';
import TimelinePlan from './TimelinePlan';

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

  const rankedOptions = result?.calculation?.ranked_options || [];
  const [focus, setFocus] = useState(result?.calculation?.sequencing_focus || 'balanced');

  // Budget planner: the slider drives a live re-computation of the multi-year timeline.
  const [budget, setBudget] = useState(0);
  const [timeline, setTimeline] = useState(result?.calculation?.timeline || null);
  const [timelineLoading, setTimelineLoading] = useState(false);

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

  // Live-recompute the timeline whenever the budget slider changes (debounced).
  // At budget 0 we simply render the ranked cards instead, so no state reset is needed
  // here — any stale timeline stays in state but is not shown.
  useEffect(() => {
    const calcRequest = result?.calculation_request;
    if (!calcRequest || budget <= 0) return;
    let cancelled = false;
    const handle = setTimeout(async () => {
      setTimelineLoading(true);
      try {
        const resp = await calculateRetrofit({ ...calcRequest, budget_per_year: budget, focus });
        if (!cancelled) setTimeline(resp.timeline || null);
      } catch (err) {
        if (!cancelled) console.error('Failed to compute timeline', err);
      } finally {
        if (!cancelled) setTimelineLoading(false);
      }
    }, 300);
    return () => { cancelled = true; clearTimeout(handle); };
  }, [budget, focus, result]);

  if (!result) return null;

  const calculation = result.calculation;
  const optionByKey = Object.fromEntries(rankedOptions.map((o) => [o.upgrade_key, o]));

  const maxBudget = Math.max(
    0,
    Math.ceil(rankedOptions.reduce((sum, o) => sum + (o.gross_cost || 0), 0) / 500) * 500,
  );

  const openUpgrade = (option) => navigate('/upgrade', {
    state: {
      option,
      upgradeSteps: upgradeSteps[option.upgrade_key],
      solarSteps,
      mapsApiKey,
      propertyCoords: result.solar_data?.coordinates,
    },
  });

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

      {/* Budget planner — drives the multi-year timeline */}
      {maxBudget > 0 && (
        <BudgetPlanner
          budget={budget}
          maxBudget={maxBudget}
          onChange={setBudget}
          loading={timelineLoading}
          focus={focus}
          onFocusChange={setFocus}
        />
      )}

      {/* Multi-year timeline — always shown */}
      {timelineLoading ? (
        <div className="glass-panel" style={{ padding: '2.5rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
          Building your multi-year plan…
        </div>
      ) : timeline ? (
        <div style={{ opacity: timelineLoading ? 0.55 : 1, transition: 'opacity 0.2s ease' }}>
          <TimelinePlan
            timeline={timeline}
            optionByKey={optionByKey}
            onSelectUpgrade={openUpgrade}
          />
        </div>
      ) : (
        <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)', marginBottom: '2rem' }}>
          <p style={{ fontSize: '1rem', margin: 0 }}>Set a yearly budget above to see your phased multi-year plan.</p>
        </div>
      )}
    </div>
  );
}

function BudgetPlanner({ budget, maxBudget, onChange, loading, focus, onFocusChange }) {
  const pct = maxBudget > 0 ? (budget / maxBudget) * 100 : 0;
  return (
    <div className="glass-panel" style={{ padding: '1.5rem 1.75rem', marginBottom: '2rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.35rem' }}>
        <h3 style={{ margin: 0 }}>Plan Around Your Budget</h3>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem' }}>
          <span style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--accent-primary)' }}>
            {currency.format(budget)}
          </span>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>/ year</span>
          {loading && <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>updating…</span>}
        </div>
      </div>
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.5, margin: '0 0 1.25rem' }}>
        Drag to set how much you can invest per year. We’ll phase your upgrades across years to fit — and time them to capture the most incentives.
      </p>
      <input
        type="range"
        min={0}
        max={maxBudget}
        step={250}
        value={budget}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{
          width: '100%',
          accentColor: 'var(--accent-primary)',
          height: '6px',
          cursor: 'pointer',
          background: `linear-gradient(to right, var(--accent-primary) ${pct}%, var(--card-border) ${pct}%)`,
          borderRadius: '999px',
          appearance: 'none',
          WebkitAppearance: 'none',
        }}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '0.5rem', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
        <span>$0</span>
        <span>{currency.format(maxBudget)}</span>
      </div>
      {budget > 0 ? (
        <div style={{ marginTop: '1.5rem', paddingTop: '1.25rem', borderTop: '1px solid var(--card-border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div>
            <span style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>Optimize for</span>
            <p style={{ margin: '0.2rem 0 0', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              Changes which upgrades win the budget and when they’re scheduled.
            </p>
          </div>
          <FocusToggle focus={focus} onChange={onFocusChange} disabled={false} />
        </div>
      ) : (
        <p style={{ margin: '1rem 0 0', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
          Showing all upgrades ranked below. Set a yearly budget to build a phased, multi-year plan.
        </p>
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


export default Dashboard;
