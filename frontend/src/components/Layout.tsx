import { useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useApi } from '../hooks'
import { Badge, Icon, Loading } from './ui'

const programNav = [
  { to: 'overview', label: 'Program overview', icon: 'programs' },
  { to: 'schedule', label: 'Schedule & capacity', icon: 'schedule' },
  { to: 'risks', label: 'Risk attribution', icon: 'risk' },
  { to: 'suppliers', label: 'Supply exposure', icon: 'supply' },
  { to: 'milestones', label: 'Milestones', icon: 'milestone' },
  { to: 'simulation', label: 'Monte Carlo', icon: 'simulation' },
  { to: 'scenarios', label: 'Scenarios', icon: 'scenario' },
  { to: 'optimization', label: 'Optimiser', icon: 'optimize' },
  { to: 'assistant', label: 'Risk copilot', icon: 'ai' },
  { to: 'decisions', label: 'Decisions & audit', icon: 'decisions' },
  { to: 'methodology', label: 'Methodology', icon: 'method' },
]

export default function Layout() {
  const { projectId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const { data: projects, loading } = useApi(() => api.projects.list(), [])

  const activeProject = useMemo(
    () => projects?.find((project) => project.id === projectId) || null,
    [projects, projectId],
  )
  const pageLabel = useMemo(() => {
    if (location.pathname === '/') return 'Portfolio overview'
    if (location.pathname === '/projects') return 'Programs'
    if (location.pathname === '/settings') return 'Platform settings'
    const key = programNav.find((item) => location.pathname.endsWith(item.to))
    return key?.label || 'Program'
  }, [location.pathname])

  return (
    <div className="shell">
      <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <div className="brand-mark">
            <span>N</span>
          </div>
          <div>
            <div className="brand-title">NPI Digital Twin</div>
            <div className="brand-sub">Launch risk intelligence</div>
          </div>
          <button className="icon-btn sidebar-close" onClick={() => setOpen(false)} aria-label="Close navigation">
            ×
          </button>
        </div>

        <div className="sidebar-section">
          <div className="sidebar-label">Portfolio</div>
          <NavLink to="/" end className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Icon name="dashboard" />
            <span>Command centre</span>
          </NavLink>
          <NavLink to="/projects" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Icon name="programs" />
            <span>Programs</span>
            {projects && <span className="nav-count">{projects.length}</span>}
          </NavLink>
        </div>

        <div className="sidebar-section grow">
          <div className="sidebar-label">
            Program workspace
            {activeProject && <span className="sidebar-key">{activeProject.key}</span>}
          </div>
          {!activeProject && (
            <div className="program-hint">Select a program to open its schedule, risk and decision tools.</div>
          )}
          {programNav.map((item) =>
            activeProject ? (
              <NavLink
                key={item.to}
                to={`/projects/${activeProject.id}/${item.to}`}
                className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                onClick={() => setOpen(false)}
              >
                <Icon name={item.icon} />
                <span>{item.label}</span>
              </NavLink>
            ) : (
              <div key={item.to} className="nav-item disabled" title="Select a program first">
                <Icon name={item.icon} />
                <span>{item.label}</span>
              </div>
            ),
          )}
        </div>

        <div className="sidebar-footer">
          <NavLink to="/settings" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Icon name="settings" />
            <span>Settings & AI providers</span>
          </NavLink>
          <div className="sidebar-meta">
            <span>v1.0.0</span>
            <a href={import.meta.env.VITE_DOCS_URL || 'http://localhost:8000/docs'} target="_blank" rel="noreferrer">
              API docs ↗
            </a>
          </div>
        </div>
      </aside>

      {open && <div className="scrim" onClick={() => setOpen(false)} />}

      <div className="main">
        <header className="topbar">
          <button className="icon-btn menu-btn" onClick={() => setOpen(true)} aria-label="Open navigation">
            ☰
          </button>
          <div className="crumbs">
            <span className="crumb-muted">NPI twin</span>
            <span className="crumb-sep">/</span>
            {activeProject ? (
              <>
                <button className="crumb-project" onClick={() => navigate(`/projects/${activeProject.id}/overview`)}>
                  {activeProject.key}
                </button>
                <span className="crumb-sep">/</span>
                <span>{pageLabel}</span>
              </>
            ) : (
              <span>{pageLabel}</span>
            )}
          </div>
          <div className="topbar-right">
            {activeProject && (
              <select
                className="project-switcher"
                value={activeProject.id}
                onChange={(event) => {
                  const target = projects?.find((project) => project.id === event.target.value)
                  if (target) {
                    const suffix = location.pathname.endsWith('/overview') ? '/overview' : '/overview'
                    navigate(`/projects/${target.id}${suffix}`)
                  }
                }}
                aria-label="Switch program"
              >
                {projects?.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.key} — {project.name}
                  </option>
                ))}
              </select>
            )}
            <Badge tone="good" dot>
              API connected
            </Badge>
            <span className="topbar-date">
              {new Date().toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' })}
            </span>
          </div>
        </header>

        <main className="content">
          {loading && !projects ? <Loading label="Connecting to the digital twin" /> : <Outlet context={{ projects: projects || [] }} />}
          {projects && projects.length > 0 && !activeProject && location.pathname.startsWith('/projects/') && (
            <div className="state state-empty">
              <div className="state-icon">?</div>
              <div>
                <strong>Program not found</strong>
                <p>The selected program may have been archived. Choose another from the portfolio.</p>
              </div>
            </div>
          )}
        </main>
        <footer className="footer">
          <span>Synthetic demo data · deterministic CPM + CP-SAT + serial-SGS Monte Carlo</span>
          <span>Forecasts are model estimates, not guarantees.</span>
        </footer>
      </div>
    </div>
  )
}
