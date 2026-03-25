#!/usr/bin/env python3
"""Run all repository scripts as smoke tests and write a machine-readable report."""

from __future__ import annotations

import json
import argparse
import subprocess
import sys
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List


SCRIPT_PATTERNS = [
    "LDO/**/*.py",
    "LIWO/**/*.py",
]
EXCLUDE_SUFFIXES = {"LDO_utils.py", "_ldo_common.py", "_liwo_common.py", "_ldo_crossborder_common.py"}


@dataclass
class ScriptResult:
    script: str
    returncode: int
    status: str
    duration_sec: float
    stdout_tail: str
    stderr_tail: str
    error: str = ""


def find_scripts(root: Path) -> List[Path]:
    """Discover runnable repository scripts.

    Parameters
    ----------
    root : Path
        Repository root used to resolve scripts.

    Returns
    -------
    List[Path]
        Discovered runnable scripts.
    """
    scripts: list[Path] = []
    patterns = list(SCRIPT_PATTERNS)
    for pattern in patterns:
        scripts.extend(root.glob(pattern))
    filtered = [
        p
        for p in scripts
        if p.is_file() and p.suffix == ".py" and p.name not in EXCLUDE_SUFFIXES
        and not p.name.startswith("_")
        and "__pycache__" not in p.parts
    ]
    return sorted(set(filtered), key=lambda p: str(p).lower())


def tail_text(text: str, max_lines: int = 40, max_chars: int = 4000) -> str:
    """Return the tail of a text block.

    Parameters
    ----------
    text : str
        Text to trim.
    max_lines : int
        Maximum number of lines to keep.
    max_chars : int
        Maximum number of characters to keep.

    Returns
    -------
    str
        Trimmed tail text.
    """
    lines = text.splitlines()
    tail = "\n".join(lines[-max_lines:])
    if len(tail) > max_chars:
        return tail[-max_chars:]
    return tail


def run_script(root: Path, script: Path, timeout_sec: int, smoke_mode: bool) -> ScriptResult:
    """Run one script and collect the smoke-test result.

    Parameters
    ----------
    root : Path
        Repository root used to resolve scripts.
    script : Path
        Script path to run.
    timeout_sec : int
        Timeout per script run in seconds.
    smoke_mode : bool
        Whether to enable lightweight smoke-test behavior.

    Returns
    -------
    ScriptResult
        Script execution result.
    """
    rel = script.relative_to(root).as_posix()
    start = datetime.now()
    env = os.environ.copy()
    if smoke_mode:
        env.setdefault("LIWO_LDO_SMOKE", "1")
    try:
        cp = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(root),
            timeout=timeout_sec,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        elapsed = (datetime.now() - start).total_seconds()
        status = "ok" if cp.returncode == 0 else "failed"
        return ScriptResult(
            script=rel,
            returncode=cp.returncode,
            status=status,
            duration_sec=elapsed,
            stdout_tail=tail_text(cp.stdout),
            stderr_tail=tail_text(cp.stderr),
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = (datetime.now() - start).total_seconds()
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return ScriptResult(
            script=rel,
            returncode=124,
            status="timeout",
            duration_sec=elapsed,
            stdout_tail=tail_text(stdout if isinstance(stdout, str) else stdout.decode("utf-8", "ignore")),
            stderr_tail=tail_text(stderr if isinstance(stderr, str) else stderr.decode("utf-8", "ignore")),
            error=f"Timed out after {timeout_sec}s",
        )
    except Exception as exc:  # pragma: no cover
        elapsed = (datetime.now() - start).total_seconds()
        return ScriptResult(
            script=rel,
            returncode=1,
            status="error",
            duration_sec=elapsed,
            stdout_tail="",
            stderr_tail="",
            error=str(exc),
        )


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=60,
        help="Timeout per script in seconds.",
    )
    parser.add_argument(
        "--full-run",
        action="store_true",
        help="Run scripts without LIWO_LDO_SMOKE quick mode.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    scripts = find_scripts(root)
    smoke_mode = not args.full_run
    results = [run_script(root, s, args.timeout_sec, smoke_mode) for s in scripts]

    output_dir = root / "tools" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"smoke_report_{ts}.json"
    summary_path = output_dir / f"smoke_summary_{ts}.txt"

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "python": sys.version,
        "cwd": str(root),
        "timeout_sec": args.timeout_sec,
        "smoke_mode": smoke_mode,
        "scripts_total": len(results),
        "ok": sum(1 for r in results if r.status == "ok"),
        "failed": sum(1 for r in results if r.status == "failed"),
        "timeout": sum(1 for r in results if r.status == "timeout"),
        "error": sum(1 for r in results if r.status == "error"),
        "results": [asdict(r) for r in results],
    }
    report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"Generated: {payload['generated_at']}",
        f"Total: {payload['scripts_total']}",
        f"OK: {payload['ok']}",
        f"Failed: {payload['failed']}",
        f"Timeout: {payload['timeout']}",
        f"Error: {payload['error']}",
        "",
    ]
    for r in results:
        if r.status == "ok":
            continue
        lines.append(f"[{r.status}] {r.script} (rc={r.returncode}, {r.duration_sec:.1f}s)")
        if r.error:
            lines.append(f"  error: {r.error}")
        if r.stderr_tail:
            lines.append("  stderr:")
            lines.extend(f"    {ln}" for ln in r.stderr_tail.splitlines()[-6:])
        lines.append("")
    summary_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote: {report_path}")
    print(f"Wrote: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
