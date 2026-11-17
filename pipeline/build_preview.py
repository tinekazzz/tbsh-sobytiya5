from pathlib import Path
import json, base64
ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'site'
html=(SITE/'index.html').read_text('utf8')
css=(SITE/'assets/app.css').read_text('utf8')
js=(SITE/'assets/app.js').read_text('utf8')
data={
 'bundle':json.loads((SITE/'data/events.json').read_text('utf8')),
 'sources':json.loads((SITE/'data/sources.json').read_text('utf8')),
 'people':json.loads((SITE/'data/people.json').read_text('utf8')),
 'status':json.loads((SITE/'data/status.json').read_text('utf8'))
}
payload=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
html=html.replace('<link rel="stylesheet" href="./assets/app.css" />','<style>'+css+'</style>')
html=html.replace('<script defer src="./assets/app.js"></script>', '<script>window.__RADAR_PREVIEW__='+payload+';</script>\n<script>'+js+'</script>')
# Inline branded image assets to keep preview self-contained.
for filename in ['tbsh-mark-white.png','tbsh-logo-white.png']:
    tag = './assets/'+filename
    encoded = base64.b64encode((SITE/'assets'/filename).read_bytes()).decode('ascii')
    mime = 'image/webp' if filename.endswith('.webp') else 'image/png'
    html = html.replace(tag,'data:'+mime+';base64,'+encoded)

path=ROOT.parent/'ТБШ_СОБЫТИЯ_превью.html'
path.write_text(html,'utf8')
print('Created',path, 'bytes',path.stat().st_size)
