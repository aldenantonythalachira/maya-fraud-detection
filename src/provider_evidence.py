"""Inspectable mock provider envelopes; no invented clean verdicts or FRI scores."""


def responses(world, evidence, at):
    reports = [e for e in evidence if e['kind'] == 'report']
    result = {}
    for name in ('FRI', 'MuleHunter', 'NCRP'):
        setting = world.get('providers', {}).get(name, {})
        status = setting.get('status', 'unavailable')
        result[name] = dict(provider=name, synthetic=True, status=status,
                            observed_at=at, available_at=setting.get('changed_at'),
                            provenance='local simulation control; no external request',
                            verdict='unknown', evidence_ids=[])
        if name == 'MuleHunter' and status == 'available':
            result[name].update(verdict='synthetic_report_present' if reports else 'unknown',
                                evidence_ids=[e['id'] for e in reports])
        if name == 'FRI' and status == 'available':
            result[name]['detail'] = 'No phone identity supplied; no phone-risk verdict'
        if name == 'NCRP' and status == 'available':
            result[name]['detail'] = 'Synthetic case filing available to analyst; never sent externally'
    return result
