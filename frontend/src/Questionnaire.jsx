import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { generatePlan } from './api';

const FIELDS = [
  { key: 'monthly_electricity_bill', label: 'Average monthly electricity bill', type: 'number', unit: '$', placeholder: 'e.g. 120', required: true, section: 'Monthly Costs' },
  { key: 'monthly_gas_bill', label: 'Average monthly gas bill', type: 'number', unit: '$', placeholder: 'e.g. 60', required: true, section: 'Monthly Costs' },
  { key: 'home_ownership_status', label: 'Home ownership', type: 'choice', required: true, section: 'Your Home', options: ['Own', 'Rent / Lease'] },
  { key: 'home_type', label: 'Home type', type: 'choice', required: false, section: 'Your Home', options: ['Single Family', 'Townhouse', 'Condo / Apartment', 'Other'] },
  { key: 'year_built', label: 'Year built', type: 'choice', required: false, section: 'Your Home', options: ['Before 1980', '1980 - 2000', '2001 - 2015', 'After 2015'] },
  { key: 'square_footage', label: 'Home square footage', type: 'choice', required: false, section: 'Your Home', options: ['Under 1,000 sq ft', '1,000 - 1,500 sq ft', '1,500 - 2,500 sq ft', 'Over 2,500 sq ft'] },
  { key: 'num_occupants', label: 'Number of occupants', type: 'choice', required: false, section: 'Your Home', options: ['1', '2', '3', '4', '5 or more'] },
  { key: 'roof_type', label: 'Roof type', type: 'choice', required: true, section: 'Your Home', options: ['Asphalt Shingle', 'Metal', 'Tile', 'Flat / TPO', 'Other'] },
  { key: 'primary_heating_fuel', label: 'Primary heating fuel', type: 'choice', required: false, section: 'Energy & Appliances', options: ['Gas', 'Electric', 'Oil', 'Propane'] },
  { key: 'appliances_fuel', label: 'Water heating and cooking fuel', type: 'choice', required: true, section: 'Energy & Appliances', options: ['Electric', 'Gas', 'Mixed (both)'] },
  { key: 'ev_owner_or_planning', label: 'EV ownership or plans', type: 'choice', required: false, section: 'Future Plans', options: ['Yes, I own one', 'Planning within 3 years', 'No'] },
  { key: 'planning_roof_replacement', label: 'Roof replacement in next 5 years', type: 'choice', required: false, section: 'Future Plans', options: ['Yes', 'No', 'Not sure'] },
  { key: 'planned_electric_additions', label: 'Major electric additions planned', type: 'choice', required: false, section: 'Future Plans', options: ['Yes', 'No'] },
];
const SECTION_ORDER = ['Monthly Costs', 'Your Home', 'Energy & Appliances', 'Future Plans'];

