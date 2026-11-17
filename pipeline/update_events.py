#!/usr/bin/env python3
"""Daily event gathering for ТБШ СОБЫТИЯ.

Uses official sources from collectors.json. Only verifiable event dates are accepted:
JSON-LD schema.org/Event, HTML time tags, or a Russian written date adjacent to
an event-specific link. Robots directives are respected. No paid/closed API or
anti-bot bypass is attempted. Events from the reviewed editorial list remain.

Usage:
  python pipeline/update_events.py --offline   # build local preview from reviewed entries
  python pipeline/update_events.py             # collect on GitHub Actions

An attempted crawl is not proof of source coverage. Look at data/status.json.
"""
from __future__ import annotations
import argparse
import copy
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import hashlib
import json
import logging
from pathlib import Path
import re
import time
import sys
from urllib.parse import urljoin, urlparse, urldefrag, parse_qs
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'site/data'
LOG=logging.getLogger('radar')
TZ=ZoneInfo('Europe/Moscow')
HEADERS={'User-Agent':'KultRadarResearchBot/0.1 (+non-commercial editorial calendar; honors robots.txt)', 'Accept-Language':'ru-RU,ru;q=0.9,en;q=0.5'}
MONTHS={'января':1,'январь':1,'янв':1,'февраля':2,'февраль':2,'фев':2,'марта':3,'март':3,'мар':3,'апреля':4,'апрель':4,'апр':4,'мая':5,'май':5,'июня':6,'июнь':6,'июн':6,'июля':7,'июль':7,'июл':7,'августа':8,'август':8,'авг':8,'сентября':9,'сентябрь':9,'сен':9,'октября':10,'октябрь':10,'окт':10,'ноября':11,'ноябрь':11,'ноя':11,'декабря':12,'декабрь':12,'дек':12}
MONTH_RE='(?:'+'|'.join(sorted(map(re.escape,MONTHS),key=len,reverse=True))+')'
DATE_RE=re.compile(r'(?<!\d)(?P<day>\d{1,2})\s*(?P<month>'+MONTH_RE+r')\.?\s*(?P<year>20\d{2})?(?!\d)',re.I)
ISO_RE=re.compile(r'(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)')
RANGE_RE=re.compile(r'(\d{1,2})\s*[—–-]\s*(\d{1,2})\s*('+MONTH_RE+r')\.?\s*(20\d{2})?',re.I)
GENRE_PATTERNS={
 'Выставки':r'выставк|галер|экспозици|инсталляци|скульптур|ретроспектив',
 'Театр':r'спектакл|театральн|драма|постановк|опера|балет|мюзикл',
 'Шоу':r'ледов[оаые]|шоу|цирк|импровизатор|иллюзион|представлени',
 'Стендап':r'стендап|stand.?up|комик|юмор',
 'Фестивали':r'фестивал|форум|биеннале|ярмарк|преми[яи]',
 'Кино':r'кинопоказ|кинофест|премьер[аы] фильма|киносеанс',
 'Лекции':r'лекци|экскурси|публичн.*встреч|мастер.класс',
 'Концерты':r'концерт|оркестр|джаз|музык|песн|рок|гастрол',
}
LINK_HINTS=('event','exhibit','project','repertoire','perform','concert','show','spectacl','afisha','events','program','poster','tickets','выстав','спектак','концерт','проект','афиша')
SKIP_EXT=('.jpg','.png','.jpeg','.pdf','.gif','.svg','.zip','.mp4','.webp','.doc','.docx','.ics')


def load_json(path, default):
    try:return json.loads(Path(path).read_text('utf8'))
    except (FileNotFoundError, json.JSONDecodeError):return default

def write_json(path, data):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf8')
    tmp.replace(p)

def clean(s):
    return re.sub(r'\s+',' ',str(s or '')).strip()

def slug(s):
    return re.sub(r'[^а-яёa-z0-9]+','',clean(s).lower())

def target_window(now):
    first=date(now.year,now.month,1)
    y=first.year+(first.month==12);m=first.month%12+1
    next_first=date(y,m,1)
    y2=y+(m>=10);m2=(m+3-1)%12+1
    # cover next three calendar months
    after=date(y2,m2,1)
    return next_first,after

def parse_iso(raw):
    if not raw:return None
    x=clean(raw)
    try:return date.fromisoformat(x[:10]).isoformat()
    except ValueError:return None

