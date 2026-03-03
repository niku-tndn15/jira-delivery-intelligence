import { useState, useEffect, createContext, useContext } from 'react'
import { getProjects } from './api'
import Dashboard from './pages/Dashboard'
import { Activity } from 'lucide-react'

// ── Project context ────────────────────────────────────────────────────────────
export const ProjectContext = createContext({ project: null, projects: [] })
export const useProject = () => useContext(ProjectContext)

// ── Skeleton for initial load ─────────────────────────────────────────────────
function BootLoader() {
  return (
    <div className="min-h-screen bg-ink flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="relative">
          <Activity size={32} className="text-azure animate-pulse" />
          <div className="absolute inset-0 rounded-full bg-azure/20 animate-ping" />
        </div>
        <p className="label text-ghost">Connecting to analytics API…</p>
      </div>
    </div>
  )
}

function ErrorScreen({ message }) {
  // 1. Detect if this is a sync timeout vs a real crash
  const isBuilding = 
    message?.includes('502') || 
    message?.toLowerCase().includes('gateway') || 
    message?.toLowerCase().includes('network');

  // 2. Smart Timer: Check if we already did the 3-minute wait
  const [timeLeft, setTimeLeft] = useState(() => {
    const hasWaited = sessionStorage.getItem('hasWaitedInitialSync');
    return hasWaited ? 60 : 200; // 60s for subsequent retries, 180s for the first
  });

  useEffect(() => {
    if (isBuilding) {
      const timer = setInterval(() => {
        setTimeLeft((prev) => {
          if (prev <= 1) {
            clearInterval(timer);
            // Drop a note in browser storage before reloading
            sessionStorage.setItem('hasWaitedInitialSync', 'true');
            window.location.reload(); 
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
      return () => clearInterval(timer);
    }
  }, [isBuilding]);

  if (isBuilding) {
    return (
      <div className="min-h-screen bg-ink flex items-center justify-center">
        <div className="panel p-8 max-w-md text-center border border-azure/30">
          <div className="w-12 h-12 rounded-full bg-azure/10 flex items-center justify-center mx-auto mb-4 animate-pulse">
            <Activity size={22} className="text-azure" /> 
          </div>
          <h2 className="font-display text-snow text-xl mb-2">Building Data Warehouse 🚀</h2>
          <p className="text-ghost text-sm leading-relaxed mb-4">
            Syncing historical tickets from Jira Cloud. 
            {timeLeft > 60 
              ? " For enterprise datasets, this initial download takes a few minutes." 
              : " Finalizing the data pipeline, almost there..."}
          </p>
          <div className="inline-flex items-center justify-center px-4 py-2 bg-azure/10 text-azure rounded-full text-xs font-mono">
            Auto-refreshing in {timeLeft}s...
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-ink flex items-center justify-center">
      <div className="panel p-8 max-w-md text-center">
        <div className="w-12 h-12 rounded-full bg-rose/10 flex items-center justify-center mx-auto mb-4">
          <Activity size={22} className="text-rose" />
        </div>
        <h2 className="font-display text-snow text-xl mb-2">API Unreachable</h2>
        <p className="text-ghost text-sm leading-relaxed mb-4">{message}</p>
        <p className="text-muted text-xs">
          Make sure the FastAPI server is running on{' '}
          <code className="font-mono text-azure">localhost:8000</code>
        </p>
      </div>
    </div>
  )
}

export default function App() {
  const [projects,   setProjects]   = useState([])
  const [project,    setProject]    = useState(null)
  const [bootState,  setBootState]  = useState('loading') 
  const [bootError,  setBootError]  = useState('')

  useEffect(() => {
    getProjects()
      .then((data) => {
        setProjects(data)
        const defaultProject =
          data.find((p) => p.jira_key === 'GETSCTCL') ?? data[0] ?? null
        setProject(defaultProject)
        setBootState('ready')
      })
      .catch((err) => {
        setBootError(err.message)
        setBootState('error')
      })
  }, [])

  if (bootState === 'loading') return <BootLoader />
  if (bootState === 'error')   return <ErrorScreen message={bootError} />

  return (
    <ProjectContext.Provider value={{ project, projects, setProject }}>
      <Dashboard />
    </ProjectContext.Provider>
  )
}