const API_BASE = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : '');

export async function planTrip(payload) {
  const response = await fetch(`${API_BASE}/api/trips/plan`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    try {
      const data = await response.json();
      throw new Error(data.error || JSON.stringify(data));
    } catch (error) {
      if (error instanceof SyntaxError) throw new Error(`API returned HTTP ${response.status}`, { cause: error });
      throw error;
    }
  }

  return response.json();
}

export async function planFuelRoute(payload) {
  let response;
  try {
    response = await fetch(`${API_BASE}/api/fuel/route`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error('Cannot reach the ETTO API. Check the connection and try again.');
  }
  if (!response.ok) {
    let detail;
    try {
      const body = await response.json();
      detail = body.error || Object.entries(body).map(([key, value]) => `${key}: ${value}`).join('; ');
    } catch {
      detail = `API returned HTTP ${response.status}`;
    }
    throw new Error(detail || `API returned HTTP ${response.status}`);
  }
  return response.json();
}
