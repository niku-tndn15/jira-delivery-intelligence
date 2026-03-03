import { useState } from 'react'
import { useQuery } from '../hooks/useQuery'
import { getScopeCreep } from '../api'
import { AlertTriangle, ChevronDown, ChevronRight, Circle } from 'lucide-react'

// ── Colour for % badge ────────────────────────────────────────────────────────

function creepColor(pct) {
  if (pct === 0)   return { bg: 'bg-sage/10',   border: 'border-sage/20',   text: 'text-sage'   }
  if (pct <= 10)   return { bg: 'bg-amber/10',  border: 'border-amber/20',  text: 'text-amber'  }
  return              { bg: 'bg-rose/10',   border: 'border-rose/20',   text: 'text-rose'   }
}

// ── Single sprint row ─────────────────────────────────────────────────────────

function SprintRow({ sprint }) {
  const [open, setOpen] = useState(false)
  const c = creepColor(sprint.scope_creep_pct ?? 0)
  const hasDetail = sprint.added_issue_detail?.length > 0

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      {/* Header */}
      <button
        onClick={() => hasDetail && setOpen((v) => !v)}
        className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors
                    ${hasDetail ? 'hover:bg-slate cursor-pointer' : 'cursor-default'}`}
      >
        {/* Expand chevron */}
        <span className="text-ghost shrink-0">
          {hasDetail
            ? open ? <ChevronDown size={13} /> : <ChevronRight size={13} />
            : <Circle size={8} className="text-muted ml-0.5" />
          }
        </span>

        {/* Sprint name */}
        <span className="text-sm text-cloud font-medium flex-1 truncate">
          {sprint.sprint_name}
        </span>

        {/* State pill */}
        <span className={`label shrink-0 px-1.5 py-0.5 rounded
          ${sprint.state === 'active'
            ? 'bg-azure/10 text-azure border border-azure/20'
            : 'bg-panel text-ghost border border-border'}`}>
          {sprint.state}
        </span>

        {/* Scope creep % */}
        <span className={`label shrink-0 px-2 py-1 rounded border font-mono ${c.bg} ${c.border} ${c.text}`}>
          +{sprint.scope_creep_pct ?? 0}%
        </span>

        {/* Points added */}
        <span className="font-mono text-xs text-ghost shrink-0 w-20 text-right">
          {sprint.added_issues} iss / {sprint.added_points} pts
        </span>
      </button>

      {/* Drill-down: added issues */}
      {open && hasDetail && (
        <div className="border-t border-border bg-ink/40 divide-y divide-border">
          {sprint.added_issue_detail.map((iss) => (
            <div key={iss.jira_issue_id} className="flex items-start gap-3 px-4 py-2.5">
              <span className="font-mono text-xs text-amber shrink-0 w-20">{iss.jira_issue_id}</span>
              <span className="text-xs text-cloud flex-1 leading-snug">{iss.summary}</span>
              <div className="flex items-center gap-2 shrink-0 text-xs">
                <span className="text-ghost">{iss.issue_type}</span>
                {iss.story_points != null && (
                  <span className="font-mono text-silver bg-panel px-1.5 py-0.5 rounded border border-border">
                    {iss.story_points}p
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ScopeCreepBadge({ projectKey, refreshToken }) {
  const { data, loading, error } = useQuery(
    () => getScopeCreep(projectKey, 5),
    `${projectKey}-scope-${refreshToken}`
  )

  const sprints = data ?? []
  const totalAddedPts = sprints.reduce((s, r) => s + (r.added_points ?? 0), 0)
  const worstSprint   = sprints.reduce((a, b) =>
    (b.scope_creep_pct ?? 0) > (a?.scope_creep_pct ?? 0) ? b : a, null
  )

  return (
    <div className="panel animate-fade-up" style={{ animationDelay: '260ms' }}>
      <div className="panel-header pb-5">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle size={15} className="text-amber" />
            <h2 className="text-snow font-semibold text-sm">Scope Creep</h2>
          </div>
          <p className="label">Issues added after sprint start</p>
        </div>
        {totalAddedPts > 0 && (
          <span className="font-display text-xl text-amber leading-none">
            +{totalAddedPts.toFixed(0)}
            <span className="label ml-1">pts</span>
          </span>
        )}
      </div>

      <div className="px-6 pb-6 space-y-2">
        {loading && (
          <div className="space-y-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="skeleton h-11 w-full rounded-lg" />
            ))}
          </div>
        )}
        {error && <p className="text-rose text-sm text-center py-6">{error}</p>}
        {!loading && !error && sprints.length === 0 && (
          <p className="text-ghost text-sm text-center py-6">No sprint data available.</p>
        )}
        {!loading && !error && sprints.map((sprint) => (
          <SprintRow key={sprint.sprint_id} sprint={sprint} />
        ))}

        {/* Summary callout */}
        {!loading && worstSprint && (worstSprint.scope_creep_pct ?? 0) > 0 && (
          <div className="mt-3 p-3 rounded-lg bg-amber/5 border border-amber/15 text-xs text-amber leading-relaxed">
            <strong>Highest creep:</strong> {worstSprint.sprint_name} at{' '}
            {worstSprint.scope_creep_pct}% — {worstSprint.added_issues} issue
            {worstSprint.added_issues !== 1 ? 's' : ''} added mid-sprint.
          </div>
        )}
      </div>
    </div>
  )
}
