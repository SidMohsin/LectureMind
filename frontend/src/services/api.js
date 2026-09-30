/**
 * Central API client. All backend requests should go through this module
 * instead of scattering fetch() calls across components/pages.
 *
 * Requests are authenticated by default with the current Supabase access
 * token. Pass { auth: false } for public endpoints.
 */
import { supabase } from "../lib/supabase";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const SESSION_EXPIRED_MESSAGE = "Your session has expired. Please log in again.";

class ApiError extends Error {
  constructor(message, { status, data } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

async function accessToken({ refresh = false } = {}) {
  const { data } = refresh ? await supabase.auth.refreshSession() : await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

const NETWORK_ERROR_MESSAGE = "Unable to reach the server. Check your connection and try again.";

function headersFrom(raw) {
  const headers = new Headers();
  raw
    .trim()
    .split(/[\r\n]+/)
    .filter(Boolean)
    .forEach((line) => {
      const index = line.indexOf(":");
      headers.append(line.slice(0, index).trim(), line.slice(index + 1).trim());
    });
  return headers;
}

// fetch() can't report upload progress, so uploads that want it use XHR and
// are converted back into a standard Response.
function sendWithProgress(url, { method, body, headers, signal, onUploadProgress }) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);
    Object.entries(headers).forEach(([name, value]) => xhr.setRequestHeader(name, value));
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onUploadProgress({ loaded: event.loaded, total: event.total });
    };
    xhr.onload = () => {
      const empty = [204, 205, 304].includes(xhr.status);
      resolve(new Response(empty ? null : xhr.responseText, { status: xhr.status, headers: headersFrom(xhr.getAllResponseHeaders()) }));
    };
    xhr.onerror = () => reject(new ApiError(NETWORK_ERROR_MESSAGE, { status: 0 }));
    xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));
    if (signal) {
      if (signal.aborted) return xhr.abort();
      signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }
    xhr.send(body);
  });
}

async function send(url, { method, body, headers, isFormData, signal, token, onUploadProgress }) {
  const finalHeaders = { ...headers };
  if (!isFormData && body !== undefined) finalHeaders["Content-Type"] = "application/json";
  if (token) finalHeaders.Authorization = `Bearer ${token}`;

  if (onUploadProgress) {
    return sendWithProgress(url, { method, body, headers: finalHeaders, signal, onUploadProgress });
  }

  try {
    return await fetch(url, {
      method,
      headers: finalHeaders,
      body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
      signal,
    });
  } catch (networkError) {
    if (networkError.name === "AbortError") throw networkError;
    throw new ApiError(NETWORK_ERROR_MESSAGE, {
      status: 0,
      data: { cause: networkError.message },
    });
  }
}

async function parse(response) {
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => null);
}

async function request(
  path,
  { method = "GET", body, headers, isFormData = false, signal, auth = true, onUploadProgress } = {}
) {
  const url = `${API_BASE_URL}${path}`;
  const options = { method, body, headers, isFormData, signal, onUploadProgress };

  let response = await send(url, { ...options, token: auth ? await accessToken() : null });

  if (auth && response.status === 401) {
    // The stored token may have expired between refreshes; try once more with a fresh one.
    const refreshed = await accessToken({ refresh: true });
    if (refreshed) response = await send(url, { ...options, token: refreshed });

    if (response.status === 401) {
      // Clearing the local session lets the auth layer route the user back to login.
      await supabase.auth.signOut({ scope: "local" });
      throw new ApiError(SESSION_EXPIRED_MESSAGE, { status: 401, data: await parse(response) });
    }
  }

  const payload = await parse(response);

  if (!response.ok) {
    const message =
      response.status === 403
        ? "You don't have permission to do that."
        : (payload && typeof payload === "object" && payload.message) || `Request failed with status ${response.status}`;
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
