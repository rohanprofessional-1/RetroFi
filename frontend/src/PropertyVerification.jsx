import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const FIELD_LABELS = {
  // Priority 1 — Essential
  home_ownership_status: 'Home Ownership',
  has_cooling: 'Has Cooling',
  cooling_type: 'Cooling Type',
  roof_type: 'Roof Type',
  monthly_electricity_bill: 'Monthly Electricity Bill',
  monthly_gas_bill: 'Monthly Gas Bill',
  appliances_fuel: 'Appliances Fuel',
  // Priority 2 — High-Value
  home_type: 'Home Type',
  year_built: 'Year Built',
  primary_heating_fuel: 'Primary Heating Fuel',
  ev_owner_or_planning: 'EV Ownership / Plans',
  planning_roof_replacement: 'Roof Replacement Plans',
  primary_goal: 'Primary Goal',
  // Priority 3 — Nice to Have
  square_footage: 'Square Footage',
  num_occupants: 'Estimated Occupants',
  planned_electric_additions: 'Planned Electric Additions',
};

function formatValue(key, value) {
  if (value === null || value === undefined) return null;
  if (key === 'square_footage') return `${Number(value).toLocaleString()} sq ft`;
  if (key === 'year_built') return String(value);
  if (key === 'num_occupants') return `~${value} people`;
  if (key === 'home_ownership_status')
    return value === 'owner' ? 'Owner-Occupied' : value === 'renter' ? 'Renter' : value;
  if (key === 'has_cooling') return value ? 'Yes' : 'No';
  return String(value).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function PropertyVerification() {
  const location = useLocation();
  const navigate = useNavigate();

  const { pre_filled, meta, address } = location.state || {};

  if (!pre_filled) {
    navigate('/');
    return null;
  }

  const confirmed = Object.entries(FIELD_LABELS).filter(
    ([key]) => pre_filled[key] !== null && pre_filled[key] !== undefined,
  );
  const pending = Object.entries(FIELD_LABELS).filter(
    ([key]) => pre_filled[key] === null || pre_filled[key] === undefined,
  );

  const handleContinue = () => {
    navigate('/questionnaire', {
      state: { answers: { ...pre_filled, _questions_asked: 0 }, address },
    });
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
      <div className="animate-fade-in" style={{ maxWidth: '800px', width: '100%' }}>
        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
          <h1 style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>
            <span className="text-gradient">Property Verified</span>
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '1rem' }}>
            {meta?.formatted_address || address}
          </p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '2rem' }}>
          {/* Confirmed column */}
          <div className="glass-panel" style={{ padding: '1.5rem' }}>
            <h3 style={{ marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{
                background: 'rgba(16, 185, 129, 0.15)',
                color: 'var(--success)',
                borderRadius: '50%',
                width: '1.5rem', height: '1.5rem',
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '0.85rem',
              }}>✓</span>
              Confirmed from Public Records
            </h3>
            {confirmed.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                No fields could be pre-filled for this address.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {confirmed.map(([key, label]) => (
                  <div key={key} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '0.6rem 0.75rem',
                    background: 'rgba(16, 185, 129, 0.07)',
                    border: '1px solid rgba(16, 185, 129, 0.2)',
                    borderRadius: '8px',
                  }}>
                    <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>{label}</span>
                    <span style={{ color: 'var(--text-primary)', fontWeight: 500, fontSize: '0.9rem' }}>
                      {formatValue(key, pre_filled[key])}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Pending column */}
          <div className="glass-panel" style={{ padding: '1.5rem' }}>
            <h3 style={{ marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{
                background: 'rgba(59, 130, 246, 0.15)',
                color: 'var(--accent-primary)',
                borderRadius: '50%',
                width: '1.5rem', height: '1.5rem',
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '0.85rem',
              }}>?</span>
              We'll Ask You About
            </h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', marginBottom: '1rem' }}>
              Up to {Math.min(pending.length, 10)} quick questions — public records don't cover these.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
              {pending.map(([key, label]) => (
                <div key={key} style={{
                  padding: '0.5rem 0.75rem',
                  background: 'rgba(148, 163, 184, 0.05)',
                  border: '1px solid rgba(148, 163, 184, 0.15)',
                  borderRadius: '8px',
                  color: 'var(--text-secondary)',
                  fontSize: '0.85rem',
                }}>
                  {label}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* CTA */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem' }}>
          <button
            className="btn-primary"
            onClick={handleContinue}
            style={{ padding: '0.85rem 2.5rem', fontSize: '1rem' }}
          >
            Looks right — continue →
          </button>
          <button
            onClick={() => navigate('/')}
            style={{
              background: 'transparent',
              border: '1px solid var(--card-border)',
              color: 'var(--text-secondary)',
              padding: '0.85rem 1.5rem',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '1rem',
            }}
          >
            Wrong address
          </button>
        </div>
      </div>

      <div style={{
        position: 'absolute', top: '20%', left: '10%',
        width: '300px', height: '300px',
        background: 'var(--accent-primary)', filter: 'blur(150px)',
        opacity: '0.1', zIndex: -1, borderRadius: '50%',
      }} />
    </div>
  );
}

export default PropertyVerification;
