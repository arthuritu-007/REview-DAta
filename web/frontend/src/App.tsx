import { useEffect, useMemo, useState } from 'react'
import './App.css'

function App() {
  const [page, setPage] = useState<
    | 'dashboard'
    | 'datasets'
    | 'validation'
    | 'findings'
    | 'stats'
    | 'reports'
    | 'recommendations'
  >('dashboard')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('rd_token'))
  const [sessionEmail, setSessionEmail] = useState<string>(() => localStorage.getItem('rd_email') || '')
  const [status, setStatus] = useState<string>('')

  const [datasets, setDatasets] = useState<any[]>([])
  const [runs, setRuns] = useState<any[]>([])
  const [reports, setReports] = useState<any[]>([])
  const [rules, setRules] = useState<any[]>([])

  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [schemaRequired, setSchemaRequired] = useState('Folio_reporte')
  const [schemaDates, setSchemaDates] = useState('Fecha_reporte')
  const [schemaTimes, setSchemaTimes] = useState('')

  const [selectedDatasetId, setSelectedDatasetId] = useState('')
  const [selectedRunId, setSelectedRunId] = useState('')
  const [selectedRuleIds, setSelectedRuleIds] = useState<Record<string, boolean>>({})
  const [mappingRequired, setMappingRequired] = useState('Folio_reporte')
  const [mappingDates, setMappingDates] = useState('Fecha_reporte')
  const [mappingConductor, setMappingConductor] = useState('Numero_operador')
  const [mappingCartaPorte, setMappingCartaPorte] = useState('')
  const [mappingCliente, setMappingCliente] = useState('')
  const [mappingFecha, setMappingFecha] = useState('')
  const [mappingDireccion, setMappingDireccion] = useState('')
  const [mappingEmpleado, setMappingEmpleado] = useState('')
  const [mappingPlacas, setMappingPlacas] = useState('')
  const [mappingPeso, setMappingPeso] = useState('')
  const [mappingFechaSalida, setMappingFechaSalida] = useState('')
  const [mappingFechaLlegada, setMappingFechaLlegada] = useState('')
  const [mappingPlacasRegex, setMappingPlacasRegex] = useState('')

  const [findings, setFindings] = useState<any[]>([])
  const [findingsTotal, setFindingsTotal] = useState(0)
  const [findingsOffset, setFindingsOffset] = useState(0)
  const [findingsLimit, setFindingsLimit] = useState(200)

  const [severity, setSeverity] = useState<Record<string, number>>({})
  const [recRunId, setRecRunId] = useState('')
  const [recommendations, setRecommendations] = useState<any[]>([])

  const apiFetch = async (path: string, init?: RequestInit) => {
    const headers: Record<string, string> = {}
    if (init?.headers) {
      Object.assign(headers, init.headers as any)
    }
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    const res = await fetch(path, { ...init, headers })
    const contentType = res.headers.get('content-type') || ''
    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        if (contentType.includes('application/json')) {
          const j = await res.json()
          detail = j.detail || JSON.stringify(j)
        } else {
          detail = await res.text()
        }
      } catch {
        detail = `HTTP ${res.status}`
      }
      throw new Error(detail)
    }
    if (contentType.includes('application/json')) {
      return res.json()
    }
    return res
  }

  const isAuthed = !!token

  const logout = () => {
    setToken(null)
    setSessionEmail('')
    localStorage.removeItem('rd_token')
    localStorage.removeItem('rd_email')
    setStatus('Sesión cerrada.')
  }

  const login = async () => {
    setStatus('Iniciando sesión...')
    try {
      const sess = await apiFetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      setToken(sess.token)
      setSessionEmail(sess.email || email)
      localStorage.setItem('rd_token', sess.token)
      localStorage.setItem('rd_email', sess.email || email)
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  const loadCoreLists = async () => {
    setStatus('Cargando datos...')
    try {
      const [ds, rs, rls, rps] = await Promise.all([
        apiFetch('/api/datasets'),
        apiFetch('/api/runs'),
        apiFetch('/api/rules'),
        apiFetch('/api/reports'),
      ])
      setDatasets(ds)
      setRuns(rs)
      setRules(rls)
      setReports(rps)
      if (!selectedDatasetId && ds?.length) setSelectedDatasetId(ds[0].id)
      if (!selectedRunId && rs?.length) setSelectedRunId(rs[0].id)
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  useEffect(() => {
    if (!isAuthed) return
    loadCoreLists()
  }, [isAuthed])

  const selectedRuleIdList = useMemo(() => {
    const out: string[] = []
    for (const [k, v] of Object.entries(selectedRuleIds)) {
      if (v) out.push(k)
    }
    return out
  }, [selectedRuleIds])

  const uploadDataset = async () => {
    if (!uploadFile) {
      setStatus('Selecciona un CSV.')
      return
    }
    setStatus('Subiendo dataset...')
    try {
      const schema = {
        required_columns: schemaRequired
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        date_columns: schemaDates
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        time_columns: schemaTimes
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
      }
      const fd = new FormData()
      fd.append('file', uploadFile)
      fd.append('schema_json', JSON.stringify(schema))
      const ds = await apiFetch('/api/datasets/upload', { method: 'POST', body: fd })
      setStatus('Dataset cargado.')
      setDatasets((prev) => [ds, ...prev])
      setSelectedDatasetId(ds.id)
      setPage('validation')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  const runValidation = async () => {
    if (!selectedDatasetId) {
      setStatus('Selecciona un dataset.')
      return
    }
    if (!selectedRuleIdList.length) {
      setStatus('Selecciona al menos una regla.')
      return
    }
    setStatus('Ejecutando validación...')
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
      const run = await apiFetch(`/api/runs/${selectedDatasetId}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rule_ids: selectedRuleIdList, mapping }),
      })
      setStatus(`Listo. Run: ${String(run.id).slice(0, 8)}`)
      setRuns((prev) => [run, ...prev])
      setSelectedRunId(run.id)
      setPage('findings')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  const loadFindings = async (offset: number) => {
    if (!selectedRunId) {
      setStatus('Selecciona un run.')
      return
    }
    setStatus('Cargando hallazgos...')
    try {
      const res = await apiFetch(
        `/api/findings?run_id=${encodeURIComponent(selectedRunId)}&offset=${offset}&limit=${findingsLimit}`,
      )
      setFindings(res.items || [])
      setFindingsTotal(res.total || 0)
      setFindingsOffset(offset)
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  const loadStats = async () => {
    setStatus('Cargando estadísticas...')
    try {
      const dsParam = selectedDatasetId ? `?dataset_id=${encodeURIComponent(selectedDatasetId)}` : ''
      const [sev, rs] = await Promise.all([apiFetch(`/api/stats/severity${dsParam}`), apiFetch(`/api/runs${dsParam}`)])
      setSeverity(sev || {})
      setRuns(rs || [])
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  const loadReports = async () => {
    setStatus('Cargando reportes...')
    try {
      const rps = await apiFetch('/api/reports')
      setReports(rps || [])
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  const downloadPdf = (runId: string) => {
    const url = `/api/reports/${encodeURIComponent(runId)}/pdf`
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  const loadRecommendations = async () => {
    const runId = (recRunId || selectedRunId || '').trim()
    if (!runId) {
      setStatus('Escribe un run_id.')
      return
    }
    setStatus('Cargando recomendaciones...')
    try {
      const recs = await apiFetch(`/api/recommendations?run_id=${encodeURIComponent(runId)}`)
      setRecommendations(recs || [])
      setStatus('Listo.')
    } catch (e: any) {
      setStatus(`Error: ${e?.message || e}`)
    }
  }

  return (
    <div className="rd-shell">
      <aside className="rd-sidebar">
        <div className="rd-brand">
          <div className="rd-badge">RD</div>
          <div>
            <div className="rd-title">Review Data</div>
            <div className="rd-subtitle">{isAuthed ? sessionEmail : 'Web'}</div>
          </div>
        </div>

        <nav className="rd-nav">
          <button className={page === 'dashboard' ? 'active' : ''} onClick={() => setPage('dashboard')}>
            Inicio
          </button>
          <button className={page === 'datasets' ? 'active' : ''} onClick={() => setPage('datasets')}>
            Cargar Dataset
          </button>
          <button className={page === 'validation' ? 'active' : ''} onClick={() => setPage('validation')}>
            Ejecutar Validación
          </button>
          <button className={page === 'findings' ? 'active' : ''} onClick={() => setPage('findings')}>
            Hallazgos
          </button>
          <button className={page === 'recommendations' ? 'active' : ''} onClick={() => setPage('recommendations')}>
            Recomendaciones
          </button>
          <button className={page === 'stats' ? 'active' : ''} onClick={() => setPage('stats')}>
            Estadísticas
          </button>
          <button className={page === 'reports' ? 'active' : ''} onClick={() => setPage('reports')}>
            Reportes
          </button>
        </nav>

        <div className="rd-sidebar-footer">
          {isAuthed ? (
            <button className="rd-danger" onClick={logout}>
              Cerrar sesión
            </button>
          ) : null}
        </div>
      </aside>

      <main className="rd-main">
        <header className="rd-topbar">
          <div className="rd-topbar-left">
            <div className="rd-h1">
              {page === 'dashboard'
                ? 'Inicio'
                : page === 'datasets'
                  ? 'Cargar Dataset'
                  : page === 'validation'
                    ? 'Ejecutar Validación'
                    : page === 'findings'
                      ? 'Hallazgos'
                      : page === 'recommendations'
                        ? 'Recomendaciones'
                        : page === 'stats'
                          ? 'Estadísticas'
                          : 'Reportes'}
            </div>
          </div>
          <div className="rd-topbar-right">
            <button
              className="rd-secondary"
              onClick={() => {
                if (!isAuthed) return
                loadCoreLists()
              }}
              disabled={!isAuthed}
            >
              Actualizar
            </button>
          </div>
        </header>

        <div className="rd-status">{status}</div>

        {!isAuthed ? (
          <section className="rd-card rd-login">
            <div className="rd-card-title">Iniciar sesión</div>
            <div className="rd-form">
              <label>
                Email
                <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="user@reviewdata.local" />
              </label>
              <label>
                Contraseña
                <input
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  type="password"
                />
              </label>
              <button className="rd-primary" onClick={login}>
                Entrar
              </button>
            </div>
          </section>
        ) : null}

        {isAuthed && page === 'dashboard' ? (
          <section className="rd-grid">
            <div className="rd-card">
              <div className="rd-card-title">Resumen</div>
              <div className="rd-kpis">
                <div className="rd-kpi">
                  <div className="label">Datasets</div>
                  <div className="value">{datasets.length}</div>
                </div>
                <div className="rd-kpi">
                  <div className="label">Ejecuciones</div>
                  <div className="value">{runs.length}</div>
                </div>
                <div className="rd-kpi">
                  <div className="label">Reportes</div>
                  <div className="value">{reports.length}</div>
                </div>
              </div>
              <div className="rd-actions">
                <button className="rd-primary" onClick={loadStats}>
                  Ver severidad
                </button>
              </div>
              <div className="rd-sev">
                <div>Crítica: {severity['Crítica'] ?? severity['CrÝtica'] ?? 0}</div>
                <div>Alta: {severity['Alta'] ?? 0}</div>
                <div>Media: {severity['Media'] ?? 0}</div>
                <div>Baja: {severity['Baja'] ?? 0}</div>
              </div>
            </div>

            <div className="rd-card">
              <div className="rd-card-title">Últimos runs</div>
              <div className="rd-table-wrap">
                <table className="rd-table">
                  <thead>
                    <tr>
                      <th>Run</th>
                      <th>Dataset</th>
                      <th>Incons.</th>
                      <th>Fecha</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.slice(0, 10).map((r) => (
                      <tr key={r.id}>
                        <td>{String(r.id).slice(0, 8)}</td>
                        <td>{r.dataset_name}</td>
                        <td>{r.inconsistencies}</td>
                        <td>
                          {r.date} {r.time}
                        </td>
                      </tr>
                    ))}
                    {!runs.length ? (
                      <tr>
                        <td colSpan={4} className="muted">
                          Sin ejecuciones
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        ) : null}

        {isAuthed && page === 'datasets' ? (
          <section className="rd-grid">
            <div className="rd-card">
              <div className="rd-card-title">Subir CSV</div>
              <div className="rd-form">
                <label>
                  Archivo CSV
                  <input type="file" accept=".csv" onChange={(e) => setUploadFile(e.target.files?.[0] || null)} />
                </label>
                <label>
                  Columnas obligatorias (coma)
                  <input value={schemaRequired} onChange={(e) => setSchemaRequired(e.target.value)} />
                </label>
                <label>
                  Columnas fecha (coma)
                  <input value={schemaDates} onChange={(e) => setSchemaDates(e.target.value)} />
                </label>
                <label>
                  Columnas hora (coma)
                  <input value={schemaTimes} onChange={(e) => setSchemaTimes(e.target.value)} />
                </label>
                <button className="rd-primary" onClick={uploadDataset}>
                  Subir
                </button>
              </div>
            </div>

            <div className="rd-card">
              <div className="rd-card-title">Datasets</div>
              <div className="rd-table-wrap">
                <table className="rd-table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Nombre</th>
                      <th>Registros</th>
                      <th>Fecha</th>
                    </tr>
                  </thead>
                  <tbody>
                    {datasets.slice(0, 50).map((d) => (
                      <tr key={d.id} className={selectedDatasetId === d.id ? 'selected' : ''}>
                        <td>
                          <button className="rd-link" onClick={() => setSelectedDatasetId(d.id)}>
                            {String(d.id).slice(0, 8)}
                          </button>
                        </td>
                        <td>{d.name}</td>
                        <td>{d.records}</td>
                        <td>
                          {d.date} {d.time}
                        </td>
                      </tr>
                    ))}
                    {!datasets.length ? (
                      <tr>
                        <td colSpan={4} className="muted">
                          Sin datasets
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        ) : null}

        {isAuthed && page === 'validation' ? (
          <section className="rd-grid">
            <div className="rd-card">
              <div className="rd-card-title">Dataset</div>
              <div className="rd-form">
                <label>
                  Selecciona dataset
                  <select value={selectedDatasetId} onChange={(e) => setSelectedDatasetId(e.target.value)}>
                    <option value="">Seleccionar</option>
                    {datasets.map((d) => (
                      <option key={d.id} value={d.id}>
                        {String(d.id).slice(0, 8)} - {d.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="rd-card-title" style={{ marginTop: 16 }}>
                Mapeo (si aplica)
              </div>
              <div className="rd-form rd-form-2">
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
            </div>

            <div className="rd-card">
              <div className="rd-card-title">Reglas</div>
              <div className="rd-rules">
                {rules.map((r) => (
                  <label key={r.id} className="rd-check">
                    <input
                      type="checkbox"
                      checked={!!selectedRuleIds[r.id]}
                      onChange={(e) => setSelectedRuleIds((prev) => ({ ...prev, [r.id]: e.target.checked }))}
                    />
                    <span className="name">{r.name}</span>
                    <span className="meta">
                      {r.id} · {r.severity}
                    </span>
                  </label>
                ))}
                {!rules.length ? <div className="muted">Sin reglas</div> : null}
              </div>
              <div className="rd-actions">
                <button className="rd-primary" onClick={runValidation}>
                  Ejecutar
                </button>
              </div>
            </div>
          </section>
        ) : null}

        {isAuthed && page === 'findings' ? (
          <section className="rd-card">
            <div className="rd-row">
              <div className="rd-form rd-inline">
                <label>
                  Run
                  <select value={selectedRunId} onChange={(e) => setSelectedRunId(e.target.value)}>
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
                    value={findingsLimit}
                    onChange={(e) => setFindingsLimit(Math.max(1, Math.min(2000, Number(e.target.value) || 200)))}
                  />
                </label>
                <button className="rd-primary" onClick={() => loadFindings(0)}>
                  Cargar
                </button>
              </div>
              <div className="muted">
                Total: {findingsTotal} · Página: {Math.floor(findingsOffset / findingsLimit) + 1}
              </div>
            </div>

            <div className="rd-table-wrap">
              <table className="rd-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Regla</th>
                    <th>Campo</th>
                    <th>Valor</th>
                    <th>Sev.</th>
                    <th>Fecha</th>
                  </tr>
                </thead>
                <tbody>
                  {findings.map((f) => (
                    <tr key={f.id}>
                      <td>{String(f.id).slice(0, 8)}</td>
                      <td>{f.rule_name}</td>
                      <td>{f.field}</td>
                      <td className="mono">{String(f.value).slice(0, 80)}</td>
                      <td>{f.severity}</td>
                      <td>
                        {f.date} {f.time}
                      </td>
                    </tr>
                  ))}
                  {!findings.length ? (
                    <tr>
                      <td colSpan={6} className="muted">
                        Sin hallazgos
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>

            <div className="rd-actions">
              <button className="rd-secondary" disabled={findingsOffset === 0} onClick={() => loadFindings(findingsOffset - findingsLimit)}>
                Anterior
              </button>
              <button
                className="rd-secondary"
                disabled={findingsOffset + findingsLimit >= findingsTotal}
                onClick={() => loadFindings(findingsOffset + findingsLimit)}
              >
                Siguiente
              </button>
            </div>
          </section>
        ) : null}

        {isAuthed && page === 'stats' ? (
          <section className="rd-grid">
            <div className="rd-card">
              <div className="rd-card-title">Filtros</div>
              <div className="rd-form">
                <label>
                  Dataset
                  <select value={selectedDatasetId} onChange={(e) => setSelectedDatasetId(e.target.value)}>
                    <option value="">Todos</option>
                    {datasets.map((d) => (
                      <option key={d.id} value={d.id}>
                        {String(d.id).slice(0, 8)} - {d.name}
                      </option>
                    ))}
                  </select>
                </label>
                <button className="rd-primary" onClick={loadStats}>
                  Cargar
                </button>
              </div>
              <div className="rd-sev">
                <div>Crítica: {severity['Crítica'] ?? severity['CrÝtica'] ?? 0}</div>
                <div>Alta: {severity['Alta'] ?? 0}</div>
                <div>Media: {severity['Media'] ?? 0}</div>
                <div>Baja: {severity['Baja'] ?? 0}</div>
              </div>
            </div>

            <div className="rd-card">
              <div className="rd-card-title">Runs</div>
              <div className="rd-table-wrap">
                <table className="rd-table">
                  <thead>
                    <tr>
                      <th>Run</th>
                      <th>Dataset</th>
                      <th>Incons.</th>
                      <th>Usuario</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.slice(0, 25).map((r) => (
                      <tr key={r.id}>
                        <td>{String(r.id).slice(0, 8)}</td>
                        <td>{r.dataset_name}</td>
                        <td>{r.inconsistencies}</td>
                        <td>{r.user_email}</td>
                      </tr>
                    ))}
                    {!runs.length ? (
                      <tr>
                        <td colSpan={4} className="muted">
                          Sin datos
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        ) : null}

        {isAuthed && page === 'reports' ? (
          <section className="rd-card">
            <div className="rd-row">
              <button className="rd-primary" onClick={loadReports}>
                Cargar
              </button>
            </div>
            <div className="rd-table-wrap">
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
                  {reports.map((r) => (
                    <tr key={r.id}>
                      <td>{String(r.id).slice(0, 8)}</td>
                      <td className="mono">{String(r.run_id).slice(0, 8)}</td>
                      <td>{r.dataset_name}</td>
                      <td>{r.generated_at}</td>
                      <td>
                        <button className="rd-secondary" onClick={() => downloadPdf(r.run_id)}>
                          Descargar PDF
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!reports.length ? (
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
        ) : null}

        {isAuthed && page === 'recommendations' ? (
          <section className="rd-grid">
            <div className="rd-card">
              <div className="rd-card-title">Run</div>
              <div className="rd-form">
                <label>
                  Run ID
                  <input value={recRunId} onChange={(e) => setRecRunId(e.target.value)} placeholder={selectedRunId || ''} />
                </label>
                <button className="rd-primary" onClick={loadRecommendations}>
                  Cargar
                </button>
              </div>
            </div>
            <div className="rd-card">
              <div className="rd-card-title">Recomendaciones</div>
              <div className="rd-table-wrap">
                <table className="rd-table">
                  <thead>
                    <tr>
                      <th>Regla</th>
                      <th>Recomendación</th>
                      <th>Fuente</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recommendations.map((r) => (
                      <tr key={r.rule_id}>
                        <td className="mono">{r.rule_id}</td>
                        <td>{r.recommendation}</td>
                        <td>{r.source}</td>
                      </tr>
                    ))}
                    {!recommendations.length ? (
                      <tr>
                        <td colSpan={3} className="muted">
                          Sin recomendaciones
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        ) : null}
      </main>
    </div>
  )
}

export default App
