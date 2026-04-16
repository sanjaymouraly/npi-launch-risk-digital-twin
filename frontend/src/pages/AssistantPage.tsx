import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import { useApi } from '../hooks'
import Markdown from '../components/Markdown'
import {
  Badge,
  Button,
  Callout,
  Card,
  EmptyState,
  ErrorState,
  Icon,
  Loading,
  PageHeader,
} from '../components/ui'
import { fmtDateTime, fmtNumber } from '../utils'

type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
  citations?: any[]
  provider?: string
  model?: string
  usage?: { prompt_tokens: number; completion_tokens: number }
  cost_usd?: number
  latency_ms?: number
  evidence?: any[]
  fallback_reason?: string | null
}

export default function AssistantPage() {
  const { projectId = '' } = useParams()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [offline, setOffline] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  const { data, error: loadError, loading, reload } = useApi(async () => {
    const [project, status, suggestions, conversations] = await Promise.all([
      api.projects.get(projectId),
      api.ai.status(projectId),
      api.ai.suggestions(projectId),
      api.ai.conversations(projectId),
    ])
    return { project, status, suggestions, conversations }
  }, [projectId])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, sending])

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed) return
      setError(null)
      setMessages((current) => [...current, { role: 'user', content: trimmed }])
      setInput('')
      setSending(true)
      try {
        const response = await api.ai.chat(projectId, {
          message: trimmed,
          conversation_id: conversationId,
          offline,
        })
        setConversationId(response.conversation_id)
        setMessages((current) => [
          ...current,
          {
            role: 'assistant',
            content: response.answer,
            citations: response.citations,
            provider: response.provider,
            model: response.model,
            usage: response.usage,
            cost_usd: response.cost_usd,
            latency_ms: response.latency_ms,
            evidence: response.evidence_used,
            fallback_reason: response.fallback_reason,
          },
        ])
        reload()
      } catch (err: any) {
        setError(err?.message || 'The copilot is unavailable')
      } finally {
        setSending(false)
      }
    },
    [conversationId, offline, projectId, reload],
  )

  const openConversation = async (id: string) => {
    setError(null)
    try {
      const conversation = await api.ai.conversation(projectId, id)
      setConversationId(id)
      setMessages(
        conversation.messages.map((message: any) => ({
          role: message.role,
          content: message.content,
          citations: message.citations,
          provider: message.provider,
          model: message.model,
          usage: message.usage,
          cost_usd: message.cost_usd,
          latency_ms: message.latency_ms,
          evidence: message.tool_calls,
        })),
      )
    } catch (err: any) {
      setError(err?.message || 'Could not open the conversation')
    }
  }

  if (loading && !data) return <Loading label="Connecting to the copilot" />
  if (loadError) return <ErrorState message={loadError} retry={reload} />
  if (!data) return null

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${data.project.key} · risk copilot`}
        title="Ask about this program"
        description="The copilot reads this program's schedule, simulations, supply chain, scenarios and decisions through read-only tools, then cites what it used."
        actions={
          <div className="row-actions">
            <Badge tone={data.status.configured ? 'good' : 'warn'}>
              {data.status.active_provider} · {data.status.model}
            </Badge>
            <Badge tone="info">offline mode available</Badge>
          </div>
        }
      />

      <div className="chat-layout">
        <div className="chat-main">
          <Card
            title="Conversation"
            subtitle="Answers are grounded in stored evidence. Nothing is generated without a citation."
            actions={
              <div className="row-actions">
                <label className="switch-row inline">
                  <input type="checkbox" checked={offline} onChange={(event) => setOffline(event.target.checked)} />
                  <span>Offline analytics</span>
                </label>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setMessages([])
                    setConversationId(null)
                  }}
                >
                  New thread
                </Button>
              </div>
            }
            padded={false}
          >
            <div className="chat-scroll">
              {messages.length === 0 && (
                <div className="chat-welcome">
                  <div className="chat-welcome-icon"><Icon name="ai" size={28} /></div>
                  <h3>Ask the risk copilot</h3>
                  <p>
                    It has read-only access to this program's schedule, Monte Carlo runs, risk register, supplier
                    exposure, scenarios, optimisation results and audit trail. Answers cite the records used.
                  </p>
                  <div className="suggestion-grid">
                    {data.suggestions.map((suggestion) => (
                      <button key={suggestion} className="suggestion" onClick={() => send(suggestion)}>
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((message, index) => (
                <div key={index} className={`chat-message ${message.role}`}>
                  <div className="chat-avatar">
                    {message.role === 'user' ? 'You' : <Icon name="ai" size={16} />}
                  </div>
                  <div className="chat-bubble">
                    {message.fallback_reason && <Callout tone="warn">{message.fallback_reason}</Callout>}
                    {message.role === 'assistant' ? (
                      <Markdown text={message.content} />
                    ) : (
                      <p>{message.content}</p>
                    )}
                    {message.role === 'assistant' && (
                      <div className="chat-meta">
                        {message.citations && message.citations.length > 0 && (
                          <div className="citation-row">
                            {message.citations.map((citation: any) => (
                              <span key={`${citation.kind}-${citation.id}`} className="citation" title={citation.detail}>
                                {citation.label}
                              </span>
                            ))}
                          </div>
                        )}
                        <div className="chat-stats">
                          <span>{message.provider}/{message.model}</span>
                          {message.usage && (
                            <span>
                              {fmtNumber(message.usage.prompt_tokens)} prompt · {fmtNumber(message.usage.completion_tokens)} completion tokens
                            </span>
                          )}
                          {message.latency_ms ? <span>{(message.latency_ms / 1000).toFixed(1)}s</span> : null}
                          {message.cost_usd ? <span>${message.cost_usd.toFixed(4)}</span> : null}
                        </div>
                        {message.evidence && message.evidence.length > 0 && (
                          <details className="evidence-details">
                            <summary>Evidence tools used ({message.evidence.length})</summary>
                            <ul>
                              {message.evidence.map((tool: any, toolIndex: number) => (
                                <li key={toolIndex}>
                                  <code>{tool.tool}</code> · as of {fmtDateTime(tool.as_of)}
                                </li>
                              ))}
                            </ul>
                          </details>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {sending && (
                <div className="chat-message assistant">
                  <div className="chat-avatar"><Icon name="ai" size={16} /></div>
                  <div className="chat-bubble">
                    <span className="spinner" /> Reading project evidence…
                  </div>
                </div>
              )}
              <div ref={endRef} />
            </div>

            <div className="chat-composer">
              {error && <div className="inline-error">{error}</div>}
              <div className="composer-row">
                <textarea
                  value={input}
                  rows={2}
                  placeholder="Ask about deadline probability, risk drivers, supplier exposure, milestone confidence or what to do next…"
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault()
                      send(input)
                    }
                  }}
                />
                <Button onClick={() => send(input)} loading={sending} icon={<Icon name="arrow" />}>
                  Ask
                </Button>
              </div>
              <div className="composer-hint">
                Enter to send · Shift+Enter for a new line · live providers may take 30–60 s while they reason over the
                evidence pack.
              </div>
            </div>
          </Card>
        </div>

        <div className="chat-side">
          <Card title="Provider" eyebrow="Grounding & budget">
            <dl className="fact-list dense">
              <div><dt>Active provider</dt><dd>{data.status.active_provider}</dd></div>
              <div><dt>Model</dt><dd>{data.status.model}</dd></div>
              <div><dt>Configured</dt><dd>{data.status.configured ? 'yes' : 'no'}</dd></div>
              <div><dt>Monthly budget</dt><dd>{data.status.monthly_budget_usd ? `$${data.status.monthly_budget_usd}` : 'unlimited'}</dd></div>
              <div><dt>Spent this month</dt><dd>${Number(data.status.month_spend_usd || 0).toFixed(4)}</dd></div>
            </dl>
            <p className="muted-small">{data.status.grounding}</p>
          </Card>

          <Card title="Conversation history" eyebrow="Persisted">
            {data.conversations.length ? (
              <ul className="conversation-list">
                {data.conversations.map((conversation: any) => (
                  <li key={conversation.id}>
                    <button onClick={() => openConversation(conversation.id)}>
                      <strong>{conversation.title || 'Untitled'}</strong>
                      <span>
                        {conversation.provider} · {fmtDateTime(conversation.created_at)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="No conversations" message="Your questions and answers are stored per program." />
            )}
          </Card>

          <Card title="What the copilot can see" eyebrow="Read-only tools">
            <ul className="plain-list small">
              <li>Program scope, budget and deadline</li>
              <li>CPM versus CP-SAT schedule and bottlenecks</li>
              <li>Latest Monte Carlo distribution and convergence</li>
              <li>Risk attribution, tornado and risk events</li>
              <li>Supplier and component exposure</li>
              <li>Milestone confidence</li>
              <li>Scenarios and optimisation results</li>
              <li>Audit trail and forecast snapshots</li>
            </ul>
          </Card>
        </div>
      </div>
    </div>
  )
}
