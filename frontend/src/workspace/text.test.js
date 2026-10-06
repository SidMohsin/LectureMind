import { describe, expect, it } from "vitest";
import { readableParagraphs, tidyTranscript } from "./text";

describe("tidyTranscript", () => {
  it("drops filler words and false starts for display", () => {
    expect(tidyTranscript("uh, it- it works, um, really well")).toBe("It works, really well");
    expect(tidyTranscript("So I- I think, uh, the rate matters.")).toBe("So I think, the rate matters.");
  });

  it("leaves words that only contain filler letters alone", () => {
    expect(tidyTranscript("the umbrella and the human")).toBe("The umbrella and the human");
  });
});

describe("readableParagraphs", () => {
  it("keeps the model's own paragraph breaks", () => {
    expect(readableParagraphs("First part.\n\nSecond part.")).toEqual(["First part.", "Second part."]);
  });

  it("splits one long paragraph into groups of three sentences", () => {
    const sentence = "This sentence is long enough to make the summary a wall of text for a reader.";
    const paragraphs = readableParagraphs(Array.from({ length: 7 }, () => sentence).join(" "));
    expect(paragraphs).toHaveLength(3);
    expect(paragraphs[0].split(". ")).toHaveLength(3);
  });

  it("leaves a short summary as it is", () => {
    expect(readableParagraphs("Short. Summary.")).toEqual(["Short. Summary."]);
  });
});
