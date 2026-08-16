import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("labels mock status as MOCK, never VERIFIED", () => {
    render(<StatusBadge status="mock" />);
    expect(screen.getByText("MOCK")).toBeInTheDocument();
    expect(screen.queryByText("VERIFIED")).not.toBeInTheDocument();
  });

  it("labels verified status as VERIFIED", () => {
    render(<StatusBadge status="verified" />);
    expect(screen.getByText("VERIFIED")).toBeInTheDocument();
  });

  it("falls back to the raw uppercased status for unknown values instead of hiding it", () => {
    render(<StatusBadge status="something_new" />);
    expect(screen.getByText("SOMETHING_NEW")).toBeInTheDocument();
  });

  it("is case-insensitive on the input status", () => {
    render(<StatusBadge status="UNVERIFIED" />);
    expect(screen.getByText("UNVERIFIED")).toBeInTheDocument();
  });
});