def russian_dates(text, context_date=None):
    context_date=context_date or datetime.now(TZ).date()
    found=[]
    compact=clean(text)[:900]
    for m in DATE_RE.finditer(compact):
        mm=MONTHS[m.group('month').lower()]
        yyyy=int(m.group('year') or context_date.year)
        if not m.group('year') and mm < context_date.month-2:
            yyyy+=1
        try:found.append(date(yyyy,mm,int(m.group('day'))))
        except ValueError:continue
    if found and len(found)==1:
        rng=RANGE_RE.search(compact)
        if rng:
            try:
                first=date(int(rng.group(4) or found[0].year),MONTHS[rng.group(3).lower()],int(rng.group(1)))
                second=date(int(rng.group(4) or found[0].year),MONTHS[rng.group(3).lower()],int(rng.group(2)))
                return [first.isoformat(),second.isoformat()]
            except ValueError:pass
    return [d.isoformat() for d in found[:2]]

def in_scope(start, end, today):
    begin,last=target_window(today)
    try:
        st=date.fromisoformat(start[:10]);en=date.fromisoformat((end or start)[:10])
        return en >= begin and st < last and en >= st
    except (ValueError,TypeError):return False

def classify(s, default='Другое'):
    text=clean(s).lower()
    # Genre based on a title, with deterministic order.
    for genre,pattern in GENRE_PATTERNS.items():
        if re.search(pattern,text,re.I):return genre
    return default

def first_meta(soup, selectors):
    for q in selectors:
        tag=soup.select_one(q)
        if tag:
            content=tag.get('content') or tag.get('datetime') or tag.get_text(' ',strip=True)
            if clean(content):return clean(content)
    return ''

def normalize_image_url(raw, base=''):
    raw=clean(raw)
    if not raw:return ''
    if raw.startswith('//'):raw='https:'+raw
    elif base and not raw.startswith('http'):raw=urljoin(base,raw)
    try:
        parsed=urlparse(raw)
    except Exception:
        return ''
    if parsed.scheme!='https':return ''
    if parsed.path.lower().endswith(('.svg', '.ico')):
        return ''
    return raw

def image_from_tag(tag, base=''):
    if not tag:return ''
    values=[]
    for attr in ('content','src','data-src','data-original','data-lazy-src','href'):
        if tag.get(attr):values.append(tag.get(attr))
    srcset=tag.get('srcset') or tag.get('data-srcset') or ''
    if srcset:
        first=srcset.split(',')[0].strip().split(' ')[0]
        if first:values.append(first)
    for raw in values:
        normalized=normalize_image_url(raw,base)
        if normalized:return normalized
    return ''

def extract_image_url(soup, base=''):
    selectors=[
        'meta[property="og:image"]',
        'meta[name="og:image"]',
        'meta[property="og:image:url"]',
        'meta[name="twitter:image"]',
        'meta[property="twitter:image"]',
        'meta[itemprop="image"]',
        'link[rel="image_src"]',
    ]
    for sel in selectors:
        tag=soup.select_one(sel)
        img=image_from_tag(tag,base)
        if img:return img
    for script in soup.select('script[type="application/ld+json"]'):
        try:data=json.loads(script.string or script.get_text())
        except Exception:continue
        stack=[data]
        while stack:
            node=stack.pop()
            if isinstance(node,dict):
                image=node.get('image')
                if isinstance(image,str):
                    img=normalize_image_url(image,base)
                    if img:return img
                elif isinstance(image,list):
                    for item in image:
                        if isinstance(item,str):
                            img=normalize_image_url(item,base)
                            if img:return img
                        elif isinstance(item,dict):
                            img=normalize_image_url(item.get('url') or item.get('@id') or '',base)
                            if img:return img
                elif isinstance(image,dict):
                    img=normalize_image_url(image.get('url') or image.get('@id') or '',base)
                    if img:return img
                stack.extend(v for v in node.values() if isinstance(v,(dict,list)))
            elif isinstance(node,list):
                stack.extend(node)
    content=soup.select_one('article, main, .content, .post, .event, .event-card, .afisha-card, .entry-content, .page-content') or soup
    for sel in ('img[src]','img[data-src]','source[srcset]'):
        for tag in content.select(sel)[:8]:
            img=image_from_tag(tag,base)
            if img:return img
    return ''

