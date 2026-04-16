import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../services/api';
import { Users as UsersIcon, Shield, ShieldCheck, Mail } from 'lucide-react';
import './Pages.css';

export default function UsersPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadUsers();
  }, []);

  async function loadUsers() {
    try { const data = await api.getUsers(); setUsers(data); } catch {} finally { setLoading(false); }
  }

  return (
    <div>
      <div className="page-header">
        <div><h1 className="page-title">User Management</h1><p className="page-subtitle">Manage users and roles</p></div>
      </div>

      <div className="table-container card">
        <table className="data-table">
          <thead>
            <tr><th>User</th><th>Email</th><th>Role</th><th>Status</th><th>Joined</th></tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>
                  <div className="user-cell">
                    <div className="user-avatar-sm">{u.full_name?.[0] || 'U'}</div>
                    <span>{u.full_name}</span>
                  </div>
                </td>
                <td><span className="cell-email"><Mail size={12} /> {u.email}</span></td>
                <td>{u.is_superuser ? <span className="badge badge-brand"><ShieldCheck size={10} /> Admin</span> : <span className="badge badge-info"><Shield size={10} /> Member</span>}</td>
                <td>{u.is_active ? <span className="badge badge-success">Active</span> : <span className="badge badge-error">Inactive</span>}</td>
                <td className="cell-date">{u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
              </tr>
            ))}
            {users.length === 0 && !loading && <tr><td colSpan={5} className="empty-cell">No users found (admin access required)</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
