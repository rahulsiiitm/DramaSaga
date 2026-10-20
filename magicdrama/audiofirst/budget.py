import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import sqlite3


def amount(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('Invalid amount')
    if not result.is_finite() or result < 0:
        raise ValueError('Amount must be finite and nonnegative')
    return result


class SpendLedger:
    """A conservative local ledger. It cannot reverse provider-side overcharges."""
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=10, isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (key TEXT PRIMARY KEY, provider TEXT, unit TEXT, payload_hash TEXT, reserved TEXT, actual TEXT, state TEXT, provider_id TEXT)')

    def close(self):
        self.db.close()

    def reserve(self, key, provider, unit, payload, quote, approval):
        estimate = amount(quote['amount'])
        cap = amount(approval['cap'])
        if estimate <= 0 or cap <= 0:
            raise ValueError('Positive quote and explicit approved cap required')
        today = datetime.date.today().isoformat()
        if quote.get('verified_at') != today or approval.get('valid_on') != today:
            raise ValueError('Quote and approval must be current')
        if quote.get('unit') != unit or approval.get('unit') != unit or approval.get('provider') != provider or not approval.get('approval_reference'):
            raise ValueError('Provider, units and approval evidence must match')
        signature = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT payload_hash,state,provider_id FROM jobs WHERE key=?', (key,)).fetchone()
            if row:
                if row[0] != signature:
                    raise ValueError('Existing job has a different payload; use an explicit new attempt')
                raise RuntimeError(f'Job already reserved: {row[1]}; reconcile or resume, never auto-resubmit')
            rows = self.db.execute('SELECT reserved,actual FROM jobs WHERE provider=? AND unit=?', (provider, unit)).fetchall()
            exposure = sum((max(amount(r), amount(a)) for r, a in rows), Decimal(0))
            if exposure + estimate > cap:
                raise ValueError('Approved spend cap exceeded')
            self.db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)',
                            (key, provider, unit, signature, str(estimate), '0', 'reserved', None))
        except Exception:
            self.db.execute('ROLLBACK')
            raise
        self.db.execute('COMMIT')
        return signature

    def mark_submitting(self, key):
        if self.db.execute("UPDATE jobs SET state='submitting' WHERE key=? AND state='reserved'", (key,)).rowcount != 1:
            raise ValueError('Job must be reserved exactly once')

    def submitted(self, key, provider_id):
        if not provider_id:
            raise ValueError('Provider ID required')
        if self.db.execute("UPDATE jobs SET state='submitted',provider_id=? WHERE key=? AND state IN ('submitting','unknown')", (provider_id, key)).rowcount != 1:
            raise ValueError('Unexpected submission state')

    def unknown(self, key):
        if self.db.execute("UPDATE jobs SET state='unknown' WHERE key=? AND state='submitting'", (key,)).rowcount != 1:
            raise ValueError('Unexpected timeout state')

    def complete(self, key, actual):
        cost = str(amount(actual))
        if self.db.execute("UPDATE jobs SET state='complete',actual=? WHERE key=? AND state='submitted'", (cost, key)).rowcount != 1:
            raise ValueError('Only reconciled submitted jobs can complete')

    def report(self):
        rows = self.db.execute('SELECT key,provider,unit,reserved,actual,state,provider_id FROM jobs ORDER BY key').fetchall()
        return [dict(zip(('key', 'provider', 'unit', 'reserved', 'actual', 'state', 'provider_id'), row)) for row in rows]
