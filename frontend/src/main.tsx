import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { Activity, ArrowDownToLine, ArrowLeft, ArrowRight, ArrowUpRight, BarChart3, Check, ChevronDown, CircleAlert, Clock3, Columns2, Eye, FlaskConical, Globe2, LayoutDashboard, Layers3, LoaderCircle, Monitor, Moon, Plus, ScanLine, Smartphone, Sun, Target } from 'lucide-react'
import { api, stages } from './api'
import type { Check as CheckResult, History, Job, Result } from './api'
import './styles.css'

const AnalysisIcon = ScanLine
const percent = (value?: number) => value == null ? '—' : `${(value * 100).toFixed(1)}%`
const date = (value?: string) => value ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—'
const message = (error: unknown) => error instanceof Error ? error.message : 'Something went wrong.'
const link = (id: string) => `#/analysis/${encodeURIComponent(id)}`
function readRoute() { return window.location.hash.slice(1) || '/' }

function App() {
  const [route, setRoute] = useState(readRoute)
  const [dark, setDark] = useState(() => localStorage.getItem('designqa-theme') === 'dark')
  useEffect(() => {
    const update = () => setRoute(readRoute())
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('designqa-theme', dark ? 'dark' : 'light')
  }, [dark])
  const jobId = route.startsWith('/analysis/') ? route.slice('/analysis/'.length) : ''
  return <div className="shell">
    <aside className="sidebar">
      <a className="brand" href="#/"><span className="brand-icon"><ScanLine size={22}/></span>Design<span>QA</span></a>
      <div className="nav">
        <a className={route === '/' ? 'active' : ''} href="#/"><LayoutDashboard size={18}/> Overview</a>
        <a className={route === '/new' ? 'active' : ''} href="#/new"><Plus size={18}/> New analysis</a>
        <a className={route === '/history' ? 'active' : ''} href="#/history"><Clock3 size={18}/> History</a>
      </div>
      <button className="theme" onClick={() => setDark(!dark)}>{dark ? <Sun size={18}/> : <Moon size={18}/>} {dark ? 'Light mode' : 'Dark mode'}</button>
    </aside>
    <main className="main">
      <div className="topbar"><span>Workspace</span><span>/</span><strong>{jobId ? 'Analysis' : route === '/new' ? 'New analysis' : route === '/history' ? 'History' : 'Overview'}</strong></div>
      <div className="content">
        {jobId ? <JobPage id={jobId} key={jobId}/> : route === '/new' ? <NewAnalysis/> : <Dashboard historyOnly={route === '/history'}/>}
      </div>
    </main>
  </div>
}

