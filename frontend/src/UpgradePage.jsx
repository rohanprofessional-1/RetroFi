import { useLocation, useNavigate } from 'react-router-dom';

const currency = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

function UpgradePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const state = location.state;

  if (!state?.option) {
    navigate('/');
    return null;
  }

  const { option, upgradeSteps, solarSteps, mapsApiKey, propertyCoords } = state;
  const isSolar = option.upgrade_key === 'solar';

  return (
    <div className="animate-fade-in" style={{ minHeight: '100vh', padding: '2rem', maxWidth: '820px', margin: '0 auto' }}>

      {/* Back arrow */}
      <button
        onClick={() => navigate(-1)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.45rem',
          background: 'none',
          border: 'none',
          color: 'var(--text-secondary)',
          cursor: 'pointer',
          fontSize: '0.9rem',
          fontWeight: 600,
          fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
          padding: '0.25rem 0',
          marginBottom: '2rem',
          transition: 'color 0.15s ease',
        }}
        onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent-primary)'; }}
        onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-secondary)'; }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M19 12H5M12 19l-7-7 7-7" />
        </svg>
        Back to Dashboard
      </button>

      {/* Header */}
      <div style={{ marginBottom: '1.75rem' }}>
        <span style={{ color: 'var(--accent-primary)', fontWeight: 700, fontSize: '0.8rem', letterSpacing: '0.05em' }}>
          STEP {option.recommended_sequence}
        </span>
        <h1 style={{ marginTop: '0.4rem', marginBottom: '0.5rem', fontSize: '2rem' }}>{option.name}</h1>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.65, maxWidth: '620px' }}>
          {option.description}
        </p>
      </div>

      {/* Cost waterfall */}
      <div className="glass-panel" style={{
        padding: '1.25rem 1.5rem',
        marginBottom: '2rem',
        borderTop: '4px solid var(--accent-primary)',
      }}>
        <h3 style={{ marginBottom: '1rem', fontSize: '1rem' }}>Cost Breakdown</h3>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.6rem' }}>
          <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Gross Install Cost</span>
          <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{currency.format(option.gross_cost)}</span>
        </div>
        {option.matched_incentives.map((incentive) => (
          <div key={incentive.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.45rem' }}>
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', maxWidth: '72%' }}>
              <span style={{ color: 'var(--success)', fontWeight: 700, marginRight: '0.3rem' }}>−</span>
              {incentive.name}
            </span>
            <span style={{ color: 'var(--success)', fontWeight: 600 }}>−{currency.format(incentive.amount)}</span>
          </div>
        ))}
        {option.matched_incentives.length === 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.45rem' }}>
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', fontStyle: 'italic' }}>No incentives applied</span>
            <span style={{ color: 'var(--text-secondary)' }}>−$0</span>
          </div>
        )}
        <div style={{ borderTop: '1px solid rgba(34,197,94,0.25)', margin: '0.75rem 0' }} />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <span style={{ color: 'var(--text-primary)', fontWeight: 700, fontSize: '1.05rem' }}>Net Cost</span>
          <span style={{ color: 'var(--text-primary)', fontWeight: 700, fontSize: '1.3rem' }}>{currency.format(option.net_cost)}</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginTop: '1rem', paddingTop: '0.875rem', borderTop: '1px solid rgba(34,197,94,0.1)' }}>
          <div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.75rem', marginBottom: '0.2rem' }}>Annual Savings</p>
            <p style={{ color: 'var(--success)', fontWeight: 700, fontSize: '1.1rem' }}>{currency.format(option.annual_savings)}/yr</p>
          </div>
          <div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.75rem', marginBottom: '0.2rem' }}>Payback Period</p>
            <p style={{ color: 'var(--accent-primary)', fontWeight: 700, fontSize: '1.1rem' }}>{option.payback_years ?? 'N/A'} years</p>
          </div>
        </div>
      </div>

      {/* Personalized next steps */}
      <div style={{ marginBottom: '3rem' }}>
        {isSolar
          ? <SolarActionList solarSteps={solarSteps} mapsApiKey={mapsApiKey} propertyCoords={propertyCoords} />
          : <UpgradeActionList upgradeSteps={upgradeSteps} mapsApiKey={mapsApiKey} propertyCoords={propertyCoords} />
        }
      </div>

    </div>
  );
}

