const API_BASE = import.meta.env.VITE_API_BASE_URL !== undefined ? import.meta.env.VITE_API_BASE_URL : 'http://localhost:8000';

export async function planTrip(payload) {
  const response = await fetch(`${API_BASE}/api/trips/plan`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    let errorMsg = 'An error occurred';
    try {
      const data = await response.json();
      errorMsg = data.error || JSON.stringify(data);
    } catch(e) {
      errorMsg = await response.text();
    }
    throw new Error(errorMsg);
  }

  return response.json();
}
