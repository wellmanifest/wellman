"""Shared read-only provenance checks for already validated observations.

Snapshot declarations are not authority or a live checkout freshness check.
Only a successful, unambiguous producing stage without affected quality errors
can establish evidence. Partial positive evidence remains distinct from proof
of absence or complete coverage.
"""
from collections import Counter, defaultdict
from datetime import datetime


def _moment(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return result if result.tzinfo is not None else None


class ObservationEvidence:
    """Index artifact proofs without reading files or changing the observation."""

    def __init__(self, observation):
        self.observation = observation
        self.artifacts = {a['id']: a for a in observation['artifacts']}
        self.components = {c['id']: c for c in observation['components']}
        self.stage_counts = Counter(s['id'] for s in observation['stages'])
        self.stages = defaultdict(list)
        for stage in observation['stages']:
            for ref in stage['artifact_refs']:
                self.stages[ref].append(stage)
        self.start = _moment(observation['started_at'])
        self.end = _moment(observation['finished_at'])

    def bound(self, ref, *, component_id=None, repository_id=None, complete=True):
        artifact = self.artifacts.get(ref)
        if (not artifact or artifact['freshness'] != 'verified'
                or artifact['origin_observation_id'] != self.observation['observation_id']
                or self.start is None or self.end is None or self.start > self.end):
            return False
        for stage in self.stages[ref]:
            cid = stage['component_id']
            component = self.components.get(cid)
            if (self.stage_counts[stage['id']] != 1 or stage['tool'] != artifact['producer']
                    or component_id is not None and cid not in (None, component_id)
                    or repository_id is not None and cid is not None and
                       (not component or component['repository_id'] != repository_id)
                    or stage['status'] not in (('complete',) if complete else ('complete', 'partial'))
                    or stage['exit_code'] != 0 or stage['errors']
                    or complete and (stage['coverage'] != 'complete' or stage['truncated'])):
                continue
            start, end = _moment(stage['started_at']), _moment(stage['finished_at'])
            if start is None or end is None or not self.start <= start <= end <= self.end:
                continue
            affected = {ref, stage['id']}
            for scope_cid in (component_id, cid):
                if scope_cid is not None:
                    affected.add(scope_cid)
                    if scope_cid in self.components:
                        affected.add(self.components[scope_cid]['repository_id'])
            if repository_id is not None:
                affected.add(repository_id)
            invalid = any(
                (issue['severity'] == 'error' or issue['code'] == 'SOURCE_CHANGED_DURING_SCAN')
                and (not issue['affected_refs'] or affected.intersection(issue['affected_refs']))
                for issue in self.observation['quality_issues']
            )
            if not invalid:
                return True
        return False
