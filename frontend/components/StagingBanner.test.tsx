import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { StagingBanner } from "./StagingBanner";

describe("StagingBanner", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("renders nothing when NEXT_PUBLIC_STAGING_BANNER is unset (local dev, production)", () => {
    vi.stubEnv("NEXT_PUBLIC_STAGING_BANNER", "");
    const { container } = render(<StagingBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the honest test-environment notice when explicitly enabled", () => {
    vi.stubEnv("NEXT_PUBLIC_STAGING_BANNER", "true");
    render(<StagingBanner />);
    expect(screen.getByText(/ТЕСТОВАЯ СРЕДА/)).toBeInTheDocument();
    expect(screen.getByText(/Не загружайте конфиденциальные данные/)).toBeInTheDocument();
  });
});
