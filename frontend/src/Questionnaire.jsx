import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

// Mirror of backend PRIORITY_FIELDS
const FIELDS = [
  { key: 'monthly_electricity_bill', label: 'Average monthly electricity bill', type: 'number', unit: '$', placeholder: 'e.g. 120', required: true, section: 'Monthly Costs' },
  { key: 'monthly_gas_bill',         label: 'Average monthly gas bill',         type: 'number', unit: '$', placeholder: 'e.g. 60',  required: true, section: 'Monthly Costs' },
  { key: 'home_ownership_status',    label: 'Home ownership',                   type: 'choice', required: true, section: 'Your Home',
    options: ['Own', 'Rent / Lease'] },
  { key: 'home_type',                label: 'Home type',                        type: 'choice', required: false, section: 'Your Home',
    options: ['Single Family', 'Townhouse', 'Condo / Apartment', 'Other'] },
  { key: 'year_built',               label: 'Year built',                       type: 'choice', required: false, section: 'Your Home',
    options: ['Before 1980', '1980 – 2000', '2001 – 2015', 'After 2015'] },
  { key: 'square_footage',           label: 'Home square footage',              type: 'choice', required: false, section: 'Your Home',
    options: ['Under 1,000 sq ft', '1,000 – 1,500 sq ft', '1,500 – 2,500 sq ft', 'Over 2,500 sq ft'] },
  { key: 'num_occupants',            label: 'Number of occupants',              type: 'choice', required: false, section: 'Your Home',
    options: ['1', '2', '3', '4', '5 or more'] },
  { key: 'roof_type',                label: 'Roof type',                        type: 'choice', required: true, section: 'Your Home',
    options: ['Asphalt Shingle', 'Metal', 'Tile', 'Flat / TPO', 'Other'] },
  { key: 'primary_heating_fuel',     label: 'Primary heating fuel',             type: 'choice', required: false, section: 'Energy & Appliances',
    options: ['Gas', 'Electric', 'Oil', 'Propane'] },
  { key: 'appliances_fuel',          label: 'Water heating & cooking fuel',     type: 'choice', required: true, section: 'Energy & Appliances',
    options: ['Electric', 'Gas', 'Mixed (both)'] },
  { key: 'ev_owner_or_planning',     label: 'EV ownership or plans',            type: 'choice', required: false, section: 'Future Plans',
    options: ['Yes, I own one', 'Planning within 3 years', 'No'] },
  { key: 'planning_roof_replacement',label: 'Roof replacement in next 5 years', type: 'choice', required: false, section: 'Future Plans',
    options: ['Yes', 'No', 'Not sure'] },
  { key: 'planned_electric_additions',label: 'Major electric additions planned (pool, hot tub, ADU, etc.)', type: 'choice', required: false, section: 'Future Plans',
    options: ['Yes', 'No'] },
  { key: 'primary_goal',             label: 'Primary goal',                     type: 'choice', required: false, section: 'Future Plans',
    options: ['Lower bills', 'Backup power during outages', 'Reduce carbon footprint', 'Increase home value', 'Other'] },
];

const SECTION_ORDER = ['Monthly Costs', 'Your Home', 'Energy & Appliances', 'Future Plans'];

const PREFILL_LABELS = {
  home_ownership_status: 'Home Ownership',
  home_type: 'Home Type',
  year_built: 'Year Built',
  primary_heating_fuel: 'Primary Heating Fuel',
  roof_type: 'Roof Type',
  square_footage: 'Square Footage',
  num_occupants: 'Est. Occupants',
};

