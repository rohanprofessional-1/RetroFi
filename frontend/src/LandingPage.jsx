import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getGoogleMapsConfig, lookupProperty } from './api';

const GOOGLE_MAPS_SCRIPT_ID = 'google-maps-places-script';
let googlePlacesScriptPromise;

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
      placeholder="Enter your home address"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      autoComplete="street-address"
      disabled={disabled}
      required
    />
  );
}

async function reverseGeocode(lat, lng, apiKey) {
  const res = await fetch(
    `https://maps.googleapis.com/maps/api/geocode/json?latlng=${lat},${lng}&key=${apiKey}`
  );
  const data = await res.json();
  const result = data.results?.[0];
  if (!result) throw new Error('No address found for your location.');
  return result.formatted_address;
}

function LandingPage() {
  const [address, setAddress] = useState('');
  const [loading, setLoading] = useState(false);
  const [locating, setLocating] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleUseLocation = async () => {
    if (!navigator.geolocation) {
      setError('Your browser does not support geolocation.');
      return;
    }
    setLocating(true);
    setError('');
    try {
      const position = await new Promise((resolve, reject) =>
        navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 10000 })
      );
      const { latitude: lat, longitude: lng } = position.coords;
      const { api_key: apiKey } = await getGoogleMapsConfig();
      const resolved = await reverseGeocode(lat, lng, apiKey);
      setAddress(resolved);
    } catch (err) {
      if (err.code === 1) {
        setError('Location access was denied. Please enter your address manually.');
      } else {
        setError('Could not detect your location. Please enter your address manually.');
      }
    } finally {
      setLocating(false);
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    const trimmed = address.trim();
    if (!trimmed) return;

    setLoading(true);
    setError('');
    try {
      const { pre_filled, meta } = await lookupProperty(trimmed);
      navigate('/verify', { state: { pre_filled, meta, address: trimmed } });
    } catch (err) {
      setError(err.message || 'Could not find that address. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      position: 'relative',
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '2rem',
    }}>

      {/* Background: photo of solar panels on a house roof */}
      <div style={{
        position: 'absolute',
        inset: 0,
        backgroundImage: 'url(https://images.unsplash.com/photo-1640802396402-094375631000?q=80&w=2072&auto=format&fit=crop)',
        backgroundSize: 'cover',
        backgroundPosition: 'center 40%',
        zIndex: 0,
      }} />

      {/* Dark green gradient overlay for readability */}
      <div style={{
        position: 'absolute',
        inset: 0,
        background: 'linear-gradient(160deg, rgba(7,24,16,0.68) 0%, rgba(7,24,16,0.92) 100%)',
        zIndex: 1,
      }} />

      {/* Content */}
      <div className="animate-fade-in" style={{
        position: 'relative',
        zIndex: 2,
        maxWidth: '560px',
        width: '100%',
        textAlign: 'center',
      }}>

        {/* Badge */}
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.4rem',
          background: 'rgba(34, 197, 94, 0.25)',
          border: '1px solid rgba(34, 197, 94, 0.3)',
          borderRadius: '999px',
          padding: '0.35rem 1rem',
          marginBottom: '1.75rem',
          fontSize: '0.75rem',
          color: '#4ade80',
          letterSpacing: '0.07em',
          textTransform: 'uppercase',
          fontWeight: 600,
        }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 2L9.5 8.5H3L8 13l-2 7 6-4 6 4-2-7 5-4.5h-6.5L12 2z"/>
          </svg>
          AI-Powered Home Energy Planner
        </div>

        {/* Headline */}
        <h1 style={{ fontSize: '3.75rem', fontWeight: 700, marginBottom: '1.25rem', lineHeight: 1.1 }}>
          <span className="text-gradient">RetroFi</span>
        </h1>

        {/* Subheadline */}
        <p style={{
          color: 'rgba(240, 253, 244, 0.75)',
          fontSize: '1.15rem',
          lineHeight: 1.7,
          marginBottom: '2.5rem',
        }}>
          Discover the smartest upgrades for your home — cut energy costs, reduce your carbon footprint, and prioritize renewable energy.
        </p>

        {/* Form card */}
        <div className="glass-panel" style={{
          padding: '1.75rem 2rem',
          textAlign: 'left',
          borderRadius: '20px',
          background: 'rgba(10, 26, 20, 0.72)',
          border: '1px solid rgba(34, 197, 94, 0.18)',
        }}>
          <label style={{
            display: 'block',
            fontSize: '0.8rem',
            fontWeight: 600,
            color: 'var(--text-primary)',
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            marginBottom: '0.6rem',
          }}>
            Your Home Address
          </label>

          <form onSubmit={handleSearch} style={{ display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
            <AddressAutocomplete value={address} onChange={setAddress} disabled={loading || locating} />

            <button
              type="button"
              onClick={handleUseLocation}
              disabled={locating || loading}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
                background: 'none',
                border: 'none',
                padding: '0.15rem 0',
                cursor: locating || loading ? 'default' : 'pointer',
                color: locating ? 'rgba(74, 222, 128, 0.5)' : 'rgba(74, 222, 128, 0.85)',
                fontSize: '0.82rem',
                fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
                fontWeight: 500,
                width: 'fit-content',
                transition: 'color 0.2s ease',
              }}
              onMouseEnter={(e) => {
                if (!locating && !loading) e.currentTarget.style.color = '#4ade80';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.color = locating ? 'rgba(74, 222, 128, 0.5)' : 'rgba(74, 222, 128, 0.85)';
              }}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3"/>
                <path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>
                <path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z" strokeOpacity="0"/>
              </svg>
              {locating ? 'Detecting location…' : 'Use my current location'}
            </button>

            {error && (
              <p style={{ color: '#f87171', fontSize: '0.875rem', margin: 0 }}>
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                background: '#22c55e',
                color: '#071810',
                border: 'none',
                padding: '1rem 1.5rem',
                borderRadius: '10px',
                fontSize: '1rem',
                fontWeight: 700,
                cursor: loading ? 'default' : 'pointer',
                opacity: loading ? 0.7 : 1,
                transition: 'background 0.2s ease, box-shadow 0.2s ease, transform 0.15s ease',
                boxShadow: '0 4px 20px rgba(34, 197, 94, 0.45)',
                letterSpacing: '0.01em',
                fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
              }}
              onMouseEnter={(e) => {
                if (!loading) {
                  e.currentTarget.style.background = '#16a34a';
                  e.currentTarget.style.transform = 'translateY(-1px)';
                  e.currentTarget.style.boxShadow = '0 6px 24px rgba(34, 197, 94, 0.55)';
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = '#22c55e';
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.boxShadow = '0 4px 20px rgba(34, 197, 94, 0.45)';
              }}
            >
              {loading ? 'Looking up your property…' : 'Get My Retrofit Plan →'}
            </button>
          </form>
        </div>

        {/* Trust signal */}
        <p style={{
          marginTop: '1.25rem',
          color: 'rgba(189, 202, 220, 0.85)',
          fontSize: '0.78rem',
          letterSpacing: '0.03em',
        }}>
          Free &nbsp;·&nbsp; No account required &nbsp;·&nbsp; Results in seconds
        </p>
      </div>
    </div>
  );
}

export default LandingPage;