def fragment_image_url(node, base=''):
    if not node:return ''
    for sel in ('img[src]','img[data-src]','source[srcset]'):
        tag=node.select_one(sel) if hasattr(node,'select_one') else None
        img=image_from_tag(tag,base)
        if img:return img
    style=(node.get('style') or '') if hasattr(node,'get') else ''
    m=re.search(r"url\(['\"]?(.*?)['\"]?\)", style)
    if m:
        img=normalize_image_url(m.group(1),base)
        if img:return img
    return ''

def get_people(event, registry):
    corpus=clean((event.get('title') or '')+' '+(event.get('description') or '')).casefold()
    matched=[]
    for person in registry:
        # Full name or distinctive artist stage name; bare surnames can be ambiguous.
        aliases=[person['name']]+[x.strip() for x in person.get('aliases','').split(';')]
        for alias in aliases:
            alias=alias.strip()
            if len(alias)<7:continue
            if re.search(r'(?<![а-яёa-z0-9])'+re.escape(alias.casefold())+r'(?![а-яёa-z0-9])',corpus):
                matched.append(person['name']);break
        if len(matched)==6:break
    return matched

def event_from_ld(node, base, source, today):
    if not isinstance(node,dict):return None
    kinds=node.get('@type',[])
    kinds=[kinds] if isinstance(kinds,str) else kinds
    if not any('event' in str(k).lower() for k in kinds):return None
    status=str(node.get('eventStatus') or '').lower()
    if 'cancel' in status or 'postpon' in status:return None
    title=clean(node.get('name'))
    start=parse_iso(node.get('startDate'))
    end=parse_iso(node.get('endDate')) or start
    if not title or not start or not in_scope(start,end,today):return None
    location=node.get('location') or {}
    if isinstance(location,list):location=location[0] if location else {}
    venue=clean(location.get('name') if isinstance(location,dict) else location) or source['name']
    desc=BeautifulSoup(str(node.get('description') or ''),'html.parser').get_text(' ',strip=True)
    uri=clean(node.get('url') or base)
    if not uri.startswith('http'):uri=urljoin(base,uri)
    image_url=''
    image=node.get('image')
    if isinstance(image,str): image_url=normalize_image_url(image,uri)
    elif isinstance(image,list):
        for item in image:
            if isinstance(item,str) and normalize_image_url(item,uri):
                image_url=normalize_image_url(item,uri); break
            if isinstance(item,dict):
                cand=normalize_image_url(item.get('url') or item.get('@id') or '',uri)
                if cand: image_url=cand; break
    elif isinstance(image,dict):
        image_url=normalize_image_url(image.get('url') or image.get('@id') or '',uri)
    if not image_url:image_url=extract_image_url(BeautifulSoup(str(node.get('description') or ''),'html.parser'),uri)
    ev=build_event(title,start,end,desc[:300],venue,uri,source,image_url=image_url)
    if isinstance(location,dict):
        address=location.get('address') or {}
        locality=address.get('addressLocality') if isinstance(address,dict) else None
        if isinstance(locality,str) and 2<=len(locality)<60:
            ev['city']=clean(locality)
    return ev

def jsonld_events(soup, page_url, source, today):
    found=[]
    def walk(val):
        if isinstance(val,dict):
            one=event_from_ld(val,page_url,source,today)
            if one:found.append(one)
            for x in val.values():
                if isinstance(x,(dict,list)):walk(x)
        elif isinstance(val,list):
            for x in val:walk(x)
    for script in soup.select('script[type="application/ld+json"]'):
        try:walk(json.loads(script.string or script.get_text()))
        except (ValueError,TypeError):continue
    return found

def build_event(title,start,end,desc,venue,url,source,image_url=''):
    title=clean(title)
    source_name=source['name']
    dt=datetime.now(TZ).date().isoformat()
    image_url=normalize_image_url(image_url,url)
    ev={
        'id':'auto-'+hashlib.sha256((url+'|'+title+'|'+start).encode()).hexdigest()[:14],
        'title':title[:200], 'start_date':start,'end_date':end,
        'time':None, 'category':classify(title+' '+desc[:100],source.get('category','Другое')),
        'venue':clean(venue)[:130],'city':source.get('city','Москва'),
        'url':url,'description':clean(desc)[:320], 'source_name':source_name,
        'image_url':image_url,
        'source_id':source['id'], 'people':[], 'editor_score':68,'featured':False,
        'tag':'','discovered_at':dt,'origin':'automatic',
        'verified_at':dt,'verification':'Собрано автоматически; уточните детали у организатора'
    }
    return ev

