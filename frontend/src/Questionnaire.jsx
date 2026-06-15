import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { generatePlan } from './api';

const FIELDS = [
  { key: 'monthly_electricity_bill', label: 'Average monthly electricity bill', type: 'number', valueType: 'money', unit: '$', placeholder: 'e.g. 120', required: true, section: 'Monthly Costs' },
  { key: 'monthly_gas_bill', label: 'Average monthly gas bill', type: 'number', valueType: 'money', unit: '$', placeholder: 'e.g. 60', required: true, section: 'Monthly Costs' },
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
  { key: 'primary_goal', label: 'Primary goal', type: 'choice', required: false, section: 'Future Plans', options: ['Lower bills', 'Backup power during outages', 'Reduce carbon footprint', 'Increase home value', 'Other'] },
];
const SECTION_ORDER = ['Monthly Costs', 'Your Home', 'Energy & Appliances', 'Future Plans'];

const BUILDING_FIELDS = [
  { key: 'role', label: 'Your role', type: 'choice', required: true, section: 'Role & Scope', options: ['Landlord', 'Property manager', 'Owner-operator', 'Enterprise asset manager'] },
  { key: 'scope', label: 'What are you evaluating?', type: 'choice', required: true, section: 'Role & Scope', options: ['Single building', 'Portfolio'] },
  { key: 'building_type', label: 'Building type', type: 'choice', required: true, section: 'Building Basics', options: ['Single-family rental', 'Duplex / Triplex / Quadplex', 'Garden-style multifamily', 'Mid-rise multifamily', 'High-rise multifamily', 'Mixed-use', 'Commercial / Office / Retail'] },
  { key: 'units', label: 'Number of units', type: 'number', placeholder: 'e.g. 24', required: true, section: 'Building Basics' },
  { key: 'square_footage', label: 'Gross floor area', type: 'number', placeholder: 'e.g. 24000', required: true, section: 'Building Basics' },
  { key: 'occupancy', label: 'Occupancy or operating schedule', type: 'number', placeholder: 'e.g. 22 occupied units or 95', required: false, section: 'Building Basics' },
  { key: 'utility_structure', label: 'Utility / meter structure', type: 'choice', required: true, section: 'Utilities & Meters', options: ['Master-metered whole building', 'Common-area meter plus tenant meters', 'Individually metered units', 'Mixed / unknown'] },
  { key: 'electric_bill_responsibility', label: 'Who pays electric bills?', type: 'choice', required: true, section: 'Utilities & Meters', options: ['Owner pays all', 'Tenant pays in-unit, owner pays common areas', 'Tenant pays all', 'Mixed / unknown'] },
  { key: 'gas_bill_responsibility', label: 'Who pays gas or delivered fuel?', type: 'choice', required: false, section: 'Utilities & Meters', options: ['Owner pays all', 'Tenant pays in-unit, owner pays common areas', 'Tenant pays all', 'No gas / all electric', 'Mixed / unknown'] },
  { key: 'annual_electric_kwh', label: '12-month electric usage', type: 'number', placeholder: 'kWh, if available', required: false, section: 'Utility History' },
  { key: 'annual_electric_cost', label: '12-month electric cost', type: 'number', valueType: 'money_number', placeholder: 'e.g. 36000', required: false, section: 'Utility History' },
  { key: 'annual_gas_therms', label: '12-month gas or fuel usage', type: 'number', placeholder: 'therms, if available', required: false, section: 'Utility History' },
  { key: 'annual_gas_cost', label: '12-month gas or fuel cost', type: 'number', valueType: 'money_number', placeholder: 'e.g. 12000', required: false, section: 'Utility History' },
  { key: 'hvac_system_type', label: 'Primary HVAC system', type: 'choice', required: true, section: 'Systems', options: ['Central plant', 'Packaged rooftop units', 'Split systems', 'PTAC / PTHP', 'Individual furnaces', 'Heat pumps', 'Unknown'] },
  { key: 'domestic_hot_water_type', label: 'Domestic hot water system', type: 'choice', required: true, section: 'Systems', options: ['Central gas', 'Central electric', 'In-unit gas', 'In-unit electric', 'Heat pump water heater', 'Unknown'] },
  { key: 'roof_control', label: 'Roof control', type: 'choice', required: false, section: 'Systems', options: ['Owner controls roof', 'Shared / HOA control', 'Roof replacement planned', 'Structural constraints known', 'Unknown'] },
  { key: 'primary_goal', label: 'Primary objective', type: 'choice', required: false, section: 'Goals', options: ['Lower operating expenses', 'Improve NOI / asset value', 'Reduce tenant bills', 'Meet climate or compliance goals', 'Improve comfort / complaints', 'Plan capital budget', 'Identify incentives'] },
  { key: 'planning_horizon', label: 'Planning horizon', type: 'choice', required: false, section: 'Goals', options: ['Immediate', '0-12 months', '1-3 years', '3-5 years'] },
  { key: 'capex_budget_range', label: 'Capex budget range', type: 'choice', required: false, section: 'Goals', options: ['Under $25k', '$25k-$100k', '$100k-$500k', 'Over $500k', 'Not sure'] },
];
const BUILDING_SECTION_ORDER = ['Role & Scope', 'Building Basics', 'Utilities & Meters', 'Utility History', 'Systems', 'Goals'];

