import Link from "next/link";

export default function PrivacyPage() {
  return (
    <main className="min-h-screen">
      <header className="flex items-center justify-between px-8 py-6 max-w-3xl mx-auto">
        <Link href="/" className="text-xl font-bold tracking-tight">SPY</Link>
      </header>
      <article className="max-w-3xl mx-auto px-6 py-12 prose-invert text-sm text-muted leading-relaxed space-y-6">
        <div className="text-xs bg-yellow-950/40 border border-yellow-900 text-yellow-300 rounded-md p-3">
          Draft placeholder — replace with counsel-reviewed copy before handling real user data in
          production.
        </div>
        <h1 className="text-2xl font-semibold text-white">Privacy Policy</h1>
        <p>Last updated: {new Date().toISOString().slice(0, 10)}</p>

        <h2 className="text-white font-semibold">What we collect</h2>
        <p>
          Account details you provide (email, password hash), website URLs you submit for
          auditing, crawl data from those websites, and usage data needed to operate the service.
        </p>

        <h2 className="text-white font-semibold">How we use it</h2>
        <p>
          To run audits you request, to enforce the one-free-audit entitlement, to process
          payments via Razorpay, and to improve the product. We do not sell your data.
        </p>

        <h2 className="text-white font-semibold">Third parties</h2>
        <p>
          Razorpay (payments), Google (Search Console integration, if you connect it), and our
          infrastructure providers process data on our behalf under their own terms.
        </p>

        <h2 className="text-white font-semibold">Data retention</h2>
        <p>
          Free-tier audit data is retained for 30 days; paid-tier retention follows your plan.
          You can request deletion of your account and associated data at any time.
        </p>

        <h2 className="text-white font-semibold">Your rights</h2>
        <p>
          You may request access to, correction of, or deletion of your personal data by
          contacting us.
        </p>

        <h2 className="text-white font-semibold">Contact</h2>
        <p>Questions about this policy can be sent to the address listed on our contact page.</p>
      </article>
    </main>
  );
}
