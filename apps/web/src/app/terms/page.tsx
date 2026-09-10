import Link from "next/link";

export default function TermsPage() {
  return (
    <main className="min-h-screen">
      <header className="flex items-center justify-between px-8 py-6 max-w-3xl mx-auto">
        <Link href="/" className="text-xl font-bold tracking-tight">SPY</Link>
      </header>
      <article className="max-w-3xl mx-auto px-6 py-12 prose-invert text-sm text-muted leading-relaxed space-y-6">
        <div className="text-xs bg-yellow-950/40 border border-yellow-900 text-yellow-300 rounded-md p-3">
          Draft placeholder — replace with counsel-reviewed copy before handling real customers in
          production.
        </div>
        <h1 className="text-2xl font-semibold text-white">Terms of Service</h1>
        <p>Last updated: {new Date().toISOString().slice(0, 10)}</p>

        <h2 className="text-white font-semibold">The service</h2>
        <p>
          Spy audits websites you own or are authorized to audit, and reports search-visibility
          findings and estimates derived from our own crawler and analysis — not guarantees of
          search ranking or AI-answer-engine placement.
        </p>

        <h2 className="text-white font-semibold">Free audit</h2>
        <p>
          Each verified account receives one complete audit at no charge. Subsequent audits
          require a paid credit or subscription. The free entitlement is consumed only once an
          audit completes successfully.
        </p>

        <h2 className="text-white font-semibold">Acceptable use</h2>
        <p>
          You may only submit websites you own or are authorized to crawl. Our crawler respects
          robots.txt and will not attempt to access internal or private network addresses.
        </p>

        <h2 className="text-white font-semibold">Payments</h2>
        <p>
          Payments are processed by Razorpay. Prices are shown in INR and are configurable; the
          price displayed at checkout is the price charged.
        </p>

        <h2 className="text-white font-semibold">Limitation of liability</h2>
        <p>
          Spy is provided &quot;as is&quot; without warranty of any kind. We are not liable for indirect or
          consequential damages arising from use of the service.
        </p>

        <h2 className="text-white font-semibold">Contact</h2>
        <p>Questions about these terms can be sent to the address listed on our contact page.</p>
      </article>
    </main>
  );
}
