import { useQuery } from '../hooks/useQuery'
import { getDistribution } from '../api'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, Cell,
} from 'recharts'
import { LayoutGrid } from 'lucide-react'

const STATUS_COLORS = {
  'Done':        '#10b981',
  'In Progress': '#3b82f6',
  'To Do':       '#2e3447',
}

function DistTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const total = payload.reduce((s, p) => s + (p.value ?? 0), 0)
  return (
    <div className="bg-slate border border-border rounded-lg p-3 shadow-xl text-xs">
      <p className="font-mono text-cloud mb-2">{label}</p>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2 mb-1">
          <span className="w-2 h-2 rounded-sm" style={{ background: p.fill }} />
          <span className="text-ghost">{p.name}:</span>
          <span className="text-snow font-mono">{p.value ?? 0} pts</span>
          <span className="text-muted">
            ({total > 0 ? ((p.value / total) * 100).toFixed(0) : 0}%)
          </span>
        </div>
      ))}
      <div className="mt-1 pt-1 border-t border-border text-muted">
        Total: <span className="text-silver font-mono">{total} pts</span>
      </div>
    </div>
  )
}

export default function DistributionChart({ projectKey, refreshToken }) {
  const { data, loading, error } = useQuery(
    () => getDistribution(projectKey),
    `${projectKey}-dist-${refreshToken}`
  )

  // Transform by_type into stacked bar data: one entry per issue_type
  const rawByType = data?.by_type ?? []
  const types = [...new Set(rawByType.map((r) => r.issue_type).filter(Boolean))]
  const statusCategories = ['To Do', 'In Progress', 'Done']

  const chartData = types.map((type) => {
    const entry = { type }
    statusCategories.forEach((sc) => {
      const row = rawByType.find((r) => r.issue_type === type && r.status_category === sc)
      entry[sc] = row?.total_points ?? 0
    })
    return entry
  })

  // Also build a summary pie-like table from by_status
  const byStatus = data?.by_status ?? []

  return (
    <div className="panel animate-fade-up" style={{ animationDelay: '300ms' }}>
      <div className="panel-header pb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <LayoutGrid size={15} className="text-violet" />
            <h2 className="text-snow font-semibold text-sm">Story Point Distribution</h2>
          </div>
          <p className="label">Points across statuses, broken down by issue type</p>
        </div>

        {/* Status summary badges */}
        {!loading && byStatus.length > 0 && (
          <div className="flex items-center gap-3">
            {byStatus.map((s) => {
              const color = STATUS_COLORS[s.status_category] ?? '#4a5168'
              return (
                <div key={s.status_category} className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-sm" style={{ background: color }} />
                  <span className="label">{s.status_category}</span>
                  <span className="font-mono text-xs text-silver">{s.total_points}pts</span>
                  <span className="label text-muted">({s.pct_of_total}%)</span>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="px-6 pb-6">
        {loading && <div className="skeleton h-48 w-full" />}
        {error && <p className="text-rose text-sm text-center py-10">{error}</p>}
        {!loading && !error && chartData.length === 0 && (
          <p className="text-ghost text-sm text-center py-10">No issue data found.</p>
        )}
        {!loading && !error && chartData.length > 0 && (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chartData} barCategoryGap="35%">
              <CartesianGrid strokeDasharray="3 3" stroke="#2e3447" vertical={false} />
              <XAxis
                dataKey="type"
                tick={{ fill: '#9ba3bf', fontSize: 12, fontFamily: 'DM Sans' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: '#6b7494', fontSize: 11, fontFamily: 'JetBrains Mono' }}
                axisLine={false}
                tickLine={false}
                width={34}
              />
              <Tooltip content={<DistTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
              <Legend
                wrapperStyle={{ fontSize: 11, color: '#6b7494', paddingTop: 10 }}
                iconType="square"
                iconSize={8}
              />
              {statusCategories.map((sc) => (
                <Bar
                  key={sc}
                  dataKey={sc}
                  stackId="a"
                  fill={STATUS_COLORS[sc] ?? '#4a5168'}
                  radius={sc === 'Done' ? [3, 3, 0, 0] : [0, 0, 0, 0]}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
