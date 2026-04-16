import React from 'react'

type Tone = 'good' | 'warn' | 'bad' | 'info' | 'neutral' | 'accent'

export function Badge({ children, tone = 'neutral', dot = false }: { children: React.ReactNode; tone?: Tone; dot?: boolean }) {
  return (
    <span className={`badge badge-${tone}`}>
      {dot && <span className="badge-dot" />}
      {children}
    </span>
  )
}

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  className = '',
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'outline'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  icon?: React.ReactNode
}) {
  return (
    <button
      {...props}
      disabled={props.disabled || loading}
      className={`btn btn-${variant} btn-${size} ${className}`}
    >
      {loading ? <span className="spinner" /> : icon}
      {children}
    </button>
  )
}

export function Card({
  title,
  subtitle,
  eyebrow,
  actions,
  children,
  className = '',
  padded = true,
}: {
  title?: React.ReactNode
  subtitle?: React.ReactNode
  eyebrow?: React.ReactNode
  actions?: React.ReactNode
  children: React.ReactNode
  className?: string
  padded?: boolean
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions || eyebrow) && (
        <header className="card-head">
          <div>
            {eyebrow && <div className="eyebrow">{eyebrow}</div>}
            {title && <h2>{title}</h2>}
            {subtitle && <p className="card-sub">{subtitle}</p>}
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      <div className={padded ? 'card-body' : ''}>{children}</div>
    </section>
  )
}

export function Kpi({
  label,
  value,
  sub,
  tone = 'neutral',
  icon,
}: {
  label: string
  value: React.ReactNode
  sub?: React.ReactNode
  tone?: Tone
  icon?: React.ReactNode
}) {
  return (
    <div className={`kpi kpi-${tone}`}>
      <div className="kpi-top">
        <span className="kpi-label">{label}</span>
        {icon && <span className="kpi-icon">{icon}</span>}
      </div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  )
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string
  title: React.ReactNode
  description?: React.ReactNode
  actions?: React.ReactNode
}) {
  return (
    <div className="page-head">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  )
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="loading">
      <span className="spinner spinner-lg" />
      <span>{label}…</span>
    </div>
  )
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="state state-error">
      <div className="state-icon">!</div>
      <div>
        <strong>Could not load this view</strong>
        <p>{message}</p>
      </div>
      {retry && (
        <Button variant="outline" size="sm" onClick={retry}>
          Retry
        </Button>
      )}
    </div>
  )
}

export function EmptyState({
  title,
  message,
  action,
  icon = '◇',
}: {
  title: string
  message: string
  action?: React.ReactNode
  icon?: string
}) {
  return (
    <div className="state state-empty">
      <div className="state-icon">{icon}</div>
      <div>
        <strong>{title}</strong>
        <p>{message}</p>
      </div>
      {action}
    </div>
  )
}

export function ProgressBar({ value, tone = 'accent' }: { value: number; tone?: Tone }) {
  return (
    <div className={`progress progress-${tone}`}>
      <div style={{ width: `${Math.max(2, Math.min(100, value * 100))}%` }} />
    </div>
  )
}

export function Field({
  label,
  hint,
  children,
  className = '',
}: {
  label: string
  hint?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <label className={`field ${className}`}>
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  )
}

export function Callout({
  children,
  tone = 'info',
  title,
}: {
  children: React.ReactNode
  tone?: Tone
  title?: string
}) {
  return (
    <div className={`callout callout-${tone}`}>
      {title && <strong>{title}</strong>}
      <div>{children}</div>
    </div>
  )
}

export function KeyValue({ items }: { items: Array<{ label: string; value: React.ReactNode }> }) {
  return (
    <dl className="kv">
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  }
  const paths: Record<string, React.ReactNode> = {
    dashboard: (
      <>
        <rect x="3" y="3" width="7" height="9" rx="1.5" />
        <rect x="14" y="3" width="7" height="5" rx="1.5" />
        <rect x="14" y="12" width="7" height="9" rx="1.5" />
        <rect x="3" y="16" width="7" height="5" rx="1.5" />
      </>
    ),
    programs: (
      <>
        <path d="M4 7.5 12 3l8 4.5v9L12 21l-8-4.5z" />
        <path d="M12 12v9M4 7.5 12 12l8-4.5" />
      </>
    ),
    schedule: (
      <>
        <path d="M4 5h16M4 12h10M4 19h13" />
        <circle cx="18" cy="12" r="2" />
      </>
    ),
    risk: (
      <>
        <path d="M12 3 2.8 20h18.4z" />
        <path d="M12 9v5M12 17.2v.1" />
      </>
    ),
    supply: (
      <>
        <path d="M3 7h11v10H3zM14 10h4l3 3v4h-7z" />
        <circle cx="7" cy="19" r="1.6" />
        <circle cx="18" cy="19" r="1.6" />
      </>
    ),
    milestone: (
      <>
        <path d="M6 3v18M6 4h11l-1.7 4L17 12H6" />
      </>
    ),
    simulation: (
      <>
        <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />
      </>
    ),
    scenario: (
      <>
        <circle cx="6" cy="6" r="2.2" />
        <circle cx="18" cy="18" r="2.2" />
        <path d="M6 8.2v5.3a4 4 0 0 0 4 4h5.6M8.2 6h7.3a2.5 2.5 0 0 1 2.5 2.5v7.3" />
      </>
    ),
    optimize: (
      <>
        <path d="M4 20V10M10 20V4M16 20v-6M22 20H2" />
        <path d="m4 7 5-4 5 6 6-5" />
      </>
    ),
    ai: (
      <>
        <path d="M12 3 13.8 8.2 19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />
        <path d="M19 15.5 19.9 18l2.5.9-2.5.9L19 22l-.9-2.2-2.5-.9 2.5-.9z" />
      </>
    ),
    decisions: (
      <>
        <path d="M5 4h14v16H5z" />
        <path d="M8.5 9h7M8.5 13h7M8.5 17h4" />
      </>
    ),
    method: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 8v.1M11 12h1v5h1" />
      </>
    ),
    settings: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4v-.2a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.6-1H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1z" />
      </>
    ),
    arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
    refresh: (
      <>
        <path d="M21 12a9 9 0 1 1-2.6-6.4" />
        <path d="M21 3v6h-6" />
      </>
    ),
    play: <path d="m8 5 11 7-11 7z" />,
    download: (
      <>
        <path d="M12 3v12M7 10l5 5 5-5" />
        <path d="M4 19h16" />
      </>
    ),
    check: <path d="m4 12 5 5L20 6" />,
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    spark: <path d="M13 2 4 14h6l-1 8 9-12h-6z" />,
    users: (
      <>
        <circle cx="9" cy="8" r="3" />
        <path d="M3 20a6 6 0 0 1 12 0M16 5.5a3 3 0 0 1 0 5.8M18 20a5 5 0 0 0-2-4" />
      </>
    ),
    alert: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v6M12 16.5v.1" />
      </>
    ),
    info: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v5M12 7.5v.1" />
      </>
    ),
  }
  return <svg {...common}>{paths[name] || paths.dashboard}</svg>
}
