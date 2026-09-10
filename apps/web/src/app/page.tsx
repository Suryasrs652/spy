import Link from "next/link";

export default function LandingPage() {
  return (
    <main className="min-h-screen">
      <header className="flex items-center justify-between px-8 py-6 max-w-6xl mx-auto">
        <div className="text-xl font-bold tracking-tight">SPY</div>
        <nav className="flex items-center gap-6 text-sm text-muted">
          <Link href="/pricing" className="hover:text-white">Pricing</Link>
          <Link href="/login" className="hover:text-white">Log in</Link>
          <Link href="/signup" className="btn-primary text-sm">Sign up free</Link>
        </nav>
      </header>

      <section className="max-w-4xl mx-auto text-center px-6 py-24">
        <h1 className="text-5xl font-bold tracking-tight leading-tight">
          One platform to see what search engines,
          <br />
          users and AI systems see in your website.
        </h1>
        <p className="mt-6 text-lg text-muted max-w-2xl mx-auto">
          Spy crawls your site, audits SEO, AEO and GEO readiness, and turns the findings into a
          prioritized plan — no credit card required for your first audit.
        </p>
        <div className="mt-10 flex items-center justify-center gap-4">
          <Link href="/signup" className="btn-primary text-base px-8 py-3">
            Audit My Website Free
          </Link>
          <Link href="#how-it-works" className="btn-secondary text-base px-8 py-3">
            See How Spy Works
          </Link>
        </div>
      </section>

      <section id="how-it-works" className="max-w-5xl mx-auto px-6 py-16 grid grid-cols-1 md:grid-cols-4 gap-6">
        {[
          { title: "Crawl", desc: "A real crawler visits every page, respecting robots.txt." },
          { title: "Analyze", desc: "100+ deterministic checks across SEO, AEO and GEO." },
          { title: "Score", desc: "One reproducible Spy Score, with full evidence behind it." },
          { title: "Act", desc: "A prioritized, effort-ranked plan — not just a list of problems." },
        ].map((step) => (
          <div key={step.title} className="card p-6">
            <div className="text-accent font-semibold mb-2">{step.title}</div>
            <div className="text-sm text-muted">{step.desc}</div>
          </div>
        ))}
      </section>

      <section className="max-w-3xl mx-auto px-6 py-16 text-center">
        <div className="card p-10">
          <h2 className="text-2xl font-semibold">Your free audit is complete.</h2>
          <p className="mt-3 text-muted">
            Fix the issues. Then run another Spy audit to measure exactly what improved.
          </p>
        </div>
      </section>

      <footer className="max-w-6xl mx-auto px-6 py-10 text-xs text-muted flex justify-between border-t border-border">
        <div>© {new Date().getFullYear()} Spy. All rights reserved.</div>
        <div className="flex gap-4">
          <Link href="/privacy">Privacy</Link>
          <Link href="/terms">Terms</Link>
        </div>
      </footer>
    </main>
  );
}
