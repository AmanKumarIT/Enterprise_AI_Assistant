import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import {
  MessageSquare, Database, Upload, Activity, Users, BarChart3,
  ThumbsUp, LogOut, ChevronDown, Sparkles,
} from 'lucide-react';
import './Layout.css';

const navItems = [
  { to: '/chat', icon: MessageSquare, label: 'Chat' },
  { to: '/sources', icon: Database, label: 'Sources' },
  { to: '/upload', icon: Upload, label: 'Upload' },
  { to: '/ingestion', icon: Activity, label: 'Ingestion' },
  { to: '/users', icon: Users, label: 'Users' },
  { to: '/analytics', icon: BarChart3, label: 'Analytics' },
  { to: '/feedback', icon: ThumbsUp, label: 'Feedback' },
];

export default function Layout() {
  const { user, workspace, workspaces, setWorkspace, logout } = useAuth();

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-icon"><Sparkles size={22} /></div>
          <span className="brand-text">EKA</span>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            >
              <item.icon size={18} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="workspace-selector">
            <label className="ws-label">Workspace</label>
            <select
              className="ws-select"
              value={workspace?.id || ''}
              disabled={workspaces.length === 0}
              onChange={(e) => {
                const ws = workspaces.find((w) => w.id === e.target.value);
                if (ws) setWorkspace(ws);
              }}
            >
              {workspaces.length === 0 ? (
                <option value="">No Workspaces</option>
              ) : (
                workspaces.map((ws) => (
                  <option key={ws.id} value={ws.id}>{ws.name}</option>
                ))
              )}
            </select>
          </div>

          <div className="user-card">
            <div className="user-avatar">{user?.full_name?.[0] || 'U'}</div>
            <div className="user-info">
              <div className="user-name">{user?.full_name}</div>
              <div className="user-email">{user?.email}</div>
            </div>
            <button className="logout-btn" onClick={logout} title="Logout">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
