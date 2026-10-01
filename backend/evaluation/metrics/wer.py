"""Word error rate (and character error rate) with a fixed, documented normalizer.

Normalizer "lecturemind-wer-normalizer/v1", applied identically to reference and hypothesis:

 1. Unicode NFKC; curly quotes/apostrophes to ASCII; lowercase.
 2. Remove spans in square brackets or parentheses (e.g. "[music]", "(laughs)").
 3. Hyphens, slashes and dashes become spaces ("e-mail" -> "e mail").
 4. Remove all punctuation except apostrophes inside words ("don't" is kept; quotes are not).
 5. Remove the filler words: uh, um, uhm, hmm, mm, mhm, er, erm, ah.
 6. Collapse whitespace.

Deliberately NOT normalized (so references must follow the same convention, stated in the
annotation guideline): numbers vs number words ("10" vs "ten"), contractions vs expansions
("you're" vs "you are"), British vs American spelling. Whisper's own evaluation normalizer
handles these (Radford et al., App. C); WER from this normalizer is therefore not directly
comparable to WER reported with Whisper's normalizer. A new normalizer gets a new version.

WER = (S + D + I) / N over reference words; corpus WER sums edits and reference words over
all documents (not a mean of per-document WERs).
"""

import re
import unicodedata
from dataclasses import asdict, dataclass

NORMALIZER_VERSION = "lecturemind-wer-normalizer/v1"
FILLERS = frozenset({"uh", "um", "uhm", "hmm", "mm", "mhm", "er", "erm", "ah"})

_BRACKETED = re.compile(r"\[[^\]]*\]|\([^)]*\)")
_SEPARATORS = re.compile(r"[-‐‑‒–—―/]")
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "`": "'"})


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_APOSTROPHES).lower()
    text = _BRACKETED.sub(" ", text)
    text = _SEPARATORS.sub(" ", text)
    kept = []
    for char in text:
        category = unicodedata.category(char)
        if char == "'" or not (category.startswith("P") or category.startswith("S")):
            kept.append(char)
        else:
            kept.append(" ")
    words = []
    for word in "".join(kept).split():
        word = word.strip("'")  # quotes, not intra-word apostrophes
        if word and word not in FILLERS:
            words.append(word)
    return " ".join(words)


@dataclass(frozen=True)
class EditCounts:
    substitutions: int
    deletions: int
    insertions: int
    reference_length: int

    @property
    def errors(self) -> int:
        return self.substitutions + self.deletions + self.insertions

    @property
    def rate(self) -> float | None:
        return self.errors / self.reference_length if self.reference_length else None

    def __add__(self, other: "EditCounts") -> "EditCounts":
        return EditCounts(
            self.substitutions + other.substitutions,
            self.deletions + other.deletions,
            self.insertions + other.insertions,
            self.reference_length + other.reference_length,
        )

    def as_dict(self) -> dict:
        return {**asdict(self), "errors": self.errors, "rate": self.rate}


def edit_counts(reference: list, hypothesis: list) -> EditCounts:
    """Minimum edit alignment (Levenshtein) with S/D/I breakdown; ties prefer substitutions."""
    rows, cols = len(reference) + 1, len(hypothesis) + 1
    # cost[i][j] = (total, subs, dels, ins) for reference[:i] vs hypothesis[:j]
    previous = [(j, 0, 0, j) for j in range(cols)]
    for i in range(1, rows):
        current = [(i, 0, i, 0)] + [None] * (cols - 1)
        for j in range(1, cols):
            if reference[i - 1] == hypothesis[j - 1]:
                current[j] = previous[j - 1]
                continue
            sub, dele, ins = previous[j - 1], previous[j], current[j - 1]
            options = [
                (sub[0] + 1, sub[1] + 1, sub[2], sub[3]),
                (dele[0] + 1, dele[1], dele[2] + 1, dele[3]),
                (ins[0] + 1, ins[1], ins[2], ins[3] + 1),
            ]
            current[j] = min(options, key=lambda option: option[0])
        previous = current
    _, subs, dels, ins = previous[-1]
    return EditCounts(subs, dels, ins, len(reference))


def wer(reference: str, hypothesis: str) -> EditCounts:
    return edit_counts(normalize(reference).split(), normalize(hypothesis).split())


def cer(reference: str, hypothesis: str) -> EditCounts:
    """Character error rate over normalized text with spaces removed."""
    return edit_counts(list(normalize(reference).replace(" ", "")), list(normalize(hypothesis).replace(" ", "")))


def corpus(pairs: list[tuple[str, str]]) -> EditCounts:
    total = EditCounts(0, 0, 0, 0)
    for reference, hypothesis in pairs:
        total = total + wer(reference, hypothesis)
    return total
