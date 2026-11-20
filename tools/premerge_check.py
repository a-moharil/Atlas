"""Pre-merge safety check for Sanjaya. Standard library only; run from the repository root:

    python tools/premerge_check.py

It checks the files git is about to publish, then runs the whole test suite with the network switched off, and
prints PASS or FAIL for each step. Exit code 0 means everything passed.

1. Every tracked Python file compiles.
2. No local data, caches, databases or secrets are tracked (observatory.sqlite3, election_data/, model_cache/, .env ...),
   and no file this branch adds or changes is larger than 5 MB.
3. No credentials in tracked text: private keys, GitHub/AWS/OpenAI-style tokens, key=value secrets.
4. TLS verification is never switched off (no CERT_NONE, _create_unverified_context or verify=False).
5. Every request to a state site goes through the public-address check, and the AP connector is gone.
6. The test suite passes offline: connections outside this computer are refused for the whole run, so no test
   touches the internet (tests may still use their own local servers on 127.0.0.1).
"""
from __future__ import annotations

import py_compile
import re
import socket
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 5_000_000
FORBIDDEN = re.compile(r'(^|/)(observatory\.sqlite3.*|.*\.sqlite3(-wal|-shm)?|\.env(\..*)?|election_data/.*|model_cache/.*|'
                       r'research_cache/.*|logo_cache/.*|previews/.*|\.sanjaya_python\.txt|setup_log\.txt)$')
SECRETS = [
    (re.compile(r'-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----'), 'private key'),
    (re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b'), 'GitHub token'),
    (re.compile(r'\bAKIA[0-9A-Z]{16}\b'), 'AWS access key'),
    (re.compile(r'\bsk-[A-Za-z0-9]{32,}\b'), 'API secret key'),
    (re.compile(r'''(?i)\b(api[_-]?key|secret|password|token)\b\s*[:=]\s*['"][A-Za-z0-9_\-]{16,}['"]'''), 'hard-coded credential'),
]
INSECURE_TLS = re.compile(r'CERT_NONE|_create_unverified_context|verify\s*=\s*False|check_hostname\s*=\s*False')
TEXT_EXT = {'.py', '.js', '.css', '.html', '.md', '.json', '.txt', '.bat', '.sh', '.yaml', '.yml', '.toml', '.cfg', '.ini'}
results = []


def report(name, ok, detail=''):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f'\n      {detail}' if detail and not ok else ''))


def tracked():
    try:
        out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [ROOT / p for p in out.splitlines() if p], True
    except (OSError, subprocess.CalledProcessError):
        skip = re.compile(r'(^|/)(\.git|__pycache__|election_data|model_cache|research_cache|logo_cache|previews|\.venv|venv)(/|$)')
        return [p for p in ROOT.rglob('*') if p.is_file() and not skip.search(p.relative_to(ROOT).as_posix())], False


def changed():
    """Files this branch changes compared with origin/main, or None when that can't be worked out."""
    try:
        out = subprocess.run(['git', 'diff', '--name-only', 'origin/main...HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return {ROOT / p for p in out.splitlines() if p}
    except (OSError, subprocess.CalledProcessError):
        return None


def rel(p):
    return p.relative_to(ROOT).as_posix()


def main():
    files, in_git = tracked()
    if not in_git:
        print('note: not a git checkout, so every file in the folder is checked\n')

    bad = []
    for p in files:
        if p.suffix == '.py':
            try:
                py_compile.compile(str(p), doraise=True)
            except py_compile.PyCompileError as exc:
                bad.append(f'{rel(p)}: {exc.msg.strip().splitlines()[-1]}')
    report('1. Every Python file compiles', not bad, '; '.join(bad[:5]))

    if in_git:
        forbidden = [rel(p) for p in files if FORBIDDEN.search(rel(p))]
    else:
        forbidden = [rel(p) for p in files if FORBIDDEN.search(rel(p)) and not rel(p).endswith('.sqlite3')]
    diff = changed() if in_git else None
    scope = [p for p in files if diff is None or p in diff]
    big = [f'{rel(p)} ({p.stat().st_size / 1e6:.1f} MB)' for p in scope if p.exists() and p.stat().st_size > MAX_BYTES]
    report('2. No local data, caches, databases or .env files tracked', not forbidden, ', '.join(forbidden[:8]))
    report('2. No file larger than 5 MB ' + ('added or changed by this branch' if diff is not None else 'in the folder'), not big,
           ', '.join(big[:8]))

    leaks, insecure = [], []
    for p in files:
        if p.suffix.lower() not in TEXT_EXT or not p.exists() or p.stat().st_size > MAX_BYTES:
            continue
        r = rel(p)
        text = p.read_text(encoding='utf-8', errors='replace')
        if not r.startswith('tests/fixtures/'):
            for rx, what in SECRETS:
                m = rx.search(text)
                if m and 'premerge_check.py' not in r:
                    leaks.append(f'{r}: {what}')
        if p.suffix == '.py' and 'premerge_check.py' not in r and not r.startswith('tests/'):
            for n, line in enumerate(text.splitlines(), 1):
                if INSECURE_TLS.search(line) and not line.lstrip().startswith('#'):
                    insecure.append(f'{r}:{n}')
    report('3. No credentials in tracked files', not leaks, ', '.join(leaks[:8]))
    report('4. TLS certificate checks are never switched off', not insecure, ', '.join(insecure[:8]))

    server = (ROOT / 'server.py').read_text(encoding='utf-8')
    fetch = server[server.find('def fetch_public_record'):server.find('def fetch_bytes')]
    ok = 'validate_external_url(url, allow_http=True)' in fetch and 'PublicRecordRedirectHandler' in fetch
    report('5. State-site requests pass the public-address check (and on every redirect)', ok)
    ap = [rel(p) for p in files if p.suffix in ('.py', '.js') and rel(p) != 'tools/premerge_check.py' and not rel(p).startswith('tests/')
          and re.search(r'\bus_ap\b|ap_key|/api/us/settings', p.read_text(encoding='utf-8', errors='replace'))]
    report('5. The AP connector is fully removed', not (ROOT / 'us_ap.py').exists() and not ap, ', '.join(ap))

    # Tests may talk to their own local servers (127.0.0.1); anything outside this computer is refused.
    def local(addr):
        host = addr[0] if isinstance(addr, tuple) else addr
        return isinstance(host, str) and (host in ('localhost', '::1') or host.startswith('127.'))
    real_connect, real_connect_ex, real_create = socket.socket.connect, socket.socket.connect_ex, socket.create_connection

    def connect(self, addr):
        if not local(addr):
            raise OSError(f'network disabled during the pre-merge test run: {addr}')
        return real_connect(self, addr)

    def connect_ex(self, addr):
        if not local(addr):
            raise OSError(f'network disabled during the pre-merge test run: {addr}')
        return real_connect_ex(self, addr)

    def create(addr, *a, **k):
        if not local(addr):
            raise OSError(f'network disabled during the pre-merge test run: {addr}')
        return real_create(addr, *a, **k)
    socket.socket.connect, socket.socket.connect_ex, socket.create_connection = connect, connect_ex, create
    import os
    os.chdir(ROOT)
    sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    run = unittest.TextTestRunner(verbosity=0, stream=sys.stderr).run(suite)
    report(f'6. Test suite passes with the network off ({run.testsRun} tests, {len(run.skipped)} skipped)', run.wasSuccessful(),
           f'{len(run.failures)} failures, {len(run.errors)} errors (details above)')

    print('\nAll checks passed: safe to merge.' if all(results) else '\nSome checks failed: fix them before merging.')
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
