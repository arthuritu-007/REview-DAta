import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import './App.css'

type UserSession = {
  email?: string
  role?: string
}

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n))
}

function Gauge({ value }: { value: number }) {
  const v = clamp(Number(value || 0), 0, 100)
  const r = 46
  const c = 2 * Math.PI * r
  const dash = (v / 100) * c
  const color = v >= 85 ? '#22c55e' : v >= 70 ? '#60a5fa' : v >= 50 ? '#ff9900' : '#dc3545'
  return (
    <div style={{ display: 'grid', placeItems: 'center' }}>
      <svg width="120" height="120" viewBox="0 0 120 120">
        <defs>
          <linearGradient id="rdGaugeGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={color} stopOpacity="0.7" />
            <stop offset="1" stopColor={color} stopOpacity="1" />
          </linearGradient>
        </defs>
        <circle cx="60" cy="60" r={r} stroke="#263244" strokeWidth="12" fill="none" />
        <circle
          cx="60"
          cy="60"
          r={r}
          stroke="url(#rdGaugeGrad)"
          strokeWidth="12"
          fill="none"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c - dash}`}
          transform="rotate(-90 60 60)"
          style={{ transition: 'stroke-dasharray 650ms ease' }}
        />
        <text x="60" y="63" textAnchor="middle" fontSize="22" fill="#e5e7eb" fontWeight="800">
          {v}
        </text>
        <text x="60" y="82" textAnchor="middle" fontSize="11" fill="#94a3b8" fontWeight="700">
          /100
        </text>
      </svg>
    </div>
  )
}

function CountUpNumber({ value, durationMs = 700 }: { value: number; durationMs?: number }) {
  const target = Number(value || 0)
  const [v, setV] = useState(0)

  useEffect(() => {
    let raf = 0
    const start = performance.now()
    const from = v
    const to = target
    const dur = Math.max(150, Number(durationMs || 700))

    const tick = (t: number) => {
      const p = clamp((t - start) / dur, 0, 1)
      const eased = 1 - Math.pow(1 - p, 3)
      const next = Math.round(from + (to - from) * eased)
      setV(next)
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target])

  return <>{v}</>
}

function Skeleton({ h = 14, w = '100%', r = 12 }: { h?: number; w?: number | string; r?: number }) {
  return <div className="rd-skel" style={{ height: h, width: w, borderRadius: r }} />
}

function getStoredToken(): string | null {
  return localStorage.getItem('rd_token')
}

function setStoredToken(token: string | null) {
  if (!token) {
    localStorage.removeItem('rd_token')
    return
  }
  localStorage.setItem('rd_token', token)
}

async function readError(res: Response): Promise<string> {
  const contentType = res.headers.get('content-type') || ''
  try {
    if (contentType.includes('application/json')) {
      const j = await res.json()
      return j.detail || j.message || JSON.stringify(j)
    }
    return await res.text()
  } catch {
    return `HTTP ${res.status}`
  }
}

function validateEmailInput(email: string): string {
  const e = String(email || '').trim()
  if (!e) return 'Email requerido.'
  if (e.length > 254) return 'Email demasiado largo.'
  if (/\s/.test(e)) return 'Email inválido.'
  const parts = e.split('@')
  if (parts.length !== 2) return 'Email inválido.'
  const [local, domain] = parts
  if (!local || !domain) return 'Email inválido.'
  if (local.length > 64) return 'Email inválido.'
  const emailRe = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$/
  if (!emailRe.test(e)) return 'Email inválido. Debe ser un correo válido.'
  return ''
}

function validatePasswordInput(password: string): string {
  const p = String(password || '')
  if (!p) return 'Contraseña requerida.'
  if (p.length < 10) return 'Contraseña inválida. Mínimo 10 caracteres.'
  if (p.length > 64) return 'Contraseña inválida. Máximo 64 caracteres.'
  if (/\s/.test(p)) return 'Contraseña inválida. No debe contener espacios.'
  if (!/[A-Za-z]/.test(p)) return 'Contraseña inválida. Debe incluir al menos una letra.'
  if (!/\d/.test(p)) return 'Contraseña inválida. Debe incluir al menos un número.'
  for (const ch of p) {
    const code = ch.codePointAt(0) || 0
    if (code < 33 || code > 126) return 'Contraseña inválida. Usa caracteres imprimibles (sin espacios).'
  }
  return ''
}

function useApi(token: string | null) {
  const apiJson = async (path: string, init?: RequestInit) => {
    const headers: Record<string, string> = {}
    if (init?.headers) Object.assign(headers, init.headers as any)
    if (token) headers.Authorization = `Bearer ${token}`
    const res = await fetch(path, { ...init, headers })
    if (!res.ok) throw new Error(await readError(res))
    return res.json()
  }

  const apiFetch = async (path: string, init?: RequestInit) => {
    const headers: Record<string, string> = {}
    if (init?.headers) Object.assign(headers, init.headers as any)
    if (token) headers.Authorization = `Bearer ${token}`
    const res = await fetch(path, { ...init, headers })
    if (!res.ok) throw new Error(await readError(res))
    return res
  }

  return { apiJson, apiFetch }
}

function Protected({ token, children }: { token: string | null; children: React.ReactNode }) {
  const loc = useLocation()
  if (!token) return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />
  return <>{children}</>
}

function LoginPage({
  onLoggedIn,
}: {
  onLoggedIn: (token: string, session: UserSession) => void
}) {
  const navigate = useNavigate()
  const location = useLocation() as any
  const [email, setEmail] = useState('user@reviewdata.local')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>('')

  const { apiJson } = useApi(null)

  const submit = async () => {
    setBusy(true)
    setError('')
    try {
      const sess = await apiJson('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const token = String(sess.token || '')
      if (!token) throw new Error('Token vacío.')
      const session: UserSession = { email: sess.email, role: sess.role }
      onLoggedIn(token, session)
      const to = (location?.state?.from as string) || '/app'
      navigate(to, { replace: true })
    } catch (e: any) {
      setError(e?.message || String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rd-login-page">
      <div className="rd-login-card">
        <div className="rd-login-brand">
          <div className="rd-badge">RD</div>
          <div>
            <div className="rd-title">Review Data</div>
            <div className="rd-subtitle">Sistema Web</div>
          </div>
        </div>

        <div className="rd-card-title">Iniciar sesión</div>
        <div className="rd-form">
          <label>
            Email
            <input value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label>
            Contraseña
            <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" />
          </label>
          <button className="rd-primary" onClick={submit} disabled={busy}>
            {busy ? 'Entrando…' : 'Entrar'}
          </button>
          {error ? <div className="rd-error">{error}</div> : null}
        </div>
      </div>
    </div>
  )
}

function AppLayout({
  token,
  session,
  onLogout,
  status,
  setStatus,
}: {
  token: string
  session: UserSession
  onLogout: () => void
  status: string
  setStatus: (s: string) => void
}) {
  const isAdmin = String(session.role || 'user') === 'admin'
  const location = useLocation()
  const navigate = useNavigate()
  const [globalQ, setGlobalQ] = useState('')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return localStorage.getItem('rd_sidebar_collapsed') === '1'
    } catch {
      return false
    }
  })

  const navItems = useMemo(() => {
    if (isAdmin) {
      return [
        { to: '/app/admin', label: 'Dashboard Admin', icon: 'AD' },
        { to: '/app/admin/users', label: 'Usuarios', icon: 'US' },
        { to: '/app/admin/rules', label: 'Reglas', icon: 'RG' },
        { to: '/app/admin/activity', label: 'Bitácora', icon: 'LG' },
      ]
    }
    return [
      { to: '/app', label: 'Inicio', icon: 'IN' },
      { to: '/app/datasets', label: 'Cargar Dataset', icon: 'DS' },
      { to: '/app/validation', label: 'Validación', icon: 'VL' },
      { to: '/app/findings', label: 'Hallazgos', icon: 'HZ' },
      { to: '/app/recommendations', label: 'Recomendaciones', icon: 'RC' },
      { to: '/app/stats', label: 'Estadísticas', icon: 'ST' },
      { to: '/app/dataset-history', label: 'Historial Dataset', icon: 'HD' },
      { to: '/app/report-history', label: 'Historial Reporte', icon: 'HR' },
    ]
  }, [isAdmin])

  const currentTitle = useMemo(() => {
    const exact = navItems.find((n) => n.to === location.pathname)
    if (exact) return exact.label
    if (location.pathname.startsWith('/app/admin')) return 'Administración'
    if (location.pathname.startsWith('/app')) return 'Panel'
    return 'Review Data'
  }, [location.pathname, navItems])

  const toggleSidebar = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev
      try {
        localStorage.setItem('rd_sidebar_collapsed', next ? '1' : '0')
      } catch {
      }
      return next
    })
  }

  return (
    <div className={sidebarCollapsed ? 'rd-shell collapsed' : 'rd-shell'}>
      <aside className={sidebarCollapsed ? 'rd-sidebar collapsed' : 'rd-sidebar'}>
        <div className="rd-brand">
          <button className="rd-icon-btn" onClick={toggleSidebar} title={sidebarCollapsed ? 'Expandir' : 'Contraer'}>
            {sidebarCollapsed ? '»' : '«'}
          </button>
          <div className="rd-badge">RD</div>
          <div className="rd-brand-text">
            <div className="rd-title">Review Data</div>
            <div className="rd-subtitle">{session.email || 'Sesión'}</div>
          </div>
        </div>

        <nav className="rd-nav">
          {navItems.map((it) => (
            <Link
              key={it.to}
              className={location.pathname === it.to ? 'active' : ''}
              to={it.to}
              title={sidebarCollapsed ? it.label : undefined}
            >
              <span className="rd-nav-ico">{it.icon}</span>
              <span className="rd-nav-label">{it.label}</span>
            </Link>
          ))}
        </nav>

        <div className="rd-sidebar-footer">
        </div>
      </aside>

      <main className="rd-main">
        <header className="rd-topbar">
          <div className="left">
            <div className="rd-topbar-title">{currentTitle}</div>
            <div className="rd-pill">{isAdmin ? 'ADMIN' : 'USUARIO'}</div>
          </div>
          <div className="rd-search">
            <input
              value={globalQ}
              onChange={(e) => setGlobalQ(e.target.value)}
              placeholder="Búsqueda global (dataset/run/regla)…"
              onKeyDown={(e) => {
                if (e.key !== 'Enter') return
                const q = globalQ.trim()
                if (!q) return
                navigate(`/app/dataset-history?q=${encodeURIComponent(q)}`)
              }}
            />
          </div>
          <div className="right">
            <button className="rd-danger" onClick={onLogout}>
              Cerrar sesión
            </button>
          </div>
        </header>
        <div className={status && status !== 'Listo.' ? 'rd-loading-bar active' : 'rd-loading-bar'} />
        <div className="rd-status">{status}</div>
        <Routes>
          <Route index element={<DashboardPage token={token} setStatus={setStatus} />} />
          <Route path="datasets" element={<UploadDatasetPage token={token} setStatus={setStatus} />} />
          <Route path="validation" element={<ValidationPage token={token} setStatus={setStatus} />} />
          <Route path="findings" element={<FindingsPage token={token} setStatus={setStatus} />} />
          <Route path="recommendations" element={<RecommendationsPage token={token} setStatus={setStatus} />} />
          <Route path="stats" element={<StatsPage token={token} setStatus={setStatus} />} />
          <Route path="dataset-history" element={<DatasetHistoryPage token={token} setStatus={setStatus} />} />
          <Route path="report-history" element={<ReportHistoryPage token={token} setStatus={setStatus} />} />

          <Route path="admin" element={<AdminDashboardPage token={token} setStatus={setStatus} />} />
          <Route path="admin/users" element={<AdminUsersPage token={token} setStatus={setStatus} />} />
          <Route path="admin/rules" element={<AdminRulesPage token={token} setStatus={setStatus} />} />
          <Route path="admin/activity" element={<AdminActivityPage token={token} setStatus={setStatus} />} />

          <Route path="*" element={<Navigate to="/app" replace />} />
        </Routes>
      </main>
    </div>
  )
}

function DashboardPage({ token, setStatus }: { token: string; setStatus: (s: string) => void }) {
  const { apiJson } = useApi(token)
  const [stats, setStats] = useState<any | null>(null)
  const [runs, setRuns] = useState<any[]>([])
  const [severity, setSeverity] = useState<Record<string, number>>({})
  const [datasetScores, setDatasetScores] = useState<Record<string, number>>({})
  const [overview, setOverview] = useState<any | null>(null)
  const [aiRunId, setAiRunId] = useState('')
  const [aiInsights, setAiInsights] = useState<any[]>([])
  const [aiDrift, setAiDrift] = useState<any[]>([])
  const [aiQ, setAiQ] = useState('')
  const [aiA, setAiA] = useState<any | null>(null)
  const [aiBusy, setAiBusy] = useState(false)
  const [loading, setLoading] = useState(true)

  const refresh = async () => {
    setStatus('Cargando dashboard...')
    setLoading(true)
    try {
      const [s, r, sev, ds, ov] = await Promise.all([
        apiJson('/api/dashboard/stats'),
        apiJson('/api/runs?offset=0&limit=25'),
        apiJson('/api/stats/severity'),
        apiJson('/api/datasets?offset=0&limit=500'),
        apiJson('/api/stats/overview'),
      ])
      setStats(s)
      const runItems = Array.isArray((r as any)?.items) ? (r as any).items : Array.isArray(r) ? r : []
      setRuns(runItems)
      setSeverity(sev || {})
      const map: Record<string, number> = {}
      const datasetItems = Array.isArray((ds as any)?.items) ? (ds as any).items : Array.isArray(ds) ? ds : []
      if (Array.isArray(datasetItems)) {
        for (const d of datasetItems) {
          const id = String(d?.id || '')
          if (!id) continue
          const score = Number(d?.quality_score ?? 0)
          if (!Number.isNaN(score)) map[id] = score
        }
      }
      setDatasetScores(map)
      setOverview(ov || null)
      try {
        const latest = String(runItems?.[0]?.id || '')
        if (latest) {
          setAiRunId(latest)
          const [ins, dr] = await Promise.all([
            apiJson(`/api/ai/insights?run_id=${encodeURIComponent(latest)}`),
            apiJson(`/api/ai/drift?run_id=${encodeURIComponent(latest)}`),
          ])
          setAiInsights(Array.isArray(ins) ? ins : [])
          setAiDrift(Array.isArray(dr) ? dr : [])
        } else {
          setAiRunId('')
          setAiInsights([])
          setAiDrift([])
        }
      } catch {
        setAiInsights([])
        setAiDrift([])
      }
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  return (
    <section className="rd-grid">
      <div className="rd-card">
        <div className="rd-card-title">DATA HEALTH</div>
        <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: 14, alignItems: 'center' }}>
          {loading ? (
            <Skeleton h={120} w={120} r={999} />
          ) : (
            <Gauge value={Number(stats?.latest_health_score ?? stats?.latest_quality_score ?? overview?.avg_quality_score ?? 0)} />
          )}
          <div>
            <div className="rd-sev">
              <div>
                Health Score (último run):{' '}
                {loading ? (
                  <Skeleton h={12} w={110} r={10} />
                ) : (
                  <span className="mono">{stats?.latest_health_score ?? stats?.latest_quality_score ?? overview?.avg_quality_score ?? 0}/100</span>
                )}
              </div>
              <div>
                Grade:{' '}
                {loading ? <Skeleton h={12} w={70} r={10} /> : <span className="mono">{String(stats?.latest_health_grade ?? '') || '—'}</span>}
              </div>
              <div>
                Tendencia (vs anterior):{' '}
                {loading ? (
                  <Skeleton h={12} w={60} r={10} />
                ) : (
                  <span className="mono">{stats?.latest_score_delta === null || stats?.latest_score_delta === undefined ? '—' : `${stats.latest_score_delta > 0 ? '+' : ''}${stats.latest_score_delta}`}</span>
                )}
              </div>
              <div>
                % reglas OK: {loading ? <Skeleton h={12} w={70} r={10} /> : <span className="mono">{overview?.pct_rules_ok ?? 0}%</span>}
              </div>
              <div>
                Datasets: {loading ? <Skeleton h={12} w={40} r={10} /> : <span className="mono">{stats?.datasets ?? 0}</span>}
              </div>
              <div>
                Validaciones: {loading ? <Skeleton h={12} w={40} r={10} /> : <span className="mono">{stats?.validations ?? 0}</span>}
              </div>
            </div>
            <div className="rd-progress">
              <div
                className="bar"
                style={{ width: `${clamp(Number(stats?.latest_health_score ?? stats?.latest_quality_score ?? overview?.avg_quality_score ?? 0), 0, 100)}%` }}
              />
            </div>
          </div>
        </div>

        <div className="rd-card-title" style={{ marginTop: 14 }}>
          Resumen
        </div>
        <div className="rd-kpis">
          <div className="rd-kpi">
            <div className="label">Datasets</div>
            <div className="value">{loading ? <Skeleton h={26} w={60} r={10} /> : <CountUpNumber value={Number(stats?.datasets ?? 0)} />}</div>
          </div>
          <div className="rd-kpi">
            <div className="label">Validaciones</div>
            <div className="value">{loading ? <Skeleton h={26} w={60} r={10} /> : <CountUpNumber value={Number(stats?.validations ?? 0)} />}</div>
          </div>
          <div className="rd-kpi">
            <div className="label">Inconsistencias</div>
            <div className="value">{loading ? <Skeleton h={26} w={80} r={10} /> : <CountUpNumber value={Number(stats?.inconsistencies ?? 0)} />}</div>
          </div>
        </div>
        <div className="rd-sev">
          <div>Crítica: {loading ? '—' : severity['Crítica'] ?? severity['CrÝtica'] ?? 0}</div>
          <div>Alta: {loading ? '—' : severity['Alta'] ?? 0}</div>
          <div>Media: {loading ? '—' : severity['Media'] ?? 0}</div>
          <div>Baja: {loading ? '—' : severity['Baja'] ?? 0}</div>
        </div>
        <div className="rd-actions">
          <button className="rd-primary" onClick={refresh}>
            Actualizar
          </button>
        </div>
      </div>

      <div className="rd-card">
        <div className="rd-card-title">AI Insights</div>
        {loading ? (
          <div className="rd-form">
            <Skeleton h={14} />
            <Skeleton h={14} />
            <Skeleton h={14} />
            <Skeleton h={44} />
          </div>
        ) : (
          <>
            <div className="rd-sev">
              <div className="mono">Run: {aiRunId ? aiRunId.slice(0, 8) : '—'}</div>
              <div>Top risk: {aiInsights.find((x: any) => String(x?.severity || '') === 'Crítica') ? <span className="rd-pill bad">Crítico</span> : <span className="rd-pill good">Estable</span>}</div>
            </div>
            <div style={{ marginTop: 10 }}>
              {aiInsights?.length ? (
                <div className="rd-form">
                  {aiInsights.slice(0, 6).map((it: any) => (
                    <div key={it.id} className="rd-ai-item">
                      <div className={String(it.severity || '') === 'Crítica' || String(it.severity || '') === 'Alta' ? 'rd-pill bad' : 'rd-pill good'}>
                        {String(it.title || 'AI')}
                      </div>
                      <div className="rd-ai-text">{String(it.description || '')}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="muted">Sin insights aún. Ejecuta una validación para generarlos.</div>
              )}
            </div>

            {aiDrift?.length ? (
              <div style={{ marginTop: 12 }}>
                <div className="rd-card-title">Drift (vs run anterior)</div>
                <div className="rd-table-wrap" style={{ maxHeight: 220 }}>
                  <table className="rd-table">
                    <thead>
                      <tr>
                        <th>Tipo</th>
                        <th>Campo</th>
                        <th>Diferencia</th>
                        <th>Sev.</th>
                      </tr>
                    </thead>
                    <tbody>
                      {aiDrift.slice(0, 12).map((d: any) => (
                        <tr key={d.id}>
                          <td className="mono">{d.drift_type}</td>
                          <td className="mono">{String(d.field || '').slice(0, 34)}</td>
                          <td className="mono">{d.difference}</td>
                          <td>{d.severity}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}

            <div style={{ marginTop: 12 }}>
              <div className="rd-card-title">Preguntar al sistema</div>
              <div className="rd-form rd-inline">
                <label style={{ flex: 1 }}>
                  Pregunta
                  <input value={aiQ} onChange={(e) => setAiQ(e.target.value)} placeholder="Ej: ¿Qué debo corregir primero?" />
                </label>
                <button
                  className="rd-primary"
                  disabled={aiBusy}
                  onClick={async () => {
                    const q = aiQ.trim()
                    if (!q) return
                    setAiBusy(true)
                    setStatus('Consultando AI...')
                    try {
                      const res = await apiJson('/api/ai/query', {
                        method: 'POST',
                        body: JSON.stringify({ question: q, run_id: aiRunId || null }),
                        headers: { 'Content-Type': 'application/json' },
                      })
                      setAiA(res || null)
                      setStatus('Listo.')
                    } catch (e: any) {
                      setStatus(`Error: ${e?.message || e}`)
                    } finally {
                      setAiBusy(false)
                    }
                  }}
                >
                  {aiBusy ? '...' : 'Enviar'}
                </button>
              </div>
              {aiA ? (
                <div className="rd-error" style={{ marginTop: 10, background: 'rgba(34,197,94,0.08)', borderColor: 'rgba(34,197,94,0.25)' }}>
                  {String(aiA.answer || '')}
                </div>
              ) : null}
            </div>
          </>
        )}
      </div>

      <div className="rd-card">
        <div className="rd-card-title">Últimas ejecuciones</div>
        <div className="rd-table-wrap">
          <table className="rd-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Dataset</th>
                <th>Incons.</th>
                <th>Score</th>
                <th>Usuario</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i}>
                    <td colSpan={5}>
                      <Skeleton h={14} />
                    </td>
                  </tr>
                ))
              ) : (
                runs.slice(0, 25).map((r) => (
                <tr key={r.id}>
                  <td className="mono">{String(r.id).slice(0, 8)}</td>
                  <td>{r.dataset_name}</td>
                  <td>{r.inconsistencies}</td>
                  <td className="mono">{datasetScores[String(r.dataset_id || '')] ?? ''}</td>
                  <td>{r.user_email}</td>
                </tr>
                ))
              )}
              {!runs.length ? (
                <tr>
                  <td colSpan={5} className="muted">
                    Sin datos
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}

function UploadDatasetPage({ token, setStatus }: { token: string; setStatus: (s: string) => void }) {
  const { apiJson } = useApi(token)
  const [file, setFile] = useState<File | null>(null)
  const [dragActive, setDragActive] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [datasets, setDatasets] = useState<any[]>([])
  const [activeDataset, setActiveDataset] = useState<any | null>(null)
  const [profile, setProfile] = useState<any | null>(null)
  const [preview, setPreview] = useState<any | null>(null)
  const [detected, setDetected] = useState<{ name: string; confidence: number } | null>(null)
  const [metrics, setMetrics] = useState<any | null>(null)
  const [heatmap, setHeatmap] = useState<any[]>([])
  const [expectations, setExpectations] = useState<any[]>([])
  const [selectedExp, setSelectedExp] = useState<Record<string, boolean>>({})
  const [acceptBusy, setAcceptBusy] = useState(false)

  const refresh = async () => {
    setStatus('Cargando datasets...')
    try {
      const ds = await apiJson('/api/datasets?offset=0&limit=500')
      const items = Array.isArray((ds as any)?.items) ? (ds as any).items : Array.isArray(ds) ? ds : []
      setDatasets(items)
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const detectDataset = (p: any) => {
    const cols: string[] = Array.isArray(p?.columns) ? p.columns : []
    const norm = (s: string) => String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '_')
    const set = new Set(cols.map(norm))
    const signals = [
      'folio_reporte',
      'fecha_reporte',
      'numero_operador',
      'origen_destino',
      'ruta_autorizada',
      'placas_tracto',
      'fecha_salida',
      'fecha_llegada',
    ]
    let hit = 0
    for (const k of signals) {
      if (set.has(k)) hit += 1
    }
    const ratio = hit / signals.length
    if (ratio >= 0.55) {
      return { name: 'Transportation Operations CSV', confidence: clamp(Math.round(70 + ratio * 30), 70, 99) }
    }
    if (ratio >= 0.3) {
      return { name: 'Transportation-like CSV', confidence: clamp(Math.round(55 + ratio * 30), 55, 85) }
    }
    return { name: 'Generic CSV', confidence: clamp(Math.round(35 + ratio * 40), 35, 70) }
  }

  const computeMetrics = (p: any) => {
    const rows = Number(p?.rows ?? 0) || 0
    const cols = Number(p?.column_count ?? (Array.isArray(p?.columns) ? p.columns.length : 0)) || 0
    const emptyCounts = p?.empty_counts || {}
    let nulls = 0
    for (const k of Object.keys(emptyCounts || {})) {
      nulls += Number(emptyCounts?.[k] ?? 0) || 0
    }
    const anomalies = Array.isArray(p?.anomalies) ? p.anomalies.length : 0
    const missing = Array.isArray(p?.missing_columns) ? p.missing_columns.length : 0
    const extra = Array.isArray(p?.extra_columns) ? p.extra_columns.length : 0
    const matched = Math.max(0, cols - extra)
    const denom = Math.max(1, cols + missing)
    const schemaMatch = clamp(Math.round((matched / denom) * 100), 0, 100)
    return { rows, columns: cols, nulls, anomalies, schemaMatch }
  }

  const computeHeatmap = (p: any) => {
    const cols: string[] = Array.isArray(p?.columns) ? p.columns : []
    const rows = Math.max(1, Number(p?.rows ?? 0) || 1)
    const empty = p?.empty_counts || {}
    const issues = p?.contract_issues || {}
    const missing: string[] = Array.isArray(p?.missing_columns) ? p.missing_columns : []

    const out = cols.map((c) => {
      const emptyN = Number(empty?.[c] ?? 0) || 0
      const invN = Number(issues?.[c]?.invalid ?? 0) || 0
      const emptyRate = emptyN / rows
      const invRate = invN / rows
      let status: 'good' | 'warn' | 'bad' = 'good'
      if (invRate > 0.2 || emptyRate > 0.5) status = 'bad'
      else if (invRate > 0.05 || emptyRate > 0.2) status = 'warn'
      const label = `${c}\nVacíos: ${emptyN} (${Math.round(emptyRate * 100)}%)\nInválidos: ${invN} (${Math.round(invRate * 100)}%)`
      return { column: c, status, emptyN, invN, label }
    })

    for (const c of missing) {
      out.unshift({ column: c, status: 'bad', emptyN: 0, invN: 0, label: `${c}\nColumna requerida faltante` })
    }
    return out
  }

  const uploadViaXhr = async (f: File) => {
    const fd = new FormData()
    fd.append('file', f)
    setProgress(0)
    return await new Promise<any>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', '/api/datasets/upload')
      xhr.setRequestHeader('Authorization', `Bearer ${token}`)
      xhr.upload.onprogress = (e) => {
        if (!e.lengthComputable) return
        setProgress(clamp(Math.round((e.loaded / e.total) * 100), 0, 100))
      }
      xhr.onload = () => {
        const ok = xhr.status >= 200 && xhr.status < 300
        if (!ok) {
          try {
            const j = JSON.parse(xhr.responseText || '{}')
            reject(new Error(j.detail || j.message || xhr.responseText || `HTTP ${xhr.status}`))
          } catch {
            reject(new Error(xhr.responseText || `HTTP ${xhr.status}`))
          }
          return
        }
        try {
          resolve(JSON.parse(xhr.responseText || '{}'))
        } catch {
          resolve(xhr.responseText)
        }
      }
      xhr.onerror = () => reject(new Error('Error de red al subir el archivo.'))
      xhr.send(fd)
    })
  }

  const upload = async () => {
    if (!file) {
      setStatus('Selecciona un CSV.')
      return
    }
    setDetected(null)
    setMetrics(null)
    setHeatmap([])
    setProfile(null)
    setPreview(null)
    setExpectations([])
    setSelectedExp({})
    setStatus('Subiendo dataset...')
    setUploading(true)
    try {
      const ds = await uploadViaXhr(file)
      setDatasets((prev) => [ds, ...prev])
      setActiveDataset(ds)
      try {
        localStorage.setItem('rd_dataset_id', String(ds.id || ''))
      } catch {
      }
      setStatus('Dataset cargado. Generando perfil...')
      try {
        const [p, pv] = await Promise.all([
          apiJson(`/api/datasets/${encodeURIComponent(ds.id)}/profile`),
          apiJson(`/api/datasets/${encodeURIComponent(ds.id)}/preview?offset=0&limit=20`),
        ])
        setProfile(p)
        setPreview(pv)
        setDetected(detectDataset(p))
        setMetrics(computeMetrics(p))
        setHeatmap(computeHeatmap(p))
        try {
          const ex = await apiJson(`/api/ai/expectations?dataset_id=${encodeURIComponent(ds.id)}`)
          const items = Array.isArray(ex) ? ex : []
          setExpectations(items)
          const next: Record<string, boolean> = {}
          for (const it of items) {
            if (String(it?.status || '').toLowerCase() === 'suggested') next[String(it.id || '')] = true
          }
          setSelectedExp(next)
        } catch {
          setExpectations([])
          setSelectedExp({})
        }
        setStatus('Listo.')
      } catch {
        setStatus('Dataset cargado.')
      }
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    } finally {
      setUploading(false)
    }
  }

  return (
    <section className="rd-grid">
      <div className="rd-card">
        <div className="rd-card-title">Subir CSV</div>
        <div
          className={dragActive ? 'rd-dropzone active' : 'rd-dropzone'}
          onDragEnter={(e) => {
            e.preventDefault()
            e.stopPropagation()
            setDragActive(true)
          }}
          onDragOver={(e) => {
            e.preventDefault()
            e.stopPropagation()
            setDragActive(true)
          }}
          onDragLeave={(e) => {
            e.preventDefault()
            e.stopPropagation()
            setDragActive(false)
          }}
          onDrop={(e) => {
            e.preventDefault()
            e.stopPropagation()
            setDragActive(false)
            const f = e.dataTransfer?.files?.[0]
            if (f) setFile(f)
          }}
        >
          <div className="rd-drop-icon">⬆</div>
          <div className="rd-drop-title">Drag & Drop tu CSV</div>
          <div className="rd-drop-sub">o selecciona un archivo</div>
          <label className="rd-drop-file">
            <input type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            Elegir archivo
          </label>
          {file ? (
            <div className="rd-drop-meta">
              <div className="mono">{file.name}</div>
              <div className="muted">{Math.max(1, Math.round(file.size / 1024))} KB</div>
            </div>
          ) : null}
          <div className="rd-actions" style={{ marginTop: 10 }}>
            <button className="rd-primary" onClick={upload} disabled={!file || uploading}>
              {uploading ? `Subiendo… ${progress}%` : 'Subir'}
            </button>
          </div>
          {uploading ? (
            <div className="rd-progress" style={{ marginTop: 10 }}>
              <div className="bar" style={{ width: `${progress}%` }} />
            </div>
          ) : null}
        </div>

        {activeDataset ? (
          <div style={{ marginTop: 14 }}>
            <div className="rd-card-title">Preview inteligente</div>
            {detected ? (
              <div className="rd-detected">
                <div>
                  <div className="rd-detected-title">Dataset detected</div>
                  <div className="rd-detected-name">{detected.name}</div>
                </div>
                <div className="rd-pill good">Confidence: {detected.confidence}%</div>
              </div>
            ) : null}

            {metrics ? (
              <div className="rd-metrics">
                <div className="row">
                  <div className="k">filas</div>
                  <div className="v mono">{metrics.rows}</div>
                </div>
                <div className="row">
                  <div className="k">columnas</div>
                  <div className="v mono">{metrics.columns}</div>
                </div>
                <div className="row">
                  <div className="k">nulls</div>
                  <div className="v mono">{metrics.nulls}</div>
                </div>
                <div className="row">
                  <div className="k">anomalías</div>
                  <div className="v mono">{metrics.anomalies}</div>
                </div>
                <div className="row">
                  <div className="k">schema match</div>
                  <div className="v mono">{metrics.schemaMatch}%</div>
                </div>
              </div>
            ) : null}

            <div className="rd-actions" style={{ marginTop: 12 }}>
              <Link className="rd-primary" to="/app/validation">
                Ejecutar validación
              </Link>
            </div>

            {heatmap?.length ? (
              <div style={{ marginTop: 14 }}>
                <div className="rd-card-title">Heatmap de columnas</div>
                <div className="rd-heat-legend">
                  <span className="rd-dot good" /> bien
                  <span className="rd-dot warn" /> warning
                  <span className="rd-dot bad" /> crítico
                </div>
                <div className="rd-heatmap">
                  {heatmap.slice(0, 200).map((c: any) => (
                    <div key={c.column} className={`rd-col ${c.status}`} title={c.label}>
                      {String(c.column).slice(0, 22)}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {expectations?.length ? (
              <div style={{ marginTop: 14 }}>
                <div className="rd-card-title">Expectativas sugeridas (AI)</div>
                <div className="rd-table-wrap" style={{ maxHeight: 260 }}>
                  <table className="rd-table">
                    <thead>
                      <tr>
                        <th>✔</th>
                        <th>Columna</th>
                        <th>Tipo</th>
                        <th>Conf.</th>
                        <th>Estado</th>
                        <th>Razón</th>
                      </tr>
                    </thead>
                    <tbody>
                      {expectations.slice(0, 100).map((it: any) => {
                        const id = String(it.id || '')
                        const st = String(it.status || 'suggested')
                        const canPick = st.toLowerCase() === 'suggested'
                        return (
                          <tr key={id}>
                            <td>
                              <input
                                type="checkbox"
                                checked={!!selectedExp[id]}
                                disabled={!canPick}
                                onChange={(e) => setSelectedExp((prev) => ({ ...prev, [id]: e.target.checked }))}
                              />
                            </td>
                            <td className="mono">{it.column_name}</td>
                            <td className="mono">{it.expectation_type}</td>
                            <td className="mono">{it.confidence}%</td>
                            <td className="mono">{st}</td>
                            <td>{String(it.reason || '').slice(0, 120)}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="rd-actions">
                  <button
                    className="rd-primary"
                    disabled={acceptBusy}
                    onClick={async () => {
                      const ids = Object.entries(selectedExp)
                        .filter(([, v]) => v)
                        .map(([k]) => k)
                        .filter(Boolean)
                      if (!ids.length) {
                        setStatus('Selecciona al menos una expectativa.')
                        return
                      }
                      setAcceptBusy(true)
                      setStatus('Aceptando expectativas...')
                      try {
                        const res = await apiJson(`/api/ai/expectations/${encodeURIComponent(String(activeDataset.id || ''))}/accept`, {
                          method: 'POST',
                          body: JSON.stringify({ expectation_ids: ids }),
                          headers: { 'Content-Type': 'application/json' },
                        })
                        setStatus(`Listo. Reglas creadas: ${res?.created_rules ?? 0}`)
                        try {
                          const ex = await apiJson(`/api/ai/expectations?dataset_id=${encodeURIComponent(String(activeDataset.id || ''))}`)
                          setExpectations(Array.isArray(ex) ? ex : [])
                        } catch {
                        }
                      } catch (e: any) {
                        setStatus(`Error: ${e?.message || e}`)
                      } finally {
                        setAcceptBusy(false)
                      }
                    }}
                  >
                    {acceptBusy ? 'Procesando…' : 'Aceptar reglas sugeridas'}
                  </button>
                </div>
              </div>
            ) : null}

            {profile?.missing_columns?.length ? (
              <div className="rd-error" style={{ marginTop: 10 }}>
                Faltan columnas: {profile.missing_columns.join(', ')}
              </div>
            ) : null}
            {profile?.extra_columns?.length ? (
              <div className="rd-error" style={{ marginTop: 10 }}>
                Columnas extra: {profile.extra_columns.join(', ')}
              </div>
            ) : null}

            {profile?.inferred_types ? (
              <div style={{ marginTop: 12 }}>
                <div className="rd-card-title">Tipos detectados (muestra)</div>
                <div className="rd-table-wrap" style={{ maxHeight: 260 }}>
                  <table className="rd-table">
                    <thead>
                      <tr>
                        <th>Columna</th>
                        <th>Tipo</th>
                        <th>Vacíos</th>
                        <th>Únicos</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.keys(profile.inferred_types)
                        .slice(0, 30)
                        .map((c: string) => (
                          <tr key={c}>
                            <td className="mono">{c}</td>
                            <td className="mono">{String(profile.inferred_types?.[c] ?? '')}</td>
                            <td className="mono">{String(profile.empty_counts?.[c] ?? '')}</td>
                            <td className="mono">{String(profile.unique_counts?.[c] ?? '')}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="rd-card">
        <div className="rd-card-title">Preview / Contrato</div>
        {preview?.rows?.length ? (
          <div className="rd-table-wrap" style={{ maxHeight: 260 }}>
            <table className="rd-table">
              <thead>
                <tr>
                  {(preview.columns || []).slice(0, 8).map((c: string) => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(preview.rows || []).slice(0, 10).map((r: any, idx: number) => (
                  <tr key={idx}>
                    {(preview.columns || []).slice(0, 8).map((c: string) => (
                      <td key={c} className="mono">
                        {String(r?.[c] ?? '').slice(0, 30)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="muted">Sube un dataset para ver preview.</div>
        )}

        {profile?.anomalies?.length ? (
          <div style={{ marginTop: 12 }}>
            <div className="rd-card-title">Anomalías detectadas (muestra)</div>
            <div className="rd-table-wrap" style={{ maxHeight: 260 }}>
              <table className="rd-table">
                <thead>
                  <tr>
                    <th>Columna</th>
                    <th>Fila</th>
                    <th>Valor</th>
                    <th>Motivo</th>
                    <th>Sev.</th>
                  </tr>
                </thead>
                <tbody>
                  {profile.anomalies.slice(0, 50).map((a: any, idx: number) => (
                    <tr key={idx}>
                      <td className="mono">{a.column}</td>
                      <td className="mono">{a.row_index}</td>
                      <td className="mono">{String(a.value || '').slice(0, 60)}</td>
                      <td>{a.reason}</td>
                      <td>{a.severity}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        <div className="rd-card-title" style={{ marginTop: 14 }}>
          Historial de datasets
        </div>
        <div className="rd-table-wrap">
          <table className="rd-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Nombre</th>
                <th>Registros</th>
                <th>Score</th>
                <th>Fecha</th>
              </tr>
            </thead>
            <tbody>
              {datasets.slice(0, 50).map((d) => (
                <tr key={d.id}>
                  <td className="mono">{String(d.id).slice(0, 8)}</td>
                  <td>{d.name}</td>
                  <td>{d.records}</td>
                  <td className="mono">{d.quality_score ?? 0}</td>
                  <td>
                    {d.date} {d.time}
                  </td>
                </tr>
              ))}
              {!datasets.length ? (
                <tr>
                  <td colSpan={5} className="muted">
                    Sin datasets
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <div className="rd-actions">
          <button className="rd-secondary" onClick={refresh}>
            Actualizar
          </button>
        </div>
      </div>
    </section>
  )
}

function ValidationPage({ token, setStatus }: { token: string; setStatus: (s: string) => void }) {
  const navigate = useNavigate()
  const { apiJson, apiFetch } = useApi(token)
  const [datasets, setDatasets] = useState<any[]>([])
  const [rules, setRules] = useState<any[]>([])
  const [datasetId, setDatasetId] = useState('')
  const [datasetCols, setDatasetCols] = useState<string[]>([])
  const [selectedRuleIds, setSelectedRuleIds] = useState<Record<string, boolean>>({})
  const [lastRun, setLastRun] = useState<any | null>(null)
  const [busy, setBusy] = useState(false)
  const [ruleQ, setRuleQ] = useState('')
  const [history, setHistory] = useState<any[]>([])

  const [mappingRequired, setMappingRequired] = useState('Folio_reporte')
  const [mappingDates, setMappingDates] = useState('Fecha_reporte')
  const [mappingConductor, setMappingConductor] = useState('Numero_operador')
  const [mappingCartaPorte, setMappingCartaPorte] = useState('')
  const [mappingCliente, setMappingCliente] = useState('')
  const [mappingFecha, setMappingFecha] = useState('')
  const [mappingDireccion, setMappingDireccion] = useState('')
  const [mappingEmpleado, setMappingEmpleado] = useState('')
  const [mappingPlacas, setMappingPlacas] = useState('')
  const [mappingPlacasRegex, setMappingPlacasRegex] = useState('')
  const [mappingPeso, setMappingPeso] = useState('')
  const [mappingFechaSalida, setMappingFechaSalida] = useState('')
  const [mappingFechaLlegada, setMappingFechaLlegada] = useState('')

  const selected = useMemo(() => Object.entries(selectedRuleIds).filter(([, v]) => v).map(([k]) => k), [selectedRuleIds])
  const filteredRules = useMemo(() => {
    const q = ruleQ.trim().toLowerCase()
    if (!q) return rules
    return rules.filter((r) => String(r?.id || '').toLowerCase().includes(q) || String(r?.name || '').toLowerCase().includes(q))
  }, [rules, ruleQ])

  const refresh = async () => {
    setStatus('Cargando configuración...')
    setBusy(true)
    try {
      const [ds, rs] = await Promise.all([apiJson('/api/datasets?offset=0&limit=500'), apiJson('/api/rules')])
      const dsItems = Array.isArray((ds as any)?.items) ? (ds as any).items : Array.isArray(ds) ? ds : []
      setDatasets(dsItems)
      setRules(Array.isArray(rs) ? rs : [])
      if (!Object.keys(selectedRuleIds).length && Array.isArray(rs) && rs.length) {
        const defaults = ['contrato_csv_viajes', 'reglas_negocio_viajes', 'campos_obligatorios_no_nulos']
        const next: Record<string, boolean> = {}
        for (const id of defaults) {
          if (rs.find((r: any) => r?.id === id && r?.active !== false)) {
            next[id] = true
          }
        }
        setSelectedRuleIds(next)
      }
      if (!datasetId && Array.isArray(dsItems) && dsItems.length) {
        let preferred = ''
        try {
          preferred = String(localStorage.getItem('rd_dataset_id') || '')
        } catch {
          preferred = ''
        }
        const found = preferred ? dsItems.find((d: any) => d?.id === preferred) : null
        setDatasetId(found?.id || dsItems[0].id)
      }
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    } finally {
      setBusy(false)
    }
  }

  const refreshHistory = async (did: string) => {
    const id = String(did || '').trim()
    if (!id) {
      setHistory([])
      return
    }
    try {
      const rs = await apiJson(`/api/runs?dataset_id=${encodeURIComponent(id)}&offset=0&limit=25`)
      const items = Array.isArray((rs as any)?.items) ? (rs as any).items : Array.isArray(rs) ? rs : []
      setHistory(items)
    } catch {
      setHistory([])
    }
  }

  const downloadPdf = async (runId: string) => {
    const rid = String(runId || '').trim()
    if (!rid) return
    setStatus('Generando PDF...')
    const res = await apiFetch(`/api/reports/${encodeURIComponent(rid)}/pdf`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Reporte_Inconsistencias_${rid.slice(0, 8)}.pdf`
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 2500)
    setStatus('PDF descargado.')
  }

  useEffect(() => {
    refresh()
  }, [])

  useEffect(() => {
    if (!datasetId) return
    try {
      localStorage.setItem('rd_dataset_id', datasetId)
    } catch {
    }
    refreshHistory(datasetId)
  }, [datasetId])

  useEffect(() => {
    const did = String(datasetId || '').trim()
    if (!did) {
      setDatasetCols([])
      return
    }
    ;(async () => {
      try {
        const cols = await apiJson(`/api/datasets/${encodeURIComponent(did)}/columns`)
        const arr = Array.isArray(cols) ? cols.map((x: any) => String(x || '').trim()).filter(Boolean) : []
        setDatasetCols(arr)
        const has = (v: string) => arr.includes(v)

        if (!mappingRequired || mappingRequired === 'Folio_reporte') {
          const important = arr.filter((c) => {
            const n = norm(c)
            return n.includes('folio') || n.includes('remision') || n.includes('operador') || n.includes('unidad') || n.includes('placa')
          })
          if (important.length) setMappingRequired(important.join(', '))
        }
        if (!mappingDates || mappingDates === 'Fecha_reporte') {
          const dates = arr.filter((c) => {
            const n = norm(c)
            return (n.includes('fecha') || n.includes('date')) && !n.includes('hora') && !n.includes('time')
          })
          if (dates.length) setMappingDates(dates.join(', '))
        }

        if (mappingConductor && !has(mappingConductor)) setMappingConductor('')
        if (mappingCartaPorte && !has(mappingCartaPorte)) setMappingCartaPorte('')
        if (mappingCliente && !has(mappingCliente)) setMappingCliente('')
        if (mappingFecha && !has(mappingFecha)) setMappingFecha('')
        if (mappingDireccion && !has(mappingDireccion)) setMappingDireccion('')
        if (mappingEmpleado && !has(mappingEmpleado)) setMappingEmpleado('')
        if (mappingPlacas && !has(mappingPlacas)) setMappingPlacas('')
        if (mappingPeso && !has(mappingPeso)) setMappingPeso('')
        if (mappingFechaSalida && !has(mappingFechaSalida)) setMappingFechaSalida('')
        if (mappingFechaLlegada && !has(mappingFechaLlegada)) setMappingFechaLlegada('')

        const norm = (s: string) =>
          String(s || '')
            .trim()
            .toLowerCase()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .replace(/[^a-z0-9]+/g, '_')

        const scoreCol = (col: string, want: string[], avoid: string[]) => {
          const c = norm(col)
          let score = 0
          want.forEach((w, index) => {
            const ww = norm(w)
            if (!ww) return
            const priorityBoost = (want.length - index) * 10 // Más prioridad a los primeros elementos
            if (c === ww) score += 100 + priorityBoost
            else if (c.startsWith(ww + '_') || c.endsWith('_' + ww) || c.includes('_' + ww + '_')) score += 60 + priorityBoost
            else if (c.includes(ww)) score += 20 + priorityBoost
          })
          for (const a of avoid) {
            const aa = norm(a)
            if (aa && c.includes(aa)) score -= 50
          }
          return score
        }

        const pick = (want: string[], avoid: string[] = []) => {
          let best = ''
          let bestScore = 15
          for (const c of arr) {
            const sc = scoreCol(c, want, avoid)
            if (sc > bestScore) {
              bestScore = sc
              best = c
            }
          }
          return best
        }

        if (!mappingConductor) {
          const v = pick(['Conductor', 'Operador', 'Nombre_operador', 'Numero_operador'])
          if (v) setMappingConductor(v)
        }
        if (!mappingCartaPorte) {
          const v = pick(['Carta_porte', 'CartaPorte', 'Numero_remision', 'Remision'])
          if (v) setMappingCartaPorte(v)
        }
        if (!mappingCliente) {
          const v = pick(['Cliente', 'Remitente_cliente', 'Destinatario_cliente'])
          if (v) setMappingCliente(v)
        }
        if (!mappingFecha) {
          const v = pick(['Fecha', 'Fecha_reporte'], ['Hora'])
          if (v) setMappingFecha(v)
        }
        if (!mappingDireccion) {
          const v = pick(['Direccion', 'Calle', 'Domicilio', 'Ubicacion', 'Colonia'])
          if (v) setMappingDireccion(v)
        }
        if (!mappingEmpleado) {
          const v = pick(['Numero_empleado', 'Empleado'])
          if (v) setMappingEmpleado(v)
        }

        if (!mappingPlacas) {
          const v = has('Placas_tracto') ? 'Placas_tracto' : pick(['Placas', 'Placa', 'Tracto'])
          if (v) setMappingPlacas(v)
        }
        if (!mappingPeso) {
          const v = pick(['Peso', 'Kg', 'Kilos', 'Ton', 'Tonelada'], ['Casetas', 'Hora', 'Fecha', 'Boton'])
          if (v) setMappingPeso(v)
        }
        if (!mappingFechaSalida) {
          const v = pick(['Fecha_salida', 'Salida'], ['Hora'])
          if (v) setMappingFechaSalida(v)
        }
        if (!mappingFechaLlegada) {
          const v = pick(['Fecha_llegada', 'Llegada'], ['Hora'])
          if (v) setMappingFechaLlegada(v)
        }
      } catch {
        setDatasetCols([])
      }
    })()
  }, [datasetId])

  const run = async () => {
    if (!datasetId) {
      setStatus('Selecciona un dataset.')
      return
    }
    if (!selected.length) {
      setStatus('Selecciona al menos una regla.')
      return
    }
    const hasCol = (c: string) => datasetCols.includes(c)
    const omit: string[] = []
    const keep: string[] = []
    for (const rid of selected) {
      if (rid === 'formato_placas') {
        if (!mappingPlacas || !hasCol(mappingPlacas)) {
          omit.push(rid)
          continue
        }
      }
      if (rid === 'peso_en_rango_0_35') {
        if (!mappingPeso || !hasCol(mappingPeso)) {
          omit.push(rid)
          continue
        }
      }
      if (rid === 'fecha_salida_no_futura') {
        if (!mappingFechaSalida || !hasCol(mappingFechaSalida)) {
          omit.push(rid)
          continue
        }
      }
      if (rid === 'logica_fechas_llegada_no_menor_salida') {
        if (!mappingFechaSalida || !hasCol(mappingFechaSalida) || !mappingFechaLlegada || !hasCol(mappingFechaLlegada)) {
          omit.push(rid)
          continue
        }
      }
      keep.push(rid)
    }
    const uniqueOmit = Array.from(new Set(omit))
    if (uniqueOmit.length) {
      setSelectedRuleIds((prev) => {
        const next = { ...prev }
        for (const r of uniqueOmit) next[r] = false
        return next
      })
      if (!keep.length) {
        setStatus(`Se omitieron reglas por falta de mapeo/columnas: ${uniqueOmit.join(', ')}`)
        return
      }
      setStatus(`Se omitieron reglas por mapeo: ${uniqueOmit.join(', ')}. Ejecutando el resto…`)
    }
    const phases = ['Schema check', 'Contract validation', 'Business rules', 'Drift analysis', 'AI insights', 'Report generation']
    let phaseIdx = 0
    setStatus(`Ejecutando validación… (${phases[phaseIdx]})`)
    setBusy(true)
    let t: any = null
    try {
      t = setInterval(() => {
        phaseIdx = (phaseIdx + 1) % phases.length
        setStatus(`Ejecutando validación… (${phases[phaseIdx]})`)
      }, 900)
    } catch {
    }
    try {
      const mapping = {
        required_columns: mappingRequired
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        date_columns: mappingDates
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        conductor_col: mappingConductor || null,
        carta_porte_col: mappingCartaPorte || null,
        cliente_col: mappingCliente || null,
        fecha_col: mappingFecha || null,
        direccion_col: mappingDireccion || null,
        empleado_col: mappingEmpleado || null,
        placas_col: mappingPlacas || null,
        placas_regex: mappingPlacasRegex || null,
        peso_col: mappingPeso || null,
        fecha_salida_col: mappingFechaSalida || null,
        fecha_llegada_col: mappingFechaLlegada || null,
      }
      const run = await apiJson(`/api/runs/${encodeURIComponent(datasetId)}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rule_ids: keep.length ? keep : selected, mapping }),
      })
      const runId = String(run.id || '')
      setLastRun(run)
      try {
        localStorage.setItem('rd_last_run', JSON.stringify(run))
      } catch {
      }
      setStatus(`Listo. Score: ${run.quality_score ?? 0}/100 · Inconsistencias: ${run.inconsistencies ?? 0}`)
      try {
        await downloadPdf(runId)
      } catch (e: any) {
        setStatus(`Validación OK, pero no se pudo descargar PDF: ${e?.message || e}`)
      }
      refreshHistory(datasetId)
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    } finally {
      try {
        if (t) clearInterval(t)
      } catch {
      }
      setBusy(false)
    }
  }

  return (
    <section className="rd-grid">
      <div className="rd-card">
        <div className="rd-card-title">Dataset</div>
        <div className="rd-form">
          <label>
            Selecciona dataset
            <select value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
              <option value="">Seleccionar</option>
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {String(d.id).slice(0, 8)} - {d.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {lastRun ? (
          <div style={{ marginTop: 14 }}>
            <div className="rd-card-title">Resultado</div>
            <div className="rd-sev">
              <div>Run: {String(lastRun.id || '').slice(0, 8)}</div>
              <div>Score: {lastRun.quality_score ?? 0}/100</div>
              <div>Registros: {lastRun.total_records ?? 0}</div>
              <div>Inconsistencias: {lastRun.inconsistencies ?? 0}</div>
              <div>Reglas aplicadas: {(lastRun.rules_applied || []).length}</div>
              <div>Reglas OK: {(lastRun.rules_passed || []).length}</div>
              <div>Reglas fallidas: {(lastRun.rules_failed || []).length}</div>
            </div>
            <div className="rd-actions" style={{ marginTop: 10 }}>
              <button className="rd-secondary" onClick={() => navigate(`/app/findings?run_id=${encodeURIComponent(String(lastRun.id || ''))}`)}>
                Ver hallazgos
              </button>
              <button className="rd-primary" onClick={() => downloadPdf(String(lastRun.id || ''))}>
                Descargar PDF
              </button>
            </div>
          </div>
        ) : null}

        <details style={{ marginTop: 14 }}>
          <summary className="rd-card-title">Mapeo (avanzado)</summary>
          <div className="rd-form rd-form-2" style={{ marginTop: 10 }}>
            <label>
              Obligatorias (coma)
              <input value={mappingRequired} onChange={(e) => setMappingRequired(e.target.value)} />
            </label>
            <label>
              Fechas (coma)
              <input value={mappingDates} onChange={(e) => setMappingDates(e.target.value)} />
            </label>
            <label>
              Conductor
              <input value={mappingConductor} onChange={(e) => setMappingConductor(e.target.value)} />
            </label>
            <label>
              Carta porte
              <input value={mappingCartaPorte} onChange={(e) => setMappingCartaPorte(e.target.value)} />
            </label>
            <label>
              Cliente
              <input value={mappingCliente} onChange={(e) => setMappingCliente(e.target.value)} />
            </label>
            <label>
              Fecha (dup)
              <input value={mappingFecha} onChange={(e) => setMappingFecha(e.target.value)} />
            </label>
            <label>
              Dirección (dup)
              <input value={mappingDireccion} onChange={(e) => setMappingDireccion(e.target.value)} />
            </label>
            <label>
              Empleado
              <input value={mappingEmpleado} onChange={(e) => setMappingEmpleado(e.target.value)} />
            </label>
            <label>
              Placas
              <input value={mappingPlacas} onChange={(e) => setMappingPlacas(e.target.value)} />
            </label>
            <label>
              Regex placas
              <input value={mappingPlacasRegex} onChange={(e) => setMappingPlacasRegex(e.target.value)} />
            </label>
            <label>
              Peso
              <input value={mappingPeso} onChange={(e) => setMappingPeso(e.target.value)} />
            </label>
            <label>
              Fecha salida
              <input value={mappingFechaSalida} onChange={(e) => setMappingFechaSalida(e.target.value)} />
            </label>
            <label>
              Fecha llegada
              <input value={mappingFechaLlegada} onChange={(e) => setMappingFechaLlegada(e.target.value)} />
            </label>
          </div>
        </details>

        <div className="rd-card-title" style={{ marginTop: 14 }}>
          Historial (últimas 25)
        </div>
        <div className="rd-table-wrap" style={{ maxHeight: 260 }}>
          <table className="rd-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Fecha</th>
                <th>Incons.</th>
                <th>Score</th>
                <th>Acción</th>
              </tr>
            </thead>
            <tbody>
              {history.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{String(r.id).slice(0, 8)}</td>
                  <td>
                    {r.date} {r.time}
                  </td>
                  <td className="mono">{r.inconsistencies}</td>
                  <td className="mono">{r.quality_score ?? ''}</td>
                  <td>
                    <div className="rd-actions">
                      <button className="rd-secondary" onClick={() => navigate(`/app/findings?run_id=${encodeURIComponent(String(r.id || ''))}`)}>
                        Hallazgos
                      </button>
                      <button className="rd-secondary" onClick={() => downloadPdf(String(r.id || ''))}>
                        PDF
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!history.length ? (
                <tr>
                  <td colSpan={5} className="muted">
                    Sin validaciones
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rd-card">
        <div className="rd-row">
          <div className="rd-card-title">Reglas</div>
          <div className="rd-actions">
            <button
              className="rd-secondary"
              onClick={() => {
                const next: Record<string, boolean> = {}
                for (const r of rules) {
                  if (r?.active !== false) next[String(r.id)] = true
                }
                setSelectedRuleIds(next)
              }}
            >
              Seleccionar todas
            </button>
            <button className="rd-secondary" onClick={() => setSelectedRuleIds({})}>
              Limpiar
            </button>
          </div>
        </div>
        <div className="rd-form rd-inline">
          <label>
            Buscar regla
            <input value={ruleQ} onChange={(e) => setRuleQ(e.target.value)} placeholder="ID o nombre" />
          </label>
        </div>
        <div className="rd-rules">
          {filteredRules.map((r) => (
            <label key={r.id} className="rd-check">
              <input
                type="checkbox"
                checked={!!selectedRuleIds[r.id]}
                onChange={(e) => setSelectedRuleIds((prev) => ({ ...prev, [r.id]: e.target.checked }))}
              />
              <span className="name">{r.name}</span>
              <span className="meta">
                {r.id} · {r.severity} · {r.active ? 'Activa' : 'Inactiva'}
              </span>
            </label>
          ))}
          {!filteredRules.length ? <div className="muted">Sin reglas</div> : null}
        </div>
        <div className="rd-actions">
          <button className="rd-secondary" onClick={refresh} disabled={busy}>
            Recargar
          </button>
          <button className="rd-primary" onClick={run} disabled={busy}>
            {busy ? 'Ejecutando…' : 'Ejecutar'}
          </button>
        </div>
      </div>
    </section>
  )
}

function FindingsPage({ token, setStatus }: { token: string; setStatus: (s: string) => void }) {
  const { apiJson } = useApi(token)
  const [search] = useSearchParams()
  const [runs, setRuns] = useState<any[]>([])
  const [runId, setRunId] = useState('')
  const [items, setItems] = useState<any[]>([])
  const [grouped, setGrouped] = useState<any[]>([])
  const [groupMode, setGroupMode] = useState(true)
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [limit, setLimit] = useState(200)
  const [preview, setPreview] = useState<any | null>(null)
  const [aiExplain, setAiExplain] = useState<any | null>(null)
  const [ruleBusy, setRuleBusy] = useState(false)

  const refreshRuns = async () => {
    try {
      const rs = await apiJson('/api/runs?offset=0&limit=500')
      const items = Array.isArray((rs as any)?.items) ? (rs as any).items : Array.isArray(rs) ? rs : []
      setRuns(items)
    } catch {
      setRuns([])
    }
  }

  const load = async (newOffset: number) => {
    if (!runId) {
      setStatus('Selecciona un run.')
      return
    }
    setStatus('Cargando hallazgos...')
    try {
      const res = await apiJson(`/api/findings?run_id=${encodeURIComponent(runId)}&offset=${newOffset}&limit=${limit}`)
      setItems(res.items || [])
      setTotal(res.total || 0)
      setOffset(newOffset)
      setGrouped([])
      setAiExplain(null)
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  const loadGrouped = async () => {
    if (!runId) {
      setStatus('Selecciona un run.')
      return
    }
    setStatus('Agrupando hallazgos...')
    try {
      const res = await apiJson(`/api/ai/findings/grouped?run_id=${encodeURIComponent(runId)}&limit=${Math.max(1, Math.min(1000, limit))}`)
      setGrouped(Array.isArray(res) ? res : [])
      setItems([])
      setTotal(0)
      setOffset(0)
      setPreview(null)
      setAiExplain(null)
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  const explain = async (findingId: string) => {
    const id = String(findingId || '').trim()
    if (!id) return
    setStatus('Generando explicación...')
    try {
      const res = await apiJson(`/api/ai/findings/${encodeURIComponent(id)}/explain`, { method: 'POST' })
      setAiExplain(res || null)
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  const createRule = async (findingId: string) => {
    const id = String(findingId || '').trim()
    if (!id) return
    setRuleBusy(true)
    setStatus('Creando regla...')
    try {
      const res = await apiJson(`/api/ai/findings/${encodeURIComponent(id)}/create-rule`, { method: 'POST' })
      if (res?.ok) setStatus(`Listo. Regla creada: ${String(res.rule_id || '').slice(0, 12)} (${res.expectation_type || ''})`)
      else setStatus(`No se creó regla: ${res?.message || 'No derivable'}`)
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    } finally {
      setRuleBusy(false)
    }
  }

  useEffect(() => {
    refreshRuns()
  }, [])

  useEffect(() => {
    const qRun = (search.get('run_id') || '').trim()
    if (qRun) setRunId(qRun)
  }, [search.toString()])

  const openPreview = async (f: any) => {
    const datasetId = String(f.dataset_id || '')
    const rowIndex = f.row_index
    if (!datasetId || rowIndex === null || rowIndex === undefined) return
    setStatus('Cargando preview...')
    try {
      const data = await apiJson(`/api/datasets/${encodeURIComponent(datasetId)}/row-preview?row_index=${encodeURIComponent(String(rowIndex))}`)
      setPreview(data)
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  return (
    <section className="rd-grid">
      <div className="rd-card">
        <div className="rd-card-title">Filtro</div>
        <div className="rd-form">
          <label>
            Run
            <select value={runId} onChange={(e) => setRunId(e.target.value)}>
              <option value="">Seleccionar</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {String(r.id).slice(0, 8)} - {r.dataset_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Límite
            <input
              type="number"
              value={limit}
              onChange={(e) => setLimit(Math.max(1, Math.min(2000, Number(e.target.value) || 200)))}
            />
          </label>
          <label>
            Agrupar repetidos
            <input
              type="checkbox"
              checked={groupMode}
              onChange={(e) => {
                const v = !!e.target.checked
                setGroupMode(v)
                setPreview(null)
                setAiExplain(null)
              }}
            />
          </label>
          <div className="rd-actions">
            <button className="rd-secondary" onClick={refreshRuns}>
              Recargar runs
            </button>
            <button className="rd-primary" onClick={() => (groupMode ? loadGrouped() : load(0))}>
              Cargar
            </button>
          </div>
          <div className="muted">
            {groupMode ? `Grupos: ${grouped.length}` : `Total: ${total} · Página: ${Math.floor(offset / limit) + 1}`}
          </div>
        </div>
      </div>

      <div className="rd-card">
        <div className="rd-card-title">Hallazgos</div>
        <div className="rd-table-wrap">
          {groupMode ? (
            <table className="rd-table">
              <thead>
                <tr>
                  <th>Conteo</th>
                  <th>Sev.</th>
                  <th>Regla</th>
                  <th>Campo</th>
                  <th>Tipo</th>
                  <th>Esperado</th>
                  <th>Impacto</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {grouped.map((g: any, idx: number) => (
                  <tr key={`${g.sample_finding_id || ''}_${idx}`}>
                    <td className="mono">{g.count ?? 0}</td>
                    <td>{g.worst_severity}</td>
                    <td>{g.rule_name}</td>
                    <td className="mono">{String(g.field || '').slice(0, 44)}</td>
                    <td className="mono">{g.error_type}</td>
                    <td className="mono">{String(g.expected || '').slice(0, 44)}</td>
                    <td>{String(g.business_impact || '').slice(0, 90)}</td>
                    <td>
                      <div className="rd-actions">
                        <button className="rd-secondary" onClick={() => explain(String(g.sample_finding_id || ''))}>
                          Ver explicación IA
                        </button>
                        <button className="rd-secondary" disabled={ruleBusy} onClick={() => createRule(String(g.sample_finding_id || ''))}>
                          Crear regla
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!grouped.length ? (
                  <tr>
                    <td colSpan={8} className="muted">
                      Sin hallazgos
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          ) : (
            <table className="rd-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Regla</th>
                  <th>Campo</th>
                  <th>Tipo</th>
                  <th>Valor</th>
                  <th>Esperado</th>
                  <th>Sev.</th>
                  <th>Fila</th>
                  <th>Impacto</th>
                  <th>Recomendación</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {items.map((f) => (
                  <tr key={f.id}>
                    <td className="mono">{String(f.id).slice(0, 8)}</td>
                    <td>{f.rule_name}</td>
                    <td>{f.field}</td>
                    <td className="mono">{f.error_type}</td>
                    <td className="mono">{String(f.value || '').slice(0, 50)}</td>
                    <td className="mono">{String(f.expected || '').slice(0, 50)}</td>
                    <td>{f.severity}</td>
                    <td className="mono">{f.row_index ?? ''}</td>
                    <td>{String(f.business_impact || '').slice(0, 120)}</td>
                    <td>{String(f.recommendation || '').slice(0, 120)}</td>
                    <td>
                      <div className="rd-actions">
                        <button className="rd-secondary" onClick={() => openPreview(f)}>
                          Preview
                        </button>
                        <button className="rd-secondary" onClick={() => explain(String(f.id || ''))}>
                          Ver explicación IA
                        </button>
                        <button className="rd-secondary" disabled={ruleBusy} onClick={() => createRule(String(f.id || ''))}>
                          Crear regla
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!items.length ? (
                  <tr>
                    <td colSpan={11} className="muted">
                      Sin hallazgos
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          )}
        </div>

        <div className="rd-actions">
          <button className="rd-secondary" disabled={groupMode || offset === 0} onClick={() => load(Math.max(0, offset - limit))}>
            Anterior
          </button>
          <button className="rd-secondary" disabled={groupMode || offset + limit >= total} onClick={() => load(offset + limit)}>
            Siguiente
          </button>
        </div>

        {preview ? (
          <div className="rd-card" style={{ marginTop: 12 }}>
            <div className="rd-card-title">
              Preview (fila {preview.row_index})
              <button className="rd-link" style={{ marginLeft: 10 }} onClick={() => setPreview(null)}>
                Cerrar
              </button>
            </div>
            <div className="rd-table-wrap" style={{ maxHeight: 240 }}>
              <table className="rd-table">
                <thead>
                  <tr>
                    <th>Campo</th>
                    <th>Valor</th>
                  </tr>
                </thead>
                <tbody>
                  {(preview.columns || []).map((c: string) => (
                    <tr key={c}>
                      <td className="mono">{c}</td>
                      <td className="mono">{String(preview.row?.[c] ?? '')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {aiExplain ? (
          <div className="rd-card" style={{ marginTop: 12 }}>
            <div className="rd-card-title">
              Explicación IA
              <button className="rd-link" style={{ marginLeft: 10 }} onClick={() => setAiExplain(null)}>
                Cerrar
              </button>
            </div>
            <div className="rd-error" style={{ marginTop: 10, background: 'rgba(96,165,250,0.08)', borderColor: 'rgba(96,165,250,0.25)' }}>
              {String(aiExplain.explanation || '')}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  )
}

function RecommendationsPage({ token, setStatus }: { token: string; setStatus: (s: string) => void }) {
  const { apiJson, apiFetch } = useApi(token)
  const [runs, setRuns] = useState<any[]>([])
  const [runId, setRunId] = useState('')
  const [items, setItems] = useState<any[]>([])
  const [autoFixes, setAutoFixes] = useState<any[]>([])
  const [autoFixSel, setAutoFixSel] = useState<Record<string, boolean>>({})
  const [autoFixBusy, setAutoFixBusy] = useState(false)
  const [aiExpectationRules, setAiExpectationRules] = useState<any[]>([])
  const [busy, setBusy] = useState(false)
  const [q, setQ] = useState('')

  const refreshRuns = async () => {
    try {
      const rs = await apiJson('/api/runs?offset=0&limit=500')
      const items = Array.isArray((rs as any)?.items) ? (rs as any).items : Array.isArray(rs) ? rs : []
      setRuns(items)
    } catch {
      setRuns([])
    }
  }

  useEffect(() => {
    refreshRuns()
  }, [])

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase()
    if (!s) return items
    return items.filter(
      (r) =>
        String(r.rule_id || '').toLowerCase().includes(s) ||
        String(r.rule_name || '').toLowerCase().includes(s) ||
        String(r.column_name || '').toLowerCase().includes(s) ||
        String(r.problem || '').toLowerCase().includes(s) ||
        String(r.recommendation || '').toLowerCase().includes(s),
    )
  }, [items, q])

  const summary = useMemo(() => {
    const isAi = !!items?.[0]?.problem
    if (isAi) {
      const counts: Record<string, number> = { Crítica: 0, Alta: 0, Media: 0, Baja: 0 }
      for (const r of items) {
        const p = String(r.priority || 'Media')
        counts[p] = (counts[p] || 0) + 1
      }
      return { mode: 'ai', total: items.length, counts }
    }
    let ok = 0
    let bad = 0
    let totalFindings = 0
    for (const r of items) {
      if (String(r.status || '').toLowerCase() === 'ok') ok += 1
      else bad += 1
      totalFindings += Number(r.findings_count ?? 0) || 0
    }
    return { mode: 'legacy', ok, bad, total: items.length, totalFindings }
  }, [items])

  const load = async () => {
    if (!runId) {
      setStatus('Selecciona un run.')
      return
    }
    setStatus('Cargando recomendaciones...')
    setBusy(true)
    try {
      let recs: any = []
      try {
        recs = await apiJson(`/api/ai/recommendations?run_id=${encodeURIComponent(runId)}`)
      } catch {
        recs = []
      }
      if (!Array.isArray(recs) || !recs.length) {
        recs = await apiJson(`/api/recommendations?run_id=${encodeURIComponent(runId)}`)
      }
      setItems(Array.isArray(recs) ? recs : [])
      try {
        const fx = await apiJson(`/api/ai/autofix?run_id=${encodeURIComponent(runId)}`)
        setAutoFixes(Array.isArray(fx) ? fx : [])
        setAutoFixSel({})
      } catch {
        setAutoFixes([])
        setAutoFixSel({})
      }
      try {
        const rules = await apiJson('/api/rules')
        const rr = Array.isArray(rules) ? rules : []
        setAiExpectationRules(rr.filter((r: any) => String(r?.type || '') === 'ai_expectation'))
      } catch {
        setAiExpectationRules([])
      }
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    } finally {
      setBusy(false)
    }
  }

  const applyAutoFixes = async () => {
    if (!runId) return
    const selectedIds = Object.keys(autoFixSel).filter((k) => autoFixSel[k])
    setAutoFixBusy(true)
    setStatus('Aplicando correcciones...')
    try {
      const res = await apiFetch(`/api/ai/autofix/${encodeURIComponent(runId)}/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ suggestion_ids: selectedIds.length ? selectedIds : null }),
      })
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ReviewData_Autofix_${String(runId).slice(0, 8)}.csv`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      try {
        const fx = await apiJson(`/api/ai/autofix?run_id=${encodeURIComponent(runId)}`)
        setAutoFixes(Array.isArray(fx) ? fx : [])
        setAutoFixSel({})
      } catch {
      }
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    } finally {
      setAutoFixBusy(false)
    }
  }

  return (
    <section className="rd-grid">
      <div className="rd-card">
        <div className="rd-card-title">Run</div>
        <div className="rd-form">
          <label>
            Selecciona run
            <select value={runId} onChange={(e) => setRunId(e.target.value)}>
              <option value="">Seleccionar</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {String(r.id).slice(0, 8)} - {r.dataset_name}
                </option>
              ))}
            </select>
          </label>
          <div className="rd-actions">
            <button className="rd-secondary" onClick={refreshRuns} disabled={busy}>
              Recargar runs
            </button>
            <button className="rd-primary" onClick={load} disabled={busy}>
              {busy ? 'Cargando…' : 'Cargar'}
            </button>
          </div>
        </div>
        <div className="rd-sev" style={{ marginTop: 10 }}>
          <div>Total: {summary.total}</div>
          {summary.mode === 'ai' ? (
            <>
              <div>Crítica: {(summary as any).counts?.['Crítica'] ?? 0}</div>
              <div>Alta: {(summary as any).counts?.['Alta'] ?? 0}</div>
              <div>Media: {(summary as any).counts?.['Media'] ?? 0}</div>
              <div>Baja: {(summary as any).counts?.['Baja'] ?? 0}</div>
            </>
          ) : (
            <>
              <div>Buenas: {(summary as any).ok}</div>
              <div>Malas: {(summary as any).bad}</div>
              <div>Inconsistencias: {(summary as any).totalFindings}</div>
            </>
          )}
        </div>
        <div className="rd-form rd-inline" style={{ marginTop: 10 }}>
          <label>
            Buscar recomendación
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Regla, texto, etc." />
          </label>
        </div>
      </div>

      <div className="rd-card">
        <div className="rd-card-title">Recomendaciones</div>
        {(() => {
          const isAi = !!filtered?.[0]?.problem
          const renderAi = (r: any) => {
            const pr = String(r.priority || 'Media')
            const pill = pr === 'Crítica' || pr === 'Alta' ? 'rd-pill bad' : 'rd-pill good'
            return (
              <div key={r.id} className={pr === 'Crítica' || pr === 'Alta' ? 'rd-rec-card bad' : 'rd-rec-card ok'}>
                <div className="rd-rec-head">
                  <div>
                    <div className="rd-rec-title">{r.column_name ? `Columna: ${r.column_name}` : 'Recomendación'}</div>
                    <div className="rd-rec-meta mono">{r.rule_id || ''}</div>
                  </div>
                  <div className={pill}>{pr}</div>
                </div>
                <div className="rd-rec-kpis">
                  <div>{r.problem}</div>
                </div>
                <div className="rd-rec-body">
                  <div className="rd-rec-label">Qué hacer</div>
                  <div className="rd-rec-text">{r.recommendation}</div>
                  {r.business_impact ? (
                    <>
                      <div className="rd-rec-label" style={{ marginTop: 10 }}>
                        Impacto de negocio
                      </div>
                      <div className="rd-rec-text">{r.business_impact}</div>
                    </>
                  ) : null}
                  <div className="rd-rec-foot">
                    <span className="mono">Auto-fix: {r.can_auto_fix ? 'Posible' : 'No'}</span>
                    <span className="mono">Fuente: AI</span>
                  </div>
                </div>
              </div>
            )
          }

          const renderLegacy = (r: any) => {
            const ok = String(r.status || '').toLowerCase() === 'ok'
            const sev = r.severity_counts || {}
            return (
              <div key={r.rule_id} className={ok ? 'rd-rec-card ok' : 'rd-rec-card bad'}>
                <div className="rd-rec-head">
                  <div>
                    <div className="rd-rec-title">{r.rule_name || r.rule_id}</div>
                    <div className="rd-rec-meta mono">{r.rule_id}</div>
                  </div>
                  <div className={ok ? 'rd-pill good' : 'rd-pill bad'}>{ok ? 'BUENO' : 'MALO'}</div>
                </div>

                <div className="rd-rec-kpis">
                  <div>Inconsistencias: {r.findings_count ?? 0}</div>
                  <div>Peor severidad: {r.worst_severity || ''}</div>
                  <div>
                    Crítica: {sev['Crítica'] ?? sev['CrÝtica'] ?? 0} · Alta: {sev['Alta'] ?? 0} · Media: {sev['Media'] ?? 0} · Baja:{' '}
                    {sev['Baja'] ?? 0}
                  </div>
                </div>

                <div className="rd-rec-body">
                  <div className="rd-rec-label">Qué hacer</div>
                  <div className="rd-rec-text">{r.recommendation || (ok ? 'Sin acciones pendientes.' : 'Revisar la inconsistencia y aplicar corrección.')}</div>
                  <div className="rd-rec-foot">
                    <span className="mono">Acción: {r.action_type || '—'}</span>
                    <span className="mono">Fuente: {r.source || '—'}</span>
                  </div>
                </div>

                {Array.isArray(r.examples) && r.examples.length ? (
                  <details className="rd-rec-details">
                    <summary>Ver ejemplos</summary>
                    <div className="rd-table-wrap" style={{ marginTop: 10 }}>
                      <table className="rd-table">
                        <thead>
                          <tr>
                            <th>Campo</th>
                            <th>Valor</th>
                            <th>Descripción</th>
                            <th>Sev.</th>
                            <th>Fila</th>
                          </tr>
                        </thead>
                        <tbody>
                          {r.examples.map((ex: any, idx: number) => (
                            <tr key={idx}>
                              <td className="mono">{String(ex.field || '').slice(0, 40)}</td>
                              <td className="mono">{String(ex.value || '').slice(0, 40)}</td>
                              <td>{String(ex.description || '').slice(0, 120)}</td>
                              <td>{ex.severity}</td>
                              <td className="mono">{ex.row_index ?? ''}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                ) : null}
              </div>
            )
          }

          if (!filtered.length) return <div className="muted">Sin recomendaciones</div>
          if (!isAi) return <div className="rd-rec-grid">{filtered.map(renderLegacy)}</div>

          const critical = filtered.filter((r: any) => String(r.priority || '') === 'Crítica' || String(r.priority || '') === 'Alta')
          const business = filtered.filter((r: any) => String(r.priority || '') === 'Media' || String(r.priority || '') === 'Baja')

          return (
            <>
              <div className="rd-card-title">Prioridad crítica</div>
              <div className="rd-rec-grid">{critical.length ? critical.map(renderAi) : <div className="muted">Sin recomendaciones críticas.</div>}</div>

              <div className="rd-card-title" style={{ marginTop: 12 }}>
                Correcciones rápidas
              </div>
              {autoFixes.length ? (
                <>
                  <div className="rd-table-wrap" style={{ maxHeight: 260 }}>
                    <table className="rd-table">
                      <thead>
                        <tr>
                          <th />
                          <th>Columna</th>
                          <th>Tipo</th>
                          <th>Conf.</th>
                          <th>Original</th>
                          <th>Corregido</th>
                        </tr>
                      </thead>
                      <tbody>
                        {autoFixes.slice(0, 250).map((f: any) => (
                          <tr key={f.id}>
                            <td>
                              <input
                                type="checkbox"
                                checked={!!autoFixSel[f.id]}
                                onChange={(e) => setAutoFixSel((prev) => ({ ...prev, [f.id]: e.target.checked }))}
                              />
                            </td>
                            <td className="mono">{String(f.column_name || '').slice(0, 40)}</td>
                            <td className="mono">{String(f.fix_type || '')}</td>
                            <td className="mono">{f.confidence ?? 0}</td>
                            <td className="mono">{String(f.original_value || '').slice(0, 34)}</td>
                            <td className="mono">{String(f.fixed_value || '').slice(0, 34)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="rd-actions" style={{ marginTop: 10 }}>
                    <button className="rd-primary" disabled={autoFixBusy} onClick={applyAutoFixes}>
                      {autoFixBusy ? 'Procesando…' : 'Aplicar y descargar CSV corregido'}
                    </button>
                    <button
                      className="rd-secondary"
                      disabled={autoFixBusy}
                      onClick={() => {
                        const next: Record<string, boolean> = {}
                        for (const x of autoFixes) next[String(x.id || '')] = true
                        setAutoFixSel(next)
                      }}
                    >
                      Seleccionar todo
                    </button>
                    <button className="rd-secondary" disabled={autoFixBusy} onClick={() => setAutoFixSel({})}>
                      Limpiar
                    </button>
                  </div>
                </>
              ) : (
                <div className="muted">Sin correcciones rápidas sugeridas para este run.</div>
              )}

              <div className="rd-card-title" style={{ marginTop: 12 }}>
                Reglas sugeridas (activas)
              </div>
              {aiExpectationRules.length ? (
                <div className="rd-table-wrap" style={{ maxHeight: 220 }}>
                  <table className="rd-table">
                    <thead>
                      <tr>
                        <th>Regla</th>
                        <th>Sev.</th>
                      </tr>
                    </thead>
                    <tbody>
                      {aiExpectationRules.slice(0, 40).map((r: any) => (
                        <tr key={r.id}>
                          <td>
                            <div>{r.name}</div>
                            <div className="mono">{String(r.id || '').slice(0, 36)}</div>
                          </td>
                          <td>{r.severity}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="muted">Sin reglas AI activas aún. Acepta expectativas sugeridas o crea reglas desde un hallazgo.</div>
              )}

              <div className="rd-card-title" style={{ marginTop: 12 }}>
                Mejoras de negocio
              </div>
              <div className="rd-rec-grid">{business.length ? business.map(renderAi) : <div className="muted">Sin recomendaciones adicionales.</div>}</div>
            </>
          )
        })()}
      </div>
    </section>
  )
}

function StatsPage({ token, setStatus }: { token: string; setStatus: (s: string) => void }) {
  const { apiJson } = useApi(token)
  const [datasets, setDatasets] = useState<any[]>([])
  const [datasetId, setDatasetId] = useState('')
  const [severity, setSeverity] = useState<Record<string, number>>({})
  const [runs, setRuns] = useState<any[]>([])
  const [overview, setOverview] = useState<any | null>(null)
  const [trends, setTrends] = useState<any | null>(null)
  const [days, setDays] = useState(30)

  const sevOrder = ['Crítica', 'Alta', 'Media', 'Baja']
  const sevColors: Record<string, string> = {
    Crítica: '#dc3545',
    Alta: '#ff9900',
    Media: '#ffc107',
    Baja: '#198754',
  }

  const sevData = useMemo<Array<{ key: string; value: number }>>(() => {
    return sevOrder.map((k) => ({ key: k, value: Number(severity?.[k] ?? severity?.[k.replace('í', 'Ý')] ?? 0) }))
  }, [severity])

  const topCols = useMemo<Array<{ label: string; value: number }>>(() => {
    const arr = Array.isArray(overview?.top_columns) ? overview.top_columns : []
    return arr.slice(0, 12).map((x: any) => ({ label: String(x?.field ?? ''), value: Number(x?.count ?? 0) }))
  }, [overview])

  const maxSev = Math.max(1, ...sevData.map((d: { value: number }) => d.value))
  const maxCol = Math.max(1, ...topCols.map((d: { value: number }) => d.value))

  const refresh = async () => {
    setStatus('Cargando estadísticas...')
    try {
      const ds = await apiJson('/api/datasets?offset=0&limit=500')
      const dsItems = Array.isArray((ds as any)?.items) ? (ds as any).items : Array.isArray(ds) ? ds : []
      setDatasets(dsItems)
      const q = datasetId ? `?dataset_id=${encodeURIComponent(datasetId)}&offset=0&limit=200` : '?offset=0&limit=200'
      const [sev, rs, ov, tr] = await Promise.all([
        apiJson(`/api/stats/severity${datasetId ? `?dataset_id=${encodeURIComponent(datasetId)}` : ''}`),
        apiJson(`/api/runs${q}`),
        apiJson(`/api/stats/overview${datasetId ? `?dataset_id=${encodeURIComponent(datasetId)}` : ''}`),
        apiJson(`/api/stats/trends?days=${encodeURIComponent(String(days))}${datasetId ? `&dataset_id=${encodeURIComponent(datasetId)}` : ''}`),
      ])
      setSeverity(sev || {})
      const runItems = Array.isArray((rs as any)?.items) ? (rs as any).items : Array.isArray(rs) ? rs : []
      setRuns(runItems)
      setOverview(ov || null)
      setTrends(tr || null)
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  return (
    <section className="rd-grid">
      <div className="rd-card">
        <div className="rd-card-title">Filtro</div>
        <div className="rd-form">
          <label>
            Dataset
            <select value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
              <option value="">Todos</option>
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {String(d.id).slice(0, 8)} - {d.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Días
            <input type="number" value={days} onChange={(e) => setDays(Math.max(1, Math.min(90, Number(e.target.value) || 30)))} />
          </label>
          <div className="rd-actions">
            <button className="rd-primary" onClick={refresh}>
              Cargar
            </button>
          </div>
        </div>

        <div className="rd-sev">
          <div>Crítica: {severity['Crítica'] ?? severity['CrÝtica'] ?? 0}</div>
          <div>Alta: {severity['Alta'] ?? 0}</div>
          <div>Media: {severity['Media'] ?? 0}</div>
          <div>Baja: {severity['Baja'] ?? 0}</div>
        </div>

        <div className="rd-chart">
          <div className="rd-card-title">Gráfica por severidad</div>
          <svg viewBox="0 0 520 170" width="100%" height="170" role="img">
            {sevData.map((d, i) => {
              const y = 20 + i * 34
              const w = Math.round((d.value / maxSev) * 360)
              const color = sevColors[d.key] || '#6c757d'
              return (
                <g key={d.key}>
                  <text x="10" y={y + 12} fill="#cbd5e1" fontSize="12">
                    {d.key}
                  </text>
                  <rect x="110" y={y} width="380" height="18" rx="6" fill="#263244" />
                  <rect x="110" y={y} width={Math.max(2, w)} height="18" rx="6" fill={color} />
                  <text x="500" y={y + 13} fill="#e5e7eb" fontSize="12" textAnchor="end">
                    {d.value}
                  </text>
                </g>
              )
            })}
          </svg>
        </div>

        {overview ? (
          <div style={{ marginTop: 12 }}>
            <div className="rd-card-title">Calidad</div>
            <div className="rd-sev">
              <div>Score promedio: {overview.avg_quality_score ?? 0}/100</div>
              <div>% reglas cumplidas: {overview.pct_rules_ok ?? 0}%</div>
            </div>
            <div className="rd-progress">
              <div className="bar" style={{ width: `${Math.max(0, Math.min(100, Number(overview.avg_quality_score ?? 0)))}%` }} />
            </div>
          </div>
        ) : null}
      </div>

      {trends ? (
        <div className="rd-card">
          <div className="rd-card-title">Tendencias ({days} días)</div>
          {(() => {
            const qt = Array.isArray(trends?.quality_trend) ? trends.quality_trend : []
            const vt = Array.isArray(trends?.valid_trend) ? trends.valid_trend : []
            const dt = Array.isArray(trends?.drift_trend) ? trends.drift_trend : []
            const maxDrift = Math.max(1, ...dt.map((x: any) => Number(x?.count ?? 0)))

            const linePoints = (arr: any[], getY: (x: any) => number) => {
              if (!arr.length) return ''
              const w = 500
              const h = 120
              return arr
                .map((p, i) => {
                  const x = 10 + (i * w) / Math.max(1, arr.length - 1)
                  const y = 10 + ((100 - clamp(getY(p), 0, 100)) * h) / 100
                  return `${x.toFixed(1)},${y.toFixed(1)}`
                })
                .join(' ')
            }

            return (
              <div className="rd-form">
                <div>
                  <div className="rd-card-title">Score histórico</div>
                  {qt.length ? (
                    <svg viewBox="0 0 520 150" width="100%" height="150" role="img">
                      <polyline points={linePoints(qt, (p) => Number(p?.avg_quality_score ?? 0))} fill="none" stroke="#60a5fa" strokeWidth="3" />
                      <polyline points="10,130 510,130" fill="none" stroke="#263244" strokeWidth="2" />
                    </svg>
                  ) : (
                    <div className="muted">Sin datos de score.</div>
                  )}
                </div>

                <div>
                  <div className="rd-card-title">Drift histórico</div>
                  {dt.length ? (
                    <svg viewBox="0 0 520 160" width="100%" height="160" role="img">
                      {dt.slice(-30).map((p: any, i: number) => {
                        const n = Number(p?.count ?? 0)
                        const barW = 12
                        const gap = 4
                        const x = 10 + i * (barW + gap)
                        const h = Math.round((n / maxDrift) * 120)
                        return <rect key={String(p?.day || i)} x={x} y={140 - h} width={barW} height={Math.max(2, h)} rx={4} fill="#ff9900" />
                      })}
                      <polyline points="10,140 510,140" fill="none" stroke="#263244" strokeWidth="2" />
                    </svg>
                  ) : (
                    <div className="muted">Sin datos de drift.</div>
                  )}
                </div>

                <div>
                  <div className="rd-card-title">% registros válidos</div>
                  {vt.length ? (
                    <svg viewBox="0 0 520 150" width="100%" height="150" role="img">
                      <polyline points={linePoints(vt, (p) => Number(p?.valid_pct ?? 0))} fill="none" stroke="#22c55e" strokeWidth="3" />
                      <polyline points="10,130 510,130" fill="none" stroke="#263244" strokeWidth="2" />
                    </svg>
                  ) : (
                    <div className="muted">Sin datos de registros válidos.</div>
                  )}
                </div>
              </div>
            )
          })()}
        </div>
      ) : null}

      <div className="rd-card">
        <div className="rd-card-title">Últimas ejecuciones</div>
        <div className="rd-table-wrap">
          <table className="rd-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Fecha</th>
                <th>Incons.</th>
                <th>Score</th>
                <th>Usuario</th>
              </tr>
            </thead>
            <tbody>
              {runs.slice(0, 25).map((r) => (
                <tr key={r.id}>
                  <td className="mono">{String(r.id).slice(0, 8)}</td>
                  <td>
                    {r.date} {r.time}
                  </td>
                  <td>{r.inconsistencies}</td>
                  <td className="mono">{r.quality_score ?? ''}</td>
                  <td>{r.user_email}</td>
                </tr>
              ))}
              {!runs.length ? (
                <tr>
                  <td colSpan={5} className="muted">
                    Sin datos
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      {overview?.top_columns?.length ? (
        <div className="rd-card">
          <div className="rd-card-title">Columnas con más fallos</div>
          <div className="rd-chart" style={{ marginBottom: 10 }}>
            <svg viewBox="0 0 520 240" width="100%" height="240" role="img">
              {topCols.map((d: { label: string; value: number }, i: number) => {
                const x = 10
                const y = 18 + i * 18
                const w = Math.round((d.value / maxCol) * 360)
                return (
                  <g key={d.label + i}>
                    <text x={x} y={y + 10} fill="#cbd5e1" fontSize="10">
                      {String(d.label).slice(0, 30)}
                    </text>
                    <rect x="170" y={y} width="330" height="12" rx="5" fill="#263244" />
                    <rect x="170" y={y} width={Math.max(2, w)} height="12" rx="5" fill="#60a5fa" />
                    <text x="510" y={y + 10} fill="#e5e7eb" fontSize="10" textAnchor="end">
                      {d.value}
                    </text>
                  </g>
                )
              })}
            </svg>
          </div>
          <div className="rd-table-wrap" style={{ maxHeight: 360 }}>
            <table className="rd-table">
              <thead>
                <tr>
                  <th>Columna</th>
                  <th>Errores</th>
                </tr>
              </thead>
              <tbody>
                {overview.top_columns.map((c: any, idx: number) => (
                  <tr key={idx}>
                    <td className="mono">{c.field}</td>
                    <td className="mono">{c.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {overview?.datasets_problematic?.length ? (
        <div className="rd-card">
          <div className="rd-card-title">Datasets más problemáticos</div>
          <div className="rd-table-wrap" style={{ maxHeight: 360 }}>
            <table className="rd-table">
              <thead>
                <tr>
                  <th>Dataset</th>
                  <th>Score prom.</th>
                  <th>Incons.</th>
                </tr>
              </thead>
              <tbody>
                {overview.datasets_problematic.map((d: any) => (
                  <tr key={d.dataset_id}>
                    <td>{d.dataset_name}</td>
                    <td className="mono">{d.avg_score}</td>
                    <td className="mono">{d.total_inconsistencies}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  )
}

function DatasetHistoryPage({ token, setStatus }: { token: string; setStatus: (s: string) => void }) {
  const { apiJson } = useApi(token)
  const [datasets, setDatasets] = useState<any[]>([])
  const [q, setQ] = useState('')
  const [search] = useSearchParams()

  const refresh = async () => {
    setStatus('Cargando datasets...')
    try {
      const ds = await apiJson('/api/datasets?offset=0&limit=2000')
      const items = Array.isArray((ds as any)?.items) ? (ds as any).items : Array.isArray(ds) ? ds : []
      setDatasets(items)
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  useEffect(() => {
    const v = String(search.get('q') || '').trim()
    if (!v) return
    setQ(v)
  }, [search.toString()])

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase()
    if (!s) return datasets
    return datasets.filter((d) => String(d.name || '').toLowerCase().includes(s) || String(d.id || '').toLowerCase().includes(s))
  }, [datasets, q])

  return (
    <section className="rd-card">
      <div className="rd-row">
        <div className="rd-card-title">Historial de Datasets</div>
        <div className="rd-actions">
          <button className="rd-secondary" onClick={refresh}>
            Actualizar
          </button>
        </div>
      </div>
      <div className="rd-form rd-inline">
        <label>
          Buscar
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nombre o ID" />
        </label>
      </div>
      <div className="rd-table-wrap" style={{ marginTop: 12 }}>
        <table className="rd-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Nombre</th>
              <th>Registros</th>
              <th>Folios</th>
              <th>Estado</th>
              <th>Fecha</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((d) => (
              <tr key={d.id}>
                <td className="mono">{String(d.id).slice(0, 8)}</td>
                <td>{d.name}</td>
                <td>{d.records}</td>
                <td>{d.folios}</td>
                <td>{d.status}</td>
                <td>
                  {d.date} {d.time}
                </td>
              </tr>
            ))}
            {!filtered.length ? (
              <tr>
                <td colSpan={6} className="muted">
                  Sin resultados
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function ReportHistoryPage({ token, setStatus }: { token: string; setStatus: (s: string) => void }) {
  const { apiJson, apiFetch } = useApi(token)
  const [reports, setReports] = useState<any[]>([])
  const [q, setQ] = useState('')
  const [openRunId, setOpenRunId] = useState<string>('')
  const [pdfUrls, setPdfUrls] = useState<Record<string, string>>({})
  const pdfUrlRef = useRef<Record<string, string>>({})

  const refresh = async () => {
    setStatus('Cargando reportes...')
    try {
      const rs = await apiJson('/api/reports?offset=0&limit=2000')
      const items = Array.isArray((rs as any)?.items) ? (rs as any).items : Array.isArray(rs) ? rs : []
      setReports(items)
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  useEffect(() => {
    return () => {
      for (const k of Object.keys(pdfUrlRef.current || {})) {
        try {
          URL.revokeObjectURL(pdfUrlRef.current[k])
        } catch {
        }
      }
    }
  }, [])

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase()
    if (!s) return reports
    return reports.filter((r) => String(r.id || '').toLowerCase().includes(s) || String(r.run_id || '').toLowerCase().includes(s))
  }, [reports, q])

  const ensurePdfUrl = async (runId: string) => {
    const id = String(runId || '').trim()
    if (!id) return
    if (pdfUrls[id]) return
    setStatus('Cargando preview PDF...')
    try {
      const res = await apiFetch(`/api/reports/${encodeURIComponent(id)}/pdf`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      pdfUrlRef.current = { ...(pdfUrlRef.current || {}), [id]: url }
      setPdfUrls((prev) => ({ ...prev, [id]: url }))
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  const download = async (runId: string) => {
    try {
      setStatus('Generando PDF...')
      const res = await apiFetch(`/api/reports/${encodeURIComponent(runId)}/pdf`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank', 'noopener,noreferrer')
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  return (
    <section className="rd-card">
      <div className="rd-row">
        <div className="rd-card-title">Historial de Reportes</div>
        <div className="rd-actions">
          <button className="rd-secondary" onClick={refresh}>
            Actualizar
          </button>
        </div>
      </div>
      <div className="rd-form rd-inline">
        <label>
          Buscar
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="ID reporte o run" />
        </label>
      </div>
      <div className="rd-table-wrap" style={{ marginTop: 12 }}>
        <table className="rd-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Run</th>
              <th>Dataset</th>
              <th>Generado</th>
              <th>Acción</th>
            </tr>
          </thead>
          <tbody>
            {filtered.flatMap((r) => {
              const rid = String(r.run_id || '').trim()
              const open = rid && openRunId === rid
              const base = (
                <tr key={r.id}>
                  <td className="mono">{String(r.id).slice(0, 8)}</td>
                  <td className="mono">{String(r.run_id).slice(0, 8)}</td>
                  <td>{r.dataset_name}</td>
                  <td className="mono">{String(r.generated_at || '').slice(0, 19)}</td>
                  <td>
                    <div className="rd-actions" style={{ marginTop: 0 }}>
                      <button
                        className="rd-secondary"
                        onClick={async () => {
                          if (!rid) return
                          if (open) {
                            setOpenRunId('')
                            return
                          }
                          setOpenRunId(rid)
                          await ensurePdfUrl(rid)
                        }}
                      >
                        {open ? 'Cerrar preview' : 'Preview'}
                      </button>
                      <button className="rd-primary" onClick={() => download(rid)}>
                        Abrir PDF
                      </button>
                    </div>
                  </td>
                </tr>
              )
              if (!open) return [base]
              return [
                base,
                <tr key={`${r.id}_p`}>
                  <td colSpan={5}>
                    <div className="rd-pdf-preview">
                      {pdfUrls[rid] ? <iframe className="rd-pdf-thumb" src={pdfUrls[rid]} title={`PDF ${rid}`} /> : <div className="muted">Cargando preview…</div>}
                    </div>
                  </td>
                </tr>,
              ]
            })}
            {!filtered.length ? (
              <tr>
                <td colSpan={5} className="muted">
                  Sin reportes
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function AdminDashboardPage({ token, setStatus }: { token: string; setStatus: (s: string) => void }) {
  const { apiJson } = useApi(token)
  const [summary, setSummary] = useState<any | null>(null)

  const refresh = async () => {
    setStatus('Cargando panel admin...')
    try {
      const s = await apiJson('/api/admin/summary')
      setSummary(s)
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  return (
    <section className="rd-card">
      <div className="rd-row">
        <div className="rd-card-title">Panel de Administrador</div>
        <button className="rd-secondary" onClick={refresh}>
          Actualizar
        </button>
      </div>
      <div className="rd-kpis">
        <div className="rd-kpi">
          <div className="label">Usuarios</div>
          <div className="value">{summary?.users ?? 0}</div>
        </div>
        <div className="rd-kpi">
          <div className="label">Datasets</div>
          <div className="value">{summary?.datasets ?? 0}</div>
        </div>
        <div className="rd-kpi">
          <div className="label">Validaciones</div>
          <div className="value">{summary?.validations ?? 0}</div>
        </div>
        <div className="rd-kpi">
          <div className="label">Reportes</div>
          <div className="value">{summary?.reports ?? 0}</div>
        </div>
      </div>
    </section>
  )
}

function AdminActivityPage({ token, setStatus }: { token: string; setStatus: (s: string) => void }) {
  const { apiJson } = useApi(token)
  const [items, setItems] = useState<any[]>([])

  const refresh = async () => {
    setStatus('Cargando bitácora...')
    try {
      const rows = await apiJson('/api/admin/activity?limit=200')
      setItems(Array.isArray(rows) ? rows : [])
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  return (
    <section className="rd-card">
      <div className="rd-row">
        <div className="rd-card-title">Bitácora</div>
        <button className="rd-secondary" onClick={refresh}>
          Actualizar
        </button>
      </div>
      <div className="rd-table-wrap">
        <table className="rd-table">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Usuario</th>
              <th>Módulo</th>
              <th>Acción</th>
              <th>Detalle</th>
            </tr>
          </thead>
          <tbody>
            {items.map((a, idx) => (
              <tr key={idx}>
                <td className="mono">{String(a.created_at || '').slice(0, 19)}</td>
                <td>{a.user_email}</td>
                <td>{a.module}</td>
                <td>{a.action}</td>
                <td>{a.description}</td>
              </tr>
            ))}
            {!items.length ? (
              <tr>
                <td colSpan={5} className="muted">
                  Sin actividad
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function AdminUsersPage({ token, setStatus }: { token: string; setStatus: (s: string) => void }) {
  const { apiJson } = useApi(token)
  const [users, setUsers] = useState<any[]>([])
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<'admin' | 'user'>('user')
  const [attempted, setAttempted] = useState(false)

  const emailErr = useMemo(() => validateEmailInput(email), [email])
  const passwordErr = useMemo(() => validatePasswordInput(password), [password])

  const refresh = async () => {
    setStatus('Cargando usuarios...')
    try {
      const rows = await apiJson('/api/admin/users')
      setUsers(Array.isArray(rows) ? rows : [])
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const create = async () => {
    setAttempted(true)
    const eErr = validateEmailInput(email)
    const pErr = validatePasswordInput(password)
    if (eErr || pErr) {
      setStatus(`Error: ${eErr || pErr}`)
      return
    }
    const cleanEmail = String(email || '').trim()
    setStatus('Creando usuario...')
    try {
      await apiJson('/api/admin/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: cleanEmail, password, role, active: true }),
      })
      setEmail('')
      setPassword('')
      await refresh()
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  const setActive = async (userId: string, active: boolean) => {
    setStatus('Actualizando usuario...')
    try {
      await apiJson(`/api/admin/users/${encodeURIComponent(userId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active }),
      })
      await refresh()
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  const setUserRole = async (userId: string, role: string) => {
    setStatus('Actualizando rol...')
    try {
      await apiJson(`/api/admin/users/${encodeURIComponent(userId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role }),
      })
      await refresh()
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  const resetPassword = async (userId: string) => {
    const newPass = prompt('Nueva contraseña:')
    if (!newPass) return
    const pErr = validatePasswordInput(newPass)
    if (pErr) {
      setStatus(`Error: ${pErr}`)
      return
    }
    setStatus('Reseteando contraseña...')
    try {
      await apiJson(`/api/admin/users/${encodeURIComponent(userId)}/password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: newPass }),
      })
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  const remove = async (userId: string) => {
    if (!confirm('¿Eliminar usuario?')) return
    setStatus('Eliminando...')
    try {
      await apiJson(`/api/admin/users/${encodeURIComponent(userId)}`, { method: 'DELETE' })
      await refresh()
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  return (
    <section className="rd-grid">
      <div className="rd-card">
        <div className="rd-card-title">Crear usuario</div>
        <div className="rd-form">
          <label>
            Email
            <input value={email} onChange={(e) => setEmail(e.target.value)} />
            {attempted && emailErr ? <div className="rd-error">{emailErr}</div> : null}
          </label>
          <label>
            Contraseña
            <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" />
            {attempted && passwordErr ? <div className="rd-error">{passwordErr}</div> : null}
            <div className="muted">10–64 chars · 1 letra · 1 número · sin espacios · ASCII imprimible</div>
          </label>
          <label>
            Rol
            <select value={role} onChange={(e) => setRole(e.target.value as any)}>
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
          </label>
          <button className="rd-primary" onClick={create}>
            Crear
          </button>
        </div>
      </div>

      <div className="rd-card">
        <div className="rd-row">
          <div className="rd-card-title">Usuarios</div>
          <button className="rd-secondary" onClick={refresh}>
            Actualizar
          </button>
        </div>
        <div className="rd-table-wrap">
          <table className="rd-table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Rol</th>
                <th>Activo</th>
                <th>Acción</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}</td>
                  <td>
                    <select value={u.role} onChange={(e) => setUserRole(u.id, e.target.value)}>
                      <option value="user">user</option>
                      <option value="admin">admin</option>
                    </select>
                  </td>
                  <td className="mono">{u.active ? 'true' : 'false'}</td>
                  <td>
                    <div className="rd-actions">
                      <button className="rd-secondary" onClick={() => setActive(u.id, !u.active)}>
                        {u.active ? 'Desactivar' : 'Activar'}
                      </button>
                      <button className="rd-secondary" onClick={() => resetPassword(u.id)}>
                        Reset pass
                      </button>
                      <button className="rd-danger" onClick={() => remove(u.id)}>
                        Eliminar
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!users.length ? (
                <tr>
                  <td colSpan={4} className="muted">
                    Sin usuarios
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}

function AdminRulesPage({ token, setStatus }: { token: string; setStatus: (s: string) => void }) {
  const { apiJson } = useApi(token)
  const [rules, setRules] = useState<any[]>([])
  const [rid, setRid] = useState('')
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [rtype, setRtype] = useState('')
  const [sev, setSev] = useState('Alta')
  const [active, setActive] = useState(true)

  const refresh = async () => {
    setStatus('Cargando reglas...')
    try {
      const rs = await apiJson('/api/rules')
      setRules(Array.isArray(rs) ? rs : [])
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const create = async () => {
    setStatus('Guardando regla...')
    try {
      await apiJson('/api/admin/rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rule_id: rid, name, description: desc, rule_type: rtype, severity: sev, active }),
      })
      setRid('')
      setName('')
      setDesc('')
      setRtype('')
      setSev('Alta')
      setActive(true)
      await refresh()
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  const toggle = async (ruleId: string, active: boolean) => {
    setStatus('Actualizando regla...')
    try {
      await apiJson(`/api/admin/rules/${encodeURIComponent(ruleId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active }),
      })
      await refresh()
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  return (
    <section className="rd-grid">
      <div className="rd-card">
        <div className="rd-card-title">Crear/Actualizar regla</div>
        <div className="rd-form">
          <label>
            ID
            <input value={rid} onChange={(e) => setRid(e.target.value)} placeholder="R001" />
          </label>
          <label>
            Nombre
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            Descripción
            <input value={desc} onChange={(e) => setDesc(e.target.value)} />
          </label>
          <label>
            Tipo
            <input value={rtype} onChange={(e) => setRtype(e.target.value)} placeholder="formato/rango/logica/..." />
          </label>
          <label>
            Severidad
            <select value={sev} onChange={(e) => setSev(e.target.value)}>
              <option value="Crítica">Crítica</option>
              <option value="Alta">Alta</option>
              <option value="Media">Media</option>
              <option value="Baja">Baja</option>
            </select>
          </label>
          <label>
            Activa
            <select value={active ? '1' : '0'} onChange={(e) => setActive(e.target.value === '1')}>
              <option value="1">Sí</option>
              <option value="0">No</option>
            </select>
          </label>
          <button className="rd-primary" onClick={create}>
            Guardar
          </button>
        </div>
      </div>

      <div className="rd-card">
        <div className="rd-row">
          <div className="rd-card-title">Reglas</div>
          <button className="rd-secondary" onClick={refresh}>
            Actualizar
          </button>
        </div>
        <div className="rd-table-wrap">
          <table className="rd-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Nombre</th>
                <th>Tipo</th>
                <th>Sev.</th>
                <th>Activa</th>
                <th>Acción</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{r.id}</td>
                  <td>{r.name}</td>
                  <td className="mono">{r.type}</td>
                  <td>{r.severity}</td>
                  <td className="mono">{r.active ? 'true' : 'false'}</td>
                  <td>
                    <button className="rd-secondary" onClick={() => toggle(r.id, !r.active)}>
                      {r.active ? 'Desactivar' : 'Activar'}
                    </button>
                  </td>
                </tr>
              ))}
              {!rules.length ? (
                <tr>
                  <td colSpan={6} className="muted">
                    Sin reglas
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}

export default function AppRouter() {
  const [token, setToken] = useState<string | null>(() => getStoredToken())
  const [session, setSession] = useState<UserSession>({})
  const [status, setStatus] = useState<string>('Listo.')
  const { apiJson } = useApi(token)

  const logout = () => {
    setStoredToken(null)
    setToken(null)
    setSession({})
    setStatus('Sesión cerrada.')
  }

  const onLoggedIn = (token: string, session: UserSession) => {
    setStoredToken(token)
    setToken(token)
    setSession(session)
    setStatus('Listo.')
  }

  useEffect(() => {
    if (!token) return
    ;(async () => {
      try {
        const me = await apiJson('/api/auth/me')
        setSession({ email: me.email, role: me.role })
      } catch (e: any) {
        setStatus(`Error: ${e?.message || e}`)
      }
    })()
  }, [token])

  return (
    <Routes>
      <Route path="/" element={<Navigate to={token ? '/app' : '/login'} replace />} />
      <Route path="/login" element={<LoginPage onLoggedIn={onLoggedIn} />} />
      <Route
        path="/app/*"
        element={
          <Protected token={token}>
            <AppLayout token={token as string} session={session} onLogout={logout} status={status} setStatus={setStatus} />
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
