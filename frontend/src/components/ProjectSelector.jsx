import { useProject } from '../App'
import { ChevronDown } from 'lucide-react'

export default function ProjectSelector() {
  const { project, projects, setProject } = useProject()

  if (!projects.length) return null

  return (
    <div className="relative">
      <select
        value={project?.jira_key ?? ''}
        onChange={(e) => {
          const p = projects.find((p) => p.jira_key === e.target.value)
          if (p) setProject(p)
        }}
        className="appearance-none h-8 pl-3 pr-8 rounded-lg border border-border bg-panel
                   text-sm text-cloud hover:border-muted focus:outline-none focus:border-azure
                   transition-colors cursor-pointer font-mono"
      >
        {projects.map((p) => (
          <option key={p.jira_key} value={p.jira_key}>
            {p.jira_key} — {p.name}
          </option>
        ))}
      </select>
      <ChevronDown
        size={12}
        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ghost pointer-events-none"
      />
    </div>
  )
}
