import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useApi } from '../hooks'
import { Badge, Button, Callout, Card, EmptyState, ErrorState, Icon, Kpi, Loading, PageHeader } from '../components/ui'
import { fmtDate, fmtDays, fmtMoney, fmtPct, riskTone } from '../utils'

export default function ProjectOverview() {
  const { projectId = '' } = useParams()
  const navigate = useNavigate()
  const { data, error, loading, reload } = useApi(async () => {
    const [project, schedule, milestones] = await Promise.all([
      api.projects.get(projectId),
      api.projects.schedule(projectId),
      api.projects.milestones(projectId),
    ])
    let simulation = null
    try {
      simulation = await api.simulations.latest(projectId)
    } catch {
      simulation = null
    }
    return { project, schedule, milestones, simulation }
  }, [projectId])

  if (loading && !data) return <Loading label="Building program twin" />
  if (error) return <ErrorState message={error} retry={reload} />
  if (!data) return null

  const { project, schedule, milestones, simulation } = data
  const cpm = schedule.cpm
  const constrained = schedule.constrained
  const summary = simulation?.summary
  const onTime = summary?.deadline?.on_time_probability
  const tone = riskTone(onTime)
  const topDrivers = (summary?.attribution?.sensitivity || []).slice(0, 4)
  const topSuppliers = (simulation?.summary?.suppliers || []).slice(0, 3)
  const atRiskMilestones = (milestones.milestones || [])
    .filter((m: any) => m.on_time_probability !== null && m.on_time_probability !== undefined)
    .sort((a: any, b: any) => a.on_time_probability - b.on_time_probability)
    .slice(0, 3)

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${project.key} · ${project.status}`}
        title={project.name}
        description={project.description}
        actions={
          <>
            <Button variant="outline" onClick={() => navigate(`/projects/${projectId}/assistant`)} icon={<Icon name="ai" />}>
              Ask the copilot
            </Button>
            <Button onClick={() => navigate(`/projects/${projectId}/simulation`)} icon={<Icon name="simulation" />}>
              Run simulation
            </Button>
          </>
        }
      />

      <div className="kpi-grid kpi-grid-6">
        <Kpi label="CPM duration" value={fmtDays(cpm.project_duration, 0)} sub={`Logic only · finish ${fmtDate(cpm.finish_date)}`} />
        <Kpi
          label="Constrained duration"
          value={fmtDays(constrained?.makespan, 0)}
          sub={`CP-SAT · finish ${fmtDate(constrained?.project_finish_date)}`}
          tone="info"
        />
        <Kpi
          label="Capacity delay"
          value={fmtDays(constrained?.capacity_delay_days, 0)}
          sub="Difference between CPM and CP-SAT"
          tone={(constrained?.capacity_delay_days || 0) > 0 ? 'warn' : 'good'}
        />
        <Kpi
          label="P50 / P90"
          value={summary ? `${fmtDays(summary.makespan.p50, 0)} / ${fmtDays(summary.makespan.p90, 0)}` : '—'}
          sub={summary ? `Latest run · ${summary.engine.iterations.toLocaleString()} trials` : 'No simulation yet'}
        />
        <Kpi
          label="On-time probability"
          value={summary ? fmtPct(onTime) : '—'}
          sub={summary ? `vs ${fmtDate(summary.deadline.date)}` : 'Run a simulation to quantify'}
          tone={summary ? tone : 'neutral'}
        />
        <Kpi
          label="Expected delay cost"
          value={summary ? fmtMoney(summary.deadline.expected_delay_cost, project.currency, true) : '—'}
          sub={summary ? `CVaR90 ${fmtMoney(summary.deadline.cvar90_delay_cost, project.currency, true)}` : 'Model estimate'}
          tone={summary && summary.deadline.expected_delay_cost > 0 ? 'warn' : 'neutral'}
        />
      </div>

      <div className="dashboard-grid">
        <Card title="The schedule, stated honestly" eyebrow="Three different questions" className="span-2">
          <div className="schedule-stack">
            <div className="schedule-lane">
              <div className="lane-head">
                <span className="lane-tag">Logic</span>
                <strong>Unconstrained CPM</strong>
                <span className="lane-value">{fmtDays(cpm.project_duration, 0)}</span>
              </div>
              <div className="lane-bar">
                <div className="lane-fill cpm" style={{ width: '68%' }} />
              </div>
              <p>
                Earliest possible schedule with all FS/SS/FF/SF dependencies and the working-day calendar.
                Resources are ignored, so this is <em>not</em> a delivery date.
              </p>
            </div>
            <div className="schedule-lane">
              <div className="lane-head">
                <span className="lane-tag">Feasible plan</span>
                <strong>Resource-constrained CP-SAT</strong>
                <span className="lane-value">{fmtDays(constrained?.makespan, 0)}</span>
              </div>
              <div className="lane-bar">
                <div className="lane-fill cpsat" style={{ width: `${((constrained?.makespan || cpm.project_duration) / (summary?.makespan?.p90 || cpm.project_duration)) * 100}%` }} />
              </div>
              <p>
                Respects team, lab and line capacity plus material release dates. Solver status:{" "}
                <strong>{constrained?.status || 'not run'}</strong>. This is the deterministic delivery plan.
              </p>
            </div>
            <div className="schedule-lane">
              <div className="lane-head">
                <span className="lane-tag">Risk</span>
                <strong>Monte Carlo P90</strong>
                <span className="lane-value">{summary ? fmtDays(summary.makespan.p90, 0) : '—'}</span>
              </div>
              <div className="lane-bar">
                <div
                  className="lane-fill risk"
                  style={{ width: summary ? `${Math.min(100, (summary.makespan.p90 / Math.max(1, summary.makespan.p90)) * 100)}%` : '0%' }}
                />
              </div>
              <p>
                90% of resource-feasible trials finish by this date. The tail reflects supplier, validation,
                capacity and execution variability — not schedule logic.
              </p>
            </div>
          </div>
          {schedule.comparison && <Callout tone="info" title="Headline">{schedule.comparison.headline}</Callout>}
          {!schedule.validation.valid && (
            <Callout tone="bad" title="Validation errors">
              <ul>{schedule.validation.errors.map((item: string) => <li key={item}>{item}</li>)}</ul>
            </Callout>
          )}
        </Card>

        <Card title="Program facts" eyebrow="Digital twin scope">
          <dl className="fact-list">
            <div><dt>Owner</dt><dd>{project.owner}</dd></div>
            <div><dt>Product</dt><dd>{project.product}</dd></div>
            <div><dt>Start</dt><dd>{fmtDate(project.start_date)}</dd></div>
            <div><dt>Launch deadline</dt><dd>{fmtDate(project.launch_deadline)}</dd></div>
            <div><dt>Cost of delay</dt><dd>{fmtMoney(project.delay_cost_per_day, project.currency)}/day</dd></div>
            <div><dt>Intervention budget</dt><dd>{fmtMoney(project.intervention_budget, project.currency)}</dd></div>
            <div><dt>Scope</dt><dd>{project.tasks.length} tasks · {project.resources.length} resources · {project.suppliers.length} suppliers</dd></div>
            <div><dt>Risk register</dt><dd>{project.risks.length} risks · {project.milestones.length} milestones</dd></div>
          </dl>
          <div className="button-row">
            <Link className="btn btn-outline btn-sm" to={`/projects/${projectId}/schedule`}>Schedule detail</Link>
            <Link className="btn btn-ghost btn-sm" to={`/projects/${projectId}/decisions`}>Audit trail</Link>
          </div>
        </Card>
      </div>

      <div className="three-col">
        <Card
          title="What the model says is driving risk"
          eyebrow="Empirical attribution"
          actions={<Link className="text-link" to={`/projects/${projectId}/risks`}>Full analysis →</Link>}
        >
          {topDrivers.length ? (
            <ol className="driver-list">
              {topDrivers.map((driver: any) => (
                <li key={driver.input_id || driver.input}>
                  <div className="driver-main">
                    <span>{driver.input}</span>
                    <strong>{driver.correlation >= 0 ? '+' : ''}{driver.correlation.toFixed(3)}</strong>
                  </div>
                  <div className="driver-meta">{driver.method} · association, not causation</div>
                  <div className="driver-track">
                    <div style={{ width: `${Math.min(100, Math.abs(driver.correlation) * 100)}%` }} />
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <EmptyState
              title="No attribution yet"
              message="Run a Monte Carlo simulation to measure which inputs move the makespan."
              action={<Button size="sm" onClick={() => navigate(`/projects/${projectId}/simulation`)}>Run simulation</Button>}
            />
          )}
        </Card>

        <Card
          title="Supplier concentration"
          eyebrow="Simulated impact"
          actions={<Link className="text-link" to={`/projects/${projectId}/suppliers`}>Exposure →</Link>}
        >
          {topSuppliers.length ? (
            <ul className="supplier-mini">
              {topSuppliers.map((supplier: any) => (
                <li key={supplier.id}>
                  <div>
                    <strong>{supplier.name}</strong>
                    <span>{supplier.category} · {supplier.region}</span>
                  </div>
                  <div className="supplier-mini-value">
                    <span>{supplier.expected_delay_contribution_days.toFixed(1)}d</span>
                    <small>expected contribution</small>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="body-text">No simulation supplier attribution. Open the supply page for BOM-derived exposure.</p>
          )}
        </Card>

        <Card
          title="Milestones at risk"
          eyebrow="Gate confidence"
          actions={<Link className="text-link" to={`/projects/${projectId}/milestones`}>All gates →</Link>}
        >
          {atRiskMilestones.length ? (
            <ul className="milestone-mini">
              {atRiskMilestones.map((milestone: any) => (
                <li key={milestone.id || milestone.name}>
                  <div>
                    <strong>{milestone.name}</strong>
                    <span>Due {fmtDate(milestone.due_date)} · P90 {fmtDate(milestone.p90_date)}</span>
                  </div>
                  <Badge tone={riskTone(milestone.on_time_probability)}>{fmtPct(milestone.on_time_probability, 0)}</Badge>
                </li>
              ))}
            </ul>
          ) : (
            <p className="body-text">No probabilistic milestone forecast. Run a simulation or open the milestone page.</p>
          )}
          {(summary?.warnings?.length ?? 0) > 0 && (
            <div className="warning-box">
              <Icon name="alert" />
              <span>{summary?.warnings?.[0]}</span>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
