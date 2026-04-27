'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function RecentRuns(){
  const [runs, setRuns] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(()=>{
    fetch(`${API_BASE}/runs`).then(r=>r.json()).then(j=>{
      setRuns(j.runs || [])
      setLoading(false)
    }).catch(()=>{
      setLoading(false)
    })
  },[])

  if(loading){
    return (
      <div className="space-y-3">
        {[1,2,3].map(i => (
          <div key={i} className="animate-pulse bg-slate-200 dark:bg-slate-700 h-20 rounded-xl"></div>
        ))}
      </div>
    )
  }

  if(runs.length === 0){
    return (
      <div className="bg-white dark:bg-slate-800 rounded-xl p-6 border border-slate-200 dark:border-slate-700 text-center">
        <div className="text-4xl mb-2">📊</div>
        <p className="text-slate-500 dark:text-slate-400 text-sm">No recent audits yet.</p>
        <p className="text-slate-400 dark:text-slate-500 text-xs mt-1">Start your first audit above!</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {runs.slice(0, 5).map(r => (
        <Link 
          key={r.run_id} 
          href={`/results/${r.run_id}`}
          className="block bg-white dark:bg-slate-800 rounded-xl p-4 border border-slate-200 dark:border-slate-700 hover:border-primary hover:shadow-md transition-all group"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-primary to-accent rounded-full flex items-center justify-center text-white font-bold text-sm">
                @{r.username?.[0]?.toUpperCase()}
              </div>
              <div>
                <div className="font-medium text-slate-900 dark:text-white group-hover:text-primary transition-colors">
                  @{r.username}
                </div>
                <div className="text-xs text-slate-400">
                  {new Date(r.requested_at).toLocaleDateString('en-US', { 
                    month: 'short', 
                    day: 'numeric', 
                    hour: '2-digit', 
                    minute: '2-digit' 
                  })}
                </div>
              </div>
            </div>
            <StatusBadge status={r.status} />
          </div>
        </Link>
      ))}
    </div>
  )
}

function StatusBadge({ status }: { status: string }){
  const statusStyles: Record<string, string> = {
    complete: 'bg-green-500/20 text-green-400',
    failed: 'bg-red-500/20 text-red-400',
    processing: 'bg-blue-500/20 text-blue-400',
    queued: 'bg-slate-500/20 text-slate-400',
  }
  const style = statusStyles[status || 'queued'] || statusStyles.queued
  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${style}`}>
      {status === 'complete' ? 'Done' : status === 'failed' ? 'Failed' : status === 'processing' ? 'Running' : 'Queued'}
    </span>
  )
}