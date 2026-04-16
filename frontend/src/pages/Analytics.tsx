import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../services/api';
import { BarChart3, FileText, Database, TrendingUp } from 'lucide-react';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import './Pages.css';

const CHART_COLORS = ['#6366f1', '#8b5cf6', '#a78bfa', '#10b981', '#f59e0b', '#3b82f6', '#ef4444', '#ec4899'];

export default function AnalyticsPage() {
  const { workspace } = useAuth();
  const [documents, setDocuments] = useState<any[]>([]);
  const [feedbackStats, setFeedbackStats] = useState<any>(null);
  const [sources, setSources] = useState<any[]>([]);

  useEffect(() => {
    if (workspace) {
      api.getDocuments(workspace.id).then(setDocuments).catch(() => {});
      api.getFeedbackStats(workspace.id).then(setFeedbackStats).catch(() => {});
      api.getSources(workspace.id).then(setSources).catch(() => {});
    }
  }, [workspace]);

  const sourceDistribution = Object.entries(
    documents.reduce((acc: Record<string, number>, doc: any) => {
      acc[doc.source_type] = (acc[doc.source_type] || 0) + 1;
      return acc;
    }, {})
  ).map(([name, value]) => ({ name, value }));

  const totalChunks = documents.reduce((sum: number, d: any) => sum + (d.chunk_count || 0), 0);

  return (
    <div>
      <div className="page-header">
        <div><h1 className="page-title">Analytics</h1><p className="page-subtitle">Knowledge base insights and metrics</p></div>
      </div>

      <div className="stats-grid">
        <div className="stat-card card">
          <div className="stat-icon" style={{ background: 'var(--color-brand-glow)' }}><FileText size={20} color="var(--color-brand-secondary)" /></div>
          <div><div className="stat-value">{documents.length}</div><div className="stat-label">Documents</div></div>
        </div>
        <div className="stat-card card">
          <div className="stat-icon" style={{ background: 'var(--color-success-bg)' }}><Database size={20} color="var(--color-success)" /></div>
          <div><div className="stat-value">{totalChunks.toLocaleString()}</div><div className="stat-label">Chunks Indexed</div></div>
        </div>
        <div className="stat-card card">
          <div className="stat-icon" style={{ background: 'var(--color-info-bg)' }}><BarChart3 size={20} color="var(--color-info)" /></div>
          <div><div className="stat-value">{sources.length}</div><div className="stat-label">Data Sources</div></div>
        </div>
        <div className="stat-card card">
          <div className="stat-icon" style={{ background: 'var(--color-warning-bg)' }}><TrendingUp size={20} color="var(--color-warning)" /></div>
          <div><div className="stat-value">{feedbackStats?.helpful_percentage?.toFixed(0) || 0}%</div><div className="stat-label">Helpful Rate</div></div>
        </div>
      </div>

      <div className="charts-grid">
        <div className="card">
          <h3 className="card-title">Documents by Source Type</h3>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={sourceDistribution} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="value" nameKey="name" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                {sourceDistribution.map((_, i) => (<Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />))}
              </Pie>
              <Tooltip contentStyle={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', color: 'var(--color-text-primary)' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <h3 className="card-title">Feedback Overview</h3>
          {feedbackStats && (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={[
                { name: 'Helpful', value: feedbackStats.helpful, fill: '#10b981' },
                { name: 'Not Helpful', value: feedbackStats.not_helpful, fill: '#ef4444' },
                { name: 'Corrections', value: feedbackStats.with_corrections, fill: '#f59e0b' },
              ]}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="name" stroke="var(--color-text-muted)" fontSize={12} />
                <YAxis stroke="var(--color-text-muted)" fontSize={12} />
                <Tooltip contentStyle={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', color: 'var(--color-text-primary)' }} />
                <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                  {[0, 1, 2].map((i) => (<Cell key={i} fill={['#10b981', '#ef4444', '#f59e0b'][i]} />))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}
