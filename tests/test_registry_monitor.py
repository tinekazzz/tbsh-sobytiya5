"""Offline verification: no external websites or API keys needed."""
from datetime import date
from pathlib import Path
import json
import sys

from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pipeline'))
import monitor_registry as m
import update_events as core

TODAY=date(2026,11,17)
SOURCE={'id':'SRC-007','name':'Тестовый музей','url':'https://example.org/exhibitions',
        'city':'Москва','category':'Выставки','max_details':1,'priority':'A','editorial_media':False}


def test_all_registry_addresses_configured():
    registry=json.loads((ROOT/'registry/full_registry.json').read_text(encoding='utf8'))['sources']
    custom=json.loads((ROOT/'pipeline/collectors.json').read_text(encoding='utf8'))
    rows=m.all_collectors(registry,custom)
    assert len(registry)==len(rows)==274
    assert len({x['id'] for x in rows})==len(registry)
    assert len([x for x in rows if x['priority']=='A']) == sum(x['priority']=='A' for x in registry)
    assert all(x['enabled'] for x in rows)
    assert any(row['id']=='SRC-066' and '/afisha/' in row['url'] for row in rows)


def test_realistic_jsonld_source_extraction():
    soup=BeautifulSoup('''
      <script type="application/ld+json">{"@graph":[
        {"@type":"ExhibitionEvent","name":"Выставка 21 декабря", "startDate":"2026-12-21", "endDate":"2027-01-31", "url":"https://example.org/events/one"},
        {"@type":"Event","name":"Прошедшая выставка","startDate":"2024-01-01"}
      ]}</script>''','html.parser')
    found=core.jsonld_events(soup,SOURCE['url'],SOURCE,TODAY)
    assert len(found)==1
    assert found[0]['start_date']=='2026-12-21'


def test_microdata_support():
    soup=BeautifulSoup('''<main itemscope itemtype="https://schema.org/Event">
    <h2 itemprop="name">Спектакль «Город»</h2>
    <time itemprop="startDate" datetime="2026-12-19T19:00">19 декабря</time>
    <span itemprop="location">Большая сцена</span>
    </main>''','html.parser')
    evs=m.parse_microdata(soup,'https://example.org/events/gorod',SOURCE,core,TODAY)
    assert len(evs)==1 and evs[0]['start_date']=='2026-12-19'


def test_ics_public_calendar():
    ics=b'''BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nSUMMARY:Jazz December\r\nDTSTART:20261211T190000\r\nDTEND:20261211T210000\r\nLOCATION:Concert Hall\r\nURL:https://example.org/events/jazz\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nSUMMARY:Past\r\nDTSTART:20251001\r\nEND:VEVENT\r\nEND:VCALENDAR'''
    evs=m.parse_ics(ics,'https://example.org/cal.ics',SOURCE,core,TODAY)
    assert len(evs)==1 and evs[0]['extraction_method']=='calendar_ics'
    assert evs[0]['title']=='Jazz December'


def test_feed_does_not_treat_publication_date_as_event_date():
    feed=b'''<rss><channel><item><title>Concert news</title><pubDate>Tue, 01 Dec 2026 18:00:00 GMT</pubDate>
    <description>Very interesting artist interview</description><link>https://example.org/news/123</link></item>
    </channel></rss>'''
    assert m.extract_feed(feed,'https://example.org/feed.xml',SOURCE,core,TODAY)==[]


def test_feed_extracts_only_dated_event():
    feed='''<rss><channel><item><title>Концерт 12 декабря 2026 года</title>
    <description>Выступление в концертном зале</description><link>https://example.org/events/123</link></item>
    </channel></rss>'''.encode()
    evs=m.extract_feed(feed,'https://example.org/feed.xml',SOURCE,core,TODAY)
    assert len(evs)==1
    assert evs[0]['start_date']=='2026-12-12'


def test_listing_requires_evidence_of_event_and_date():
    soup=BeautifulSoup('''<ul><li><a href="/events/123">Концерт известной группы</a>
    <time datetime="2026-12-27T20:00:00+03:00">27 дек</time></li>
    <li><a href="/news/456">Новости за декабрь</a><time datetime="2026-12-02">2 дек</time></li></ul>''','html.parser')
    evs=m.extract_listing_anchors(soup,'https://example.org/',SOURCE,core,TODAY)
    assert len(evs)==1 and evs[0]['title']=='Концерт известной группы'


def test_media_site_never_promotes_article_date():
    src={**SOURCE,'editorial_media':True}
    soup=BeautifulSoup('''<a href="/news/concert">Концерт группы</a><time datetime="2026-12-01">12.01</time>''','html.parser')
    assert m.extract_listing_anchors(soup,'https://example.org/',src,core,TODAY)==[]


def test_no_network_offline_preview(tmp_path,monkeypatch):
    # Ensure metadata gets upgraded even when crawl is disabled.
    monkeypatch.setattr(core,'DATA',tmp_path)
    (tmp_path/'editorial_events.json').write_text('[]',encoding='utf8')
    status=core.run(offline=True)
    assert status['configured_collectors']==len(json.loads((ROOT/'registry/full_registry.json').read_text(encoding='utf8'))['sources'])
    assert status['sources_checked_today']==0
    assert status['sources_reached_today']==0
    assert status['mode']=='offline_preview'
    assert (tmp_path/'status.json').exists()
