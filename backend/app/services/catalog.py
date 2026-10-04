import difflib
import re

from app.models import Product

_NON_WORD = re.compile(r"[^a-z0-9 ]+")


def normalize(text: str) -> str:
    return " ".join(_NON_WORD.sub(" ", text.lower()).split())


def _variants(phrase: str) -> set[str]:
    base = normalize(phrase)
    if not base:
        return set()
    out = {base}
    if base.endswith("s"):
        out.add(base[:-1])
    else:
        out.add(base + "s")
    return out


class ProductCatalog:
    """Maps free-text product mentions to catalogue products.

    Exact matching only (after normalisation and simple plural handling). Fuzzy matches are
    offered as suggestions, never applied silently, so a typo cannot book the wrong product.
    """

    def __init__(self, products: list[Product]):
        self.products = [p for p in products if p.active]
        self.by_id = {p.id: p for p in products}
        self.phrases: dict[str, Product] = {}
        for p in self.products:
            for phrase in [p.name, *p.aliases]:
                for v in _variants(phrase):
                    self.phrases.setdefault(v, p)

    def match(self, text: str) -> Product | None:
        if text in self.by_id:
            return self.by_id[text]
        return self.phrases.get(normalize(text))

    def suggest(self, text: str) -> str | None:
        hits = difflib.get_close_matches(normalize(text), list(self.phrases), n=1, cutoff=0.6)
        return self.phrases[hits[0]].name if hits else None

    def phrases_longest_first(self) -> list[tuple[str, Product]]:
        return sorted(self.phrases.items(), key=lambda kv: len(kv[0]), reverse=True)
