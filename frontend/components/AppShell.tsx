import { AuthGuard } from "@/components/AuthGuard";
import { Header } from "@/components/Header";
import { NavSidebar } from "@/components/NavSidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex min-h-screen">
        <NavSidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Header />
          <main className="min-w-0 flex-1 overflow-auto">{children}</main>
        </div>
      </div>
    </AuthGuard>
  );
}
