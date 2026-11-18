"""Regression tests for real event poster collection + poster fallback data."""
from datetime import date
from pathlib import Path
import sys

from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pipeline'))
import update_events as core
import monitor_registry as monitor

TODAY=date(2026,11,18)
SOURCE={'id':'test','name':'Театр-тест','url':'https://example.org/afisha',
        'city':'Москва','category':'Театр','editorial_media':False}


def test_og_image_on_event_page():
    page='''<html><head><meta property="og:image" content="/images/dekabr-premiere.jpg"></head>
    <body><h1>Спектакль «Пример»</h1><time datetime="2026-12-18">18 декабря</time></body></html>'''
    soup=BeautifulSoup(page,'html.parser')
    out=core.page_event(soup,'https://example.org/events/primer',SOURCE,TODAY)
    assert len(out)==1
    assert out[0]['image_url']=='https://example.org/images/dekabr-premiere.jpg'


def test_image_from_event_jsonld():
    html='''<script type="application/ld+json">{
    "@type":"TheaterEvent", "name":"Спектакль Проект", "startDate":"2026-12-18",
    "image":{"url":"/media/theater-poster.webp"}, "url":"https://example.org/events/project"
    }</script>'''
    events=core.jsonld_events(BeautifulSoup(html,'html.parser'),'https://example.org/events/',SOURCE,TODAY)
    assert events[0]['image_url']=='https://example.org/media/theater-poster.webp'


def test_poster_matching_from_the_correct_card_only():
    html='''<main><article class="card"><a href="/events/1">Тестовая постановка «Шум»</a>
    <img src="/images/noise.jpg" alt="Шум"></article>
    <article class="card"><a href="/events/2">Тестовая постановка «Рай»</a>
    <img src="/images/heaven.jpg" alt="Рай"></article></main>'''
    soup=BeautifulSoup(html,'html.parser')
    assert core.find_poster_in_listing(soup,'Тестовая постановка «Шум»','https://example.org/afisha')=='https://example.org/images/noise.jpg'
    assert core.find_poster_in_listing(soup,'Тестовая постановка «Рай»','https://example.org/afisha')=='https://example.org/images/heaven.jpg'
    assert not core.find_poster_in_listing(soup,'Совсем другое шоу','https://example.org/afisha')


def test_images_in_listing_crawler():
    soup=BeautifulSoup('''<ul><li><a href="/events/123">Концерт известной группы</a>
    <picture><img data-src="/poster/123.jpg"></picture>
    <time datetime="2026-12-27T20:00:00+03:00">27 дек</time></li></ul>''','html.parser')
    events=monitor.extract_listing_anchors(soup,'https://example.org/afisha',SOURCE,core,TODAY)
    assert len(events)==1
    assert events[0]['image_url']=='https://example.org/poster/123.jpg'


def test_dedupe_preserves_event_poster_when_editorial_wins():
    e={'id':'seed-1','title':'Выставка месяца','start_date':'2026-12-20','end_date':'2027-02-20','venue':'ГЭС-2',
       'url':'https://example.org/projects/first','origin':'editorial','description':'Проверено','category':'Выставки'}
    a={**e,'id':'auto-1','url':'https://example.org/projects/first','origin':'automatic',
       'image_url':'https://example.org/posters/exhibition.jpg'}
    result=core.merge_events([e],[],[a],[],TODAY)
    assert len(result)==1
    assert result[0]['origin']=='editorial'
    assert result[0]['image_url']==a['image_url']


def test_reject_branding_icons_as_posters():
    assert not core.normalize_image_url('https://example.org/assets/logo.svg')
    assert not core.normalize_image_url('https://example.org/icon.png')
    assert core.normalize_image_url('//example.org/poster/123.webp')=='https://example.org/poster/123.webp'


def test_image_frontend_always_keeps_fallback_in_markup():
    js=(ROOT/'site/assets/app.js').read_text(encoding='utf-8')
    assert 'poster-real-image' in js
    assert 'poster-image-loaded' in js
    assert 'if(!img)return fallback' in js
    assert 'referrerpolicy="no-referrer"' in js


def test_enrich_existing_event_fetches_real_poster_and_remembers_check(monkeypatch):
    from datetime import datetime
    page='''<html><head><meta property="og:image" content="/media/expo-poster.jpg"></head>
    <body><h1>Выставка месяца</h1></body></html>'''.encode('utf-8')
    calls=[]
    def fake_read(self,url,session,base_host=None):
        calls.append(url)
        return page,'text/html; charset=UTF-8',url
    monkeypatch.setattr(monitor.PoliteClient,'read',fake_read)
    events=[{'id':'seed-1','title':'Выставка месяца','start_date':'2026-12-20',
             'url':'https://example.org/projects/one','editor_score':95,'origin':'editorial'}]
    result=core.enrich_missing_images(events,limit=2)
    assert result['attempts']==1 and result['found']==1
    assert events[0]['image_url']=='https://example.org/media/expo-poster.jpg'
    assert events[0]['image_checked_at']
    assert events[0]['image_status']=='found'
    again=core.enrich_missing_images(events,limit=2)
    assert again['attempts']==0
    assert len(calls)==1


def test_listing_enrichment_does_not_attach_generic_homepage_banner(monkeypatch):
    html='''<html><head><meta property="og:image" content="https://example.org/banners/home.jpg"></head>
      <body><h1>All Events</h1><article><a href="/events/one">Балет Зима</a>
        <img src="/posters/zima.jpg"></article></body></html>'''.encode('utf-8')
    def fake_read(self,url,session,base_host=None):
        return html,'text/html',url
    monkeypatch.setattr(monitor.PoliteClient,'read',fake_read)
    events=[{'id':'1','title':'Балет Зима','start_date':'2026-12-20','url':'https://example.org/afisha'},
            {'id':'2','title':'Другая постановка','start_date':'2026-12-19','url':'https://example.org/afisha'}]
    stats=core.enrich_missing_images(events,limit=1)
    assert stats['attempts']==1
    assert stats['found']==1
    assert events[0]['image_url']=='https://example.org/posters/zima.jpg'
    assert not events[1].get('image_url')
