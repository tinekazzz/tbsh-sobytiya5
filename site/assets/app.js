/* ТБШ СОБЫТИЯ — editorial discovery dashboard. Poster images v3, with load-failure fallback. */
(() => {
'use strict';
const $ = (id) => document.getElementById(id);
const MONTHS = ['январь','февраль','март','апрель','май','июнь','июль','август','сентябрь','октябрь','ноябрь','декабрь'];
const MONTHS_GEN = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];
const MONTHS_SHORT = ['ЯНВ','ФЕВ','МАР','АПР','МАЙ','ИЮН','ИЮЛ','АВГ','СЕН','ОКТ','НОЯ','ДЕК'];
const CATS = ['Все','Концерты','Театр','Выставки','Шоу','Фестивали','Стендап','Кино','Лекции','Другое'];
const CSS_CLASSES = {'Концерты':'concerts','Театр':'theatre','Выставки':'exhibitions','Шоу':'show','Фестивали':'festivals','Стендап':'show','Кино':'cinema','Лекции':'lectures','Другое':'other'};
const POSTERS = {'Концерты':'LIVE','Театр':'ТЕАТР','Выставки':'АРТ','Шоу':'ШОУ','Фестивали':'ФЕСТ','Стендап':'СМЕХ','Кино':'КИНО','Лекции':'ИДЕИ','Другое':'СОБЫТИЕ'};
const SCREENS = {
 overview:['Пульс города','Всё самое интересное в культурной жизни — на месяц вперёд.','ОБЗОР'],
 events:['Афиша месяца','Подтверждённые события и яркие премьеры — выбирайте, что снимать.','АФИША'],
 editors:['Выбор редакции','События, которые команда ТБШ рекомендует посетить и включить в выпуск.','ВЫБОР РЕДАКЦИИ'],
 fresh:['Новые находки','События, которые недавно появились в нашей базе.','НОВОЕ'],
 favorites:['Ваша подборка','Отмеченные события для сценария и будущих выпусков.','ИЗБРАННОЕ'],
 sources:['Наши источники','Большая редакционная база площадок, медиа и афиш.','ИСТОЧНИКИ'],
 people:['Люди на радаре','Творческие имена, по которым ищем концерты, спектакли и выставки.','ИМЕНА'],
 about:['Как работает радар','От первоисточника до готовой редакционной подборки.','О ПРОЕКТЕ']
};
const todayMSK = new Date(new Date().toLocaleString('en-US', {timeZone:'Europe/Moscow'}));
let month = new Date(todayMSK.getFullYear(),todayMSK.getMonth()+1,1);
const state={view:'overview',category:'Все',city:'moscow',sort:'curated',term:'',limit:9,registryLimit:48,registryCategory:'all',sources:[],people:[],events:[],picks:[],status:{},favorites:new Set(),loaded:false};
try { state.favorites=new Set(JSON.parse(localStorage.getItem('kultradar:favorites')||'[]')); } catch { state.favorites=new Set(); }
const escapeHtml=(raw)=>String(raw??'').replace(/[&<>"']/g,(x)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const safeUrl=(raw)=>{try {let u=new URL(raw);return u.protocol==='https:'?u.href:'#';} catch{return '#';}};
const safeImageUrl=(raw)=>{try {let u=new URL(raw);return u.protocol==='https:'?u.href:'';} catch{return '';}};
// Secondary deduplication: older published JSONs may still contain cross-source repeats.
// The Python collector uses the same conservative title + date + location logic.
const identityText=(value)=>String(value||'').normalize('NFKC').toLowerCase().replace(/ё/g,'е').match(/[а-яa-z0-9]+/g)?.join(' ')||'';
const knownCity=(value)=>{const s=identityText(value);if(['','россия','рф','неизвестно','другое'].includes(s))return '';if(s.includes('московская область')||s.includes('подмосков'))return 'московская область';if(s.includes('москв')||s==='москва')return 'москва';if(s.includes('петербург')||s==='спб')return 'санкт петербург';return s;};
const venueGenerics=new Set(['центр','культурный','культуры','пространство','музей','театр','галерея','выставочный','зал','имени','им','г']);
function knownVenue(value){let s=identityText(value);if(['','неизвестно','не указано','не указан','уточняется','площадка уточняется','место уточняется','москва','россия'].includes(s))return '';if(['афиша ru','яндекс афиша','kudago','time out','неизвестн','уточняет','мтс live','кассир ru'].some(x=>s.includes(x)))return '';let t=s.split(' ');while(t.length&&venueGenerics.has(t[0]))t.shift();while(t.length&&['москва','московская','область','россия'].includes(t[t.length-1]))t.pop();return t.join(' ')||s;}
function sameVenue(a,b){const x=knownVenue(a),y=knownVenue(b);if(!x||!y)return false;if(x===y)return true;const xs=new Set(x.split(' ')),ys=new Set(y.split(' '));const small=xs.size<=ys.size?xs:ys,big=xs.size<=ys.size?ys:xs;return [...small].sort().join(' ').length>=4&&[...small].every(w=>big.has(w))&&big.size-small.size<=2;}
function sameDateSpan(a,b){const a0=String(a.start_date||'').slice(0,10),a1=String(a.end_date||a0).slice(0,10),b0=String(b.start_date||'').slice(0,10),b1=String(b.end_date||b0).slice(0,10);return /^20\d{2}-\d{2}-\d{2}$/.test(a0)&&/^20\d{2}-\d{2}-\d{2}$/.test(b0)&&a0<=b1&&b0<=a1;}
function canonicalLink(raw){try{const u=new URL(raw);const p=u.pathname.toLowerCase().replace(/\/$/,'')||'/';return u.protocol==='https:'&&!new Set(['/','/afisha','/events','/tickets','/program','/exhibitions','/performances','/concerts','/shows']).has(p)?u.hostname.replace(/^www\./,'')+p:'';}catch{return '';}}
function canonicalPoster(raw){try{const u=new URL(raw);return u.protocol==='https:'?u.hostname.replace(/^www\./,'')+u.pathname:'';}catch{return '';}}
function sameEvent(a,b){const title=identityText(a.title);if(title.length<5||title!==identityText(b.title))return false;const ac=knownCity(a.city),bc=knownCity(b.city);if(ac&&bc&&ac!==bc)return false;if(!sameDateSpan(a,b))return false;const av=knownVenue(a.venue),bv=knownVenue(b.venue);if(av&&bv)return sameVenue(a.venue,b.venue);const ai=canonicalPoster(a.image_url),bi=canonicalPoster(b.image_url),au=canonicalLink(a.url),bu=canonicalLink(b.url);if(ai&&ai===bi||au&&au===bu)return true;return title.length>=25&&title.split(' ').length>=3&&((av||bv)||String(a.start_date).slice(0,10)===String(b.start_date).slice(0,10))&&ac===bc;}
function clusterCompatible(e,cluster){if(!cluster.some(c=>sameEvent(e,c)))return false;return cluster.every(c=>{const a=knownCity(e.city),b=knownCity(c.city),av=knownVenue(e.venue),bv=knownVenue(c.venue);return !(a&&b&&a!==b)&&!(av&&bv&&!sameVenue(e.venue,c.venue));});}
const detailScore=e=>canonicalLink(e.url)?1:0;
const quality=e=>[(e.origin==='editorial_manual'?2:e.origin==='editorial'?1:0),Number(!!knownVenue(e.venue)),detailScore(e),Number(!!safeImageUrl(e.image_url)),String(e.description||'').length,Number(e.editor_score||0)];
function compareQuality(a,b){const aq=quality(a),bq=quality(b);for(let i=0;i<aq.length;i++){if(aq[i]!==bq[i])return bq[i]-aq[i];}return 0;}
function collapseCatalogGroup(group){if(group.length===1)return group[0];const ranked=[...group].sort(compareQuality),best={...ranked[0]};const allIds=[],allUrls=[],allSources=[],people=[];for(const ev of group){for(const id of [ev.id,...(ev.duplicate_ids||[])])if(id&&!allIds.includes(id))allIds.push(id);for(const url of [ev.url,...(ev.source_urls||[])])if(url&&!allUrls.includes(url))allUrls.push(url);for(const src of [ev.source_name,...(ev.duplicate_sources||[])])if(src&&!allSources.includes(src))allSources.push(src);for(const p of ev.people||[])if(!people.includes(p))people.push(p);}const editorial=ranked.find(e=>['editorial','editorial_manual'].includes(e.origin));if(editorial)best.id=editorial.id;best.duplicate_ids=allIds.filter(id=>id!==best.id);best.source_urls=allUrls;best.duplicate_sources=allSources;best.people=people;best.editor_score=Math.max(...group.map(e=>Number(e.editor_score||0)));best.featured=group.some(e=>e.featured);best.start_date=[...group].map(e=>e.start_date).sort()[0];best.end_date=[...group].map(e=>e.end_date||e.start_date).sort().at(-1);for(const field of ['venue','city']){const check=field==='venue'?knownVenue:knownCity;const found=ranked.find(e=>check(e[field]));if(found)best[field]=found[field];}const classified=ranked.find(e=>e.category&&e.category!=='Другое');if(classified)best.category=classified.category;const pictured=ranked.find(e=>safeImageUrl(e.image_url));if(pictured)best.image_url=pictured.image_url;const described=[...ranked].sort((a,b)=>String(b.description||'').length-String(a.description||'').length).find(e=>e.description&&!e.description.toLowerCase().startsWith('описание уточняется'));if(described)best.description=described.description;const dated=group.map(e=>e.discovered_at).filter(Boolean).sort();if(dated.length)best.discovered_at=dated[0];return best;}
function deduplicateEvents(records){const byTitle=new Map();for(const item of records){if(!item||!item.title)continue;const key=identityText(item.title),groups=byTitle.get(key)||[];const found=groups.find(group=>clusterCompatible(item,group));if(found)found.push(item);else groups.push([item]);byTitle.set(key,groups);}return [...byTitle.values()].flatMap(groups=>groups.map(collapseCatalogGroup));}
const aliasMatches=(record,id)=>record.id===id||(record.duplicate_ids||[]).includes(id);
const pickMatches=(pick,record)=>aliasMatches(record,pick.id);

const dayText=(iso)=>iso ? new Date(iso.slice(0,10)+'T12:00:00') : null;
const monthPrefix=()=>`${month.getFullYear()}-${String(month.getMonth()+1).padStart(2,'0')}`;
const monthStart=()=>monthPrefix()+'-01';
const monthEnd=()=>`${month.getFullYear()}-${String(month.getMonth()+1).padStart(2,'0')}-${String(new Date(month.getFullYear(),month.getMonth()+1,0).getDate()).padStart(2,'0')}`;
const niceMonth=()=>`${MONTHS[month.getMonth()].toUpperCase()} ${month.getFullYear()}`;
const presentDate=(d)=> {let dt=dayText(d);return dt?`${dt.getDate()} ${MONTHS_GEN[dt.getMonth()]} ${dt.getFullYear()}`:'Дата уточняется';};
const clockFmt=(d)=>{if(!d)return 'не проводилась';let x=new Date(d);return isNaN(+x)?d:`${String(x.getDate()).padStart(2,'0')}.${String(x.getMonth()+1).padStart(2,'0')}.${x.getFullYear()}`;};
const daysSince=(d)=>{let dt=dayText(d); if(!dt)return Infinity;let n=new Date(todayMSK.getFullYear(),todayMSK.getMonth(),todayMSK.getDate(),12);return Math.floor((n-dt)/86400000);};
const isRecent=(e)=>daysSince(e.discovered_at)>=0 && daysSince(e.discovered_at)<=7;
const isInMonth=(e)=>String(e.start_date||'').slice(0,10)<=monthEnd() && String(e.end_date||e.start_date||'').slice(0,10)>=monthStart();
const isInCity=(e)=>state.city==='all'|| (state.city==='moscow'&&/москв|москов/i.test(e.city||'')) ||(state.city==='spb'&&/петербург|ленинград/i.test(e.city||''))||(state.city==='other'&&!/москв|москов|петербург|ленинград/i.test(e.city||''));
const containsTerm=(fields)=> !state.term || fields.filter(Boolean).join(' ').toLowerCase().includes(state.term.toLowerCase());
const sortEvents=(a,b)=>{
 if(state.sort==='date')return a.start_date.localeCompare(b.start_date)||b.editor_score-a.editor_score;
 if(state.sort==='fresh')return String(b.discovered_at).localeCompare(String(a.discovered_at))||b.editor_score-a.editor_score;
 return (b.editor_score||0)-(a.editor_score||0)||a.start_date.localeCompare(b.start_date);
};
let displayedEvents=[];let toastTimer;
function notify(msg){let el=$('toast');el.textContent=msg;el.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('show'),2500);}
function saveFavs(){try{localStorage.setItem('kultradar:favorites',JSON.stringify([...state.favorites]));}catch{}$('fav-counter').textContent=String(state.favorites.size);}
function editorialEvents(){
 const seen=new Set();
 return state.picks.map((item,i)=>{
  const snapshot=(item.event&&typeof item.event==='object')?item.event:{};
  const current=state.events.find(e=>pickMatches(item,e))||{};
  const ev={...snapshot,...current};
  ev.id=current.id||item.id||ev.id;
  ev.editorial_pick=true;
  ev.editorial_note=String(item.note||'').slice(0,500);
  ev.editorial_order=i;
  if(safeImageUrl(item.image_url))ev.image_url=item.image_url;
  return ev;
 }).filter(e=>{if(!e.id||!e.start_date||!e.title||seen.has(e.id))return false;seen.add(e.id);return true;});
}
function matchingEvents(){
 const pool=state.view==='editors'?editorialEvents():state.events.map(e=>{
  const index=state.picks.findIndex(p=>pickMatches(p,e));
  if(index<0)return e;
  const pick=state.picks[index];
  return {...e, editorial_pick:true, editor_score:1000-index, image_url:safeImageUrl(pick.image_url)?pick.image_url:e.image_url};
 });
 const matches=pool.filter(e=>isInMonth(e)&&isInCity(e)&&(state.category==='Все'||e.category===state.category)&&containsTerm([e.title,e.description,e.venue,e.city,e.category,e.source_name,e.editorial_note,...(e.people||[])]))
 .filter(e=>state.view!=='fresh'||isRecent(e))
 .filter(e=>state.view!=='favorites'||state.favorites.has(e.id));
 return (state.view==='editors'&&state.sort==='curated')?matches.sort((a,b)=>a.editorial_order-b.editorial_order):matches.sort(sortEvents);
}
function poster(ev){
 const word=POSTERS[ev.category]||'СЦЕНА', img=safeImageUrl(ev.image_url);
 const fallback=`<span class="poster-decoration deco-a"></span><span class="poster-decoration deco-b"></span><span class="poster-word">${escapeHtml(word)}</span><span class="poster-star">✳</span>`;
 if(!img)return fallback;
 // Keep the branded fallback visible until the actual image loads. Browser
 // hotlink failures never turn a card into a blank rectangle.
 return `${fallback}<img class="poster-real-image" src="${escapeHtml(img)}" alt="Афиша: ${escapeHtml(ev.title)}" loading="lazy" decoding="async" referrerpolicy="no-referrer"><span class="poster-photo-shade"></span>`;
}
function eventCard(e){const ongoing=(e.start_date||'')<monthStart(),d=dayText(ongoing?monthStart():e.start_date),dateLabel=ongoing?'ВЕСЬ':MONTHS_SHORT[d?.getMonth()||0],dateDay=ongoing?'↳':String(d?.getDate()||'—'),cls=CSS_CLASSES[e.category]||'other';
 const isPicked=!!e.editorial_pick||state.picks.some(x=>pickMatches(x,e));
 const fav=state.favorites.has(e.id),desc=e.description||'Описание уточняется на странице организатора.', tag=ongoing?'ПРОДОЛЖАЕТСЯ':(e.tag|| (isRecent(e)&&e.origin==='automatic'?'НОВОЕ':'')).toUpperCase();
 return `<article class="event-card ${isPicked?'is-editorial':''}">
 <div class="card-visual poster-${cls}${safeImageUrl(e.image_url)?' poster-has-source':''}">${poster(e)}
 <div class="card-top-row"><span class="card-date-badge"><strong>${escapeHtml(dateDay)}</strong><small>${escapeHtml(dateLabel)}</small></span><button class="favorite-btn ${fav?'is-saved':''}" type="button" data-fav="${escapeHtml(e.id)}" aria-label="${fav?'Удалить из избранного':'В избранное'}" title="В избранное">${fav?'♥':'♡'}</button></div>
 ${tag?`<span class="poster-tag">${escapeHtml(tag)}</span>`:''}</div>
 <div class="card-content"><span class="card-category">${escapeHtml(e.category||'Другое')} · ${escapeHtml(e.city||'Россия')}</span>${isPicked?'<span class="editorial-badge">✦ ВЫБОР РЕДАКЦИИ</span>':''}
 <div class="card-title" tabindex="0" role="button" data-open="${escapeHtml(e.id)}">${escapeHtml(e.title)}</div>${e.editorial_note?`<p class="editorial-note">${escapeHtml(e.editorial_note)}</p>`:''}<p class="card-desc">${escapeHtml(desc)}</p><div class="card-spacer"></div>
 <div class="card-meta"><span class="meta-icon">⌖</span><span>${escapeHtml(e.venue||'Место уточняется')}</span></div>
 ${e.people?.length?`<div class="card-people">✳ ${escapeHtml(e.people.slice(0,2).join(' · '))}</div>`:''}
 <div class="card-bottom"><span class="card-source">${escapeHtml(e.source_name||'Источник')}</span><button class="card-open" type="button" data-open="${escapeHtml(e.id)}">Подробнее ↗</button></div></div></article>`;
}
function updateMetrics(){const inMonth=state.events.filter(e=>isInMonth(e)&&isInCity(e));$('metric-events').textContent=inMonth.length;$('metric-new').textContent=inMonth.filter(isRecent).length;$('metric-sources').textContent=state.sources.length;$('metric-people').textContent=state.people.length;}
function renderGenres(){const el=$('genre-pills');el.innerHTML=CATS.map(cat=>`<button type="button" data-cat="${escapeHtml(cat)}" class="category-pill ${cat===state.category?'selected':''}">${escapeHtml(cat)}</button>`).join('');}
function emptyEvents(){return `<div class="empty-state"><span>✳</span><h3>${state.view==='editors'?'Подборка готовится':'Пока ничего не нашлось'}</h3><p>${state.view==='editors'?'Пока редакция не опубликовала события для выбранного месяца. Загляните позже или выберите другой месяц.':state.view==='favorites'?'Добавьте события в избранное с помощью сердечка на карточке.':'В этом разделе пока нет подходящих событий. Попробуйте другой жанр, месяц или город.'}</p>${state.view==='editors'?'':`<button data-clear="true" type="button">Сбросить фильтры</button>`}</div>`;}
function updateGrid(){displayedEvents=matchingEvents();const filtered=displayedEvents.slice(0,state.limit);$('events-grid').innerHTML=filtered.length?filtered.map(eventCard).join(''):emptyEvents();
 const isOverview=state.view==='overview';const suffix=state.view==='editors'?'рекомендаций редакции':state.view==='fresh'?'недавно добавленных':state.view==='favorites'?'сохранённых':'событий';
 $('result-meta').innerHTML=`<span>НАЙДЕНО <strong>${displayedEvents.length}</strong> ${suffix}</span><span class="meta-refresh">${escapeHtml(niceMonth())}</span>`;
 $('event-more').innerHTML=displayedEvents.length>state.limit?`<button type="button" class="show-more" id="show-more">Показать ещё · ${displayedEvents.length-state.limit}</button>`:'';
 $('events-section-title').textContent=state.view==='editors'?'Рекомендует редакция ТБШ':state.view==='fresh'?'Недавно обнаруженные события':state.view==='favorites'?'Выбранное для будущего выпуска':isOverview?'События, которые стоят внимания':'Вся афиша на месяц';
 $('events-view-tag').textContent=state.view==='editors'?'РЕКОМЕНДУЕМ':state.view==='fresh'?'НОВОЕ':state.view==='favorites'?'МОЯ ПОДБОРКА':'АФИША';
 $('see-all-events').style.display=isOverview?'':'none';
}
function renderHighlights(){const list=[...state.events].filter(e=>isInMonth(e)).sort((a,b)=>String(b.discovered_at).localeCompare(String(a.discovered_at))||(b.editor_score||0)-(a.editor_score||0)).slice(0,5);
 $('recent-events').innerHTML=list.length?list.map((e,i)=>`<button data-open="${escapeHtml(e.id)}" type="button" class="recent-item"><span class="recent-mark ${e.category==='Выставки'?'r-exhibit':e.category==='Концерты'?'r-concert':'r-festival'}">${e.category==='Выставки'?'◈':e.category==='Концерты'?'♫':'✳'}</span><span class="recent-content"><span class="recent-date">${escapeHtml(presentDate(e.start_date))}</span><span class="recent-title">${escapeHtml(e.title)}</span><span class="recent-source">${escapeHtml(e.venue||e.source_name)}</span></span></button>`).join(''):'<p class="registry-description">Пока нет новых анонсов.</p>';
 const names=['Константин Богомолов','Юрий Башмет','Полина Гагарина','Антон Фёдоров','Маурицио Каттелан'];const found=names.map(n=>state.people.find(p=>p.name===n)).filter(Boolean);
 $('tracked-highlights').innerHTML=found.map((p,i)=>`<button class="tracked-person" data-person="${escapeHtml(p.name)}" type="button"><span class="person-monogram tint-${i%3}">${escapeHtml(p.name.split(' ').slice(0,2).map(t=>t[0]).join(''))}</span><span><span class="tracked-person-name">${escapeHtml(p.name)}</span><span class="tracked-person-category">${escapeHtml(p.category)}</span></span></button>`).join('');
}
function renderStatus(){const st=state.status||{};const on=st.mode==='daily_collection',ok=(st.sources_reached_today||0)>0;$('status-indicator').className='status-dot'+(on&&ok?'':' status-demo');
 $('status-label').textContent=!on?'Демоверсия / стартовые данные':ok?'Ежедневный сбор выполнен':'Сбор запущен · есть ошибки';
 $('last-refresh').textContent=clockFmt(st.updated_at);
 $('refresh-description').textContent=!on?'Стартовые анонсы. Автоматическая проверка начнётся после публикации проекта.':`Попыток проверки: ${st.sources_checked_today||0} из ${st.sources_in_registry||state.sources.length}. Открылись: ${st.sources_reached_today||0}. С датированными событиями: ${st.sources_with_events_today||0}. Новых карточек: ${st.new_events_added_today||0}.`;
 if(on && Number.isFinite(st.events_with_images)) $('refresh-description').textContent+=` С афишами: ${st.events_with_images} из ${st.events_in_catalog||0}.`;
 $('refresh-frequency').textContent=on?'ежедневно':'ожидает запуска';
 $('about-status-title').textContent=!on?'Стартовая версия, ещё не опубликована':ok?'Автосборщик запускался':'Автосборщик запущен, доступ к сайтам ограничен';
 $('about-status-text').textContent=!on?'Сейчас на сайте стартовые анонсы. Для ежедневной проверки нужен успешный запуск GitHub Actions.':`Последний запуск ${clockFmt(st.updated_at)}. Запрошено: ${st.sources_checked_today||0} из ${st.sources_in_registry||state.sources.length} источников; открылись: ${st.sources_reached_today||0}; с датированными событиями: ${st.sources_with_events_today||0}; заблокировано: ${st.sources_blocked_today||0}; ошибки: ${st.sources_failed_today||0}. Попытка проверки не означает, что у сайта удалось получить афишу. ${state.people.length} имён используются для сопоставления с найденными анонсами. ${Number.isFinite(st.events_with_images)?`Карточек со ссылками на афиши: ${st.events_with_images}; найдено изображений за последний запуск: ${st.images_found_today||0}; проверено страниц: ${st.images_checked_today||0}.`:'Статистика афиш появится после запуска обновлённого сборщика.'}`;
}
function setView(view,scroll=true){
 if(view==='editors' && state.view!=='editors'){
  state.category='Все';state.city='all';state.sort='curated';state.term='';
  $('global-search').value='';$('city-select').value='all';$('sort-select').value='curated';renderGenres();
 }
 state.view=SCREENS[view]?view:'overview';state.limit=view==='overview'?9:24;state.registryLimit=48;
 document.querySelectorAll('[data-view]').forEach(btn=>btn.classList.toggle('active',btn.dataset.view===state.view));
 $('screen-title').innerHTML=escapeHtml(SCREENS[state.view][0])+'<span class="title-dot">.</span>';
 $('screen-description').textContent=SCREENS[state.view][1];$('breadcrumb-view').textContent='/ '+SCREENS[state.view][2];
 const isCatalog=['overview','events','editors','fresh','favorites'].includes(state.view);
 $('hero-section').classList.toggle('hidden',state.view!=='overview');$('metrics').classList.toggle('hidden',state.view!=='overview');$('editorial-intro').classList.toggle('hidden',state.view!=='editors');
 $('events-section').classList.toggle('hidden',!isCatalog);$('registry-section').classList.toggle('hidden',!['sources','people'].includes(state.view));
 $('about-section').classList.toggle('hidden',state.view!=='about');
 $('main-header').classList.toggle('registry-header',['sources','people','about'].includes(state.view));
 if(isCatalog)updateGrid();
 if(['sources','people'].includes(state.view))renderRegistry();
 if(scroll)window.scrollTo({top:0,behavior:'smooth'});
 location.hash=state.view;
}
function setMonth(by){month=new Date(month.getFullYear(),month.getMonth()+by,1);renderMonth();}
function renderMonth(){$('month-display').textContent=niceMonth();$('hero-month-small').textContent=`${String(month.getMonth()+1).padStart(2,'0')} — ${month.getFullYear()}`;$('hero-month-label').textContent=['ЯНВАРЯ','ФЕВРАЛЯ','МАРТА','АПРЕЛЯ','МАЯ','ИЮНЯ','ИЮЛЯ','АВГУСТА','СЕНТЯБРЯ','ОКТЯБРЯ','НОЯБРЯ','ДЕКАБРЯ'][month.getMonth()];updateMetrics();if(['overview','events','editors','fresh','favorites'].includes(state.view))updateGrid();renderHighlights();}
function renderRegistry(refreshControls=true){const sourceMode=state.view==='sources',data=sourceMode?state.sources:state.people;
 const categories=[...new Set(data.map(x=>x.category))].sort((a,b)=>a.localeCompare(b,'ru'));
 const current=categories.includes(state.registryCategory)?state.registryCategory:'all';state.registryCategory=current;
 if(refreshControls)$('registry-controls').innerHTML=`<input type="search" id="registry-search" value="${escapeHtml(state.term)}" placeholder="${sourceMode?'Найти театр, музей, площадку...':'Найти режиссёра, артиста, художника...'}" aria-label="Поиск по реестру" /><select id="registry-category" aria-label="Категория реестра"><option value="all">Все категории</option>${categories.map(x=>`<option value="${escapeHtml(x)}" ${x===current?'selected':''}>${escapeHtml(x)}</option>`).join('')}</select>`;
 const rows=data.filter(x=>(current==='all'||x.category===current)&&containsTerm([x.name,x.category,x.region,x.why,x.aliases,x.url]));
 $('registry-stats').innerHTML=`<strong>${rows.length}</strong> из ${data.length} ${sourceMode?'источников':'имён'} · ${sourceMode?'А — высокий редакционный приоритет · подключение к сбору отдельно':'важные имена и псевдонимы для поиска анонсов'}`;
 $('registry-items').innerHTML=rows.slice(0,state.registryLimit).map((x,i)=>sourceMode?sourceRow(x,i):personRow(x,i)).join('') || `<div class="empty-state"><span>⌕</span><h3>Нет совпадений</h3><p>Попробуйте изменить поисковый запрос или категорию.</p></div>`;
 $('registry-more').innerHTML=rows.length>state.registryLimit?`<button type="button" id="registry-show-more" class="show-more">Показать ещё · ${rows.length-state.registryLimit}</button>`:'';
}
function sourceRow(x,i){const st=state.status?.source_log?.find(y=>y.id===x.source_id);const stateLabels={found:`событий: ${st?.events||0}`,no_events:'сайт открылся, дат нет',needs_javascript:'нужен JavaScript',blocked:'доступ ограничен',error:'ошибка соединения',invalid_url:'некорректный адрес',unsupported:'формат не поддерживается',ok:'сайт открылся'};const status=st?`Проверка: ${stateLabels[st.status]||st.status}`:'Нет результатов последней проверки';return `<article class="registry-row"><span class="registry-icon">${i%3===0?'◈':i%3===1?'⌁':'✳'}</span><div class="registry-body"><strong class="registry-name">${escapeHtml(x.name)}</strong><p class="registry-description">${escapeHtml(x.why)}</p><div class="registry-meta"><span class="tag">${escapeHtml(x.category)}</span><span>${escapeHtml(x.region)}</span><span class="registry-status">${escapeHtml(status)}</span></div></div><span class="registry-priority priority-${escapeHtml(x.priority)}">${escapeHtml(x.priority)}</span><a class="registry-external" title="Открыть источник" href="${escapeHtml(safeUrl(x.url))}" target="_blank" rel="noopener noreferrer" aria-label="Открыть ${escapeHtml(x.name)}">↗</a></article>`;}
function personRow(x,i){const matches=state.events.filter(e=>Array.isArray(e.people)&&e.people.includes(x.name)).length;return `<article class="registry-row"><span class="registry-icon">${i%3===0?'✳':i%3===1?'♬':'◈'}</span><div class="registry-body"><strong class="registry-name">${escapeHtml(x.name)}</strong><p class="registry-description">${escapeHtml(x.why)}</p><div class="registry-meta"><span class="tag">${escapeHtml(x.category)}</span><span>${matches?matches+' событий в базе':'мониторинг по имени'}</span></div></div><span class="registry-priority priority-${escapeHtml(x.priority)}">${escapeHtml(x.priority)}</span><button type="button" class="registry-person-button" data-person="${escapeHtml(x.name)}" title="Искать события по этому имени">Искать ↗</button></article>`;}
function showEvent(id){const e=editorialEvents().find(x=>aliasMatches(x,id))||state.events.find(x=>aliasMatches(x,id));if(!e)return;const cl=CSS_CLASSES[e.category]||'other';const fav=state.favorites.has(id);
 $('modal-root').innerHTML=`<div class="modal-backdrop" role="presentation" data-modal-close="1"><div class="modal" role="dialog" aria-modal="true" aria-label="Информация о событии"><div class="modal-visual poster-${cl}${safeImageUrl(e.image_url)?' poster-has-source':''}">${poster(e)}<button type="button" class="modal-close" data-modal-close="1" aria-label="Закрыть">×</button></div><div class="modal-body"><span class="modal-category">${escapeHtml(e.category)} · ${escapeHtml(e.city||'Россия')}</span><h2>${escapeHtml(e.title)}</h2>${e.editorial_note?`<p class="editorial-note">✦ ${escapeHtml(e.editorial_note)}</p>`:''}<p>${escapeHtml(e.description||'Описание смотрите в первоисточнике.')}</p><div class="modal-details"><div class="modal-detail"><span>КОГДА</span><strong>${escapeHtml(presentDate(e.start_date))}${e.end_date&&e.end_date!==e.start_date?' — '+escapeHtml(presentDate(e.end_date)):''}${e.time?' / '+escapeHtml(e.time):''}</strong></div><div class="modal-detail"><span>ГДЕ</span><strong>${escapeHtml(e.venue||'Площадка уточняется')}</strong></div><div class="modal-detail"><span>ИСТОЧНИК</span><strong>${escapeHtml(e.source_name||'Официальная страница')}</strong></div><div class="modal-detail"><span>УЧАСТНИКИ / АВТОРЫ</span><strong>${escapeHtml((e.people||[]).join(', ')||'Уточняйте у организатора')}</strong></div></div><div class="modal-footer"><a class="modal-primary" href="${escapeHtml(safeUrl(e.url))}" target="_blank" rel="noopener noreferrer">Открыть первоисточник ↗</a><button type="button" class="modal-secondary ${fav?'saved':''}" data-fav="${escapeHtml(e.id)}">${fav?'♥ В избранном':'♡ В избранное'}</button></div><p class="modal-footer-note">${escapeHtml(e.verification||'Проверьте подробности у организатора.')} · Добавлено в базу: ${escapeHtml(clockFmt(e.discovered_at))}</p></div></div></div>`;
 document.body.style.overflow='hidden';
}
function closeModal(){$('modal-root').innerHTML='';document.body.style.overflow='';}
function toggleFav(id){const e=state.events.find(x=>aliasMatches(x,id));if(e)id=e.id;if(state.favorites.has(id))state.favorites.delete(id);else state.favorites.add(id);saveFavs();if($('modal-root').children.length)showEvent(id);if(['overview','events','editors','fresh','favorites'].includes(state.view))updateGrid();notify(state.favorites.has(id)?'Сохранено в избранное':'Удалено из избранного');}
function resetFilters(){state.category='Все';state.city='moscow';state.term='';state.sort='curated';$('global-search').value='';$('city-select').value='moscow';$('sort-select').value='curated';renderGenres();if(['sources','people'].includes(state.view))renderRegistry();else updateGrid();}
function csvExport(){let events=matchingEvents();if(state.view==='overview')events=matchingEvents();
 const headers=['Название','Категория','Дата начала','Дата окончания','Время','Город','Площадка','Участники','Источник','Ссылка','Описание','Комментарий редакции'];
 const cell=x=>'"'+String(x??'').replace(/"/g,'""')+'"';const rows=[headers,...events.map(e=>[e.title,e.category,e.start_date,e.end_date,e.time,e.city,e.venue,(e.people||[]).join(', '),e.source_name,e.url,e.description,e.editorial_note||''])];
 const blob=new Blob(['\ufeff'+rows.map(row=>row.map(cell).join(';')).join('\r\n')],{type:'text/csv;charset=utf-8'});
 const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`TBSH-SOBYTIYA-${monthPrefix()}.csv`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1500);notify(`CSV: ${events.length} событий`);
}
function jumpToPerson(name){state.term=name;state.category='Все';state.city='all';$('global-search').value=name;$('city-select').value='all';renderGenres();setView('events');notify(`Поиск по имени: ${name}`);}
function wireEvents(){
 document.addEventListener('load',(event)=>{
  const img=event.target;
  if(img?.classList?.contains('poster-real-image') && img.naturalWidth>0){
   img.closest('.card-visual, .modal-visual')?.classList.add('poster-image-loaded');
  }
 },true);
 document.addEventListener('error',(event)=>{
  const img=event.target;
  if(img?.classList?.contains('poster-real-image')){
   img.closest('.card-visual, .modal-visual')?.classList.remove('poster-image-loaded');
   img.remove();
  }
 },true);
 document.addEventListener('click',(event)=>{
  if(event.target.classList.contains('modal-backdrop')){closeModal();return;}
  const el=event.target.closest('button, a, [role="button"]');if(!el)return;
  if(el.dataset.view){event.preventDefault();state.registryCategory='all';setView(el.dataset.view);return;}
  if(el.dataset.cat){state.category=el.dataset.cat;state.limit=state.view==='overview'?9:24;renderGenres();updateGrid();return;}
  if(el.dataset.open){showEvent(el.dataset.open);return;}
  if(el.dataset.fav){toggleFav(el.dataset.fav);return;}
  if(el.dataset.person){jumpToPerson(el.dataset.person);return;}
  if(el.dataset.clear){resetFilters();return;}
  if(el.dataset.modalClose){if(event.target.closest('.modal') && !event.target.classList.contains('modal-close'))return;closeModal();return;}
  if(el.id==='month-prev'){setMonth(-1);return;}
  if(el.id==='month-next'){setMonth(1);return;}
  if(['hero-go-events','see-all-events'].includes(el.id)){setView('events');return;}
  if(el.id==='go-favorites'){setView('favorites');return;}
  if(el.id==='export-events'){csvExport();return;}
  if(el.id==='show-more'){state.limit+=18;updateGrid();return;}
  if(el.id==='registry-show-more'){state.registryLimit+=48;renderRegistry();return;}
 });
 document.addEventListener('change',event=>{
  if(event.target.id==='city-select'){state.city=event.target.value;updateMetrics();updateGrid();return;}
  if(event.target.id==='sort-select'){state.sort=event.target.value;updateGrid();return;}
  if(event.target.id==='registry-category'){state.registryCategory=event.target.value;state.registryLimit=48;renderRegistry();return;}
 });
 let searchTimer;document.addEventListener('input',event=>{
  if(event.target.id==='global-search'||event.target.id==='registry-search'){
   const term=event.target.value;const counterpart=event.target.id==='global-search'?'registry-search':'global-search';if($(counterpart))$(counterpart).value=term;
   clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.term=term.trim();state.registryLimit=48;if(['sources','people'].includes(state.view))renderRegistry(false);else updateGrid();},130);
  }
 });
 document.addEventListener('keydown',event=>{
  if(event.key==='Escape')closeModal();
  if(event.key==='Enter'&&event.target.dataset.open)showEvent(event.target.dataset.open);
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();$('global-search').focus();}
 });
}
async function readFile(rel){const res=await fetch(rel+'?v='+Date.now(),{cache:'no-store'});if(!res.ok)throw new Error('HTTP '+res.status+' '+rel);return res.json();}
async function init(){wireEvents();let bundle,sources,people,status,picks;
 if(window.__RADAR_PREVIEW__){({bundle,sources,people,status,picks}=window.__RADAR_PREVIEW__);}
 else {try{[bundle,sources,people,status,picks]=await Promise.all([readFile('./data/events.json'),readFile('./data/sources.json'),readFile('./data/people.json'),readFile('./data/status.json'),readFile('./data/editorial_picks.json').catch(()=>({items:[]}))]);}
 catch(error){console.error(error); $('events-grid').innerHTML='<div class="empty-state"><span>!</span><h3>Данные не загрузились</h3><p>Откройте сайт через HTTP-сервер: python -m http.server 8000 в папке site.</p></div>';notify('Не удалось загрузить базу');return;}}
 state.events=deduplicateEvents(Array.isArray(bundle?.events)?bundle.events:[]);state.sources=Array.isArray(sources)?sources:[];state.people=Array.isArray(people)?people:[];state.picks=Array.isArray(picks?.items)?picks.items.filter(x=>x&&x.id&&x.event):[];state.status=status||{};state.loaded=true;
 if($('sidebar-sources-count'))$('sidebar-sources-count').textContent=String(state.sources.length);
 if($('sidebar-people-count'))$('sidebar-people-count').textContent=String(state.people.length);
 if($('about-source-count'))$('about-source-count').textContent=state.sources.length+' сайтов';
 if($('about-people-count'))$('about-people-count').textContent=state.people.length+' имён';
 // Manually authored events remain visible even if automatic collection does not know about them.
 for(const pick of state.picks){if(pick.event?.origin==='editorial_manual'&&!state.events.some(e=>pickMatches(pick,e)))state.events.push(pick.event);}
 state.events=deduplicateEvents(state.events);
 // Favorites from an older duplicated record survive migration to a single card.
 const idMapping=new Map();for(const e of state.events){idMapping.set(e.id,e.id);for(const alias of e.duplicate_ids||[])idMapping.set(alias,e.id);}
 state.favorites=new Set([...state.favorites].map(id=>idMapping.get(id)||id));
 try{localStorage.setItem('kultradar:favorites',JSON.stringify([...state.favorites]));}catch{}
 if($('editorial-counter'))$('editorial-counter').textContent=String(state.picks.length);
 $('fav-counter').textContent=String(state.favorites.size);
 renderGenres();renderStatus();renderMonth();
 const initial=location.hash.replace('#','');setView(SCREENS[initial]?initial:'overview',false);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
