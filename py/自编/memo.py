import base64, json, re, time, urllib.parse, sys
import requests
from pyquery import PyQuery as pq
sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    host = 'https://memojav.com'
    headers = {'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'referer': host + '/'}
    proxy_prefix = 'http://127.0.0.1:10079/p/0/127.0.0.1:10172/'

    def init(self, extend=''):
        cfg = json.loads(extend) if extend else {}
        self.proxies = cfg.get('proxies', {          "http": "http://127.0.0.1:10172",

          "https": "http://127.0.0.1:10172"})

    def getName(self):
        return 'memo'

    def proxy(self, url):
        return self.proxy_prefix + url if url and url.startswith(('http://', 'https://')) else url

    def fetch(self, url, params=None):
        try:
            return requests.get(url, headers=self.headers, params=params, proxies=self.proxies, timeout=15).text
        except Exception:
            return ''

    def path(self, tid):
        tid = (tid or '/').strip()
        tid = re.sub(r'^https?://[^/]+', '', tid)
        return tid if tid.startswith('/') else '/' + tid

    def list_url(self, tid, pg):
        pg, p = int(pg or 1), self.path(tid).rstrip('/')
        return f'{self.host}{p}/' if p in ('/video', '/best') and pg == 1 else f'{self.host}{p}' if pg == 1 else f'{self.host}{p}/page-{pg}'

    def pagecount(self, doc):
        mx = doc('input.inputNumber_nav').attr('max')
        if mx and mx.isdigit(): return int(mx)
        nums = [int(a.text()) for a in doc('ul.pageNav-main a').items() if a.text().strip().isdigit()]
        return max(nums) if nums else 1

    def homeContent(self, filter):
        return {'class': [{'type_name': n, 'type_id': i} for n, i in [('新视频', 'video'), ('最佳视频', 'best'), ('女演员', 'actress'), ('工作室', 'studio')]], 'list': self.parse_videos(pq(self.fetch(self.host))('.video-item'))}

    def categoryContent(self, tid, pg, filter, extend):
        doc = pq(self.fetch(self.list_url(tid, pg)))
        return {'list': self.parse_videos(doc('.video-item')) if doc('.video-item').length else self.parse_folders(doc('a:has(.description-block)')), 'page': pg, 'pagecount': self.pagecount(doc), 'limit': 90, 'total': 999999}

    def detailContent(self, ids):
        vid = (ids[0] or '').strip()
        if not vid: return {'list': []}
        url = vid if vid.startswith(('http://', 'https://')) else self.host + (vid if vid.startswith('/') else ('/video/' + vid if not vid.startswith('video/') else '/' + vid))
        doc = pq(self.fetch(url))
        video_id = (re.search(r'/video/([^/?#]+)', url) or [None, url.rstrip('/').split('/')[-1].split('?')[0]])[1]
        title = re.sub(r'\s*\|.*$', '', doc('#title').text() or doc('h1').text() or doc('title').text() or '').strip()
        vod = {'vod_name': title, 'vod_play_from': 'MemoJav', 'vod_play_url': f'{title}${video_id}', 'vod_pic': self.proxy(doc('meta[property="og:image"]').attr('content') or doc('#poster,img#poster').attr('src')), 'vod_year': doc('table.details tr:contains("Release Date") td').text().strip()}

        def row(name):
            name = name.rstrip(':')
            for tr in doc('table.details tr').items():
                if tr('th').text().strip().rstrip(':') == name: return tr
            return pq([])

        def links(name, sel='a', must=''):
            out = []
            for a in row(name)(sel).items():
                href = (a.attr('href') or '').strip()
                if href and (not must or must in href):
                    text = a.find('span').eq(-1).text().strip() or a.text().strip()
                    if text: out.append(f'[a=cr:{json.dumps({"id": href, "name": text})}/]{text}[/a]')
            return out

        data = {'vod_actor': ' '.join(links('Actress', 'a', '/actress/')), 'vod_director': ' '.join(links('Director')), 'vod_remarks': '发行商：' + ' '.join(links('Studio'))}
        vod.update({k: v for k, v in data.items() if v and v != '发行商：'})
        content = [('系列：' + ' '.join(x)) for x in [links('Series')] if x] + [('标签: ' + ' '.join(x)) for x in [links('Categories', 'a.box-tag')] if x]
        if content: vod['vod_content'] = '\n'.join(content)
        return {'list': [vod]}

    def searchContent(self, key, quick, pg='1'):
        return {'list': self.parse_videos(pq(self.fetch(self.host + '/search', {'text': key, **({'p': pg} if int(pg) > 1 else {})}))('.video-item')), 'page': pg}

    def video_sig(self):
        sig = base64.b64encode(str(int(time.time() * 1000)).encode()).decode()[-12:-2]
        return sig, 1 + sum(ord(c) * i * 1743 for i, c in enumerate(sig[:10]))

    def playerContent(self, flag, id, vipFlags):
        vid = (id or '').strip()
        if not vid: return {'parse': 0, 'url': ''}
        sig, sts = self.video_sig()
        raw = self.fetch(f'{self.host}/hls/get_video_info.php?id={urllib.parse.quote(vid)}&sig={sig}&sts={sts}').split('for (;;);')[-1]
        try:
            url = urllib.parse.unquote(json.loads(raw).get('url', ''))
        except Exception:
            url = ''
        return {'parse': 0, 'url': self.proxy(url), 'header': {'user-agent': self.headers['user-agent'], 'referer': f'{self.host}/embed/{vid}', 'origin': self.host}} if url else {'parse': 0, 'url': ''}

    def parse_videos(self, items):
        out = []
        for it in items.items():
            link = it.attr('href') or it('a').attr('href')
            title = re.sub(r'\s*(HoHoJ|\|).*$','', it('.video-title,.video-item-title').text() or it('img').attr('alt') or '').strip()
            if link and title: out.append({'vod_id': link, 'vod_name': title, 'vod_pic': self.proxy(it('img').attr('src')), 'vod_remarks': '', 'style': {'type': 'rect', 'ratio': 1.5}})
        return out

    def parse_folders(self, items):
        out = []
        for a in items.items():
            href = a.attr('href')
            if not href: continue
            spans = [s.text().strip() for s in a.find('span').items() if s.text().strip()]
            name = spans[0] if href.startswith('/actress') and spans else spans[-1] if spans else (a.text().strip().split('\n')[-1] or href.split('/')[-1])
            out.append({'vod_id': href, 'vod_name': name, 'vod_pic': self.proxy(a('img.actress-icon').attr('src') or a('img').attr('src')), 'vod_tag': 'folder', 'style': {'type': 'rect', 'ratio': .75}})
        return out