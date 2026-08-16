import { AppShell } from "@/components/AppShell";
import { ContractDetailView } from "@/features/contracts/ContractDetailView";

export default function ContractDetailPage({ params }: { params: { id: string } }) {
  return (
    <AppShell>
      <ContractDetailView contractId={params.id} />
    </AppShell>
  );
}
