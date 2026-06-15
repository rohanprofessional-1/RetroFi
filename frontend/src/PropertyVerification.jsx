import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const FIELD_LABELS = {
  home_ownership_status: 'Home Ownership',
  has_cooling: 'Has Cooling',
  cooling_type: 'Cooling Type',
  roof_type: 'Roof Type',
  monthly_electricity_bill: 'Monthly Electricity Bill',
  monthly_gas_bill: 'Monthly Gas Bill',
  appliances_fuel: 'Appliances Fuel',
  home_type: 'Home Type',
  year_built: 'Year Built',
  primary_heating_fuel: 'Primary Heating Fuel',
  ev_owner_or_planning: 'EV Ownership / Plans',
  planning_roof_replacement: 'Roof Replacement Plans',
  primary_goal: 'Primary Goal',
  square_footage: 'Square Footage',
  num_occupants: 'Estimated Occupants',
  planned_electric_additions: 'Planned Electric Additions',
};

function formatValue(key, value) {
  if (value === null || value === undefined) return null;
  if (key === 'square_footage') return `${Number(value).toLocaleString()} sq ft`;
  if (key === 'num_occupants') return `~${value} people`;
  if (key === 'home_ownership_status') {
    return value === 'owner' ? 'Owner-Occupied' : value === 'renter' ? 'Renter' : value;
  }
  if (key === 'has_cooling') {
    const normalized = String(value).toLowerCase().trim();
    return (value === true || normalized === 'true' || normalized === 'yes' || value === 1) ? 'Yes' : 'No';
  }
  return String(value).replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function EditableField({ fieldKey, label, value, isEditing, isEdited, onEdit, onChange, onBlur }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      gap: '0.75rem',
      padding: '0.6rem 0.75rem',
      background: isEdited ? 'rgba(245, 158, 11, 0.08)' : 'rgba(34, 197, 94, 0.07)',
      border: `1px solid ${isEdited ? 'rgba(245, 158, 11, 0.35)' : 'rgba(34, 197, 94, 0.2)'}`,
      borderRadius: '8px',
      transition: 'border-color 0.2s ease, background 0.2s ease',
    }}>
      <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', flexShrink: 0 }}>
        {label}
      </span>

      {isEditing ? (
        <input
          autoFocus
          value={value ?? ''}
          onChange={(e) => onChange(fieldKey, e.target.value)}
          onBlur={onBlur}
          onKeyDown={(e) => e.key === 'Enter' && onBlur()}
          style={{
            background: 'transparent',
            border: 'none',
            borderBottom: '1px solid #22c55e',
            color: 'var(--text-primary)',
            fontSize: '0.9rem',
            fontWeight: 500,
            outline: 'none',
            textAlign: 'right',
            minWidth: 0,
            flex: 1,
            padding: '0 0 2px',
          }}
        />
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0 }}>
          <span style={{
            color: isEdited ? '#fbbf24' : 'var(--text-primary)',
            fontWeight: 500,
            fontSize: '0.9rem',
            textAlign: 'right',
          }}>
            {formatValue(fieldKey, value)}
          </span>
          <button
            onClick={() => onEdit(fieldKey)}
            title="Edit this value"
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'rgba(34, 197, 94, 0.55)',
              padding: '2px',
              borderRadius: '4px',
              display: 'flex',
              alignItems: 'center',
              flexShrink: 0,
              transition: 'color 0.15s ease',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.color = '#22c55e'; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = 'rgba(34, 197, 94, 0.55)'; }}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}

