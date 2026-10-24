"""Watch a bounded engine run live, read-only.

    python tools/engine_tail.py [--project PATH] [--seconds 2]

Prints every new step row and model call from state/research.sqlite as it appears, one line each, until Ctrl+C.
It opens the store read-only (SQLite URI mode=ro), takes no lease, and changes nothing. It shows roles, step kinds,
phases, refusal codes, request timings and token counts; never prompt or reply text (those are not in the ledger).
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time


def rows_after(connection,table,last_rowid):
    return connection.execute(f'SELECT rowid,* FROM "{table}" WHERE rowid>? ORDER BY rowid',(last_rowid,)).fetchall()


def main(argv=None):
    parser=argparse.ArgumentParser(prog='engine_tail',description='Read-only live view of the engine ledger.')
    parser.add_argument('--project',type=Path,default=Path('.'));parser.add_argument('--seconds',type=float,default=2.0)
    args=parser.parse_args(argv)
    path=(args.project/'state'/'research.sqlite').resolve()
    if not path.is_file(): print(f'no store at {path}');return 2
    uri=path.as_uri()+'?mode=ro'
    last={'engine_bounded_runs':0,'engine_cycles':0,'engine_steps':0,'engine_model_calls':0}
    first=True
    print(f'watching {path} (read-only). Ctrl+C to stop.')
    try:
        while True:
            connection=sqlite3.connect(uri,uri=True,timeout=1)
            try:
                for table in last:
                    try: rows=rows_after(connection,table,last[table])
                    except sqlite3.Error: continue
                    for row in rows:
                        last[table]=row[0]
                        if first: continue  # only new rows after the first pass
                        record=json.loads(row[-1]) if isinstance(row[-1],str) and row[-1].startswith('{') else {}
                        stamp=(record.get('recorded_at') or '')[11:19]
                        if table=='engine_bounded_runs': print(f'{stamp} RUN   {row[2]} {row[3]} {record.get("reason") or ""}')
                        elif table=='engine_cycles': print(f'{stamp} CYCLE {row[1]} {row[3]} {record.get("status") or ""}')
                        elif table=='engine_steps':
                            who=record.get('hypothesis_id') or record.get('candidate_id') or ''
                            print(f'{stamp} STEP  {row[4]:<13} {row[5]:<10} {record.get("phase",""):<9} {record.get("code") or ""} {who}')
                        else:
                            usage=record.get('usage') or {};elapsed=record.get('elapsed_seconds')
                            calls=record.get('tool_calls') or []
                            print(f'{stamp} MODEL {row[2]:<13} {row[3]:<10} {elapsed:.1f}s prompt {usage.get("prompt_tokens","?")} completion {usage.get("completion_tokens","?")}'
                                  +(f' tools {[c["name"] for c in calls]}' if calls else ''))
                first=False
            finally: connection.close()
            sys.stdout.flush();time.sleep(args.seconds)
    except KeyboardInterrupt: return 0


if __name__=='__main__': sys.exit(main())
