import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import EvidenceReader from "./EvidenceReader";

describe("EvidenceReader", () => {
  const text =
    "The platform shall operate at high altitude.\nUnrelated procurement filler sentence.";
  const requirements = [
    { need: "High-altitude operation", evidence: "operate at high altitude" },
    { need: "Unfindable requirement", evidence: "quantum teleportation subsystem" },
  ];

  it("renders the requirements and the grounded count", () => {
    render(<EvidenceReader text={text} requirements={requirements} />);
    expect(screen.getByText("High-altitude operation")).toBeInTheDocument();
    // one of two requirements is located in the text
    expect(screen.getByText(/1\/2 grounded in the text/i)).toBeInTheDocument();
  });

  it("flags requirements with no matching sentence", () => {
    render(<EvidenceReader text={text} requirements={requirements} />);
    expect(screen.getByText(/no matching sentence found/i)).toBeInTheDocument();
  });
});