function StepCards({ steps }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {steps.map((step, i) => (
        <div
          key={i}
          style={{
            background: 'rgba(34,197,94,0.05)',
            border: '1px solid rgba(34,197,94,0.15)',
            borderRadius: '12px',
            padding: '1rem 1.1rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.4rem' }}>
            <span style={{
              background: 'rgba(34,197,94,0.15)',
              color: 'var(--accent-primary)',
              fontWeight: 700,
              fontSize: '0.8rem',
              borderRadius: '50%',
              minWidth: '26px',
              height: '26px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}>{i + 1}</span>
            <p style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.97rem' }}>{step.title}</p>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', lineHeight: 1.55, marginBottom: '0.6rem', paddingLeft: '2.2rem', fontStyle: 'italic' }}>
            {step.summary}
          </p>
          <ul style={{ paddingLeft: '2.2rem', listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            {(step.bullets || []).map((bullet, j) => (
              <li key={j} style={{ display: 'flex', alignItems: 'flex-start', gap: '0.4rem', color: 'var(--text-secondary)', fontSize: '0.85rem', lineHeight: 1.55 }}>
                <span style={{ color: 'var(--accent-primary)', fontWeight: 700, flexShrink: 0, marginTop: '0.05rem' }}>›</span>
                {bullet}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <h3 style={{ marginBottom: '0.5rem' }}>Your Personalized Next Steps</h3>
      {[...Array(6)].map((_, i) => (
        <div key={i} style={{
          height: '80px',
          borderRadius: '12px',
          background: 'rgba(34,197,94,0.05)',
          border: '1px solid rgba(34,197,94,0.1)',
          animation: 'pulse 1.5s ease-in-out infinite',
          opacity: 1 - i * 0.1,
        }} />
      ))}
    </div>
  );
}

function ContractorCards({ contractors, label = 'Nearby Contractors', propertyCoords, mapsApiKey }) {
  if (!contractors || contractors.length === 0) return null;
  return (
    <div style={{ marginTop: '2rem' }}>
      <h3 style={{ marginBottom: '1rem' }}>{label}</h3>
      <InstallerMap propertyCoords={propertyCoords} installers={contractors} apiKey={mapsApiKey} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
        {contractors.map((c) => (
          <a
            key={c.place_id}
            href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(c.name)}&query_place_id=${c.place_id}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              background: 'rgba(34,197,94,0.05)',
              border: '1px solid rgba(34,197,94,0.15)',
              borderRadius: '10px',
              padding: '0.75rem 1rem',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: '0.5rem',
              textDecoration: 'none',
              transition: 'border-color 0.15s ease, background 0.15s ease',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'rgba(34,197,94,0.4)'; e.currentTarget.style.background = 'rgba(34,197,94,0.09)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'rgba(34,197,94,0.15)'; e.currentTarget.style.background = 'rgba(34,197,94,0.05)'; }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <span style={{ fontWeight: 600, color: 'var(--accent-primary)', fontSize: '0.95rem' }}>{c.name}</span>
                <svg width="11" height="11" viewBox="0 0 12 12" fill="none" style={{ flexShrink: 0, opacity: 0.7 }}>
                  <path d="M2.5 1.5H10.5V9.5" stroke="#22c55e" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M10.5 1.5L1.5 10.5" stroke="#22c55e" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              </div>
              <span style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>
                <span style={{ color: 'var(--accent-primary)', fontWeight: 600 }}>{c.rating}★</span>
                {' '}({c.ratings_count} reviews) · {c.vicinity}
              </span>
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--accent-primary)', fontWeight: 600, whiteSpace: 'nowrap', opacity: 0.8 }}>
              View on Maps →
            </span>
          </a>
        ))}
      </div>
    </div>
  );
}

function UpgradeActionList({ upgradeSteps, mapsApiKey, propertyCoords }) {
  if (!upgradeSteps || upgradeSteps.loading) return <LoadingSkeleton />;

  if (upgradeSteps.error || upgradeSteps.steps.length === 0) {
    return (
      <>
        <h3 style={{ marginBottom: '0.75rem' }}>Next Steps</h3>
        <ol style={{ color: 'var(--text-secondary)', paddingLeft: '1.25rem', lineHeight: 1.7 }}>
          <li>Ask a qualified contractor for a quote and site assessment.</li>
          <li>Confirm equipment meets incentive requirements before signing.</li>
          <li>Keep receipts, model numbers, and photos for rebate or tax credit paperwork.</li>
        </ol>
      </>
    );
  }

  return (
    <>
      <h3 style={{ marginBottom: '1rem' }}>Your Personalized Next Steps</h3>
      <StepCards steps={upgradeSteps.steps} />
      <ContractorCards
        contractors={upgradeSteps.contractors}
        label="Nearby Contractors"
        propertyCoords={propertyCoords}
        mapsApiKey={mapsApiKey}
      />
    </>
  );
}

function SolarActionList({ solarSteps, mapsApiKey, propertyCoords }) {
  if (!solarSteps || solarSteps.loading) return <LoadingSkeleton />;

  if (solarSteps.error || solarSteps.steps.length === 0) {
    return (
      <>
        <h3 style={{ marginBottom: '0.75rem' }}>Next Steps</h3>
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
      <h3 style={{ marginBottom: '1rem' }}>Your Personalized Next Steps</h3>
      <StepCards steps={solarSteps.steps} />
      <ContractorCards
        contractors={solarSteps.installers}
        label="Nearby Solar Installers"
        propertyCoords={propertyCoords}
        mapsApiKey={mapsApiKey}
      />
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
  const src = `https://maps.googleapis.com/maps/api/staticmap?size=760x260&scale=2&${darkStyles}&${homeMarker}&${installerMarkers}&key=${apiKey}`;
  return (
    <div style={{ borderRadius: '12px', overflow: 'hidden', border: '1px solid rgba(34,197,94,0.2)', marginBottom: '0.875rem' }}>
      <img
        src={src}
        alt="Map showing your property and nearby contractors"
        style={{ width: '100%', display: 'block' }}
        onError={(e) => { e.currentTarget.parentElement.style.display = 'none'; }}
      />
      <div style={{ padding: '0.5rem 0.875rem', background: 'rgba(34,197,94,0.04)', display: 'flex', gap: '1.25rem', fontSize: '0.75rem', color: 'var(--text-secondary)', flexWrap: 'wrap' }}>
        <span><span style={{ color: '#3b82f6', fontWeight: 700 }}>H</span> Your property</span>
        {withCoords.map((ins, i) => (
          <span key={ins.place_id}><span style={{ color: '#22c55e', fontWeight: 700 }}>{i + 1}</span> {ins.name}</span>
        ))}
      </div>
    </div>
  );
}

export default UpgradePage;
