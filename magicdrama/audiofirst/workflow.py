"""Content-addressed stage receipts. No implicit retry of uncertain remote work."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .core import digest
from .execution import signature


class SubmissionNotStarted(RuntimeError):
    """Preflight refused before contacting an inference provider; safe to retry."""


@contextmanager
def workspace_lock(path):
    """Cross-platform process lock; another invocation fails before writing artifacts."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=0,isolation_level=None)
    try:
        try:db.execute('BEGIN EXCLUSIVE')
        except sqlite3.OperationalError as error:
            raise RuntimeError('Workspace is busy in another invocation') from error
        yield
    finally:
        db.rollback();db.close()


class StageStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10, isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS stages (name TEXT, fingerprint TEXT, state TEXT, result TEXT, error TEXT, PRIMARY KEY(name,fingerprint))')
        self.db.execute('CREATE TABLE IF NOT EXISTS stage_reconciliations (name TEXT, fingerprint TEXT, evidence TEXT, result_hash TEXT)')

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def run(self, name, inputs, action, remote=False):
        fingerprint = signature(inputs)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT state,result FROM stages WHERE name=? AND fingerprint=?', (name, fingerprint)).fetchone()
            if row and row[0] == 'complete':
                result = json.loads(row[1])
                for artifact in result.get('artifacts', []) if isinstance(result, dict) else []:
                    path = Path(artifact['path'])
                    if not path.is_file() or digest(path) != artifact['sha256']:
                        raise ValueError('Cached artifact missing/changed: ' + str(path))
                self.db.execute('COMMIT')
                return result
            if row and row[0] in ('running', 'unknown'):
                raise RuntimeError('Stage outcome unresolved; reconcile before retry: ' + name)
            self.db.execute('INSERT OR REPLACE INTO stages VALUES (?,?,?,NULL,NULL)', (name, fingerprint, 'running'))
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK')
            raise
        try:
            result = action()
            encoded = json.dumps(result, ensure_ascii=False, allow_nan=False)
            self.db.execute('UPDATE stages SET state=?,result=? WHERE name=? AND fingerprint=?', ('complete', encoded, name, fingerprint))
            return result
        except BaseException as error:
            self.db.execute('UPDATE stages SET state=?,error=? WHERE name=? AND fingerprint=?',
                            ('unknown' if remote and not isinstance(error, SubmissionNotStarted) else 'failed', type(error).__name__, name, fingerprint))
            raise

    def report(self):
        return [dict(zip(('stage', 'input_sha256', 'state', 'error'), row)) for row in self.db.execute('SELECT name,fingerprint,state,error FROM stages ORDER BY rowid')]

    def reconcile(self,name,fingerprint,result,evidence):
        """Import an externally recovered response; never authorize a new submission."""
        if not isinstance(evidence,str) or not evidence.strip():
            raise ValueError('Explicit reconciliation evidence reference required')
        encoded=json.dumps(result,ensure_ascii=False,allow_nan=False)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            changed=self.db.execute("UPDATE stages SET state='complete',result=?,error=NULL WHERE name=? AND fingerprint=? AND state IN ('unknown','running')",
                                    (encoded,name,fingerprint)).rowcount
            if changed!=1:raise ValueError('Only an existing unresolved stage may be reconciled')
            self.db.execute('INSERT INTO stage_reconciliations VALUES (?,?,?,?)',(name,fingerprint,evidence,signature(result)))
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK');raise
