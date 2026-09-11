import { redirect } from "next/navigation";

// Self-hosted and single-user: there's nobody to market to and nothing to
// sign up for, so the root is just the way into the tool.
export default function Home() {
  redirect("/dashboard");
}
