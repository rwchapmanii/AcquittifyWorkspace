import os
import json
import pytest

from scripts.hybrid_retrieval import _rank_key


@pytest.mark.skipif(os.getenv("RUN_VECTOR_TESTS") != "1", reason="set RUN_VECTOR_TESTS=1 to run vector integration tests")
def test_vector_retrieval_ordering_no_inversion():
    primary = "4A.SUPP.GEN.GEN"
    secondary = ["4A.SEIZ"]
    high_authority = {
        "primary_taxonomy_code": primary,
        "authority_weight": 5,
        "is_holding": True,
        "is_dicta": False,
        "favorability": 10,
        "year": 2020,
        "vector_distance": 0.9,
    }
    low_authority = {
        "primary_taxonomy_code": primary,
        "authority_weight": 2,
        "is_holding": True,
        "is_dicta": False,
        "favorability": 10,
        "year": 2022,
        "vector_distance": 0.1,
    }
    assert _rank_key(high_authority, primary, secondary) > _rank_key(low_authority, primary, secondary)


@pytest.mark.skipif(os.getenv("RUN_VECTOR_TESTS") != "1", reason="set RUN_VECTOR_TESTS=1 to run vector integration tests")
def test_vectors_do_not_change_top_rank_for_equal_authority():
    primary = "4A.SUPP.GEN.GEN"
    secondary = []
    base = {
        "primary_taxonomy_code": primary,
        "authority_weight": 3,
        "is_holding": True,
        "is_dicta": False,
        "favorability": 5,
        "year": 2018,
    }
    row_a = dict(base, vector_distance=0.9)
    row_b = dict(base, vector_distance=0.1)
    assert _rank_key(row_a, primary, secondary) < _rank_key(row_b, primary, secondary)
