import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../services/api';
import { Database, Plus, Trash2, RefreshCw, Globe, GitBranch, MessageSquare, FileText, Bug } from 'lucide-react';
import './Pages.css';

const SOURCE_ICONS: Record<string, any> = { GITHUB: GitBranch, SLACK: MessageSquare, JIRA: Bug, PDF: FileText, SQL_DATABASE: Database, CONFLUENCE: Globe };

export default function SourcesPage() {
  const { workspace } = useAuth();
  const [sources, setSources] = useState<any[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ name: '', source_type: 'PDF', connection_config: '{}' });
  const [loading, setLoading] = useState(true);

  useEffect(() => { if (workspace) loadSources(); }, [workspace]);

  async function loadSources() {
    setLoading(true);
    try { const data = await api.getSources(workspace!.id); setSources(data); } catch {} finally { setLoading(false); }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      let config = {};
      try { config = JSON.parse(form.connection_config); } catch {}
      await api.createSource(workspace!.id, { name: form.name, source_type: form.source_type, connection_config: config });
      setShowModal(false);
      setForm({ name: '', source_type: 'PDF', connection_config: '{}' });
      loadSources();
    } catch {}
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this data source?')) return;
    try { await api.deleteSource(id); loadSources(); } catch {}
  }

  async function handleSync(sourceId: string) {
    try {
      await api.triggerIngestion(workspace!.id, { data_source_id: sourceId });
      alert('Ingestion job queued!');
    } catch {}
  }

  return (
    <div>
      <div className="page-header">
        <div><h1 className="page-title">Data Sources</h1><p className="page-subtitle">Manage your connected enterprise data sources</p></div>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}><Plus size={16} /> Add Source</button>
      </div>

      <div className="grid-cards">
        {sources.map((src) => {
          const Icon = SOURCE_ICONS[src.source_type] || Database;
          return (
            <div key={src.id} className="card source-card animate-fade-in">
              <div className="source-card-header">
                <div className="source-icon-wrap"><Icon size={20} /></div>
                <div className="source-actions">
                  <button className="btn btn-ghost" onClick={() => handleSync(src.id)}><RefreshCw size={14} /></button>
                  <button className="btn btn-ghost" onClick={() => handleDelete(src.id)}><Trash2 size={14} /></button>
                </div>
              </div>
              <h3 className="source-name">{src.name}</h3>
              <span className="badge badge-brand">{src.source_type}</span>
              <div className="source-meta">
                <span>Sync: {src.sync_frequency_minutes ? `Every ${src.sync_frequency_minutes}m` : 'Manual'}</span>
                <span>{src.last_sync_at ? `Last: ${new Date(src.last_sync_at).toLocaleDateString()}` : 'Never synced'}</span>
              </div>
            </div>
          );
        })}
      </div>

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal animate-fade-in" onClick={(e) => e.stopPropagation()}>
            <h2 className="modal-title">Add Data Source</h2>
            <form onSubmit={handleCreate}>
              <div className="form-group"><label className="form-label">Name</label><input className="input-field" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></div>
              <div className="form-group"><label className="form-label">Type</label>
                <select className="input-field" value={form.source_type} onChange={(e) => setForm({ ...form, source_type: e.target.value })}>
                  {['PDF', 'DOCX', 'TXT', 'GITHUB', 'SQL_DATABASE', 'SLACK', 'CONFLUENCE', 'NOTION', 'JIRA'].map((t) => (<option key={t} value={t}>{t}</option>))}
                </select>
              </div>
              <div className="form-group"><label className="form-label">Connection Config (JSON)</label><textarea className="input-field" rows={4} value={form.connection_config} onChange={(e) => setForm({ ...form, connection_config: e.target.value })} /></div>
              <div className="modal-actions"><button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>Cancel</button><button type="submit" className="btn btn-primary">Create</button></div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
