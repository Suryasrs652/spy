import Link from "next/link";
import { serverApiGet } from "@/lib/serverApi";
import type { Project } from "@/lib/api";

export default async function ProjectsPage() {
  const projects = await serverApiGet<Project[]>("projects");

  return (
    <div className="p-8 max-w-5xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Projects</h1>
        <Link href="/projects/new" className="btn-primary">Add a Project</Link>
      </div>

      {!projects ? (
        <div className="card p-6 mt-6 text-muted text-sm">Couldn't load projects right now.</div>
      ) : projects.length === 0 ? (
        <div className="card p-8 mt-6 text-center">
          <p className="text-muted">No projects yet.</p>
          <Link href="/projects/new" className="btn-primary inline-block mt-4">Add your first website</Link>
        </div>
      ) : (
        <table className="w-full mt-6 text-sm">
          <thead>
            <tr className="text-left text-muted border-b border-border">
              <th className="py-2 font-normal">Name</th>
              <th className="py-2 font-normal">Domain</th>
              <th className="py-2 font-normal">Status</th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.id} className="border-b border-border/50 hover:bg-white/5">
                <td className="py-3">
                  <Link href={`/projects/${p.id}`} className="text-accent">{p.name}</Link>
                </td>
                <td className="py-3 text-muted">{p.domain}</td>
                <td className="py-3 text-muted">{p.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