function Notice({ children }: { children: ReactNode }) {
  return <div className="notice" role="alert"><CircleAlert size={18}/><span>{children}</span></div>
}
function Heading({ title, description, children }: { title: string; description?: string; children?: ReactNode }) {
  return <header className="heading"><div><h1>{title}</h1>{description && <p>{description}</p>}</div>{children}</header>
}
function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: ReactNode }) {
  return <div className="panel metric"><div className="metric-icon">{icon}</div><div className="muted">{label}</div><strong>{value}</strong></div>
}
function Dashboard({ historyOnly }: { historyOnly: boolean }) {
  const [history, setHistory] = useState<History>()
  const [error, setError] = useState('')
  const [attempt, retry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setError('')
    api<History>('/history', undefined, controller.signal)
      .then(setHistory).catch(err => { if (!controller.signal.aborted) setError(message(err)) })
    return () => controller.abort()
  }, [attempt, historyOnly])
  return <>
    <Heading title={historyOnly ? 'Analysis history' : 'Overview'} description={historyOnly ? 'Review previous comparisons and reopen their reports.' : 'Compare your Figma designs with what’s live on the web.'}>
      <a href="#/new" className="button primary"><Plus size={17}/> New analysis</a>
    </Heading>
    {!historyOnly && <div className="metrics grid grid-cols-1 gap-4 sm:grid-cols-3">
      <Metric icon={<Globe2 size={19}/>} label="Websites tested" value={history?.totals?.websites ?? '—'}/>
      <Metric icon={<Layers3 size={19}/>} label="Issues detected" value={history?.totals?.issues ?? '—'}/>
      <Metric icon={<Target size={19}/>} label="Average visual similarity" value={percent(history?.totals?.similarity)}/>
    </div>}
    <section className="panel">
      <div className="section-head"><div><h2>{historyOnly ? 'All analyses' : 'Recent analyses'}</h2><p>View run status, similarity, and findings.</p></div>{!historyOnly && <a className="text-link" href="#/history">View history <ArrowRight size={15}/></a>}</div>
      {error ? <div className="section-body"><Notice>{error}</Notice><button className="button secondary mt-3" onClick={() => retry(attempt + 1)}>Retry</button></div> :
        !history ? <div className="empty"><LoaderCircle className="spin" size={24}/> Loading history</div> :
        history.items.length === 0 ? <div className="empty"><BarChart3 size={32}/><strong>No analyses yet</strong><a href="#/new" className="text-link">Start an analysis <ArrowRight size={15}/></a></div> :
        <div className="table-wrap"><table><thead><tr><th>Analysis</th><th>Date</th><th>Result</th><th>Similarity</th><th>Issues</th></tr></thead><tbody>
          {(historyOnly ? history.items : history.items.slice(0, 6)).map(item => <tr key={item.job_id}><td><a className="text-link" href={link(item.job_id)}>{item.name}<ArrowUpRight size={14}/></a></td><td>{date(item.created_at)}</td><td>{item.verdict ?? item.state.replaceAll('_', ' ')}</td><td>{percent(item.similarity)}</td><td>{item.issues ?? '—'}</td></tr>)}
        </tbody></table></div>}
    </section>
  </>
}

function NewAnalysis() {
  const [mode, setMode] = useState<'figma' | 'demo'>('figma')
  const [devices, setDevices] = useState({ desktop: true, mobile: true })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const values = new FormData(form)
    const breakpoints = [
      ...(devices.desktop ? [Number(values.get('desktop_width'))] : []),
      ...(devices.mobile ? [Number(values.get('mobile_width'))] : []),
    ]
    if (!breakpoints.length) { setError('Select at least one viewport.'); return }
    if (new Set(breakpoints).size !== breakpoints.length) { setError('Use a different width for each viewport.'); return }
    setError('')
    setBusy(true)
    try {
      const job = await api<{ job_id: string }>('/analyze', {
        mode, breakpoints,
        ...(mode === 'figma' ? {
          figma_url: values.get('figma_url'), live_url: values.get('live_url'),
          figma_token: String(values.get('figma_token') ?? '').trim() || undefined,
          hide_selectors: String(values.get('hide_selectors') ?? '').split(',').map(s => s.trim()).filter(Boolean),
        } : { demo_variant: values.get('demo_variant') }),
      })
      window.location.hash = link(job.job_id)
    } catch (err) { setError(message(err)) }
    finally {
      const token = form.elements.namedItem('figma_token')
      if (token instanceof HTMLInputElement) token.value = ''
      setBusy(false)
    }
  }
  return <>
    <a href="#/" className="text-link back"><ArrowLeft size={15}/> Overview</a>
    <Heading title="New analysis" description="Choose a design source and the viewport widths to compare."/>
    <div className="mode-tabs" aria-label="Design source">
      <button type="button" aria-pressed={mode === 'figma'} onClick={() => { setMode('figma'); setError('') }}><Layers3 size={17}/> Figma design</button>
      <button type="button" aria-pressed={mode === 'demo'} onClick={() => { setMode('demo'); setError('') }}><FlaskConical size={17}/> Demo analysis</button>
    </div>
    <form className="panel form" onSubmit={submit}>
      {mode === 'figma' ? <fieldset><legend>Design and website</legend>
        <label>Figma design URL<input name="figma_url" type="url" placeholder="https://www.figma.com/design/…" required/></label>
        <label>Live website URL<input name="live_url" type="url" placeholder="https://example.com" required/></label>
        <label>Figma access token<input name="figma_token" type="password" autoComplete="off" placeholder="Use server token if left blank"/><small>Use a token with read access to the Figma file.</small></label>
      </fieldset> : <fieldset><legend>Demo website</legend><label>Brewly variant<select name="demo_variant"><option value="buggy">Seeded defects</option><option value="baseline">Clean baseline</option></select></label></fieldset>}
      <fieldset><legend>Viewports</legend><div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {(['desktop', 'mobile'] as const).map(device => {
          const Icon = device === 'desktop' ? Monitor : Smartphone
          return <div className="viewport" key={device}>
            <label className="check"><input type="checkbox" checked={devices[device]} onChange={event => setDevices({ ...devices, [device]: event.target.checked })}/><Icon size={17}/>{device === 'desktop' ? 'Desktop' : 'Mobile'}</label>
            <label>Width (px)<input key={mode} name={`${device}_width`} type="number" min={320} max={2560} defaultValue={device === 'desktop' ? 1440 : 375} disabled={!devices[device]} readOnly={mode === 'demo'} required/></label>
          </div>
        })}
      </div></fieldset>
      {mode === 'figma' && <details><summary>Analysis options <ChevronDown size={15}/></summary><label>Hide selectors<input name="hide_selectors" placeholder=".ad-banner, .carousel"/><small>Comma-separated selectors for dynamic content.</small></label></details>}
      {error && <Notice>{error}</Notice>}
      <div className="form-actions"><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17}/> : <AnalysisIcon size={17}/>} {busy ? 'Submitting…' : 'Analyze website'}</button></div>
    </form>
  </>
}

