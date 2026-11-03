"""Ein fehlgeschlagener Sicherheitscheck darf kein Release veröffentlichen."""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


def test_release_veroeffentlicht_nur_nach_erfolgreicher_security_ci():
    # BaseLoader bewahrt GitHub Actions' YAML-1.2-Schlüssel `on` als String.
    ci = yaml.load((ROOT / '.github/workflows/ci.yml').read_text(), Loader=yaml.BaseLoader)
    release = yaml.load((ROOT / '.github/workflows/build.yml').read_text(), Loader=yaml.BaseLoader)
    assert 'workflow_call' in ci['on']
    jobs = release['jobs']
    assert jobs['security']['uses'] == './.github/workflows/ci.yml'
    assert 'security' in jobs['build']['needs']
    assert ci['jobs']['desktop-audit']['steps'][-1]['run'].endswith('cargo audit --deny unsound\n')
    for job, prerequisite in [('updater-json', 'build'), ('release-notes', 'updater-json'), ('deploy-web', 'release-notes')]:
        assert jobs[job]['needs'] == prerequisite
        # Ohne if-Override gilt success(); !cancelled() würde auch bei Fehlern laufen.
        assert 'if' not in jobs[job]
