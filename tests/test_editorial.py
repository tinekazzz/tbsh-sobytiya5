"""Static contract checks for the editor's choice on a GitHub Pages site.

The catalog is automatically collected; editorial selections must be separate
and require an authorized GitHub commit to publish.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_editorial_catalog_is_valid_even_when_editor_has_published_picks():
    # The daily workflow must keep passing after the editor publishes a list.
    picks = json.loads((ROOT / 'site/data/editorial_picks.json').read_text('utf8'))
    assert picks.get('version') == 1
    assert isinstance(picks.get('items'), list)
    assert picks.get('updated_at') is None or isinstance(picks.get('updated_at'), str)
    ids = []
    for item in picks['items']:
        assert isinstance(item.get('id'), str) and item['id']
        assert isinstance(item.get('event'), dict)
        assert item['event'].get('title') and item['event'].get('start_date')
        ids.append(item['id'])
    assert len(ids) == len(set(ids))


def test_public_tab_and_administration_are_available():
    page = (ROOT / 'site/index.html').read_text('utf8')
    admin = (ROOT / 'site/admin.html').read_text('utf8')
    app = (ROOT / 'site/assets/app.js').read_text('utf8')
    assert 'data-view="editors"' in page
    assert 'id="editorial-intro"' in page
    assert 'href="./admin.html"' in page
    assert 'Выбор редакции' in page
    assert 'editorial_picks.json' in app
    assert "state.picks" in app
    assert 'Скопировать JSON' in admin
    assert 'Новый' in admin or 'Новое' in admin
    assert 'editorial_picks.json' in admin


def test_automated_crawler_does_not_overwrite_editorial_picks():
    collector = (ROOT / 'pipeline/update_events.py').read_text('utf8')
    workflow = (ROOT / '.github/workflows/daily-update.yml').read_text('utf8')
    assert 'editorial_picks.json' not in collector
    assert 'git add site/data/events.json site/data/status.json' in workflow
    assert 'editorial_picks.json' not in workflow


def test_public_editor_and_poster_keep_https_safety():
    admin = (ROOT / 'site/admin.html').read_text('utf8')
    app = (ROOT / 'site/assets/app.js').read_text('utf8')
    assert 'protocol===\'https:\'' in admin
    assert 'safeImageUrl' in app
    assert 'escapeHtml' in app
