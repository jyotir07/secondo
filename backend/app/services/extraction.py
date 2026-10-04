"""Turns a pasted customer message into structured order lines.

Providers return the same ExtractionResult. Product matching, date resolution and confidence
scoring are deterministic post-processing shared by every provider, so an LLM can never book a
product that is not in the catalogue.
"""

import re
from datetime import date, timedelta
from typing import Protocol

from pydantic import BaseModel, Field

from app.models import Product
from app.services.catalog import ProductCatalog, normalize


class ExtractedItem(BaseModel):
    product_id: str | None
    product_name: str
    mention: str
    quantity: int = Field(gt=0, le=10_000)
    matched: bool


class ExtractionResult(BaseModel):
    items: list[ExtractedItem]
    order_date: date | None
    customer_name: str | None
    dietary_constraints: list[str]
    notes: str | None
    confidence: float
    provider: str
    model: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    original_input: str
    latency_ms: int | None = None


class ExtractionError(RuntimeError):
    pass


class Extractor(Protocol):
    name: str

    def extract(self, text: str, catalog: ProductCatalog, today: date) -> ExtractionResult: ...


NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "fifteen": 15, "twenty": 20, "couple": 2, "pair": 2,
}  # fmt: skip
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = {
    m: i
    for i, names in enumerate(
        [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
         ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
         ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
         ("dec", "december")],
        start=1,
    )
    for m in names
}  # fmt: skip
DIETARY_PATTERNS = {
    "eggless": r"\beggless\b|\bno eggs?\b|\bwithout eggs?\b|\begg[- ]free\b",
    "vegan": r"\bvegan\b",
    "gluten-free": r"\bgluten[- ]?free\b|\bno gluten\b",
    "sugar-free": r"\bsugar[- ]?free\b|\bno sugar\b|\bdiabetic\b",
    "nut-free": r"\bnut[- ]?free\b|\bno nuts?\b|\bnut allergy\b|\ballergic to nuts\b",
    "dairy-free": r"\bdairy[- ]?free\b|\bno dairy\b|\blactose\b",
    "jain": r"\bjain\b",
}
NOTE_HINTS = re.compile(
    r"\b(pick ?up|deliver|delivery|write|message on|candle|less sweet|extra|by \d|"
    r"morning|evening|afternoon|noon|am\b|pm\b|birthday|anniversary|pack|box)",
    re.I,
)
NAME_PATTERNS = [
    re.compile(r"(?:^|\n|[.!?])\s*[-–—~]\s*([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)?)\s*$"),
    re.compile(r"\b(?:this is|i am|i'm|it's)\s+([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)?)"),
    re.compile(
        r"\b(?:thanks|thank you|regards|cheers)[,!.]?\s+([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)?)"
        r"\s*[.!]?\s*$"
    ),
]
_NOT_NAMES = {"Hi", "Hello", "Hey", "Please", "Thanks", "Ma'am", "Sir", "Aunty", "Didi"}


def resolve_date(text: str, today: date) -> date | None:
    """Resolve the delivery date mentioned in a message relative to the business's today."""
    t = text.lower()
    if m := re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t):
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            pass
    if "day after tomorrow" in t:
        return today + timedelta(days=2)
    if re.search(r"\b(tomorrow|tmrw|tmr|kal)\b", t):
        return today + timedelta(days=1)
    if re.search(r"\b(today|tonight|aaj)\b", t):
        return today

    month_names = "|".join(sorted(MONTHS, key=len, reverse=True))
    day_month = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({month_names})\b", t)
    month_day = re.search(rf"\b({month_names})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", t)
    numeric = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
    day = month = year = None
    if day_month:
        day, month = int(day_month[1]), MONTHS[day_month[2]]
    elif month_day:
        day, month = int(month_day[2]), MONTHS[month_day[1]]
    elif numeric:
        day, month = int(numeric[1]), int(numeric[2])
        if numeric[3]:
            year = int(numeric[3]) + (2000 if len(numeric[3]) == 2 else 0)
    if day and month:
        try:
            candidate = date(year or today.year, month, day)
        except ValueError:
            return None
        if year is None and candidate < today:
            candidate = candidate.replace(year=today.year + 1)
        return candidate

    for i, name in enumerate(WEEKDAYS):
        if re.search(rf"\b{name}\b", t):
            ahead = (i - today.weekday()) % 7 or 7
            return today + timedelta(days=ahead)
    return None


def extract_dietary(text: str) -> list[str]:
    t = text.lower()
    return [label for label, pattern in DIETARY_PATTERNS.items() if re.search(pattern, t)]


