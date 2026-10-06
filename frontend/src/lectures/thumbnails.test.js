import { describe, expect, it } from "vitest";
import { coverInitials, coverStyle, thumbnailUrl, youtubeId } from "./thumbnails";

describe("youtubeId", () => {
  it("reads the video id from the common YouTube URL shapes", () => {
    expect(youtubeId("https://www.youtube.com/watch?v=jGwO_UgTS7I&t=30")).toBe("jGwO_UgTS7I");
    expect(youtubeId("https://youtu.be/jGwO_UgTS7I")).toBe("jGwO_UgTS7I");
    expect(youtubeId("https://m.youtube.com/watch?v=jGwO_UgTS7I")).toBe("jGwO_UgTS7I");
    expect(youtubeId("https://www.youtube.com/embed/jGwO_UgTS7I")).toBe("jGwO_UgTS7I");
    expect(youtubeId("https://www.youtube.com/shorts/jGwO_UgTS7I")).toBe("jGwO_UgTS7I");
  });

  it("rejects other hosts and malformed ids", () => {
    expect(youtubeId("https://vimeo.com/12345")).toBeNull();
    expect(youtubeId("https://www.youtube.com/watch?v=bad")).toBeNull();
    expect(youtubeId("not a url")).toBeNull();
    expect(youtubeId(null)).toBeNull();
  });
});

describe("thumbnailUrl", () => {
  it("uses YouTube's public thumbnail only for YouTube lectures", () => {
    expect(thumbnailUrl({ source_type: "url", source_url: "https://youtu.be/jGwO_UgTS7I" })).toBe(
      "https://i.ytimg.com/vi/jGwO_UgTS7I/mqdefault.jpg",
    );
    expect(thumbnailUrl({ source_type: "video", source_url: null })).toBeNull();
  });
});

describe("generated covers", () => {
  it("are stable per subject and show initials", () => {
    expect(coverStyle("Physics")).toEqual(coverStyle("Physics"));
    expect(coverInitials({ subject: "Machine Learning" })).toBe("ML");
    expect(coverInitials({ subject: "Physics" })).toBe("PH");
    expect(coverInitials({ title: "" })).toBe("");
  });
});
