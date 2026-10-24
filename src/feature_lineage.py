"""Calculation witnesses for the existing batch-compatible feature contract."""
import math
from statistics import median

DAY = 86400


def witnesses(world, sender, recipient, amount_paise, at, values, windows):
    eligible = sorted((e for e in world['events'] if e['event_at'] < at and e['available_at'] < at),
                      key=lambda e: e['event_at'])
    payments = [e for e in eligible if e['kind'] == 'payment']
    cutoff = int(at) // DAY * DAY
    graph = [e for e in payments if max(e['event_at'], e['available_at']) < cutoff]
    reports = [e for e in eligible if e['kind'] == 'report' and max(e['event_at'], e['available_at']) < cutoff]
    edges = {}
    for e in graph:
        edges.setdefault(e['sender'], []).append(e)
    result = {}
    for side, endpoint, counterparty in (('snd', sender, recipient), ('rcv', recipient, sender)):
        history = [e for e in payments if endpoint in (e['sender'], e['receiver'])]
        first = {}
        for e in history:
            other = e['receiver'] if e['sender'] == endpoint else e['sender']
            first.setdefault(other, e)
        new7 = [e for e in first.values() if at - 7 * DAY < e['event_at']]
        new14 = [e for e in first.values() if at - 14 * DAY < e['event_at']]
        hooks = [e for e in new7 if e['receiver'] == endpoint]
        probes = [e for e in history if {e['sender'], e['receiver']} == {endpoint, counterparty}
                  and e['event_at'] > at - 3600 and e['amount_paise'] <= 1000]
        recent = [e for e in history if e['event_at'] > at - DAY]
        pair = [e for e in recent if e['sender'] == sender and e['receiver'] == recipient]
        # Witness the current report-outward convention, not the deck's reverse.
        paths = []
        for report in reports:
            queue = [(report['account'], [])]
            seen = {report['account']}
            for node, path in queue:
                if node == endpoint:
                    paths.append(dict(report_id=report['id'], edge_ids=[e['id'] for e in path], hops=len(path)))
                    break
                if len(path) < 2:
                    for e in edges.get(node, []):
                        if e['receiver'] not in seen:
                            seen.add(e['receiver'])
                            queue.append((e['receiver'], path + [e]))
        paths.sort(key=lambda p: p['hops'])
        nearest = paths[:1]
        sources = dict(n_t=new7, e_t=new14, g_t=hooks, z_t=history, pi_t=probes,
                       d_R=[e for e in graph if nearest and e['id'] in nearest[0]['edge_ids']],
                       v_t=pair, zc_t=history, ptr_t=recent)
        max_new = max((e['amount_paise'] for e in new14), default=None)
        logs = [math.log(e['amount_paise'] / 100) for e in history]
        calculations = dict(n_t=dict(distinct_counterparties=len(new7)),
                            e_t=dict(candidate_rupees=amount_paise / 100, denominator_rupees=max_new / 100 if max_new else None),
                            g_t=dict(first_contact_credit_ids=[e['id'] for e in hooks]),
                            z_t=dict(log_candidate=math.log(amount_paise / 100), median_log_history=median(logs) if logs else None),
                            pi_t=dict(qualifying_count=len(probes), counterpart=counterparty),
                            d_R=dict(paths=nearest, cap=3, cutoff=cutoff),
                            v_t=dict(count=len(pair)),
                            zc_t=dict(pair24_paise=sum(e['amount_paise'] for e in pair),
                                      median_log_history=median(logs) if logs else None),
                            ptr_t=dict(inflow_paise=sum(e['amount_paise'] for e in recent if e['receiver'] == endpoint),
                                       outflow_paise=sum(e['amount_paise'] for e in recent if e['sender'] == endpoint)))
        for base in sources:
            key = base + '_' + side
            result[key] = dict(value=values[key], endpoint=endpoint, definition=windows[base],
                               event_ids=[e['id'] for e in sources[base]],
                               report_ids=[p['report_id'] for p in nearest] if base == 'd_R' else [],
                               calculation=calculations[base], cutoff=at)
    business = {a['id']: a['business'] for a in world['accounts']}
    for base in windows:
        dependencies = [base + '_snd', base + '_rcv']
        if base in ('n_t', 'e_t'):
            if not business[sender] and business[recipient]:
                dependencies = [base + '_snd']
            elif business[sender] and not business[recipient]:
                dependencies = [base + '_rcv']
        aggregation = 'min capped distance' if base == 'd_R' else 'largest absolute value' if base in ('z_t', 'zc_t') else 'max (ignoring missing)'
        result[base] = dict(value=values[base], definition=windows[base], dependencies=dependencies,
                            aggregation=aggregation, event_ids=sorted({eid for k in dependencies for eid in result[k]['event_ids']}),
                            report_ids=sorted({eid for k in dependencies for eid in result[k]['report_ids']}), cutoff=at)
    return result
