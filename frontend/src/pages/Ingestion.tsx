import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../services/api';
import { Activity, CheckCircle, XCircle, Clock, Loader, AlertTriangle } from 'lucide-react';
import './Pages.css';

const STATUS_CONFIG: Record<string, { icon: any; badge: string }> = {
  COMPLETED: { icon: CheckCircle, badge: 'badge-success' },
  FAILED: { icon: XCircle, badge: 'badge-error' },
  IN_PROGRESS: { icon: Loader, badge: 'badge-warning' },
  PENDING: { icon: Clock, badge: 'badge-info' },
  PARTIAL: { icon: AlertTriangle, badge: 'badge-warning' },
};

export default function IngestionPage() {
  const { workspace } = useAuth();
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { if (workspace) loadJobs(); }, [workspace]);
  useEffect(() => {
    const interval = setInterval(() => { if (workspace) loadJobs(); }, 10000);
    return () => clearInterval(interval);
  }, [workspace]);

  async function loadJobs() {
    try { const data = await api.getIngestionJobs(workspace!.id); setJobs(data); } catch {} finally { setLoading(false); }
  }

  return (
    <div>
      <div className="page-header">
        <div><h1 className="page-title">Ingestion Status</h1><p className="page-subtitle">Monitor data ingestion jobs</p></div>
        <button className="btn btn-secondary" onClick={loadJobs}><Activity size={14} /> Refresh</button>
      </div>

      <div className="table-container card">
        <table className="data-table">
          <thead>
            <tr><th>Status</th><th>Data Source</th><th>Progress</th><th>Errors</th><th>Started</th><th>Completed</th></tr>
          </thead>
          <tbody>
            {jobs.map((job) => {
              const cfg = STATUS_CONFIG[job.status] || STATUS_CONFIG.PENDING;
              const Icon = cfg.icon;
              const progress = job.total_documents > 0 ? Math.round((job.processed_documents / job.total_documents) * 100) : 0;
              return (
                <tr key={job.id}>
                  <td><span className={`badge ${cfg.badge}`}><Icon size={10} /> {job.status}</span></td>
                  <td className="cell-id">{job.data_source_id?.slice(0, 8)}...</td>
                  <td>
                    <div className="progress-bar-container">
                      <div className="progress-bar" style={{ width: `${progress}%` }} />
                    </div>
                    <span className="progress-text">{job.processed_documents}/{job.total_documents}</span>
                  </td>
                  <td>{job.failed_documents > 0 ? <span style={{ color: 'var(--color-error)' }}>{job.failed_documents}</span> : '—'}</td>
                  <td className="cell-date">{job.started_at ? new Date(job.started_at).toLocaleString() : '—'}</td>
                  <td className="cell-date">{job.completed_at ? new Date(job.completed_at).toLocaleString() : '—'}</td>
                </tr>
              );
            })}
            {jobs.length === 0 && <tr><td colSpan={6} className="empty-cell">No ingestion jobs yet</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
