import axios from 'axios'

const api = axios.create({
  baseURL: '/',          // Vite proxy forwards /api → http://127.0.0.1:8000
  timeout: 45_000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const msg =
      err.response?.data?.detail ||
      err.response?.statusText ||
      err.message ||
      'Unknown error'
    return Promise.reject(new Error(msg))
  }
)

// ── Endpoints ─────────────────────────────────────────────────────────────────

export const getProjects = ()           => api.get('/api/projects')

export const getHealth   = (key)        => api.get(`/api/${key}/metrics/health`)
export const getVelocity = (key, w = 3) => api.get(`/api/${key}/metrics/velocity?window=${w}`)
export const getCycleTime = (key)       => api.get(`/api/${key}/metrics/cycle-time`)
export const getCycleTimeDist = (key)   => api.get(`/api/${key}/metrics/cycle-time/distribution`)
export const getScopeCreep = (key, n=5) => api.get(`/api/${key}/metrics/scope-creep?limit=${n}`)
export const getSprintCompletion = (key)=> api.get(`/api/${key}/metrics/sprint-completion`)
export const getDistribution = (key)    => api.get(`/api/${key}/metrics/distribution`)
export const getBacklogReadiness = (key)=> api.get(`/api/${key}/metrics/backlog-readiness`)

export default api

export async function triggerJiraSync(projectKey) {
  // We use POST because we are instructing the server to perform an action
  const res = await axios.post(`http://127.0.0.1:8000/api/projects/${projectKey}/sync`)
  return res.data
}