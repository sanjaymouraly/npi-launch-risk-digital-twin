import { useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
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
import { fmtDateTime, fmtDays, fmtMoney, fmtPct } from '../utils'

export default function DecisionsPage() {
  const { projectId = '' } = useParams()
  const { data, error, loading, reload } = useApi(async () => {
    const [project, audit, snapshots, calibration, jobs, scenarios, optimizations] = await Promise.all([
      api.projects.get(projectId),
      api.projects.audit(projectId, 100),
      api.projects.snapshots(projectId),
      api.simulations.calibration(projectId),
      api.jobs.list(projectId),
      api.scenarios.list(projectId),
      api.optimization.list(projectId),
    ])
    return { project, audit, snapshots, calibration, jobs, scenarios, optimizations }
  }, [projectId])

  const snapshotChart = useMemo(() => {
    const rows = [...(data?.snapshots || [])]
      .filter((row: any) => row.p90_days !== null)
      .sort((a: any, b: any) => a.created_at.localeCompare(b.created_at))
    return [
      {
        type: 'scatter',
        mode: 'lines+markers',
        x: rows.map((row: any) => row.created_at),
        y: rows.map((row: any) => row.p90_days),
        line: { color: PALETTE.navy, width: 2 },
        marker: { size: 7 },
        name: 'P90 (days)',
        hovertemplate: '%{x}<br>P90 %{y:.1f} days<extra></extra>',
      },
      {
        type: 'scatter',
        mode: 'lines+markers',
        x: rows.map((row: any) => row.created_at),
        y: rows.map((row: any) => row.p50_days),
        line: { color: PALETTE.teal, width: 2, dash: 'dot' },
        marker: { size: 6 },
        name: 'P50 (days)',
        hovertemplate: '%{x}<br>P50 %{y:.1f} days<extra></extra>',
      },
    ]
  }, [data])

  if (loading && !data) return <Loading label="Loading decision record" />
  if (error) return <ErrorState message={error} retry={reload} />
  if (!data) return null

  const currency = data.project.currency || 'USD'
  const approvedScenarios = data.scenarios.filter((scenario: any) => scenario.status === 'approved')
  const completedJobs = data.jobs.filter((job: any) => job.status === 'completed')
  const latestOptimization = data.optimizations[0]

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${data.project.key} · decisions & audit`}
        title="The record of what was decided"
        description="Every run, scenario change, approval and copilot answer is written to an immutable audit trail with its actor and payload."
        actions={<Button variant="outline" onClick={reload} icon={<Icon name="refresh" />}>Refresh</Button>}
      />

      <div className="kpi-grid kpi-grid-4">
        <Kpi label="Audit entries" value={data.audit.length} sub="Most recent 100 shown" />
        <Kpi label="Approved scenarios" value={approvedScenarios.length} sub={`${data.scenarios.length} total`} tone={approvedScenarios.length ? 'good' : 'neutral'} />
        <Kpi label="Completed jobs" value={completedJobs.length} sub={`${data.jobs.length} total runs`} />
        <Kpi label="Latest recommendation" value={latestOptimization ? fmtPct(latestOptimization.on_time_probability) : '—'} sub={latestOptimization ? `Net ${fmtMoney(latestOptimization.net_economic_benefit, currency, true)}` : 'No optimisation yet'} tone="info" />
      </div>

      {data.calibration?.status === 'insufficient_data' && (
        <Callout tone="info" title="Calibration status: insufficient data">
          {data.calibration.message}
        </Callout>
      )}

      <div className="dashboard-grid">
        <Card
          title="Forecast history"
          subtitle="Immutable snapshots of the forecast at the time each decision was taken."
          className="span-2"
        >
          {data.snapshots.length ? (
            <>
              <PlotChart
                data={snapshotChart}
                height={280}
                layout={{
                  xaxis: { title: 'Snapshot time' },
                  yaxis: { title: 'Working days' },
                  showlegend: true,
                  legend: { orientation: 'h', x: 0, y: 1.12 },
                }}
              />
              <div className="table-wrap">
                <table className="compact">
                  <thead><tr><th>Snapshot</th><th className="num">P50</th><th className="num">P90</th><th className="num">On-time</th><th>Created</th></tr></thead>
                  <tbody>
                    {data.snapshots.map((row: any) => (
                      <tr key={row.id}>
                        <td><div className="cell-title">{row.label || row.id.slice(0, 8)}</div></td>
                        <td className="num">{fmtDays(row.p50_days, 0)}</td>
                        <td className="num">{fmtDays(row.p90_days, 0)}</td>
                        <td className="num">{fmtPct(row.on_time_probability)}</td>
                        <td>{fmtDateTime(row.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <EmptyState title="No snapshots" message="Snapshots are recorded when a decision-grade forecast is produced." />
          )}
        </Card>

        <Card title="Calibration" eyebrow="Are we over-confident?">
          {data.calibration?.status === 'insufficient_data' ? (
            <>
              <p className="body-text">{data.calibration.message}</p>
              <dl className="fact-list dense">
                <div><dt>Observed launch events</dt><dd>{data.calibration.observed_events}</dd></div>
                <div><dt>Forecast/outcome pairs</dt><dd>{data.calibration.records}</dd></div>
              </dl>
              <Callout tone="info">
                A Brier score or reliability curve needs real outcomes. The platform reports “insufficient data” rather
                than manufacturing a calibration statistic from synthetic programs.
              </Callout>
            </>
          ) : (
            <div className="table-wrap">
              <table className="compact">
                <thead><tr><th>Metric</th><th className="num">Value</th></tr></thead>
                <tbody>
                  {Object.entries(data.calibration || {}).map(([key, value]) => (
                    <tr key={key}><td>{key.replaceAll('_', ' ')}</td><td className="num">{String(value)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <div className="dashboard-grid">
        <Card title="Audit trail" subtitle="Newest first. Payloads carry the request parameters." className="span-2">
          {data.audit.length ? (
            <div className="timeline">
              {data.audit.map((row: any) => (
                <div className="timeline-item" key={row.id}>
                  <div className="timeline-dot" />
                  <div className="timeline-body">
                    <div className="timeline-head">
                      <Badge tone="neutral">{row.action}</Badge>
                      <span className="muted-small">{row.actor}</span>
                      <span className="muted-small">{fmtDateTime(row.created_at)}</span>
                    </div>
                    <p>{row.summary}</p>
                    {row.entity_type && (
                      <div className="muted-small">
                        {row.entity_type}:{row.entity_id?.slice(0, 8)}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="No audit entries" message="Activity on this program will be recorded here." />
          )}
        </Card>

        <Card title="Background jobs" eyebrow="Runs and their outcomes">
          {data.jobs.length ? (
            <ul className="job-list">
              {data.jobs.map((job: any) => (
                <li key={job.id}>
                  <div>
                    <strong>{job.kind}</strong>
                    <span>
                      {fmtDateTime(job.created_at)} · {job.progress ? `${Math.round(job.progress * 100)}%` : '—'}
                    </span>
                  </div>
                  <Badge tone={job.status === 'completed' ? 'good' : job.status === 'failed' ? 'bad' : job.status === 'cancelled' ? 'neutral' : 'info'}>
                    {job.status}
                  </Badge>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No jobs" message="Simulation and optimisation runs appear here." />
          )}
        </Card>
      </div>
    </div>
  )
}
