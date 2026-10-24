"""Consistent local SQLite backup; PostgreSQL uses pg_dump as documented."""
import argparse
import hashlib
import json
import sqlite3
import time
from pathlib import Path

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--database',default='data/v4/product.sqlite');p.add_argument('--out',required=True);a=p.parse_args()
    source=Path(a.database).resolve();target=Path(a.out).resolve()
    if source==target or target.exists():raise ValueError('Choose a new backup path; existing files are preserved')
    if not source.is_file():raise ValueError('Source database does not exist')
    target.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(f'file:{source.as_posix()}?mode=ro',uri=True) as src,sqlite3.connect(target) as dst:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Backup verification failed')
    target.with_suffix('.manifest.json').write_text(json.dumps(dict(created_at=time.time(),sha256=hashlib.sha256(target.read_bytes()).hexdigest(),source=str(source)),indent=2))
    print('Consistent backup verified:',target)
