from __future__ import annotations


from dataclasses import dataclass


@dataclass(slots=True)
class Chapter:
    number: int
    title: str
    body: str
    raw_heading: str = ""

    @property
    def heading(self) -> str:
        return f"第{self.number}章 {self.title}".strip()

    @property
    def word_count(self) -> int:
        return len(self.body.replace("\n", "").strip())

    def to_text(self) -> str:
        return f"{self.heading}\n\n{self.body.strip()}\n"

    def to_preview(self) -> dict[str, object]:
        return {"number": self.number, "title": self.heading, "subtitle": self.title, "body": self.body}


