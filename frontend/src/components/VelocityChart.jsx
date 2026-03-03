import { useQuery } from '../hooks/useQuery'
import { getVelocity } from '../api'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts'
import { TrendingUp } from 'lucide-react'

// ── Custom tooltip ────────────────────────────────────────────────────────────

function VelocityTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-slate border border-border rounded-lg p-3 shadow-xl text-sm">
      <p className="font-mono text-cloud mb-2 text-xs">{label}</p>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-sm" style={{ background: p.fill }} />
          <span className="text-ghost capitalize">{p.name}:</span>
          <span className="text-snow font-mono">{p.value} pts</span>
        </div>
      ))}
      {payload.length === 2 && (
        <div className="mt-2 pt-2 border-t border-border">
          <span className="text-ghost text-xs">
            Predictability:{' '}
            <span className="text-amber font-mono">
              {payload[1]?.value && payload[0]?.value
                ? `${((payload[1].value / payload[0].value) * 100).toFixed(0)}%`
                : '—'}
            </span>
          </span>
        </div>
      )}
    </div>
  )
}

// ── Short sprint name helper ──────────────────────────────────────────────────

function shortName(name = '') {
  // "Team Sprint 24" → "Spr 24", or just truncate to 12 chars
  const match = name.match(/(\w*sprint\w*\s*\d+)/i)
  if (match) return match[1].replace(/sprint/i, 'Spr')
  return name.length > 10 ? name.slice(0, 10) + '…' : name
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function VelocityChart({ projectKey, refreshToken }) {
  const { data, loading, error } = useQuery(
    () => getVelocity(projectKey, 6),
    `${projectKey}-velocity-${refreshToken}`
  )

  const chartData = (data?.trend ?? []).map((s) => ({
    name:      shortName(s.sprint_name),
    Committed: s.committed_points ?? 0,
    Completed: s.completed_points ?? 0,
  }))

  const avgCompleted = data?.average_completed_points

  return (
    <div className="panel animate-fade-up" style={{ animationDelay: '100ms' }}>
      <div className="panel-header pb-5">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp size={15} className="text-azure" />
            <h2 className="text-snow font-semibold text-sm">Sprint Velocity</h2>
          </div>
          <p className="label">Committed vs completed story points</p>
        </div>
        {avgCompleted != null && (
          <div className="text-right">
            <div className="font-display text-2xl text-azure leading-none">
              {avgCompleted.toFixed(1)}
            </div>
            <div className="label mt-0.5">avg pts</div>
          </div>
        )}
      </div>

      <div className="px-6 pb-6">
        {loading && <div className="skeleton h-52 w-full" />}
        {error   && <p className="text-rose text-sm text-center py-10">{error}</p>}
        {!loading && !error && chartData.length === 0 && (
          <p className="text-ghost text-sm text-center py-10">No closed sprints found.</p>
        )}
        {!loading && !error && chartData.length > 0 && (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData} barGap={4} barCategoryGap="30%">
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#2e3447"
                vertical={false}
              />
              <XAxis
                dataKey="name"
                tick={{ fill: '#6b7494', fontSize: 11, fontFamily: 'JetBrains Mono' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: '#6b7494', fontSize: 11, fontFamily: 'JetBrains Mono' }}
                axisLine={false}
                tickLine={false}
                width={34}
              />
              <Tooltip content={<VelocityTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
              <Legend
                wrapperStyle={{ fontSize: 11, color: '#6b7494', paddingTop: 12 }}
                iconType="square"
                iconSize={8}
              />
              {avgCompleted != null && (
                <ReferenceLine
                  y={avgCompleted}
                  stroke="#3b82f6"
                  strokeDasharray="4 4"
                  strokeOpacity={0.5}
                  label={{
                    value: `avg ${avgCompleted.toFixed(0)}`,
                    fill: '#3b82f6',
                    fontSize: 10,
                    fontFamily: 'JetBrains Mono',
                    position: 'insideTopRight',
                  }}
                />
              )}
              <Bar dataKey="Committed" fill="#2e3447" radius={[3, 3, 0, 0]}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill="#2e3447" />
                ))}
              </Bar>
              <Bar dataKey="Completed" radius={[3, 3, 0, 0]}>
                {chartData.map((entry, i) => {
                  const pct = entry.Committed > 0 ? entry.Completed / entry.Committed : 0
                  // Green if ≥80%, amber if ≥60%, rose below
                  const fill = pct >= 0.8 ? '#10b981' : pct >= 0.6 ? '#f59e0b' : '#f43f5e'
                  return <Cell key={i} fill={fill} />
                })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
