import { ru } from "@/lib/copy";

// Staging deployment audit — a small, non-intrusive notice that this is a
// test environment, not production. Server component: reads the env var
// directly, no client state needed. Renders nothing (not even a hidden
// element) unless NEXT_PUBLIC_STAGING_BANNER is explicitly set — local dev
// and any real production deployment stay silent by default.
//
// UX iteration: RU wording (was EN), and `text-balance` + horizontal
// padding that scales down on narrow viewports so the banner wraps to two
// lines on mobile instead of forcing a min-width that could cause overflow.
export function StagingBanner() {
  if (process.env.NEXT_PUBLIC_STAGING_BANNER !== "true") return null;

  return (
    <div className="border-b border-amber-900 bg-amber-950 px-3 py-1.5 text-center text-[11px] leading-snug text-amber-300 sm:px-4 sm:text-xs">
      {ru.staging.banner}
    </div>
  );
}
