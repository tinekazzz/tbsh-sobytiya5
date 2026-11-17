"""Verified starter records from official schedules, checked 2026-11-17.

This is an editorial seed, not the result of an automated collection.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EVENTS=[]

def item(title, date, cat, venue, url, desc, *, end=None, time=None, people=None, priority=76, featured=False, tag=None, city='Москва', source=None):
    EVENTS.append({
        'id': 'seed-'+str(len(EVENTS)+1).zfill(3), 'title':title,'start_date':date,'end_date':end,
        'time':time,'category':cat,'city':city,'venue':venue,'url':url,'description':desc,
        'source_name':source or venue,'people':people or [],'editor_score':priority,'featured':featured,
        'tag':tag or '', 'discovered_at':'2026-11-17', 'origin':'editorial',
        'verified_at':'2026-11-17', 'verification':'Проверено по официальной афише'
    })

live='https://www.live-arena.moscow/afisha/'
item('Маркиза де Помпадур. Триумф рококо','2026-12-01','Выставки','Пушкинский музей','https://www.pushkinmuseum.art/events/archive/2026/exhibitions/marquise_de_pompadour/index.php?lang=ru', 'Большая выставка об эпохе рококо и одной из самых влиятельных фигур французского искусства XVIII века.',end='2027-03-14',priority=97,featured=True,tag='ОТКРЫТИЕ')
item('Вещи, идолы, бананы. 20 000 лет скульптуры','2026-12-04','Выставки','ГЭС-2','https://ges-2.org/projects/things-idols-bananas', 'Почти 50 произведений разных эпох: от древних артефактов до современной скульптуры. Выставка к пятилетию Дома культуры.',end='2027-04-04',people=['Франческо Бонами','Маурицио Каттелан'],priority=99,featured=True,tag='ПРЕМЬЕРА')
item('Пять лет в городе','2026-12-01','Выставки','ГЭС-2','https://ges-2.org/projects/five-years-in-the-city','Проекты и истории городской программы «ГЭС-2» — выставка о сотрудничестве художников и жителей Москвы.',end='2026-12-08',priority=81,tag='СПЕЦПРОЕКТ')
item('Пятилетие Дома культуры «ГЭС-2»','2026-12-04','Фестивали','ГЭС-2','https://ges-2.org/projects/the-house-of-culture-turns-5-programme','Три дня выставок, перформансов, мастер-классов, кинопоказов, концертов и встреч.',end='2026-12-06',priority=97,featured=True,tag='ФЕСТИВАЛЬ')
item('Декабрьские вечера Святослава Рихтера','2026-12-01','Фестивали','Пушкинский музей','https://decemberfest.pushkinmuseum.art/','Музыкальный фестиваль в пространстве музея — программа 2026 года посвящена французской культуре и эпохе рококо.',end='2026-12-24',priority=93,featured=True,tag='ФЕСТИВАЛЬ')
item('Лев Бакст','2026-11-10','Выставки','Третьяковская галерея, Инженерный корпус','https://new.tretyakov.ru/tickets/exhibitions/','Выставка работ знаменитого художника театра и балета, создателя ярких сценических образов.',end='2027-04-18',priority=90,featured=True,tag='ИДЁТ')
item('Точка и линия','2026-06-12','Выставки','Третьяковская галерея','https://vcs.tretyakov.ru/exhibitions/','Геометрическая абстракция в российском искусстве XX–XXI века.',end='2027-03-28',priority=78,tag='ИДЁТ')
item('Супердискотека 90-х. Это фантастика!','2026-12-04','Концерты','Live Арена',live,'Масштабная танцевальная программа с музыкой девяностых и большой сценической постановкой.',time='20:00',priority=91,featured=True,tag='ШОУ',city='Московская область')
item('Гарик Сукачёв','2026-12-05','Концерты','Live Арена',live,'Большой концерт российского рок-музыканта.',time='20:00',people=['Гарик Сукачёв'],priority=88,city='Московская область')
item('Анжелика Варум и Леонид Агутин','2026-12-11','Концерты','Live Арена',live,'Совместная концертная программа двух артистов.',end='2026-12-12',time='20:00',people=['Анжелика Варум','Леонид Агутин'],priority=87,city='Московская область')
item('ЖАРА Новый год','2026-12-17','Шоу','Live Арена',live,'Большое музыкальное новогоднее шоу.',time='20:00',priority=82,tag='ПРЕМЬЕРА',city='Московская область')
item('Импровизаторы. 10 лет','2026-12-18','Шоу','Live Арена',live,'Юбилейное комедийное шоу команды «Импровизаторы».',time='20:00',priority=90,featured=True,tag='ЮБИЛЕЙ',city='Московская область')
item('Филипп Киркоров','2026-12-19','Концерты','Live Арена',live,'Два больших концертных вечера.',end='2026-12-20',time='19:00',people=['Филипп Киркоров'],priority=90,city='Московская область')
item('Гурам Амарян. «Базар»','2026-12-22','Стендап','Live Арена',live,'Большой сольный стендап-концерт.',time='20:00',people=['Гурам Амарян'],priority=80,city='Московская область')
item('Алиса — 35 лет Армии Алиса','2026-12-25','Концерты','Live Арена',live,'Большое юбилейное рок-шоу группы «Алиса».',time='20:00',people=['Константин Кинчев'],priority=89,city='Московская область')
item('Дискотека Авария','2026-12-27','Концерты','Live Арена',live,'Большое танцевальное шоу группы «Дискотека Авария».',time='19:00',priority=79,city='Московская область')
item('Кураторская лекция Анны Сулимовой','2026-12-11','Лекции','Пушкинский музей','https://www.pushkinmuseum.art/events/archive/2026/exhibitions/marquise_de_pompadour/1211/index.php','Разбор концепции и подготовки выставки «Маркиза де Помпадур. Триумф рококо».',time='19:00',people=['Анна Сулимова'],priority=74)
item('Отражения рококо','2026-12-24','Концерты','Пушкинский музей','https://decemberfest.pushkinmuseum.art/program/2026/24_12/index.php','Концерт в рамках Декабрьских вечеров: «Солисты Москвы» под руководством Юрия Башмета.',time='20:00',people=['Юрий Башмет'],priority=85)
item('Щелкунчик — ледовое шоу Евгения Плющенко','2027-01-02','Шоу','Live Арена',live,'Ледовое шоу-сказка Евгения Плющенко с балетом.',end='2027-01-04',people=['Евгений Плющенко'],priority=85,city='Московская область')

if __name__ == '__main__':
 path=ROOT/'site/data/editorial_events.json'
 path.write_text(json.dumps(EVENTS,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 print('Created',len(EVENTS),'verified editorial records')
