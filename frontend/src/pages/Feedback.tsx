import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../services/api';
import { ThumbsUp, ThumbsDown, MessageSquare, Filter } from 'lucide-react';
import './Pages.css';

export default function FeedbackPage() {
  const { workspace } = useAuth();
  const [feedback, setFeedback] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [ratingFilter, setRatingFilter] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => { if (workspace) loadData(); }, [workspace, ratingFilter]);

  async function loadData() {
    setLoading(true);
    try {
      const [fb, st] = await Promise.all([
        api.getFeedback(workspace!.id, ratingFilter || undefined),
        api.getFeedbackStats(workspace!.id),
      ]);
      setFeedback(fb);
      setStats(st);
    } catch {} finally { setLoading(false); }
  }

  return (
    <div>
      <div className="page-header">
        <div><h1 className="page-title">Feedback Review</h1><p className="page-subtitle">Review user feedback on AI answers</p></div>
        <div className="filter-group">
          <Filter size={14} />
          <select className="ws-select" value={ratingFilter} onChange={(e) => setRatingFilter(e.target.value)}>
            <option value="">All</option>
            <option value="HELPFUL">Helpful</option>
            <option value="NOT_HELPFUL">Not Helpful</option>
          </select>
        </div>
      </div>

      {stats && (
        <div className="stats-grid" style={{ marginBottom: 'var(--space-6)' }}>
          <div className="stat-card card"><div className="stat-icon" style={{ background: 'var(--color-brand-glow)' }}><MessageSquare size={20} color="var(--color-brand-secondary)" /></div><div><div className="stat-value">{stats.total}</div><div className="stat-label">Total Responses</div></div></div>
          <div className="stat-card card"><div className="stat-icon" style={{ background: 'var(--color-success-bg)' }}><ThumbsUp size={20} color="var(--color-success)" /></div><div><div className="stat-value">{stats.helpful}</div><div className="stat-label">Helpful</div></div></div>
          <div className="stat-card card"><div className="stat-icon" style={{ background: 'var(--color-error-bg)' }}><ThumbsDown size={20} color="var(--color-error)" /></div><div><div className="stat-value">{stats.not_helpful}</div><div className="stat-label">Not Helpful</div></div></div>
          <div className="stat-card card"><div className="stat-icon" style={{ background: 'var(--color-warning-bg)' }}><MessageSquare size={20} color="var(--color-warning)" /></div><div><div className="stat-value">{stats.with_corrections}</div><div className="stat-label">With Corrections</div></div></div>
        </div>
      )}

      <div className="feedback-list">
        {feedback.map((fb) => (
          <div key={fb.id} className="card feedback-card animate-fade-in">
            <div className="feedback-header">
              <span className={`badge ${fb.rating === 'HELPFUL' ? 'badge-success' : 'badge-error'}`}>
                {fb.rating === 'HELPFUL' ? <><ThumbsUp size={10} /> Helpful</> : <><ThumbsDown size={10} /> Not Helpful</>}
              </span>
              <span className="cell-date">{new Date(fb.created_at).toLocaleString()}</span>
            </div>
            <div className="feedback-query"><strong>Q:</strong> {fb.query}</div>
            <div className="feedback-answer"><strong>A:</strong> {fb.answer.slice(0, 200)}{fb.answer.length > 200 ? '...' : ''}</div>
            {fb.correction && <div className="feedback-correction"><strong>Correction:</strong> {fb.correction}</div>}
          </div>
        ))}
        {feedback.length === 0 && !loading && <div className="card" style={{ textAlign: 'center', color: 'var(--color-text-muted)', padding: 'var(--space-10)' }}>No feedback submitted yet</div>}
      </div>
    </div>
  );
}
