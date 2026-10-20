"""Read-only comparison of rounded Playwright UI observations to archived API samples.

Uses the workspace's existing credential-resolving remote helper. Never sends UI
credentials anywhere or treats a minute-level match as an exact source timestamp.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
import json
from pathlib import Path
import statistics
import sys
from zoneinfo import ZoneInfo


def compare(observations, api):
    indexed = defaultdict(list)
    for sample in api:
        for zone in {x['timezone'] for x in observations}:
            dt = datetime.fromisoformat(sample[2]).astimezone(ZoneInfo(zone))
            indexed[(sample[1], zone, dt.strftime('%Y-%m-%d %H:%M'))].append(sample)
    matched = {}
    ambiguous = 0
    for capture in observations:
        zone = capture['timezone']
        captured = datetime.fromisoformat(capture['captured_at'].replace('Z','+00:00')).astimezone(ZoneInfo(zone))
        for point in capture['observations']:
            hour, minute = map(int, point['displayed_time'].split(':'))
            dt = captured.replace(hour=hour,minute=minute,second=0,microsecond=0)
            if dt > captured: dt -= timedelta(days=1)
            key = (capture['serial'],zone,dt.strftime('%Y-%m-%d %H:%M'))
            samples = indexed.get(key, [])
            if len(samples) > 1:
                ambiguous += 1
                continue
            if not samples: continue
            sample = samples[0]
            pairkey = (sample[0],sample[1],sample[2])
            pointvalue = float(point['displayed_percent'])
            pair = dict(integration=sample[0],serial=sample[1],api_observed_at=sample[2],model=sample[3],
                        raw=sample[4],cores=sample[5],ui_percent=pointvalue,ui_minute=key[2],
                        captured_at=capture['captured_at'],precision='unique same-minute match; UI seconds unavailable')
            if pairkey in matched and (matched[pairkey].get('changed_ui_value') or matched[pairkey]['ui_percent'] != pointvalue):
                pair['changed_ui_value'] = True
            matched[pairkey] = pair
    groups = defaultdict(list)
    for pair in matched.values(): groups[pair['model']].append(pair)
    hypotheses = {'raw/1000':lambda r,c:r/1000,
                  'raw/(1000*cores)':lambda r,c:r/(1000*c),
                  'raw/(1000*cores)*100':lambda r,c:r/(1000*c)*100}
    summary = []
    for model,pairs in groups.items():
        for formula,fn in hypotheses.items():
            errors = [abs(fn(p['raw'],p['cores'])-p['ui_percent']) for p in pairs]
            summary.append(dict(model=model,pairs=len(pairs),hypothesis=formula,
                                median_absolute_error=statistics.median(errors),max_absolute_error=max(errors)))
    return dict(generated_at=datetime.now().astimezone().isoformat(),pairs=list(matched.values()),
                summary=summary,ambiguous_minutes_skipped=ambiguous,
                warning='Empirical comparison only. Rounded UI values/time, aggregation and core scaling remain unverified; no formula or thresholds activated.')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--ui-jsonl',required=True)
    p.add_argument('--output',required=True)
    args = p.parse_args()
    observations = [json.loads(line) for line in Path(args.ui_jsonl).read_text().splitlines() if line.strip()]
    observations = [x for x in observations if 'observations' in x]
    serials = sorted({x['serial'] for x in observations})
    if not serials: raise RuntimeError('No successful UI observations available')
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'local/analysis'))
    from remote import run
    script = '''import sqlite3,json
c=sqlite3.connect('file:/var/lib/concierge-cpu-calibration/samples.sqlite3?mode=ro',uri=True)
serials='''+repr(serials)+'''
q='SELECT integration,serial,observed_at,model,cpu_load5,cpu_count FROM samples WHERE serial IN ('+','.join('?' for _ in serials)+') ORDER BY observed_at'
print(json.dumps(c.execute(q,serials).fetchall()))
'''
    status,text = run('controller',script)
    if status: raise RuntimeError('Read-only API archive query failed')
    result = compare(observations,json.loads(text))
    target = Path(args.output)
    target.write_text(json.dumps(result,indent=2))
    target.chmod(0o600)
    print(json.dumps({'pairs':len(result['pairs']),'summary':result['summary'],'output':str(target)}))


if __name__ == '__main__': main()
