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
import { fmtDays, fmtMoney, fmtPct } from '../utils'

export default function SuppliersPage() {
  const { projectId = '' } = useParams()
  const { data, error, loading, reload } = useApi(async () => {
    const [project, suppliers] = await Promise.all([api.projects.get(projectId), api.projects.suppliers(projectId)])
    return { project, suppliers }
  }, [projectId])

  const exposurePlot = useMemo(() => {
    const rows = [...(data?.suppliers.components || [])].sort((a: any, b: any) => b.exposure_score - a.exposure_score).slice(0, 10).reverse()
    return [
      {
        type: 'bar',
        orientation: 'h',
        x: rows.map((row: any) => row.exposure_score),
        y: rows.map((row: any) => row.name),
        marker: {
          color: rows.map((row: any) => (row.single_source ? PALETTE.red : PALETTE.teal)),
        },
        customdata: rows.map((row: any) => [row.supplier, row.net_ready_days, row.disruption_probability]),
        hovertemplate:
          '%{y}<br>%{customdata[0]}<br>Exposure %{x:.3f}<br>Net readiness %{customdata[1]}d<br>Disruption P %{customdata[2]:.0%}<extra></extra>',
        text: rows.map((row: any) => (row.single_source ? 'single source' : '')),
        textposition: 'outside',
        cliponaxis: false,
      },
    ]
  }, [data])

  const simulatedPlot = useMemo(() => {
    const rows = [...(data?.suppliers.simulated_supplier_impact || [])].slice(0, 8).reverse()
    return [
      {
        type: 'bar',
        orientation: 'h',
        x: rows.map((row: any) => row.expected_delay_contribution_days),
        y: rows.map((row: any) => row.name),
        marker: { color: PALETTE.amber },
        customdata: rows.map((row: any) => [row.observed_disruption_rate, row.probability_impacting_launch]),
        hovertemplate:
          '%{y}<br>Expected contribution %{x:.2f}d<br>Observed disruption %{customdata[0]:.1%}<br>P(launch impact) %{customdata[1]:.1%}<extra></extra>',
      },
    ]
  }, [data])

  if (loading && !data) return <Loading label="Loading supply exposure" />
  if (error) return <ErrorState message={error} retry={reload} />
  if (!data) return null

  const { project, suppliers } = data
  const components = suppliers.components || []
  const simulated = suppliers.simulated_supplier_impact || []
  const totalMonthly = components.reduce((sum: number, row: any) => sum + (row.monthly_spend || 0), 0)
  const atRisk = components.filter((row: any) => row.single_source && row.criticality >= 0.6)

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${project.key} · supply exposure`}
        title="Material and supplier concentration"
        description="BOM-derived lead-time readiness, qualification status and simulated disruption impact. Single-source exposure is called out explicitly."
        actions={<Badge tone="info">{components.length} components · {suppliers.suppliers.length} suppliers</Badge>}
      />

      <div className="kpi-grid kpi-grid-4">
        <Kpi label="Components in BOM" value={components.length} sub={`${suppliers.suppliers.length} suppliers`} />
        <Kpi
          label="Single-source components"
          value={suppliers.single_source_components.length}
          sub="No qualified alternate source"
          tone="bad"
        />
        <Kpi
          label="No qualified alternate"
          value={suppliers.no_qualified_alternate.length}
          sub="Alternative may exist but is not qualified"
          tone="warn"
        />
        <Kpi
          label="Monthly material spend"
          value={fmtMoney(totalMonthly, project.currency, true)}
          sub="Sum of component monthly spend"
          tone="neutral"
        />
      </div>

      {atRisk.length > 0 && (
        <Callout tone="bad" title={`${atRisk.length} critical single-source exposure${atRisk.length === 1 ? '' : 's'}`}>
          {atRisk.slice(0, 3).map((row: any) => `${row.name} (${row.supplier})`).join('; ')}
          {atRisk.length > 3 ? ` and ${atRisk.length - 3} more` : ''}. Qualifying a second source is usually cheaper than
          expediting after a disruption, but verify the cost and lead time in a scenario.
        </Callout>
      )}

      <div className="dashboard-grid">
        <Card
          title="Component exposure"
          subtitle="Exposure blends criticality, lead-time readiness and disruption probability. Red bars are single-source."
          eyebrow="BOM view"
          className="span-2"
        >
          {components.length ? (
            <PlotChart
              data={exposurePlot}
              height={Math.max(320, Math.min(10, components.length) * 34 + 70)}
              layout={{
                xaxis: { title: 'Exposure score (0–1)' },
                yaxis: { automargin: true, tickfont: { size: 11 } },
                margin: { l: 175, r: 70, t: 10, b: 44 },
              }}
            />
          ) : (
            <EmptyState title="No components" message="The BOM is empty for this program." />
          )}
          <div className="chart-legend">
            <span><i style={{ background: PALETTE.red }} />Single source</span>
            <span><i style={{ background: PALETTE.teal }} />Alternate available</span>
          </div>
        </Card>

        <Card
          title="Simulated supplier impact"
          subtitle="Expected makespan contribution from the latest Monte Carlo run."
          eyebrow="Empirical"
        >
          {simulated.length ? (
            <PlotChart
              data={simulatedPlot}
              height={Math.max(280, Math.min(8, simulated.length) * 34 + 60)}
              layout={{
                xaxis: { title: 'Expected delay contribution (working days)' },
                yaxis: { automargin: true, tickfont: { size: 10 } },
                margin: { l: 130, r: 30, t: 10, b: 44 },
              }}
            />
          ) : (
            <EmptyState
              title="No simulated impact"
              message="Run a simulation to attribute delay to suppliers and BOM components."
            />
          )}
        </Card>
      </div>

      <Card title="Supplier register" subtitle="Lead time, reliability and qualification status." className="table-card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Supplier</th>
                <th>Category</th>
                <th>Region</th>
                <th className="num">Components</th>
                <th className="num">Single source</th>
                <th className="num">Lead time</th>
                <th className="num">Reliability</th>
                <th className="num">Disruption P</th>
                <th className="num">Exposure</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {suppliers.suppliers.map((supplier: any) => (
                <tr key={supplier.id}>
                  <td><div className="cell-title">{supplier.name}</div></td>
                  <td>{supplier.category}</td>
                  <td>{supplier.region}</td>
                  <td className="num">{supplier.component_count}</td>
                  <td className="num">{supplier.single_source_count}</td>
                  <td className="num">{fmtDays(supplier.lead_time_days, 0)}</td>
                  <td className="num">{fmtPct(supplier.reliability, 0)}</td>
                  <td className="num">{fmtPct(supplier.disruption_probability)}</td>
                  <td className="num strong">{supplier.exposure_score.toFixed(3)}</td>
                  <td>
                    <Badge tone={supplier.qualified ? 'good' : 'warn'}>{supplier.qualified ? 'qualified' : 'unqualified'}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card
        title="Component readiness"
        subtitle="Net ready days = lead time minus inventory and safety stock, floored at zero. Used as a material release constraint in scheduling and simulation."
        className="table-card"
      >
        <div className="table-wrap table-tall">
          <table>
            <thead>
              <tr>
                <th>Component</th>
                <th>Part number</th>
                <th>Supplier</th>
                <th className="num">Lead time</th>
                <th className="num">Inventory + safety</th>
                <th className="num">Net ready</th>
                <th className="num">Criticality</th>
                <th className="num">Disruption P</th>
                <th className="num">Expected delay</th>
                <th>Alternate</th>
              </tr>
            </thead>
            <tbody>
              {[...components]
                .sort((a: any, b: any) => b.exposure_score - a.exposure_score)
                .map((component: any) => (
                  <tr key={component.id}>
                    <td><div className="cell-title">{component.name}</div></td>
                    <td><code>{component.part_number}</code></td>
                    <td>{component.supplier || '—'}</td>
                    <td className="num">{fmtDays(component.lead_time_days, 0)}</td>
                    <td className="num">{fmtDays((component.inventory_days || 0) + (component.safety_stock_days || 0), 0)}</td>
                    <td className="num strong">{fmtDays(component.net_ready_days, 0)}</td>
                    <td className="num">{component.criticality.toFixed(2)}</td>
                    <td className="num">{fmtPct(component.disruption_probability)}</td>
                    <td className="num">{fmtDays(component.expected_delay_days)}</td>
                    <td>
                      {component.alternative_supplier ? (
                        <Badge tone={component.alternative_qualified ? 'good' : 'warn'}>
                          {component.alternative_supplier} {component.alternative_qualified ? '(qualified)' : '(not qualified)'}
                        </Badge>
                      ) : (
                        <Badge tone="bad">none</Badge>
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
