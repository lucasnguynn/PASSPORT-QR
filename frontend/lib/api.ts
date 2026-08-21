export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

export interface Product {
  id: string; sku: string; name: string; gem_type?: string; gem_color?: string;
  gem_color_hex?: string; gem_carat?: string | number; gem_origin?: string;
  gem_clarity?: string; silver_grade?: string;
}
export interface Certificate { id: string; cert_type: string; cert_number?: string; issuer: string; document_url?: string; }
export interface DesignStory { designer_name?: string; inspiration?: string; craft_process?: string; media_urls: string[]; }
export interface MaintenanceSchedule { id: string; scheduled_at: string; notes?: string; }
export interface PassportData {
  product: Product; certificates: Certificate[]; design_story?: DesignStory | null;
  maintenance_schedules: MaintenanceSchedule[]; has_qr?: boolean; qr_image_url?: string | null;
}
export type ReactionType = "love" | "sparkle" | "inspired";
export interface Story {
  id: string; author_id: string; product_id: string; title?: string | null; content: string;
  color_tag?: string | null; color_hex?: string | null; media_urls: string[];
  reaction_count: number; display_name?: string; product_name?: string;
}
export interface FeedPage { items: Story[]; page: number; limit: number; }
export interface StoryCreate { product_id: string; title?: string; content: string; color_tag?: string; color_hex?: string; media_urls?: string[]; visibility: "public" | "followers"; }
export interface ProblemDetails { type?: string; title: string; status: number; detail?: string; instance?: string; }

export class ApiError extends Error {
  constructor(public readonly problem: ProblemDetails) { super(problem.detail || problem.title); }
}

function accessToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem("keycloak_access_token");
}

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = typeof window === "undefined" ? null : sessionStorage.getItem("keycloak_refresh_token");
  if (!refreshToken) return null;
  const response = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) return null;
  const tokens = await response.json() as { access_token: string; refresh_token?: string };
  sessionStorage.setItem("keycloak_access_token", tokens.access_token);
  if (tokens.refresh_token) sessionStorage.setItem("keycloak_refresh_token", tokens.refresh_token);
  return tokens.access_token;
}

export async function apiFetch<T>(endpoint: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(options.headers);
  const token = accessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
  if (response.status === 401 && retry && typeof window !== "undefined") {
    const refreshed = await refreshAccessToken();
    if (refreshed) return apiFetch<T>(endpoint, options, false);
  }
  if (!response.ok) {
    let problem: ProblemDetails = { title: response.statusText || "Request failed", status: response.status };
    try { problem = { ...problem, ...await response.json() as Partial<ProblemDetails> }; } catch { /* Non-JSON upstream response. */ }
    throw new ApiError(problem);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const getPassport = (id: string): Promise<PassportData> => apiFetch(`/passport/${encodeURIComponent(id)}`);
export const verifyQR = (tokenUri: string, deviceFp: string): Promise<PassportData> =>
  apiFetch("/qr/verify", { method: "POST", body: JSON.stringify({ token_uri: tokenUri, device_fingerprint: deviceFp }) });
export const getFeed = (page: number): Promise<FeedPage> => apiFetch(`/social/feed?page=${page}`);
export const createStory = (data: StoryCreate): Promise<Story> => apiFetch("/social/stories", { method: "POST", body: JSON.stringify(data) });
export const reactToStory = (id: string, type: ReactionType): Promise<void> => apiFetch(`/social/stories/${id}/reactions`, { method: "POST", body: JSON.stringify({ reaction_type: type }) });
