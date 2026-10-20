"""Archive scoped CPU API observations and compare timestamped dashboard values."""
import csv
import json
import math
import sqlite3
import statistics
from datetime import datetime, timezone, timedelta
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from inventory.data import rows, devices


def stamp(value):
    dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Timestamp must include UTC offset')
    return dt.astimezone(timezone.utc).isoformat()


class Command(BaseCommand):
    help = 'Archive MR CPU samples; optionally compare dashboard CSV without activating thresholds.'

    def add_arguments(self, parser):
        parser.add_argument('--database', required=True)
        parser.add_argument('--dashboard-csv')

    def handle(self, *args, **options):
        path = Path(options['database'])
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.touch(mode=0o600, exist_ok=True)
        path.chmod(0o600)
        with sqlite3.connect(path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS samples (
                integration INTEGER, serial TEXT, observed_at TEXT, model TEXT, name TEXT,
                cpu_load5 INTEGER, cpu_count INTEGER, collected_at TEXT, archived_at TEXT,
                PRIMARY KEY(integration,serial,observed_at))''')
            db.execute('''CREATE TABLE IF NOT EXISTS dashboard_pairs (
                integration INTEGER, serial TEXT, observed_at TEXT, dashboard_value REAL,
                unit TEXT, provenance TEXT, PRIMARY KEY(integration,serial,observed_at))''')
            inventory = {(int(d['meraki_integration_id']), d['meraki_serial']): d
                         for d in devices() if d.get('meraki_integration_id') and str(d.get('model','')).startswith('MR')}
            snapshots = rows('telemetry', '''SELECT s.integration_id,s.snapshot_json FROM meraki_health_snapshots s
                JOIN meraki_integrations i ON i.id=s.integration_id JOIN tenants t ON t.id=i.tenant_id
                WHERE t.tenant_uuid=%s AND i.enabled=TRUE AND s.resource='mr_cpu' ''', (settings.TENANT_UUID,))
            now = datetime.now(timezone.utc)
            added = 0
            for snapshot in snapshots:
                stored = json.loads(snapshot['snapshot_json'])
                payload = stored.get('payload', stored)
                if payload.get('error'):
                    self.stdout.write('CPU source reports failure; no successful samples archived')
                    continue
                for sample in payload.get('mr_observations', []):
                    key = (int(snapshot['integration_id']), sample['serial'])
                    if key not in inventory:
                        continue
                    observed = stamp(sample['observed_at'])
                    if not -60 <= (now-datetime.fromisoformat(observed)).total_seconds() <= 1800:
                        continue
                    if not -60 <= (now-datetime.fromisoformat(stamp(payload['collected_at']))).total_seconds() <= 900:
                        continue
                    raw, cores = sample['cpu_load5'], sample['cpu_count']
                    if isinstance(raw,bool) or not isinstance(raw,int) or raw<0 or isinstance(cores,bool) or not isinstance(cores,int) or cores<1:
                        continue
                    d = inventory[key]
                    added += db.execute('INSERT OR IGNORE INTO samples VALUES (?,?,?,?,?,?,?,?,?)',
                        (key[0],key[1],observed,d['model'],d['display_name'],raw,cores,
                         stamp(payload['collected_at']),now.isoformat())).rowcount
            cutoff = (now-timedelta(days=30)).isoformat()
            db.execute('DELETE FROM dashboard_pairs WHERE observed_at < ?', (cutoff,))
            db.execute('DELETE FROM samples WHERE observed_at < ?', (cutoff,))
            self.stdout.write(f'Archived {added} new CPU samples; retained {db.execute("SELECT COUNT(*) FROM samples").fetchone()[0]} samples (30 days).')
            if options['dashboard_csv']:
                self.compare(db, Path(options['dashboard_csv']))

    def compare(self, db, path):
        """Exact source-time matching only: never pair current UI with older API data."""
        with path.open(newline='') as source:
            reader = csv.DictReader(source)
            required = {'integration_id','serial','observed_at','dashboard_value','unit','provenance'}
            if not required.issubset(reader.fieldnames or []):
                raise CommandError('CSV requires: '+','.join(sorted(required)))
            for row in reader:
                observed = stamp(row['observed_at'])
                value = float(row['dashboard_value'])
                if not math.isfinite(value) or value < 0 or row['unit'] not in {'percent','load-average'} or not row['provenance'].strip():
                    raise CommandError('Invalid dashboard value, unit or provenance')
                identity = (int(row['integration_id']),row['serial'],observed)
                if not db.execute('SELECT 1 FROM samples WHERE integration=? AND serial=? AND observed_at=?',identity).fetchone():
                    raise CommandError('No exact timestamp-matched API sample for '+row['serial'])
                db.execute('INSERT OR REPLACE INTO dashboard_pairs VALUES (?,?,?,?,?,?)',identity+(value,row['unit'],row['provenance']))
        for model,unit in db.execute('SELECT DISTINCT s.model,p.unit FROM samples s JOIN dashboard_pairs p USING(integration,serial,observed_at)'):
            pairs = list(db.execute('''SELECT s.cpu_load5,s.cpu_count,p.dashboard_value FROM samples s
                JOIN dashboard_pairs p USING(integration,serial,observed_at) WHERE s.model=? AND p.unit=?''',(model,unit)))
            formulas = {'raw/1000':lambda r,c:r/1000} if unit=='load-average' else {
                'raw/1000':lambda r,c:r/1000,
                'raw/(1000*cores)*100':lambda r,c:r/(1000*c)*100}
            for formula, predict in formulas.items():
                errors = [abs(predict(raw,cores)-value) for raw,cores,value in pairs]
                self.stdout.write(f'{model}: {len(pairs)} pairs, unit={unit}, hypothesis={formula}, median absolute error={statistics.median(errors):.4f}, maximum error={max(errors):.4f}')
        self.stdout.write('Comparison only. No formula or alert thresholds activated; validate aggregation windows, multiple devices/models and independent intervals.')