def page_event(soup,url,source,today):
    ld=jsonld_events(soup,url,source,today)
    if ld:return ld
    # Only event-specific pages qualify for fallback date extraction.
    parsed=urlparse(url)
    suffix=parsed.path.rstrip('/').split('/')[-1].lower()
    if suffix in ('','afisha','events','repertoire','exhibitions','calendar','program') or (suffix=='index.php' and len(parsed.path.strip('/').split('/'))<=3):
        return []
    h1=soup.select_one('h1')
    title=clean(h1.get_text(' ',strip=True)) if h1 else ''
    if not 7<=len(title)<=160:return []
    if title.lower() in ('афиша','мероприятия','выставки','концерты','календарь','билеты'):return []
    # Prefer nearby date markers to a footer-wide text scan.
    elements=soup.select('time[datetime], [itemprop="startDate"], [itemprop="endDate"], .event-date, .date, [class*="event-date"], [class*="eventDate"], [class*="schedule"]')[:15]
    fragments=[]
    for el in elements:
        x=el.get('datetime') or el.get('content') or el.get_text(' ',strip=True)
        if x:fragments.append(clean(x))
    if h1.parent:fragments.append(clean(h1.parent.get_text(' ',strip=True))[:250])
    # Date regex from the first 900 chars after headline; never treat a page's footer as event.
    for parent in list(h1.parents)[:2]:
        if parent:fragments.append(clean(parent.get_text(' ',strip=True))[:750])
    candidates=[]
    for frag in fragments:
        iso=ISO_RE.findall(frag)
        dates=iso[:2] or russian_dates(frag,today)
        if dates and in_scope(dates[0], dates[-1],today):
            candidates=dates;break
    if not candidates:return []
    desc=first_meta(soup,['meta[name="description"]','meta[property="og:description"]'])
    venue=first_meta(soup,['meta[property="event:location"]']) or source['name']
    image_url=extract_image_url(soup,url)
    return [build_event(title,candidates[0],candidates[-1],desc,venue,url,source,image_url=image_url)]

def listing_events(soup,base,source,today):
    """Conservative listing extraction: event-specific anchor and nearby date.

    This is intentionally not a generic scrape of every date on a page.
    """
    found=[]
    dom=urlparse(base).netloc.removeprefix('www.')
    for anchor in soup.select('a[href]'):
        href=urljoin(base,anchor.get('href',''))
        parsed=urlparse(href)
        if parsed.netloc.removeprefix('www.')!=dom:continue
        if parsed.path.lower().endswith(SKIP_EXT):continue
        if href.rstrip('/')==base.rstrip('/'):continue
        title=clean(anchor.get_text(' ',strip=True))
        if not 9<=len(title)<=125:continue
        if title.lower() in ('купить билет','купить билеты','подробнее','узнать больше','читать далее','открыть','билеты'):continue
        if re.search(r'^(\d+|все мероприятия|афиша|смотреть|выставки|контакты|о нас)$',title.lower()):continue
        ctx=anchor.parent
        if ctx:ctx=ctx.parent or ctx
        snippet=clean(ctx.get_text(' ',strip=True))[:450] if ctx else title
        dates=russian_dates(snippet,today)
        if not dates or not in_scope(dates[0],dates[-1],today):continue
        # Exclude links that evidently label a category, not the event.
        if not any(token in parsed.path.lower() for token in LINK_HINTS) and len(snippet)>300:continue
        image_url=fragment_image_url(ctx or anchor,base)
        found.append(build_event(title,dates[0],dates[-1],'',source['name'],href,source,image_url=image_url))
    return found

