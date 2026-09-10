"use client";

import { useEffect, useState } from "react";
import Script from "next/script";
import { apiGet, apiPost } from "@/lib/api";
import type { Plan } from "@/lib/api";

interface BillingStatus {
  has_active_subscription: boolean;
  available_credits: number;
}

interface OrderResponse {
  order_id: string;
  amount_minor: number;
  currency: string;
  razorpay_key_id: string;
  purchase_id: string;
}

declare global {
  interface Window {
    Razorpay: new (options: Record<string, unknown>) => { open: () => void };
  }
}

export default function BillingPage() {
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [busyPlan, setBusyPlan] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Plan[]>("billing/plans").then(setPlans).catch(() => setPlans([]));
    apiGet<BillingStatus>("billing/status").then(setStatus).catch(() => {});
  }, []);

  async function purchase(plan: Plan) {
    setBusyPlan(plan.code);
    setMessage(null);
    try {
      const order = await apiPost<OrderResponse>("billing/order", { plan_code: plan.code });

      const rzp = new window.Razorpay({
        key: order.razorpay_key_id,
        amount: order.amount_minor,
        currency: order.currency,
        order_id: order.order_id,
        name: "Spy",
        description: plan.name,
        handler: () => {
          // The webhook (server-side, signature-verified) is the source of
          // truth for granting the credit — this just gives the user quick
          // feedback while that lands.
          setMessage("Payment received — your credit will appear shortly.");
          setTimeout(() => {
            apiGet<BillingStatus>("billing/status").then(setStatus).catch(() => {});
          }, 3000);
        },
        theme: { color: "#5b8def" },
      });
      rzp.open();
    } catch {
      setMessage("Couldn't start checkout. Please try again.");
    } finally {
      setBusyPlan(null);
    }
  }

  return (
    <div className="p-8 max-w-5xl">
      <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="afterInteractive" />

      <h1 className="text-2xl font-semibold">Billing</h1>
      {status && (
        <p className="text-muted mt-1">
          {status.available_credits} audit credit(s) available
          {status.has_active_subscription ? " · active subscription" : ""}
        </p>
      )}

      {message && <div className="mt-4 text-sm text-accent bg-accent/10 border border-accent/30 rounded-md p-3">{message}</div>}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-8">
        {plans === null ? (
          <div className="text-muted text-sm">Loading plans…</div>
        ) : plans.length === 0 ? (
          <div className="text-muted text-sm">No plans available right now.</div>
        ) : (
          plans
            .filter((p) => p.code !== "FREE")
            .map((plan) => (
              <div key={plan.code} className="card p-6 flex flex-col">
                <div className="font-semibold">{plan.name}</div>
                <div className="text-2xl font-bold mt-2">
                  ₹{(plan.price_minor / 100).toLocaleString("en-IN")}
                  <span className="text-sm text-muted font-normal">
                    {plan.billing_interval === "MONTHLY" ? "/mo" : " one-time"}
                  </span>
                </div>
                <ul className="text-sm text-muted mt-4 space-y-1 flex-1">
                  <li>{plan.audit_limit ?? "1"} audit{plan.audit_limit === 1 ? "" : "s"}</li>
                  <li>{plan.crawl_url_limit.toLocaleString()} URLs per audit</li>
                  {plan.project_limit && <li>{plan.project_limit} projects</li>}
                  {plan.member_limit && <li>{plan.member_limit} team member(s)</li>}
                </ul>
                <button
                  onClick={() => purchase(plan)}
                  disabled={busyPlan === plan.code}
                  className="btn-primary mt-6"
                >
                  {busyPlan === plan.code ? "Starting…" : "Buy"}
                </button>
              </div>
            ))
        )}
      </div>
    </div>
  );
}
