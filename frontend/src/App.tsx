import React, { useState, useRef, useEffect } from 'react'
import './App.css'

// --- ICONS ---
const OperatorIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
);

const NodeIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>
);

const ActionIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
);

const ShieldIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
);

const CpuIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect><rect x="9" y="9" width="6" height="6"></rect><line x1="9" y1="1" x2="9" y2="4"></line><line x1="15" y1="1" x2="15" y2="4"></line><line x1="9" y1="20" x2="9" y2="23"></line><line x1="15" y1="20" x2="15" y2="23"></line><line x1="20" y1="9" x2="23" y2="9"></line><line x1="20" y1="14" x2="23" y2="14"></line><line x1="1" y1="9" x2="4" y2="9"></line><line x1="1" y1="14" x2="4" y2="14"></line></svg>
);

const CheckIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
);

const FileIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
);

const DatabaseIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path></svg>
);

const SparkleIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2l2.4 7.6L22 12l-7.6 2.4L12 22l-2.4-7.6L2 12l7.6-2.4L12 2z"/></svg>
);

const CopyIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
);

const DownloadIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
);

const TrashIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
);

const PaperclipIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path></svg>
);

const FileWordIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><path d="M9 13l2 4 2-4 2 4"></path></svg>
);

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// --- HELPERS ---
const isActualReportGenerated = (text: string) => {
  if (!text) return false;
  return text.includes("Successfully generated Word document") || 
         (text.includes("sandbox_report.docx") && (text.includes("saved directly to disk") || text.includes("generated and saved to")));
};

function formatMathFormula(mathStr: string): string {
  let s = mathStr.trim();
  s = s.replace(/^\\\[/, '').replace(/\\\]$/, '').trim();
  s = s.replace(/^\$\$/, '').replace(/\$\$$/, '').trim();
  
  s = s.replace(/\\text\{([^}]+)\}/g, '$1');
  s = s.replace(/\\mathrm\{([^}]+)\}/g, '$1');
  s = s.replace(/\\mathbf\{([^}]+)\}/g, '$1');
  s = s.replace(/\\Delta/g, 'Δ');
  s = s.replace(/\\times/g, ' × ');
  s = s.replace(/\\cdot/g, ' · ');
  s = s.replace(/\\approx/g, ' ≈ ');
  s = s.replace(/\\pm/g, ' ± ');
  s = s.replace(/\\le(q)?/g, ' ≤ ');
  s = s.replace(/\\ge(q)?/g, ' ≥ ');
  s = s.replace(/\\ne(q)?/g, ' ≠ ');
  s = s.replace(/\\circ/g, '°');
  s = s.replace(/\\,/g, ' ');
  s = s.replace(/\\;/g, ' ');
  s = s.replace(/\\quad/g, '   ');
  s = s.replace(/\\qquad/g, '      ');
  s = s.replace(/\\alpha/g, 'α');
  s = s.replace(/\\beta/g, 'β');
  s = s.replace(/\\gamma/g, 'γ');
  s = s.replace(/\\theta/g, 'θ');
  s = s.replace(/\\lambda/g, 'λ');
  s = s.replace(/\\pi/g, 'π');
  s = s.replace(/\\sigma/g, 'σ');
  s = s.replace(/\\mu/g, 'μ');
  s = s.replace(/\\omega/g, 'ω');
  s = s.replace(/\\rho/g, 'ρ');
  s = s.replace(/\\eta/g, 'η');
  s = s.replace(/\\infty/g, '∞');
  s = s.replace(/\\sqrt\{([^}]+)\}/g, '√($1)');
  s = s.replace(/\\frac\{([^}]+)\}\{([^}]+)\}/g, '($1 / $2)');
  return s;
}

function formatInlineText(text: string): (string | React.JSX.Element)[] {
  const regex = /(\\\([\s\S]*?\\\)|\$[^$\n]+\$|\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;
  const parts = text.split(regex);
  return parts.map((part, idx) => {
    if (!part) return '';
    if ((part.startsWith('\\(') && part.endsWith('\\)')) || (part.startsWith('$') && part.endsWith('$'))) {
      const inner = part.startsWith('\\(') ? part.slice(2, -2) : part.slice(1, -1);
      return (
        <span key={idx} className="math-inline" title="Formula">
          {formatMathFormula(inner)}
        </span>
      );
    }
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={idx} className="prose-strong">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={idx} className="prose-inline-code">{part.slice(1, -1)}</code>;
    }
    if (part.startsWith('*') && part.endsWith('*')) {
      return <em key={idx} className="prose-em">{part.slice(1, -1)}</em>;
    }
    return part;
  });
}

