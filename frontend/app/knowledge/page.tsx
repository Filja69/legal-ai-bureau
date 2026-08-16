import { AppShell } from "@/components/AppShell";
import { KnowledgeOverviewView } from "@/features/knowledge/KnowledgeOverviewView";

export default function KnowledgePage() {
  return (
    <AppShell>
      <KnowledgeOverviewView />
    </AppShell>
  );
}
