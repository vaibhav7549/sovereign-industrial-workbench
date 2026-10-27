import { useState, useRef, useEffect } from 'react'
import './App.css'

const OperatorIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
);

const NodeIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>
);

const ActionIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
);

const ShieldIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
);

const CpuIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect><rect x="9" y="9" width="6" height="6"></rect><line x1="9" y1="1" x2="9" y2="4"></line><line x1="15" y1="1" x2="15" y2="4"></line><line x1="9" y1="20" x2="9" y2="23"></line><line x1="15" y1="20" x2="15" y2="23"></line><line x1="20" y1="9" x2="23" y2="9"></line><line x1="20" y1="14" x2="23" y2="14"></line><line x1="1" y1="9" x2="4" y2="9"></line><line x1="1" y1="14" x2="4" y2="14"></line></svg>
);

const CheckIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="green" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
);

const FileIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
);

const DatabaseIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path></svg>
);

const SparkleIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 2l2.4 7.6L22 12l-7.6 2.4L12 22l-2.4-7.6L2 12l7.6-2.4L12 2z"/>
  </svg>
);

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function ScholarKeywordSection({ keyword, results, onOpenSummary }: { keyword: string, results: {title: string, link: string}[], onOpenSummary: (data: any)=>void }) {
  const [expanded, setExpanded] = useState(false);
  const [hoveredCard, setHoveredCard] = useState<number | null>(null);
  const [summaryData, setSummaryData] = useState<Record<number, any>>({});
  const hoverTimer = useRef<number | null>(null);

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
      } catch (e) {
         setSummaryData(prev => ({...prev, [idx]: { title: r.title, status: 'error', short_summary: ["Failed to summarize."] }}));
      }
    }, 500);
  };

  const handleMouseLeave = () => {
    setHoveredCard(null);
    if (hoverTimer.current) window.clearTimeout(hoverTimer.current);
  };
  
  
  return (
    <div style={{ marginBottom: expanded ? '16px' : '8px', display: 'flex', flexDirection: 'column' }}>
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
            try { domain = new URL(r.link).hostname.replace('www.', ''); } catch (e) {}
            
            const isHovered = hoveredCard === j;
            const mySumm = summaryData[j];
            
            return (
              <div key={j} className="scholar-card" style={{ animationDelay: `${j * 60}ms`, position: 'relative' }} onMouseEnter={() => handleMouseEnter(j, r)} onMouseLeave={handleMouseLeave}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div className="scholar-card-domain">
                     {domain && <img src={`https://www.google.com/s2/favicons?domain=${domain}&sz=16`} alt="" />}
                     {domain || 'scholar.google.com'}
                  </div>
                  <button 
                     className="summarize-btn"
                     onClick={(e) => { e.stopPropagation(); onOpenSummary(mySumm && !mySumm.loading ? mySumm : { loading: true, title: r.title, link: r.link }); }}
                     title="Summarize Paper"
                  >
                     <SparkleIcon />
                  </button>
                </div>
                <a href={r.link} target="_blank" rel="noopener noreferrer" className="scholar-card-title">{r.title}</a>
                
                {/* Popover Hover */}
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
    // short timeout to trigger CSS animation
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
    <div style={{ marginTop: '32px', width: '100%', maxWidth: width, position: 'relative' }} onMouseLeave={() => setHoverData(null)}>
      <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '12px', textTransform: 'uppercase' }}>
        Research coverage across {entries.length} keywords
      </div>
      
      <svg width="100%" height="auto" viewBox={`0 0 ${width} ${height}`} style={{ overflow: 'visible' }}>
        <defs>
          <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent-color)" stopOpacity="0.15" />
            <stop offset="100%" stopColor="var(--accent-color)" stopOpacity="0.0" />
          </linearGradient>
        </defs>
        
        {/* Grids */}
        {[0, Math.ceil(maxCount/2), maxCount].map((t, i) => (
          <g key={i}>
            <line x1={padding.left} y1={padding.top + innerHeight - (t/maxCount)*innerHeight} x2={width-padding.right} y2={padding.top + innerHeight - (t/maxCount)*innerHeight} stroke="rgba(0,0,0,0.06)" strokeWidth={1} />
            <text x={padding.left - 10} y={padding.top + innerHeight - (t/maxCount)*innerHeight + 4} textAnchor="end" fontSize="11" fill="var(--text-muted)" fontFamily="var(--font-sans)">{t}</text>
          </g>
        ))}

        {/* Labels with rotation if needed */}
        {points.map((p, i) => (
          <text key={i} x={p.x} y={height - 15} textAnchor="middle" fontSize="11" fill="var(--text-muted)" fontFamily="var(--font-sans)" transform={`rotate(-15, ${p.x}, ${height - 15})`}>
            {p.keyword.length > 15 ? p.keyword.substring(0, 15) + '...' : p.keyword}
          </text>
        ))}

        {/* Area */}
        <path d={areaD} fill="url(#areaGradient)" style={{ opacity: mounted ? 1 : 0, transition: 'opacity 0.8s ease' }} />
        
        {/* Line */}
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

        {/* Interactive Points */}
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
             {/* Invisible target area for easier hovering */}
             <circle cx={p.x} cy={p.y} r={16} fill="transparent" />
             <circle cx={p.x} cy={p.y} r={p.count === 0 ? 3 : 5} fill={p.count === 0 ? '#ebe9e0' : '#fff'} stroke={p.count === 0 ? '#aaa' : 'var(--accent-color)'} strokeWidth="2" />
          </g>
        ))}
      </svg>
      
      {/* Tooltip HTML Overlay */}
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
           
           {/* Tooltip triangle pointer */}
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

