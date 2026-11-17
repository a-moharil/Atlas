"""Safely copy a previous ATLAS SQLite database into this installation.
Usage: python migrate_database.py '/path/to/previous/observatory.sqlite3'
Stop any old server before running. The destination is not replaced if it already exists.
"""
from pathlib import Path
import argparse,sqlite3,sys
p=argparse.ArgumentParser(description='Copy old ATLAS data without overwriting the destination database')
p.add_argument('old_database',type=Path)
a=p.parse_args()
source=a.old_database.resolve()
target=(Path(__file__).resolve().parent/'observatory.sqlite3').resolve()
if not source.exists() or source.stat().st_size==0:sys.exit('Old database was not found or is empty')
if source==target:sys.exit('Source and destination are identical')
if target.exists():sys.exit('Destination exists. Refusing to overwrite. Rename the destination only after backing it up.')
try:
 with sqlite3.connect(f'file:{source}?mode=ro',uri=True) as old, sqlite3.connect(target) as new:
  old.backup(new)
 print('Database copied successfully to',target)
except Exception:
 if target.exists():target.unlink(missing_ok=True)
 raise
