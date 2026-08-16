import { AppShell } from "@/components/AppShell";
import { DocumentDetailView } from "@/features/documents/DocumentDetailView";

export default function DocumentDetailPage({ params }: { params: { id: string } }) {
  return (
    <AppShell>
      <DocumentDetailView documentId={params.id} />
    </AppShell>
  );
}
