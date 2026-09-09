# -- coding: utf-8 --
# hornyjav.com spider

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
    headers = {'user-agent': ua, 'referer': host + '/'}

    def init(self, extend=''):
        self.proxies = json.loads(extend).get('proxy', {}) if extend else {}

    def getName(self):
        return 'hornyjav'

    def _abs(self, u: str) -> str:
        if not u:
            return self.host
        return u if u.startswith(('http://', 'https://')) else urljoin(self.host + '/', u.lstrip('/'))

    def _page(self, base_url: str, pg: int) -> str:
        pg = int(pg)
        if pg <= 1:
            return base_url
        return (base_url.rstrip('/') + f'/page/{pg}/')

    def fetch(self, url, params=None):
        try:
            return requests.get(url, headers=self.headers, params=params, proxies=self.proxies, timeout=10).text
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
        items = d('article.thumb-block') if tid_norm in ['/actors', '/studios'] else d('article.loop-video.thumb-block')
        lst = self.parse_cards(items) if tid_norm in ['/actors', '/studios'] else self.parse_videos(items)

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

        # 去重
        seen = set()
        play_urls = [u for u in play_urls if not (u in seen or seen.add(u))]

        play_list = []
        if labels and len(labels) == len(play_urls):
            pairs = [(lab, u) for lab, u in zip(labels, play_urls) if lab.upper() != 'DB']  # 屏蔽 DB
            for lab, u in pairs:
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

    def playerContent(self, flag, id, vipFlags):
        if not id or not id.startswith(('http://', 'https://')):
            return {'parse': 0, 'url': ''}

        try:
            html = requests.get(
                id,
                headers={'user-agent': self.ua, 'referer': self.host + '/'},
                proxies=self.proxies,
                timeout=20
            ).text
        except Exception:
            return {'parse': 0, 'url': ''}

        m_pox = re.search(r"let\s+pox\s*=\s*'([^']+)'", html)
        m_dp = re.search(r"let\s+dp\s*=\s*'([^']+)'", html)
        if not (m_pox and m_dp):
            return {'parse': 0, 'url': ''}

        pox = m_pox.group(1)
        dp_b64 = m_dp.group(1)

        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import unpad

            dp_obj = json.loads(base64.b64decode(dp_b64 + '===').decode('utf-8', 'ignore'))
            ct = base64.b64decode(dp_obj['ct'])
            salt = bytes.fromhex(dp_obj.get('s', '') or '')
            iv_stored = bytes.fromhex(dp_obj.get('iv', '') or '')

            def evp(passphrase: bytes, salt_bytes: bytes, key_len=32, iv_len=16):
                d = b''
                last = b''
                while len(d) < key_len + iv_len:
                    last = hashlib.md5(last + passphrase + salt_bytes).digest()
                    d += last
                return d[:key_len], d[key_len:key_len + iv_len]

            parts = [p for p in pox.split('+') if p]
            cands, seen = [], set()
            for p in parts:
                for c in (p, p[1:] if len(p) > 1 else ''):
                    if c and c not in seen:
                        seen.add(c)
                        cands.append(c)

            key = iv = None
            for cand in cands:
                k, v = evp(cand.encode('utf-8'), salt)
                if iv_stored and v == iv_stored:
                    key, iv = k, v
                    break
            if key is None:
                key, iv = evp(cands[0].encode('utf-8'), salt)

            media_url = json.loads(unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(ct), 16).decode('utf-8', 'ignore'))
            if not isinstance(media_url, str):
                return {'parse': 0, 'url': ''}

            org = re.match(r'^(https?://[^/]+)', id)
            org = org.group(1) if org else ''
            return {
                'parse': 0,
                'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{media_url}',
                'header': {'user-agent': self.ua, 'referer': id, 'origin': org}
            }
        except Exception:
            return {'parse': 0, 'url': ''}

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
            remarks = ' '.join([x for x in (views, duration) if x])

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
