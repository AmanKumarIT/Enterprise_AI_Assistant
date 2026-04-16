import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../services/api';
import {
  Upload as UploadIcon,
  File,
  CheckCircle,
  XCircle,
  Loader,
} from 'lucide-react';
import './Pages.css';

export default function UploadPage() {
  const { workspace } = useAuth();

  const [sources, setSources] = useState<any[]>([]);
  const [selectedSource, setSelectedSource] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    console.log('Workspace changed:', workspace);

    if (workspace) {
      api.getSources(workspace.id)
        .then((data) => {
          console.log('Fetched Sources:', data);

          const fileSources = data.filter((s: any) =>
            ['PDF', 'DOCX', 'TXT'].includes(
              String(s.source_type).toUpperCase()
            )
          );

          console.log('Filtered File Sources:', fileSources);

          setSources(fileSources);

          if (fileSources.length > 0) {
            setSelectedSource(fileSources[0].id);
          } else {
            setSelectedSource('');
          }
        })
        .catch((err) => {
          console.error('Failed to fetch sources:', err);
          setResult({ error: 'Failed to load data sources.' });
        });
    } else {
      setSources([]);
      setSelectedSource('');
    }
  }, [workspace]);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    const dropped = Array.from(e.dataTransfer.files);

    console.log('Dropped Files:', dropped);

    setFiles((prev) => [...prev, ...dropped]);
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files) {
      const selected = Array.from(e.target.files);

      console.log('Selected Files:', selected);

      setFiles((prev) => [...prev, ...selected]);
    }
  }

  async function handleUpload() {
    console.log('UPLOAD BUTTON CLICKED');

    setResult(null);

    console.log({
      workspace,
      selectedSource,
      files,
      filesCount: files.length,
    });

    if (!workspace) {
      setResult({ error: 'No workspace selected' });
      return;
    }

    if (!selectedSource) {
      setResult({ error: 'No valid file data source selected' });
      return;
    }

    if (files.length === 0) {
      setResult({ error: 'No files selected' });
      return;
    }

    setUploading(true);

    try {
      console.log('Calling upload API...');

      const res = await api.uploadFiles(
        workspace.id,
        selectedSource,
        files
      );

      console.log('Upload Success Response:', res);

      setResult(res);
      setFiles([]);
    } catch (err: any) {
      console.error('File upload error details:', err);

      setResult({
        error:
          err.message ||
          'Upload failed. Please check backend connection.',
      });
    } finally {
      setUploading(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Upload Center</h1>
          <p className="page-subtitle">
            Upload documents for ingestion and indexing
          </p>
        </div>
      </div>

      <div
        className="card"
        style={{ marginBottom: 'var(--space-6)' }}
      >
        <div className="form-group">
          <label className="form-label">Target Data Source</label>

          <select
            className="input-field"
            value={selectedSource}
            onChange={(e) => setSelectedSource(e.target.value)}
          >
            {sources.length === 0 ? (
              <option value="">
                No PDF-compatible sources found
              </option>
            ) : (
              sources.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.source_type})
                </option>
              ))
            )}
          </select>
        </div>

        <div
          className="upload-zone"
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          onClick={() =>
            document.getElementById('file-input')?.click()
          }
        >
          <input
            id="file-input"
            type="file"
            multiple
            hidden
            accept=".pdf,.docx,.txt,.md"
            onChange={handleFileSelect}
          />

          <UploadIcon
            size={36}
            className="upload-icon"
          />

          <p className="upload-text">
            Drop files here or click to browse
          </p>

          <p className="upload-hint">
            Supports PDF, DOCX, TXT, Markdown
          </p>
        </div>
      </div>

      {files.length > 0 && (
        <div
          className="card"
          style={{ marginBottom: 'var(--space-6)' }}
        >
          <h3
            style={{
              marginBottom: 'var(--space-4)',
              fontSize: 'var(--text-sm)',
              fontWeight: 600,
            }}
          >
            Selected Files ({files.length})
          </h3>

          <div className="file-list">
            {files.map((f, i) => (
              <div key={i} className="file-item">
                <File size={14} />

                <span className="file-name">{f.name}</span>

                <span className="file-size">
                  {(f.size / 1024).toFixed(1)} KB
                </span>

                <button
                  className="btn btn-ghost"
                  onClick={() =>
                    setFiles(
                      files.filter((_, j) => j !== i)
                    )
                  }
                >
                  <XCircle size={14} />
                </button>
              </div>
            ))}
          </div>

          <button
            className="btn btn-primary"
            style={{
              marginTop: 'var(--space-4)',
              width: '100%',
            }}
            onClick={handleUpload}
            disabled={uploading}
          >
            {uploading ? (
              <>
                <Loader
                  size={16}
                  className="spin"
                />
                Uploading...
              </>
            ) : (
              <>
                <UploadIcon size={16} />
                Upload {files.length} file
                {files.length > 1 ? 's' : ''}
              </>
            )}
          </button>
        </div>
      )}

      {result && (
        <div
          className={`card ${result.error
            ? 'upload-error'
            : 'upload-success'
            }`}
        >
          {result.error ? (
            <>
              <XCircle size={20} />
              Error: {result.error}
            </>
          ) : (
            <>
              <CheckCircle size={20} />
              {result.files_received} files queued for
              ingestion (Job:{' '}
              {result.job_id?.slice(0, 8)}...)
            </>
          )}
        </div>
      )}
    </div>
  );
}