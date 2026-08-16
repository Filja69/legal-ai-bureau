import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DocumentStatusBadge } from "./DocumentStatusBadge";
import type { DocumentStatus } from "@/types/document";

describe("DocumentStatusBadge", () => {
  const cases: [DocumentStatus, string][] = [
    ["uploaded", "UPLOADED"],
    ["processing", "PROCESSING"],
    ["ready", "READY"],
    ["failed", "FAILED"],
    ["ocr_required", "OCR REQUIRED"],
    ["unsupported", "UNSUPPORTED"],
  ];

  it.each(cases)("labels %s as %s", (status, label) => {
    render(<DocumentStatusBadge status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("never labels ocr_required as failed — they are distinct, honest states", () => {
    render(<DocumentStatusBadge status="ocr_required" />);
    expect(screen.queryByText("FAILED")).not.toBeInTheDocument();
  });
});