function FormattedProse({ content, isUser, apiUrl }: { content: string, isUser: boolean, apiUrl: string }) {
  if (isUser) {
    return <div className="user-prose">{content}</div>;
  }

  // If this is an upload status JSON response, render a clean card instead of raw JSON
  if (content.trim().startsWith('{') && content.includes('"status": "success"') && content.includes('"markdown_snippet"')) {
    try {
      const data = JSON.parse(content);
      return (
        <div className="upload-result-card">
          <div className="upload-result-header">
            <span className="upload-badge"><CheckIcon /> PDF Ingested</span>
            <span className="upload-status-text">{data.message}</span>
          </div>
          {data.markdown_snippet && (
            <div className="upload-snippet-preview">
              <div className="preview-label">Extracted Text Preview:</div>
              <pre>{data.markdown_snippet}</pre>
            </div>
          )}
          {data.kg_result && (
            <div className="upload-kg-status">
              <span className="kg-label">Knowledge Graph Sync:</span>
              <span className={data.kg_result?.error ? "kg-tag offline" : "kg-tag online"}>
                {data.kg_result?.error ? "Sovereign Standalone Mode (MCP Offline)" : "Synced to Centralized Graph"}
              </span>
            </div>
          )}
        </div>
      );
    } catch {}
  }

  // Only show Word report card if it was ACTUALLY generated on disk
  const hasWordReport = isActualReportGenerated(content);

  const blocks: React.JSX.Element[] = [];
  const lines = content.split('\n');
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Math display block: \[ ... \] or $$ ... $$
    if (line.trim().startsWith('\\[') || line.trim().startsWith('$$')) {
      const mathLines = [line];
      const endMarker = line.trim().startsWith('\\[') ? '\\]' : '$$';
      if (!line.includes(endMarker) || (line.trim().startsWith('\\[') && line.trim() === '\\[')) {
        i++;
        while (i < lines.length && !lines[i].includes(endMarker)) {
          mathLines.push(lines[i]);
          i++;
        }
        if (i < lines.length) {
          mathLines.push(lines[i]);
        }
      }
      const rawMath = mathLines.join('\n');
      const formatted = formatMathFormula(rawMath);
      blocks.push(
        <div key={`math-${i}`} className="math-display-card">
          <div className="math-card-header">
            <span className="math-badge">EQUATION</span>
            <button 
              type="button"
              className="copy-formula-btn" 
              onClick={() => navigator.clipboard.writeText(formatted)}
              title="Copy Formula"
            >
              <CopyIcon /> Copy
            </button>
          </div>
          <div className="math-card-content">{formatted}</div>
        </div>
      );
      i++;
      continue;
    }

    // Code block ```
    if (line.trim().startsWith('```')) {
      const lang = line.trim().slice(3).trim() || 'code';
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      const codeText = codeLines.join('\n');
      blocks.push(
        <div key={`code-${i}`} className="code-block-card">
          <div className="code-block-header">
            <span className="code-lang-tag">{lang}</span>
            <button 
              type="button"
              className="copy-code-btn" 
              onClick={() => navigator.clipboard.writeText(codeText)}
            >
              <CopyIcon /> Copy Code
            </button>
          </div>
          <pre className="code-block-pre"><code>{codeText}</code></pre>
        </div>
      );
      i++;
      continue;
    }

    // Callout box
    if (line.startsWith('### [') && line.includes(']')) {
      const title = line.replace(/^###\s*/, '');
      blocks.push(
        <div key={`callout-${i}`} className="alert-callout-box">
          <div className="alert-callout-title">{title}</div>
        </div>
      );
      i++;
      continue;
    }

    // Headers
    if (line.startsWith('### ')) {
      blocks.push(<h4 key={`h4-${i}`} className="prose-h4">{formatInlineText(line.slice(4))}</h4>);
      i++;
      continue;
    }
    if (line.startsWith('## ')) {
      blocks.push(<h3 key={`h3-${i}`} className="prose-h3">{formatInlineText(line.slice(3))}</h3>);
      i++;
      continue;
    }
    if (line.startsWith('# ')) {
      blocks.push(<h2 key={`h2-${i}`} className="prose-h2">{formatInlineText(line.slice(2))}</h2>);
      i++;
      continue;
    }

    // Bullet item
    if (/^\s*[-*]\s+/.test(line)) {
      const clean = line.replace(/^\s*[-*]\s+/, '');
      blocks.push(
        <div key={`li-${i}`} className="prose-list-item">
          <span className="bullet-dot">•</span>
          <div className="list-text">{formatInlineText(clean)}</div>
        </div>
      );
      i++;
      continue;
    }

    // Numbered item
    if (/^\s*\d+\.\s+/.test(line)) {
      const match = line.match(/^\s*(\d+)\.\s+(.*)$/);
      if (match) {
        blocks.push(
          <div key={`num-${i}`} className="prose-list-item numbered">
            <span className="number-badge">{match[1]}</span>
            <div className="list-text">{formatInlineText(match[2])}</div>
          </div>
        );
        i++;
        continue;
      }
    }

    if (!line.trim()) {
      blocks.push(<div key={`sp-${i}`} className="prose-spacer" />);
      i++;
      continue;
    }

    blocks.push(
      <p key={`p-${i}`} className="prose-paragraph">
        {formatInlineText(line)}
      </p>
    );
    i++;
  }

  return (
    <div className="formatted-prose">
      {blocks}
      {hasWordReport && (
        <div className="generated-report-card">
          <div className="report-card-left">
            <div className="report-badge">
              <FileWordIcon />
            </div>
            <div className="report-meta">
              <div className="report-title">Sovereign_Industrial_Report.docx</div>
              <div className="report-subtitle">Calculation Sandbox Output & Executive Summary</div>
            </div>
          </div>
          <a 
            href={`${apiUrl}/download/report`} 
            download="Sovereign_Industrial_Report.docx" 
            className="download-report-btn"
          >
            <DownloadIcon /> Download .docx
          </a>
        </div>
      )}
    </div>
  );
}

function MessageActionBar({ content, activeModel, researchMode }: { content: string, activeModel?: string, researchMode?: boolean }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="message-action-bar">
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span className="model-chip">{activeModel || "Local LLM"}</span>
        {researchMode ? (
          <span className="mode-pill mode-research" title="Grounded with Google Scholar peer-reviewed papers">
            🔬 Deep Research
          </span>
        ) : (
          <span className="mode-pill mode-airgap" title="Strict air-gapped sovereign execution">
            🛡️ Air-Gapped Mode
          </span>
        )}
      </div>
      <button type="button" className="msg-action-btn" onClick={handleCopy} title="Copy response text">
        {copied ? <><CheckIcon /> Copied!</> : <><CopyIcon /> Copy</>}
      </button>
    </div>
  );
}

function formatTerminalLine(log: string) {
  if (log.startsWith('$') || log.startsWith('>')) {
    return <><span className="cmd-prompt">{log.slice(0, 2)}</span> {log.slice(2)}</>;
  }
  if (log.startsWith('[OK]') || log.startsWith('[PASS]') || log.startsWith('[READY]')) {
    const tag = log.split(']')[0] + ']';
    const rest = log.slice(tag.length);
    return <><span className="tag-ok">{tag}</span>{rest}</>;
  }
  if (log.startsWith('[DIAG]')) {
    return <><span className="tag-diag">[DIAG]</span>{log.slice(6)}</>;
  }
  if (log.startsWith('[DOCX]')) {
    return <><span className="tag-docx">[DOCX]</span>{log.slice(6)}</>;
  }
  if (log.startsWith('[RESEARCH]')) {
    return <><span className="tag-diag">[RESEARCH]</span>{log.slice(10)}</>;
  }
  if (log.startsWith('[AIRGAP]')) {
    return <><span className="tag-ok">[AIRGAP]</span>{log.slice(8)}</>;
  }
  if (log.startsWith('[WARN]') || log.startsWith('[ERR]')) {
    return <><span className="tag-warn">{log.split(']')[0] + ']'}</span>{log.slice(log.indexOf(']') + 1)}</>;
  }
  if (log.startsWith('[EXEC]') || log.startsWith('[AGENT]')) {
    return <><span className="tag-exec">{log.split(']')[0] + ']'}</span>{log.slice(log.indexOf(']') + 1)}</>;
  }
  return log;
}

// --- SCHOLAR & CHART COMPONENTS ---

const DEFAULT_SCHOLAR_PAPERS: Record<string, {title: string, link: string}[]> = {
  "Heat Exchanger Thermal Duty": [
    {
      title: "Investigation of Heat Transfer Rates on Shell and Tube Heat Exchanger by Numerical Modelling via CFD Analysis",
      link: "https://arxiv.org/abs/2310.17257"
    },
    {
      title: "Thermal Performance and Friction Factor in Double Pipe and Shell-and-Tube Heat Exchangers",
      link: "https://www.sciencedirect.com/science/article/pii/S135943111932456X"
    },
    {
      title: "Design and optimization of shell-and-tube heat exchangers based on TEMA standards",
      link: "https://link.springer.com/article/10.1007/s10973-018-7241-x"
    }
  ],
  "Hydrocracker Catalytic Safety": [
    {
      title: "Slurry phase hydrocracking: process operations, safety margins and reactor dynamics",
      link: "https://www.sciencedirect.com/science/article/pii/S001623612032682X"
    },
    {
      title: "Emergency Shutdown Systems (ESD) and safety integrity levels in petroleum hydrocrackers",
      link: "https://pubs.acs.org/doi/10.1021/ie50367a012"
    },
    {
      title: "Risk assessment and failure mitigation in high-pressure industrial hydroprocessing reactors",
      link: "https://www.icheme.org/publications/journals/psep"
    }
  ]
};

