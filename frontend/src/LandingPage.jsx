import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getGoogleMapsConfig, lookupProperty } from './api';

const GOOGLE_MAPS_SCRIPT_ID = 'google-maps-places-script';
let googlePlacesScriptPromise;

const MODE_OPTIONS = [
  {
    id: 'homeowner',
    label: 'Homeowner',
    description: 'A single home you own and live in.',
    context: { mode: 'homeowner', role: 'homeowner', scope: 'single_property' },
  },
  {
    id: 'landlord',
    label: 'Landlord / Multifamily',
    description: 'A rental property, multifamily building, or mixed-use asset.',
    context: { mode: 'landlord', role: 'landlord', scope: 'single_building' },
  },
  {
    id: 'enterprise',
    label: 'Enterprise / Portfolio',
    description: 'One asset now, with portfolio ranking support later.',
    context: { mode: 'enterprise', role: 'enterprise_asset_manager', scope: 'portfolio' },
  },
];

function loadGooglePlacesScript(apiKey) {
  if (!apiKey) {
    return Promise.reject(new Error('Missing Google Maps API key.'));
  }

  if (window.google?.maps?.places) {
    return Promise.resolve();
  }

  if (googlePlacesScriptPromise) {
    return googlePlacesScriptPromise;
  }

  googlePlacesScriptPromise = new Promise((resolve, reject) => {
    const existingScript = document.getElementById(GOOGLE_MAPS_SCRIPT_ID);
    if (existingScript) {
      existingScript.addEventListener('load', resolve, { once: true });
      existingScript.addEventListener('error', reject, { once: true });
      return;
    }

    const script = document.createElement('script');
    script.id = GOOGLE_MAPS_SCRIPT_ID;
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&libraries=places`;
    script.async = true;
    script.defer = true;
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });

  return googlePlacesScriptPromise;
}

function AddressAutocomplete({ value, onChange, disabled }) {
  const inputRef = useRef(null);
  const autocompleteRef = useRef(null);

  useEffect(() => {
    let isMounted = true;
    let placeChangedListener;

    getGoogleMapsConfig()
      .then(({ api_key: apiKey }) => loadGooglePlacesScript(apiKey))
      .then(() => {
        if (!isMounted || !inputRef.current || autocompleteRef.current) {
          return;
        }

        autocompleteRef.current = new window.google.maps.places.Autocomplete(inputRef.current, {
          componentRestrictions: { country: 'us' },
          fields: ['formatted_address', 'geometry', 'place_id'],
          types: ['address'],
        });

        placeChangedListener = autocompleteRef.current.addListener('place_changed', () => {
          const place = autocompleteRef.current.getPlace();
          const formattedAddress = place.formatted_address || inputRef.current.value;
          if (formattedAddress) {
            onChange(formattedAddress);
          }
        });
      })
      .catch(() => {
        // Keep manual address entry available if Places cannot load.
      });

    return () => {
      isMounted = false;
      if (placeChangedListener) {
        window.google?.maps?.event?.removeListener(placeChangedListener);
      }
    };
  }, [onChange]);

  return (
    <input
      ref={inputRef}
      type="text"
      className="input-premium"
      placeholder="Enter your address (e.g. 123 Peachtree St NE, Atlanta, GA)"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      autoComplete="street-address"
      disabled={disabled}
      required
    />
  );
}

function LandingPage() {
  const [address, setAddress] = useState('');
  const [selectedMode, setSelectedMode] = useState(MODE_OPTIONS[0]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleSearch = async (e) => {
    e.preventDefault();
    const trimmed = address.trim();
    if (!trimmed) {
      return;
    }

    setLoading(true);
    setError('');
    try {
      const context = selectedMode.context;
      const { pre_filled, meta, mode } = await lookupProperty(trimmed, context);
      navigate('/verify', {
        state: {
          pre_filled,
          meta,
          mode: mode || context.mode,
          requestedMode: context.mode,
          role: context.role,
          scope: context.scope,
          address: trimmed,
        },
      });
    } catch (err) {
      setError(err.message || 'Could not find that address. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ 
      minHeight: '100vh', 
      display: 'flex', 
      flexDirection: 'column',
      alignItems: 'center', 
      justifyContent: 'center',
      padding: '2rem',
      background: 'radial-gradient(circle at 50% -20%, #1e293b, #0f172a)'
    }}>
      <div className="glass-panel animate-fade-in" style={{ maxWidth: '760px', width: '100%', textAlign: 'center' }}>
        <h1 style={{ fontSize: '3rem', marginBottom: '1rem' }}>
          <span className="text-gradient">RetroFi ATL</span>
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '1.25rem', marginBottom: '2rem' }}>
          Discover retrofit opportunities for Atlanta homes, rental buildings, and portfolios without breaking the homeowner flow.
        </p>

        <form onSubmit={handleSearch} style={{ display: 'flex', gap: '1rem', flexDirection: 'column' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem', textAlign: 'left' }}>
            {MODE_OPTIONS.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => setSelectedMode(option)}
                style={{
                  padding: '1rem',
                  borderRadius: '12px',
                  cursor: 'pointer',
                  background: selectedMode.id === option.id ? 'rgba(59, 130, 246, 0.25)' : 'rgba(59, 130, 246, 0.07)',
                  border: selectedMode.id === option.id ? '1px solid rgba(59, 130, 246, 0.8)' : '1px solid rgba(59, 130, 246, 0.25)',
                  color: 'var(--text-primary)',
                }}
              >
                <strong style={{ display: 'block', marginBottom: '0.4rem' }}>{option.label}</strong>
                <span style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', lineHeight: 1.4 }}>{option.description}</span>
              </button>
            ))}
          </div>
          <AddressAutocomplete value={address} onChange={setAddress} disabled={loading} />
          {error && (
            <p style={{ color: '#f87171', fontSize: '0.9rem', textAlign: 'left', margin: 0 }}>
              {error}
            </p>
          )}
          <button type="submit" className="btn-primary" style={{ padding: '1rem', fontSize: '1.1rem', opacity: loading ? 0.7 : 1 }} disabled={loading}>
            {loading ? 'Looking up your property...' : selectedMode.id === 'homeowner' ? 'Get Home Retrofit Plan' : 'Start Building Analysis'}
          </button>
        </form>
      </div>

      {/* Decorative background elements */}
      <div style={{
        position: 'absolute',
        top: '20%',
        left: '10%',
        width: '300px',
        height: '300px',
        background: 'var(--accent-primary)',
        filter: 'blur(150px)',
        opacity: '0.15',
        zIndex: -1,
        borderRadius: '50%'
      }}></div>
      <div style={{
        position: 'absolute',
        bottom: '20%',
        right: '10%',
        width: '400px',
        height: '400px',
        background: '#8b5cf6',
        filter: 'blur(150px)',
        opacity: '0.15',
        zIndex: -1,
        borderRadius: '50%'
      }}></div>
    </div>
  );
}

export default LandingPage;
