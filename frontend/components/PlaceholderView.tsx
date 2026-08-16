export function PlaceholderView({ title, phase }: { title: string; phase: string }) {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-2 text-sm text-slate-400">
        This product surface is scaffolded but not yet implemented — see LEGAL-ROADMAP.md, {phase}.
      </p>
    </div>
  );
}
