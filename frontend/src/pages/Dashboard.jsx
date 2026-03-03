import { useState } from 'react'
import { useProject } from '../App'
import { getHealth, triggerJiraSync } from '../api'
import { useQuery } from '../hooks/useQuery'

import ProjectSelector  from '../components/ProjectSelector'
import KpiCard          from '../components/KpiCard'
import VelocityChart    from '../components/VelocityChart'
import CycleTimeChart   from '../components/CycleTimeChart'
import ScopeCreepBadge  from '../components/ScopeCreepBadge'
import SprintCompletion from '../components/SprintCompletion'
import DistributionChart from '../components/DistributionChart'
import TimeTrackingChart from '../components/TimeTrackingChart'

import {
  Zap, Clock, BookOpen, Target,
  RefreshCw, AlertTriangle,
} from 'lucide-react'

// ── Tiny helpers ──────────────────────────────────────────────────────────────

function fmt(val, suffix = '', decimals = 1) {
  if (val == null) return '—'
  return `${Number(val).toFixed(decimals)}${suffix}`
}

function statusColor(pct) {
  if (pct == null) return 'text-ghost'
  if (pct >= 80) return 'text-sage'
  if (pct >= 60) return 'text-amber'
  return 'text-rose'
}

// ── Top navigation bar ────────────────────────────────────────────────────────

function Navbar({ project, onRefresh, refreshing }) {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-ink/90 backdrop-blur-sm">
      <div className="max-w-screen-2xl mx-auto px-6 h-14 flex items-center justify-between gap-4">
        {/* Wordmark */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="w-7 h-7 rounded-lg bg-azure/15 border border-azure/30 flex items-center justify-center">
            <Zap size={14} className="text-azure" />
          </div>
          <span className="font-display text-snow text-lg leading-none tracking-tight">
            Delivery Intelligence
          </span>
          <span className="hidden sm:block label bg-panel px-2 py-0.5 rounded border border-border">
            Beta
          </span>
        </div>

        {/* Right controls */}
        <div className="flex items-center gap-3">
          <ProjectSelector />
          <button
            onClick={onRefresh}
            disabled={refreshing}
            title="Refresh all data"
            className="w-8 h-8 rounded-lg border border-border bg-panel hover:bg-slate hover:border-muted transition-colors flex items-center justify-center"
          >
            <RefreshCw size={14} className={`text-silver ${refreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>
    </header>
  )
}

// ── KPI row ───────────────────────────────────────────────────────────────────

function KpiRow({ healthData, loading, error }) {
  if (error) {
    return (
      <div className="panel p-4 flex items-center gap-3 text-amber">
        <AlertTriangle size={16} />
        <span className="text-sm">Could not load health metrics: {error}</span>
      </div>
    )
  }

  const h  = healthData
  const vel = h?.velocity
  const ct  = h?.cycle_time
  const bl  = h?.backlog
  const sp  = h?.current_sprint

  const kpis = [
    {
      icon:    <Zap size={16} />,
      color:   'azure',
      label:   'Predictability',
      value:   fmt(vel?.predictability_pct, '%', 1),
      sub:     vel ? `Avg ${fmt(vel.average_completed_points, ' pts', 1)} / sprint` : null,
      quality: statusColor(vel?.predictability_pct),
      delay:   '0ms',
    },
    {
      icon:    <Clock size={16} />,
      color:   'teal',
      label:   'Mean Cycle Time',
      value:   fmt(ct?.mean_days, 'd', 1),
      sub:     ct ? `p95 = ${fmt(ct.p95_days, 'd', 1)}  ·  n=${ct.sample_size}` : null,
      quality: ct?.mean_days != null ? (ct.mean_days <= 5 ? 'text-sage' : ct.mean_days <= 10 ? 'text-amber' : 'text-rose') : 'text-ghost',
      delay:   '80ms',
    },
    {
      icon:    <BookOpen size={16} />,
      color:   'violet',
      label:   'Backlog Readiness',
      value:   fmt(bl?.full_readiness_pct, '%', 1),
      sub:     bl ? `${bl.total} items  ·  ${fmt(bl.ac_readiness_pct, '% with AC', 1)}` : null,
      quality: statusColor(bl?.full_readiness_pct),
      delay:   '160ms',
    },
    {
      icon:    <Target size={16} />,
      color:   'amber',
      label:   'Sprint Completion',
      value:   sp ? fmt(sp.completion_pct_points, '%', 1) : '—',
      sub:     sp ? sp.sprint_name : 'No active sprint',
      quality: statusColor(sp?.completion_pct_points),
      delay:   '240ms',
    },
  ]

  return (
    <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
      {kpis.map((k) => (
        <KpiCard key={k.label} {...k} loading={loading} />
      ))}
    </div>
  )
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { project } = useProject()
  const key = project?.jira_key

  
  const [refreshToken, setRefreshToken] = useState(0)
  const [isSyncing, setIsSyncing] = useState(false)

  const handleManualSync = async () => {
    if (!key) return
    setIsSyncing(true) // Starts the spinning animation on the button
    
    // 1. We removed the heavy triggerJiraSync(key) call!
    // The background Python worker handles Jira downloads now.
    
    // 2. We just tell React to instantly fetch the latest SQL data from our database
    setRefreshToken((n) => n + 1) 
    
    // 3. Stop the spinning animation after a tiny delay so the UI feels responsive
    setTimeout(() => {
      setIsSyncing(false) 
    }, 500)
  }

  const { data: health, loading: healthLoading, error: healthError } =
    useQuery(() => getHealth(key), `${key}-${refreshToken}`)

  return (
    <div className="min-h-screen bg-ink text-cloud">
	  <Navbar project={project} onRefresh={handleManualSync} refreshing={isSyncing || healthLoading} />

      <main className="max-w-screen-2xl mx-auto px-6 py-8 space-y-8">

        {/* Project breadcrumb */}
        <div className="flex items-baseline gap-3" style={{ animationDelay: '0ms' }}>
          <h1 className="font-display text-snow text-3xl tracking-tight">
            {project?.name ?? 'Loading…'}
          </h1>
          <span className="label text-ghost">{key}</span>
        </div>

        {/* KPI row */}
        <KpiRow
          healthData={health}
          loading={healthLoading}
          error={healthError}
        />

        {/* Primary charts row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <VelocityChart projectKey={key} refreshToken={refreshToken} />
          <CycleTimeChart projectKey={key} refreshToken={refreshToken} />
        </div>

        {/* Secondary row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <SprintCompletion projectKey={key} refreshToken={refreshToken} />
          </div>
          <ScopeCreepBadge projectKey={key} refreshToken={refreshToken} />
        </div>
		
		{/* NEW TIME TRACKING ROW */}
        <div className="grid grid-cols-1 gap-6">
           <TimeTrackingChart projectKey={key} refreshToken={refreshToken} />
        </div>

        {/* Distribution full-width */}
        <DistributionChart projectKey={key} refreshToken={refreshToken} />

        {/* Footer */}
        <footer className="text-center label text-muted pb-6 pt-2">
          Jira Delivery Analytics Platform — data synced from Jira Cloud
        </footer>
      </main>
    </div>
  )
}