function PropertyVerification() {
  const location = useLocation();
  const navigate = useNavigate();
  const { pre_filled, meta, address } = location.state || {};

  const [editedValues, setEditedValues] = useState({});
  const [editingKey, setEditingKey] = useState(null);

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

  const getValue = (key) => (editedValues[key] !== undefined ? editedValues[key] : pre_filled[key]);
  const isEdited = (key) => editedValues[key] !== undefined && editedValues[key] !== String(pre_filled[key]);
  const editedCount = confirmed.filter(([key]) => isEdited(key)).length;

  const handleEdit = (key) => setEditingKey(key);
  const handleChange = (key, val) => setEditedValues((prev) => ({ ...prev, [key]: val }));
  const handleBlur = () => setEditingKey(null);

  const handleContinue = () => {
    const normalized = { ...editedValues };
    if (normalized.has_cooling !== undefined) {
      const v = String(normalized.has_cooling).toLowerCase().trim();
      normalized.has_cooling = v === 'true' || v === 'yes' || v === '1';
    }
    const mergedAnswers = { ...pre_filled, ...normalized, _questions_asked: 0 };
    navigate('/questionnaire', { state: { answers: mergedAnswers, address } });
  };

  return (
    <div style={{ minHeight: '100vh', position: 'relative', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem' }}>

      {/* Background image */}
      <div style={{
        position: 'absolute',
        inset: 0,
        backgroundImage: 'url(https://images.unsplash.com/photo-1640802396402-094375631000?q=80&w=2072&auto=format&fit=crop)',
        backgroundSize: 'cover',
        backgroundPosition: 'center 40%',
        zIndex: 0,
      }} />

      {/* Dark overlay */}
      <div style={{
        position: 'absolute',
        inset: 0,
        background: 'linear-gradient(160deg, rgba(7,24,16,0.72) 0%, rgba(7,24,16,0.88) 100%)',
        zIndex: 1,
      }} />

      {/* Content */}
      <div className="animate-fade-in" style={{ position: 'relative', zIndex: 2, maxWidth: '820px', width: '100%' }}>

        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <h1 style={{ fontSize: '2.1rem', marginBottom: '0.6rem' }}>
            <span className="text-gradient">Verify Property Details</span>
          </h1>
          <p style={{ color: '#f0fdf4', fontSize: '1.05rem', fontWeight: 700, opacity: 0.9 }}>
            {meta?.formatted_address || address}
          </p>
          {editedCount > 0 && (
            <p style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: '#fbbf24' }}>
              {editedCount} field{editedCount > 1 ? 's' : ''} edited — your changes will be used in the plan
            </p>
          )}
        </div>

        {/* Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>

          {/* Confirmed fields — editable */}
          <div className="glass-panel" style={{ padding: '1.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0 }}>From Public Records</h3>
            </div>

            {confirmed.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                No fields could be pre-filled for this address.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                {confirmed.map(([key, label]) => (
                  <EditableField
                    key={key}
                    fieldKey={key}
                    label={label}
                    value={getValue(key)}
                    isEditing={editingKey === key}
                    isEdited={isEdited(key)}
                    onEdit={handleEdit}
                    onChange={handleChange}
                    onBlur={handleBlur}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Pending questions */}
          <div className="glass-panel" style={{ padding: '1.5rem' }}>
            <h3 style={{ marginBottom: '0.5rem' }}>We'll Ask You About</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', marginBottom: '1rem' }}>
              Up to {Math.min(pending.length, 10)} quick questions for fields public records don't cover.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {pending.map(([key, label]) => (
                <div key={key} style={{ padding: '0.5rem 0.75rem', background: 'rgba(148, 163, 184, 0.05)', border: '1px solid rgba(148, 163, 184, 0.15)', borderRadius: '8px', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                  {label}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Action buttons */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: '0.875rem', flexWrap: 'wrap' }}>
          <button
            onClick={handleContinue}
            style={{
              background: '#22c55e',
              color: '#071810',
              border: 'none',
              padding: '0.9rem 2.5rem',
              borderRadius: '10px',
              fontSize: '1rem',
              fontWeight: 700,
              cursor: 'pointer',
              boxShadow: '0 4px 18px rgba(34, 197, 94, 0.4)',
              transition: 'background 0.2s ease, box-shadow 0.2s ease',
              fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = '#16a34a'; e.currentTarget.style.boxShadow = '0 6px 22px rgba(34,197,94,0.5)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = '#22c55e'; e.currentTarget.style.boxShadow = '0 4px 18px rgba(34,197,94,0.4)'; }}
          >
            {editedCount > 0 ? 'Save Changes & Continue →' : 'Continue →'}
          </button>

          <button
            onClick={() => navigate('/')}
            style={{
              background: 'rgba(248, 113, 113, 0.12)',
              border: '1px solid rgba(248, 113, 113, 0.4)',
              color: '#fca5a5',
              padding: '0.9rem 1.75rem',
              borderRadius: '10px',
              fontSize: '1rem',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'background 0.2s ease, border-color 0.2s ease',
              fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(248,113,113,0.22)'; e.currentTarget.style.borderColor = 'rgba(248,113,113,0.6)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(248,113,113,0.12)'; e.currentTarget.style.borderColor = 'rgba(248,113,113,0.4)'; }}
          >
            Wrong Address
          </button>
        </div>
      </div>
    </div>
  );
}

export default PropertyVerification;
