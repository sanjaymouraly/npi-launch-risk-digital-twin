import { useState } from 'react'
import { api } from '../api'
import { useApi } from '../hooks'
import {
  Badge,
  Button,
  Callout,
  Card,
  ErrorState,
  Field,
  Icon,
  Kpi,
  Loading,
  PageHeader,
} from '../components/ui'
import { fmtMoney, fmtNumber } from '../utils'

type ProviderRow = {
  provider: string
  enabled: boolean
  active: boolean
  configured: boolean
  base_url: string
  model: string
  api_key_masked: string | null
  timeout_seconds: number
  max_retries: number
  monthly_budget_usd: number
  input_price_per_mtok: number
  output_price_per_mtok: number
  requires_key: boolean
}

const PROVIDER_BLURB: Record<string, string> = {
  offline: 'Deterministic, no-network analytics. Always available and never invents numbers.',
  ollama: 'Local models such as gemma3. No data leaves the machine; tool calling is disabled.',
  openai: 'OpenAI chat completions API. Tool calling is enabled for grounded retrieval.',
  anthropic: 'Anthropic messages API. Tool calling is disabled; the evidence pack is injected instead.',
  openrouter: 'OpenRouter aggregation of many hosted models.',
  custom: 'Any OpenAI-compatible endpoint, including self-hosted gateways.',
}

