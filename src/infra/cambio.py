"""Exchange rates to convert taxes and CPMs into the search currency. Free, keyless APIs, cached for 24h.

1. Frankfurter (ECB rates): https://api.frankfurter.dev/v1/latest?from=USD&to=BRL
2. open.er-api.com (covers more currencies, e.g. ARS, CLP, COP): https://open.er-api.com/v6/latest/USD
With no internet and no cache, `converter` raises SemCambio; the caller decides (e.g. drop the tax and warn).
"""

from __future__ import annotations

import httpx

from infra.cache import Cache

TTL_HORAS = 24


class SemCambio(RuntimeError):
    pass


class Cambio:
    def __init__(self, cache: Cache | None = None, http: httpx.Client | None = None):
        self.cache = cache or Cache()
        self.http = http
        self._memo: dict[str, dict[str, float]] = {}

    def _taxas_de(self, base: str) -> dict[str, float]:
        base = base.upper()
        if base in self._memo:
            return self._memo[base]
        if (hit := self.cache.get("cambio", base, ttl_horas=TTL_HORAS)) is not None:
            self._memo[base] = hit
            return hit
        http = self.http or httpx.Client(timeout=15, follow_redirects=True)
        taxas: dict[str, float] = {}
        try:
            r = http.get("https://open.er-api.com/v6/latest/" + base)
            if r.status_code == 200 and r.json().get("result") == "success":
                taxas.update(r.json()["rates"])
        except (httpx.HTTPError, ValueError):
            pass
        try:  # ECB rates take precedence when they cover the currency
            r = http.get("https://api.frankfurter.dev/v1/latest", params={"from": base})
            if r.status_code == 200:
                taxas.update(r.json().get("rates") or {})
        except (httpx.HTTPError, ValueError):
            pass
        if not taxas:
            raise SemCambio(f"no exchange rates available for {base}")
        taxas[base] = 1.0
        self.cache.set("cambio", base, taxas)
        self._memo[base] = taxas
        return taxas

    def taxa(self, de: str, para: str) -> float:
        de, para = de.upper(), para.upper()
        if de == para:
            return 1.0
        taxas = self._taxas_de(de)
        if para not in taxas:
            raise SemCambio(f"no rate {de}→{para}")
        return float(taxas[para])

    def converter(self, valor: float, de: str, para: str) -> float:
        return round(valor * self.taxa(de, para), 2)


_padrao: Cambio | None = None


def padrao() -> Cambio:
    global _padrao
    if _padrao is None:
        _padrao = Cambio()
    return _padrao
