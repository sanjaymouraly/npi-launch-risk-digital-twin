import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ApiError, api } from '../api'
import { useApi } from '../hooks'
import PlotChart, { PALETTE } from '../components/Plot'
import {
  Badge,
  Button,
  Callout,
  Card,
  EmptyState,
  ErrorState,
  Icon,
  Kpi,
  Loading,
  PageHeader,
} from '../components/ui'
import { fmtDays, fmtMoney, fmtPct, riskTone } from '../utils'

const KIND_COLORS: Record<string, string> = {
  task_duration: PALETTE.navy,
  risk_event: PALETTE.amber,
  supplier_disruption: PALETTE.teal,
}

export default function RiskPage() {
  const { projectId = '' } = useParams()
  const [sobol, setSobol] = useState<any>(null)
  const [loo, setLoo] = useState<any>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const { data, error, loading, reload } = useApi(async () => {
    const project = await api.projects.get(projectId)
    let simulation = null
    try {
      simulation = await api.simulations.latest(projectId)
    } catch (err) {
      if (!(err instanceof ApiError) || err.status !== 404) throw err
    }
    return { project, simulation }
  }, [projectId])

  const sensitivity = data?.simulation?.summary?.attribution?.sensitivity || []
  const tornado = data?.simulation?.summary?.attribution?.tornado || []
  const dependencies = data?.simulation?.summary?.attribution?.dependency_criticality || []
  const riskEvents = data?.simulation?.summary?.risks || []
  const summary = data?.simulation?.summary

  const sensitivityPlot = useMemo(() => {
    const rows = [...sensitivity].slice(0, 12).reverse()
    return [
      {
        type: 'bar',
        orientation: 'h',
        x: rows.map((row: any) => row.correlation),
        y: rows.map((row: any) => row.input),
        marker: { color: rows.map((row: any) => KIND_COLORS[row.kind] || PALETTE.slate) },
        text: rows.map((row: any) => `${row.correlation >= 0 ? '+' : ''}${row.correlation.toFixed(2)}`),
        textposition: 'outside',
        cliponaxis: false,
        customdata: rows.map((row: any) => [row.method, row.kind]),
        hovertemplate: '%{y}<br>Correlation %{x:.3f}<br>%{customdata[0]}<extra></extra>',
      },
    ]
  }, [sensitivity])

  const tornadoPlot = useMemo(() => {
    const rows = [...tornado].slice(0, 10).reverse()
    return [
      {
        type: 'bar',
        orientation: 'h',
        name: '−20% duration',
        y: rows.map((row: any) => row.input),
        x: rows.map((row: any) => row.low_case - row.base),
        marker: { color: PALETTE.teal },
        hovertemplate: '%{y}<br>Low case %{x:+.1f}d vs base<extra></extra>',
      },
      {
        type: 'bar',
        orientation: 'h',
        name: '+20% duration',
        y: rows.map((row: any) => row.input),
        x: rows.map((row: any) => row.high_case - row.base),
        marker: { color: PALETTE.red },
        hovertemplate: '%{y}<br>High case %{x:+.1f}d vs base<extra></extra>',
      },
    ]
  }, [tornado])

  const runSobol = async () => {
    setBusy('sobol')
    setActionError(null)
    try {
      const result = await api.simulations.sobol(projectId, { n_base: 256, seed: 42 })
      setSobol(result)
    } catch (err: any) {
      setActionError(err?.message || 'Sobol analysis failed')
    } finally {
      setBusy(null)
    }
  }

  const runLoo = async () => {
    setBusy('loo')
    setActionError(null)
    try {
      const result = await api.simulations.leaveOneOut(projectId, { iterations: 400, limit: 5 })
      setLoo(result)
    } catch (err: any) {
      setActionError(err?.message || 'Leave-one-out analysis failed')
    } finally {
      setBusy(null)
    }
  }

  if (loading && !data) return <Loading label="Loading attribution" />
  if (error) return <ErrorState message={error} retry={reload} />
  if (!data) return null

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${data.project.key} · risk attribution`}
        title="What moves the launch date?"
        description="Empirical association, deterministic sensitivity and model-internal counterfactuals. Correlation is explicitly not causation."
        actions={
          <>
            <Button variant="outline" onClick={runSobol} loading={busy === 'sobol'} disabled={!summary}>
              Run Sobol
            </Button>
            <Button variant="outline" onClick={runLoo} loading={busy === 'loo'} disabled={!summary}>
              Leave-one-out
            </Button>
          </>
        }
      />
      {actionError && <div className="inline-error">{actionError}</div>}

      {!summary ? (
        <Card>
          <EmptyState
            icon="◇"
            title="No empirical attribution yet"
            message="A Monte Carlo run is required to attribute makespan variance. The risk register alone cannot tell you what drives the date."
            action={
              <Button onClick={() => (window.location.href = `/projects/${projectId}/simulation`)}>
                Run a simulation
              </Button>
            }
          />
        </Card>
      ) : (
        <>
          <div className="kpi-grid kpi-grid-4">
            <Kpi
              label="On-time probability"
              value={fmtPct(summary.deadline.on_time_probability)}
              sub={`95% CI ${fmtPct(summary.deadline.on_time_ci?.[0])}–${fmtPct(summary.deadline.on_time_ci?.[1])}`}
              tone={riskTone(summary.deadline.on_time_probability)}
            />
            <Kpi
              label="Expected delay"
              value={fmtDays(summary.deadline.expected_delay_days)}
              sub={`P90 delay ${fmtDays(summary.deadline.p90_delay_days)}`}
              tone="warn"
            />
            <Kpi
              label="Expected delay cost"
              value={fmtMoney(summary.deadline.expected_delay_cost, data.project.currency, true)}
              sub={`CVaR90 ${fmtMoney(summary.deadline.cvar90_delay_cost, data.project.currency, true)}`}
              tone="bad"
            />
            <Kpi
              label="Empirical drivers measured"
              value={sensitivity.length}
              sub={`${riskEvents.length} discrete risks · ${(data.simulation?.iterations ?? 0).toLocaleString()} trials`}
              tone="neutral"
            />
          </div>

          <div className="dashboard-grid">
            <Card
              title="Rank-correlation sensitivity"
              subtitle="Spearman ρ between each sampled input and the simulated makespan. Association only."
              eyebrow="What co-moves with the date"
              className="span-2"
              actions={<Badge tone="info">SIM {data.simulation?.id.slice(0, 8)}</Badge>}
            >
              <PlotChart
                data={sensitivityPlot}
                height={Math.max(300, Math.min(12, sensitivity.length) * 29 + 70)}
                layout={{
                  xaxis: { title: 'Spearman correlation with makespan', range: [-1, 1], zeroline: true, zerolinecolor: '#9aa8b8' },
                  yaxis: { automargin: true, tickfont: { size: 11 } },
                  margin: { l: 190, r: 40, t: 10, b: 44 },
                }}
              />
              <div className="chart-legend">
                <span><i style={{ background: PALETTE.navy }} />Task duration</span>
                <span><i style={{ background: PALETTE.amber }} />Risk event</span>
                <span><i style={{ background: PALETTE.teal }} />Supplier disruption</span>
              </div>
              <Callout tone="warn" title="Interpretation guardrail">
                A high ρ means the input and the date move together inside the model. It does not prove that changing
                the input would move the real launch date by the same amount.
              </Callout>
            </Card>

            <Card
              title="Tail posture"
              subtitle="Cost of delay is a model estimate derived from the program's daily delay cost."
              eyebrow="Downside"
            >
              <dl className="fact-list dense">
                <div><dt>Probability of any delay</dt><dd>{fmtPct(summary.deadline.probability_of_delay)}</dd></div>
                <div><dt>P90 delay</dt><dd>{fmtDays(summary.deadline.p90_delay_days)}</dd></div>
                <div><dt>Cost at risk</dt><dd>{fmtMoney(summary.deadline.cost_at_risk, data.project.currency)}</dd></div>
                <div><dt>CVaR90 delay cost</dt><dd>{fmtMoney(summary.deadline.cvar90_delay_cost, data.project.currency)}</dd></div>
                <div><dt>Expected total cost</dt><dd>{fmtMoney(summary.cost.expected_total_cost, data.project.currency)}</dd></div>
                <div><dt>P90 total cost</dt><dd>{fmtMoney(summary.cost.p90_total_cost, data.project.currency)}</dd></div>
              </dl>
              <div className="divider" />
              <div className="mini-method">
                <Icon name="info" />
                <p>{summary.engine.percentile_method}.</p>
              </div>
            </Card>
          </div>

          <div className="dashboard-grid">
            <Card
              title="One-at-a-time tornado"
              subtitle="Deterministic schedule reruns with task durations shifted ±20%. This isolates logic and capacity effects, not probability."
              eyebrow="Deterministic sensitivity"
              className="span-2"
            >
              <PlotChart
                data={tornadoPlot}
                height={Math.max(300, Math.min(10, tornado.length) * 32 + 70)}
                layout={{
                  barmode: 'relative',
                  xaxis: { title: 'Makespan change vs base (working days)', zeroline: true, zerolinecolor: '#9aa8b8' },
                  yaxis: { automargin: true, tickfont: { size: 11 } },
                  margin: { l: 190, r: 30, t: 12, b: 46 },
                  showlegend: true,
                  legend: { orientation: 'h', x: 0, y: 1.12, font: { size: 11 } },
                }}
              />
              <p className="muted-small">
                The tornado is a deterministic rerun, so it does not include event probabilities or sampling error.
              </p>
            </Card>

            <Card title="Critical dependencies" eyebrow="Logic criticality">
              {dependencies.length ? (
                <ul className="dependency-list">
                  {dependencies.slice(0, 6).map((row: any, index: number) => (
                    <li key={`${row.from_id}-${row.to_id}`}>
                      <span className="dep-index">{index + 1}</span>
                      <div>
                        <strong>{row.from} → {row.to}</strong>
                        <span>{row.type} · lag {row.lag}d · present in {fmtPct(row.frequency, 0)} of critical paths</span>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="body-text">No dependency frequency data.</p>
              )}
              <Callout tone="info">
                Dependency criticality counts how often a link appears on a trial's critical path. It is a structural
                signal, not a probability of failure.
              </Callout>
            </Card>
          </div>

          <Card
            title="Discrete risk events"
            subtitle="Trigger rates and delay contributions come from the simulation. Input probability is the register assumption."
            className="table-card"
          >
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Risk</th>
                    <th>Category</th>
                    <th className="num">Input P</th>
                    <th className="num">Observed trigger</th>
                    <th className="num">Conditional delay</th>
                    <th className="num">Expected contribution</th>
                    <th className="num">P(launch impact)</th>
                    <th className="num">Expected cost</th>
                  </tr>
                </thead>
                <tbody>
                  {riskEvents.map((risk: any) => (
                    <tr key={risk.id}>
                      <td><div className="cell-title">{risk.name}</div></td>
                      <td><Badge tone="neutral">{risk.category}</Badge></td>
                      <td className="num">{fmtPct(risk.input_probability)}</td>
                      <td className="num">{fmtPct(risk.observed_trigger_rate)}</td>
                      <td className="num">{fmtDays(risk.conditional_delay_days)}</td>
                      <td className="num strong">{fmtDays(risk.expected_delay_contribution_days)}</td>
                      <td className="num">{fmtPct(risk.probability_of_launch_impact)}</td>
                      <td className="num">{fmtMoney(risk.expected_impact_cost, data.project.currency)}</td>
                    </tr>
                  ))}
                  {riskEvents.length === 0 && (
                    <tr><td colSpan={8}><span className="muted-small">No modelled risk events triggered in this run.</span></td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>

          <div className="two-col">
            <Card
              title="Variance-based Sobol indices"
              subtitle="First-order Saltelli estimator on the deterministic scheduler, with bootstrap intervals."
              eyebrow="Sensitivity, not causation"
              actions={<Button size="sm" variant="outline" onClick={runSobol} loading={busy === 'sobol'}>Recompute</Button>}
            >
              {sobol ? (
                <>
                  <div className="table-wrap">
                    <table className="compact">
                      <thead>
                        <tr><th>Input</th><th className="num">S1</th><th className="num">95% CI</th><th className="num">Bounds</th></tr>
                      </thead>
                      <tbody>
                        {sobol.indices.map((row: any, index: number) => (
                          <tr key={`${row.task_id}-${index}`}>
                            <td>{row.task || sobol.inputs?.[index]}</td>
                            <td className="num strong">{row.S1.toFixed(3)}</td>
                            <td className="num">{row.ci_low.toFixed(2)} – {row.ci_high.toFixed(2)}</td>
                            <td className="num">{row.bounds_days?.map((v: number) => v.toFixed(1)).join('–')}d</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="muted-small">{sobol.evaluations} schedule evaluations · n_base {sobol.n_base} · seed {sobol.seed}</p>
                  <Callout tone="warn">{sobol.caveat}</Callout>
                </>
              ) : (
                <p className="body-text">
                  Sobol decomposes the variance of the deterministic scheduler across up to six task durations. It is
                  more expensive and more rigorous than rank correlation; run it on demand.
                </p>
              )}
            </Card>

            <Card
              title="Leave-one-driver-out"
              subtitle="Neutralise each empirical driver, re-simulate with common random numbers, and measure the change."
              eyebrow="Model counterfactual"
              actions={<Button size="sm" variant="outline" onClick={runLoo} loading={busy === 'loo'}>Recompute</Button>}
            >
              {loo ? (
                <>
                  <div className="table-wrap">
                    <table className="compact">
                      <thead>
                        <tr><th>Driver</th><th className="num">Mean reduction</th><th className="num">P90 reduction</th><th className="num">On-time gain</th></tr>
                      </thead>
                      <tbody>
                        {loo.drivers.map((row: any) => (
                          <tr key={row.driver_id}>
                            <td>{row.driver}</td>
                            <td className="num strong">{fmtDays(row.expected_delay_reduction_days)}</td>
                            <td className="num">{fmtDays(row.p90_reduction_days)}</td>
                            <td className="num">{fmtPct(row.on_time_probability_gain)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="muted-small">
                    Base mean {fmtDays(loo.baseline.mean_makespan)} · on-time {fmtPct(loo.baseline.on_time_probability)} ·{" "}
                    {loo.baseline.iterations} paired iterations.
                  </p>
                  <Callout tone="warn">{loo.caveat}</Callout>
                </>
              ) : (
                <p className="body-text">
                  This is the closest the platform gets to a causal probe: remove a driver from the model, holding
                  random streams fixed, and re-run. It is still a model-internal counterfactual.
                </p>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
