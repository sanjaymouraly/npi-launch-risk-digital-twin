import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useApi } from '../hooks'
import { Badge, Button, Card, EmptyState, ErrorState, Icon, Loading, PageHeader } from '../components/ui'
import { fmtDate, fmtDays, fmtMoney, fmtPct, riskTone } from '../utils'

export default function Projects() {
  const navigate = useNavigate()
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { data, loading, error: loadError, reload } = useApi(() => api.projects.list(true), [])

  const action = async (label: string, fn: () => Promise<any>) => {
    setBusy(label)
    setError(null)
    try {
      await fn()
      await reload()
    } catch (err: any) {
      setError(err?.message || 'Action failed')
    } finally {
      setBusy(null)
    }
  }

  const importFile = async (file?: File | null) => {
    if (!file) return
    await action('import', async () => {
      const result = await api.projects.importFile(file)
      if (result.projects?.[0]?.id) navigate(`/projects/${result.projects[0].id}/overview`)
    })
  }

  if (loading && !data) return <Loading label="Loading programs" />
  if (loadError) return <ErrorState message={loadError} retry={reload} />

  return (
    <div className="page">
      <PageHeader
        eyebrow="Program portfolio"
        title="Programs under management"
        description="Each program is a complete digital twin: task graph, calendar, resources, BOM, suppliers, risks, validation tests and launch commitments."
        actions={
          <label className="btn btn-primary btn-md file-btn">
            {busy === 'import' ? <span className="spinner" /> : <Icon name="download" />}
            Import JSON
            <input type="file" accept="application/json" onChange={(event) => importFile(event.target.files?.[0])} />
          </label>
        }
      />
      {error && <div className="inline-error">{error}</div>}

      <Card padded={false}>
        {(data || []).length === 0 ? (
          <EmptyState
            title="No programs"
            message="Import one of the synthetic sample programs from data/samples to get started."
          />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Program</th>
                  <th>Status</th>
                  <th>Start</th>
                  <th>Launch deadline</th>
                  <th className="num">Tasks</th>
                  <th className="num">Latest on-time</th>
                  <th className="num">P90</th>
                  <th className="num">Cost of delay</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {(data || []).map((project) => {
                  const sim = project.latest_simulation
                  const tone = riskTone(sim?.on_time_probability)
                  return (
                    <tr key={project.id}>
                      <td>
                        <Link to={`/projects/${project.id}/overview`} className="cell-title link">
                          {project.key}
                        </Link>
                        <div className="cell-sub">{project.name}</div>
                      </td>
                      <td>
                        <Badge tone={project.status === 'active' ? 'good' : project.status === 'archived' ? 'neutral' : 'info'}>
                          {project.status}
                        </Badge>
                        {project.is_demo && <span className="demo-tag">synthetic</span>}
                      </td>
                      <td>{fmtDate(project.start_date)}</td>
                      <td>{fmtDate(project.launch_deadline)}</td>
                      <td className="num">{project.task_count}</td>
                      <td className="num">
                        <span className={`strong tone-${tone}`}>{sim ? fmtPct(sim.on_time_probability) : '—'}</span>
                      </td>
                      <td className="num">{sim ? fmtDays(sim.p90) : '—'}</td>
                      <td className="num">{fmtMoney(project.delay_cost_per_day)}/day</td>
                      <td>
                        <div className="row-actions">
                          <Button size="sm" variant="outline" onClick={() => navigate(`/projects/${project.id}/overview`)}>
                            Open
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            loading={busy === `dup-${project.id}`}
                            onClick={() => action(`dup-${project.id}`, () => api.projects.duplicate(project.id))}
                          >
                            Duplicate
                          </Button>
                          <a className="btn btn-ghost btn-sm" href={api.projects.exportUrl(project.id)}>
                            Export
                          </a>
                          {project.status !== 'archived' && (
                            <Button
                              size="sm"
                              variant="ghost"
                              loading={busy === `arch-${project.id}`}
                              onClick={() => action(`arch-${project.id}`, () => api.projects.archive(project.id))}
                            >
                              Archive
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="two-col">
        <Card title="Import format" eyebrow="Data contract">
          <p className="body-text">
            A program JSON contains metadata, resources, suppliers, components, tasks, dependencies, risks,
            validation tests, ECOs, milestones, quotes, purchase orders and inventory. Imports are transactional:
            a validation error rolls back the entire import.
          </p>
          <div className="button-row">
            <a className="btn btn-outline btn-md" href={api.projects.csvTemplateUrl()} download>
              <Icon name="download" /> Task CSV template
            </a>
            <a className="btn btn-ghost btn-md" href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
              OpenAPI schema ↗
            </a>
          </div>
        </Card>
        <Card title="Sample programs" eyebrow="Synthetic, realistic">
          <ul className="plain-list">
            <li><strong>Aurora X1</strong> — industrial gateway, tooling + EMC + allocation risk.</li>
            <li><strong>Helios EV</strong> — automotive inverter, IATF/PPAP qualification gates.</li>
            <li><strong>Vector 5G</strong> — electronics module, semiconductor allocation and carrier certification.</li>
            <li><strong>Titan H7</strong> — industrial pump, casting tooling and machining capacity.</li>
          </ul>
          <p className="muted-small">Located in <code>data/samples/</code>. Every program is synthetic; no customer data.</p>
        </Card>
      </div>
    </div>
  )
}