def extract_customer_name(text: str) -> str | None:
    for pattern in NAME_PATTERNS:
        if m := pattern.search(text.strip()):
            name = m[1].strip()
            if name.split()[0] not in _NOT_NAMES:
                return name
    return None


def extract_notes(text: str) -> str | None:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
    notes = [s for s in sentences if NOTE_HINTS.search(s)]
    return " ".join(notes) if notes else None


def _quantity_before(tokens: list[str]) -> int | None:
    """Read a quantity from the words immediately preceding a product mention."""
    window = tokens[-4:]
    total = None
    # "half a dozen", "2 dozen", "a dozen"
    if window and window[-1] in ("dozen", "dozens"):
        prefix = window[:-1]
        if len(prefix) >= 2 and prefix[-2] == "half" and prefix[-1] in ("a", "an"):
            return 6
        if prefix and prefix[-1] == "half":
            return 6
        mult = 1
        if prefix:
            if prefix[-1].isdigit():
                mult = int(prefix[-1])
            elif prefix[-1] in NUMBER_WORDS:
                mult = NUMBER_WORDS[prefix[-1]]
        return 12 * mult
    for tok in reversed(window):
        if tok in ("of", "x", "nos", "pcs", "pieces", "packs", "boxes", "box", "kg"):
            continue
        if tok.isdigit():
            total = int(tok)
        elif tok in NUMBER_WORDS:
            total = NUMBER_WORDS[tok]
        break
    return total


def _quantity_after(tokens: list[str]) -> int | None:
    """Handles 'croissants x 4' and 'croissants: 4'."""
    window = tokens[:2]
    if len(window) >= 2 and window[0] == "x" and window[1].isdigit():
        return int(window[1])
    if window and re.fullmatch(r"x?\d+", window[0]):
        return int(window[0].lstrip("x"))
    return None


def find_products(text: str, catalog: ProductCatalog) -> list[ExtractedItem]:
    normalized = normalize(text)
    padded = f" {normalized} "
    consumed = [False] * len(padded)
    found: dict[str, ExtractedItem] = {}
    for phrase, product in catalog.phrases_longest_first():
        needle = f" {phrase} "
        start = padded.find(needle)
        while start != -1:
            span = range(start + 1, start + len(needle) - 1)
            if not any(consumed[i] for i in span):
                for i in span:
                    consumed[i] = True
                before = padded[:start].split()
                after = padded[start + len(needle) :].split()
                qty = _quantity_before(before) or _quantity_after(after)
                item = found.get(product.id)
                if item:
                    item.quantity += qty or 1
                else:
                    found[product.id] = ExtractedItem(
                        product_id=product.id,
                        product_name=product.name,
                        mention=phrase,
                        quantity=qty or 1,
                        matched=True,
                    )
                    if qty is None:
                        found[product.id].mention += " (quantity assumed 1)"
            start = padded.find(needle, start + 1)
    return list(found.values())


def score(result: ExtractionResult) -> float:
    """Deterministic confidence; model self-reported confidence is not trusted."""
    if not result.items:
        return 0.0
    s = 0.4
    s += 0.2 * (sum(i.matched for i in result.items) / len(result.items))
    s += 0.2 if result.order_date else 0
    s += 0.2 if not any("assumed" in i.mention for i in result.items) else 0
    return round(min(s, 1.0), 2)


def finalize(result: ExtractionResult, today: date) -> ExtractionResult:
    if not result.items:
        result.warnings.append("No catalogue products recognised. Add the items manually.")
    for item in result.items:
        if not item.matched:
            result.warnings.append(f"'{item.mention}' is not in the catalogue.")
        elif "assumed" in item.mention:
            result.warnings.append(f"No quantity found for {item.product_name}; assumed 1.")
    if result.order_date is None:
        result.warnings.append("No date found in the message. Please pick one.")
    elif result.order_date < today:
        result.warnings.append("The resolved date is in the past. Please check it.")
    result.confidence = score(result)
    return result


class RuleBasedExtractor:
    name = "rules"

    def extract(self, text: str, catalog: ProductCatalog, today: date) -> ExtractionResult:
        result = ExtractionResult(
            items=find_products(text, catalog),
            order_date=resolve_date(text, today),
            customer_name=extract_customer_name(text),
            dietary_constraints=extract_dietary(text),
            notes=extract_notes(text),
            confidence=0,
            provider=self.name,
            original_input=text,
        )
        return finalize(result, today)


def catalogue_prompt(products: list[Product]) -> str:
    return "\n".join(f"- {p.name}" for p in products if p.active)
