import regex

PATTERN = regex.compile(
    r"(?<![\w.+-])[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9-]|\.[A-Za-z0-9-])"
    r"|(?<!\d)\d{3}[- ]?\d{2}[- ]?\d{4}(?!\d)"
    r"|(?<!\d)\d(?:[ -]?\d){12,18}(?![ -]?\d)"
)

class StreamRedactor:
    def __init__(self):
        self.pending = ""

    def feed(self, text: str, final: bool = False) -> str:
        self.pending += text
        parts = []

        while self.pending:
            match = PATTERN.search(self.pending, partial=True)

            if match is None:
                parts.append(self.pending)
                self.pending = ""
                break

            if match.partial:
                if final:
                    parts.append(self.pending)
                    self.pending = ""
                else:
                    parts.append(self.pending[:match.start()])
                    self.pending = self.pending[match.start():]
                break

            if not final and not self.pending[match.end():].strip(" .-"):
                parts.append(self.pending[:match.start()])
                self.pending = self.pending[match.start():]
                break

            parts.extend((self.pending[:match.start()], "[REDACTED]"))
            self.pending = self.pending[match.end():]

        if len(self.pending) > 320:
            parts.append("[REDACTED]")
            self.pending = ""

        return "".join(parts)

    def finish(self) -> str:
        return self.feed("", final=True)
