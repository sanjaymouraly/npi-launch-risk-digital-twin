import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, Scenario } from '../api'
import { useApi } from '../hooks'
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
} from '../components/ui'
import { fmtDate, fmtDays, fmtMoney, fmtPct } from '../utils'

export default function ScenariosPage() {
  const { projectId = '' } = useParams()
  const [selectedId, setSelectedId] = useState<string>('')
  const [builderOpen, setBuilderOpen] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [comparison, setComparison] = useState<any>(null)
  const [preview, setPreview] = useState<any>(null)
  const [iterations, setIterations] = useState(800)
  const [seed, setSeed] = useState(42)
  const [busy, setBusy] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const { data, error, loading, reload } = useApi(async () => {
    const [project, scenarios, catalog] = await Promise.all([
      api.projects.get(projectId),
      api.scenarios.list(projectId),
      api.scenarios.interventions(projectId),
    ])
    return { project, scenarios, catalog }
  }, [projectId])

  useEffect(() => {
    if (!data?.scenarios.length) return
    if (selectedId && data.scenarios.some((scenario) => scenario.id === selectedId)) return
    const preferred = data.scenarios.find((scenario) => !scenario.is_baseline) || data.scenarios[0]
    setSelectedId(preferred.id)
  }, [data, selectedId])

  const selected = data?.scenarios.find((scenario) => scenario.id === selectedId) || null
  const baseline = data?.scenarios.find((scenario) => scenario.is_baseline) || null
  const catalog = data?.catalog.interventions || []
  const selectedCatalog = useMemo(() => catalog.filter((item: any) => picked.includes(item.id)), [catalog, picked])
  const pickedCost = selectedCatalog.reduce((sum: number, item: any) => sum + (item.cost || 0), 0)

  const curve = useMemo(() => {
    if (!comparison) return []
    const traces: any[] = []
    const baseRows = comparison.baseline.summary.completion_curve || []
    const scenRows = comparison.scenario.summary.completion_curve || []
    traces.push({
      type: 'scatter',
      mode: 'lines',
      name: 'Baseline',
      x: baseRows.map((row: any) => row.offset),
      y: baseRows.map((row: any) => row.probability * 100),
      line: { color: PALETTE.slate, width: 2.2, dash: 'dot' },
      hovertemplate: 'Baseline · %{x:.0f}d · %{y:.1f}%<extra></extra>',
    })
    traces.push({
      type: 'scatter',
      mode: 'lines',
      name: comparison.scenario.name,
      x: scenRows.map((row: any) => row.offset),
      y: scenRows.map((row: any) => row.probability * 100),
      line: { color: PALETTE.teal, width: 2.8 },
      fill: 'tozeroy',
      fillcolor: 'rgba(15,122,112,0.08)',
      hovertemplate: 'Scenario · %{x:.0f}d · %{y:.1f}%<extra></extra>',
    })
    return traces
  }, [comparison])

  const runAction = async (label: string, fn: () => Promise<any>, after?: (result: any) => void) => {
    setBusy(label)
    setActionError(null)
    try {
      const result = await fn()
      after?.(result)
      return result
    } catch (err: any) {
      setActionError(err?.message || 'Action failed')
    } finally {
      setBusy(null)
    }
  }

  const createScenario = async () => {
    if (!name.trim() || !picked.length) {
      setActionError('Give the scenario a name and select at least one intervention.')
      return
    }
    await runAction(
      'create',
      () =>
        api.scenarios.create(projectId, {
          name: name.trim(),
          description: description.trim(),
          interventions: selectedCatalog.map((item: any) => ({
            type: item.type,
            target_type: item.target_type,
            target_id: item.target_id,
            params: item.params,
            cost: item.cost,
            label: item.label,
            id: item.id,
          })),
        }),
      async (result) => {
        const refreshed = await api.scenarios.list(projectId)
        setSelectedId(result.id)
        setBuilderOpen(false)
        setName('')
        setDescription('')
        setPicked([])
        setComparison(null)
        setPreview(null)
        await reload()
        if (refreshed.length) setSelectedId(result.id)
      },
    )
  }

  const doPreview = () =>
    selected &&
    runAction('preview', () => api.scenarios.preview(projectId, selected.id), (result) => setPreview(result))

  const doCompare = () =>
    selected &&
    runAction(
      'compare',
      () => api.scenarios.compare(projectId, { scenario_id: selected.id, iterations, seed }),
      (result) => setComparison(result),
    )

  const approve = () =>
    selected &&
    runAction('approve', () => api.scenarios.patch(selected.id, { status: 'approved' }), async () => {
      await reload()
    })

  const clone = () => {
    if (!selected) return
    const cloneName = window.prompt('Name for the cloned scenario', `${selected.name} (copy)`)
    if (!cloneName) return
    runAction('clone', () => api.scenarios.clone(selected.id, cloneName), async (result) => {
      await reload()
      setSelectedId(result.id)
    })
  }

  const remove = () => {
    if (!selected || selected.is_baseline) return
    if (!window.confirm(`Delete scenario “${selected.name}”? This cannot be undone.`)) return
    runAction('delete', () => api.scenarios.remove(selected.id), async () => {
      setSelectedId(baseline?.id || '')
      setComparison(null)
      setPreview(null)
      await reload()
    })
  }

  if (loading && !data) return <Loading label="Loading scenarios" />
  if (error) return <ErrorState message={error} retry={reload} />
  if (!data) return null

  const currency = data.project.currency || 'USD'
  const scenarioRows: Scenario[] = data.scenarios

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${data.project.key} · scenarios`}
        title="Test interventions before committing spend"
        description="Scenarios are immutable snapshots of interventions. Comparisons use common random numbers, so the paired difference isolates the intervention effect."
        actions={
          <Button onClick={() => setBuilderOpen(!builderOpen)} icon={<Icon name="scenario" />}>
            New scenario
          </Button>
        }
      />
      {actionError && <div className="inline-error">{actionError}</div>}

      {builderOpen && (
        <Card title="Scenario builder" eyebrow="Catalog-derived interventions" className="builder-card">
          <div className="form-grid">
            <Field label="Scenario name">
              <input value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Dual-source MCU + capacity" />
            </Field>
            <Field label="Description">
              <input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What decision does this represent?" />
            </Field>
          </div>
          <div className="catalog-list">
            {catalog.map((item: any) => (
              <label key={item.id} className={`catalog-item ${picked.includes(item.id) ? 'picked' : ''}`}>
                <input
                  type="checkbox"
                  checked={picked.includes(item.id)}
                  onChange={(event) =>
                    setPicked((current) =>
                      event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id),
                    )
                  }
                />
                <div>
                  <div className="catalog-title">{item.label}</div>
                  <div className="catalog-meta">
                    <Badge tone="neutral">{item.category}</Badge>
                    <span>{item.type.replaceAll('_', ' ')}</span>
                    {item.expected_benefit_days !== null && item.expected_benefit_days !== undefined && (
                      <span>{fmtDays(item.expected_benefit_days)} estimated</span>
                    )}
                  </div>
                  {item.notes && <p>{item.notes}</p>}
                </div>
                <div className="catalog-cost">{fmtMoney(item.cost, currency)}</div>
              </label>
            ))}
            {catalog.length === 0 && <p className="body-text">No catalog interventions available.</p>}
          </div>
          <div className="builder-footer">
            <span>{picked.length} selected · {fmtMoney(pickedCost, currency)} total</span>
            <div className="row-actions">
              <Button variant="ghost" onClick={() => setBuilderOpen(false)}>Cancel</Button>
              <Button onClick={createScenario} loading={busy === 'create'}>Create scenario</Button>
            </div>
          </div>
        </Card>
      )}

      <div className="scenario-layout">
        <div className="scenario-list">
          {scenarioRows.map((scenario) => (
            <button
              key={scenario.id}
              className={`scenario-card ${scenario.id === selectedId ? 'selected' : ''}`}
              onClick={() => {
                setSelectedId(scenario.id)
                setComparison(null)
                setPreview(null)
              }}
            >
              <div className="scenario-card-head">
                <span>{scenario.name}</span>
                {scenario.is_baseline ? <Badge tone="info">baseline</Badge> : <Badge tone={scenario.status === 'approved' ? 'good' : 'neutral'}>{scenario.status}</Badge>}
              </div>
              <p>{scenario.description || (scenario.is_baseline ? 'Approved plan with no interventions.' : 'No description')}</p>
              <div className="scenario-card-meta">
                <span>{scenario.intervention_count} interventions</span>
                <span>{fmtMoney(scenario.total_cost, currency)}</span>
              </div>
            </button>
          ))}
          {scenarioRows.length === 0 && <EmptyState title="No scenarios" message="Create one from the intervention catalog." />}
        </div>

        <div className="scenario-detail">
          {selected ? (
            <>
              <Card
                title={selected.name}
                subtitle={selected.description}
                eyebrow={selected.is_baseline ? 'Approved baseline' : `Scenario · ${selected.status}`}
                actions={
                  <div className="row-actions">
                    {!selected.is_baseline && selected.status !== 'approved' && (
                      <Button size="sm" variant="outline" onClick={approve} loading={busy === 'approve'}>Approve</Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={clone} loading={busy === 'clone'}>Clone</Button>
                    {!selected.is_baseline && (
                      <Button size="sm" variant="ghost" onClick={remove} loading={busy === 'delete'}>Delete</Button>
                    )}
                  </div>
                }
              >
                <div className="kpi-grid kpi-grid-3">
                  <Kpi label="Interventions" value={selected.interventions.length} sub={selected.interventions.map((item) => item.type.replaceAll('_', ' ')).join(', ') || 'None'} />
                  <Kpi label="Total cost" value={fmtMoney(selected.total_cost, currency)} sub={`Against ${fmtMoney(data.project.intervention_budget, currency)} budget`} />
                  <Kpi label="Status" value={selected.status} sub={selected.approved_at ? `Approved ${fmtDate(selected.approved_at.slice(0, 10))}` : 'Not yet approved'} tone={selected.status === 'approved' ? 'good' : 'neutral'} />
                </div>
                {selected.interventions.length > 0 ? (
                  <div className="table-wrap">
                    <table className="compact">
                      <thead><tr><th>Intervention</th><th>Type</th><th>Target</th><th className="num">Cost</th></tr></thead>
                      <tbody>
                        {selected.interventions.map((item) => (
                          <tr key={item.id}>
                            <td>{item.label || item.type}</td>
                            <td><Badge tone="neutral">{item.type.replaceAll('_', ' ')}</Badge></td>
                            <td className="cell-sub">{item.target_type}{item.target_id ? ` ${item.target_id.slice(0, 8)}` : ''}</td>
                            <td className="num">{fmtMoney(item.cost, currency)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="body-text">The baseline has no interventions. Select a non-baseline scenario to compare.</p>
                )}

                {!selected.is_baseline && (
                  <div className="compare-controls">
                    <div className="form-grid">
                      <Field label="Paired iterations">
                        <input type="number" min={100} max={20000} value={iterations} onChange={(event) => setIterations(Number(event.target.value))} />
                      </Field>
                      <Field label="Seed">
                        <input type="number" min={0} value={seed} onChange={(event) => setSeed(Number(event.target.value))} />
                      </Field>
                    </div>
                    <div className="button-row">
                      <Button variant="outline" onClick={doPreview} loading={busy === 'preview'} icon={<Icon name="schedule" />}>
                        Deterministic preview
                      </Button>
                      <Button onClick={doCompare} loading={busy === 'compare'} icon={<Icon name="simulation" />}>
                        Simulate paired comparison
                      </Button>
                    </div>
                    <p className="muted-small">
                      Both arms share the same random streams. Negative paired delta means the scenario finishes earlier.
                    </p>
                  </div>
                )}
                {selected.interventions.length === 0 && !selected.is_baseline && (
                  <Callout tone="warn">This scenario contains no interventions; it will exactly reproduce the baseline.</Callout>
                )}
              </Card>

              {preview && (
                <Card title="Deterministic preview" eyebrow="Before stochastic verification">
                  <div className="kpi-grid kpi-grid-4">
                    <Kpi label="Baseline constrained" value={fmtDays(preview.baseline.constrained_days, 0)} sub={fmtDate(preview.baseline.constrained_finish)} />
                    <Kpi label="Scenario constrained" value={fmtDays(preview.scenario.constrained_days, 0)} sub={fmtDate(preview.scenario.constrained_finish)} tone="info" />
                    <Kpi label="Deterministic delta" value={fmtDays(preview.deterministic_delta_days)} sub="Working days, negative is faster" tone={preview.deterministic_delta_days < 0 ? 'good' : 'warn'} />
                    <Kpi label="Cost per day saved" value={preview.deterministic_delta_days < 0 ? fmtMoney(preview.cost_per_day_saved, currency) : '—'} sub={`${fmtMoney(preview.total_cost, currency)} intervention cost`} />
                  </div>
                  {preview.warnings?.length > 0 && (
                    <Callout tone="warn" title="Preview warnings"><ul>{preview.warnings.map((warning: string) => <li key={warning}>{warning}</li>)}</ul></Callout>
                  )}
                  <p className="muted-small">
                    Preview is a single deterministic solve. It does not replace the paired Monte Carlo comparison because
                    it cannot see probability shifts or interactions in the tails.
                  </p>
                </Card>
              )}

              {comparison && (
                <>
                  <div className="kpi-grid kpi-grid-4">
                    <Kpi
                      label="Paired mean delta"
                      value={fmtDays(comparison.paired_delta.mean_delta)}
                      sub={`95% CI ${fmtDays(comparison.paired_delta.ci95_delta?.[0])} to ${fmtDays(comparison.paired_delta.ci95_delta?.[1])}`}
                      tone={comparison.paired_delta.mean_delta < 0 ? 'good' : 'warn'}
                    />
                    <Kpi
                      label="On-time probability"
                      value={fmtPct(comparison.scenario.summary.deadline.on_time_probability)}
                      sub={`Baseline ${fmtPct(comparison.baseline.summary.deadline.on_time_probability)} · P(improve) ${fmtPct(comparison.paired_delta.probability_improvement)}`}
                      tone="info"
                    />
                    <Kpi
                      label="Net expected benefit"
                      value={fmtMoney(comparison.economics.net_expected_benefit, currency)}
                      sub={`Intervention cost ${fmtMoney(comparison.economics.intervention_cost, currency)}`}
                      tone={comparison.economics.net_expected_benefit > 0 ? 'good' : 'bad'}
                    />
                    <Kpi
                      label="ROI"
                      value={comparison.economics.roi.toFixed(2)}
                      sub="Net benefit ÷ intervention cost"
                      tone={comparison.economics.roi > 1 ? 'good' : comparison.economics.roi > 0 ? 'warn' : 'bad'}
                    />
                  </div>

                  <div className="dashboard-grid">
                    <Card title="Completion curves" subtitle="Cumulative probability of finishing by each offset. The gap is the intervention effect." className="span-2">
                      <PlotChart
                        data={curve}
                        height={310}
                        layout={{
                          xaxis: { title: 'Working-day offset' },
                          yaxis: { title: 'Probability (%)', ticksuffix: '%', range: [0, 102] },
                          showlegend: true,
                          legend: { orientation: 'h', x: 0, y: 1.12 },
                        }}
                      />
                    </Card>
                    <Card title="Paired difference" eyebrow="Common random numbers">
                      <dl className="fact-list dense">
                        <div><dt>Mean</dt><dd>{fmtDays(comparison.paired_delta.mean_delta)}</dd></div>
                        <div><dt>Median</dt><dd>{fmtDays(comparison.paired_delta.median_delta)}</dd></div>
                        <div><dt>P10 / P90 delta</dt><dd>{fmtDays(comparison.paired_delta.p10_delta)} / {fmtDays(comparison.paired_delta.p90_delta)}</dd></div>
                        <div><dt>P(improvement)</dt><dd>{fmtPct(comparison.paired_delta.probability_improvement)}</dd></div>
                        <div><dt>P(harm)</dt><dd>{fmtPct(comparison.paired_delta.probability_of_harm)}</dd></div>
                        <div><dt>Iterations</dt><dd>{comparison.paired_delta.iterations}</dd></div>
                      </dl>
                      <Callout tone="info" title="Comparison method">
                        {comparison.comparison_method?.note || 'Paired comparison with common random numbers.'}
                        {typeof comparison.comparison_method?.iterations === 'number' && (
                          <div className="muted-small">
                            {comparison.comparison_method.iterations.toLocaleString()} paired iterations · seed{' '}
                            {comparison.comparison_method.seed} · common random numbers{' '}
                            {comparison.comparison_method.common_random_numbers ? 'on' : 'off'}
                          </div>
                        )}
                      </Callout>
                    </Card>
                  </div>

                  <Card title="Arm-by-arm results" className="table-card">
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr><th>Arm</th><th className="num">P50</th><th className="num">P90</th><th className="num">CVaR90</th><th className="num">On-time</th><th className="num">Expected delay cost</th><th className="num">Intervention cost</th></tr>
                        </thead>
                        <tbody>
                          {[comparison.baseline, comparison.scenario].map((arm: any, index: number) => (
                            <tr key={arm.scenario_id || index}>
                              <td><div className="cell-title">{index === 0 ? 'Baseline' : arm.name}</div></td>
                              <td className="num">{fmtDays(arm.summary.makespan.p50, 0)}</td>
                              <td className="num">{fmtDays(arm.summary.makespan.p90, 0)}</td>
                              <td className="num">{fmtDays(arm.summary.makespan.cvar90, 0)}</td>
                              <td className="num">{fmtPct(arm.summary.deadline.on_time_probability)}</td>
                              <td className="num">{fmtMoney(arm.summary.deadline.expected_delay_cost, currency)}</td>
                              <td className="num">{arm.intervention_cost ? fmtMoney(arm.intervention_cost, currency) : '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Card>
                </>
              )}
            </>
          ) : (
            <Card><EmptyState title="Select a scenario" message="Choose a scenario to inspect, preview or compare." /></Card>
          )}
        </div>
      </div>
    </div>
  )
}
