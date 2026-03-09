import os
import json
import subprocess
import sys
import pytest


@pytest.mark.skipif(os.getenv("RUN_VECTOR_TESTS") != "1", reason="set RUN_VECTOR_TESTS=1 to run vector integration tests")
def test_vector_recall_improves():
    intent = {
        "primary": {"code": "4A.SUPP.GEN.GEN", "confidence": 0.8, "version": "2026.01"},
        "secondary": [],
        "posture": "UNKNOWN",
    }
    query = "multi-factor test for suppression under the fourth amendment"
    python_bin = os.getenv("PYTHON_BIN") or sys.executable
    cmd_sql = [
        python_bin,
        "scripts/hybrid_retrieval.py",
        "--intent",
        json.dumps(intent),
        "--query",
        query,
        "--limit",
        "20",
    ]
    cmd_vec = cmd_sql + ["--vectors"]

    out_sql = subprocess.check_output(cmd_sql, text=True)
    out_vec = subprocess.check_output(cmd_vec, text=True)

    res_sql = json.loads(out_sql)
    res_vec = json.loads(out_vec)

    assert len(res_vec.get("results", [])) >= len(res_sql.get("results", []))
