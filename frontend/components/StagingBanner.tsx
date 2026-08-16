// Staging deployment audit — a small, non-intrusive notice that this is a
// test environment, not production. Server component: reads the env var
// directly, no client state needed. Renders nothing (not even a hidden
// element) unless NEXT_PUBLIC_STAGING_BANNER is explicitly set — local dev
// and any real production deployment stay silent by default.
export function StagingBanner() {
  if (process.env.NEXT_PUBLIC_STAGING_BANNER !== "true") return null;

  return (
    <div className="border-b border-amber-900 bg-amber-950 px-4 py-1.5 text-center text-xs text-amber-300">
      TEST ENVIRONMENT — some AI/legal-data providers are currently mock or unverified. Do not upload confidential
      production data.
    </div>
  );
}
