import base64
import hashlib
import json
import re
import sys
from urllib.parse import urljoin

import requests
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    host = 'https://hornyjav.com'
    ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

    def init(self, extend=''):
        self.proxies = json.loads(extend).get('proxy', {}) if extend else {}
        self.session = requests.Session()
        self.session.headers.update({'user-agent': self.ua, 'referer': self.host + '/'})

    def getName(self):
        return 'hornyjav'

    def _abs(self, u: str) -> str:
        if not u:
            return self.host
        return u if u.startswith(('http://', 'https://')) else urljoin(self.host + '/', u.lstrip('/'))

    def _page(self, base_url: str, pg: int) -> str:
        pg = int(pg)
        return base_url if pg <= 1 else (base_url.rstrip('/') + f'/page/{pg}/')

    def fetch(self, url, params=None, timeout=10):
        try:
            r = self.session.get(url, params=params, proxies=self.proxies, timeout=timeout)
            return r.text
        except Exception:
            return ''

    def homeContent(self, filter):
        html = self.fetch(self.host)
        return {
            'class': [
                {'type_name': '最新视频', 'type_id': '/'},
                {'type_name': '有码', 'type_id': '/category/censored/'},
                {'type_name': '無碼', 'type_id': '/category/reducing-mosaic/'},
                {'type_name': '英文字幕', 'type_id': '/category/english-subtitle/'},
                {'type_name': '女优', 'type_id': '/actors/'},
                {'type_name': '工作室', 'type_id': '/studios/'},
            ],
            'filters': {},
            'list': self.parse_videos(pq(html)('article.loop-video.thumb-block'))
        }

    def categoryContent(self, tid, pg, filter, extend):
        base_url = self._abs(tid)
        url = self._page(base_url, pg)
        params = extend.copy() if extend else None
        html = self.fetch(url, params=params)
        d = pq(html)

        tid_norm = (tid or '').rstrip('/')
        if tid_norm in ['/actors', '/studios']:
            items = d('article.thumb-block')
            lst = self.parse_cards(items)
        else:
            items = d('article.loop-video.thumb-block')
            lst = self.parse_videos(items)

        pagecount = d('.pagination a').length or 1
        return {'list': lst, 'page': pg, 'pagecount': pagecount, 'limit': 90, 'total': 999999}

    def detailContent(self, ids):
        url = self._abs(ids[0])
        html = self.fetch(url)
        d = pq(html)

        title = (d('h1').text() or d('title').text() or '').strip()

        play_urls = []
        m = re.search(r'data:text/javascript;base64,([A-Za-z0-9+/=]+)', html)
        if m:
            try:
                js = base64.b64decode(m.group(1)).decode('utf-8', 'ignore')
                m2 = re.search(r'defaultUrl\s*=\s*"(https?://[^"]+)"', js)
                if m2:
                    play_urls.append(m2.group(1).strip())
            except Exception:
                pass

        labels = []
        for a in d('.box-server a').items():
            v = (a.find('input').attr('value') or '').strip()
            if v:
                labels.append(v)
            onclick = a.attr('onclick') or ''
            m3 = re.search(r"atob\('([^']+)'\)", onclick)
            if not m3:
                continue
            try:
                u = base64.b64decode(m3.group(1)).decode('utf-8', 'ignore').strip()
                if u:
                    play_urls.append(u)
            except Exception:
                pass

        seen = set()
        play_urls = [u for u in play_urls if not (u in seen or seen.add(u))]

        play_list = []
        if labels and len(labels) == len(play_urls):
            for lab, u in zip(labels, play_urls):
                if lab.upper() != 'DB':
                    play_list.append(f'{lab}${u}')
        else:
            for i, u in enumerate(play_urls, 1):
                play_list.append(f'线路{i}${u}')

        vod = {
            'vod_name': title,
            'vod_play_from': 'hornyjav',
            'vod_play_url': '#'.join(play_list),
            'vod_pic': d('meta[property="og:image"]').attr('content') or d('meta[itemprop="thumbnailUrl"]').attr('content') or '',
            'vod_year': d('meta[property="article:published_time"]').attr('content') or d('meta[itemprop="uploadDate"]').attr('content') or ''
        }

        actors = []
        for a in d('#video-actors a[href*="/actor/"]').items():
            name = pq(f'<div>{a.text()}</div>').text().strip()
            href = a.attr('href')
            if name and href:
                actors.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')
        if actors:
            vod['vod_actor'] = ' '.join(actors)

        tags = []
        for a in d('.tags-list a').items():
            name = pq(f'<div>{a.text()}</div>').text().strip()
            href = a.attr('href')
            if name and href:
                tags.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')
        if tags:
            vod['vod_content'] = ' '.join(tags)

        st = d('#video-actors a[href*="/studios/"]').eq(0)
        if st:
            sname = pq(f'<div>{st.text()}</div>').text().strip()
            shref = st.attr('href')
            if sname and shref:
                vod['vod_director'] = f'[a=cr:{json.dumps({"id": shref, "name": sname})}/]{sname}[/a]'

        return {'list': [vod]}

    def searchContent(self, key, quick, pg='1'):
        params = {'s': key}
        if int(pg) > 1:
            params['paged'] = int(pg)
        html = self.fetch(self.host + '/', params=params)
        return {'list': self.parse_videos(pq(html)('article.loop-video.thumb-block')), 'page': pg}

    @staticmethod
    def _evp_bytes_to_key_md5(password: bytes, salt: bytes, key_len=32, iv_len=16):
        d = b''
        last = b''
        while len(d) < key_len + iv_len:
            last = hashlib.md5(last + password + salt).digest()
            d += last
        return d[:key_len], d[key_len:key_len + iv_len]

    @staticmethod
    def _extract_passphrase_from_pox(pox: str) -> str:
        m = re.search(r'\+\d([A-Za-z0-9]{10})\+', pox or '')
        return m.group(1) if m else ''

    def _decrypt_dp_to_media_url(self, pox: str, dp_b64: str) -> str:
        if not pox or not dp_b64:
            return ''
        passphrase = self._extract_passphrase_from_pox(pox)
        if not passphrase:
            return ''

        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import unpad

            dp_obj = json.loads(base64.b64decode(dp_b64 + '===').decode('utf-8', 'ignore'))
            ct = base64.b64decode(dp_obj['ct'])
            salt = bytes.fromhex(dp_obj.get('s', '') or '')
            iv_stored = bytes.fromhex(dp_obj.get('iv', '') or '')

            key, iv = self._evp_bytes_to_key_md5(passphrase.encode('utf-8'), salt)
            if iv_stored and iv != iv_stored:
                return ''

            plain = unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(ct), 16)
            media_url = json.loads(plain.decode('utf-8', 'ignore'))
            return media_url if isinstance(media_url, str) else ''
        except Exception:
            return ''

    def playerContent(self, flag, id, vipFlags):
        if not id or not id.startswith(('http://', 'https://')):
            return {'parse': 0, 'url': ''}

        try:
            html = self.session.get(id, proxies=self.proxies, timeout=20).text
        except Exception:
            return {'parse': 0, 'url': ''}

        m_pox = re.search(r"let\s+pox\s*=\s*'([^']+)'", html)
        m_dp = re.search(r"let\s+dp\s*=\s*'([^']+)'", html)
        if not (m_pox and m_dp):
            return {'parse': 0, 'url': ''}

        media_url = self._decrypt_dp_to_media_url(m_pox.group(1), m_dp.group(1))
        if not media_url:
            return {'parse': 0, 'url': ''}

        org_m = re.match(r'^(https?://[^/]+)', id)
        org = org_m.group(1) if org_m else ''
        return {
            'parse': 0,
            'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{media_url}',
            'header': {'user-agent': self.ua, 'referer': id, 'origin': org}
        }

    def parse_videos(self, items):
        out = []
        for i in items.items():
            a = i('a')
            link = a.attr('href')
            if not link:
                continue
            title = a.find('.entry-header span').text() or a.find('img').attr('alt') or ''
            title = pq(f'<div>{title}</div>').text().strip()
            if not title:
                continue
            img = a.find('img')
            pic = img.attr('data-src') or img.attr('src') or ''
            views = a.find('span.views').text().replace('\n', ' ').strip()
            duration = a.find('span.duration').text().replace('\n', ' ').strip()
            remarks = (views + ' ' + duration).strip()

            cls = i.attr('class') or ''
            vod_tag = '有码' if 'category-censored' in cls else ('无码' if 'category-reducing-mosaic' in cls else '')

            out.append({
                'vod_id': link,
                'vod_name': title,
                'vod_pic': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pic}',
                'vod_remarks': remarks,
                'vod_tag': vod_tag,
                'style': {'type': 'rect', 'ratio': 1.5}
            })
        return out

    def parse_cards(self, items):
        out = []
        for i in items.items():
            a = i('a')
            href = a.attr('href')
            if not href or ('/actor/' not in href and '/studios/' not in href):
                continue
            name = a.find('span.actor-title').text() or a.attr('title') or ''
            name = pq(f'<div>{name}</div>').text().strip()
            if not name:
                continue
            img = a.find('img')
            pic = img.attr('data-src') or img.attr('src') or ''
            out.append({
                'vod_id': href,
                'vod_name': name,
                'vod_pic': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pic}',
                'vod_tag': 'folder',
                'style': {'type': 'rect', 'ratio': 0.75}
            })
        return out

    def parse_models(self, items):
        return self.parse_cards(items)

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def homeVideoContent(self):
        pass

    def localProxy(self, param):
        pass

    def liveContent(self, url):
        pass
