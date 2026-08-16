import { AppShell } from "@/components/AppShell";
import { SettingsProfileView } from "@/features/settings/SettingsProfileView";

export default function SettingsPage() {
  return (
    <AppShell>
      <SettingsProfileView />
    </AppShell>
  );
}
