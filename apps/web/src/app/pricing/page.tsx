import Link from "next/link";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://api:8000";

interface Plan {
  code: string; name: string; price_minor: number; currency: string;
  billing_interval: string; audit_limit: number | null; crawl_url_limit: number;
  project_limit: number | null; member_limit: number | null;
}

async function getPlans(): Promise<Plan[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/billing/plans`, { next: { revalidate: 60 } });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export default async function PricingPage() {
  const plans = await getPlans();

  return (
    <main className="min-h-screen">
      <header className="flex items-center justify-between px-8 py-6 max-w-6xl mx-auto">
        <Link href="/" className="text-xl font-bold tracking-tight">SPY</Link>
        <Link href="/signup" className="btn-primary text-sm">Sign up free</Link>
      </header>

      <section className="max-w-5xl mx-auto px-6 py-16">
        <h1 className="text-4xl font-bold text-center">Simple, transparent pricing</h1>
        <p className="text-muted text-center mt-3">Your first complete audit is always free.</p>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mt-12">
          <div className="card p-6">
            <div className="font-semibold">Free</div>
            <div className="text-2xl font-bold mt-2">₹0</div>
            <ul className="text-sm text-muted mt-4 space-y-1">
              <li>1 lifetime audit</li>
              <li>500 URL crawl</li>
              <li>SEO + AEO + GEO</li>
              <li>PDF export</li>
            </ul>
          </div>
          {plans.filter((p) => p.code !== "FREE").map((plan) => (
            <div key={plan.code} className="card p-6">
              <div className="font-semibold">{plan.name}</div>
              <div className="text-2xl font-bold mt-2">
                ₹{(plan.price_minor / 100).toLocaleString("en-IN")}
                <span className="text-sm text-muted font-normal">
                  {plan.billing_interval === "MONTHLY" ? "/mo" : ""}
                </span>
              </div>
              <ul className="text-sm text-muted mt-4 space-y-1">
                <li>{plan.audit_limit ?? 1} audit(s)</li>
                <li>{plan.crawl_url_limit.toLocaleString()} URLs/audit</li>
                {plan.project_limit && <li>{plan.project_limit} projects</li>}
                {plan.member_limit && <li>{plan.member_limit} team member(s)</li>}
              </ul>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