function Questionnaire() {
  const location = useLocation();
  const navigate = useNavigate();
  const { answers: initialAnswers, address } = location.state || {};
  const [formValues, setFormValues] = useState({});
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  if (!initialAnswers) {
    navigate('/');
    return null;
  }

  const fieldsToShow = FIELDS.filter(
    (field) => initialAnswers[field.key] === null || initialAnswers[field.key] === undefined,
  );

  const setValue = (key, value) => {
    setFormValues((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: '' }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const nextErrors = validate(fieldsToShow, formValues);
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }

    const merged = { ...initialAnswers };
    fieldsToShow.forEach((field) => {
      const raw = (formValues[field.key] || '').toString().trim();
      if (!raw) return;
      if (field.type === 'number') {
        const parsed = parseFloat(raw.replace(/[$,]/g, ''));
        merged[field.key] = `$${parsed.toFixed(0)}`;
      } else {
        merged[field.key] = raw;
      }
    });

    setSubmitting(true);
    setSubmitError('');
    try {
      const result = await generatePlan(address, merged);
      navigate('/dashboard', { state: { result } });
    } catch (err) {
      setSubmitError(err.message || 'Failed to generate plan. Please try again.');
      setSubmitting(false);
    }
  };

  const sections = SECTION_ORDER.map((section) => ({
    name: section,
    fields: fieldsToShow.filter((field) => field.section === section),
  })).filter((section) => section.fields.length > 0);

  return (
    <div style={{ minHeight: '100vh', background: 'radial-gradient(circle at 50% -20%, #1e293b, #0f172a)' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem 2rem', borderBottom: '1px solid var(--card-border)', background: 'rgba(15, 23, 42, 0.8)', position: 'sticky', top: 0, zIndex: 10 }}>
        <h2 style={{ margin: 0, fontSize: '1.25rem' }}>
          <span className="text-gradient">RetroFi ATL</span>
        </h2>
        <button onClick={() => navigate('/')} style={{ background: 'transparent', border: '1px solid var(--card-border)', color: 'var(--text-secondary)', padding: '0.4rem 0.9rem', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem' }}>
          Start over
        </button>
      </header>

      <div style={{ maxWidth: '760px', margin: '0 auto', padding: '2.5rem 1.5rem 4rem' }}>
        <div style={{ marginBottom: '2rem' }}>
          <h1 style={{ fontSize: '1.75rem', marginBottom: '0.4rem' }}>
            <span className="text-gradient">Home Energy Profile</span>
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem' }}>{address}</p>
        </div>

        <form onSubmit={handleSubmit} noValidate>
          {sections.map((section) => (
            <div key={section.name} style={{ marginBottom: '2.5rem' }}>
              <h3 style={{ fontSize: '0.75rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--accent-primary)', marginBottom: '1.25rem' }}>
                {section.name}
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                {section.fields.map((field) => (
                  <div key={field.key} className="glass-panel" style={{ padding: '1.25rem 1.5rem', border: errors[field.key] ? '1px solid rgba(248, 113, 113, 0.5)' : '1px solid var(--card-border)' }}>
                    <label style={{ display: 'block', fontSize: '0.92rem', fontWeight: 500, color: 'var(--text-primary)', marginBottom: '0.75rem' }}>
                      {field.label}
                      {field.required && <span style={{ color: '#f87171', marginLeft: '0.25rem' }}>*</span>}
                    </label>
                    {field.type === 'number' ? (
                      <input className="input-premium" type="text" inputMode="decimal" placeholder={field.placeholder} value={formValues[field.key] || ''} onChange={(event) => setValue(field.key, event.target.value)} style={{ width: '100%', maxWidth: '220px' }} />
                    ) : (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                        {field.options.map((option) => (
                          <button key={option} type="button" onClick={() => setValue(field.key, option)} style={{ padding: '0.5rem 1rem', borderRadius: '999px', cursor: 'pointer', background: formValues[field.key] === option ? 'rgba(59, 130, 246, 0.3)' : 'rgba(59, 130, 246, 0.07)', border: formValues[field.key] === option ? '1px solid rgba(59, 130, 246, 0.8)' : '1px solid rgba(59, 130, 246, 0.25)', color: formValues[field.key] === option ? '#e2e8f0' : 'var(--text-secondary)' }}>
                            {option}
                          </button>
                        ))}
                      </div>
                    )}
                    {errors[field.key] && <p style={{ color: '#f87171', fontSize: '0.78rem', marginTop: '0.4rem' }}>{errors[field.key]}</p>}
                  </div>
                ))}
              </div>
            </div>
          ))}

          {submitError && (
            <div style={{ background: 'rgba(248, 113, 113, 0.1)', border: '1px solid rgba(248, 113, 113, 0.3)', borderRadius: '10px', padding: '1rem 1.25rem', color: '#f87171', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
              {submitError}
            </div>
          )}

          <button type="submit" className="btn-primary" disabled={submitting} style={{ width: '100%', padding: '1rem', fontSize: '1rem', opacity: submitting ? 0.7 : 1 }}>
            {submitting ? 'Generating your plan...' : 'Generate My Retrofit Plan'}
          </button>
        </form>
      </div>
    </div>
  );
}

function validate(fields, values) {
  const errors = {};
  fields.forEach((field) => {
    if (!field.required) return;
    const value = (values[field.key] || '').toString().trim();
    if (!value) {
      errors[field.key] = 'This field is required.';
      return;
    }
    if (field.type === 'number') {
      const parsed = parseFloat(value.replace(/[$,]/g, ''));
      if (Number.isNaN(parsed) || parsed < 0) {
        errors[field.key] = 'Enter a valid dollar amount.';
      }
    }
  });
  return errors;
}

export default Questionnaire;
