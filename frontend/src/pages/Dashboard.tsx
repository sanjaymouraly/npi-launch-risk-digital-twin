import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ProjectSummary } from '../api'
import { useApi } from '../hooks'
import PlotChart, { PALETTE } from '../components/Plot'
import { Badge, Button, Card, EmptyState, ErrorState, Icon, Kpi, Loading, PageHeader } from '../components/ui'
import { fmtDate, fmtDays, fmtMoney, fmtPct, riskTone, shortId } from '../utils'

type ProgramForecast = {
  project: ProjectSummary
  simulation: any | null
  nextMilestone?: any | null
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState<string | null>(null)

  const { data, error, loading, reload } = useApi(async () => {
    const projects = await api.projects.list()
    const forecasts = await Promise.all(
      projects.map(async (project) => {
        let simulation: any = null
        try {
          simulation = await api.simulations.latest(project.id)
        } catch {
          simulation = null
        }
        return { project, simulation } as ProgramForecast
      }),
    )
    return forecasts
  }, [])

  const stats = useMemo(() => {
    const list = data || []
    const simulated = list.filter((item) => item.simulation)
    const onTime = simulated.map((item) => item.simulation.summary.deadline.on_time_probability ?? 0)
    const avg = onTime.length ? onTime.reduce((a, b) => a + b, 0) / onTime.length : null
    const atRisk = simulated.filter((item) => (item.simulation.summary.deadline.on_time_probability ?? 1) < 0.5).length
    const exposure = simulated.reduce(
      (sum, item) => sum + (item.simulation.summary.deadline.expected_delay_cost || 0),
      0,
    )
    return { list, simulated, avg, atRisk, exposure }
  }, [data])

  const sorted = useMemo(
    () =>
      [...(data || [])].sort((a, b) => {
        const av = a.simulation?.summary?.deadline?.on_time_probability ?? 2
        const bv = b.simulation?.summary?.deadline?.on_time_probability ?? 2
        return av - bv
      }),
    [data],
  )

  const bar = useMemo(() => {
    const rows = sorted.filter((item) => item.simulation)
    return [
      {
        type: 'bar',
        x: rows.map((item) => item.project.key),
        y: rows.map((item) => (item.simulation.summary.deadline.on_time_probability ?? 0) * 100),
        marker: {
          color: rows.map((item) => {
            const value = item.simulation.summary.deadline.on_time_probability ?? 0
            return value >= 0.75 ? PALETTE.green : value >= 0.4 ? PALETTE.amber : PALETTE.red
          }),
        },
        text: rows.map((item) => fmtPct(item.simulation.summary.deadline.on_time_probability)),
        textposition: 'outside',
        cliponaxis: false,
        hovertemplate: '%{x}<br>On-time probability %{y:.1f}%<extra></extra>',
      },
    ]
  }, [sorted])

  const importJson = async (file?: File | null) => {
    if (!file) return
    setImporting(true)
    setImportError(null)
    try {
      const result = await api.projects.importFile(file)
      await reload()
      if (result.projects?.[0]?.id) navigate(`/projects/${result.projects[0].id}/overview`)
    } catch (err: any) {
      setImportError(err?.message || 'Import failed')
    } finally {
      setImporting(false)
    }
  }

  if (loading && !data) return <Loading label="Loading portfolio" />
  if (error) return <ErrorState message={error} retry={reload} />

  return (
    <div className="page">
      <PageHeader
        eyebrow="Portfolio command centre"
        title="Where launch risk is concentrating"
        description="Deterministic schedules, resource-feasible Monte Carlo forecasts and verified interventions across every NPI program."
        actions={
          <>
            <label className="btn btn-outline btn-md file-btn">
              {importing ? <span className="spinner" /> : <Icon name="download" />}
              Import program
              <input
                type="file"
                accept="application/json"
                onChange={(event) => importJson(event.target.files?.[0])}
              />
            </label>
            <Button onClick={() => navigate('/projects')} icon={<Icon name="programs" />}>
              Manage programs
            </Button>
          </>
        }
      />
      {importError && <div className="inline-error">{importError}</div>}

      <div className="kpi-grid">
        <Kpi
          label="Active programs"
          value={stats.list.filter((item) => item.project.status === 'active').length}
          sub={`${stats.list.length} in portfolio · ${stats.simulated.length} forecast-ready`}
          tone="neutral"
          icon={<Icon name="programs" />}
        />
        <Kpi
          label="Mean on-time probability"
          value={stats.avg === null ? '—' : fmtPct(stats.avg, 0)}
          sub="Unweighted mean of latest completed runs"
          tone={stats.avg === null ? 'neutral' : stats.avg >= 0.6 ? 'good' : stats.avg >= 0.35 ? 'warn' : 'bad'}
          icon={<Icon name="simulation" />}
        />
        <Kpi
          label="Programs below 50%"
          value={stats.atRisk}
          sub="On-time probability below the 50% decision threshold"
          tone={stats.atRisk > 0 ? 'bad' : 'good'}
          icon={<Icon name="risk" />}
        />
        <Kpi
          label="Expected delay exposure"
          value={fmtMoney(stats.exposure, 'USD', true)}
          sub="Sum of expected delay cost from latest runs"
          tone={stats.exposure > 500000 ? 'warn' : 'neutral'}
          icon={<Icon name="clock" />}
        />
      </div>

      <div className="dashboard-grid">
        <Card
          title="On-time probability by program"
          subtitle="Latest completed Monte Carlo run per program. Hover for values."
          className="span-2"
        >
          {stats.simulated.length ? (
            <PlotChart
              data={bar}
              height={290}
              layout={{
                yaxis: { title: 'On-time probability (%)', range: [0, 112], ticksuffix: '%' },
                xaxis: { title: '' },
                margin: { l: 48, r: 20, t: 20, b: 46 },
                shapes: [
                  {
                    type: 'line',
                    xref: 'paper',
                    x0: 0,
                    x1: 1,
                    y0: 50,
                    y1: 50,
                    line: { color: '#b23a2f', width: 1.5, dash: 'dot' },
                  },
                ],
              }}
            />
          ) : (
            <EmptyState
              title="No forecasts yet"
              message="Run a Monte Carlo simulation on a program to populate the portfolio view."
              action={
                <Button size="sm" onClick={() => navigate('/projects')}>
                  Open a program
                </Button>
              }
            />
          )}
        </Card>

        <Card title="Decision posture" eyebrow="Reading the portfolio" className="span-1">
          <div className="posture-list">
            <div className="posture">
              <span className="posture-dot red" />
              <div>
                <strong>{stats.atRisk} program{stats.atRisk === 1 ? '' : 's'} below threshold</strong>
                <p>Targeted intervention or deadline reset needs a decision.</p>
              </div>
            </div>
            <div className="posture">
              <span className="posture-dot amber" />
              <div>
                <strong>{stats.simulated.length - stats.atRisk} with contingent risk</strong>
                <p>Forecast is above 50%, but tail exposure still matters.</p>
              </div>
            </div>
            <div className="posture">
              <span className="posture-dot teal" />
              <div>
                <strong>No fabricated precision</strong>
                <p>Every number links to a simulation ID, seed and iteration count.</p>
              </div>
            </div>
          </div>
          <div className="divider" />
          <div className="mini-method">
            <Icon name="info" />
            <p>
              Probabilities come from resource-feasible serial SGS trials. CPM and constrained durations are
              reported separately and never blended.
            </p>
          </div>
        </Card>
      </div>

      <div className="section-head">
        <div>
          <div className="eyebrow">Programs</div>
          <h2>Launch risk board</h2>
        </div>
        <span className="muted-small">Sorted by lowest on-time probability</span>
      </div>

      <div className="program-grid">
        {sorted.length === 0 && (
          <Card>
            <EmptyState
              title="No programs yet"
              message="Import a program JSON from data/samples to start exploring the platform."
            />
          </Card>
        )}
        {sorted.map(({ project, simulation }) => {
          const deadline = simulation?.summary?.deadline
          const probability = deadline?.on_time_probability
          const tone = simulation ? riskTone(probability) : 'neutral'
          return (
            <Link className="program-card" to={`/projects/${project.id}/overview`} key={project.id}>
              <div className="program-card-head">
                <div>
                  <div className="program-key">{project.key}</div>
                  <h3>{project.name}</h3>
                </div>
                <Badge tone={project.status === 'active' ? 'good' : 'neutral'}>{project.status}</Badge>
              </div>
              <p className="program-product">{project.product}</p>
              <div className="program-stats">
                <div>
                  <span>On-time</span>
                  <strong className={`tone-${tone}`}>{simulation ? fmtPct(probability) : 'Not simulated'}</strong>
                </div>
                <div>
                  <span>P50 / P90</span>
                  <strong>
                    {simulation ? `${fmtDays(simulation.summary.makespan.p50)} / ${fmtDays(simulation.summary.makespan.p90)}` : '—'}
                  </strong>
                </div>
                <div>
                  <span>Deadline</span>
                  <strong>{fmtDate(project.launch_deadline)}</strong>
                </div>
              </div>
              {simulation && (
                <div className="program-progress">
                  <div className="program-progress-label">
                    <span>Launch confidence</span>
                    <span>{fmtPct(probability, 0)}</span>
                  </div>
                  <div className="confidence-track">
                    <div
                      className={`confidence-fill tone-bg-${tone}`}
                      style={{ width: `${Math.max(2, (probability || 0) * 100)}%` }}
                    />
                  </div>
                </div>
              )}
              <div className="program-card-foot">
                <span>{project.task_count} tasks · {project.owner}</span>
                <span className="program-open">
                  Open <Icon name="arrow" size={14} />
                </span>
              </div>
            </Link>
          )
        })}
      </div>

      <Card
        title="Launch exposure register"
        subtitle="Expected delay cost is the simulated mean of delay days × the program's cost of delay. It is not a budget line."
        className="table-card"
      >
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Program</th>
                <th>Deadline</th>
                <th>Latest run</th>
                <th className="num">P50</th>
                <th className="num">P90</th>
                <th className="num">On-time</th>
                <th className="num">Expected delay cost</th>
                <th>Tail posture</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map(({ project, simulation }) => {
                const summary = simulation?.summary
                const tone = simulation ? riskTone(summary.deadline.on_time_probability) : 'neutral'
                return (
                  <tr key={project.id} onClick={() => navigate(`/projects/${project.id}/overview`)} className="click-row">
                    <td>
                      <div className="cell-title">{project.key}</div>
                      <div className="cell-sub">{project.name}</div>
                    </td>
                    <td>{fmtDate(project.launch_deadline)}</td>
                    <td>
                      {simulation ? (
                        <>
                          <div className="cell-title">SIM {shortId(simulation.id)}</div>
                          <div className="cell-sub">{simulation.iterations.toLocaleString()} trials · seed {simulation.seed}</div>
                        </>
                      ) : (
                        <span className="muted-small">—</span>
                      )}
                    </td>
                    <td className="num">{summary ? fmtDays(summary.makespan.p50) : '—'}</td>
                    <td className="num">{summary ? fmtDays(summary.makespan.p90) : '—'}</td>
                    <td className="num">
                      <span className={`tone-${tone} strong`}>{summary ? fmtPct(summary.deadline.on_time_probability) : '—'}</span>
                    </td>
                    <td className="num">{summary ? fmtMoney(summary.deadline.expected_delay_cost) : '—'}</td>
                    <td>
                      {summary ? (
                        <Badge tone={tone === 'good' ? 'good' : tone === 'warn' ? 'warn' : 'bad'}>
                          {tone === 'good' ? 'Managed' : tone === 'warn' ? 'Contingent' : 'Critical'}
                        </Badge>
                      ) : (
                        <Badge tone="neutral">No forecast</Badge>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
