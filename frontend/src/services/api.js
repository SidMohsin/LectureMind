/**
 * Central API client. All backend requests should go through this module
 * instead of scattering fetch() calls across components/pages.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(message, { status, data } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

async function request(path, { method = "GET", body, headers, isFormData = false, signal } = {}) {
  const url = `${API_BASE_URL}${path}`;

  const finalHeaders = { ...headers };
  if (!isFormData && body !== undefined) {
    finalHeaders["Content-Type"] = "application/json";
  }

  let response;
  try {
    response = await fetch(url, {
      method,
      headers: finalHeaders,
      body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
      signal,
    });
  } catch (networkError) {
    throw new ApiError("Unable to reach the server. Check your connection and try again.", {
      status: 0,
      data: { cause: networkError.message },
    });
  }

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => null);

  if (!response.ok) {
    const message =
      (payload && typeof payload === "object" && (payload.message || payload.detail)) ||
      `Request failed with status ${response.status}`;
    throw new ApiError(message, { status: response.status, data: payload });
  }

  return payload;
}

export const api = {
  get: (path, options) => request(path, { ...options, method: "GET" }),
  post: (path, body, options) => request(path, { ...options, method: "POST", body }),
  put: (path, body, options) => request(path, { ...options, method: "PUT", body }),
  patch: (path, body, options) => request(path, { ...options, method: "PATCH", body }),
  delete: (path, options) => request(path, { ...options, method: "DELETE" }),
  upload: (path, formData, options) =>
    request(path, { ...options, method: "POST", body: formData, isFormData: true }),
};

export { ApiError, API_BASE_URL };
