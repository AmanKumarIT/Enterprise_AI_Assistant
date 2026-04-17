const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
}

async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const token = localStorage.getItem('eka_token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...options.headers,
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: options.method || 'GET',
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  if (res.status === 401) {
    localStorage.removeItem('eka_token');
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(err.detail || `Error ${res.status}`);
  }

  return res.json();
}

export const api = {
  // Auth
  login: (email: string, password: string) => {
    const formData = new URLSearchParams();
    formData.append('username', email);
    formData.append('password', password);
    return fetch(`${API_BASE}/auth/login/access-token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData,
    }).then(async (res) => {
      if (!res.ok) throw new Error('Invalid credentials');
      return res.json();
    });
  },
  signup: (data: { email: string; password: string; full_name: string }) =>
    request('/auth/signup', { method: 'POST', body: data }),
  getMe: () => request<any>('/users/me'),

  // Workspaces
  getWorkspaces: () => request<any[]>('/workspaces/'),
  createWorkspace: (data: { name: string; description?: string }) =>
    request('/workspaces/', { method: 'POST', body: data }),

  // Sources
  getSources: (workspaceId: string) =>
    request<any[]>(`/sources/?workspace_id=${workspaceId}`),
  createSource: (workspaceId: string, data: any) =>
    request(`/sources/?workspace_id=${workspaceId}`, { method: 'POST', body: data }),
  deleteSource: (sourceId: string) =>
    request(`/sources/${sourceId}`, { method: 'DELETE' }),
  triggerIngestion: (workspaceId: string, data: any) =>
    request(`/sources/ingest?workspace_id=${workspaceId}`, { method: 'POST', body: data }),

  // Documents
  getDocuments: (workspaceId: string, sourceType?: string) => {
    let url = `/documents/?workspace_id=${workspaceId}`;
    if (sourceType) url += `&source_type=${sourceType}`;
    return request<any[]>(url);
  },
  deleteDocument: (docId: string) =>
    request(`/documents/${docId}`, { method: 'DELETE' }),

  // Ingestion Jobs
  getIngestionJobs: (workspaceId: string) =>
    request<any[]>(`/sources/jobs/${workspaceId}`),

  // Chat
  chat: (data: {
    query: string;
    workspace_id: string;
    use_agent?: boolean;
    source_type_filter?: string;
  }) => request<any>('/chat/query', { method: 'POST', body: data }),

  chatStream: (data: {
    query: string;
    workspace_id: string;
    source_type_filter?: string;
  }) => {
    const token = localStorage.getItem('eka_token');
    return fetch(`${API_BASE}/chat/query/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(data),
    }).then((res) => {
      if (!res.ok) throw new Error(`Stream request failed: ${res.statusText}`);
      return res;
    });
  },

  // Feedback
  submitFeedback: (workspaceId: string, data: any) =>
    request(`/feedback/?workspace_id=${workspaceId}`, { method: 'POST', body: data }),
  getFeedback: (workspaceId: string, rating?: string) => {
    let url = `/feedback/?workspace_id=${workspaceId}`;
    if (rating) url += `&rating=${rating}`;
    return request<any[]>(url);
  },
  getFeedbackStats: (workspaceId: string) =>
    request<any>(`/feedback/stats?workspace_id=${workspaceId}`),

  // Users
  getUsers: () => request<any[]>('/users/'),

  // Upload
  uploadFiles: (workspaceId: string, dataSourceId: string, files: File[]) => {
    const token = localStorage.getItem('eka_token');
    const formData = new FormData();
    formData.append('workspace_id', workspaceId);
    formData.append('data_source_id', dataSourceId);
    files.forEach((f) => formData.append('files', f));
    return fetch(`${API_BASE}/documents/upload`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    }).then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
        throw new Error(err.detail || `Upload failed: ${res.status}`);
      }
      return res.json();
    });
  },
};