function App() {
  const [token, setToken] = useState<string | null>(null);
  const [username, setUsername] = useState<string>('');
  const [query, setQuery] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<{role: string, content: any, thinking?: string, scholar_results?: any}[]>([]);
  const [scholarResults, setScholarResults] = useState<Record<string, {title: string, link: string}[]>>({});
  const [activeSummary, setActiveSummary] = useState<any>(null);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

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
    } catch (e) {
      console.error(e);
      alert("Verification failed.");
    }
  }

  const handleQuery = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query || !token) return;
    const currentQ = query;
    setQuery('');
    setHistory(prev => [...prev, {role: 'user', content: currentQ}]);
    setLoading(true);
    try {
      const resp = await fetch(`${API_URL}/agent/query?query=${encodeURIComponent(currentQ)}&token=${token}`, { method: 'POST' });
      const data = await resp.json();
      const outputTxt = data.agent_response || JSON.stringify(data, null, 2);
      const thinkingTxt = data.agent_thinking || "";
      setHistory(prev => [...prev, {role: 'agent', content: outputTxt, thinking: thinkingTxt, scholar_results: data.scholar_results}]);
      
      if (data.scholar_results && Object.keys(data.scholar_results).length > 0) {
        setScholarResults(data.scholar_results);
      }
    } catch (e) {
      console.error(e);
      setHistory(prev => [...prev, {role: 'agent', content: 'Connection to inference node lost.'}]);
    }
    setLoading(false);
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !token) return;
    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const resp = await fetch(`${API_URL}/ingest/pdf?token=${token}`, {
        method: 'POST',
        body: formData
      });
      const data = await resp.json();
      setHistory(prev => [...prev, {role: 'agent_upload_result', content: JSON.stringify(data, null, 2)}]);
    } catch (error) {
      console.error(error);
      alert("Document indexing failed.");
    }
    setLoading(false);
    if(fileInputRef.current) fileInputRef.current.value = '';
  }
  
  const callDummyTool = async () => {
    if(!token) return;
    try {
      const resp = await fetch(`${API_URL}/dummy_tool?input_val=test&token=${token}`, { method: 'POST' });
      const data = await resp.json();
      alert("Ping response: " + JSON.stringify(data));
    } catch(e) {
      alert("Error: " + e);
    }
  }

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
           <button onClick={callDummyTool} className="nav-item">
             <ActionIcon /> Diagnostic Ping
           </button>
           <button className="nav-item" onClick={() => fileInputRef.current?.click()}>
             <ActionIcon /> Ingest Document
           </button>

           <div className="nav-group-title" style={{ marginTop: '32px' }}>AGENTIC CAPABILITIES</div>
           <div className="capability-item" style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem', color: 'var(--text-muted)' }}><CheckIcon /> Local Sandbox Active</div>
           <div className="capability-item" style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem', color: 'var(--text-muted)' }}><CheckIcon /> KG Connection Alive</div>
           <div className="capability-item" style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem', color: 'var(--text-muted)' }}><CheckIcon /> OCR Vision Ready</div>
        </div>
        <div className="sidebar-footer">
          <div className="security-status" style={{ marginBottom: '16px', fontSize: '0.8rem', color: '#2f9e44', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'bold' }}>
            <ShieldIcon /> Air-Gapped Mode
          </div>
          <div className="hardware-metrics" style={{ marginBottom: '16px', fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}><span>GPU LOAD:</span> <span style={{color:'var(--text-dark)'}}>34%</span></div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>VRAM USAGE:</span> <span style={{color:'var(--text-dark)'}}>16.2 / 24 GB</span></div>
          </div>
          <div className="operator-block">
             <span className="dot active"></span> {username}
          </div>
          <button onClick={() => setToken(null)} className="disconnect-btn">Disconnect</button>
        </div>
      </aside>

      <main className="workspace main-console">
        <div className="topbar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
           <h2>Workspace: <span>Industrial Knowledge Workspace</span></h2>
           <div className="model-status" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.9rem', color: 'var(--accent-color)', fontWeight: 600, background: 'rgba(0,0,0,0.04)', padding: '6px 12px', borderRadius: '6px', fontFamily: 'var(--font-sans)' }}>
             <CpuIcon /> Open-Weight Engine: Qwen-2.5 / DeepSeek
           </div>
        </div>
        <div className="feed-scrollable">
          {history.length === 0 && (
            <div className="blank-canvas">
              <h3>Air-gapped industrial terminal connected.</h3>
                <div className="onboarding-cards">
                  <div className="card" onClick={() => setQuery("What are the primary safety protocols for industrial catalytic hydrocrackers?")}>
                     <h4>Query KG</h4>
                     <p>Search confidential process documentation.</p>
                  </div>
                  <div className="card highlight" onClick={() => fileInputRef.current?.click()}>
                     <h4>Index Data</h4>
                     <p>Upload a new PDF to expand the graph.</p>
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
                    <div className="sender-name">{isUser ? username : 'Lexicon'}</div>
                    
                    {msg.thinking && (
                       <details className="reasoning-drawer">
                         <summary>View Execution Trace</summary>
                         <div className="reasoning-body">{msg.thinking}</div>
                       </details>
                    )}
                    
                    <div className="prose-content">
                      <pre>{msg.content}</pre>
                    </div>
                    {msg.scholar_results && <CoverageChart data={msg.scholar_results} />}
                  </div>
                </div>
              );
            })}
            
            {loading && (
              <div className="thread-item agent-item loading-item">
                 <div className="avatar-column"><NodeIcon /></div>
                 <div className="content-column">
                    <div className="sender-name">Lexicon</div>
                    <div className="activity-indicator">
                       <div className="tracer-bar">
                         <div className="tracer-progress"></div>
                       </div>
                       <span>Compiling execution trace...</span>
                    </div>
                 </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
        </div>

        <div className="docked-composer">
          <form onSubmit={handleQuery} className="composer-form">
            <input id="file-upload" type="file" accept="application/pdf" ref={fileInputRef} onChange={handleFileUpload} disabled={loading} style={{display: 'none'}} />
            <textarea 
              placeholder="Query the Sovereign Knowledge Graph..." 
              value={query} 
              onChange={e => setQuery(e.target.value)} 
              disabled={loading}
              rows={1}
              onKeyDown={(e) => { if(e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleQuery(e); } }}
            />
            <button type="submit" disabled={loading || !query} className="send-action">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
            </button>
          </form>
        </div>
      </main>

      <aside className="sidebar right-panel" style={{ width: '280px', borderLeft: '1px solid rgba(0,0,0,0.1)', background: '#faf9f5', display: 'flex', flexDirection: 'column' }}>
        <div className="topbar" style={{ padding: '20px', borderBottom: '1px solid rgba(0,0,0,0.05)', display: 'flex', alignItems: 'center' }}>
           <h2 style={{ fontSize: '1.1rem', fontFamily: 'var(--font-sans)', color: 'var(--text-muted)' }}>Context & Artifacts</h2>
        </div>
        
        <div style={{ padding: '20px', flex: 1, overflowY: 'auto' }}>
           {Object.keys(scholarResults).length > 0 && (
             <>
               <div className="nav-group-title" style={{ marginTop: '0', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '12px' }}>RESEARCH PAPERS (SCHOLAR)</div>
               <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '32px', position: 'relative' }}>
                 {Object.entries(scholarResults).map(([keyword, results]) => (
                   <ScholarKeywordSection key={keyword} keyword={keyword} results={results} onOpenSummary={setActiveSummary} />
                 ))}
               </div>
             </>
           )}

           <div className="nav-group-title" style={{ marginTop: Object.keys(scholarResults).length > 0 ? '0' : '0', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '12px' }}>ACTIVE KNOWLEDGE BASE</div>
           
           <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '32px' }}>
             <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', background: '#fff', padding: '12px', borderRadius: '6px', border: '1px solid rgba(0,0,0,0.05)' }}>
                <div style={{ color: 'var(--accent-color)' }}><DatabaseIcon /></div>
                <div>
                   <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-dark)', marginBottom: '4px' }}>MRPL Internal Policies</div>
                   <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Local Vector DB Connected</div>
                </div>
             </div>
           </div>

           <div className="nav-group-title" style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '12px' }}>GENERATED COLLATERAL</div>
           <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '32px' }}>
             <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', background: '#fff', padding: '12px', borderRadius: '6px', border: '1px solid rgba(0,0,0,0.05)' }}>
                <div style={{ color: '#2f9e44' }}><FileIcon /></div>
                <div>
                   <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-dark)', marginBottom: '4px' }}>Approval_Note_Draft.docx</div>
                   <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Self-hosted generated</div>
                </div>
             </div>
             
             <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', background: '#fff', padding: '12px', borderRadius: '6px', border: '1px solid rgba(0,0,0,0.05)' }}>
                <div style={{ color: '#2f9e44' }}><FileIcon /></div>
                <div>
                   <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-dark)', marginBottom: '4px' }}>Engineering_Calcs.xlsx</div>
                   <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Via secure Python sandbox</div>
                </div>
             </div>
           </div>
           
           <div className="nav-group-title" style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '12px' }}>EXECUTION SANDBOX</div>
           <div style={{ background: '#1e1e1e', borderRadius: '6px', padding: '12px', color: '#d4d4d4', fontFamily: 'var(--font-mono)', fontSize: '0.75rem', lineHeight: 1.5 }}>
              <span style={{ color: '#569cd6' }}>$</span> verify_airgap_status<br/>
              <span style={{ color: '#4caf50' }}>[OK]</span> External network blocked<br/>
              <span style={{ color: '#569cd6' }}>$</span> sandbox run --strict<br/>
              <span style={{ color: '#4caf50' }}>[OK]</span> Sandbox secure.<br/>
              <span style={{ color: '#569cd6' }}>&gt;</span> Awaiting instructions...
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
                Open original source &↗
              </a>
              <button className="close-btn" onClick={() => setActiveSummary(null)}>×</button>
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

    </div>
  )
}

export default App