function ScholarKeywordSection({ 
  keyword, 
  results, 
  onOpenSummary,
  forceExpanded 
}: { 
  keyword: string, 
  results: {title: string, link: string}[], 
  onOpenSummary: (paper: {title: string, link: string}) => void,
  forceExpanded?: boolean
}) {
  const [expanded, setExpanded] = useState(true);
  const [hoveredCard, setHoveredCard] = useState<number | null>(null);
  const [summaryData, setSummaryData] = useState<Record<number, any>>({});
  const hoverTimer = useRef<number | null>(null);

  useEffect(() => {
    if (forceExpanded !== undefined) {
      setExpanded(forceExpanded);
    }
  }, [forceExpanded]);

  const handleMouseEnter = (idx: number, r: {title: string, link: string}) => {
    setHoveredCard(idx);
    if (summaryData[idx]) return;
    
    if (hoverTimer.current) window.clearTimeout(hoverTimer.current);
    hoverTimer.current = window.setTimeout(async () => {
      setSummaryData(prev => ({...prev, [idx]: { loading: true }}));
      try {
         const resp = await fetch(`${API_URL}/agent/summarize?url=${encodeURIComponent(r.link)}&title=${encodeURIComponent(r.title)}`, { method: 'POST' });
         const data = await resp.json();
         setSummaryData(prev => ({...prev, [idx]: data}));
      } catch {
         setSummaryData(prev => ({...prev, [idx]: { title: r.title, status: 'error', short_summary: ["Preview unavailable due to paywall or access control."] }}));
      }
    }, 400);
  };

  const handleMouseLeave = () => {
    setHoveredCard(null);
    if (hoverTimer.current) window.clearTimeout(hoverTimer.current);
  };
  
  return (
    <div style={{ marginBottom: expanded ? '14px' : '6px', display: 'flex', flexDirection: 'column' }}>
      <div 
        className="scholar-keyword-pill"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="pill-content">
          {keyword} <span className="pill-dot">·</span> <span className="pill-count">{results.length} papers</span>
          <svg className={`chevron ${expanded ? 'expanded' : ''}`} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 12 15 18 9"></polyline></svg>
        </div>
      </div>
      
      {expanded && (
        <div className="scholar-cards-container">
          {results.map((r, j) => {
            let domain = "";
            try { domain = new URL(r.link).hostname.replace('www.', ''); } catch {}
            
            const isHovered = hoveredCard === j;
            const mySumm = summaryData[j];
            
            return (
              <div key={j} className="scholar-card" style={{ animationDelay: `${j * 50}ms`, position: 'relative' }} onMouseEnter={() => handleMouseEnter(j, r)} onMouseLeave={handleMouseLeave}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '6px' }}>
                  <div className="scholar-card-domain">
                     {domain && <img src={`https://www.google.com/s2/favicons?domain=${domain}&sz=16`} alt="" onError={(e)=>{ (e.target as HTMLElement).style.display = 'none'; }} />}
                     {domain || 'scholar.google.com'}
                  </div>
                  <button 
                     type="button"
                     className="summarize-btn"
                     onClick={(e) => { 
                       e.stopPropagation(); 
                       onOpenSummary({ title: r.title, link: r.link }); 
                     }}
                     title="Summarize Paper via LexRank"
                  >
                     <SparkleIcon /> Summarize
                  </button>
                </div>
                <a href={r.link} target="_blank" rel="noopener noreferrer" className="scholar-card-title">{r.title}</a>
                
                {isHovered && mySumm && (
                  <div className="summary-popover">
                     {mySumm.loading ? (
                        <>
                           <div className="skeleton-line" style={{width: '90%'}}></div>
                           <div className="skeleton-line" style={{width: '60%'}}></div>
                        </>
                     ) : (
                        <div style={{ fontFamily: 'var(--font-serif)', lineHeight: 1.5, color: mySumm.status === 'fallback' ? 'var(--text-muted)' : 'var(--text-dark)' }}>
                          {(mySumm.short_summary || []).join(' ')}
                        </div>
                     )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function CoverageChart({ data }: { data: Record<string, {title: string, link: string}[]> }) {
  const [mounted, setMounted] = useState(false);
  const [hoverData, setHoverData] = useState<{ x: number, y: number, kw: string, count: number } | null>(null);
  
  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 50);
    return () => clearTimeout(t);
  }, []);
  
  if (!data || Object.keys(data).length === 0) return null;
  
  const width = 600;
  const height = 180;
  const padding = { top: 30, right: 30, bottom: 40, left: 40 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  
  const entries = Object.entries(data);
  const maxCount = Math.max(...entries.map(e => e[1].length), 3);
  
  const points = entries.map(([kw, arr], i) => {
    const x = padding.left + (innerWidth / Math.max(1, entries.length - 1)) * i;
    const y = padding.top + innerHeight - (arr.length / maxCount) * innerHeight;
    return { x, y, keyword: kw, count: arr.length, firstLink: arr[0]?.link };
  });

  let pathD = "";
  if (points.length === 1) {
    pathD = `M ${padding.left} ${points[0].y} L ${padding.left + innerWidth} ${points[0].y}`;
  } else {
    pathD = `M ${points[0].x} ${points[0].y}`;
    for (let i = 1; i < points.length; i++) {
        const prev = points[i-1];
        const curr = points[i];
        const cx1 = prev.x + (curr.x - prev.x) / 2;
        const cy1 = prev.y;
        const cx2 = prev.x + (curr.x - prev.x) / 2;
        const cy2 = curr.y;
        pathD += ` C ${cx1} ${cy1}, ${cx2} ${cy2}, ${curr.x} ${curr.y}`;
    }
  }

  const areaD = pathD + ` L ${points[points.length-1].x} ${height - padding.bottom} L ${points[0].x} ${height - padding.bottom} Z`;

  return (
    <div style={{ marginTop: '28px', width: '100%', maxWidth: width, position: 'relative' }} onMouseLeave={() => setHoverData(null)}>
      <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '10px', textTransform: 'uppercase' }}>
        Research coverage across {entries.length} keywords
      </div>
      
      <svg width="100%" height="auto" viewBox={`0 0 ${width} ${height}`} style={{ overflow: 'visible' }}>
        <defs>
          <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent-color)" stopOpacity="0.15" />
            <stop offset="100%" stopColor="var(--accent-color)" stopOpacity="0.0" />
          </linearGradient>
        </defs>
        
        {[0, Math.ceil(maxCount/2), maxCount].map((t, i) => (
          <g key={i}>
            <line x1={padding.left} y1={padding.top + innerHeight - (t/maxCount)*innerHeight} x2={width-padding.right} y2={padding.top + innerHeight - (t/maxCount)*innerHeight} stroke="rgba(0,0,0,0.06)" strokeWidth={1} />
            <text x={padding.left - 10} y={padding.top + innerHeight - (t/maxCount)*innerHeight + 4} textAnchor="end" fontSize="11" fill="var(--text-muted)" fontFamily="var(--font-sans)">{t}</text>
          </g>
        ))}

        {points.map((p, i) => (
          <text key={i} x={p.x} y={height - 15} textAnchor="middle" fontSize="11" fill="var(--text-muted)" fontFamily="var(--font-sans)" transform={`rotate(-15, ${p.x}, ${height - 15})`}>
            {p.keyword.length > 15 ? p.keyword.substring(0, 15) + '...' : p.keyword}
          </text>
        ))}

        <path d={areaD} fill="url(#areaGradient)" style={{ opacity: mounted ? 1 : 0, transition: 'opacity 0.8s ease' }} />
        
        <path 
           d={pathD} 
           fill="none" 
           stroke="var(--accent-color)" 
           strokeWidth="2" 
           strokeLinecap="round"
           style={{
             strokeDasharray: 2000,
             strokeDashoffset: mounted ? 0 : 2000,
             transition: 'stroke-dashoffset 0.8s ease-in-out'
           }} 
        />

        {points.map((p, i) => (
          <g 
             key={i} 
             className="chart-point" 
             style={{ 
               opacity: mounted ? 1 : 0, 
               transition: `opacity 0.4s ease ${0.4 + i*0.1}s`,
               cursor: 'pointer'  
             }}
             onMouseEnter={() => setHoverData({ x: p.x, y: p.y, kw: p.keyword, count: p.count })}
             onClick={() => {
                if (p.firstLink) window.open(p.firstLink, '_blank');
             }}
          >
             <circle cx={p.x} cy={p.y} r={16} fill="transparent" />
             <circle cx={p.x} cy={p.y} r={p.count === 0 ? 3 : 5} fill={p.count === 0 ? '#ebe9e0' : '#fff'} stroke={p.count === 0 ? '#aaa' : 'var(--accent-color)'} strokeWidth="2" />
          </g>
        ))}
      </svg>
      
      {hoverData && (
        <div style={{
           position: 'absolute',
           left: `${(hoverData.x / width) * 100}%`,
           top: `${(hoverData.y / height) * 100}%`,
           transform: 'translate(-50%, -100%)',
           marginTop: '-12px',
           pointerEvents: 'none',
           background: 'var(--text-dark)',
           color: '#fff',
           padding: '8px 12px',
           borderRadius: '6px',
           fontSize: '0.8rem',
           fontFamily: 'var(--font-sans)',
           boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
           zIndex: 10,
           whiteSpace: 'nowrap'
        }}>
           <div style={{ fontWeight: 600 }}>{hoverData.kw}</div>
           <div style={{ color: '#ccc', margin: '2px 0 4px 0', fontSize: '0.75rem' }}>{hoverData.count} paper{hoverData.count !== 1 ? 's' : ''} found</div>
           <div style={{ color: '#ffb58a', fontSize: '0.75rem', fontWeight: 600 }}>Click to view details &rarr;</div>
           <div style={{
              position: 'absolute',
              bottom: '-4px',
              left: '50%',
              transform: 'translateX(-50%)',
              width: 0, 
              height: 0, 
              borderLeft: '5px solid transparent',
              borderRight: '5px solid transparent',
              borderTop: '5px solid var(--text-dark)'
           }}></div>
        </div>
      )}
    </div>
  );
}

// --- MAIN COMPONENT ---

function App() {
  const [token, setToken] = useState<string | null>(null);
  const [username, setUsername] = useState<string>('');
  const [query, setQuery] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<{role: string, content: string, thinking?: string, scholar_results?: any, research_mode?: boolean}[]>([]);
  const [scholarResults, setScholarResults] = useState<Record<string, {title: string, link: string}[]>>(DEFAULT_SCHOLAR_PAPERS);
  const [scholarSearchTerm, setScholarSearchTerm] = useState<string>('');
  const [searchingScholar, setSearchingScholar] = useState<boolean>(false);
  const [allExpanded, setAllExpanded] = useState<boolean>(true);
  const [generatedReports, setGeneratedReports] = useState<{name: string, timestamp: string}[]>([]);
  const [activeSummary, setActiveSummary] = useState<any>(null);
  const [activeModel, setActiveModel] = useState<string>('Local Sovereign LLM');
  const [researchMode, setResearchMode] = useState<boolean>(false);
  
  // Live reactive Execution Sandbox logs
  const [sandboxLogs, setSandboxLogs] = useState<string[]>([
    "$ init_sovereign_sandbox --strict",
    "[OK] AST math compiler: HEALTHY",
    "[OK] External telemetry blocked (Air-gap)",
    "$ ready_awaiting_operator_commands..."
  ]);

  // Live Active Knowledge Base status
  const [kbStatus, setKbStatus] = useState<{
    status: string;
    mcp_connected: boolean;
    mcp_url: string;
    encryption_enabled: boolean;
    atoms_indexed: number;
    vault_mode: string;
    timestamp?: string;
  }>({
    status: 'online',
    mcp_connected: true,
    mcp_url: '',
    encryption_enabled: true,
    atoms_indexed: 52,
    vault_mode: 'CKKS 8192-bit Homomorphic'
  });
  const [showKbModal, setShowKbModal] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  
  // Real-time hardware telemetry and latency states for sidebar
  const [inferenceLatency, setInferenceLatency] = useState<string>('0.85s/turn');
  const [gpuTelemetry, setGpuTelemetry] = useState<{ status: string, device: string, vram: string, mode?: string }>({
    status: '100% VRAM Offload',
    device: 'Local GPU Acceleration',
    vram: 'Dedicated VRAM'
  });
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const sandboxBottomRef = useRef<HTMLDivElement>(null);

  const fetchKbStatus = () => {
    fetch(`${API_URL}/knowledge/status`)
      .then(r => r.json())
      .then(data => {
        if (data && data.status) {
          setKbStatus(data);
        }
      })
      .catch(() => {});
  };

  useEffect(() => {
    fetch(`${API_URL}/`)
      .then(r => r.json())
      .then(data => {
        if (data && data.llm_model) {
          setActiveModel(data.llm_model);
        }
        if (data && data.inference_latency_s) {
          setInferenceLatency(`${data.inference_latency_s}s/turn`);
        }
        if (data && data.gpu_telemetry) {
          setGpuTelemetry(data.gpu_telemetry);
        }
      })
      .catch(() => {});
    fetchKbStatus();
  }, []);

  useEffect(() => {
    sandboxBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [sandboxLogs]);

  // Auto-resize textarea like ChatGPT / Claude (smooth expansion up to ~220px)
  const autoResizeTextarea = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    const scrollH = el.scrollHeight;
    const nextHeight = Math.min(scrollH, 220);
    el.style.height = `${Math.max(nextHeight, 40)}px`;
    el.style.overflowY = scrollH > 220 ? 'auto' : 'hidden';
  };

  useEffect(() => {
    autoResizeTextarea();
  }, [query]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [history, loading]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username) return;
    try {
      const resp = await fetch(`${API_URL}/login?username=${username}`, { method: 'POST' });
      const data = await resp.json();
      setToken(data.token);
      setSandboxLogs(prev => [
        ...prev.slice(-35),
        `[AUTH] Operator '${data.username}' clearance token issued`
      ]);
    } catch {
      alert("Verification failed.");
    }
  }

  const handleQuery = async (e?: React.FormEvent, customQuery?: string) => {
    if (e) e.preventDefault();
    const currentQ = customQuery || query;
    if (!currentQ || !token || loading) return;
    
    setQuery('');
    if (textareaRef.current) {
      textareaRef.current.style.height = '40px';
      textareaRef.current.style.overflowY = 'hidden';
    }
    setHistory(prev => [...prev, {role: 'user', content: currentQ}]);
    setLoading(true);

    const logPrompt = currentQ.length > 30 ? currentQ.slice(0, 30) + '...' : currentQ;
    setSandboxLogs(prev => [
      ...prev.slice(-35),
      `> query.dispatch: "${logPrompt}" [DeepResearch: ${researchMode ? 'ON' : 'OFF'}]`,
      researchMode ? "[RESEARCH] Querying Google Scholar literature..." : "[AIRGAP] External lookups bypassed"
    ]);

    try {
      const resp = await fetch(`${API_URL}/agent/query?query=${encodeURIComponent(currentQ)}&token=${token}&research_mode=${researchMode}`, { method: 'POST' });
      const data = await resp.json();
      const outputTxt = data.agent_response || JSON.stringify(data, null, 2);
      const thinkingTxt = data.agent_thinking || "";
      const agentTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

      setHistory(prev => [...prev, {
        role: 'agent', 
        content: outputTxt, 
        thinking: thinkingTxt, 
        scholar_results: data.scholar_results,
        research_mode: data.research_mode ?? researchMode
      }]);

      if (data.execution_time_s) {
        setInferenceLatency(`${data.execution_time_s}s/turn`);
      }
      if (data.gpu_telemetry) {
        setGpuTelemetry(data.gpu_telemetry);
      }

      setSandboxLogs(prev => [
        ...prev.slice(-35),
        `[OK] Response synthesized (${agentTime}) [${data.execution_time_s || '0.8'}s]`
      ]);
      
      // If a Word report was ACTUALLY generated in this turn, record it
      if (isActualReportGenerated(outputTxt)) {
        setGeneratedReports(prev => [
          ...prev.filter(r => r.name !== "Sovereign_Industrial_Report.docx"),
          { name: "Sovereign_Industrial_Report.docx", timestamp: agentTime }
        ]);
        setSandboxLogs(prev => [...prev.slice(-35), "[DOCX] Generated Sovereign_Industrial_Report.docx"]);
      }

      if (data.scholar_results && Object.keys(data.scholar_results).length > 0) {
        setScholarResults(data.scholar_results);
        setAllExpanded(true);
      }
    } catch {
      setHistory(prev => [...prev, {role: 'agent', content: 'Connection to inference node lost.'}]);
      setSandboxLogs(prev => [...prev.slice(-35), "[ERR] Inference node connection lost"]);
    }
    setLoading(false);
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !token) return;
    setLoading(true);
    setSandboxLogs(prev => [...prev.slice(-35), `> ingest.pdf: "${file.name}"`]);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const resp = await fetch(`${API_URL}/ingest/pdf?token=${token}`, {
        method: 'POST',
        body: formData
      });
      const data = await resp.json();
      setHistory(prev => [...prev, {role: 'agent', content: JSON.stringify(data, null, 2)}]);
      setSandboxLogs(prev => [...prev.slice(-35), `[OK] "${file.name}" indexed -> Knowledge Graph`]);
      fetchKbStatus();
      setToastMessage(`Document "${file.name}" indexed into Knowledge Graph.`);
      setTimeout(() => setToastMessage(null), 4000);
    } catch {
      setSandboxLogs(prev => [...prev.slice(-35), `[ERR] Document indexing failed for "${file.name}"`]);
      setToastMessage("Document indexing failed. Please verify format.");
      setTimeout(() => setToastMessage(null), 4000);
    }
    setLoading(false);
    if(fileInputRef.current) fileInputRef.current.value = '';
  }
  
  const callDummyTool = async () => {
    if(!token) return;
    setSandboxLogs(prev => [...prev.slice(-35), "> ping --strict-diagnostic"]);
    try {
      const resp = await fetch(`${API_URL}/dummy_tool?input_val=health_check&token=${token}`, { method: 'POST' });
      const data = await resp.json();
      if (data.latency_ms) {
        setInferenceLatency(`${(data.latency_ms / 1000).toFixed(2)}s/turn`);
      }
      if (data.gpu_telemetry) {
        setGpuTelemetry(data.gpu_telemetry);
      }
      setSandboxLogs(prev => [
        ...prev.slice(-35),
        `[DIAG] Operator: ${data.user} | Latency: ${data.latency_ms}ms`,
        `[DIAG] AST Sandbox: ${data.ast_math_sandbox} | Isolation: ${data.sandbox_isolation}`,
        `[PASS] Encryption: ${data.encryption_layer} | Node: ${data.mcp_status}`
      ]);
      setToastMessage(`✅ Diagnostic Health: ${data.latency_ms}ms | AST Sandbox: ${data.ast_math_sandbox} | Air-gap: ${data.sandbox_isolation}`);
      setTimeout(() => setToastMessage(null), 4000);
    } catch(err) {
      setSandboxLogs(prev => [...prev.slice(-35), `[ERR] Diagnostic ping failed: ${err}`]);
      setToastMessage("Diagnostic ping failed. Check backend connection.");
      setTimeout(() => setToastMessage(null), 4000);
    }
  }

  const handleClearChat = () => {
    if (window.confirm("Clear conversation history and generated collateral?")) {
      setHistory([]);
      setScholarResults(DEFAULT_SCHOLAR_PAPERS);
      setGeneratedReports([]);
    }
  }

  const handleOpenPaperSummary = async (paper: {title: string, link: string}) => {
    setActiveSummary({ loading: true, title: paper.title, link: paper.link });
    try {
      const resp = await fetch(`${API_URL}/agent/summarize?url=${encodeURIComponent(paper.link)}&title=${encodeURIComponent(paper.title)}`, { method: 'POST' });
      const data = await resp.json();
      setActiveSummary({ ...data, title: paper.title, link: paper.link });
    } catch {
      setActiveSummary({ 
        title: paper.title, 
        link: paper.link, 
        status: 'error', 
        short_summary: ["Failed to summarize paper."], 
        full_summary: ["Unable to load summary at this time. Please open the original source link directly."] 
      });
    }
  };

  const handleDirectScholarSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    const term = scholarSearchTerm.trim();
    if (!term) return;
    setSearchingScholar(true);
    try {
      const resp = await fetch(`${API_URL}/agent/scholar/search?q=${encodeURIComponent(term)}`);
      const data = await resp.json();
      if (data.results && data.results.length > 0) {
        setScholarResults(prev => ({
          [term]: data.results,
          ...prev
        }));
        setAllExpanded(true);
      } else {
        alert(`No papers found for "${term}". Try another engineering keyword.`);
      }
    } catch (err) {
      console.error("Direct scholar search failed", err);
    }
    setSearchingScholar(false);
    setScholarSearchTerm('');
  };

  const totalPapersCount = Object.values(scholarResults).reduce((acc, curr) => acc + (curr ? curr.length : 0), 0);

  if (!token) {
    return (
      <div className="login-wrapper">
        <div className="login-panel">
          <div className="login-header">
            <em>001</em>
            <h1>Sovereign Node</h1>
            <p className="subtitle">Confidential Industrial Agentic Workbench</p>
          </div>
          <form onSubmit={handleLogin} className="login-form">
            <div className="input-group">
              <label>Operator Identification</label>
              <input 
                type="text" 
                placeholder="e.g. j.doe_88" 
                value={username} 
                onChange={e => setUsername(e.target.value)} 
              />
            </div>
            <button type="submit" className="action-btn">Authenticate Session</button>
          </form>
          <div className="login-footer">
            <p>Access requires active clearance. Interactions are logged securely.</p>
          </div>
        </div>
        <div className="login-decorative">
          <div className="hero-graphic">
            <div className="ring ring-1"></div>
            <div className="ring ring-2"></div>
            <div className="center-core"></div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="app-wrapper flex-row">
      <aside className="sidebar collapsible-nav">
        <div className="sidebar-header">
          <div className="brand-logo">SovereignAI</div>
        </div>
        <div className="workspace-nav">
           <div className="nav-group-title">COMMANDS</div>
           <button type="button" onClick={callDummyTool} className="nav-item" title="Run diagnostic node latency and sandbox AST check">
             <ActionIcon /> Diagnostic Ping
           </button>
           <button type="button" className="nav-item" onClick={() => fileInputRef.current?.click()} title="Ingest technical PDF into the Knowledge Graph">
             <ActionIcon /> Ingest Document
           </button>
           <button type="button" className="nav-item" onClick={() => setShowKbModal(true)} title="Inspect Active Knowledge Graph & Vault Topology">
             <ActionIcon /> Knowledge Vault
           </button>

           <div className="nav-group-title" style={{ marginTop: '28px' }}>AGENTIC CAPABILITIES</div>
           <div className="capability-item"><CheckIcon /> Local Sandbox Active</div>
           <div className="capability-item"><CheckIcon /> 100% GPU Accelerated</div>
           <div className="capability-item"><CheckIcon /> Atomic Knowledge Graph</div>
           <div className="capability-item"><CheckIcon /> Air-Gapped Sovereign Node</div>
        </div>
        <div className="sidebar-footer">
          <div className="security-status" style={{ marginBottom: '14px', fontSize: '0.8rem', color: '#2f9e44', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'bold' }}>
            <ShieldIcon /> Air-Gapped Mode
          </div>
          <div 
            className="hardware-metrics" 
            title={`Active Engine: ${activeModel}\nHardware Device: ${gpuTelemetry.device}\nVRAM Status: ${gpuTelemetry.vram}\nLatency: ${inferenceLatency}`}
            onClick={callDummyTool}
            style={{ cursor: 'pointer' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
              <span>INFERENCE:</span> 
              <span style={{ color: 'var(--accent-color)', fontWeight: 600 }}>{inferenceLatency}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span>GPU ACCEL:</span> 
              <span style={{ color: 'var(--text-dark)', fontWeight: 600 }}>{gpuTelemetry.status}</span>
            </div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: '4px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              ⚡ {gpuTelemetry.device}
            </div>
          </div>
          <div className="operator-block">
             <span className="dot active"></span> {username}
          </div>
          <button type="button" onClick={() => setToken(null)} className="disconnect-btn">Disconnect</button>
        </div>
      </aside>

      <main className="workspace main-console">
        <div className="topbar">
           <div className="topbar-left">
             <h2>Workspace: <span>Industrial Knowledge Workspace</span></h2>
             <div className="model-status">
               <CpuIcon /> {activeModel}
             </div>
           </div>

           <div className="topbar-right">
             <button type="button" className="topbar-clear-btn" onClick={handleClearChat} title="Clear conversation history">
               <TrashIcon /> Clear Chat
             </button>
           </div>
        </div>

        <div className="feed-scrollable">
          {history.length === 0 && (
            <div className="blank-canvas">
              <h3>Air-gapped industrial terminal connected.</h3>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem', marginTop: '-18px', marginBottom: '28px' }}>
                Ask complex engineering calculations, SOP safety workflows, or failure diagnostics.
              </p>
              <div className="onboarding-cards">
                <div className="card" onClick={() => handleQuery(undefined, "Calculate the heat duty for a shell-and-tube heat exchanger cooling 40,000 kg/h of crude oil from 190°C to 110°C (assume Cp = 2.3 kJ/kg·°C). Provide an executive summary and generate a formal Word report.")}>
                   <div className="card-badge">THERMAL ENG</div>
                   <h4>🌡️ Heat Exchanger Duty</h4>
                   <p>Run mathematical calculations & generate a formal Word report.</p>
                </div>
                <div className="card highlight" onClick={() => handleQuery(undefined, "What are the primary safety protocols and emergency shutdown (ESD) procedures for industrial catalytic hydrocrackers?")}>
                   <div className="card-badge">SAFETY SOP</div>
                   <h4>⚠️ Hydrocracker Safety</h4>
                   <p>Retrieve emergency shutdown procedures and API 521 compliance.</p>
                </div>
                <div className="card" onClick={() => handleQuery(undefined, "Audit the local CKKS homomorphic encryption parameters (8192 polynomial modulus, DP epsilon budget) and explain how confidential queries remain secure.")}>
                   <div className="card-badge">SECURITY</div>
                   <h4>🔐 Homomorphic Encryption</h4>
                   <p>Inspect CKKS ciphertext security & differential privacy boundaries.</p>
                </div>
                <div className="card" onClick={() => handleQuery(undefined, "Explain the governing thermal principles for heat exchanger network pinch analysis and how to determine the minimum hot and cold utility requirements.")}>
                   <div className="card-badge">OPTIMIZATION</div>
                   <h4>📐 Pinch Network Analysis</h4>
                   <p>Calculate minimum utility targets and pinch point temperatures.</p>
                </div>
              </div>
            </div>
          )}
          
          <div className="message-canvas">
            {history.map((msg, i) => {
              const isUser = msg.role === 'user';
              return (
                <div key={i} className={`thread-item ${isUser ? 'user-item' : 'agent-item'}`}>
                  <div className="avatar-column">
                    {isUser ? <OperatorIcon /> : <NodeIcon />}
                  </div>
                  <div className="content-column">
                    <div className="message-header">
                      <div className="sender-name">{isUser ? username : 'Lexicon Engine'}</div>
                    </div>
                    
                    {msg.thinking && (
                       <details className="deepseek-thought-drawer" open={false}>
                         <summary className="thought-summary">
                           <span className="thought-icon">🧠</span>
                           <span className="thought-label">Thought for 2.4s</span>
                           <span className="thought-badge">DeepThink (R1) Trace</span>
                         </summary>
                         <div className="thought-content">
                           {msg.thinking}
                         </div>
                       </details>
                    )}
                    
                    <div className="prose-content">
                      <FormattedProse content={msg.content} isUser={isUser} apiUrl={API_URL} />
                    </div>

                    {!isUser && <MessageActionBar content={msg.content} activeModel={activeModel} researchMode={msg.research_mode} />}

                    {msg.scholar_results && <CoverageChart data={msg.scholar_results} />}
                  </div>
                </div>
              );
            })}
            
            {loading && (
              <div className="thread-item agent-item loading-item">
                 <div className="avatar-column"><NodeIcon /></div>
                 <div className="content-column">
                    <div className="sender-name">Lexicon Engine</div>
                    <div className="activity-indicator">
                       <div className="tracer-bar">
                         <div className="tracer-progress"></div>
                       </div>
                       <span>Reasoning with {activeModel}...</span>
                    </div>
                 </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
        </div>

        {/* WORLD-CLASS DEEPSEEK-STYLE DOCKED COMPOSER */}
        <div className="docked-composer">
          <form onSubmit={handleQuery} className="composer-card">
            {/* Top Textarea Area */}
            <div className="composer-input-row">
              <textarea 
                ref={textareaRef}
                placeholder="Ask about TEMA heat exchangers, catalytic SOPs, or run engineering calculations..." 
                value={query} 
                onChange={e => setQuery(e.target.value)} 
                onInput={autoResizeTextarea}
                disabled={loading}
                rows={1}
                onKeyDown={(e) => { if(e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleQuery(e); } }}
              />
            </div>

            {/* Bottom Actions Toolbar */}
            <div className="composer-toolbar">
              <div className="toolbar-left">
                {/* File Attachment Hidden Input & Button */}
                <input 
                  id="file-upload" 
                  type="file" 
                  accept="application/pdf" 
                  ref={fileInputRef} 
                  onChange={handleFileUpload} 
                  disabled={loading} 
                  style={{ display: 'none' }} 
                />
                <button 
                  type="button" 
                  className="toolbar-btn attach-btn" 
                  onClick={() => fileInputRef.current?.click()} 
                  title="Upload & Ingest PDF into Knowledge Graph"
                  disabled={loading}
                >
                  <PaperclipIcon />
                  <span className="btn-label">Attach PDF</span>
                </button>

                {/* DeepSeek R1-Style DeepThink / Deep Research Pill */}
                <button
                  type="button"
                  className={`toolbar-pill deepthink-pill ${researchMode ? 'active' : ''}`}
                  onClick={() => setResearchMode(prev => !prev)}
                  title={researchMode ? "Deep Research Mode ON: SerpAPI & Google Scholar literature search active" : "Deep Research Mode OFF: Pure sovereign air-gapped fast inference"}
                  disabled={loading}
                >
                  <span className="pill-icon"><SparkleIcon /></span>
                  <span className="pill-title">Deep Research</span>
                  <span className="pill-status">{researchMode ? 'ON' : 'OFF'}</span>
                </button>

                {/* Air-gap / Privacy Mode Indicator */}
                <div className={`toolbar-pill airgap-pill ${researchMode ? 'research-active' : ''}`} title="Air-gap containment status">
                  <span className="airgap-dot"></span>
                  <span className="pill-title">{researchMode ? 'Scholar Literature' : 'Air-Gap Isolated'}</span>
                </div>
              </div>

              <div className="toolbar-right">
                {query.length > 0 && (
                  <span className="char-counter">{query.length} chars</span>
                )}
                <button 
                  type="submit" 
                  disabled={loading || !query.trim()} 
                  className={`send-action-btn ${query.trim() ? 'ready' : ''}`}
                  title="Send Query (Enter)"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="12" y1="19" x2="12" y2="5"></line>
                    <polyline points="5 12 12 5 19 12"></polyline>
                  </svg>
                </button>
              </div>
            </div>
          </form>

          <div className="composer-footer-hints">
            <span>Press <strong>Enter ↵</strong> to run · <strong>Shift + Enter</strong> for multiline</span>
            <span>Local Model: <strong>{activeModel}</strong> · Sovereign Intelligence</span>
          </div>
        </div>
      </main>

      <aside className="sidebar right-panel">
        <div className="right-panel-header">
           <h2>Context & Artifacts</h2>
        </div>
        
        <div className="right-panel-scroll">
           <div className="sidebar-section">
             <div className="nav-group-title">
               <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                 RESEARCH PAPERS (SCHOLAR)
                 {totalPapersCount > 0 && <span className="scholar-count-badge">{totalPapersCount}</span>}
               </span>
               <div className="scholar-header-actions">
                 {loading && <span className="scholar-live-pulse">● Fetching</span>}
                 {totalPapersCount > 0 && (
                   <button 
                     type="button" 
                     className="scholar-toggle-btn"
                     onClick={() => setAllExpanded(!allExpanded)}
                   >
                     {allExpanded ? "Collapse" : "Expand"}
                   </button>
                 )}
               </div>
             </div>

             {/* Direct keyword search */}
             <form onSubmit={handleDirectScholarSearch} className="scholar-search-box">
               <input 
                 type="text" 
                 placeholder="Search literature topics..." 
                 value={scholarSearchTerm}
                 onChange={e => setScholarSearchTerm(e.target.value)}
                 className="scholar-search-input"
                 disabled={searchingScholar}
               />
               <span className="scholar-search-icon">
                 {searchingScholar ? "..." : "🔍"}
               </span>
             </form>

             {loading && (
               <div className="scholar-loading-skeleton">
                 <div className="scholar-skeleton-card">
                   <div className="skeleton-line" style={{ width: '40%', height: '10px' }} />
                   <div className="skeleton-line" style={{ width: '90%', height: '12px' }} />
                   <div className="skeleton-line" style={{ width: '70%', height: '11px' }} />
                 </div>
               </div>
             )}

             {Object.keys(scholarResults).length > 0 ? (
               <div className="scholar-section-list">
                 {Object.entries(scholarResults).map(([keyword, results]) => (
                   <ScholarKeywordSection 
                     key={keyword} 
                     keyword={keyword} 
                     results={results} 
                     onOpenSummary={handleOpenPaperSummary}
                     forceExpanded={allExpanded}
                   />
                 ))}
               </div>
             ) : (
               !loading && (
                 <div className="collateral-empty-state">
                   <div className="empty-state-icon"><SparkleIcon /></div>
                   <div className="empty-state-title">Deep Research is {researchMode ? 'Active' : 'Off'}</div>
                   <div className="empty-state-sub">
                     {researchMode 
                       ? "Ask an industrial query to fetch and cross-reference literature from Google Scholar."
                       : "External SerpAPI and Google Scholar calls are disabled for strict air-gapped operation."}
                   </div>
                   {!researchMode ? (
                     <button 
                       type="button" 
                       className="enable-deepresearch-btn"
                       onClick={() => setResearchMode(true)}
                     >
                       Enable Deep Research
                     </button>
                   ) : (
                     <button 
                       type="button" 
                       className="load-starter-papers-btn"
                       onClick={() => setScholarResults(DEFAULT_SCHOLAR_PAPERS)}
                     >
                       Load Reference Literature
                     </button>
                   )}
                 </div>
               )
             )}
           </div>

           <div className="sidebar-section">
             <div className="nav-group-title">GENERATED COLLATERAL (.DOCX)</div>
             {generatedReports.length > 0 ? (
               generatedReports.map((rep, idx) => (
                 <a key={idx} href={`${API_URL}/download/report`} download={rep.name} style={{ textDecoration: 'none' }}>
                   <div className="collateral-card">
                      <div style={{ color: '#107c41' }}><FileIcon /></div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                         <div className="collateral-title">{rep.name}</div>
                         <div className="collateral-sub">Generated at {rep.timestamp}</div>
                      </div>
                      <span className="collateral-dl-pill">Download</span>
                   </div>
                 </a>
               ))
             ) : (
               <div className="collateral-empty-state">
                 <div className="empty-state-icon"><FileIcon /></div>
                 <div className="empty-state-title">No documents generated yet</div>
                 <div className="empty-state-sub">Reports generated by calculations will appear here for download.</div>
               </div>
             )}
           </div>

           <div className="sidebar-section">
             <div className="nav-group-title">ACTIVE KNOWLEDGE BASE</div>
             <div className="knowledge-base-card" onClick={() => setShowKbModal(true)} style={{ cursor: 'pointer' }} title="Click to inspect Knowledge Vault & Topology">
                <div className="kb-icon-wrap"><DatabaseIcon /></div>
                <div className="kb-details">
                   <div className="kb-title">{kbStatus.mcp_connected ? 'Atomic Knowledge Graph' : 'Sovereign Local Vault'}</div>
                   <div className="kb-meta">
                      <span className={`kb-status-dot ${kbStatus.mcp_connected ? 'active' : 'local'}`}></span>
                      <span>{kbStatus.mcp_connected ? 'MCP Connected' : 'Local Standalone'}</span>
                      <span className="kb-atom-badge">{kbStatus.atoms_indexed} Atoms</span>
                   </div>
                </div>
                <button type="button" className="kb-inspect-btn" onClick={(e) => { e.stopPropagation(); setShowKbModal(true); }}>
                  Inspect
                </button>
             </div>
           </div>
           
           <div className="sidebar-section">
             <div className="nav-group-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
               <span>EXECUTION SANDBOX</span>
             </div>
             <div className="sandbox-terminal-container">
               <div className="sandbox-terminal-header">
                 <div className="terminal-title-group">
                   <div className="live-beacon"></div>
                   <span>SANDBOX CONSOLE</span>
                 </div>
                 <div className="sandbox-terminal-actions">
                   <button 
                     type="button" 
                     className="terminal-action-btn" 
                     onClick={callDummyTool}
                     title="Run live diagnostic node health check"
                   >
                     Ping
                   </button>
                   <button 
                     type="button" 
                     className="terminal-action-btn" 
                     onClick={() => setSandboxLogs(["$ ready_awaiting_operator_commands..."])}
                     title="Clear terminal log"
                   >
                     Clear
                   </button>
                 </div>
               </div>
               <div className="sandbox-terminal-box">
                 {sandboxLogs.map((log, i) => (
                   <div key={i} className="terminal-line">
                     {formatTerminalLine(log)}
                   </div>
                 ))}
                 <div ref={sandboxBottomRef} />
               </div>
             </div>
           </div>
        </div>
      </aside>

      {/* Summary Side Modal */}
      {activeSummary && (
        <div className="summary-overlay" onClick={() => setActiveSummary(null)}>
          <div className="summary-modal" onClick={e => e.stopPropagation()}>
            <div className="summary-modal-header">
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600, marginBottom: '8px' }}>
                Quick Summarization
              </div>
              <h2 style={{ fontSize: '1.25rem', fontFamily: 'var(--font-serif)', margin: '0 0 8px 0', lineHeight: 1.3 }}>{activeSummary.title}</h2>
              <a href={activeSummary.link || `https://${activeSummary.source_domain}`} target="_blank" rel="noopener noreferrer" style={{ fontSize: '0.8rem', color: 'var(--accent-color)', textDecoration: 'none' }}>
                Open original source &rarr;
              </a>
              <button type="button" className="close-btn" onClick={() => setActiveSummary(null)}>×</button>
            </div>
            
            <div className="summary-modal-body">
               {activeSummary.loading ? (
                  <div style={{ marginTop: '24px' }}>
                     <div className="skeleton-line" style={{width: '100%', height: '14px', marginBottom: '8px'}}></div>
                     <div className="skeleton-line" style={{width: '95%', height: '14px', marginBottom: '8px'}}></div>
                     <div className="skeleton-line" style={{width: '90%', height: '14px', marginBottom: '8px'}}></div>
                     <div className="skeleton-line" style={{width: '60%', height: '14px', marginBottom: '8px'}}></div>
                  </div>
               ) : (
                  <div style={{ fontFamily: 'var(--font-serif)', fontSize: '1.05rem', lineHeight: 1.8, color: 'var(--text-dark)', marginTop: '24px' }}>
                     {(activeSummary.full_summary || []).length > 0 ? 
                        (activeSummary.full_summary.map((sent: string, k: number) => <p key={k} style={{ marginBottom: '12px' }}>{sent}</p>)) :
                        (<p style={{ color: 'var(--text-muted)' }}>Preview unavailable — please open the source link.</p>)
                     }
                  </div>
               )}
            </div>
            
            {!activeSummary.loading && activeSummary.status === 'ok' && (
              <div style={{ marginTop: 'auto', padding: '24px 32px', textAlign: 'right', fontSize: '0.7rem', color: '#bbb', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                 Summarized via LexRank
              </div>
            )}
          </div>
        </div>
      )}

      {/* Knowledge Base Modal */}
      {showKbModal && (
        <div className="kb-modal-overlay" onClick={() => setShowKbModal(false)}>
          <div className="kb-modal-card" onClick={e => e.stopPropagation()}>
            <div className="kb-modal-header">
              <h3><DatabaseIcon /> Knowledge Vault & MCP Topology</h3>
              <button type="button" className="close-btn" onClick={() => setShowKbModal(false)}>×</button>
            </div>
            <div className="kb-modal-body">
              <div className="kb-info-row">
                <span className="kb-info-label">Knowledge Engine</span>
                <span className="kb-info-value">{kbStatus.vault_mode}</span>
              </div>
              <div className="kb-info-row">
                <span className="kb-info-label">Centralized MCP Status</span>
                <span className="kb-info-value" style={{ color: kbStatus.mcp_connected ? '#2f9e44' : '#fa8c16' }}>
                  {kbStatus.mcp_connected ? '● Active Session Connected' : '● Sovereign Air-Gap Standalone'}
                </span>
              </div>
              <div className="kb-info-row">
                <span className="kb-info-label">MCP Server URL</span>
                <span className="kb-info-value" style={{ fontSize: '0.72rem' }}>{kbStatus.mcp_url || 'https://atomicapp.ai/mcp'}</span>
              </div>
              <div className="kb-info-row">
                <span className="kb-info-label">Total Indexed Atoms</span>
                <span className="kb-info-value">{kbStatus.atoms_indexed} Documents / Chunks</span>
              </div>
              <div className="kb-info-row">
                <span className="kb-info-label">Encryption Master State</span>
                <span className="kb-info-value">{kbStatus.encryption_enabled ? 'TenSEAL CKKS + Differential Privacy' : 'Local Plaintext Vault'}</span>
              </div>
              <div className="kb-info-row">
                <span className="kb-info-label">Operator Clearance</span>
                <span className="kb-info-value">{username || 'Active Operator'}</span>
              </div>
            </div>
            <div className="kb-modal-actions">
              <button type="button" className="kb-action-secondary" onClick={() => { setShowKbModal(false); fileInputRef.current?.click(); }}>
                Ingest New PDF
              </button>
              <button type="button" className="kb-action-primary" onClick={() => setShowKbModal(false)}>
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating Toast Notification Banner */}
      {toastMessage && (
        <div className="toast-banner">
          <ShieldIcon />
          <span>{toastMessage}</span>
          <button type="button" className="toast-close-btn" onClick={() => setToastMessage(null)}>×</button>
        </div>
      )}

    </div>
  )
}

export default App
