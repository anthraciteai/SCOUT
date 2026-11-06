import { describe, expect, it } from "vitest";
import {
  buildEvidenceModel,
  colorForReq,
  EVIDENCE_PALETTE,
  rgba,
  splitSegments,
  tokenize,
} from "./evidence";

describe("tokenize", () => {
  it("lowercases, keeps 3+ char words, drops stopwords", () => {
    expect(tokenize("The system SHALL track Targets")).toEqual(["track", "targets"]);
  });
  it("returns [] for empty / punctuation", () => {
    expect(tokenize("")).toEqual([]);
    expect(tokenize("... !!")).toEqual([]);
  });
});

describe("splitSegments", () => {
  it("reconstructs the exact original text", () => {
    const text = "Line one is here.\nLine two! Is it?\nTrailing no-terminator";
    expect(splitSegments(text).join("")).toBe(text);
  });
  it("breaks after sentence terminators and newlines", () => {
    const segs = splitSegments("A. B?\nC");
    expect(segs.join("")).toBe("A. B?\nC");
    expect(segs.length).toBeGreaterThan(1);
  });
});

describe("buildEvidenceModel", () => {
  const text =
    "The platform shall operate at high altitude.\n" +
    "It must track multiple moving targets.\n" +
    "Totally unrelated filler about procurement paperwork.";
  const requirements = [
    { evidence: "operate at high altitude" },
    { evidence: "track multiple moving targets" },
    { evidence: "quantum teleportation subsystem" }, // not in text
  ];

  const model = buildEvidenceModel(text, requirements);

  it("concatenates segments back to the source text", () => {
    expect(model.segments.map((s) => s.text).join("")).toBe(text);
  });

  it("links each requirement to the segment it came from", () => {
    const seg0 = model.segmentByReq[0][0];
    const seg1 = model.segmentByReq[1][0];
    expect(model.segments[seg0].text).toContain("high altitude");
    expect(model.segments[seg0].reqs).toContain(0);
    expect(model.segments[seg1].text).toContain("moving targets");
    expect(model.segments[seg1].reqs).toContain(1);
  });

  it("is bidirectional: a req's segment lists that req back", () => {
    model.segmentByReq.forEach((segs, ri) => {
      for (const si of segs) expect(model.segments[si].reqs).toContain(ri);
    });
  });

  it("does not locate requirements with no overlap", () => {
    expect(model.segmentByReq[2]).toEqual([]);
    expect(model.locatedCount).toBe(2);
  });

  it("leaves unrelated segments unhighlighted", () => {
    const filler = model.segments.find((s) => s.text.includes("procurement"));
    expect(filler?.reqs).toEqual([]);
  });

  it("ignores requirements without evidence", () => {
    const m = buildEvidenceModel("some text about drones", [{ evidence: "" }, {}]);
    expect(m.locatedCount).toBe(0);
  });
});

describe("palette helpers", () => {
  it("cycles colors and converts to rgba", () => {
    expect(colorForReq(0)).toBe(EVIDENCE_PALETTE[0]);
    expect(colorForReq(EVIDENCE_PALETTE.length)).toBe(EVIDENCE_PALETTE[0]);
    expect(rgba("#ff7a1a", 0.2)).toBe("rgba(255, 122, 26, 0.2)");
  });
});
