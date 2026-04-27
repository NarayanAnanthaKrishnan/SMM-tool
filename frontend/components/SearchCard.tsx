'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function SearchCard(){
  const [username, setUsername] = useState('')
  const [context, setContext] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const router = useRouter()

  async function startAudit(){
    if(!username.trim()) return
    setLoading(true)
    setError(null)
    try{
      const res = await fetch(`${API_BASE}/audit`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username: username.trim(), user_context: context.trim()})
      })
      const data = await res.json()
      if(res.ok){
        router.push(`/results/${data.run_id}`)
      }else{
        setError(data.detail || 'Failed to start audit')
      }
    }catch(e){
      setError(String(e))
    }finally{setLoading(false)}
  }

  return (
    <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-lg border border-slate-200 dark:border-slate-700 p-6 md:p-8">
      <div className="space-y-5">
        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
            Instagram Username
          </label>
          <div className="relative">
            <span className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">@</span>
            <input 
              value={username} 
              onChange={e=>setUsername(e.target.value)} 
              placeholder="username"
              className="w-full pl-8 pr-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-primary focus:border-primary transition-all"
              onKeyDown={e => e.key === 'Enter' && !loading && startAudit()}
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
            Optional Context <span className="text-slate-400">(what's this audit for?)</span>
          </label>
          <input 
            value={context} 
            onChange={e=>setContext(e.target.value)} 
            placeholder="e.g., competitor analysis, potential partner, pitch for services..."
            className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-primary focus:border-primary transition-all"
          />
        </div>

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
            {error}
          </div>
        )}

        <div className="flex flex-col sm:flex-row gap-3 pt-2">
          <button 
            onClick={startAudit} 
            disabled={loading || !username.trim()}
            className="flex-1 px-6 py-3 bg-gradient-to-r from-primary to-primary/80 text-white font-semibold rounded-xl hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
          >
            {loading && (
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            )}
            {loading ? 'Starting Audit...' : 'Start Audit'}
          </button>
          <button 
            onClick={()=>{setUsername(''); setContext(''); setError(null)}} 
            className="px-6 py-3 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-700 transition-all"
          >
            Clear
          </button>
        </div>

        <p className="text-xs text-slate-400 text-center">
          By starting an audit, you agree to our terms. Data is processed securely.
        </p>
      </div>
    </div>
  )
}