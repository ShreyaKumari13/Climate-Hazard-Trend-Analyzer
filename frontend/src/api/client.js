const BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";

async function handle(res) {
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function getRegions() {
  return handle(await fetch(`${BASE_URL}/api/regions`));
}

export function buildQueryString(params) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") q.append(k, v);
  });
  return q.toString();
}

export async function analyze(params) {
  const qs = buildQueryString(params);
  return handle(await fetch(`${BASE_URL}/api/analyze?${qs}`));
}

export function exportUrl(params, format) {
  const qs = buildQueryString({ ...params, format });
  return `${BASE_URL}/api/export?${qs}`;
}

export { BASE_URL };
