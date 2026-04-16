import { useParams } from 'react-router-dom'
import { api } from '../api'
import { useApi } from '../hooks'
import { Badge, Callout, Card, ErrorState, Loading, PageHeader } from '../components/ui'

const methods = [
  {
    title: 'Critical path (CPM)',
    body:
      'Exact activity-on-node critical path with FS/SS/FF/SF precedence types, lags, and a working-day calendar that honours weekends, holidays and non-5-day weeks. Durations and dates are converted exactly; no 7/5 fudge factors are applied.',
    honesty: 'CPM ignores resource contention. It answers “what is the logic-only duration?”, never “when will we launch?”.',
  },
  {
    title: 'Resource-constrained schedule (CP-SAT)',
    body:
      'OR-Tools CP-SAT model with cumulative capacity constraints per resource, material release dates derived from supplier lead time and inventory, and every precedence relation. Durations are rounded to whole working days for the solver.',
    honesty: 'The solver reports status, makespan and objective. When the deadline is infeasible, the platform returns the conflict set instead of a silent relaxation.',
  },
  {
    title: 'Monte Carlo simulation',
    body:
      'Trials sample task durations (with latent correlation), supplier disruptions, discrete risk events, validation failures, ECO rework, absenteeism, transport delay and capacity loss. Each trial is scheduled with a serial schedule generation scheme that respects logic, capacity and material availability.',
    honesty:
      'SGS is exact for feasibility but heuristic for optimality. Its gap to the CP-SAT optimum is measured on demand and reported, not assumed to be zero.',
  },
  {
    title: 'Percentiles and uncertainty',
    body:
      'Percentiles use linear interpolation between order statistics (NumPy method="linear"). Means carry a 95% confidence interval, and convergence is assessed with a batch-means relative standard error criterion below 1%.',
    honesty: 'Monte Carlo probabilities are estimates with sampling error. The iteration count, seed and convergence state are always shown next to the number.',
  },
  {
    title: 'Risk attribution',
    body:
      'Three complementary lenses: Spearman rank correlation between sampled inputs and makespan; one-at-a-time tornado reruns with ±20% durations; and Saltelli first-order Sobol indices with bootstrap intervals on the deterministic scheduler. Leave-one-out counterfactuals neutralise one driver at a time with common random numbers.',
    honesty: 'All three measure influence inside the model. None of them establishes real-world causality, and the platform never presents them as causal proof.',
  },
  {
    title: 'Scenario comparison',
    body:
      'Both arms are simulated with entity-keyed random streams, so the comparison is paired. The platform reports the mean paired delta, its 95% confidence interval, and the probability of improvement versus harm.',
    honesty: 'A paired delta is only as good as the model. Interactions between interventions are approximated, not guaranteed.',
  },
  {
    title: 'Intervention optimisation',
    body:
      'A catalog of candidates is generated from the real project (critical tasks, suppliers, bottlenecks, dependencies). Each candidate is scored with a paired pilot, then CP-SAT selects portfolios under budget, exclusivity, prerequisite, headcount and capacity constraints. Selected and Pareto-near portfolios are re-simulated at higher fidelity and re-checked with CP-SAT scheduling.',
    honesty:
      'The optimiser scores candidates additively. Verification captures interactions. The recommendation is the highest verified net economic benefit, not the highest score.',
  },
]

const limitations = [
  'The Monte Carlo scheduler is a feasibility heuristic, not an optimiser. Its makespan is an upper bound on the true optimum; the platform reports the CP-SAT gap rather than hiding it.',
  'Supplier disruption probabilities and lead-time variability are inputs from the program plan. They are not learned from historical data, because the demo data is synthetic.',
  'Cost of delay is a single scalar per program. Real programmes distinguish customer penalties, margin loss and expedited freight; the platform models the aggregate only.',
  'Calibration (Brier score, reliability curves) needs observed launch outcomes. With synthetic data the platform reports “insufficient data” instead of a fabricated score.',
  'Yield ramp economics use a simple logistic curve. It is a placeholder for a real PPAP/yield dataset, not a substitute for one.',
  'The AI copilot is a reading assistant. It is constrained to read-only tools and must cite its evidence; it does not decide, and it is not a substitute for program judgement.',
]

export default function MethodologyPage() {
  const { projectId = '' } = useParams()
  const { data, error, loading, reload } = useApi(async () => {
    const [meta, project] = await Promise.all([api.meta(), api.projects.get(projectId)])
    let simulation: any = null
    try {
      simulation = await api.simulations.latest(projectId)
    } catch {
      simulation = null
    }
    return { meta, project, simulation }
  }, [projectId])

  if (loading && !data) return <Loading label="Loading methodology" />
  if (error) return <ErrorState message={error} retry={reload} />
  if (!data) return null

  const summary = data.simulation?.summary

  return (
    <div className="page">
      <PageHeader
        eyebrow="Methodology & limitations"
        title="How the numbers are produced"
        description="Every estimate in this platform has a stated method, a stated uncertainty and a stated boundary. Read this before acting on a forecast."
        actions={<Badge tone="info">Engine {data.meta.engines.simulation}</Badge>}
      />

      <div className="method-grid">
        {methods.map((method) => (
          <Card key={method.title} title={method.title} className="method-card">
            <p className="body-text">{method.body}</p>
            <Callout tone="warn" title="Boundary">{method.honesty}</Callout>
          </Card>
        ))}
      </div>

      <div className="dashboard-grid">
        <Card title="Recorded run provenance" eyebrow="This program" className="span-2">
          {summary ? (
            <dl className="fact-list">
              <div><dt>Simulation id</dt><dd><code>{data.simulation.id}</code></dd></div>
              <div><dt>Engine</dt><dd>{summary.engine.version} · {summary.engine.scheduler}</dd></div>
              <div><dt>Iterations / seed</dt><dd>{summary.engine.iterations.toLocaleString()} · {summary.engine.seed}</dd></div>
              <div><dt>Percentile method</dt><dd>{summary.engine.percentile_method}</dd></div>
              <div><dt>Convergence</dt><dd>relative SE {summary.convergence.relative_se} ({summary.convergence.converged ? 'converged' : 'not converged'})</dd></div>
              <div><dt>Latent correlation ρ</dt><dd>{summary.engine.options.correlation_rho}</dd></div>
              <div><dt>Capacity loss / trial</dt><dd>{summary.engine.options.capacity_loss_prob}</dd></div>
              <div><dt>Absenteeism / trial</dt><dd>{summary.engine.options.absenteeism_prob}</dd></div>
              <div><dt>Supplier disruption</dt><dd>{summary.engine.options.supplier_disruption_enabled ? 'enabled' : 'disabled'}</dd></div>
              <div><dt>Material constraints</dt><dd>{summary.engine.options.material_constraints_enabled ? 'enabled' : 'disabled'}</dd></div>
            </dl>
          ) : (
            <p className="body-text">No completed run for this program yet; run one to see its recorded configuration.</p>
          )}
        </Card>

        <Card title="Stated limitations" eyebrow="Known boundaries">
          <ul className="plain-list small">
            {limitations.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </Card>
      </div>

      <Card title="Platform capabilities" eyebrow="Engine inventory">
        <div className="capability-grid">
          {data.meta.capabilities.map((capability: string) => (
            <div key={capability} className="capability">{capability}</div>
          ))}
        </div>
        <div className="button-row">
          <a className="btn btn-outline btn-md" href={import.meta.env.VITE_DOCS_URL || 'http://localhost:8000/docs'} target="_blank" rel="noreferrer">
            OpenAPI reference ↗
          </a>
        </div>
      </Card>
    </div>
  )
}
