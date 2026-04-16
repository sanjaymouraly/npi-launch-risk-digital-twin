import { useCallback, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
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
import { fmtDate, fmtDays, fmtMoney, fmtPct, riskTone } from '../utils'

const OBJECTIVES = [
  { value: 'min_combined_exposure', label: 'Minimise combined exposure (recommended)' },
  { value: 'max_probability', label: 'Maximise on-time probability' },
  { value: 'min_expected_delay', label: 'Minimise expected delay days' },
  { value: 'min_downside_risk', label: 'Minimise downside / P90 risk' },
  { value: 'min_cost', label: 'Minimise intervention cost' },
  { value: 'weighted', label: 'Weighted multi-objective' },
]

export default function OptimizationPage() {
  const { projectId = '' } = useParams()
  const [form, setForm] = useState({
    budget: 150000,
    objective: 'min_combined_exposure',
    max_selected: 4,
    pilot_iterations: 300,
    verification_iterations: 800,
    seed: 42,
    async_job: true,
  })
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)

  const { data, error, loading, reload } = useApi(async () => {
    const project = await api.projects.get(projectId)
    const history = await api.optimization.list(projectId)
    let latest: any = null
    try {
      latest = await api.optimization.latest(projectId)
    } catch {
      latest = null
    }
    return { project, history, latest }
  }, [projectId])

  const onJobComplete = useCallback(() => reload(), [reload])
  const { job, track, error: jobError } = useJobPoller(onJobComplete)
  const result = data?.latest?.results
  const recommendation = result?.recommendation
  const baseline = result?.verification?.baseline
  const currency = data?.project.currency || 'USD'

  const comparisonChart = useMemo(() => {
    if (!result || !recommendation) return []
    return [
      {
        type: 'bar',
        name: 'Verified P90',
        x: ['Baseline', 'Recommended'],
        y: [baseline.p90, recommendation.simulation.p90],
        marker: { color: [PALETTE.slate, PALETTE.teal] },
        text: [fmtDays(baseline.p90, 0), fmtDays(recommendation.simulation.p90, 0)],
        textposition: 'outside',
        hovertemplate: '%{x}<br>P90 %{y:.1f} days<extra></extra>',
      },
    ]
  }, [result, recommendation, baseline])

  const pareto = useMemo(() => {
    const rows = result?.selection?.pareto || []
    return [
      {
        type: 'scatter',
        mode: 'lines+markers',
        x: rows.map((row: any) => row.cost),
        y: rows.map((row: any) => row.benefit_days),
        line: { color: PALETTE.navy, width: 2 },
        marker: { size: 7, color: PALETTE.navy },
        customdata: rows.map((row: any) => [row.labels?.join('; ') || 'Baseline']),
        hovertemplate: 'Cost %{x:$,.0f}<br>Estimated benefit %{y:.1f}d<br>%{customdata[0]}<extra></extra>',
      },
    ]
  }, [result])

  const run = async () => {
    setRunError(null)
    setRunning(true)
    try {
      const response = await api.optimization.run(projectId, {
        budget: Number(form.budget),
        objective: form.objective,
        constraints: { max_selected: Number(form.max_selected) },
        pilot_iterations: Number(form.pilot_iterations),
        verification_iterations: Number(form.verification_iterations),
        seed: Number(form.seed),
        async_job: form.async_job,
      })
      if (response.async && response.job_id) track(response.job_id)
      else await reload()
    } catch (err: any) {
      setRunError(err?.message || 'Optimisation failed')
    } finally {
      setRunning(false)
    }
  }

  if (loading && !data) return <Loading label="Loading optimiser" />
  if (error) return <ErrorState message={error} retry={reload} />
  if (!data) return null

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${data.project.key} · optimiser`}
        title="Buy the best verified risk reduction"
        description="Candidates are generated from the real project, estimated with paired pilots, selected by CP-SAT under constraints, then re-simulated at higher fidelity."
        actions={<Badge tone="info">CP-SAT selection + Monte Carlo verification</Badge>}
      />

      <div className="opt-layout">
        <Card title="Optimisation setup" eyebrow="Budgets and constraints" className="opt-form-card">
          <div className="form-grid">
            <Field label="Budget" hint={`Project allowance ${fmtMoney(data.project.intervention_budget, currency)}`}>
              <input type="number" min={0} value={form.budget} onChange={(event) => setForm({ ...form, budget: Number(event.target.value) })} />
            </Field>
            <Field label="Max interventions">
              <input type="number" min={1} max={10} value={form.max_selected} onChange={(event) => setForm({ ...form, max_selected: Number(event.target.value) })} />
            </Field>
          </div>
          <Field label="Objective">
            <select value={form.objective} onChange={(event) => setForm({ ...form, objective: event.target.value })}>
              {OBJECTIVES.map((objective) => (
                <option key={objective.value} value={objective.value}>{objective.label}</option>
              ))}
            </select>
          </Field>
          <div className="form-grid">
            <Field label="Pilot iterations" hint="Per candidate; 100–2,000.">
              <input type="number" min={100} max={2000} value={form.pilot_iterations} onChange={(event) => setForm({ ...form, pilot_iterations: Number(event.target.value) })} />
            </Field>
            <Field label="Verification iterations" hint="Per portfolio; 200–5,000.">
              <input type="number" min={200} max={5000} value={form.verification_iterations} onChange={(event) => setForm({ ...form, verification_iterations: Number(event.target.value) })} />
            </Field>
          </div>
          <Field label="Seed" hint="Common random numbers across candidates and portfolios.">
            <input type="number" min={0} value={form.seed} onChange={(event) => setForm({ ...form, seed: Number(event.target.value) })} />
          </Field>
          <label className="switch-row">
            <input type="checkbox" checked={form.async_job} onChange={(event) => setForm({ ...form, async_job: event.target.checked })} />
            <span>Run as a background job</span>
          </label>
          <Button onClick={run} loading={running} className="full-width" icon={<Icon name="optimize" />}>
            Run optimisation
          </Button>
          {(runError || jobError) && <div className="inline-error">{runError || jobError}</div>}
          {job && (
            <div className="job-panel">
              <div className="job-head">
                <Badge tone={job.status === 'completed' ? 'good' : job.status === 'failed' ? 'bad' : 'info'}>{job.status}</Badge>
                <span className="muted-small">{Math.round(job.progress * 100)}%</span>
              </div>
              <ProgressBar value={job.progress} tone={job.status === 'failed' ? 'bad' : 'accent'} />
              <p className="muted-small">{job.message}</p>
              {job.status === 'failed' && <div className="inline-error">{job.error}</div>}
            </div>
          )}
          <div className="mini-method">
            <Icon name="alert" />
            <p>
              Optimiser scores are additive. The higher-fidelity verification measures interaction effects; the
              recommendation is chosen from verified portfolios, not raw scores.
            </p>
          </div>
        </Card>

        <div className="opt-results">
          {!result || !recommendation ? (
            <Card>
              <EmptyState
                icon="◇"
                title="No optimisation run yet"
                message="Set a budget and run the optimiser. It will not recommend a portfolio without verified simulation evidence."
              />
            </Card>
          ) : (
            <>
              <div className="kpi-grid kpi-grid-4">
                <Kpi label="Selected portfolio cost" value={fmtMoney(recommendation.intervention_cost, currency)} sub={`${fmtPct(recommendation.budget_utilization)} of budget`} />
                <Kpi
                  label="Verified P90"
                  value={fmtDays(recommendation.simulation.p90, 0)}
                  sub={`${fmtDate(recommendation.simulation.summary.makespan.p90_date)} · baseline ${fmtDays(baseline.p90, 0)}`}
                  tone={recommendation.simulation.p90 < baseline.p90 ? 'good' : 'warn'}
                />
                <Kpi
                  label="On-time probability"
                  value={fmtPct(recommendation.simulation.on_time_probability)}
                  sub={`Baseline ${fmtPct(baseline.on_time_probability)} · delta ${fmtPct(recommendation.simulation.on_time_probability - baseline.on_time_probability)}`}
                  tone={riskTone(recommendation.simulation.on_time_probability)}
                />
                <Kpi
                  label="Net economic benefit"
                  value={fmtMoney(recommendation.net_economic_benefit, currency)}
                  sub={`ROI ${recommendation.roi.toFixed(2)} · cost ${fmtMoney(recommendation.intervention_cost, currency)}`}
                  tone={recommendation.net_economic_benefit > 0 ? 'good' : 'bad'}
                />
              </div>

              <Card
                title="Recommended portfolio"
                subtitle={`Selected by CP-SAT (${result.selection.status}) and verified with ${result.verification.iterations.toLocaleString()} paired Monte Carlo trials.`}
                eyebrow="Decision"
                actions={<Badge tone={result.selection.optimal ? 'good' : 'warn'}>{result.selection.status}</Badge>}
              >
                <ol className="recommendation-list">
                  {recommendation.labels.map((label: string, index: number) => (
                    <li key={label}>
                      <span className="rec-index">{index + 1}</span>
                      <span>{label}</span>
                    </li>
                  ))}
                </ol>
                <div className="kpi-grid kpi-grid-4">
                  <div className="mini-stat"><span>Delay cost avoided</span><strong>{fmtMoney(recommendation.delay_cost_avoided, currency)}</strong></div>
                  <div className="mini-stat"><span>Incremental cost avoided</span><strong>{fmtMoney(recommendation.incremental_cost_avoided, currency)}</strong></div>
                  <div className="mini-stat"><span>P90 reduction</span><strong>{fmtDays(baseline.p90 - recommendation.simulation.p90)}</strong></div>
                  <div className="mini-stat"><span>Schedule verified</span><strong>{recommendation.schedule_verification?.feasible ? 'Feasible' : 'Check'}</strong></div>
                </div>
                {recommendation.warnings?.length > 0 && (
                  <Callout tone="warn" title="Warnings"><ul>{recommendation.warnings.map((warning: string) => <li key={warning}>{warning}</li>)}</ul></Callout>
                )}
                {recommendation.new_bottlenecks?.length > 0 && (
                  <Callout tone="info" title="New bottlenecks created by the portfolio">
                    {recommendation.new_bottlenecks.slice(0, 4).map((row: any) => `${row.name} (${fmtPct(row.utilization, 0)})`).join(', ')}
                  </Callout>
                )}
              </Card>

              <div className="dashboard-grid">
                <Card title="Verified P90 comparison" subtitle="Baseline versus recommended portfolio, same seed and simulation settings." className="span-2">
                  <PlotChart
                    data={comparisonChart}
                    height={280}
                    layout={{
                      yaxis: { title: 'P90 working days', range: [0, Math.max(baseline.p90, recommendation.simulation.p90) * 1.18] },
                      xaxis: { title: '' },
                      margin: { l: 60, r: 20, t: 20, b: 44 },
                    }}
                  />
                </Card>
                <Card title="Selection integrity" eyebrow="Verification">
                  <dl className="fact-list dense">
                    <div><dt>Estimated benefit</dt><dd>{fmtDays(result.selection.estimated_benefit_days)}</dd></div>
                    <div><dt>Verified benefit</dt><dd>{fmtDays(recommendation.delta.mean_makespan)}</dd></div>
                    <div><dt>Budget</dt><dd>{fmtMoney(result.budget, currency)}</dd></div>
                    <div><dt>Budget utilisation</dt><dd>{fmtPct(recommendation.budget_utilization)}</dd></div>
                    <div><dt>Portfolios verified</dt><dd>{result.verification.portfolios.length}</dd></div>
                    <div><dt>Feasibility</dt><dd>{Object.entries(result.selection.feasibility || {}).filter(([, value]) => value === true).length} checks passed</dd></div>
                  </dl>
                  <p className="muted-small">{result.verification.selection_rule}</p>
                </Card>
              </div>

              <div className="dashboard-grid">
                <Card title="Cost–benefit frontier" subtitle="Pareto-near portfolios scored by the optimiser. Cost is intervention spend; benefit is estimated days." className="span-2">
                  <PlotChart
                    data={pareto}
                    height={290}
                    layout={{
                      xaxis: { title: 'Intervention cost', tickprefix: '$', tickformat: ',.0f' },
                      yaxis: { title: 'Estimated benefit (working days)' },
                      margin: { l: 60, r: 20, t: 20, b: 50 },
                    }}
                  />
                </Card>
                <Card title="Method" eyebrow="What was actually done">
                  <ol className="method-steps">
                    {result.method.steps.map((step: string) => <li key={step}>{step}</li>)}
                  </ol>
                  <Callout tone="warn">{result.method.benefit_additivity_warning}</Callout>
                </Card>
              </div>
            </>
          )}
        </div>
      </div>

      {result && (
        <>
          <Card title="Candidate catalog" subtitle={`${result.catalog.length} candidates generated from the real project; estimates use paired pilot trials.`} className="table-card">
            <div className="table-wrap table-tall">
              <table>
                <thead>
                  <tr>
                    <th>Candidate</th>
                    <th>Category</th>
                    <th className="num">Cost</th>
                    <th className="num">Pilot benefit</th>
                    <th className="num">P90 gain</th>
                    <th className="num">On-time gain</th>
                    <th>Selected</th>
                    <th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {[...result.catalog]
                    .sort((a: any, b: any) => (b.expected_benefit_days || 0) - (a.expected_benefit_days || 0))
                    .map((item: any) => (
                      <tr key={item.id} className={recommendation.intervention_ids.includes(item.id) ? 'selected-row' : ''}>
                        <td><div className="cell-title">{item.label}</div><div className="cell-sub">{item.type.replaceAll('_', ' ')}</div></td>
                        <td><Badge tone="neutral">{item.category}</Badge></td>
                        <td className="num">{fmtMoney(item.cost, currency)}</td>
                        <td className="num strong">{fmtDays(item.expected_benefit_days)}</td>
                        <td className="num">{item.params?._p90_gain_days !== undefined ? fmtDays(item.params._p90_gain_days) : '—'}</td>
                        <td className="num">{fmtPct(item.expected_on_time_gain)}</td>
                        <td>{recommendation.intervention_ids.includes(item.id) ? <Badge tone="good">selected</Badge> : <span className="muted-small">—</span>}</td>
                        <td className="cell-sub">{item.notes}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="Optimisation history" subtitle="Every run records its constraints, seed and verification." className="table-card">
            <div className="table-wrap">
              <table>
                <thead><tr><th>Run</th><th>Objective</th><th className="num">Budget</th><th className="num">Cost</th><th>Status</th><th>Created</th></tr></thead>
                <tbody>
                  {data.history.map((row: any) => (
                    <tr key={row.id} className={row.id === data.latest?.id ? 'selected-row' : ''}>
                      <td><code>{row.id.slice(0, 8)}</code></td>
                      <td>{row.objective.replaceAll('_', ' ')}</td>
                      <td className="num">{fmtMoney(row.budget, currency)}</td>
                      <td className="num">{fmtMoney(row.intervention_cost, currency)}</td>
                      <td><Badge tone={row.status === 'completed' ? 'good' : 'warn'}>{row.status}</Badge></td>
                      <td>{fmtDate(row.created_at?.slice(0, 10))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
