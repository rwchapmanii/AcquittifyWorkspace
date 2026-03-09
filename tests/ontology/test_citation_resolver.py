from pathlib import Path

from acquittify.ontology.citation_resolver import CitationResolver


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self):
        self.calls = 0

    def get(self, url, headers=None, params=None, timeout=None):
        del url, headers, params, timeout
        self.calls += 1
        return _FakeResponse(
            200,
            {
                "results": [
                    {
                        "id": 123,
                        "citation": "267 U.S. 132",
                        "score": 0.92,
                    }
                ]
            },
        )


def test_resolver_uses_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "citation_cache.sqlite"
    fake_session = _FakeSession()

    resolver = CitationResolver(
        lookup_url="https://example.test/citation-lookup/",
        api_token="token",
        cache_path=cache_path,
        request_timeout=5,
        session=fake_session,
    )

    first = resolver.resolve("267 U.S. 132")
    second = resolver.resolve("267 U.S. 132")

    assert first.resolved_case_id == "courtlistener.123"
    assert first.canonical_citation == "267 U.S. 132"
    assert first.confidence == 0.92
    assert second.resolved_case_id == "courtlistener.123"
    assert fake_session.calls == 1
