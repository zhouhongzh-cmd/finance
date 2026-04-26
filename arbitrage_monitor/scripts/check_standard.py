#!/usr/bin/env python3
"""Lightweight project checks for arbitrage_monitor."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Finding:
    level: str
    message: str
    path: Path | None = None
    line: int | None = None

    def format(self) -> str:
        location = ""
        if self.path is not None:
            rel = self.path.relative_to(PROJECT_ROOT)
            location = str(rel)
            if self.line is not None:
                location = f"{location}:{self.line}"
            location = f"{location}: "
        return f"[{self.level}] {location}{self.message}"


def run_command(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def git_ls_files() -> set[str]:
    result = run_command(["git", "ls-files"], check=True)
    prefix = f"{PROJECT_ROOT.name}/"
    tracked: set[str] = set()
    for raw in result.stdout.splitlines():
        path = raw.strip()
        if not path:
            continue
        if path.startswith(prefix):
            tracked.add(path[len(prefix):])
        else:
            tracked.add(path)
    return tracked


def check_sensitive_tracked() -> list[Finding]:
    findings: list[Finding] = []
    tracked = git_ls_files()

    def is_blocked(path: str) -> bool:
        return (
            path == ".env"
            or path.startswith("data/")
            or path.endswith(".db")
            or path.endswith(".db-wal")
            or path.endswith(".db-shm")
            or (path.startswith("config/") and path.endswith(".local.json"))
        )

    blocked = sorted(path for path in tracked if is_blocked(path))
    for path in blocked:
        findings.append(
            Finding(
                "ERROR",
                "本机私密项、local 覆盖或数据库文件不应被 Git 跟踪",
                PROJECT_ROOT / path,
            )
        )
    return findings


BARE_DATE_NOW = re.compile(r"date\(\s*(['\"])now\1\s*\)")


def iter_python_files() -> list[Path]:
    ignored_parts = {".venv", "__pycache__", ".pytest_cache"}
    files: list[Path] = []
    for path in PROJECT_ROOT.rglob("*.py"):
        if ignored_parts.intersection(path.relative_to(PROJECT_ROOT).parts):
            continue
        files.append(path)
    return files


def check_bare_date_now() -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_python_files():
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if BARE_DATE_NOW.search(line):
                findings.append(
                    Finding(
                        "ERROR",
                        "SQLite 今日查询必须使用本地时间语义，例如 date('now','localtime')",
                        path,
                        line_no,
                    )
                )
    return findings


CREATE_TABLE = re.compile(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.I)


def check_snapshot_retention() -> list[Finding]:
    db_manager = PROJECT_ROOT / "utils" / "db_manager.py"
    if not db_manager.exists():
        return [Finding("ERROR", "找不到 utils/db_manager.py", db_manager)]

    text = db_manager.read_text(encoding="utf-8")
    snapshot_tables = sorted(
        {
            match.group(1)
            for match in CREATE_TABLE.finditer(text)
            if "snapshot" in match.group(1)
        }
    )

    findings: list[Finding] = []
    for table in snapshot_tables:
        if f"DELETE FROM {table} WHERE" not in text:
            findings.append(
                Finding(
                    "ERROR",
                    f"snapshot 表 {table} 缺少基于 DATA_RETENTION_DAYS 的清理路径",
                    db_manager,
                )
            )
    return findings


def run_compileall() -> list[Finding]:
    result = run_command([sys.executable, "-m", "compileall", "-q", "."])
    if result.returncode == 0:
        return []
    return [Finding("ERROR", "compileall 失败:\n" + result.stdout.rstrip())]


def run_pytest(args: list[str]) -> list[Finding]:
    result = run_command([sys.executable, "-m", "pytest", *args])
    if result.returncode == 0:
        return []
    return [Finding("ERROR", "pytest 失败:\n" + result.stdout.rstrip())]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run standard arbitrage_monitor checks.")
    parser.add_argument("--skip-compileall", action="store_true", help="跳过 Python 编译检查")
    parser.add_argument("--pytest", action="store_true", help="额外运行默认 pytest")
    parser.add_argument(
        "--legacy-pytest",
        action="store_true",
        help="额外运行兼容入口 pytest tests/*.py",
    )
    args = parser.parse_args()

    findings: list[Finding] = []
    findings.extend(check_sensitive_tracked())
    findings.extend(check_bare_date_now())
    findings.extend(check_snapshot_retention())

    if not args.skip_compileall:
        findings.extend(run_compileall())
    if args.pytest:
        findings.extend(run_pytest(["-q"]))
    if args.legacy_pytest:
        test_files = sorted(str(path.relative_to(PROJECT_ROOT)) for path in (PROJECT_ROOT / "tests").glob("test*.py"))
        findings.extend(run_pytest(["-q", *test_files]))

    if findings:
        for finding in findings:
            print(finding.format())
        return 1

    print("check_standard: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
