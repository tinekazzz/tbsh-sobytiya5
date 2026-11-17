from datetime import date
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'pipeline'))
from bs4 import BeautifulSoup
from update_events import russian_dates, target_window, in_scope, jsonld_events, merge_events

SOURCE={'id':'SRC-1','name':'Тестовый театр','city':'Москва','category':'Театр'}
TODAY=date(2026,11,17)

def test_russian_dates():
    assert russian_dates('Премьера — 18 декабря 2026 года',TODAY)==['2026-12-18']
    assert russian_dates('Выставка 4 дек 2026 — 4 апр 2027',TODAY)==['2026-12-04','2027-04-04']
    assert russian_dates('Программа 1–8 дек 2026',TODAY)==['2026-12-01','2026-12-08']

def test_month_window_and_ongoing():
    assert target_window(TODAY)==(date(2026,12,1),date(2027,3,1))
    assert in_scope('2026-11-10','2027-03-10',TODAY)
    assert not in_scope('2026-10-01','2026-11-15',TODAY)
    assert not in_scope('2027-08-01','2027-08-02',TODAY)

def test_extract_jsonld():
    html='''<html><script type="application/ld+json">{
      "@context":"https://schema.org","@type":"MusicEvent",
      "name":"Концерт тестового артиста", "startDate":"2026-12-21T19:00:00+03:00",
      "location":{"@type":"Place","name":"Концертный зал"},
      "description":"Большая программа", "url":"https://example.org/events/test"}
      </script></html>'''
    soup=BeautifulSoup(html,'html.parser')
    events=jsonld_events(soup,'https://example.org/',SOURCE,TODAY)
    assert len(events)==1
    assert events[0]['title']=='Концерт тестового артиста'
    assert events[0]['start_date']=='2026-12-21'
    assert events[0]['venue']=='Концертный зал'

def test_ignore_undated():
    soup=BeautifulSoup('<script type="application/ld+json">{"@type":"Event","name":"без даты"}</script>','html.parser')
    assert jsonld_events(soup,'https://example.org/',SOURCE,TODAY)==[]

def test_editorial_dedupe():
    e={'id':'seed-1','title':'Премьера','start_date':'2026-12-20','end_date':'2026-12-20','venue':'Сцена','url':'https://official.org/1','origin':'editorial','description':'Проверено','category':'Театр'}
    a={**e,'id':'auto-1','url':'https://official.org/2','origin':'automatic'}
    result=merge_events([e],[],[a],[],TODAY)
    assert len(result)==1
    assert result[0]['id']=='seed-1'
