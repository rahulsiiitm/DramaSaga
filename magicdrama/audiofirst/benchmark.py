"""Summarize actual same-input scene trials. Does not fabricate evaluations."""
from .core import finite, integer


def compare_trials(trials):
    if not isinstance(trials, list) or len(trials) < 2:
        raise ValueError('At least two actual trials required')
    inputs = [trial.get('input_sha256') for trial in trials]
    if any(not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value) for value in inputs) or len(set(inputs)) != 1:
        raise ValueError('Controlled trials must bind the same script, references and target format hash')
    rows, names = [], set()
    for trial in trials:
        name = trial.get('name')
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError('Unique trial names required')
        names.add(name)
        accepted = finite(trial['accepted_seconds'], 'accepted seconds')
        generated = finite(trial['generated_seconds'], 'generated seconds')
        if accepted > generated:
            raise ValueError('Accepted duration exceeds generated duration')
        cost = finite(trial['total_cost']['amount'], 'total cost')
        unit = trial['total_cost']['unit']
        if unit not in ('USD', 'INR', 'credits'):
            raise ValueError('Explicit comparable billing unit required')
        errors = trial.get('critical_errors')
        if not isinstance(errors, list) or any(not isinstance(e, str) or not e.strip() for e in errors):
            raise ValueError('Record actual critical errors, using an empty list if none')
        scores = trial.get('viewer_scores', [])
        if not isinstance(scores, list):raise ValueError('Viewer scores must be a list')
        for score in scores:
            finite(score, 'viewer score', 1)
            if score > 5:raise ValueError('Viewer scores use a 1..5 scale')
        rows.append({'name': name, 'unit': unit, 'total_cost': cost, 'accepted_seconds': accepted,
                     'cost_per_accepted_second': cost / accepted if accepted else None,
                     'acceptance_fraction': accepted / generated if generated else 0,
                     'elapsed_seconds': finite(trial['elapsed_seconds'], 'elapsed seconds'),
                     'manual_minutes': finite(trial['manual_minutes'], 'manual minutes'),
                     'rerolls': integer(trial['rerolls'], 'rerolls', 0, 10000), 'critical_errors': errors,
                     'viewer_score_mean': sum(scores) / len(scores) if scores else None, 'viewer_count': len(scores)})
    return {'input_sha256': inputs[0], 'trials': rows, 'cost_units_comparable': len({row['unit'] for row in rows}) == 1,
            'status': 'reported_trials_not_independent_quality_certification', 'automatic_winner': None}
