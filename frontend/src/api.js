const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export async function summarizeRetrofit(dto) {
  const response = await fetch(`${API_BASE_URL}/summarize-retrofit/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(dto),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Request failed with status ${response.status}`);
  }

  return response.json();
}

export async function lookupProperty(address) {
  const response = await fetch(`${API_BASE_URL}/property-lookup`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ address }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Request failed with status ${response.status}`);
  }

  return response.json();
}

export async function generatePlan(address, answers) {
  const response = await fetch(`${API_BASE_URL}/generate-plan`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ address, answers }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Request failed with status ${response.status}`);
  }

  return response.json();
}

export async function sequenceRetrofit(rankedOptions, focus) {
  const response = await fetch(`${API_BASE_URL}/sequence-retrofit/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ranked_options: rankedOptions, focus }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Request failed with status ${response.status}`);
  }

  return response.json();
}

export async function fetchSolarActionSteps(address, solarData, matchedIncentives) {
  const response = await fetch(`${API_BASE_URL}/solar-action-steps`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      address,
      solar_data: solarData,
      matched_incentives: matchedIncentives,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Request failed with status ${response.status}`);
  }

  return response.json();
}

export async function fetchActionSteps(upgradeKey, address, coordinates, propertyProfile, matchedIncentives, option) {
  const response = await fetch(`${API_BASE_URL}/action-steps`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      upgrade_key: upgradeKey,
      address,
      coordinates,
      property_profile: propertyProfile,
      matched_incentives: matchedIncentives,
      gross_cost: option?.gross_cost ?? 0,
      net_cost: option?.net_cost ?? 0,
      annual_savings: option?.annual_savings ?? 0,
      payback_years: option?.payback_years ?? null,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Request failed with status ${response.status}`);
  }

  return response.json();
}

export async function getGoogleMapsConfig() {
  const response = await fetch(`${API_BASE_URL}/config/google-maps`);

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Request failed with status ${response.status}`);
  }

  return response.json();
}
