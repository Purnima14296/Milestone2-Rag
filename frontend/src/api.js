const API_BASE = import.meta.env.VITE_API_BASE || "";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const detail =
      (payload && (payload.detail || payload.message)) ||
      "Something went wrong. Please try again.";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  return payload;
}

export function fetchConfig() {
  return request("/config");
}

export function fetchSchemes() {
  return request("/schemes");
}

export function fetchHealth() {
  return request("/health");
}

export function postChat(message, selectedScheme) {
  const body = { message };
  if (selectedScheme) {
    body.selected_scheme = selectedScheme;
  }
  return request("/chat", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