function JobPage({ id }: { id: string }) {
  const [job, setJob] = useState<Job>()
  const [result, setResult] = useState<Result>()
  const [error, setError] = useState('')
  const [revision, refresh] = useState(0)
  const [sending, setSending] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    let timer: number | undefined
    async function poll() {
      try {
        const next = await api<Job>(`/analyze/${id}`, undefined, controller.signal)
        if (controller.signal.aborted) return
        setJob(next)
        setError('')
        if (next.state === 'completed') {
          const report = await api<Result>(`/results/${id}`, undefined, controller.signal)
          if (!controller.signal.aborted) setResult(report)
        } else if (next.state === 'queued' || next.state === 'running') {
          timer = window.setTimeout(poll, 1300)
        }
      } catch (err) { if (!controller.signal.aborted) setError(message(err)) }
    }
    void poll()
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [id, revision])

  async function approve(event: FormEvent<HTMLFormElement>, step: 'frames' | 'mapping') {
    event.preventDefault()
    if (!job) return
    const fields = new FormData(event.currentTarget)
    const body = step === 'frames' ?
      { frames: (job.breakpoints ?? []).map(breakpoint => ({ breakpoint, frame_id: fields.get(String(breakpoint)) })) } :
      { mappings: (job.mappings ?? []).map(({ node_id, breakpoint }, i) => ({ node_id, breakpoint, selector: String(fields.get(`selector-${i}`) ?? '').trim() || null })) }
    setSending(true)
    setError('')
    try {
      await api(`/analyze/${id}/${step}`, body)
      setJob({ job_id: id, state: 'queued', events: job.events })
      refresh(n => n + 1)
    } catch (err) { setError(message(err)) }
    finally { setSending(false) }
  }
  if (result) return <Results result={result}/>
  return <>
    <a href="#/" className="text-link back"><ArrowLeft size={15}/> Overview</a>
    <Heading title={job?.state === 'awaiting_frames' ? 'Select design frames' : job?.state === 'awaiting_mapping' ? 'Review element mappings' : 'Analysis progress'}
      description={job ? `Run ${job.job_id}` : undefined}/>
    {error && <div className="mb-4"><Notice>{error}</Notice><button className="button secondary mt-3" onClick={() => refresh(n => n + 1)}>Refresh status</button></div>}
    {job?.error && <div className="mb-4"><Notice>{job.error.message}</Notice></div>}
    {job?.state === 'awaiting_frames' && <form className="panel form" onSubmit={e => approve(e, 'frames')}>
      <p className="muted">Select the Figma frame that matches each viewport.</p>
      {(job.breakpoints ?? []).map(width => <label key={width}>{width} px<select name={String(width)} defaultValue={job.selected_frames?.[String(width)] ?? ""} required>
        <option value="" disabled>Choose a frame</option>
        {job.frames?.map(frame => <option value={frame.id} key={frame.id}>{frame.name} · {frame.width} × {frame.height} px</option>)}
      </select></label>)}
      <div className="form-actions"><button className="button primary" disabled={sending}>Confirm frames <ArrowRight size={16}/></button></div>
    </form>}
    {job?.state === 'awaiting_mapping' && <form className="panel form" onSubmit={e => approve(e, 'mapping')}>
      <p className="muted">Check the suggested selectors. Leave a selector blank to skip that layer.</p>
      {job.mappings?.map((map, i) => <div className="mapping-row" key={`${map.breakpoint}-${map.node_id}`}>
        <label>{map.label} · {map.breakpoint} px<input name={`selector-${i}`} defaultValue={map.selector} placeholder="CSS selector"/></label>
        <small>{[map.confidence, ...(map.signals ?? [])].filter(Boolean).join(' · ') || 'No suggestion'}</small>
      </div>)}
      <div className="form-actions"><button className="button primary" disabled={sending}>Confirm mappings <ArrowRight size={16}/></button></div>
    </form>}
    {job && !['awaiting_frames','awaiting_mapping'].includes(job.state) && <section className="panel">
      <div className="section-head"><div><h2>{job.state === 'interrupted' ? 'Interrupted' : job.state === 'failed' ? 'Analysis failed' : job.state === 'completed' ? 'Loading results' : job.state === 'queued' ? 'Queued' : 'Running checks'}</h2>
        {job.total_checks != null && <p>{job.completed_checks ?? 0} of {job.total_checks} checks completed</p>}</div><Activity size={22}/></div>
      <ol className="stages" aria-live="polite">{stages.map(([key, title]) => {
        const stageEvent = job.events?.slice().reverse().find(event => event.stage === key)
        const active = job.stage === key && job.state === 'running'
        return <li key={key}><span className={active || stageEvent ? 'done' : ''}>{active ? <LoaderCircle className="spin" size={15}/> : stageEvent ? <Check size={15}/> : <span className="dot"/>}</span>
          <div><strong>{title}</strong>{stageEvent?.message && <p>{stageEvent.message}</p>}</div></li>
      })}</ol>
    </section>}
    {!job && !error && <div className="panel empty" role="status"><LoaderCircle className="spin" size={24}/> Loading analysis</div>}
  </>
}

