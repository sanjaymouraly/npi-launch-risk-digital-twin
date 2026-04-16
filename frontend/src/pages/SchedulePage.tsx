import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, SchedulePayload } from '../api'
import { useApi } from '../hooks'
import PlotChart, { PALETTE } from '../components/Plot'
import { Badge, Button, Callout, Card, ErrorState, Icon, Kpi, Loading, PageHeader } from '../components/ui'
import { fmtDate, fmtDays, fmtPct } from '../utils'

const PHASE_COLORS: Record<string, string> = {
  Requirements: '#7a8ca3',
  Design: '#17456b',
  'Supply chain': '#8a5a9e',
  Prototype: '#0f7a70',
  'EVT / DVT': '#c07a1f',
  Tooling: '#6b5b45',
  'PVT / Quality': '#2f7d4f',
  Launch: '#b23a2f',
}

export default function SchedulePage() {
  const { projectId = '' } = useParams()
  const [mode, setMode] = useState<'constrained' | 'cpm'>('constrained')
  const { data, error, loading, reload } = useApi(() => api.projects.schedule(projectId), [projectId])

  const gantt = useMemo(() => {
    if (!data) return { traces: [] as any[], height: 360 }
    const constrained = mode === 'constrained'
    const tasks = constrained ? data.constrained?.tasks || [] : data.cpm.tasks
    const ordered = [...tasks].sort((a: any, b: any) => {
      const as = constrained ? a.start : a.earliest_start
      const bs = constrained ? b.start : b.earliest_start
      return bs - as
    })
    const traces: any[] = []
    const byPhase = new Map<string, any[]>()
    ordered.forEach((task: any) => {
      const phase = task.phase || 'Other'
      if (!byPhase.has(phase)) byPhase.set(phase, [])
      byPhase.get(phase)!.push(task)
    })
    byPhase.forEach((items, phase) => {
      const isDragging = false
      traces.push({
        type: 'bar',
        orientation: 'h',
        name: phase,
        y: items.map((task: any) => task.code),
        x: items.map((task: any) => {
          const start = constrained ? task.start : task.earliest_start
          const finish = constrained ? task.finish : task.earliest_finish
          return Math.max(0.1, finish - start)
        }),
        base: items.map((task: any) => (constrained ? task.start : task.earliest_start)),
        marker: {
          color: items.map((task: any) =>
            task.is_critical ? PALETTE.red : PHASE_COLORS[phase] || PALETTE.slate,
          ),
          line: { color: 'rgba(255,255,255,0.5)', width: 1 },
        },
        customdata: items.map((task: any) => [
          task.name,
          task.start_date,
          task.finish_date,
          task.total_float,
          task.is_critical ? 'critical' : `${task.total_float}d float`,
        ]),
        hovertemplate:
          '%{y} · %{customdata[0]}<br>%{customdata[1]} → %{customdata[2]}<br>%{customdata[3]}d float · %{customdata[4]}<extra></extra>',
        showlegend: false,
        isDragging,
      })
    })
    return { traces, height: Math.max(360, ordered.length * 22 + 90) }
  }, [data, mode])

  const bottleneckPlot = useMemo(() => {
    if (!data?.bottlenecks?.length) return []
    const rows = [...data.bottlenecks].slice(0, 8).reverse()
    return [
      {
        type: 'bar',
        orientation: 'h',
        x: rows.map((row: any) => row.utilization * 100),
        y: rows.map((row: any) => row.name),
        marker: {
          color: rows.map((row: any) =>
            row.utilization > 0.85 ? PALETTE.red : row.utilization > 0.6 ? PALETTE.amber : PALETTE.teal,
          ),
        },
        text: rows.map((row: any) => fmtPct(row.utilization, 0)),
        textposition: 'outside',
        cliponaxis: false,
        hovertemplate: '%{y}<br>Utilisation %{x:.1f}%<extra></extra>',
      },
    ]
  }, [data])

  if (loading && !data) return <Loading label="Solving schedule" />
  if (error) return <ErrorState message={error} retry={reload} />
  if (!data) return null

  const cpm = data.cpm
  const constrained = data.constrained
  const deadline = constrained?.deadline
  const taskRows = [...(constrained?.tasks || data.cpm.tasks)].sort((a: any, b: any) => {
    const as = constrained ? a.start : a.earliest_start
    const bs = constrained ? b.start : b.earliest_start
    return as - bs
  })

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${data.project_key} · schedule`}
        title="Schedule and capacity reality"
        description="The logic-only critical path and the resource-feasible plan are different answers. This page keeps them separate."
        actions={
          <Button variant="outline" onClick={reload} icon={<Icon name="refresh" />}>
            Re-solve
          </Button>
        }
      />

      <div className="kpi-grid kpi-grid-5">
        <Kpi label="Unconstrained CPM" value={fmtDays(cpm.project_duration, 0)} sub={`Finish ${fmtDate(cpm.finish_date)}`} />
        <Kpi label="Constrained CP-SAT" value={fmtDays(constrained?.makespan, 0)} sub={`Finish ${fmtDate(constrained?.project_finish_date)}`} tone="info" />
        <Kpi
          label="Capacity / material delay"
          value={fmtDays(constrained?.capacity_delay_days, 0)}
          sub="Constrained minus CPM"
          tone={(constrained?.capacity_delay_days || 0) > 0 ? 'warn' : 'good'}
        />
        <Kpi
          label="Deadline slack"
          value={fmtDays(deadline?.slack_days, 0)}
          sub={deadline?.feasible === false ? 'Deadline infeasible under capacity' : `vs ${fmtDate(data.deadline)}`}
          tone={deadline?.feasible === false ? 'bad' : 'good'}
        />
        <Kpi label="Critical tasks" value={cpm.critical_path.length} sub={`${taskRows.length} tasks in scope`} />
      </div>

      {deadline?.feasible === false && (
        <Callout tone="bad" title="Deadline infeasible for the current plan">
          The solver proved that the requested deadline cannot be met with current capacities, material release dates
          and logic. {deadline.conflicts?.length ? deadline.conflicts.join(' ') : 'Move the deadline or add capacity.'}
        </Callout>
      )}
      {data.validation.warnings.length > 0 && (
        <Callout tone="warn" title="Model warnings">
          <ul>{data.validation.warnings.map((warning: string) => <li key={warning}>{warning}</li>)}</ul>
        </Callout>
      )}

      <Card
        title="Schedule gantt"
        subtitle={`${mode === 'constrained' ? 'Resource-feasible plan' : 'Logic-only CPM'} · ${taskRows.length} tasks · critical tasks in red`}
        actions={
          <div className="segmented">
            <button className={mode === 'constrained' ? 'active' : ''} onClick={() => setMode('constrained')}>
              Constrained
            </button>
            <button className={mode === 'cpm' ? 'active' : ''} onClick={() => setMode('cpm')}>
              CPM logic
            </button>
          </div>
        }
        padded={false}
      >
        <div className="chart-wrap">
          <PlotChart
            data={gantt.traces}
            height={gantt.height}
            layout={{
              barmode: 'overlay',
              bargap: 0.28,
              xaxis: { title: 'Working-day offset from program start', zeroline: false },
              yaxis: { automargin: true, tickfont: { size: 10 } },
              margin: { l: 70, r: 20, t: 10, b: 44 },
            }}
          />
        </div>
        <div className="chart-legend">
          {Object.entries(PHASE_COLORS).map(([phase, color]) => (
            <span key={phase}><i style={{ background: color }} />{phase}</span>
          ))}
          <span><i style={{ background: PALETTE.red }} />Critical</span>
        </div>
      </Card>

      <div className="dashboard-grid">
        <Card title="Resource utilisation" eyebrow="Where capacity binds" className="span-2">
          {bottleneckPlot.length ? (
            <PlotChart
              data={bottleneckPlot}
              height={Math.max(260, Math.min(8, data.bottlenecks!.length) * 38 + 60)}
              layout={{
                xaxis: { title: 'Utilisation (%)', range: [0, 108], ticksuffix: '%' },
                yaxis: { automargin: true },
                margin: { l: 160, r: 30, t: 10, b: 42 },
              }}
            />
          ) : (
            <p className="body-text">No utilisation data.</p>
          )}
        </Card>
        <Card title="Solver provenance" eyebrow="How this was computed">
          <dl className="fact-list">
            <div><dt>Status</dt><dd><Badge tone={constrained?.feasible ? 'good' : 'bad'}>{constrained?.status || 'n/a'}</Badge></dd></div>
            <div><dt>Objective</dt><dd>{constrained?.objective || 'min_makespan'}</dd></div>
            <div><dt>Constraint model</dt><dd>Cumulative capacity, material release, all precedence types</dd></div>
            <div><dt>Duration rounding</dt><dd>Whole working days for CP-SAT</dd></div>
            <div><dt>Calendar</dt><dd>{data.calendar.working_days_per_week}-day week · {data.calendar.holidays.length} holidays</dd></div>
            <div><dt>Time limit</dt><dd>15 s per solve</dd></div>
          </dl>
          <Callout tone="info">
            CP-SAT is an optimiser; SGS inside the simulation is a feasibility heuristic. Their gap is measured
            explicitly, not assumed away.
          </Callout>
        </Card>
      </div>

      <Card title="Task register" subtitle="Constrained where available; float and criticality from the solver." className="table-card">
        <div className="table-wrap table-tall">
          <table>
            <thead>
              <tr>
                <th>Task</th>
                <th>Phase</th>
                <th>Start</th>
                <th>Finish</th>
                <th className="num">Duration</th>
                <th className="num">Float</th>
                <th>Resources</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {taskRows.map((task: any) => (
                <tr key={task.id}>
                  <td>
                    <div className="cell-title">{task.code} · {task.name}</div>
                    {task.is_gate && <span className="mini-tag">gate</span>}
                  </td>
                  <td>{task.phase}</td>
                  <td>{fmtDate(task.start_date)}</td>
                  <td>{fmtDate(task.finish_date)}</td>
                  <td className="num">{fmtDays(task.duration, 0)}</td>
                  <td className="num">{fmtDays(task.total_float, 0)}</td>
                  <td className="cell-sub">
                    {task.resources?.length
                      ? task.resources.map((resource: any) => resource.name).join(', ')
                      : '—'}
                  </td>
                  <td>
                    {task.is_critical ? <Badge tone="bad">critical</Badge> : <Badge tone="neutral">float</Badge>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
