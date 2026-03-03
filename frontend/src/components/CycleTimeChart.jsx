import { useQuery } from '../hooks/useQuery'
import { getCycleTime, getCycleTimeDist } from '../api'
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { Clock } from 'lucide-react'

// ── Custom scatter tooltip ────────────────────────────────────────────────────

function ScatterTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  return (
    <div className="bg-slate border border-border rounded-lg p-3 shadow-xl text-xs max-w-xs">
      <p className="font-mono text-teal mb-1">{d.jira_issue_id}</p>
      <p className="text-cloud truncate mb-1">{d.summary}</p>
      <div className="flex gap-3 text-ghost mt-1">
        <span>Type: <span className="text-silver">{d.issue_type}</span></span>
        <span>Pts: <span className="text-silver">{d.story_points ?? '—'}</span></span>
        <span>Days: <span className="text-teal font-mono">{d.cycle_days}</span></span>
      </div>
    </div>
  )
}

// ── Percentile pill ───────────────────────────────────────────────────────────

function Pct({ label, value, color = 'text-snow' }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <span className={`font-display text-xl leading-none ${color}`}>
        {value != null ? `${value.toFixed(1)}d` : '—'}
      </span>
      <span className="label">{label}</span>
    </div>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function CycleTimeChart({ projectKey, refreshToken }) {
  const { data: stats, loading: statsLoading, error: statsError } =
    useQuery(() => getCycleTime(projectKey), `${projectKey}-ct-${refreshToken}`)

  const { data: dist, loading: distLoading } =
    useQuery(() => getCycleTimeDist(projectKey), `${projectKey}-ct-dist-${refreshToken}`)

  const loading = statsLoading || distLoading

  // Scatter needs numeric x (issue index) and y (cycle_days)
  const scatterData = (dist ?? [])
    .filter((d) => d.cycle_days != null)
    .map((d, i) => ({ ...d, idx: i + 1 }))

  const p50 = stats?.p50_days
  const p95 = stats?.p95_days

  return (
    <div className="panel animate-fade-up" style={{ animationDelay: '180ms' }}>
      <div className="panel-header pb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Clock size={15} className="text-teal" />
            <h2 className="text-snow font-semibold text-sm">Cycle Time</h2>
          </div>
          <p className="label">In Progress → Done (Stories)</p>
        </div>
        {stats && (
          <span className="label bg-teal/10 border border-teal/20 text-teal px-2 py-1 rounded">
            n = {stats.sample_size}
          </span>
        )}
      </div>

      <div className="px-6">
        {/* Percentile stat row */}
        {loading && <div className="skeleton h-14 w-full mb-4" />}
        {!loading && stats && (
          <div className="grid grid-cols-4 gap-2 pb-5 border-b border-border mb-4">
            <Pct label="Mean"   value={stats.mean_days}  color="text-cloud" />
            <Pct label="p50"    value={stats.p50_days}   color="text-teal" />
            <Pct label="p75"    value={stats.p75_days}   color="text-amber" />
            <Pct label="p95"    value={stats.p95_days}   color="text-rose" />
          </div>
        )}
        {statsError && <p className="text-rose text-sm text-center pb-4">{statsError}</p>}
      </div>

      {/* Scatter chart */}
      <div className="px-6 pb-6">
        {loading && <div className="skeleton h-36 w-full" />}
        {!loading && scatterData.length === 0 && (
          <p className="text-ghost text-sm text-center py-6">
            No completed issues with cycle time data.
          </p>
        )}
        {!loading && scatterData.length > 0 && (
          <ResponsiveContainer width="100%" height={150}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" stroke="#2e3447" />
              <XAxis
                dataKey="idx"
                name="Issue"
                tick={false}
                axisLine={false}
                tickLine={false}
                label={{
                  value: 'Issues (most recent →)',
                  fill: '#6b7494',
                  fontSize: 10,
                  fontFamily: 'DM Sans',
                  position: 'insideBottomRight',
                  offset: -4,
                }}
              />
              <YAxis
                dataKey="cycle_days"
                name="Days"
                tick={{ fill: '#6b7494', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                axisLine={false}
                tickLine={false}
                width={28}
              />
              <Tooltip content={<ScatterTooltip />} cursor={{ strokeDasharray: '3 3' }} />
              {p50 && (
                <ReferenceLine
                  y={p50}
                  stroke="#14b8a6"
                  strokeDasharray="4 3"
                  strokeOpacity={0.6}
                  label={{ value: 'p50', fill: '#14b8a6', fontSize: 9, position: 'insideTopRight' }}
                />
              )}
              {p95 && (
                <ReferenceLine
                  y={p95}
                  stroke="#f43f5e"
                  strokeDasharray="4 3"
                  strokeOpacity={0.5}
                  label={{ value: 'p95', fill: '#f43f5e', fontSize: 9, position: 'insideTopRight' }}
                />
              )}
              <Scatter
                data={scatterData}
                fill="#14b8a6"
                fillOpacity={0.7}
                shape={(props) => {
                  const { cx, cy } = props
                  return <circle cx={cx} cy={cy} r={3} fill="#14b8a6" fillOpacity={0.75} />
                }}
              />
            </ScatterChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
