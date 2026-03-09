import json
import os
from pathlib import Path
import subprocess
import sys


def test_doctrine_smoketest_runner_passes(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "run_ontology_doctrine_smoketest.py"
    vault_root = tmp_path / "vault"
    work_dir = tmp_path / "work"
    out_path = tmp_path / "report.json"

    cmd = [
        sys.executable,
        str(script),
        "--vault-root",
        str(vault_root),
        "--work-dir",
        str(work_dir),
        "--output",
        str(out_path),
    ]
    env = dict(os.environ)
    env.update({"PYTHONPATH": str(root)})
    subprocess.run(cmd, check=True, cwd=str(root), env=env)

    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert all(report["checks"].values())
    assert report["details"]["anchor_ratio"] >= 0.9
    assert report["details"]["issue_count"] <= 3
