import { useEffect } from 'react';
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

  useEffect(() => {
    if (!result) {
      navigate('/');
    }
  }, [navigate, result]);

  if (!result) {
    return null;
  }

  const calculation = result.calculation;
  const totals = calculation.totals;
  const topOptions = calculation.ranked_options?.slice(0, 4) || [];

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }} className="animate-fade-in">
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h2><span className="text-gradient">RetroFi ATL</span></h2>
        <button className="btn-primary" onClick={() => navigate('/')} style={{ padding: '0.5rem 1rem' }}>
          New Search
        </button>
      </header>

      <div style={{ marginBottom: '2rem' }}>
        <h1>Your Home Retrofit Roadmap</h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '1.1rem', maxWidth: '850px', marginTop: '1rem' }}>
          We analyzed {calculation.address} and ranked the upgrades that can lower bills, reduce carbon, and take advantage of available incentives.
        </p>
      </div>

      {result && (
        <>
          <div className="glass-panel" style={{ padding: '1.5rem', marginBottom: '2rem', borderLeft: '4px solid var(--accent-primary)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'center' }}>
              <h3>Plain-English Recommendation</h3>
              <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                {result.summary_source === 'anthropic' ? `AI summary: ${result.model}` : 'Draft summary'}
              </span>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '1.05rem', lineHeight: 1.7, marginTop: '1rem', whiteSpace: 'pre-wrap' }}>
              {result.llm_summary}
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', marginBottom: '3rem' }}>
            <Metric label="Net Cost" value={currency.format(totals.net_cost)} />
            <Metric label="Incentives" value={currency.format(totals.incentive_total)} accent="var(--success)" />
            <Metric label="Annual Savings" value={`${currency.format(totals.annual_savings)}/yr`} accent="var(--success)" />
            <Metric label="Carbon Avoided" value={`${totals.carbon_avoided_tons.toFixed(1)} tons/yr`} accent="var(--accent-primary)" />
          </div>

          <section style={{ marginBottom: '3rem' }}>
            <h3 style={{ marginBottom: '1.5rem', borderBottom: '1px solid var(--card-border)', paddingBottom: '0.5rem' }}>
              What To Do First
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem' }}>
              {topOptions.map((option) => (
                <StepCard key={option.upgrade_key} option={option} />
              ))}
            </div>
          </section>

          <section>
            <h3 style={{ marginBottom: '1.5rem', borderBottom: '1px solid var(--card-border)', paddingBottom: '0.5rem' }}>
              Upgrade Details
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {calculation.ranked_options.map((option) => (
                <div key={option.upgrade_key} className="glass-panel" style={{ padding: '1.5rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem' }}>
                    <div>
                      <h4>#{option.rank} {option.name}</h4>
                      <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>{option.description}</p>
                    </div>
                    <strong style={{ color: 'var(--accent-primary)' }}>
                      {option.payback_years ?? 'N/A'} yrs
                    </strong>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.75rem', marginTop: '1rem', color: 'var(--text-secondary)' }}>
                    <span>Gross: {currency.format(option.gross_cost)}</span>
                    <span>Incentives: {currency.format(option.incentive_total)}</span>
                    <span>Net: {currency.format(option.net_cost)}</span>
                    <span>Save: {currency.format(option.annual_savings)}/yr</span>
                  </div>
                  <ActionList option={option} />
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function StepCard({ option }) {
  return (
    <div className="glass-panel" style={{ padding: '1.25rem', borderTop: '4px solid var(--accent-primary)' }}>
      <span style={{ color: 'var(--accent-primary)', fontWeight: 700 }}>Step {option.rank}</span>
      <h4 style={{ marginTop: '0.5rem' }}>{option.name}</h4>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>
      </p>
      <div style={{ display: 'grid', gap: '0.4rem', color: 'var(--text-secondary)' }}>
        <span>Net cost: <strong style={{ color: 'var(--text-primary)' }}>{currency.format(option.net_cost)}</strong></span>
        <span>Saves: <strong style={{ color: 'var(--success)' }}>{currency.format(option.annual_savings)}/yr</strong></span>
        <span>Payback: <strong style={{ color: 'var(--text-primary)' }}>{option.payback_years ?? 'N/A'} years</strong></span>
      </div>
    </div>
  );
}

function ActionList({ option }) {
  const topIncentives = option.matched_incentives.slice(0, 2);

  return (
    <div style={{ marginTop: '1rem' }}>
      <strong>Simple next steps</strong>
      <ol style={{ color: 'var(--text-secondary)', paddingLeft: '1.25rem', marginTop: '0.5rem' }}>
        <li>Ask a qualified contractor for a quote for {option.name.toLowerCase()}.</li>
        <li>Confirm the equipment meets the incentive requirements before signing.</li>
        <li>Keep receipts, model numbers, and photos for rebate or tax credit paperwork.</li>
      </ol>
      {topIncentives.length > 0 && (
        <div style={{ marginTop: '1rem' }}>
          <strong>Likely incentives to check</strong>
          <ul style={{ color: 'var(--text-secondary)', paddingLeft: '1.25rem', marginTop: '0.5rem' }}>
            {topIncentives.map((incentive) => (
              <li key={incentive.id}>
                {incentive.name}: {currency.format(incentive.amount)}
              </li>
            ))}
          </ul>
        </div>
      )}
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
