import { useEffect, useMemo, useRef } from 'react'
import Plotly from 'plotly.js/lib/core'
import bar from 'plotly.js/lib/bar'
import scatter from 'plotly.js/lib/scatter'

/**
 * Thin Plotly wrapper.
 *
 * Only the trace types this platform uses are registered, which keeps the
 * bundle at roughly a quarter of the full `plotly.js` distribution and the
 * production build well inside a small container's memory budget.
 */
Plotly.register([bar, scatter])

const INK = '#1b2738'
const MUTED = '#66758a'
const GRID = '#e6ebf1'

export const PALETTE = {
  navy: '#17456b',
  teal: '#0f7a70',
  amber: '#c07a1f',
  red: '#b23a2f',
  slate: '#7a8ca3',
  green: '#2f7d4f',
  light: '#a9c3d6',
}

export function baseLayout(overrides: any = {}): any {
  return {
    autosize: true,
    margin: { l: 48, r: 18, t: 12, b: 42 },
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'Inter, system-ui, sans-serif', size: 12, color: INK },
    xaxis: { gridcolor: GRID, zeroline: false, linecolor: GRID, tickfont: { color: MUTED } },
    yaxis: { gridcolor: GRID, zeroline: false, linecolor: GRID, tickfont: { color: MUTED } },
    hoverlabel: {
      bgcolor: '#0f1d2e',
      bordercolor: '#0f1d2e',
      font: { color: '#ffffff', size: 12 },
    },
    showlegend: false,
    ...overrides,
  }
}

export default function PlotChart({
  data,
  layout,
  height = 320,
  config,
}: {
  data: any[]
  layout?: any
  height?: number
  config?: any
}) {
  const container = useRef<HTMLDivElement>(null)
  const signature = useMemo(() => JSON.stringify([data, layout, height, config]), [data, layout, height, config])

  useEffect(() => {
    const node = container.current
    if (!node) return
    const merged = { ...baseLayout(layout), height, autosize: true }
    Plotly.react(node, data, merged, {
      displayModeBar: false,
      responsive: true,
      locale: 'en-GB',
      ...config,
    })
    const resize = () => {
      if (container.current) Plotly.Plots.resize(container.current)
    }
    window.addEventListener('resize', resize)
    return () => {
      window.removeEventListener('resize', resize)
      if (container.current) Plotly.purge(container.current)
    }
    // `signature` is a stable digest of the plot inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature])

  return <div ref={container} style={{ width: '100%', height }} className="plotly-host" />
}
