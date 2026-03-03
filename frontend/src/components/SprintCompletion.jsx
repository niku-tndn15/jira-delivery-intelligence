import { useQuery } from '../hooks/useQuery'
import { getSprintCompletion } from '../api'
import { Target } from 'lucide-react'

function ProgressBar({ done, inProgress, todo, total }) {
  if (!total) return <div className="h-2 rounded-full bg-panel w-full" />
  const donePct = (done / total) * 100
  const inPct   = (inProgress / total) * 100
  const todoPct = (todo / total) * 100

  return (
    <div className="h-2 rounded-full bg-panel overflow-hidden flex w-full">
      <div className="h-full bg-sage transition-all"    style={{ width: `${donePct}%` }} />
      <div className="h-full bg-azure transition-all"   style={{ width: `${inPct}%` }} />
      <div className="h-full bg-border transition-all"  style={{ width: `${todoPct}%` }} />
    </div>
  )
}

function SprintRow({ sprint, isFirst }) {
  const total = sprint.total_points ?? 0
  return (
    <div className={`py-4 ${isFirst ? '' : 'border-t border-border'}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm text-cloud font-medium">{sprint.sprint_name}</span>
          {sprint.state === 'active' && (
            <span className="label px-1.5 py-0.5 rounded bg-azure/10 border border-azure/20 text-azure">
              active
            </span>
          )}
        </div>
        <div className="flex items-center gap-4 text-xs font-mono">
          <span className="text-sage">{sprint.done_points ?? 0} done</span>
          <span className="text-azure">{sprint.in_progress_points ?? 0} in prog</span>
          <span className="text-ghost">{sprint.todo_points ?? 0} todo</span>
          <span
            className={`font-semibold ${
              (sprint.completion_pct_points ?? 0) >= 80 ? 'text-sage' :
              (sprint.completion_pct_points ?? 0) >= 60 ? 'text-amber' : 'text-rose'
            }`}
          >
            {sprint.completion_pct_points ?? 0}%
          </span>
        </div>
      </div>
      <ProgressBar
        done={sprint.done_points ?? 0}
        inProgress={sprint.in_progress_points ?? 0}
        todo={sprint.todo_points ?? 0}
        total={total}
      />
      <div className="flex items-center justify-between mt-1.5 text-xs text-muted font-mono">
        <span>{sprint.done_issues}/{sprint.total_issues} issues</span>
        <span>{total} total pts</span>
      </div>
    </div>
  )
}

export default function SprintCompletion({ projectKey, refreshToken }) {
  const { data, loading, error } = useQuery(
    () => getSprintCompletion(projectKey),
    `${projectKey}-completion-${refreshToken}`
  )

  const sprints = data ?? []

  return (
    <div className="panel animate-fade-up" style={{ animationDelay: '220ms' }}>
      <div className="panel-header pb-2">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Target size={15} className="text-sage" />
            <h2 className="text-snow font-semibold text-sm">Sprint Completion</h2>
          </div>
          <p className="label">Story points by status · last 5 sprints</p>
        </div>
        {/* Legend */}
        <div className="flex items-center gap-3">
          {[['bg-sage','Done'],['bg-azure','In Prog'],['bg-border','Todo']].map(([color, label]) => (
            <div key={label} className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-sm ${color}`} />
              <span className="label">{label}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="px-6 pb-6">
        {loading && (
          <div className="space-y-5 pt-4">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="space-y-2">
                <div className="skeleton h-4 w-48" />
                <div className="skeleton h-2 w-full rounded-full" />
              </div>
            ))}
          </div>
        )}
        {error && <p className="text-rose text-sm text-center py-8">{error}</p>}
        {!loading && !error && sprints.length === 0 && (
          <p className="text-ghost text-sm text-center py-8">No sprint data.</p>
        )}
        {!loading && !error && sprints.map((sprint, i) => (
          <SprintRow key={sprint.sprint_id} sprint={sprint} isFirst={i === 0} />
        ))}
      </div>
    </div>
  )
}
