"""Lossless, preflighted transport pages. Pages are local judgments, never a joint conclusion."""
from copy import deepcopy
from .util import canonical, digest
from .compact import unpack_state

FORMAT = 'evidence-pages-v1'


def atoms(value, path=()):
    """Typed paths preserve every leaf, empty container and character without inference."""
    if isinstance(value, dict) and value:
        for key in sorted(value):
            yield from atoms(value[key], path + (key,))
    elif isinstance(value, list) and value:
        for i, item in enumerate(value):
            yield from atoms(item, path + (i,))
    elif isinstance(value, str) and len(value) > 512:
        for offset in range(0, len(value), 512):
            yield {'path': list(path), 'text': value[offset:offset+512], 'offset': offset, 'length': len(value)}
    else:
        yield {'path': list(path), 'value': value}


def pair_context(parent):
    if parent['kind'] != 'pair':
        return None
    from .compact import unpack_state
    records = unpack_state(parent['state']).get('records', [])
    columns = sorted({k for r in records for k in r['fields']})
    # Full normalized fields, not selected favorable fields. Unknown values remain explicit.
    return {'columns': columns, 'rows': [{'id': r['id'], 'values': [r['fields'].get(k) for k in columns]} for r in records],
            'note': 'Complete normalized fields of both endpoints. Raw values and provenance are in numbered evidence entries.'}


def page(parent, entries, start, stop):
    state = {'transport': FORMAT, 'parent_unit_id': parent['id'], 'parent_kind': parent['kind'],
             'research_question': parent['state']['research_question'],
             'domain': parent['state']['domain'],
             'scope': parent['scope'], 'entry_range': [start, stop], 'entry_total': len(entries),
             'evidence_entries': entries[start:stop],
             'limits': ['This is a partial-context page, not a simultaneous judgment of the entire parent evidence.',
                        'Read typed paths as locations in the original evidence. Text offsets continue the same value; nothing is omitted.',
                        'Unknowns remain unknown. Any local candidate requires review of all pages and contradictory evidence.',
                        'Completion means every declared page was inspected, not global reasoning across all pages or synthesis approval.']}
    joint = pair_context(parent)
    if joint is not None:
        state['joint_pair_context'] = joint
    uid = 'UP' + digest([parent['id'], start, stop, state])[:24]
    return {'id': uid, 'kind': parent['kind'], 'scope': parent['scope'], 'record_ids': parent['record_ids'],
            'parent_unit_id': parent['id'], 'parent_hash': digest(parent), 'entry_range': [start, stop],
            'context_mode': 'partitioned_local', 'state': state}


def budget_exceeded(exc):
    return 'Full evidence exceeds token budget:' in str(exc) or 'request body exceeds byte budget' in str(exc)


def make_pages(parent, checker):
    """Freeze exact token-checked ranges before the first inference. No failed chunk is dropped."""
    try:
        check = checker(parent['state'])
        return [parent], {'parent_hash': digest(parent), 'ranges': None, 'checks': [check]}
    except ValueError as exc:
        if not budget_exceeded(exc):
            raise
    entries = list(atoms(unpack_state(parent['state'])))
    def fit(start, stop):
        candidate = page(parent, entries, start, stop)
        try:
            return [(candidate, checker(candidate['state']), [start, stop])]
        except ValueError as exc:
            if not budget_exceeded(exc): raise
            if stop-start <= 1:
                raise ValueError('An indivisible entry or complete pair context exceeds the budget; no evidence may be dropped: ' + parent['id']) from exc
            middle = (start+stop)//2
            return fit(start, middle) + fit(middle, stop)
    fitted = fit(0, len(entries))
    return [v[0] for v in fitted], {'parent_hash': digest(parent), 'ranges': [v[2] for v in fitted],
                                 'checks': [v[1] for v in fitted], 'entry_count': len(entries),
                                 'entries_hash': digest(entries)}


def restore_pages(parent, spec):
    if spec['parent_hash'] != digest(parent):
        raise ValueError('Partition parent was modified')
    if spec['ranges'] is None:
        return [parent]
    entries = list(atoms(unpack_state(parent['state'])))
    if spec['entry_count'] != len(entries) or spec['entries_hash'] != digest(entries):
        raise ValueError('Partition source entries were modified')
    cursor = 0; result = []
    for start, stop in spec['ranges']:
        if start != cursor or stop <= start or stop > len(entries):
            raise ValueError('Partition has an omission, overlap or reordered source entries')
        result.append(page(parent, entries, start, stop)); cursor = stop
    if cursor != len(entries):
        raise ValueError('Partition does not cover every source entry')
    return result


def execution_units(records, profile, index=None):
    from .plan import enumerate_units
    seen = set()
    for parent in enumerate_units(records, profile):
        if parent['id'] in seen: continue
        seen.add(parent['id'])
        if index is None:
            yield parent
        else:
            if parent['id'] not in index['parents']: raise ValueError('Missing logical unit partition')
            yield from restore_pages(parent, index['parents'][parent['id']])
    if index is not None and seen != set(index['parents']):
        raise ValueError('Unexpected logical unit partition')