function formatPrefill(key, value) {
  if (key === 'square_footage') return `${Number(value).toLocaleString()} sq ft`;
  if (key === 'num_occupants') return `~${value} people`;
  if (key === 'home_ownership_status') return value === 'owner' ? 'Owner-Occupied' : value === 'renter' ? 'Renter' : value;
  return String(value).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function ChoiceField({ field, value, onChange, otherText, onOtherText }) {
  const hasOther = field.options.includes('Other');
  const otherSelected = value === 'Other';

  return (
    <div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
        {field.options.map((opt) => {
          const selected = value === opt;
          return (
            <button
              key={opt}
              type="button"
              onClick={() => onChange(opt)}
              style={{
                padding: '0.5rem 1rem',
                borderRadius: '999px',
                fontSize: '0.875rem',
                cursor: 'pointer',
                transition: 'all 0.15s',
                background: selected ? 'rgba(59, 130, 246, 0.3)' : 'rgba(59, 130, 246, 0.07)',
                border: selected ? '1px solid rgba(59, 130, 246, 0.8)' : '1px solid rgba(59, 130, 246, 0.25)',
                color: selected ? '#e2e8f0' : 'var(--text-secondary)',
                fontWeight: selected ? 600 : 400,
              }}
            >
              {opt}
            </button>
          );
        })}
      </div>
      {hasOther && otherSelected && (
        <input
          type="text"
          className="input-premium"
          placeholder="Describe your goal…"
          value={otherText || ''}
          onChange={(e) => onOtherText(e.target.value)}
          autoFocus
          style={{ marginTop: '0.75rem', width: '100%' }}
        />
      )}
    </div>
  );
}

function NumberField({ field, value, onChange, error }) {
  return (
    <div>
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
        <span style={{
          position: 'absolute', left: '0.85rem',
          color: 'var(--text-secondary)', fontSize: '0.95rem', pointerEvents: 'none',
        }}>$</span>
        <input
          type="text"
          inputMode="decimal"
          className="input-premium"
          placeholder={field.placeholder}
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
          style={{ paddingLeft: '1.75rem', width: '100%', maxWidth: '200px' }}
        />
      </div>
      {error && <p style={{ color: '#f87171', fontSize: '0.78rem', marginTop: '0.3rem' }}>{error}</p>}
    </div>
  );
}

function Questionnaire() {
  const location = useLocation();
  const navigate = useNavigate();

  const { answers: initialAnswers, address } = location.state || {};

  if (!initialAnswers) {
    navigate('/');
    return null;
  }

  // Fields that were pre-filled by RentCast (shown as confirmed, not in the form)
  const prefilled = Object.entries(PREFILL_LABELS).filter(
    ([key]) => initialAnswers[key] !== null && initialAnswers[key] !== undefined,
  );

  // Only show fields that are missing from initialAnswers
  const fieldsToShow = FIELDS.filter(
    (f) => initialAnswers[f.key] === null || initialAnswers[f.key] === undefined,
  );

  const [formValues, setFormValues] = useState({});
  const [otherValues, setOtherValues] = useState({});
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  const setValue = (key, val) => {
    setFormValues((prev) => ({ ...prev, [key]: val }));
    setErrors((prev) => ({ ...prev, [key]: '' }));
  };

  const setOtherValue = (key, val) => {
    setOtherValues((prev) => ({ ...prev, [key]: val }));
    setErrors((prev) => ({ ...prev, [key]: '' }));
  };

  const validate = () => {
    const newErrors = {};
    fieldsToShow.forEach((f) => {
      if (!f.required) return;
      const val = (formValues[f.key] || '').toString().trim();
      if (!val) {
        newErrors[f.key] = 'This field is required.';
        return;
      }
      if (f.type === 'number') {
        const parsed = parseFloat(val.replace(/[$,]/g, ''));
        if (isNaN(parsed) || parsed < 0) {
          newErrors[f.key] = 'Enter a valid dollar amount.';
        }
      }
      if (val === 'Other' && f.options?.includes('Other')) {
        const custom = (otherValues[f.key] || '').trim();
        if (!custom) newErrors[f.key] = 'Please describe your goal.';
      }
    });
    return newErrors;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const newErrors = validate();
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      const firstKey = Object.keys(newErrors)[0];
      document.getElementById(`field-${firstKey}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }

    // Merge pre-filled + form answers; format dollar amounts; resolve "Other" free-text
    const merged = { ...initialAnswers };
    fieldsToShow.forEach((f) => {
      const raw = (formValues[f.key] || '').toString().trim();
      if (!raw) return;
      if (f.type === 'number') {
        const parsed = parseFloat(raw.replace(/[$,]/g, ''));
        merged[f.key] = `$${parsed.toFixed(0)}`;
      } else if (raw === 'Other' && f.options?.includes('Other')) {
        const custom = (otherValues[f.key] || '').trim();
        merged[f.key] = custom || 'Other';
      } else {
        merged[f.key] = raw;
      }
    });

    setSubmitting(true);
    setSubmitError('');
    try {
      const res = await fetch('/api/generate-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address, answers: merged }),
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const { plan } = await res.json();
      navigate('/dashboard', { state: { plan, address } });
    } catch (err) {
      setSubmitError(err.message || 'Failed to generate plan. Please try again.');
      setSubmitting(false);
    }
  };

  // Group fields by section
  const sections = SECTION_ORDER.map((sec) => ({
    name: sec,
    fields: fieldsToShow.filter((f) => f.section === sec),
  })).filter((s) => s.fields.length > 0);

  const requiredCount = fieldsToShow.filter((f) => f.required).length;

  return (
    <div style={{
      minHeight: '100vh',
      background: 'radial-gradient(circle at 50% -20%, #1e293b, #0f172a)',
    }}>
      {/* Header */}
      <header style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '1rem 2rem',
        borderBottom: '1px solid var(--card-border)',
        background: 'rgba(15, 23, 42, 0.8)',
        backdropFilter: 'blur(12px)',
        position: 'sticky', top: 0, zIndex: 10,
      }}>
        <h2 style={{ margin: 0, fontSize: '1.25rem' }}>
          <span className="text-gradient">RetroFi ATL</span>
        </h2>
        <button
          onClick={() => navigate('/')}
          style={{
            background: 'transparent', border: '1px solid var(--card-border)',
            color: 'var(--text-secondary)', padding: '0.4rem 0.9rem',
            borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem',
          }}
        >
          Start over
        </button>
      </header>

      <div style={{ maxWidth: '760px', margin: '0 auto', padding: '2.5rem 1.5rem 4rem' }}>
        {/* Page title */}
        <div style={{ marginBottom: '2rem' }}>
          <h1 style={{ fontSize: '1.75rem', marginBottom: '0.4rem' }}>
            <span className="text-gradient">Home Energy Profile</span>
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem' }}>
            {address} &nbsp;·&nbsp; {requiredCount} required fields
          </p>
        </div>

        {/* Pre-filled summary */}
        {prefilled.length > 0 && (
          <div className="glass-panel" style={{ padding: '1.25rem 1.5rem', marginBottom: '2rem' }}>
            <p style={{
              fontSize: '0.8rem', fontWeight: 600, letterSpacing: '0.06em',
              color: 'var(--success)', textTransform: 'uppercase', marginBottom: '0.9rem',
            }}>
              ✓ Pre-filled from public records
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem' }}>
              {prefilled.map(([key, label]) => (
                <div key={key} style={{
                  background: 'rgba(16, 185, 129, 0.08)',
                  border: '1px solid rgba(16, 185, 129, 0.2)',
                  borderRadius: '8px',
                  padding: '0.4rem 0.75rem',
                  fontSize: '0.82rem',
                  color: 'var(--text-secondary)',
                }}>
                  <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                    {formatPrefill(key, initialAnswers[key])}
                  </span>
                  {' '}— {label}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} noValidate>
          {sections.map((section) => (
            <div key={section.name} style={{ marginBottom: '2.5rem' }}>
              <h3 style={{
                fontSize: '0.75rem', fontWeight: 700, letterSpacing: '0.08em',
                textTransform: 'uppercase', color: 'var(--accent-primary)',
                marginBottom: '1.25rem',
              }}>
                {section.name}
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                {section.fields.map((field) => (
                  <div
                    key={field.key}
                    id={`field-${field.key}`}
                    className="glass-panel"
                    style={{
                      padding: '1.25rem 1.5rem',
                      border: errors[field.key]
                        ? '1px solid rgba(248, 113, 113, 0.5)'
                        : '1px solid var(--card-border)',
                    }}
                  >
                    <label style={{
                      display: 'block',
                      fontSize: '0.92rem',
                      fontWeight: 500,
                      color: 'var(--text-primary)',
                      marginBottom: '0.75rem',
                    }}>
                      {field.label}
                      {field.required && (
                        <span style={{ color: '#f87171', marginLeft: '0.25rem' }}>*</span>
                      )}
                    </label>
                    {field.type === 'number' ? (
                      <NumberField
                        field={field}
                        value={formValues[field.key]}
                        onChange={(v) => setValue(field.key, v)}
                        error={errors[field.key]}
                      />
                    ) : (
                      <>
                        <ChoiceField
                          field={field}
                          value={formValues[field.key]}
                          onChange={(v) => setValue(field.key, v)}
                          otherText={otherValues[field.key]}
                          onOtherText={(v) => setOtherValue(field.key, v)}
                        />
                        {errors[field.key] && (
                          <p style={{ color: '#f87171', fontSize: '0.78rem', marginTop: '0.4rem' }}>
                            {errors[field.key]}
                          </p>
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}

          {submitError && (
            <div style={{
              background: 'rgba(248, 113, 113, 0.1)', border: '1px solid rgba(248, 113, 113, 0.3)',
              borderRadius: '10px', padding: '1rem 1.25rem',
              color: '#f87171', marginBottom: '1.5rem', fontSize: '0.9rem',
            }}>
              {submitError}
            </div>
          )}

          <button
            type="submit"
            className="btn-primary"
            disabled={submitting}
            style={{ width: '100%', padding: '1rem', fontSize: '1rem' }}
          >
            {submitting ? 'Generating your plan…' : 'Generate My Retrofit Plan →'}
          </button>
        </form>
      </div>

      {submitting && (
        <div style={{
          position: 'fixed', inset: 0,
          background: 'rgba(15, 23, 42, 0.85)',
          backdropFilter: 'blur(8px)',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          gap: '1.5rem', zIndex: 50,
        }}>
          <div style={{ display: 'flex', gap: '8px' }}>
            {[0, 1, 2].map((i) => (
              <span key={i} style={{
                width: '10px', height: '10px',
                background: 'var(--accent-primary)',
                borderRadius: '50%', display: 'inline-block',
                animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
              }} />
            ))}
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '1rem' }}>
            Building your personalised retrofit plan…
          </p>
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50% { opacity: 1; transform: scale(1.2); }
        }
      `}</style>
    </div>
  );
}

export default Questionnaire;
