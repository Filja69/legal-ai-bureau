import { AppShell } from "@/components/AppShell";
import { ResearchDetailView } from "@/features/research/ResearchDetailView";

export default function ResearchDetailPage({ params }: { params: { id: string } }) {
  return (
    <AppShell>
      <ResearchDetailView reportId={params.id} />
    </AppShell>
  );
}
