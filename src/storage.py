"""SQLite sandbox and PostgreSQL deployment adapters for the transactional ledger.

PostgreSQL sessions use a per-world transaction advisory lock before modifying
state. The service lock protects a single connection; independent replicas use
the database lock and revision checks, never a distributed Python lock.
"""
import sqlite3


class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Cursor:
    def __init__(self, cursor):
        self.cursor=cursor
    def fetchone(self):
        r=self.cursor.fetchone()
        return Row(r) if r is not None else None
    def fetchall(self):
        return [Row(r) for r in self.cursor.fetchall()]
    def __iter__(self):
        return iter(self.fetchall())


SCHEMA='''
CREATE TABLE IF NOT EXISTS schema_migration(version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS sim_world(id TEXT PRIMARY KEY, owner TEXT NOT NULL, observer TEXT UNIQUE NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sim_intent(id TEXT PRIMARY KEY, world TEXT NOT NULL, body TEXT NOT NULL, rowid BIGSERIAL UNIQUE);
CREATE TABLE IF NOT EXISTS sim_review(id TEXT PRIMARY KEY, world TEXT NOT NULL, body TEXT NOT NULL, rowid BIGSERIAL UNIQUE);
CREATE TABLE IF NOT EXISTS sim_transfer(id TEXT PRIMARY KEY, payment TEXT UNIQUE NOT NULL, world TEXT NOT NULL, body TEXT NOT NULL, rowid BIGSERIAL UNIQUE);
CREATE TABLE IF NOT EXISTS sim_ledger(id BIGSERIAL PRIMARY KEY, world TEXT NOT NULL, transfer TEXT NOT NULL, account INTEGER NOT NULL, delta BIGINT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS sim_ledger_once ON sim_ledger(world,transfer,account);
CREATE TABLE IF NOT EXISTS sim_event(sequence BIGSERIAL PRIMARY KEY, world TEXT NOT NULL, body TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS sim_event_world ON sim_event(world,sequence);
CREATE INDEX IF NOT EXISTS sim_ledger_world ON sim_ledger(world,account);
CREATE INDEX IF NOT EXISTS sim_intent_world ON sim_intent(world,rowid);
CREATE INDEX IF NOT EXISTS sim_review_world ON sim_review(world,rowid);
CREATE TABLE IF NOT EXISTS sim_access(id TEXT PRIMARY KEY, world TEXT NOT NULL, role TEXT NOT NULL, account INTEGER, expires DOUBLE PRECISION NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, acknowledged BIGINT NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sim_purge(world TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS product_pair(code TEXT PRIMARY KEY, world TEXT NOT NULL, role TEXT NOT NULL, account INTEGER NOT NULL, expires DOUBLE PRECISION NOT NULL, claimed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS product_grant(id TEXT PRIMARY KEY, world TEXT NOT NULL, role TEXT NOT NULL, account INTEGER NOT NULL, expires DOUBLE PRECISION NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS product_idempotency(owner TEXT NOT NULL,path TEXT NOT NULL,key TEXT NOT NULL,fingerprint TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(owner,path,key));
CREATE TABLE IF NOT EXISTS product_case(id TEXT PRIMARY KEY,world TEXT NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS product_check(id TEXT PRIMARY KEY,owner TEXT NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS product_label(id TEXT PRIMARY KEY,world TEXT NOT NULL,body TEXT NOT NULL);
CREATE OR REPLACE FUNCTION maya_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'immutable audit record'; END; $$;
CREATE OR REPLACE FUNCTION maya_retain_review() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NOT EXISTS(SELECT 1 FROM sim_purge WHERE world=OLD.world) THEN RAISE EXCEPTION 'review retention'; END IF; RETURN OLD; END; $$;
INSERT INTO schema_migration(version) VALUES(1) ON CONFLICT DO NOTHING;
'''


class Postgres:
    def __init__(self,url):
        import psycopg
        from psycopg.rows import dict_row
        self.raw=psycopg.connect(url,autocommit=True,row_factory=dict_row,connect_timeout=10)
        # Lock migration setup so multiple replicas do not race on DDL.
        self.raw.execute('SELECT pg_advisory_lock(640040)')
        try:
            self.raw.execute(SCHEMA,prepare=False)
            for table in ('sim_review','sim_transfer','sim_event','sim_ledger'):
                exists=self.raw.execute('SELECT 1 FROM pg_trigger WHERE tgname=%s',(table+'_immutable',)).fetchone()
                if not exists:
                    self.raw.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION maya_immutable()')
            exists=self.raw.execute("SELECT 1 FROM pg_trigger WHERE tgname='sim_review_retain'").fetchone()
            if not exists:
                self.raw.execute('CREATE TRIGGER sim_review_retain BEFORE DELETE ON sim_review FOR EACH ROW EXECUTE FUNCTION maya_retain_review()')
        finally:
            self.raw.execute('SELECT pg_advisory_unlock(640040)')
    @property
    def in_transaction(self):
        from psycopg.pq import TransactionStatus
        return self.raw.info.transaction_status!=TransactionStatus.IDLE
    def execute(self,query,params=()):
        if query.startswith('PRAGMA '):
            return self.raw.execute('SELECT 1')
        query=query.replace('BEGIN IMMEDIATE','BEGIN').replace('?', '%s')
        # This bounded adapter is used only with application-owned SQL.
        return Cursor(self.raw.execute(query,params))
    def executescript(self,script):
        # Equivalent versioned PostgreSQL migrations above replace SQLite-only DDL.
        return None
    def commit(self): self.raw.commit()
    def rollback(self): self.raw.rollback()
    def close(self): self.raw.close()


def connect(database):
    if str(database).startswith(('postgres://','postgresql://')):
        return Postgres(database)
    conn=sqlite3.connect(database,timeout=10,check_same_thread=False)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=10000')
    return conn
