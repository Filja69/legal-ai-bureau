export function CompaniesView() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold">Companies &amp; Due Diligence</h1>
      <div className="mt-4 max-w-xl rounded border border-slate-800 bg-slate-900/50 p-4 text-sm text-slate-400">
        Company profiles and due diligence reports are not available yet — there is no real data
        provider connected (backend: <code className="text-slate-300">/companies</code> and{" "}
        <code className="text-slate-300">/due-diligence</code> return 501). This page intentionally
        shows nothing rather than fabricated company data. See LEGAL-ROADMAP.md, Phase 5.
      </div>
    </div>
  );
}