const categories = ['Typography', 'Alignment', 'Colour', 'Component', 'Visual'] as const
function classify(property: string, category: string) {
  if (category === 'Visual') return 'Visual'
  if (/font|line.height/i.test(property)) return 'Typography'
  if (/colou?r/i.test(property)) return 'Colour'
  if (/position|width|height|spacing/i.test(property)) return 'Alignment'
  return 'Component'
}

function Results({ result }: { result: Result }) {
  const [selected, setSelected] = useState(0)
  const [tab, setTab] = useState<'findings' | 'visual'>('findings')
  const [category, setCategory] = useState('All')
  const [overlay, setOverlay] = useState(false)
  const [opacity, setOpacity] = useState(50)
  const check: CheckResult | undefined = result.checks[selected]
  const findings = check?.findings ?? []
  const shown = findings.filter(item => category === 'All' || classify(item.property, item.category) === category)
  const report = (format: string) => `/api/reports/${encodeURIComponent(result.job_id)}?format=${format}`
  return <>
    <a href="#/history" className="text-link back"><ArrowLeft size={15}/> History</a>
    <Heading title="Analysis results" description={[result.live_url, result.created_at && date(result.created_at)].filter(Boolean).join(' · ')}/>
    <div className="metrics grid grid-cols-1 gap-4 sm:grid-cols-3">
      <Metric icon={<Activity size={18}/>} label="Overall result" value={result.verdict ?? '—'}/>
      <Metric icon={<Target size={18}/>} label="Overall similarity" value={percent(result.similarity)}/>
      <Metric icon={<Layers3 size={18}/>} label="Total issues across viewports" value={result.issues ?? '—'}/>
    </div>
    <div className="report-links">{['html', 'xlsx', 'json'].map(format => <a className="button secondary" key={format} href={report(format)} download><ArrowDownToLine size={15}/>{format.toUpperCase()}</a>)}</div>
    {check ? <>
      <div className="result-controls"><label>Page and breakpoint<select value={selected} onChange={e => setSelected(Number(e.target.value))}>
        {result.checks.map((item, i) => <option value={i} key={i}>{item.page} · {item.breakpoint} px</option>)}
      </select></label></div>
      <div className="metrics grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <Metric icon={<Layers3 size={18}/>} label="Total issues" value={findings.length}/>
        {(['High','Medium','Low'] as const).map(severity => <Metric key={severity} icon={<CircleAlert size={18}/>} label={severity} value={findings.filter(item => item.severity === severity).length}/>)}
        <Metric icon={<Target size={18}/>} label="Similarity" value={percent(check.ssim)}/>
        <Metric icon={<Activity size={18}/>} label="Result" value={check.status}/>
      </div>
      {check.error && <div className="mb-4"><Notice>{check.error}</Notice></div>}
      <div className="mode-tabs"><button aria-pressed={tab === 'findings'} onClick={() => setTab('findings')}><Layers3 size={16}/> Findings</button><button aria-pressed={tab === 'visual'} onClick={() => setTab('visual')}><Eye size={16}/> Visual comparison</button></div>
      {tab === 'findings' ? <section className="panel">
        <div className="section-head"><div><h2>Findings</h2>{check.coverage?.map((note, i) => <p key={i}>{note}</p>)}</div>
          <select aria-label="Finding category" value={category} onChange={e => setCategory(e.target.value)}>{['All', ...categories].map(name => <option key={name}>{name}</option>)}</select>
        </div>
        {shown.length ? <div className="table-wrap"><table><thead><tr>{['Element','Category','Check','Expected','Actual','Difference','Severity','Breakpoint'].map(title => <th key={title}>{title}</th>)}</tr></thead>
          <tbody>{shown.map((item, i) => <tr key={i}><td>{item.label}{item.recommendation && <small className="block mt-1">{item.recommendation}</small>}</td><td>{classify(item.property,item.category)}</td><td>{item.property}</td><td>{item.expected}</td><td>{item.actual}</td><td>{item.difference ?? '—'}</td><td><span className={`severity ${item.severity.toLowerCase()}`}>{item.severity}</span></td><td>{check.breakpoint} px</td></tr>)}</tbody>
        </table></div> : <div className="empty">{check.status === 'ERROR' ? 'Comparison unavailable for this breakpoint.' : category === 'All' ? 'No findings for this breakpoint.' : 'No findings in this category.'}</div>}
      </section> : <section className="panel">
        <div className="section-head"><div><h2>Screenshot comparison</h2><p>{check.breakpoint} px · {percent(check.ssim)} similarity</p></div>
          {check.images && <button className="button secondary" onClick={() => setOverlay(!overlay)}><Columns2 size={16}/>{overlay ? 'Side by side' : 'Overlay'}</button>}
        </div>
        {check.images ? <div className="section-body screenshots">
          {overlay ? <>
            <label>Live image opacity · {opacity}%<input type="range" min="0" max="100" value={opacity} onChange={e => setOpacity(Number(e.target.value))}/></label>
            <figure className="overlay"><img src={check.images.design} alt="Design screenshot"/><img src={check.images.live} alt="Live screenshot overlay" style={{ opacity: opacity / 100 }}/></figure>
          </> : <div className="grid grid-cols-1 gap-4 md:grid-cols-3">{(['design','live','diff'] as const).map((key) => <figure key={key}><figcaption>{key === 'diff' ? 'Highlighted differences' : key === 'live' ? 'Live website' : 'Design reference'}</figcaption><img src={check.images?.[key]} alt={`${key} screenshot`}/></figure>)}</div>}
        </div> : <div className="empty">Screenshots are unavailable for this check.</div>}
      </section>}
    </> : <div className="panel empty">This run returned no comparison checks.</div>}
  </>
}

createRoot(document.getElementById('root')!).render(<App/>)



