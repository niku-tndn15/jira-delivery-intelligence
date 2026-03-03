import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { useQuery } from '../useQuery'
import axios from 'axios'

export default function TimeTrackingChart({ projectKey, refreshToken }) {
  const { data, loading, error } = useQuery(
    () => axios.get(`http://127.0.0.1:8000/api/${projectKey}/metrics/time-tracking`).then(res => res.data),
    `time-${projectKey}-${refreshToken}`
  )

  if (loading) return <div className="panel p-6 animate-pulse h-80"></div>
  if (error) return <div className="panel p-6 text-rose">Error loading time tracking: {error.message}</div>
  if (!data || data.length === 0) return null

  return (
    <div className="panel p-6 flex flex-col h-full">
      <h3 className="font-display text-snow mb-1">Time Estimation vs Logged</h3>
      <p className="label text-ghost mb-6">HOURS ESTIMATED VS ACTUAL HOURS SPENT</p>
      <div className="flex-1 min-h-[250px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2e3d" vertical={false} />
            <XAxis dataKey="sprint_name" stroke="#6b7280" fontSize={11} tickLine={false} axisLine={false} />
            <YAxis stroke="#6b7280" fontSize={11} tickLine={false} axisLine={false} />
            <Tooltip
              cursor={{ fill: '#1e2230' }}
              contentStyle={{ backgroundColor: '#0f1117', borderColor: '#2a2e3d', color: '#f8fafc' }}
            />
            <Legend iconType="circle" wrapperStyle={{ fontSize: '12px', color: '#94a3b8' }} />
            <Bar dataKey="estimated_hours" name="Estimated (Hrs)" fill="#3b82f6" radius={[4, 4, 0, 0]} />
            <Bar dataKey="spent_hours" name="Spent (Hrs)" fill="#10b981" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}