def discover_links(soup,base,max_n):
    host=urlparse(base).netloc.removeprefix('www.')
    choices=[]
    seen=set()
    for a in soup.select('a[href]'):
        raw=a.get('href','')
        url=urldefrag(urljoin(base,raw)).url
        parsed=urlparse(url)
        if parsed.scheme not in ('http','https'):continue
        if parsed.netloc.removeprefix('www.')!=host:continue
        if parsed.path.lower().endswith(SKIP_EXT) or url in seen:continue
        if parsed.path.rstrip('/')==urlparse(base).path.rstrip('/'):continue
        seen.add(url)
        label=clean(a.get_text(' ',strip=True)).lower()
        path=parsed.path.lower()
        pts=3*any(s in path for s in LINK_HINTS) + 2*any(s in label for s in ('выставк','спектакл','концерт','премьера','фестиваль','шоу','программа'))
        pts+=bool(re.search(r'20\d{2}|/\d{2}[-_/]\d{2}',path))
        if pts>=3:choices.append((pts,url))
    choices.sort(key=lambda x:x[0],reverse=True)
    return [url for _,url in choices[:max_n]]

class Fetcher:
    def __init__(self, session, sleep_seconds=0.45):
        self.session=session;self.sleep=sleep_seconds;self.last={};self.robots={};self.pages=0

    def allowed(self,url):
        parsed=urlparse(url)
        if parsed.scheme!='https':return False
        host=parsed.netloc
        if host not in self.robots:
            rp=RobotFileParser();rp.set_url(f'https://{host}/robots.txt')
            try:
                r=self.session.get(rp.url,timeout=9)
                if r.ok:rp.parse(r.text.splitlines())
                elif r.status_code in (401,403):rp.disallow_all=True
                else:rp.parse([])
            except requests.RequestException:
                # Do not override rules: remember availability uncertainty.
                LOG.warning('robots.txt unavailable on %s',host)
                self.robots[host]=None
                return False
            self.robots[host]=rp
        rp=self.robots[host]
        return rp is not None and rp.can_fetch(HEADERS['User-Agent'],url)

    def fetch(self,url):
        if not self.allowed(url):
            raise PermissionError('robots.txt disallows or unavailable')
        host=urlparse(url).netloc
        now=time.monotonic()
        wait=self.sleep-(now-self.last.get(host,0))
        if wait>0:time.sleep(wait)
        self.last[host]=time.monotonic()
        r=self.session.get(url,timeout=15,headers=HEADERS,allow_redirects=True)
        r.raise_for_status()
        if 'text/html' not in r.headers.get('Content-Type','text/html'):
            raise ValueError('Non-HTML response')
        if len(r.content)>5_000_000:raise ValueError('Document exceeds max size')
        self.pages+=1
        return BeautifulSoup(r.content,'html.parser')

def merge_events(editorial,existing,found,people,today):
    combined={};keys={}
    for ev in list(editorial)+list(existing)+list(found):
        ev=copy.deepcopy(ev)
        start=ev.get('start_date');end=ev.get('end_date') or start
        if not in_scope(start,end,today):continue
        title=clean(ev.get('title'));url=ev.get('url')
        if not title or not url or not str(url).startswith('https://'):continue
        ev['title']=title
        ev['end_date']=end
        ev['people']=list(dict.fromkeys((ev.get('people') or [])+get_people(ev,people)))[:8]
        ev['category']=ev.get('category') or classify(title)
        ev['source_name']=ev.get('source_name') or 'Не указан'
        ev['image_url']=normalize_image_url(ev.get('image_url') or '',ev.get('url') or '')
        ev['id']=ev.get('id') or 'event-'+hashlib.sha256((title+start).encode()).hexdigest()[:12]
        key=slug(title)+'|'+start[:7]+'|'+slug(ev.get('venue'))
        if key in keys:
            prev=combined[keys[key]]
            if prev.get('origin')=='editorial' and ev.get('origin')!='editorial':
                prev['verified_at']=ev.get('verified_at',prev.get('verified_at'))
                continue
            if ev.get('origin')=='editorial' or len(ev.get('description',''))>len(prev.get('description','')):
                ev['discovered_at']=prev.get('discovered_at',ev.get('discovered_at'))
                del combined[prev['id']]
                combined[ev['id']]=ev
                keys[key]=ev['id']
        else:
            combined[ev['id']]=ev;keys[key]=ev['id']
    return sorted(combined.values(),key=lambda e:(e['start_date'],-e.get('editor_score',50),e['title']))