export default function SettingsPage() {
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState<any>({})
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState<{ tone: 'good' | 'bad' | 'info'; text: string } | null>(null)
  const [models, setModels] = useState<Record<string, string[]>>({})

  const { data, error, loading, reload } = useApi(async () => {
    const [meta, providers, stats] = await Promise.all([
      api.meta(),
      api.settings.providers(),
      api.stats(),
    ])
    return { meta, providers: providers.providers as ProviderRow[], note: providers.note, stats }
  }, [])

  const startEdit = (provider: ProviderRow) => {
    setEditing(provider.provider)
    setDraft({
      base_url: provider.base_url,
      model: provider.model,
      api_key: '',
      timeout_seconds: provider.timeout_seconds,
      max_retries: provider.max_retries,
      monthly_budget_usd: provider.monthly_budget_usd,
      input_price_per_mtok: provider.input_price_per_mtok,
      output_price_per_mtok: provider.output_price_per_mtok,
    })
  }

  const save = async (provider: string) => {
    setBusy(provider)
    setMessage(null)
    try {
      await api.settings.update(provider, {
        base_url: draft.base_url || null,
        model: draft.model || null,
        api_key: draft.api_key ? draft.api_key : null,
        timeout_seconds: draft.timeout_seconds ? Number(draft.timeout_seconds) : null,
        max_retries: draft.max_retries !== undefined ? Number(draft.max_retries) : null,
        monthly_budget_usd: draft.monthly_budget_usd !== undefined ? Number(draft.monthly_budget_usd) : null,
        input_price_per_mtok: draft.input_price_per_mtok !== undefined ? Number(draft.input_price_per_mtok) : null,
        output_price_per_mtok: draft.output_price_per_mtok !== undefined ? Number(draft.output_price_per_mtok) : null,
      })
      setEditing(null)
      setMessage({ tone: 'good', text: `Saved configuration for ${provider}.` })
      await reload()
    } catch (err: any) {
      setMessage({ tone: 'bad', text: err?.message || 'Save failed' })
    } finally {
      setBusy(null)
    }
  }

  const activate = async (provider: string) => {
    setBusy(provider)
    setMessage(null)
    try {
      await api.settings.update(provider, { enabled: true })
      setMessage({ tone: 'good', text: `${provider} is now the active provider.` })
      await reload()
    } catch (err: any) {
      setMessage({ tone: 'bad', text: err?.message || 'Could not change the active provider' })
    } finally {
      setBusy(null)
    }
  }

  const test = async (provider: string) => {
    setBusy(provider)
    setMessage(null)
    try {
      const result = await api.settings.test(provider)
      const ok = result.ok || result.status === 'ok' || result.success
      setMessage({
        tone: ok ? 'good' : 'bad',
        text: ok
          ? `${provider} responded successfully${result.latency_ms ? ` in ${result.latency_ms} ms` : ''}.`
          : `${provider} test failed: ${result.error || result.message || 'unknown error'}`,
      })
    } catch (err: any) {
      setMessage({ tone: 'bad', text: err?.message || 'Test failed' })
    } finally {
      setBusy(null)
    }
  }

  const listModels = async (provider: string) => {
    setBusy(provider)
    try {
      const result = await api.settings.models(provider)
      setModels((current) => ({ ...current, [provider]: result.models || [] }))
      if (result.error) setMessage({ tone: 'bad', text: result.error })
    } catch (err: any) {
      setMessage({ tone: 'bad', text: err?.message || 'Could not list models' })
    } finally {
      setBusy(null)
    }
  }

  if (loading && !data) return <Loading label="Loading settings" />
  if (error) return <ErrorState message={error} retry={reload} />
  if (!data) return null

  const active = data.providers.find((provider) => provider.active)

  return (
    <div className="page">
      <PageHeader
        eyebrow="Platform settings"
        title="Providers, security and runtime"
        description="AI provider credentials are encrypted at rest with a key derived from SECRET_KEY. They are masked in responses and never written to logs."
        actions={<Badge tone={active?.configured ? 'good' : 'warn'}>{active?.provider} active</Badge>}
      />
      {message && <Callout tone={message.tone}>{message.text}</Callout>}

      <div className="kpi-grid kpi-grid-4">
        <Kpi label="Active provider" value={active?.provider || 'offline'} sub={active?.model || '—'} tone="info" />
        <Kpi label="Programs" value={data.stats.projects} sub={`${data.stats.tasks} tasks · ${data.stats.simulations} simulations`} />
        <Kpi label="Optimisation runs" value={data.stats.optimizations} sub={`${data.stats.scenarios} scenarios`} />
        <Kpi label="Authentication" value={data.meta.auth_enabled ? 'Enabled' : 'Disabled'} sub={data.meta.auth_enabled ? 'JWT + project ACL' : 'Demo mode: single admin principal'} tone={data.meta.auth_enabled ? 'good' : 'warn'} />
      </div>

      <Card title="AI providers" subtitle="Exactly one provider is active. The copilot falls back to offline analytics when the active provider fails or the budget is exhausted.">
        <div className="provider-list">
          {data.providers.map((provider) => (
            <div key={provider.provider} className={`provider-card ${provider.active ? 'active' : ''}`}>
              <div className="provider-head">
                <div>
                  <div className="provider-name">
                    {provider.provider}
                    {provider.active && <Badge tone="good">active</Badge>}
                    {provider.configured ? <Badge tone="info">configured</Badge> : <Badge tone="neutral">not configured</Badge>}
                  </div>
                  <p>{PROVIDER_BLURB[provider.provider]}</p>
                </div>
                <div className="row-actions">
                  {!provider.active && (
                    <Button size="sm" variant="outline" onClick={() => activate(provider.provider)} loading={busy === provider.provider}>
                      Activate
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => test(provider.provider)} loading={busy === provider.provider}>
                    Test
                  </Button>
                  {provider.provider !== 'offline' && (
                    <Button size="sm" variant="ghost" onClick={() => listModels(provider.provider)} loading={busy === provider.provider}>
                      Models
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => (editing === provider.provider ? setEditing(null) : startEdit(provider))}>
                    {editing === provider.provider ? 'Close' : 'Configure'}
                  </Button>
                </div>
              </div>

              <dl className="fact-list dense">
                <div><dt>Model</dt><dd>{provider.model || '—'}</dd></div>
                <div><dt>Base URL</dt><dd className="ellipsis">{provider.base_url || '—'}</dd></div>
                <div><dt>API key</dt><dd>{provider.api_key_masked || (provider.requires_key ? 'not set' : 'not required')}</dd></div>
                <div><dt>Timeout</dt><dd>{provider.timeout_seconds}s · {provider.max_retries} retries</dd></div>
                <div><dt>Monthly budget</dt><dd>{provider.monthly_budget_usd ? fmtMoney(provider.monthly_budget_usd) : 'unlimited'}</dd></div>
                <div><dt>Pricing / Mtok</dt><dd>{provider.input_price_per_mtok ? `$${provider.input_price_per_mtok} in / $${provider.output_price_per_mtok} out` : 'not set'}</dd></div>
              </dl>

              {models[provider.provider] && (
                <div className="model-list">
                  {models[provider.provider].length ? (
                    models[provider.provider].slice(0, 12).map((model) => (
                      <span key={model} className="model-chip">
                        {model}
                        <button
                          onClick={() => {
                            setEditing(provider.provider)
                            setDraft((current: any) => ({ ...current, model }))
                          }}
                        >
                          use
                        </button>
                      </span>
                    ))
                  ) : (
                    <span className="muted-small">No models returned by the endpoint.</span>
                  )}
                </div>
              )}

              {editing === provider.provider && (
                <div className="provider-editor">
                  <div className="form-grid">
                    <Field label="Model">
                      <input value={draft.model || ''} onChange={(event) => setDraft({ ...draft, model: event.target.value })} />
                    </Field>
                    <Field label="Base URL">
                      <input value={draft.base_url || ''} onChange={(event) => setDraft({ ...draft, base_url: event.target.value })} />
                    </Field>
                  </div>
                  {provider.requires_key && (
                    <Field label="API key" hint="Leave blank to keep the stored key. Keys are encrypted and never returned.">
                      <input
                        type="password"
                        autoComplete="new-password"
                        value={draft.api_key || ''}
                        onChange={(event) => setDraft({ ...draft, api_key: event.target.value })}
                      />
                    </Field>
                  )}
                  <div className="form-grid">
                    <Field label="Timeout (s)">
                      <input type="number" min={5} max={300} value={draft.timeout_seconds || 60} onChange={(event) => setDraft({ ...draft, timeout_seconds: event.target.value })} />
                    </Field>
                    <Field label="Retries">
                      <input type="number" min={0} max={5} value={draft.max_retries || 0} onChange={(event) => setDraft({ ...draft, max_retries: event.target.value })} />
                    </Field>
                    <Field label="Monthly budget (USD)">
                      <input type="number" min={0} value={draft.monthly_budget_usd || 0} onChange={(event) => setDraft({ ...draft, monthly_budget_usd: event.target.value })} />
                    </Field>
                    <Field label="Input price / Mtok">
                      <input type="number" min={0} step="0.01" value={draft.input_price_per_mtok || 0} onChange={(event) => setDraft({ ...draft, input_price_per_mtok: event.target.value })} />
                    </Field>
                    <Field label="Output price / Mtok">
                      <input type="number" min={0} step="0.01" value={draft.output_price_per_mtok || 0} onChange={(event) => setDraft({ ...draft, output_price_per_mtok: event.target.value })} />
                    </Field>
                  </div>
                  <div className="button-row">
                    <Button size="sm" onClick={() => save(provider.provider)} loading={busy === provider.provider}>
                      Save configuration
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
        <Callout tone="info">{data.note}</Callout>
      </Card>

      <div className="two-col">
        <Card title="Runtime" eyebrow="Engine inventory">
          <dl className="fact-list dense">
            <div><dt>Application</dt><dd>{data.meta.app} v{data.meta.version}</dd></div>
            <div><dt>Environment</dt><dd>{data.meta.environment}</dd></div>
            <div><dt>Simulation engine</dt><dd>{data.meta.engines.simulation}</dd></div>
            <div><dt>Scheduler</dt><dd>{data.meta.engines.scheduler}</dd></div>
            <div><dt>CPM</dt><dd>{data.meta.engines.cpm}</dd></div>
            <div><dt>Attribution</dt><dd>{data.meta.engines.attribution}</dd></div>
            <div><dt>Max iterations</dt><dd>{fmtNumber(data.meta.limits.simulation_max_iterations)}</dd></div>
            <div><dt>Max tasks</dt><dd>{fmtNumber(data.meta.limits.simulation_max_tasks)}</dd></div>
          </dl>
        </Card>

        <Card title="Security posture" eyebrow="What is enforced">
          <ul className="plain-list small">
            <li>JWT bearer tokens with Argon2 password hashing.</li>
            <li>Project-scoped access control on every project route.</li>
            <li>Roles: admin, program_manager, viewer.</li>
            <li>Provider keys encrypted with Fernet (key derived from SECRET_KEY).</li>
            <li>Structured logs with credential redaction and request IDs.</li>
            <li>Immutable audit trail for runs, scenarios and approvals.</li>
            <li>Background jobs with cancellation and stale-job recovery.</li>
          </ul>
          <Callout tone="warn" title="Production checklist">
            Set a strong <code>SECRET_KEY</code>, enable <code>AUTH_ENABLED</code>, use PostgreSQL, and put the API behind
            TLS before exposing it outside a trusted network.
          </Callout>
        </Card>
      </div>
    </div>
  )
}
