import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { api } from '../services/api';

interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_superuser: boolean;
}

interface Workspace {
  id: string;
  name: string;
  description?: string;
}

interface AuthContextType {
  user: User | null;
  workspace: Workspace | null;
  workspaces: Workspace[];
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => void;
  setWorkspace: (ws: Workspace) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [workspace, setWorkspaceState] = useState<Workspace | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [token, setToken] = useState<string | null>(localStorage.getItem('eka_token'));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (token) {
      loadUser();
    } else {
      setLoading(false);
    }
  }, [token]);

  async function loadUser() {
    try {
      const me = await api.getMe();
      setUser(me);
      
      let ws = await api.getWorkspaces();
      
      // Lazy Initialization: Create a workspace if none exists
      if (ws.length === 0) {
        try {
          await api.createWorkspace({ 
            name: 'Default Workspace', 
            description: 'My first personal workspace' 
          });
          ws = await api.getWorkspaces();
        } catch (err) {
          console.error('Failed to auto-create workspace:', err);
        }
      }
      
      setWorkspaces(ws);
      
      if (ws.length > 0 && !workspace) {
        const saved = localStorage.getItem('eka_workspace');
        const found = saved ? ws.find((w: Workspace) => w.id === saved) : null;
        setWorkspaceState(found || ws[0]);
      }
    } catch {
      localStorage.removeItem('eka_token');
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  async function login(email: string, password: string) {
    const res = await api.login(email, password);
    localStorage.setItem('eka_token', res.access_token);
    setToken(res.access_token);
  }

  async function signup(email: string, password: string, fullName: string) {
    await api.signup({ email, password, full_name: fullName });
    await login(email, password);
  }

  function logout() {
    localStorage.removeItem('eka_token');
    localStorage.removeItem('eka_workspace');
    setToken(null);
    setUser(null);
    setWorkspaceState(null);
    setWorkspaces([]);
  }

  function setWorkspace(ws: Workspace) {
    setWorkspaceState(ws);
    localStorage.setItem('eka_workspace', ws.id);
  }

  return (
    <AuthContext.Provider
      value={{ user, workspace, workspaces, token, loading, login, signup, logout, setWorkspace }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
