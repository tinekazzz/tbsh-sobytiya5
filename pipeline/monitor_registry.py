"""Bounded, respectful monitoring across the complete TBSH source registry.

Every registry entry receives a separate diagnostic. A successful HTTP request is
NOT a claim that usable events have been extracted. Event titles and dates must
be supported by calendar data or event markup; publishing an editorial/media
article merely because it has a publication date is prohibited.

This module uses only public HTTPS pages, robots.txt and advertised public
feeds/calendars. It never attempts login, access-token bypass or CAPTCHA solving.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
import json
import logging
import re
import threading
import time
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

LOG = logging.getLogger('radar.monitor')
USER_AGENT = 'TBSHEventsBot/1.0 (+public cultural-event listings; respects robots.txt)'
HEADERS = {'User-Agent': USER_AGENT, 'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.6'}
EVENT_TERMS = re.compile(r'афиш|событи|концерт|спектакл|выставк|фестивал|балет|опера|премьер|стендап|stand.?up|шоу|цирк|мюзикл|кинопоказ|лекци|экскурси|гастрол|оркестр|ярмарк|перформанс', re.I)
FUTURE_LINK_TERMS = ('afisha','event','exhibit','performance','spectacl','concert','poster','repertoire','show','premier','events','program','calendar','выстав','спектак','концерт','афиша','событи','театр')
BAD_EXTENSIONS = ('.pdf','.png','.jpg','.jpeg','.gif','.webp','.svg','.mp3','.mp4','.zip','.doc','.docx','.css','.js')
KNOWN_SPA_MARKERS = ('__NEXT_DATA__','id="__nuxt"','id="root"','id="app"')
MAX_BYTES = 2_500_000


def hostname(url):
    return (urlparse(url).hostname or '').lower().removeprefix('www.')


def valid_https(url):
    p = urlparse(str(url))
    return p.scheme == 'https' and bool(p.hostname) and not p.username and not p.password and p.port in (None, 443)


def source_city(source):
    # No location inference from arbitrary national websites.
    area=(source.get('region') or '').casefold()
    if 'московская область' in area:return 'Московская область'
    if 'санкт-петербург' in area or 'петербург' in area:return 'Санкт-Петербург'
    if 'москва' in area:return 'Москва'
    if 'казань' in area:return 'Казань'
    if 'нижний новгород' in area:return 'Нижний Новгород'
    if 'екатеринбург' in area:return 'Екатеринбург'
    if 'сочи' in area:return 'Сочи'
    return 'Россия'


def collector_category(source):
    x=source.get('category','')
    if 'музе' in x.lower() or 'искусств' in x.lower():return 'Выставки'
    if 'театр' in x.lower():return 'Театр'
    if 'опера' in x.lower() or 'балет' in x.lower():return 'Театр'
    if 'концерт' in x.lower() or 'клуб' in x.lower():return 'Концерты'
    if 'цирк' in x.lower() or 'шоу' in x.lower():return 'Шоу'
    if 'фестивал' in x.lower():return 'Фестивали'
    if 'кино' in x.lower():return 'Кино'
    return 'Другое'


def all_collectors(registry, custom):
    """Merge all 241 registered sites with specific validated seed settings."""
    overrides={x['id']:x for x in custom}
    seen=set();merged=[]
    for source in registry:
        srcid=source['source_id']
        if srcid in seen:continue
        seen.add(srcid)
        priority=source.get('priority','C')
        kind=source.get('kind','')
        editorial='медиа' in kind.casefold() or 'медиа' in source.get('category','').casefold()
        # Two-level strategy: check all 241 home pages, but cap detail traffic.
        # A/B/C use 3/2/1 links; media require event-structured evidence.
        item={
            'id':srcid,'name':source['name'],'url':source.get('url',''),
            'city':source_city(source),'category':collector_category(source),
            'priority':priority,'kind':kind,'editorial_media':editorial,
            'mode':'hybrid','enabled':True,'max_details':{'A':3,'B':2,'C':1}.get(priority,1),
        }
        override=overrides.get(srcid)
        if override:
            # Preserve manually selected official afisha URLs, bounded by the
            # global per-site page limit to avoid overloading a publisher.
            item.update({k:v for k,v in override.items() if k not in ('id','name')})
            item['max_details']=min(6,int(item.get('max_details',3)))
        merged.append(item)
    return merged


class RobotsDenied(PermissionError):pass
class SourceError(Exception):pass


class PoliteClient:
    """Share robots/cache and a per-host rate limiter among worker threads."""
    def __init__(self, delay=1.0):
        self.delay=float(delay)
        self.lock=threading.RLock()
        self.robots={}
        self.host_locks={}
        self.next_allowed={}

    def _host_lock(self,host):
        with self.lock:
            return self.host_locks.setdefault(host,threading.Lock())

    def _robots(self,host,session):
        with self._host_lock(host):
            if host in self.robots:return self.robots[host]
            url='https://'+host+'/robots.txt'
            try:
                # robots.txt redirects are common (www -> non-www). Follow
                # only HTTPS on the same normalized hostname; apply the
                # resulting policy to the original source host.
                for _ in range(3):
                    r=session.get(url,headers=HEADERS,timeout=(3,6),allow_redirects=False)
                    if r.status_code not in (301,302,303,307,308):break
                    target=urljoin(url,r.headers.get('Location',''))
                    if not valid_https(target) or hostname(target)!=hostname(url):break
                    url=target
                if r.status_code==200:
                    if '<html' in r.text[:250].lower() or '<!doctype' in r.text[:250].lower():
                        self.robots[host]=(None,'robots.txt вернул HTML вместо правил')
                        return self.robots[host]
                    policy=RobotFileParser(url)
                    policy.parse(r.text.splitlines())
                elif r.status_code in (404,410):
                    policy=RobotFileParser(url)
                    policy.parse([])
                elif r.status_code in (401,403):
                    self.robots[host]=(None,'robots.txt запрещает доступ')
                    return self.robots[host]
                else:
                    self.robots[host]=(None,'robots.txt ответил HTTP '+str(r.status_code))
                    return self.robots[host]
            except requests.RequestException as ex:
                self.robots[host]=(None,'robots.txt недоступен: '+type(ex).__name__)
                return self.robots[host]
            self.robots[host]=(policy,'')
            return self.robots[host]

    def _throttle(self,host):
        # Serialize requests to the same site, even if it occurs in the
        # registry more than once. This is stricter than a per-thread delay.
        with self._host_lock(host):
            delay=self.next_allowed.get(host,0)-time.monotonic()
            if delay>0:time.sleep(delay)
            self.next_allowed[host]=time.monotonic()+self.delay

    def read(self,url,session,base_host=None):
        if not valid_https(url):raise SourceError('Нужен публичный HTTPS URL')
        origin=base_host or hostname(url)
        if hostname(url)!=origin:raise SourceError('Ссылка ведёт на другой домен')
        for _ in range(3):
            host=urlparse(url).netloc.lower()
            policy,error=self._robots(host,session)
            if policy is None or not policy.can_fetch(USER_AGENT,url):
                raise RobotsDenied(error or 'robots.txt запрещает этот адрес')
            self._throttle(host)
            try:
                r=session.get(url,headers=HEADERS,timeout=(4,10),allow_redirects=False,stream=True)
            except requests.RequestException as ex:
                raise SourceError(type(ex).__name__+': '+str(ex)[:100]) from ex
            try:
                if r.status_code in (301,302,303,307,308):
                    nxt=urljoin(url,r.headers.get('Location',''))
                    if not valid_https(nxt) or hostname(nxt)!=origin:
                        raise SourceError('Перенаправление на другой домен или небезопасный URL')
                    url=nxt
                    continue
                if r.status_code in (401,403,429):raise RobotsDenied('HTTP '+str(r.status_code))
                r.raise_for_status()
                length=int(r.headers.get('Content-Length') or '0')
                if length>MAX_BYTES:raise SourceError('Слишком большой ответ')
                chunks=[];total=0
                for chunk in r.iter_content(chunk_size=65536):
                    total+=len(chunk)
                    if total>MAX_BYTES:raise SourceError('Слишком большой ответ')
                    chunks.append(chunk)
                return b''.join(chunks),r.headers.get('Content-Type',''),url
            except requests.HTTPError as ex:
                raise SourceError('HTTP '+str(r.status_code)) from ex
            finally:r.close()
        raise SourceError('Слишком много перенаправлений')


def parse_ics(raw,base,source,core,today):
    """Tiny strict parser for public VEVENT calendar records (no package needed)."""
    text=raw.decode('utf-8-sig',errors='replace')
    if 'BEGIN:VCALENDAR' not in text[:500]:return []
    unfolded=re.sub(r'\r?\n[ \t]','',text)
    def field(row,prefix):
        return row.split(':',1)[1].strip() if row.upper().startswith(prefix) and ':' in row else None
    found=[]
    for match in re.finditer(r'BEGIN:VEVENT(.*?)END:VEVENT',unfolded,re.S|re.I):
        vals={};cancelled=False
        for line in match.group(1).splitlines():
            left,sep,right=line.partition(':')
            if not sep:continue
            key=left.split(';',1)[0].upper()
            if key in ('SUMMARY','DTSTART','DTEND','LOCATION','DESCRIPTION','URL','STATUS'):
                vals[key]=right.strip().replace('\\n',' ').replace('\\,',',')
        if vals.get('STATUS','').upper()=='CANCELLED':continue
        start=vals.get('DTSTART','')[:8]
        end=vals.get('DTEND','')[:8] or start
        if not re.fullmatch(r'20\d{6}',start) or not re.fullmatch(r'20\d{6}',end):continue
        try:
            first=date(int(start[:4]),int(start[4:6]),int(start[6:8])).isoformat()
            last=date(int(end[:4]),int(end[4:6]),int(end[6:8])).isoformat()
        except ValueError:continue
        # iCalendar DTEND for all-day events is exclusive. Do not guess for
        # timed events; keep end date as published.
        if not core.in_scope(first,last,today):continue
        title=core.clean(vals.get('SUMMARY'))
        if len(title)<6:continue
        uri=vals.get('URL') or base
        uri=urljoin(base,uri)
        if not valid_https(uri):uri=base
        ev=core.build_event(title,first,last,vals.get('DESCRIPTION','')[:320],vals.get('LOCATION') or source['name'],uri,source)
        ev['extraction_method']='calendar_ics'
        found.append(ev)
    return found


def parse_microdata(soup,page_url,source,core,today):
    events=[]
    for item in soup.select('[itemscope][itemtype*="schema.org/"]')[:100]:
        item_type=(item.get('itemtype') or '').rstrip('/').split('/')[-1]
        if not item_type.lower().endswith('event'):continue
        def prop(name):
            t=item.select_one('[itemprop="'+name+'"]')
            return (t.get('content') or t.get('datetime') or t.get('href') or t.get_text(' ',strip=True)) if t else ''
        name=core.clean(prop('name'))
        start=core.parse_iso(prop('startDate'))
        end=core.parse_iso(prop('endDate')) or start
        if not start or not name or not core.in_scope(start,end,today):continue
        url=urljoin(page_url,prop('url') or page_url)
        if not valid_https(url):continue
        ev=core.build_event(name,start,end,prop('description'),prop('location') or source['name'],url,source,image_url=prop('image'))
        ev['extraction_method']='microdata'
        events.append(ev)
    return events


def extract_listing_anchors(soup,page_url,source,core,today):
    """Use only date-bearing event card links, not generic news or footer text."""
    if source.get('editorial_media'):return []
    found=[];origin=hostname(page_url)
    for a in soup.select('a[href]')[:450]:
        href=urldefrag(urljoin(page_url,a.get('href') or '')).url
        if not valid_https(href) or hostname(href)!=origin:continue
        if urlparse(href).path.lower().endswith(BAD_EXTENSIONS):continue
        name=core.clean(a.get_text(' ',strip=True))
        if not 10<=len(name)<=140 or name.casefold() in ('билеты','купить билеты','подробнее','читать','показать ещё','афиша','программа','расписание'):
            continue
        parent=a.find_parent(['article','li']) or a.parent
        text=core.clean(parent.get_text(' ',strip=True))[:360] if parent else ''
        # Restrict extraction to a nearby, context-specific time tag, or
        # explicit date linked with the event name. No article publish dates.
        times=parent.select('time[datetime]')[:3] if parent else []
        iso=[core.parse_iso(x.get('datetime')) for x in times]
        iso=[x for x in iso if x]
        months=core.russian_dates(text,today) if len(text)<=320 else []
        dates=(iso or months)[:2]
        if not dates or not core.in_scope(dates[0],dates[-1],today):continue
        cue=EVENT_TERMS.search(text) or any(x in urlparse(href).path.lower() for x in FUTURE_LINK_TERMS)
        if not cue:continue
        image_url=core.fragment_image_url(parent,page_url) if parent else ''
        ev=core.build_event(name,dates[0],dates[-1],'',source['name'],href,source,image_url=image_url)
        ev['extraction_method']='dated_listing'
        found.append(ev)
    return found[:100]


def public_feed_urls(soup,base):
    urls=[]
    for el in soup.select('link[rel][href], a[href]'):
        typ=(el.get('type') or '').lower()
        href=el.get('href') or ''
        if ('rss' in typ or 'atom' in typ or href.lower().split('?',1)[0].endswith(('.xml','.rss','.ics'))):
            url=urljoin(base,href)
            if valid_https(url) and hostname(url)==hostname(base) and url not in urls:
                urls.append(url)
    return urls[:1]


def extract_feed(raw,url,source,core,today):
    """Feed publication timestamp is NEVER used as the event date."""
    try:root=ET.fromstring(raw)
    except ET.ParseError:return []
    found=[]
    for entry in list(root.iter()):
        if entry.tag.split('}')[-1].lower() not in ('item','entry'):continue
        fields={}
        for child in entry:
            name=child.tag.split('}')[-1].lower()
            if name in ('title','description','summary','content','link','id'):
                fields[name]=child.attrib.get('href') or (child.text or '')
        title=core.clean(BeautifulSoup(fields.get('title',''),'html.parser').get_text(' ',strip=True))
        desc=core.clean(BeautifulSoup(fields.get('description',fields.get('summary','')),'html.parser').get_text(' ',strip=True))
        if not EVENT_TERMS.search(title+' '+desc[:150]):continue
        dates=core.russian_dates(title+' '+desc[:250],today)
        if not dates or not core.in_scope(dates[0],dates[-1],today):continue
        href=urljoin(url,fields.get('link') or fields.get('id') or url)
        if not valid_https(href):continue
        ev=core.build_event(title,dates[0],dates[-1],desc[:290],source['name'],href,source)
        ev['extraction_method']='feed_date_in_body'
        found.append(ev)
    return found


def scan_one(source,client,core,today):
    row={'id':source['id'],'name':source['name'],'url':source['url'],
         'status':'error','pages':0,'events':0,'methods':[],
         'priority':source.get('priority','B')}
    evs=[]
    if not valid_https(source.get('url')):
        row.update(status='invalid_url',error='Неверный HTTPS URL в реестре')
        return evs,row
    session=requests.Session()
    try:
        raw,ctype,current=client.read(source['url'],session)
        row['pages']+=1
        if 'html' not in ctype.casefold() and 'xml' not in ctype.casefold() and not current.lower().endswith(('.xml','.ics')):
            row['status']='unsupported';row['error']='Формат ответа: '+ctype[:65]
            return evs,row
        if 'calendar' in ctype.casefold() or current.lower().endswith('.ics'):
            evs=parse_ics(raw,current,source,core,today)
        else:
            soup=BeautifulSoup(raw,'html.parser')
            for e in core.jsonld_events(soup,current,source,today):
                e['extraction_method']='jsonld';evs.append(e)
            evs.extend(parse_microdata(soup,current,source,core,today))
            if not source.get('editorial_media'):
                evs.extend(extract_listing_anchors(soup,current,source,core,today))
            if source.get('mode')!='feed_only':
                links=core.discover_links(soup,current,int(source.get('max_details',1)))
                for link in links:
                    try:
                        detail_raw,detail_ctype,detail_url=client.read(link,session)
                        row['pages']+=1
                        if 'html' not in detail_ctype.casefold():continue
                        page=BeautifulSoup(detail_raw,'html.parser')
                        for e in core.jsonld_events(page,detail_url,source,today):
                            e['extraction_method']='detail_jsonld'
                            if not e.get('image_url') and not core.is_listing_page(detail_url):
                                e['image_url']=core.extract_image_url(page,detail_url)
                            evs.append(e)
                        evs.extend(parse_microdata(page,detail_url,source,core,today))
                        if not source.get('editorial_media'):
                            for e in core.page_event(page,detail_url,source,today):
                                e['extraction_method']='detail_dated_page';evs.append(e)
                    except (RobotsDenied,SourceError) as ex:
                        LOG.debug('Detail skip %s: %s',link,str(ex)[:80])
            # Only advertised feed links, not guessed hidden endpoints.
            for feed_url in public_feed_urls(soup,current):
                try:
                    feed,ftype,feed_final=client.read(feed_url,session)
                    row['pages']+=1
                    if feed_final.lower().endswith('.ics') or 'calendar' in ftype.casefold():
                        evs.extend(parse_ics(feed,feed_final,source,core,today))
                    elif 'xml' in ftype.casefold() or 'rss' in ftype.casefold() or 'atom' in ftype.casefold():
                        if not source.get('editorial_media'):
                            evs.extend(extract_feed(feed,feed_final,source,core,today))
                except (RobotsDenied,SourceError) as ex:
                    LOG.debug('Feed skip %s: %s',feed_url,str(ex)[:80])
            if not evs and any(marker in str(soup)[:7000] for marker in KNOWN_SPA_MARKERS) and len(soup.get_text(' ',strip=True))<600:
                row['status']='needs_javascript'
        # Unique within this website; merging across sources happens upstream.
        by_key={}
        for ev in evs:
            key=(ev['title'].casefold(),ev['start_date'],ev['url'])
            by_key[key]=ev
        evs=list(by_key.values())
        row['events']=len(evs)
        row['methods']=sorted({e.get('extraction_method','unknown') for e in evs})
        if row['status']!='needs_javascript':row['status']='found' if evs else 'no_events'
    except RobotsDenied as ex:
        row.update(status='blocked',error=str(ex)[:180])
    except SourceError as ex:
        row.update(status='error',error=str(ex)[:180])
    except Exception as ex:
        row.update(status='error',error=type(ex).__name__+': '+str(ex)[:130])
        LOG.exception('Source failed %s',source['name'])
    finally:session.close()
    return evs,row


def scan_registry(sources,core,today,workers=8,max_sources=0):
    """Attempt all registry addresses. No 'success' label without evidence."""
    selected=sources[:max_sources] if max_sources else sources
    client=PoliteClient(delay=1.1)
    results=[];logs=[]
    with ThreadPoolExecutor(max_workers=max(1,min(12,int(workers)))) as pool:
        futures={pool.submit(scan_one,s,client,core,today):s for s in selected}
        for future in as_completed(futures):
            src=futures[future]
            try:evs,record=future.result()
            except Exception as ex:
                evs=[];record={'id':src['id'],'name':src['name'],'url':src['url'],
                               'priority':src.get('priority','B'),'status':'error','pages':0,'events':0,
                               'error':type(ex).__name__+': '+str(ex)[:140]}
            results.extend(evs);logs.append(record)
            LOG.info('%s %s: %d pages, %d events',record['id'],record['status'],record['pages'],len(evs))
    order={s['id']:i for i,s in enumerate(selected)}
    logs.sort(key=lambda x:order[x['id']])
    return results,logs
