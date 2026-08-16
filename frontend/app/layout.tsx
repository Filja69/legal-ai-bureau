import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { StagingBanner } from "@/components/StagingBanner";

export const metadata: Metadata = {
  title: "Legal AI Bureau",
  description: "Legal Research & Contract Intelligence Workbench",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body className="min-h-screen bg-slate-950 text-slate-100">
        <StagingBanner />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
