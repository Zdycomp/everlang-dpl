#!/usr/bin/env python3
"""Dependency-free SQLite RAG index for source, docs, and ReFix evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Iterable, List, Dict

DEFAULT_EXTENSIONS = {'.c', '.h', '.cpp', '.hpp', '.py', '.rb', '.java', '.js',
                      '.sql', '.html', '.ever', '.go', '.rs', '.kt', '.json',
                      '.yaml', '.yml', '.md', '.rtf'}
DEFAULT_IGNORES = {'.git', '.venv', 'node_modules', '__pycache__', '.pytest_cache',
                   'dist', 'build', '.mypy_cache'}


def connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
        path UNINDEXED, kind UNINDEXED, line_start UNINDEXED,
        line_end UNINDEXED, content, source_hash UNINDEXED,
        tokenize='unicode61')""")
    con.execute("""CREATE TABLE IF NOT EXISTS metadata(
        path TEXT PRIMARY KEY, kind TEXT NOT NULL, source_hash TEXT NOT NULL,
        bytes INTEGER NOT NULL, lines INTEGER NOT NULL)""")
    con.commit()
    return con


def iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in DEFAULT_EXTENSIONS:
            continue
        if any(part in DEFAULT_IGNORES for part in path.parts):
            continue
        yield path


def kind_for(path: Path) -> str:
    if path.suffix.lower() in {'.md', '.rtf'}:
        return 'documentation'
    if '7-refix-node' in path.parts or path.name.endswith('.jsonl'):
        return 'repair-evidence'
    return 'source'


def chunks(path: Path, size: int = 80):
    lines = path.read_text(errors='replace').splitlines()
    for start in range(0, len(lines), size):
        block = lines[start:start + size]
        yield start + 1, start + len(block), '\n'.join(block)


def build(root: Path, database: Path) -> Dict[str, int]:
    con = connect(database)
    count = 0
    files = 0
    for path in iter_files(root):
        relative = str(path.relative_to(root))
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        con.execute("DELETE FROM chunks WHERE path = ?", (relative,))
        con.execute("DELETE FROM metadata WHERE path = ?", (relative,))
        con.execute("INSERT INTO metadata VALUES (?, ?, ?, ?, ?)",
                    (relative, kind_for(path), digest, len(data),
                     len(data.decode(errors='replace').splitlines())))
        for line_start, line_end, content in chunks(path):
            con.execute("INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
                        (relative, kind_for(path), line_start, line_end,
                         content, digest))
            count += 1
        files += 1
    con.commit()
    con.close()
    return {'files': files, 'chunks': count}


def search(database: Path, query: str, limit: int = 8) -> List[Dict[str, object]]:
    con = connect(database)
    rows = con.execute("""SELECT path, kind, line_start, line_end,
                                 snippet(chunks, 4, '[', ']', '…', 24)
                          FROM chunks WHERE chunks MATCH ? LIMIT ?""",
                       (query, limit)).fetchall()
    con.close()
    return [{'path': row[0], 'kind': row[1], 'line_start': row[2],
             'line_end': row[3], 'snippet': row[4]} for row in rows]


def main(argv=None):
    parser = argparse.ArgumentParser(description='Build/search the local ReFix RAG index')
    sub = parser.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build'); b.add_argument('root', type=Path); b.add_argument('--db', type=Path, default=Path('.rag/index.sqlite'))
    s = sub.add_parser('search'); s.add_argument('query'); s.add_argument('--db', type=Path, default=Path('.rag/index.sqlite')); s.add_argument('--limit', type=int, default=8)
    args = parser.parse_args(argv)
    if args.command == 'build':
        args.db.parent.mkdir(parents=True, exist_ok=True)
        print(json.dumps(build(args.root, args.db), sort_keys=True))
    else:
        print(json.dumps(search(args.db, args.query, args.limit), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
