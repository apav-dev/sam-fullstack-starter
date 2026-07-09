// Typed fetch wrapper. Token lives in localStorage; every request after login
// carries an Authorization: Bearer header.

const TOKEN_KEY = 'myapp_token'

export type User = {
  user_id: string
  email: string
  name: string
  role: 'admin' | 'user'
  created_at: string
}

export type AuthResponse = { token: string; user: User }

export type JobStatus = 'queued' | 'running' | 'done' | 'error'

export type Job = {
  run_id: string
  status: JobStatus
  result?: { bytes: number; words: number; lines: number }
  error_msg?: string
}

export const getToken = (): string | null => localStorage.getItem(TOKEN_KEY)
export const setToken = (token: string): void => localStorage.setItem(TOKEN_KEY, token)
export const clearToken = (): void => localStorage.removeItem(TOKEN_KEY)

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    ...(init.body ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...((init.headers as Record<string, string>) ?? {}),
  }
  const res = await fetch(path, { ...init, headers })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body: unknown = await res.json()
      if (body && typeof body === 'object' && 'detail' in body) {
        detail = String((body as { detail: unknown }).detail)
      }
    } catch {
      // non-JSON error body — keep statusText
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

export const api = {
  signup: (email: string, password: string, name: string) =>
    request<AuthResponse>('/api/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ email, password, name }),
    }),

  login: (email: string, password: string) =>
    request<AuthResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<{ user: User }>('/api/auth/me'),

  presignUpload: (filename: string, contentType: string) =>
    request<{ upload_url: string; s3_key: string }>(
      `/api/uploads/presign?filename=${encodeURIComponent(filename)}&content_type=${encodeURIComponent(contentType)}`,
    ),

  // Direct PUT to S3 — no auth header (the presigned URL is the credential)
  uploadToS3: async (uploadUrl: string, file: File): Promise<void> => {
    const res = await fetch(uploadUrl, {
      method: 'PUT',
      body: file,
      headers: { 'Content-Type': file.type || 'application/octet-stream' },
    })
    if (!res.ok) throw new ApiError(res.status, 'S3 upload failed')
  },

  createJob: (s3Key: string) =>
    request<{ run_id: string; status: JobStatus }>('/api/jobs', {
      method: 'POST',
      body: JSON.stringify({ s3_key: s3Key }),
    }),

  getJob: (runId: string) => request<Job>(`/api/jobs/${runId}`),

  aiEcho: (prompt: string) =>
    request<{ model: string; reply: string }>('/api/ai/echo', {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    }),
}
