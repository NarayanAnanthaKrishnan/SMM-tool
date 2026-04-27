import Link from 'next/link'
import SearchCard from '../components/SearchCard'
import RecentRuns from '../components/RecentRuns'

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Animated background elements */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 -left-20 w-72 h-72 bg-primary/20 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute bottom-1/4 -right-20 w-96 h-96 bg-accent/10 rounded-full blur-3xl animate-pulse" style={{animationDelay: '1s'}}></div>
      </div>

      <header className="relative z-10 container mx-auto px-4 py-6 flex items-center justify-between">
        <Link href="/" className="text-2xl font-bold text-white">
          <span className="text-primary">Insta</span>Consultant
        </Link>
        <nav className="flex items-center gap-6">
          <Link href="#" className="text-slate-400 hover:text-white transition-colors text-sm">
            Documentation
          </Link>
          <Link href="#" className="text-slate-400 hover:text-white transition-colors text-sm">
            Features
          </Link>
        </nav>
      </header>

      <main className="relative z-10 container mx-auto px-4 py-12">
        <div className="max-w-2xl mx-auto text-center mb-12">
          <div className="inline-flex items-center gap-2 px-4 py-2 bg-primary/20 rounded-full text-primary text-sm font-medium mb-6">
            <span className="w-2 h-2 bg-primary rounded-full animate-pulse"></span>
            AI-Powered Instagram Audits
          </div>
          <h1 className="text-4xl md:text-5xl font-bold text-white mb-4 leading-tight">
            Discover Your Instagram
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-accent"> Growth Strategy</span>
          </h1>
          <p className="text-lg text-slate-400 mb-8">
            Get actionable insights, engagement benchmarks, content analysis, 
            and personalized outreach messages — all powered by AI.
          </p>
        </div>

        <div className="mb-16">
          <SearchCard />
        </div>

        {/* Features */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl mx-auto">
          {[
            { emoji: '📊', title: 'Engagement Analysis', desc: 'Clean engagement rates, tier benchmarks, and actionable insights' },
            { emoji: '📈', title: 'Content Strategy', desc: 'Format mix, posting cadence, and content theme analysis' },
            { emoji: '💬', title: 'Outreach Generator', desc: 'AI-crafted DM and email templates ready to send' },
          ].map((f, i) => (
            <div key={i} className="p-6 bg-slate-800/50 backdrop-blur rounded-xl border border-slate-700">
              <div className="text-3xl mb-3">{f.emoji}</div>
              <h3 className="text-white font-semibold mb-2">{f.title}</h3>
              <p className="text-slate-400 text-sm">{f.desc}</p>
            </div>
          ))}
        </div>

        {/* Recent Runs */}
        <div className="mt-16 max-w-md mx-auto">
          <h3 className="text-lg font-medium text-white mb-4 text-center">Recently Analyzed</h3>
          <RecentRuns />
        </div>
      </main>

      <footer className="relative z-10 border-t border-slate-800 mt-16">
        <div className="container mx-auto px-4 py-8 text-center text-slate-500 text-sm">
          <p>© 2026 InstaConsultant. Built with AI for Social Media Managers.</p>
        </div>
      </footer>
    </div>
  )
}