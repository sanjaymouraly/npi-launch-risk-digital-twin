import { useCallback, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, SimulationSummary } from '../api'
import { useApi, useJobPoller } from '../hooks'
import PlotChart, { PALETTE } from '../components/Plot'
import {
  Badge,
  Button,
  Callout,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Icon,
  Kpi,
  Loading,
  PageHeader,
  ProgressBar,
} from '../components/ui'
import { fmtDate, fmtDays, fmtMoney, fmtNumber, fmtPct, riskTone, shortId } from '../utils'

export default function SimulationPage() {
  const { projectId = '' } = useParams()
  const navigate = useNavigate()
  const [form, setForm] = useState({
    iterations: 2000,
    seed: 42,
    label: 'Decision run',
    scenario_id: '',
    correlation_rho: 0.6,
    capacity_loss_prob: 0.02,
    absenteeism_prob: 0.02,
    transport_delay_prob: 0.015,
    supplier_disruption_enabled: true,
    material_constraints_enabled: true,
    validate_iterations: 0,
    async_job: false,
  })
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [advanced, setAdvanced] = useState(false)

  const { data, error, loading, reload } = useApi(async () => {
    const [project, scenarios] = await Promise.all([
      api.projects.get(projectId),
      api.scenarios.list(projectId),
    ])
    const history = await api.simulations.list(projectId)
    let latest: SimulationSummary | null = null
    try {
      latest = await api.simulations.latest(projectId)
    } catch {
      latest = null
    }
    return { project, scenarios, history, latest }
  }, [projectId])

  const onJobComplete = useCallback(() => {
    reload()
  }, [reload])
  const { job, track, error: jobError } = useJobPoller(onJobComplete)

  const summary = data?.latest?.summary
  const currency = data?.project.currency || 'USD'

  const histogram = useMemo(() => {
    if (!summary?.histogram) return []
    const { counts, bin_edges } = summary.histogram
    const centers = counts.map((_: number, index: number) => (bin_edges[index] + bin_edges[index + 1]) / 2)
    return [
      {
        type: 'bar',
        x: centers,
        y: counts,
        marker: { color: PALETTE.navy, opacity: 0.82 },
        hovertemplate: '%{x:.0f} working days<br>%{y} trials<extra></extra>',
      },
    ]
  }, [summary])

  const curve = useMemo(() => {
    const rows = summary?.completion_curve || []
    return [
      {
        type: 'scatter',
        mode: 'lines',
        x: rows.map((row: any) => row.offset),
        y: rows.map((row: any) => row.probability * 100),
        line: { color: PALETTE.teal, width: 2.5 },
        fill: 'tozeroy',
        fillcolor: 'rgba(15,122,112,0.10)',
        hovertemplate: 'By %{x:.0f} days: %{y:.1f}% probability<extra></extra>',
      },
    ]
  }, [summary])

  const run = async () => {
    setRunError(null)
    setRunning(true)
    try {
      const payload = {
        ...form,
        scenario_id: form.scenario_id || null,
        iterations: Number(form.iterations),
        seed: Number(form.seed),
        correlation_rho: Number(form.correlation_rho),
        validate_iterations: Number(form.validate_iterations),
      }
      const result = await api.simulations.run(projectId, payload)
      if (result.async && result.job_id) {
        track(result.job_id)
      } else {
        await reload()
      }
    } catch (err: any) {
      setRunError(err?.message || 'Simulation failed')
    } finally {
      setRunning(false)
    }
  }

  if (loading && !data) return <Loading label="Loading simulation workspace" />
  if (error) return <ErrorState message={error} retry={reload} />
  if (!data) return null

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${data.project.key} · Monte Carlo`}
        title="Simulate the launch distribution"
        description="Every trial is resource- and material-feasible. Correlated durations, supplier disruption, validation failures, ECOs and capacity loss are sampled together."
        actions={
          <Button variant="outline" onClick={() => navigate(`/projects/${projectId}/scenarios`)} icon={<Icon name="scenario" />}>
            Compare scenarios
          </Button>
        }
      />

      <div className="sim-layout">
        <Card title="Run configuration" eyebrow="Reproducible by seed" className="sim-form-card">
          <div className="form-grid">
            <Field label="Iterations" hint="50–50,000. 2,000 is a pragmatic default.">
              <input
                type="number"
                min={50}
                max={50000}
                value={form.iterations}
                onChange={(event) => setForm({ ...form, iterations: Number(event.target.value) })}
              />
            </Field>
            <Field label="Seed" hint="Same seed + same data reproduces the run.">
              <input
                type="number"
                min={0}
                value={form.seed}
                onChange={(event) => setForm({ ...form, seed: Number(event.target.value) })}
              />
            </Field>
          </div>
          <Field label="Label">
            <input value={form.label} onChange={(event) => setForm({ ...form, label: event.target.value })} />
          </Field>
          <Field label="Scenario" hint="Baseline uses the approved plan with no interventions.">
            <select value={form.scenario_id} onChange={(event) => setForm({ ...form, scenario_id: event.target.value })}>
              <option value="">Approved baseline</option>
              {data.scenarios.map((scenario) => (
                <option key={scenario.id} value={scenario.id}>
                  {scenario.name}
                </option>
              ))}
            </select>
          </Field>

          <button className="disclosure" onClick={() => setAdvanced(!advanced)} type="button">
            <span>{advanced ? '▾' : '▸'} Advanced stochastic settings</span>
            <span className="muted-small">defaults are calibrated</span>
          </button>
          {advanced && (
            <div className="advanced-panel">
              <Field label="Correlation ρ" hint="Latent correlation across task durations (0–0.99).">
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  max="0.99"
                  value={form.correlation_rho}
                  onChange={(event) => setForm({ ...form, correlation_rho: Number(event.target.value) })}
                />
              </Field>
              <div className="form-grid">
                <Field label="Capacity loss / trial">
                  <input
                    type="number"
                    step="0.005"
                    min="0"
                    max="1"
                    value={form.capacity_loss_prob}
                    onChange={(event) => setForm({ ...form, capacity_loss_prob: Number(event.target.value) })}
                  />
                </Field>
                <Field label="Absenteeism / trial">
                  <input
                    type="number"
                    step="0.005"
                    min="0"
                    max="1"
                    value={form.absenteeism_prob}
                    onChange={(event) => setForm({ ...form, absenteeism_prob: Number(event.target.value) })}
                  />
                </Field>
              </div>
              <Field label="Transport delay / trial">
                <input
                  type="number"
                  step="0.005"
                  min="0"
                  max="1"
                  value={form.transport_delay_prob}
                  onChange={(event) => setForm({ ...form, transport_delay_prob: Number(event.target.value) })}
                />
              </Field>
              <label className="switch-row">
                <input
                  type="checkbox"
                  checked={form.supplier_disruption_enabled}
                  onChange={(event) => setForm({ ...form, supplier_disruption_enabled: event.target.checked })}
                />
                <span>Supplier disruption sampling</span>
              </label>
              <label className="switch-row">
                <input
                  type="checkbox"
                  checked={form.material_constraints_enabled}
                  onChange={(event) => setForm({ ...form, material_constraints_enabled: event.target.checked })}
                />
                <span>Material release constraints</span>
              </label>
              <Field
                label="CP-SAT validation iterations"
                hint="0 disables. Each iteration solves CP-SAT to quantify the SGS optimality gap; expensive."
              >
                <input
                  type="number"
                  min={0}
                  max={10}
                  value={form.validate_iterations}
                  onChange={(event) => setForm({ ...form, validate_iterations: Number(event.target.value) })}
                />
              </Field>
            </div>
          )}

          <label className="switch-row">
            <input type="checkbox" checked={form.async_job} onChange={(event) => setForm({ ...form, async_job: event.target.checked })} />
            <span>Run as a background job</span>
          </label>

          <Button onClick={run} loading={running} className="full-width" icon={<Icon name="play" />}>
            Run Monte Carlo
          </Button>
          {(runError || jobError) && <div className="inline-error">{runError || jobError}</div>}
          {job && (
            <div className="job-panel">
              <div className="job-head">
                <Badge tone={job.status === 'completed' ? 'good' : job.status === 'failed' ? 'bad' : 'info'}>
                  {job.status}
                </Badge>
                <span className="muted-small">{Math.round(job.progress * 100)}%</span>
              </div>
              <ProgressBar value={job.progress} tone={job.status === 'failed' ? 'bad' : 'accent'} />
              <p className="muted-small">{job.message || 'Queued'}</p>
              {job.status === 'failed' && <div className="inline-error">{job.error}</div>}
            </div>
          )}
          <div className="mini-method">
            <Icon name="info" />
            <p>
              Correlated inputs share a latent factor. Percentiles use linear interpolation between order statistics;
              the method is recorded in the run summary.
            </p>
          </div>
        </Card>

        <div className="sim-results">
          {!data.latest || !summary ? (
            <Card>
              <EmptyState
                icon="◇"
                title="No completed simulation"
                message="Configure a run on the left. The platform will not invent a probability without one."
              />
            </Card>
          ) : (
            <>
              <div className="kpi-grid kpi-grid-4">
                <Kpi
                  label="P50 finish"
                  value={fmtDays(summary.makespan.p50, 0)}
                  sub={`${fmtDate(summary.makespan.p50_date)} · mean ${fmtDays(summary.makespan.mean, 0)}`}
                />
                <Kpi
                  label="P90 finish"
                  value={fmtDays(summary.makespan.p90, 0)}
                  sub={`${fmtDate(summary.makespan.p90_date)} · CVaR90 ${fmtDays(summary.makespan.cvar90, 0)}`}
                  tone="warn"
                />
                <Kpi
                  label="On-time probability"
                  value={fmtPct(summary.deadline.on_time_probability)}
                  sub={`vs ${fmtDate(summary.deadline.date)} · CI ${fmtPct(summary.deadline.on_time_ci?.[0])}–${fmtPct(summary.deadline.on_time_ci?.[1])}`}
                  tone={riskTone(summary.deadline.on_time_probability)}
                />
                <Kpi
                  label="Expected delay cost"
                  value={fmtMoney(summary.deadline.expected_delay_cost, currency, true)}
                  sub={`CVaR90 ${fmtMoney(summary.deadline.cvar90_delay_cost, currency, true)}`}
                  tone="bad"
                />
              </div>

              <div className="sim-meta">
                <div>
                  <Badge tone="info">SIM {shortId(data.latest.id)}</Badge>
                  <span>{data.latest.label || 'Untitled run'}</span>
                  <span>{data.latest.iterations.toLocaleString()} trials · seed {data.latest.seed}</span>
                  <span>{fmtDate(data.latest.created_at?.slice(0, 10))}</span>
                </div>
                <div className="row-actions">
                  <a className="btn btn-ghost btn-sm" href={api.simulations.downloadUrl(data.latest.id, 'json')}>
                    <Icon name="download" /> JSON
                  </a>
                  <a className="btn btn-ghost btn-sm" href={api.simulations.downloadUrl(data.latest.id, 'csv')}>
                    <Icon name="download" /> CSV
                  </a>
                </div>
              </div>

              <div className="dashboard-grid">
                <Card title="Makespan distribution" subtitle="Simulated project duration in working days." className="span-2">
                  <PlotChart
                    data={histogram}
                    height={300}
                    layout={{
                      xaxis: { title: 'Project duration (working days)' },
                      yaxis: { title: 'Trials' },
                      bargap: 0.03,
                      shapes: [
                        {
                          type: 'line',
                          x0: summary.makespan.p50,
                          x1: summary.makespan.p50,
                          y0: 0,
                          y1: 1,
                          yref: 'paper',
                          line: { color: PALETTE.amber, width: 1.5, dash: 'dash' },
                        },
                        {
                          type: 'line',
                          x0: summary.makespan.p90,
                          x1: summary.makespan.p90,
                          y0: 0,
                          y1: 1,
                          yref: 'paper',
                          line: { color: PALETTE.red, width: 1.5, dash: 'dash' },
                        },
                      ],
                      annotations: [
                        { x: summary.makespan.p50, y: 1, yref: 'paper', text: 'P50', showarrow: false, font: { color: PALETTE.amber, size: 11 } },
                        { x: summary.makespan.p90, y: 0.92, yref: 'paper', text: 'P90', showarrow: false, font: { color: PALETTE.red, size: 11 } },
                      ],
                    }}
                  />
                </Card>

                <Card title="Convergence" eyebrow="Is the estimate stable?">
                  <dl className="fact-list dense">
                    <div><dt>Batch-means relative SE</dt><dd>{fmtPct(summary.convergence.relative_se, 2)}</dd></div>
                    <div><dt>Criterion</dt><dd><Badge tone={summary.convergence.converged ? 'good' : 'warn'}>{summary.convergence.converged ? 'met' : 'not met'}</Badge></dd></div>
                    <div><dt>Recommended iterations</dt><dd>{fmtNumber(summary.convergence.recommended_iterations)}</dd></div>
                    <div><dt>Trials per second</dt><dd>{fmtNumber(summary.engine.trials_per_second)}</dd></div>
                    <div><dt>Elapsed</dt><dd>{summary.engine.elapsed_seconds}s</dd></div>
                    <div><dt>Infeasible trials</dt><dd>{summary.engine.infeasible_trials}</dd></div>
                  </dl>
                  <Callout tone={summary.convergence.converged ? 'good' : 'warn'}>
                    {summary.convergence.converged
                      ? 'The relative standard error is below the 1% criterion. More trials would still narrow the interval.'
                      : 'The run has not met the 1% relative standard error criterion. Increase iterations before making a high-stakes decision.'}
                  </Callout>
                </Card>
              </div>

              <div className="dashboard-grid">
                <Card title="Completion-date curve" subtitle="Probability the program finishes by a given working-day offset." className="span-2">
                  <PlotChart
                    data={curve}
                    height={280}
                    layout={{
                      xaxis: { title: 'Working-day offset' },
                      yaxis: { title: 'Cumulative probability (%)', range: [0, 102], ticksuffix: '%' },
                    }}
                  />
                </Card>
                <Card title="Percentile table" eyebrow="Distribution">
                  <div className="table-wrap">
                    <table className="compact">
                      <thead><tr><th>Statistic</th><th className="num">Days</th><th>Date</th></tr></thead>
                      <tbody>
                        <tr><td>P10</td><td className="num">{fmtDays(summary.makespan.p10, 0)}</td><td>{fmtDate(summary.makespan.p10_date)}</td></tr>
                        <tr><td>P50</td><td className="num strong">{fmtDays(summary.makespan.p50, 0)}</td><td>{fmtDate(summary.makespan.p50_date)}</td></tr>
                        <tr><td>P80</td><td className="num">{fmtDays(summary.makespan.p80, 0)}</td><td>{fmtDate(summary.makespan.p80_date)}</td></tr>
                        <tr><td>P90</td><td className="num strong">{fmtDays(summary.makespan.p90, 0)}</td><td>{fmtDate(summary.makespan.p90_date)}</td></tr>
                        <tr><td>P95</td><td className="num">{fmtDays(summary.makespan.p95, 0)}</td><td>—</td></tr>
                        <tr><td>CVaR90</td><td className="num">{fmtDays(summary.makespan.cvar90, 0)}</td><td>—</td></tr>
                      </tbody>
                    </table>
                  </div>
                </Card>
              </div>

              <div className="two-col">
                <Card title="Deterministic vs stochastic" eyebrow="No blending">
                  <dl className="fact-list dense">
                    <div><dt>CPM (logic only)</dt><dd>{fmtDays(summary.deterministic.cpm_makespan, 0)} · {fmtDate(summary.deterministic.cpm_finish_date)}</dd></div>
                    <div><dt>Base SGS (resource-feasible)</dt><dd>{fmtDays(summary.deterministic.sgs_base_makespan, 0)}</dd></div>
                    <div><dt>Capacity delay</dt><dd>{fmtDays(summary.deterministic.capacity_delay_days, 0)}</dd></div>
                    <div><dt>Monte Carlo P50</dt><dd>{fmtDays(summary.makespan.p50, 0)}</dd></div>
                    <div><dt>Monte Carlo P90</dt><dd>{fmtDays(summary.makespan.p90, 0)}</dd></div>
                  </dl>
                  <p className="muted-small">
                    The difference between SGS and P50 is execution risk, not schedule logic. The CPM-to-SGS gap is
                    capacity and material contention.
                  </p>
                </Card>
                <Card title="Cost decomposition" eyebrow="Expected value">
                  <div className="table-wrap">
                    <table className="compact">
                      <thead><tr><th>Component</th><th className="num">Expected cost</th></tr></thead>
                      <tbody>
                        {Object.entries(summary.cost.breakdown || {}).map(([key, value]) => (
                          <tr key={key}>
                            <td>{key.replaceAll('_', ' ')}</td>
                            <td className="num">{fmtMoney(value as number, currency)}</td>
                          </tr>
                        ))}
                        <tr className="total-row">
                          <td>Expected incremental cost</td>
                          <td className="num strong">{fmtMoney(summary.cost.expected_incremental_cost, currency)}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </Card>
              </div>

              {(summary.warnings?.length > 0 || summary.solver_validation) && (
                <Card title="Validation and warnings" eyebrow="Model honesty">
                  {summary.warnings?.length > 0 && (
                    <Callout tone="warn" title="Run warnings">
                      <ul>{summary.warnings.map((warning: string) => <li key={warning}>{warning}</li>)}</ul>
                    </Callout>
                  )}
                  {summary.solver_validation && (
                    <div className="table-wrap">
                      <table className="compact">
                        <thead><tr><th>Check</th><th>Result</th></tr></thead>
                        <tbody>
                          {Object.entries(summary.solver_validation).map(([key, value]) => (
                            <tr key={key}><td>{key.replaceAll('_', ' ')}</td><td>{String(value)}</td></tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Card>
              )}
            </>
          )}
        </div>
      </div>

      <Card title="Run history" subtitle="Every completed run is immutable and reproducible from its seed and configuration." className="table-card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>Label</th>
                <th>Scenario</th>
                <th className="num">Iterations</th>
                <th className="num">Seed</th>
                <th className="num">P50</th>
                <th className="num">P90</th>
                <th className="num">On-time</th>
                <th className="num">Expected delay cost</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {data.history.map((row: any) => (
                <tr key={row.id} className={row.id === data.latest?.id ? 'selected-row' : ''}>
                  <td><code>{shortId(row.id)}</code></td>
                  <td>{row.label || '—'}</td>
                  <td>{row.scenario_name || 'Baseline'}</td>
                  <td className="num">{row.iterations.toLocaleString()}</td>
                  <td className="num">{row.seed}</td>
                  <td className="num">{fmtDays(row.p50, 0)}</td>
                  <td className="num">{fmtDays(row.p90, 0)}</td>
                  <td className="num">{fmtPct(row.on_time_probability)}</td>
                  <td className="num">{fmtMoney(row.expected_delay_cost, currency)}</td>
                  <td>{fmtDate(row.created_at?.slice(0, 10))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
