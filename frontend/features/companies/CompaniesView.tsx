export function CompaniesView() {
  return (
    <div className="p-4 sm:p-8">
      <h1 className="text-2xl font-semibold">Компании и Due Diligence</h1>
      <div className="mt-4 max-w-xl rounded border border-slate-800 bg-slate-900/50 p-4 text-sm text-slate-400">
        Профили компаний и отчёты due diligence пока недоступны — не подключён реальный источник данных
        (backend: <code className="text-slate-300">/companies</code> и{" "}
        <code className="text-slate-300">/due-diligence</code> возвращают 501). Эта страница намеренно
        ничего не показывает, вместо того чтобы придумывать данные о компаниях. См. LEGAL-ROADMAP.md, Phase 5.
      </div>
    </div>
  );
}
