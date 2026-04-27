'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import ChatWidget from '../../../components/ChatWidget'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Helper to convert image URL to base64
async function imageToBase64(url: string): Promise<string> {
  try {
    const response = await fetch(url)
    const blob = await response.blob()
    return new Promise((resolve) => {
      const reader = new FileReader()
      reader.onloadend = () => resolve(reader.result as string)
      reader.readAsDataURL(blob)
    })
  } catch {
    return ''
  }
}

export default function RunResults() {
    const params = useParams()
    const run_id = typeof params.run_id === 'string' ? params.run_id : ''
    const [status, setStatus] = useState<any>(null)
  const [results, setResults] = useState<any>(null)
  const [polling, setPolling] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let mounted = true
    async function poll() {
      while (mounted && polling) {
        try {
          const sres = await fetch(`${API_BASE}/audit/${run_id}/status`)
          const s = await sres.json()
          if (!mounted) return
          setStatus(s)
          if (s.status === 'complete') {
            setPolling(false)
            const rres = await fetch(`${API_BASE}/audit/${run_id}/results`)
            const r = await rres.json()
            setResults(r)
            return
          }
          if (s.status === 'failed') {
            setPolling(false)
            setError(s.error?.error || 'Pipeline failed')
            return
          }
        } catch (e) {
          // ignore and retry
        }
        await new Promise(r => setTimeout(r, 2000))
      }
    }
    poll()
    return () => { mounted = false }
  }, [run_id])

  // Loading / Polling Screen
  if (!results && (polling || status?.status !== 'complete')) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-4">
        <div className="max-w-md w-full text-center">
          <Link href="/" className="inline-block mb-8 text-2xl font-bold text-white">InstaConsultant</Link>

          <div className="bg-slate-800/50 backdrop-blur-lg rounded-2xl p-8 border border-slate-700">
            <div className="relative w-24 h-24 mx-auto mb-6">
              <div className="absolute inset-0 border-4 border-slate-700 rounded-full"></div>
              <div className="absolute inset-0 border-4 border-t-primary border-r-transparent border-b-transparent border-l-transparent rounded-full animate-spin"></div>
              <div className="absolute inset-2 flex items-center justify-center">
                <span className="text-2xl font-bold text-primary">{status?.progress_pct || 0}%</span>
              </div>
            </div>

            <h2 className="text-xl font-semibold text-white mb-2">
              {status?.status === 'failed' ? 'Analysis Failed' : 'Analyzing Profile'}
            </h2>
            <p className="text-slate-400 text-sm mb-4 capitalize">{status?.current_stage?.replace(/_/g, ' ') || 'Preparing...'}</p>

            <div className="space-y-2">
              {['Validating', 'Scraping Instagram', 'Scraping Website', 'Processing', 'Analyzing', 'Generating Charts', 'Generating Outreach'].map((stage, i) => {
                const stageKey = stage.toLowerCase().replace(/ /g, '_')
                const isActive = status?.current_stage === stageKey
                const isComplete = status?.progress_pct > (i * 15)
                return (
                  <div key={stage} className={`flex items-center gap-3 text-sm ${isActive ? 'text-primary' : isComplete ? 'text-green-400' : 'text-slate-600'}`}>
                    <span className={`w-2 h-2 rounded-full ${isComplete ? 'bg-green-400' : isActive ? 'bg-primary animate-pulse' : 'bg-slate-700'}`}></span>
                    <span>{stage}</span>
                  </div>
                )
              })}
            </div>
          </div>

          {error && (
            <div className="mt-6 p-4 bg-red-500/20 border border-red-500/50 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}

          <Link href="/" className="mt-6 inline-block text-slate-500 hover:text-primary text-sm">
            ← Back to Home
          </Link>
        </div>
      </div>
    )
  }

  // Results Screen
  const analysis = results?.analysis || {}
  const processed = results?.processed_metrics || {}
  const outreach = results?.outreach || ''
  const report = results?.report || ''
  const charts = results?.charts || []

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      {/* Header */}
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 sticky top-0 z-50 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link href="/" className="text-xl font-bold text-primary flex items-center gap-2">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            InstaConsultant
          </Link>
          <div className="flex items-center gap-4">
            <Link href="/" className="text-slate-500 hover:text-primary text-sm">
              New Audit
            </Link>
            <span className="px-3 py-1 bg-green-500/20 text-green-400 rounded-full text-sm">Complete</span>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8 space-y-8">
        {/* Profile Summary */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div className="md:col-span-1">
            <div className="bg-white dark:bg-slate-800 rounded-xl p-6 shadow-sm border border-slate-200 dark:border-slate-700">
              <div className="w-16 h-16 bg-gradient-to-br from-primary to-accent rounded-full mb-4 flex items-center justify-center">
                <span className="text-2xl font-bold text-white">@{processed.handle?.[0]?.toUpperCase()}</span>
              </div>
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">@{processed.handle}</h2>
              <p className="text-slate-500 mt-1">{processed.followers?.toLocaleString()} followers</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {processed.is_verified && <span className="px-2 py-1 bg-blue-500/20 text-blue-400 rounded text-xs">Verified</span>}
                {processed.is_business && <span className="px-2 py-1 bg-purple-500/20 text-purple-400 rounded text-xs">Business</span>}
              </div>
            </div>
          </div>

          {/* Key Metrics */}
          <div className="md:col-span-3 grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricCard
              label="Engagement Rate"
              value={`${processed.engagement?.clean_engagement_rate_pct || 0}%`}
              subtext={processed.engagement?.benchmark_label || 'Low'}
              color="primary"
            />
            <MetricCard
              label="Follower Tier"
              value={processed.engagement?.follower_tier_label || 'N/A'}
              subtext={processed.engagement?.tier_thresholds ? `${processed.engagement.tier_thresholds.exceptional}%+ for exceptional` : ''}
              color="blue"
            />
            <MetricCard
              label="Best Format"
              value={processed.format_analysis?.best_performing_format || 'N/A'}
              subtext={processed.format_analysis?.format_mix_pct ? `${processed.format_analysis.format_mix_pct[processed.format_analysis.best_performing_format]}% of posts` : ''}
              color="green"
            />
            <MetricCard
              label="Funnel Score"
              value={`${processed.website_audit?.funnel_score || 0}/10`}
              subtext={processed.website_audit?.site_type || 'Unknown site'}
              color="orange"
            />
          </div>
        </div>

        {/* Analysis Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-white dark:bg-slate-800 rounded-xl p-6 shadow-sm border border-slate-200 dark:border-slate-700">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Strategic Analysis</h3>
            <div className="space-y-4">
              <div className="p-4 bg-green-500/10 border border-green-500/20 rounded-lg">
                <p className="text-xs text-green-400 uppercase tracking-wide mb-1">Top Strength</p>
                <p className="text-slate-900 dark:text-white">{analysis.top_strength || 'N/A'}</p>
              </div>
              <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
                <p className="text-xs text-red-400 uppercase tracking-wide mb-1">Top Weakness</p>
                <p className="text-slate-900 dark:text-white">{analysis.top_weakness || 'N/A'}</p>
              </div>
              <div className="p-4 bg-blue-500/10 border border-blue-500/20 rounded-lg">
                <p className="text-xs text-blue-400 uppercase tracking-wide mb-1">Content Theme</p>
                <p className="text-slate-900 dark:text-white capitalize">{(analysis.dominant_theme || '').replace(/_/g, ' ')}</p>
              </div>
            </div>
          </div>

          <div className="bg-white dark:bg-slate-800 rounded-xl p-6 shadow-sm border border-slate-200 dark:border-slate-700">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Summary</h3>
            <p className="text-slate-600 dark:text-slate-300 leading-relaxed">{analysis.summary || 'No summary available.'}</p>

            <div className="mt-6">
              <p className="text-sm font-medium text-slate-500 dark:text-slate-400 mb-2">Missing Themes</p>
              <div className="flex flex-wrap gap-2">
                {(analysis.missing_themes || []).map((theme: string, i: number) => (
                  <span key={i} className="px-3 py-1 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-full text-sm">
                    {(theme || '').replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>

{/* Charts with Base64 - Standardized Size */}
          {charts.length > 0 && (
            <div className="bg-white dark:bg-slate-800 rounded-2xl p-8 shadow-lg border border-slate-200 dark:border-slate-700">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-xl font-bold text-slate-900 dark:text-white">Visualizations</h3>
                <Link 
                  href="/"
                  className="text-sm text-slate-500 hover:text-primary flex items-center gap-1"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                  </svg>
                  Back to Home
                </Link>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                {charts.map((chart: string, i: number) => (
                  <div key={i} className="flex flex-col items-center">
                    <div className="w-full aspect-square max-w-sm bg-white rounded-xl shadow-md overflow-hidden border border-slate-200">
                      <ChartImage chartUrl={chart.startsWith('http') ? chart : `${API_BASE}${chart}`} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

        {/* Outreach */}
        <div className="bg-gradient-to-r from-green-500/10 to-blue-500/10 rounded-xl p-6 border border-green-500/20">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Outreach Message</h3>
            <button 
              onClick={() => navigator.clipboard.writeText(outreach)}
              className="px-4 py-2 bg-green-500 text-white rounded-lg text-sm hover:opacity-90 transition-opacity"
            >
              Copy to Clipboard
            </button>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-lg p-4 border border-slate-200 dark:border-slate-700">
            <pre className="whitespace-pre-wrap text-slate-700 dark:text-slate-300 font-sans">{outreach || 'No outreach generated'}</pre>
          </div>
        </div>

        {/* Report - Clean Version for End Users */}
        {report && (
          <div className="bg-white dark:bg-slate-800 rounded-xl p-6 shadow-sm border border-slate-200 dark:border-slate-700">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Audit Report</h3>
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <pre className="whitespace-pre-wrap text-sm text-slate-600 dark:text-slate-400 font-sans bg-transparent border-0 p-0 max-h-none overflow-visible">
                {report.split('CHARTS GENERATED:')[0].trim()}
              </pre>
            </div>
            <div className="mt-4 flex gap-3">
              <button 
                onClick={() => navigator.clipboard.writeText(report.split('CHARTS GENERATED:')[0].trim())}
                className="px-4 py-2 bg-primary text-white rounded-lg text-sm hover:opacity-90 transition-opacity"
              >
                Copy Report
              </button>
            </div>
          </div>
        )}

        {/* Chat Widget */}
        <ChatWidget runId={run_id} />
      </main>
    </div>
  )
}

function ChartImage({ chartUrl }: { chartUrl: string }) {
  const [base64, setBase64] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    async function loadImage() {
      try {
        const response = await fetch(chartUrl)
        const blob = await response.blob()
        const reader = new FileReader()
        reader.onloadend = () => {
          setBase64(reader.result as string)
          setLoading(false)
        }
        reader.onerror = () => {
          setError(true)
          setLoading(false)
        }
        reader.readAsDataURL(blob)
      } catch {
        setError(true)
        setLoading(false)
      }
    }
    loadImage()
  }, [chartUrl])

  if (error) {
    return (
      <div className="w-full aspect-square bg-slate-100 dark:bg-slate-700 rounded-lg flex items-center justify-center p-4">
        <span className="text-slate-400 text-sm">Chart unavailable</span>
      </div>
    )
  }

  return (
    <div className="w-full aspect-square relative">
      {loading ? (
        <div className="w-full h-full bg-slate-100 dark:bg-slate-700 rounded-lg flex items-center justify-center">
          <div className="animate-spin w-8 h-8 border-3 border-primary border-t-transparent rounded-full"></div>
        </div>
      ) : (
        <img
          src={base64}
          alt="Chart"
          className="w-full h-full object-contain bg-white"
        />
      )}
    </div>
  )
}

function MetricCard({ label, value, subtext, color }: { label: string, value: string, subtext: string, color: string }) {
  const colorClasses: Record<string, string> = {
    primary: 'text-primary bg-primary/10',
    blue: 'text-blue-500 bg-blue-500/10',
    green: 'text-green-500 bg-green-500/10',
    orange: 'text-orange-500 bg-orange-500/10',
  }
  return (
    <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm border border-slate-200 dark:border-slate-700">
      <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">{label}</p>
      <p className={`text-2xl font-bold ${colorClasses[color]?.split(' ')[0] || 'text-slate-900 dark:text-white'}`}>{value}</p>
      {subtext && <p className="text-xs text-slate-500 mt-1">{subtext}</p>}
    </div>
  )
}