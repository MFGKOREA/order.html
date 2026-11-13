"""Last check before anything reaches Pickle: masks 신우님's personal information. Stdlib only.

Patterns catch phone numbers, e-mail addresses, resident registration numbers, card and bank
account numbers, and apartment unit addresses (101동 1203호). Anything else private (a home
address, a family member's name) goes in a local terms file, one per line, which is re-read
whenever it changes and is never committed (it lives in downloads/, which git ignores).
"""
import re
from pathlib import Path

MASK = "[가림]"
# (kind, pattern, minimum digit count for a match to count)
PATTERNS = (
    ("주민번호", re.compile(r"(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)"), 0),
    ("카드번호", re.compile(r"(?<!\d)\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}(?!\d)"), 0),
    ("전화번호", re.compile(r"(?<!\d)0\d{1,2}[-. ]?\d{3,4}[-. ]?\d{4}(?!\d)"), 0),
    ("이메일", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), 0),
    ("계좌번호", re.compile(r"(?<!\d)\d{2,6}-\d{2,6}-\d{2,7}(?!\d)"), 10),  # 10+ digits: dates stay
    ("집 주소", re.compile(r"\d{1,4}동\s?\d{1,4}호"), 0),
)


class Filter:
    def __init__(self, terms_path=None):
        self.terms_path = Path(terms_path) if terms_path else None
        self._terms, self._stamp = (), None

    def terms(self):
        """Private words from the terms file (lines starting with # are comments)."""
        if not self.terms_path:
            return ()
        try:
            st = self.terms_path.stat()
        except FileNotFoundError:
            return ()
        if (st.st_mtime_ns, st.st_size) != self._stamp:
            lines = self.terms_path.read_text(encoding="utf-8-sig").splitlines()
            words = {line.strip() for line in lines if line.strip() and not line.strip().startswith("#")}
            self._terms = tuple(sorted(words, key=len, reverse=True))
            self._stamp = (st.st_mtime_ns, st.st_size)
        return self._terms

    def scrub(self, text):
        """(text with personal data replaced by [가림], [kinds that were found])."""
        hits = []
        for kind, pattern, min_digits in PATTERNS:
            def mask(m, kind=kind, min_digits=min_digits):
                if min_digits and sum(c.isdigit() for c in m.group()) < min_digits:
                    return m.group()
                hits.append(kind)
                return MASK
            text = pattern.sub(mask, text)
        for term in self.terms():
            if term in text:
                hits.append("개인 단어")
                text = text.replace(term, MASK)
        return text, hits
