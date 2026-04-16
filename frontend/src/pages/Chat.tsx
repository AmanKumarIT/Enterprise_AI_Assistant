import React, { useState, useRef, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../services/api';
import { Send, Bot, User, Sparkles, FileText, ExternalLink, Zap, Filter } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import './Chat.css';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  citations?: any[];
  confidence?: number;
  intent?: string;
  processing_time_ms?: number;
  loading?: boolean;
}

const SOURCE_FILTERS = [
  { value: '', label: 'All Sources' },
  { value: 'PDF', label: 'PDF' },
  { value: 'GITHUB', label: 'GitHub' },
  { value: 'SQL_DATABASE', label: 'SQL' },
  { value: 'SLACK', label: 'Slack' },
  { value: 'JIRA', label: 'Jira' },
  { value: 'CONFLUENCE', label: 'Confluence' },
];

export default function ChatPage() {
  const { workspace } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sourceFilter, setSourceFilter] = useState('');
  const [useAgent, setUseAgent] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function handleSend() {
    if (!input.trim() || !workspace || loading) return;
    const query = input.trim();
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: query }]);
    setLoading(true);

    setMessages((prev) => [...prev, { role: 'assistant', content: '', loading: true }]);

    try {
      if (useAgent) {
        const res = await api.chat({
          query,
          workspace_id: workspace.id,
          use_agent: true,
          source_type_filter: sourceFilter || undefined,
        });
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: 'assistant',
            content: res.answer,
            citations: res.citations,
            confidence: res.confidence_score,
            intent: res.query_intent,
            processing_time_ms: res.processing_time_ms,
          };
          return updated;
        });
      } else {
        const res = await api.chatStream({
          query,
          workspace_id: workspace.id,
          source_type_filter: sourceFilter || undefined,
        });

        const reader = res.body?.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        let citations: any[] = [];

        if (reader) {
          let buffer = '';
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
              const cleanLine = line.trim();
              if (!cleanLine.startsWith('data: ')) continue;
              
              try {
                const data = JSON.parse(cleanLine.slice(6));
                if (data.type === 'token') {
                  fullText += data.data;
                  setMessages((prev) => {
                    const updated = [...prev];
                    updated[updated.length - 1] = { role: 'assistant', content: fullText, loading: true };
                    return updated;
                  });
                } else if (data.type === 'done') {
                  citations = data.data?.citations || [];
                } else if (data.type === 'error') {
                  throw new Error(data.data);
                }
              } catch (e: any) {
                console.error('Error parsing stream line:', e);
              }
            }
          }
        }

        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: 'assistant', content: fullText, citations, loading: false };
          return updated;
        });
      }
    } catch (err: any) {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: 'assistant', content: `Error: ${err.message}`, loading: false };
        return updated;
      });
    } finally {
      setLoading(false);
    }
  }

  function getConfidenceColor(score: number) {
    if (score >= 0.7) return 'var(--color-success)';
    if (score >= 0.4) return 'var(--color-warning)';
    return 'var(--color-error)';
  }

  return (
    <div className="chat-page">
      <div className="chat-header">
        <div>
          <h1 className="page-title">Knowledge Assistant</h1>
          <p className="page-subtitle">Ask questions across your enterprise data</p>
        </div>
        <div className="chat-controls">
          <div className="filter-group">
            <Filter size={14} />
            <select className="ws-select" value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
              {SOURCE_FILTERS.map((f) => (<option key={f.value} value={f.value}>{f.label}</option>))}
            </select>
          </div>
          <button className={`btn ${useAgent ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setUseAgent(!useAgent)}>
            <Zap size={14} /> {useAgent ? 'Agent Mode' : 'RAG Mode'}
          </button>
        </div>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <div className="empty-icon"><Sparkles size={40} /></div>
            <h2>What would you like to know?</h2>
            <p>Ask about your documents, code, Slack discussions, Jira tickets, and more.</p>
            <div className="example-queries">
              {['Summarize our Q1 sales reports', 'Explain the auth flow in the backend repo', 'Show Jira bugs related to checkout failures', 'What did engineering discuss about database migration?'].map((q) => (
                <button key={q} className="example-btn" onClick={() => { setInput(q); }}>"{q}"</button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`message message-${msg.role} animate-fade-in`}>
            <div className="message-avatar">
              {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
            </div>
            <div className="message-content">
              {msg.loading && !msg.content ? (
                <div className="typing-indicator"><span /><span /><span /></div>
              ) : (
                <>
                  <div className="message-text"><ReactMarkdown>{msg.content}</ReactMarkdown></div>
                  {msg.confidence !== undefined && (
                    <div className="message-meta">
                      <span className="confidence-pill" style={{ color: getConfidenceColor(msg.confidence) }}>
                        Confidence: {(msg.confidence * 100).toFixed(0)}%
                      </span>
                      {msg.intent && <span className="badge badge-brand">{msg.intent}</span>}
                      {msg.processing_time_ms && <span className="meta-time">{msg.processing_time_ms.toFixed(0)}ms</span>}
                    </div>
                  )}
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="citations-panel">
                      <div className="citations-title"><FileText size={12} /> Sources ({msg.citations.length})</div>
                      {msg.citations.map((c: any, j: number) => (
                        <div key={j} className="citation-item">
                          <span className="citation-index">{c.source_index}</span>
                          <div className="citation-info">
                            <span className="citation-title">{c.document_title}</span>
                            <span className="badge badge-info">{c.source_type}</span>
                          </div>
                          {c.source_uri && (
                            <a href={c.source_uri} target="_blank" rel="noopener noreferrer" className="citation-link"><ExternalLink size={12} /></a>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-bar">
        <div className="chat-input-container">
          <input
            className="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder="Ask anything about your enterprise knowledge..."
            disabled={loading}
          />
          <button 
            className="btn btn-primary send-btn" 
            onClick={handleSend} 
            disabled={loading || !input.trim() || !workspace}
            title={!workspace ? "Please select or create a workspace first" : ""}
          >
            {loading ? <span className="spinner" /> : <Send size={18} />}
          </button>
        </div>
      </div>
    </div>
  );
}
