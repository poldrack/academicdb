"""Tests for the site-side files under deploy/sites (copied into site repos)."""
import re
from pathlib import Path

import pytest
import yaml

from academic.models import Link
from academic.publish.site_yaml import render_site_yaml, site_records
from tests.factories import PublicationFactory

ROOT = Path(__file__).resolve().parents[2]
SITES = ROOT / 'deploy' / 'sites'
UPSTREAM_LAB_RENDER = ROOT / 'tests' / 'fixtures' / 'sites' / 'lab_render_upstream.yml'
PIP_LINE = 'pip install nbformat nbclient ipykernel jupyter tomli biopython scholarly crossrefapi toml pymongo orcid'
QMDS = [
    SITES / 'personal' / 'publications.qmd',
    SITES / 'lab' / 'publications.qmd',
    SITES / 'lab' / 'software.qmd',
]


def python_blocks(qmd):
    return re.findall(r'```\{python\}\n(.*?)```', qmd.read_text(), re.S)


def run_qmd(qmd, tmp_path, monkeypatch, capsys, user):
    (tmp_path / 'publications.yml').write_text(render_site_yaml(site_records(user)))
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    for block in python_blocks(qmd):
        exec(compile(block, str(qmd), 'exec'), {'__name__': '__qmd__'})
    return capsys.readouterr().out


def make_pub(user, **kwargs):
    kwargs.setdefault('review_status', 'approved')
    return PublicationFactory(owner=user, **kwargs)


@pytest.fixture
def site_pubs(academic_user):
    make_pub(academic_user, title='New Paper', doi='10.1/x', year=2026,
             publication_name='Journal A', volume='12')
    make_pub(academic_user, title='Old Paper', doi='10.2/y', year=2025,
             publication_name='bioRxiv', is_preprint=True,
             publication_type='preprint')
    return academic_user


def assert_publications_page(out):
    assert out.index('## 2026') < out.index('## 2025')
    assert '[New Paper](https://doi.org/10.1/x)' in out
    assert 'bioRxiv (preprint)' in out
    assert '*12*' in out


def test_personal_publications_page_renders_from_yaml(
        site_pubs, tmp_path, monkeypatch, capsys):
    out = run_qmd(SITES / 'personal' / 'publications.qmd', tmp_path,
                  monkeypatch, capsys, site_pubs)
    assert_publications_page(out)


def test_lab_publications_page_renders_from_yaml(
        site_pubs, tmp_path, monkeypatch, capsys):
    out = run_qmd(SITES / 'lab' / 'publications.qmd', tmp_path,
                  monkeypatch, capsys, site_pubs)
    assert_publications_page(out)


def test_lab_software_page_lists_resource_links(
        academic_user, tmp_path, monkeypatch, capsys):
    make_pub(academic_user, title='With Links', doi='10.3/z', year=2024)
    make_pub(academic_user, title='Without Links', doi='10.4/w', year=2024)
    for kind, url in [('Data', 'https://data.example/1'),
                      ('Code', 'https://code.example/1')]:
        Link.objects.create(owner=academic_user, type=kind, doi='10.3/z',
                            url=url, title=kind)
    out = run_qmd(SITES / 'lab' / 'software.qmd', tmp_path, monkeypatch,
                  capsys, academic_user)
    assert '[Data](https://data.example/1)' in out
    assert '[Code](https://code.example/1)' in out
    assert 'With Links' in out
    assert 'Without Links' not in out


def test_pages_read_yaml_not_json():
    for qmd in QMDS:
        text = qmd.read_text()
        assert 'publications.json' not in text, qmd
        assert 'json.load' not in text, qmd
        assert 'publications.yml' in text, qmd
        assert 'generated from academicdb*' in text or qmd.name == 'software.qmd'


def load_workflow(path):
    return yaml.safe_load(path.read_text())


def triggers(wf):
    return wf.get('on', wf.get(True))


def test_personal_render_workflow():
    path = SITES / 'personal' / '.github' / 'workflows' / 'render.yml'
    wf = load_workflow(path)
    on = triggers(wf)
    assert on['push']['branches'] == ['main']
    assert 'pull_request' in on
    assert wf['permissions'] == {
        'contents': 'read', 'pages': 'write', 'id-token': 'write'}
    text = path.read_text()
    assert 'pyyaml' in text
    assert 'quarto-dev/quarto-actions/setup@v2' in text
    steps = wf['jobs']['render_site']['steps']
    upload = next(s for s in steps if 'upload-pages-artifact' in s.get('uses', ''))
    assert upload['uses'] == 'actions/upload-pages-artifact@v5'
    assert upload['with']['path'] == 'docs'
    deploy = wf['jobs']['deploy']
    assert deploy['if'] == "github.event_name == 'push'"
    assert deploy['steps'][0]['uses'] == 'actions/deploy-pages@v5'
    uses = {s['uses'].split('@')[0]: s['uses'] for s in steps if 'uses' in s}
    assert uses['actions/checkout'] == 'actions/checkout@v7'
    assert uses['actions/setup-python'] == 'actions/setup-python@v7'
    assert any(s.get('run') == 'python fix_mastodon_link.py' for s in steps)


def test_review_dispatch_workflow():
    path = SITES / 'personal' / '.github' / 'workflows' / 'review-dispatch.yml'
    wf = load_workflow(path)
    assert triggers(wf)['pull_request']['types'] == ['closed']
    job = next(iter(wf['jobs'].values()))
    assert "startsWith(github.event.pull_request.head.ref, 'academicdb/review-')" in job['if']
    token = next(s for s in job['steps'] if 'create-github-app-token' in s.get('uses', ''))
    assert token['uses'] == 'actions/create-github-app-token@v3'
    assert token['with']['owner'] == 'poldrack'
    assert token['with']['repositories'] == 'academicdb'
    run = next(s for s in job['steps'] if 'gh api' in s.get('run', ''))
    assert 'repos/poldrack/academicdb/dispatches' in run['run']
    assert 'event_type=review-pr-closed' in run['run']
    assert 'client_payload[pr]=$PR_NUMBER' in run['run']
    assert run['env']['PR_NUMBER'] == '${{ github.event.pull_request.number }}'
    assert '${{' not in run['run']


def test_lab_render_installs_pyyaml():
    upstream = UPSTREAM_LAB_RENDER.read_text()
    deployed = (SITES / 'lab' / '.github' / 'workflows' / 'render.yml').read_text()
    assert PIP_LINE in upstream
    assert deployed == upstream.replace(PIP_LINE, PIP_LINE + ' pyyaml')


def test_review_dispatch_workflow_has_no_default_permissions():
    path = SITES / 'personal' / '.github' / 'workflows' / 'review-dispatch.yml'
    assert load_workflow(path)['permissions'] == {}


@pytest.mark.parametrize('site', ['personal', 'lab'])
def test_publications_page_prints_yaml_citation_verbatim(
        site, tmp_path, monkeypatch, capsys):
    record = {'year': 2026, 'title': 'Ignored', 'citation': 'Smith J. *Exact text*.'}
    (tmp_path / 'publications.yml').write_text(render_site_yaml([record]))
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    qmd = SITES / site / 'publications.qmd'
    for block in python_blocks(qmd):
        exec(compile(block, str(qmd), 'exec'), {'__name__': '__qmd__'})
    assert '- Smith J. *Exact text*.\n' in capsys.readouterr().out
