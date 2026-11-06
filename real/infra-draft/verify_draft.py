"""Static offline checks only: no cluster/schema validation or external commands."""
import hashlib
import json
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]


def verify():
    entries = json.loads((BASE/'COPY_MANIFEST.json').read_text())
    assert len(entries) == 5
    for entry in entries:
        source, destination = (ROOT/entry[k] for k in ('source', 'destination'))
        assert source.read_bytes() == destination.read_bytes()
        assert hashlib.sha256(destination.read_bytes()).hexdigest() == entry['sha256']
    overlay = yaml.safe_load((BASE/'manifests/kustomization.yaml').read_text())
    assert overlay['namespace'] == 'qrl-calib'
    assert len(overlay['resources']) == 6
    objects = []
    for resource in overlay['resources']:
        path = (BASE/'manifests'/resource).resolve()
        assert path.is_relative_to(BASE/'manifests')
        objects.extend(yaml.safe_load_all(path.read_text()))
    assert len(objects) == 7
    for obj in objects:
        if obj['kind'] == 'Namespace':
            assert obj['metadata']['name'] == 'qrl-calib'
        else:
            assert obj['kind'] in ('Deployment', 'Service', 'HorizontalPodAutoscaler', 'NetworkPolicy')
            assert obj['metadata'].get('namespace', 'qrl-calib') == 'qrl-calib'
    policy = next(o for o in objects if o['kind'] == 'NetworkPolicy')['spec']
    assert set(policy['policyTypes']) == {'Ingress', 'Egress'}
    assert policy['ingress'] == [{'from': [{'podSelector': {}}]}]
    assert policy['egress'] == [{'to': [{'podSelector': {}}]}]
    for name in ('README.md', 'REDIS_TOPOLOGY.md', 'RUNBOOK.md'):
        assert (BASE/name).stat().st_size > 0
    return entries


if __name__ == '__main__':
    verify()
    print('DRAFT_STATIC_OK')
