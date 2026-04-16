import { useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import { useApi } from '../hooks'
import PlotChart, { PALETTE } from '../components/Plot'
import {
  Badge,
  Callout,
  Card,
  EmptyState,
  ErrorState,
  Kpi,
  Loading,
  PageHeader,
} from '../components/ui'
import { fmtDate, fmtDays, fmtPct, riskTone } from '../utils'

export default function MilestonesPage() {
  const { projectId = '' } = useParams()
  const { data, error, loading, reload } = useApi(async () => {
    const [project, milestones] = await Promise.all([api.projects.get(projectId), api.projects.milestones(projectId)])
    return { project, milestones }
  }, [projectId])

  const rows = data?.milestones.milestones || []
  const probabilistic = data?.milestones.source === 'simulation'

  const chart = useMemo(() => {
    const ordered = [...rows]
      .filter((row: any) => row.on_time_probability !== null && row.on_time_probability !== undefined)
      .sort((a: any, b: any) => a.on_time_probability - b.on_time_probability)
    return [
      {
        type: 'bar',
        x: ordered.map((row: any) => row.on_time_probability * 100),
        y: ordered.map((row: any) => row.name),
        orientation: 'h',
        marker: {
          color: ordered.map((row: any) =>
            row.on_time_probability >= 0.75 ? PALETTE.green : row.on_time_probability >= 0.4 ? PALETTE.amber : PALETTE.red,
          ),
        },
        text: ordered.map((row: any) => fmtPct(row.on_time_probability, 0)),
        textposition: 'outside',
        cliponaxis: false,
        customdata: ordered.map((row: any) => [row.due_date, row.p90_date, row.slack_vs_due_days]),
        hovertemplate:
          '%{y}<br>Due %{customdata[0]}<br>P90 %{customdata[1]}<br>Mean slack %{customdata[2]:.1f}d<extra></extra>',
      },
    ]
  }, [rows])

  if (loading && !data) return <Loading label="Loading milestones" />
  if (error) return <ErrorState message={error} retry={reload} />
  if (!data) return null

  const { project, milestones } = data
  const atRisk = rows.filter((row: any) => row.on_time_probability !== null && row.on_time_probability < 0.5)
  const committed = rows.filter((row: any) => row.customer_commitment)
  const lowest = rows
    .filter((row: any) => row.on_time_probability !== null && row.on_time_probability !== undefined)
    .sort((a: any, b: any) => a.on_time_probability - b.on_time_probability)[0]

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${project.key} · milestones`}
        title="Gate confidence, not gate dates"
        description="Milestone dates from the plan, forecast dates from the simulation, and the probability of meeting each commitment."
        actions={
          <Badge tone={probabilistic ? 'info' : 'warn'}>
            {probabilistic ? `SIM ${milestones.simulation_id?.slice(0, 8)}` : 'Deterministic CPM only'}
          </Badge>
        }
      />

      {!probabilistic && (
        <Callout tone="warn" title="No probability forecast">
          These are CPM finish dates, not probabilities. Run a Monte Carlo simulation to get P50/P90 dates and on-time
          probabilities for each gate.
        </Callout>
      )}

      <div className="kpi-grid kpi-grid-4">
        <Kpi label="Milestones" value={rows.length} sub={`${committed.length} customer commitments`} />
        <Kpi
          label="Below 50% confidence"
          value={atRisk.length}
          sub="Gates needing intervention or re-commitment"
          tone={atRisk.length ? 'bad' : 'good'}
        />
        <Kpi
          label="Lowest confidence gate"
          value={lowest ? fmtPct(lowest.on_time_probability, 0) : '—'}
          sub={lowest?.name || 'No probabilistic gate'}
          tone={lowest ? riskTone(lowest.on_time_probability) : 'neutral'}
        />
        <Kpi
          label="Mean forecast slack"
          value={
            rows.filter((row: any) => row.slack_vs_due_days !== null).length
              ? fmtDays(
                  rows
                    .filter((row: any) => row.slack_vs_due_days !== null)
                    .reduce((sum: number, row: any) => sum + row.slack_vs_due_days, 0) /
                    rows.filter((row: any) => row.slack_vs_due_days !== null).length,
                )
              : '—'
          }
          sub="Mean finish vs due date"
          tone="neutral"
        />
      </div>

      <div className="dashboard-grid">
        <Card
          title="On-time probability by gate"
          subtitle="Probability that the milestone task finishes by its due date, from the latest simulation."
          className="span-2"
        >
          {chart[0]?.x?.length ? (
            <PlotChart
              data={chart}
              height={Math.max(300, rows.length * 44 + 70)}
              layout={{
                xaxis: { title: 'Probability of meeting due date (%)', ticksuffix: '%', range: [0, 108] },
                yaxis: { automargin: true },
                margin: { l: 190, r: 50, t: 10, b: 44 },
                shapes: [
                  { type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'paper', y0: 0, y1: 0, line: { color: 'transparent' } },
                ],
              }}
            />
          ) : (
            <EmptyState title="No probabilistic milestones" message="Run a simulation to compute gate confidence." />
          )}
        </Card>

        <Card title="Commitment posture" eyebrow="Customer-facing gates">
          {committed.length ? (
            <ul className="milestone-mini">
              {committed.map((row: any) => (
                <li key={row.id || row.name}>
                  <div>
                    <strong>{row.name}</strong>
                    <span>Due {fmtDate(row.due_date)} · P50 {fmtDate(row.p50_date)}</span>
                  </div>
                  <Badge tone={riskTone(row.on_time_probability)}>{fmtPct(row.on_time_probability, 0)}</Badge>
                </li>
              ))}
            </ul>
          ) : (
            <p className="body-text">No customer commitments are flagged for this program.</p>
          )}
          <div className="divider" />
          <div className="mini-method">
            <strong>How to read this</strong>
            <p>
              A gate at 40% confidence is not “40% likely to pass” in a physical sense; it is the modelled probability
              of the milestone task finishing by the committed date under the current plan and risk assumptions.
            </p>
          </div>
        </Card>
      </div>

      <Card title="Milestone register" subtitle="Plan dates versus simulated forecast dates." className="table-card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Milestone</th>
                <th>Commitment</th>
                <th>Due</th>
                <th>P10</th>
                <th>P50</th>
                <th>P90</th>
                <th className="num">Slack (mean)</th>
                <th className="num">On-time</th>
                <th className="num">Expected delay</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row: any) => (
                <tr key={row.id || row.name}>
                  <td><div className="cell-title">{row.name}</div></td>
                  <td>{row.customer_commitment ? <Badge tone="info">customer</Badge> : <span className="muted-small">internal</span>}</td>
                  <td>{fmtDate(row.due_date)}</td>
                  <td>{fmtDate(row.p10_date)}</td>
                  <td className="strong">{fmtDate(row.p50_date)}</td>
                  <td>{fmtDate(row.p90_date)}</td>
                  <td className={`num ${(row.slack_vs_due_days || 0) < 0 ? 'tone-bad' : ''}`}>
                    {fmtDays(row.slack_vs_due_days)}
                  </td>
                  <td className="num">{fmtPct(row.on_time_probability)}</td>
                  <td className="num">{fmtDays(row.expected_delay_days)}</td>
                  <td>
                    {row.on_time_probability === null || row.on_time_probability === undefined ? (
                      <Badge tone="neutral">deterministic</Badge>
                    ) : (
                      <Badge tone={riskTone(row.on_time_probability)}>
                        {row.on_time_probability >= 0.75 ? 'on track' : row.on_time_probability >= 0.4 ? 'watch' : 'at risk'}
                      </Badge>
                    )}
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
