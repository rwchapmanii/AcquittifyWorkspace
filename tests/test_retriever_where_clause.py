from acquittify_retriever import _build_where_clause


def test_build_where_clause_uses_in_operator() -> None:
    clause = _build_where_clause("Hobbs Act / extortion")
    assert clause is not None
    clause_str = str(clause)
    assert "$contains" not in clause_str
    assert "$in" in clause_str


def test_build_where_clause_none_for_empty() -> None:
    assert _build_where_clause("") is None
    assert _build_where_clause(None) is None