def enrich_missing_images(events, limit=24):
    pending=[e for e in events if not e.get('image_url') and str(e.get('url','')).startswith('https://')]
    if not pending or limit<=0:return events
    session=requests.Session()
    session.headers.update(HEADERS)
    checked=0
    cache={}
    for ev in pending:
        url=ev.get('url')
        if url in cache:
            ev['image_url']=cache[url]
            continue
        if checked>=limit:break
        checked+=1
        try:
            r=session.get(url,timeout=12,allow_redirects=True)
            r.raise_for_status()
            if 'html' not in r.headers.get('Content-Type','text/html').lower():
                cache[url]=''; continue
            soup=BeautifulSoup(r.content,'html.parser')
            cache[url]=extract_image_url(soup,r.url)
            ev['image_url']=cache[url]
        except requests.RequestException:
            cache[url]=''
    session.close()
    return events

def run(offline=False, max_sources=0, workers=8):
    """Update local catalog and write an honest per-source coverage report.

    The full registry is attempted by default; reachability and event extraction
    are counted separately. A 200 response with no dated events is not success
    at finding events.
    """
    from monitor_registry import all_collectors, scan_registry
    now=datetime.now(TZ);today=now.date()
    editorial=load_json(DATA/'editorial_events.json',[])
    past=load_json(DATA/'events.json',{})
    existing=past.get('events',[])
    previous_ids={e.get('id') for e in existing}
    people=load_json(DATA/'people.json',[])
    registry=load_json(ROOT/'registry/full_registry.json',{})
    base_sources=registry.get('sources',[])
    custom=load_json(ROOT/'pipeline/collectors.json',[])
    config=all_collectors(base_sources,custom)
    found=[];logs=[]
    if not offline:
        found,logs=scan_registry(config,core=sys.modules[__name__],today=today,
                                 workers=workers,max_sources=max_sources)
        for e in found:e['people']=get_people(e,people)
    events=merge_events(editorial,existing,found,people,today)
    if not offline:
        events=enrich_missing_images(events,limit=36)
    seen_status={key:sum(x.get('status')==key for x in logs)
                 for key in ('found','no_events','needs_javascript','blocked','error','invalid_url','unsupported')}
    reached=seen_status['found']+seen_status['no_events']+seen_status['needs_javascript']
    new_events=sum(e.get('origin')=='automatic' and e.get('id') not in previous_ids for e in events)
    status={
        'updated_at':now.isoformat(timespec='seconds'),
        'mode':'offline_preview' if offline else 'daily_collection',
        'collection_strategy':'registry_full_sweep',
        'daily_schedule':'06:20 Europe/Moscow (GitHub Actions, возможна задержка)',
        'sources_in_registry':len(base_sources),
        'tracked_people':len(people),
        'configured_collectors':len(config),
        'sources_checked_today':len(logs),
        'sources_reached_today':reached,
        'sources_with_events_today':seen_status['found'],
        'sources_no_dated_events_today':seen_status['no_events'],
        'sources_needing_javascript_today':seen_status['needs_javascript'],
        'sources_blocked_today':seen_status['blocked'],
        'sources_failed_today':seen_status['error']+seen_status['invalid_url']+seen_status['unsupported'],
        'events_extracted_today':len(found),
        'new_events_added_today':new_events,
        'events_with_people_today':sum(bool(e.get('people')) for e in found),
        'events_in_catalog':len(events),
        'source_status_counts':seen_status,
        'source_log':logs,
        'note':('Попытка проверки всего реестра: HTTP-доступ не гарантирует наличие событий; '
                'учитываются только записи с датами. Часть сайтов требует отдельных интеграций.'
                if not offline else
                'Локальная проверка: сеть не использовалась; данные афиши сохранены из предыдущего запуска.')
    }
    bundle={'generated_at':now.isoformat(timespec='seconds'),'mode':status['mode'],'events':events}
    write_json(DATA/'events.json',bundle)
    write_json(DATA/'status.json',status)
    LOG.info('Sources attempted: %s/%s, reached: %s, dated events: %s; catalog: %s',
             len(logs),len(config),reached,len(found),len(events))
    return status

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--offline',action='store_true',help='Do not make internet requests; compose reviewed starter dataset')
    parser.add_argument('--verbose',action='store_true')
    parser.add_argument('--max-sources',type=int,default=0,help='Only the first N registered sites (diagnostics)')
    parser.add_argument('--workers',type=int,default=8,help='Concurrent source checks, default 8')
    args=parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,format='%(levelname)s %(message)s')
    status=run(args.offline,max_sources=args.max_sources,workers=args.workers)
    print(json.dumps({k:v for k,v in status.items() if k!='source_log'},ensure_ascii=False,indent=2))
