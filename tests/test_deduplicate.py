"""Cross-source deduplication contract using the repeated events seen in the UI."""
from datetime import date
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pipeline'))

from update_events import merge_events, same_event

TODAY=date(2026,11,18)

def event(id,title='Сон в музее', start='2026-10-05',end='2027-01-25',venue='Неизвестно',city='Москва',url=None,image=None,origin='automatic'):
    return {
        'id':id,'title':title,'start_date':start,'end_date':end,'venue':venue,'city':city,
        'category':'Другое','url':url or f'https://example.org/events/{id}',
        'image_url':image or '', 'source_name':'Афиша.ru' if venue=='Неизвестно' else venue,
        'description':'', 'origin':origin,'discovered_at':'2026-11-18', 'editor_score':68
    }

def test_son_v_muzee_dedupes_unknown_vs_known_with_same_poster():
    image='https://cdn.example.org/img/mars-sleep.webp?w=480'
    a=event('a',image=image)
    b=event('b',venue='Центр «Марс»',image='https://cdn.example.org/img/mars-sleep.webp?w=1280')
    result=merge_events([],[],[a,b],[],TODAY)
    assert len(result)==1
    assert result[0]['venue']=='Центр «Марс»'
    assert result[0]['image_url']
    assert set([result[0]['id']]+result[0]['duplicate_ids'])=={'a','b'}

def test_aivazovsky_duplicates_keep_venue_and_poster():
    a=event('a',title='Айвазовский. Ожившие полотна',venue='Неизвестно',image='https://cdn.example.com/aiv.jpg')
    b=event('b',title='АЙВАЗОВСКИЙ — ОЖИВШИЕ ПОЛОТНА',venue='Пространство «Люмьер-холл»',image='https://cdn.example.com/aiv.jpg?size=large')
    result=merge_events([],[],[a,b],[],TODAY)
    assert len(result)==1
    assert result[0]['venue']=='Пространство «Люмьер-холл»'


def test_name_collision_different_known_venues_preserved():
    a=event('a',title='Щелкунчик',venue='Большой театр',image='https://example.org/nut.jpg')
    b=event('b',title='Щелкунчик',venue='Кремлёвский дворец',image='https://example.org/nut.jpg')
    assert len(merge_events([],[],[a,b],[],TODAY))==2


def test_city_mismatch_keeps_distinct_shows():
    a=event('a',venue='Неизвестно',image='https://example.org/pic.jpg')
    b=event('b',venue='Неизвестно',city='Санкт-Петербург',image='https://example.org/pic.jpg')
    assert not same_event(a,b)


def test_unrelated_dates_preserved():
    a=event('a',title='Лекция о театре',start='2026-12-04',end='2026-12-04',venue='Дом музыки')
    b=event('b',title='Лекция о театре',start='2027-01-10',end='2027-01-10',venue='Дом музыки')
    assert len(merge_events([],[],[a,b],[],TODAY))==2


def test_prefix_like_titles_not_equal():
    a=event('a',title='Спектакль Сон в музее',image='https://example.org/pic.jpg')
    b=event('b',title='Сон в музее',image='https://example.org/pic.jpg')
    assert len(merge_events([],[],[a,b],[],TODAY))==2


def test_editorial_remains_and_provenance_retained():
    a=event('seed-1',title='Айвазовский. Ожившие полотна',start='2026-12-01',end='2027-02-10',venue='Неизвестно',origin='editorial',url='https://official.org/afisha')
    b=event('auto-1',title='Айвазовский. Ожившие полотна',start='2026-12-01',end='2027-02-10',venue='Люмьер-холл',image='https://official.org/posted.jpg',url='https://official.org/exhibitions/aivazovsky')
    result=merge_events([a],[],[b],[],TODAY)
    assert len(result)==1
    assert result[0]['id']=='seed-1'
    assert 'auto-1' in result[0]['duplicate_ids']
    assert result[0]['venue']=='Люмьер-холл'
    assert result[0]['image_url']=='https://official.org/posted.jpg'
    assert 'https://official.org/exhibitions/aivazovsky' in result[0]['source_urls']


def test_repeated_daily_merge_idempotent():
    a=event('a',title='Айвазовский. Ожившие полотна',venue='Неизвестно',image='https://cdn.example.org/pic.jpg')
    b=event('b',title='Айвазовский. Ожившие полотна',venue='Люмьер-холл',image='https://cdn.example.org/pic.jpg')
    first=merge_events([],[],[a,b],[],TODAY)
    second=merge_events([],[*first],[],[],TODAY)
    assert len(second)==1
    assert set([second[0]['id']]+second[0].get('duplicate_ids',[]))=={'a','b'}


def test_same_title_with_known_different_venues_never_bridged_by_unknown():
    img='https://cdn.example.org/nut.jpg'
    first=event('first',title='Щелкунчик',venue='Большой театр',image=img)
    unknown=event('unknown',title='Щелкунчик',venue='Неизвестно',image=img)
    second=event('second',title='Щелкунчик',venue='Кремлёвский дворец',image=img)
    res=merge_events([],[],[first,unknown,second],[],TODAY)
    assert len(res)==2

def test_long_distinctive_title_with_unknown_venue_and_different_start_dates():
    a=event('a',title='Айвазовский. Ожившие полотна',start='2026-08-05',end='2027-02-18',venue='Неизвестно',image=None)
    b=event('b',title='Айвазовский. Ожившие полотна',start='2026-10-12',end='2027-01-17',venue='Люмьер-холл',image=None)
    res=merge_events([],[],[a,b],[],TODAY)
    assert len(res)==1