function Questionnaire() {
  const location = useLocation();
  const navigate = useNavigate();
  const { answers: initialAnswers, address, mode = 'homeowner', requestedMode, role, scope } = location.state || {};
  const [formValues, setFormValues] = useState({});
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  if (!initialAnswers) {
    navigate('/');
    return null;
  }

  const activeFields = mode === 'homeowner' ? FIELDS : BUILDING_FIELDS;
  const sectionOrder = mode === 'homeowner' ? SECTION_ORDER : BUILDING_SECTION_ORDER;
  const fieldsToShow = activeFields.filter(
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
        merged[field.key] = field.valueType === 'money' ? `$${parsed.toFixed(0)}` : parsed;
      } else {
        merged[field.key] = raw;
      }
    });
    if (mode !== 'homeowner') {
      merged.mode = requestedMode || mode;
      merged.role = merged.role || role;
      merged.scope = merged.scope || scope;
      merged.utility_history = buildUtilityHistory(merged);
    }

    setSubmitting(true);
    setSubmitError('');
    try {
      const result = await generatePlan(address, merged, { mode: requestedMode || mode, role: merged.role || role, scope: merged.scope || scope });
      navigate('/dashboard', { state: { result } });
    } catch (err) {
      setSubmitError(err.message || 'Failed to generate plan. Please try again.');
      setSubmitting(false);
    }
  };

  const sections = sectionOrder.map((section) => ({
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
            <span className="text-gradient">{mode === 'homeowner' ? 'Home Energy Profile' : 'Building Energy Profile'}</span>
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
            {submitting ? 'Generating your plan...' : mode === 'homeowner' ? 'Generate My Retrofit Plan' : 'Generate Building Quick Estimate'}
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

function buildUtilityHistory(values) {
  const history = [];
  if (values.annual_electric_kwh || values.annual_electric_cost) {
    history.push({
      fuel_type: 'electric',
      months: 12,
      total_usage: values.annual_electric_kwh || null,
      total_cost: values.annual_electric_cost || null,
      usage_unit: 'kWh',
      meter_scope: values.utility_structure || null,
    });
  }
  if (values.annual_gas_therms || values.annual_gas_cost) {
    history.push({
      fuel_type: 'gas',
      months: 12,
      total_usage: values.annual_gas_therms || null,
      total_cost: values.annual_gas_cost || null,
      usage_unit: 'therms',
      meter_scope: values.utility_structure || null,
    });
  }
  return history;
}

export default Questionnaire;
