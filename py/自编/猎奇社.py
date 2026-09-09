import json
import re
import sys
from urllib.parse import quote, unquote, urljoin

import requests
from Crypto.Cipher import AES
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    _KEY = b'f5d965df75336270'
    _IV = b'97b60394abc2fbe1'

    def init(self, extend=""):
        cfg = json.loads(extend) if isinstance(extend, str) and extend.strip() else (extend or {})
        self.host = (cfg.get('host') or 'https://lieqihub.com').rstrip('/')
        self.proxies = cfg.get('proxies') or {}
        self.headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': f'{self.host}/',
            'Origin': self.host,
        }

    def getName(self):
        return 'lieqihub'

    def isVideoFormat(self, url):
        u = (url or '').lower()
        return ('.m3u8' in u) or ('.mp4' in u)

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ---------------- proxy (image decrypt) ----------------

    def _decrypt_img(self, enc: bytes) -> bytes:
        pt = AES.new(self._KEY, AES.MODE_CBC, self._IV).decrypt(enc)
        # JPEG trim (NoPadding)
        if pt.startswith(b'\xff\xd8'):
            end = pt.rfind(b'\xff\xd9')
            return pt if end == -1 else pt[:end + 2]
        # PNG trim
        if pt.startswith(b'\x89PNG\r\n\x1a\n'):
            end = pt.rfind(b'IEND')
            return pt if end == -1 else pt[:end + 8]
        return pt

    def _mime(self, b: bytes) -> str:
        if b.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg'
        if b.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'image/png'
        if b[:4] == b'RIFF' and b[8:12] == b'WEBP':
            return 'image/webp'
        return 'application/octet-stream'

    def _pic(self, url: str) -> str:
        base = self.getProxyUrl()  # 框架提供
        return f"{base}{'&' if '?' in base else '?'}url={quote(url, safe='')}"

    def localProxy(self, param):
        url = unquote((param or {}).get('url') or '')
        if not url:
            return [400, 'text/plain', b'missing url']
        enc = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=20).content
        dec = self._decrypt_img(enc)
        return [200, self._mime(dec), dec]

    # ---------------- http/helpers ----------------

    def _get(self, url):
        r = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=12)
        r.encoding = r.apparent_encoding
        return r

    def _abs(self, href: str) -> str:
        return href if href.startswith('http') else urljoin(self.host + '/', href)

    # ---------------- list pages ----------------

    def homeContent(self, _):
        r = self._get(self.host)
        doc = pq(r.text)

        classes, seen = [], set()
        for a in doc('.nav-list a.nav-item').items():
            name = (a.text() or '').strip()
            href = (a.attr('href') or '').strip()
            if not name or not href.startswith('/cid/'):
                continue
            if name in ('首页', '标签云', '搜索', '登陆/注册', '登录', '注册'):
                continue
            tid = self._abs(href.rstrip('/') + '/')
            if tid in seen:
                continue
            seen.add(tid)
            classes.append({'type_name': name, 'type_id': tid})

        return {'class': classes, 'filters': {}, 'list': self._parse_list(doc)}

    def homeVideoContent(self):
        return {'list': self.homeContent(None)['list']}

    def categoryContent(self, tid, pg, *_):
        pg = int(pg or 1)
        base = (tid if str(tid).startswith('http') else self._abs(str(tid))).rstrip('/') + '/'
        url = base if pg == 1 else f'{base}{pg}/'
        doc = pq(self._get(url).text)
        return {'list': self._parse_list(doc), 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}

    def searchContent(self, key, quick, pg='1'):
        pg = int(pg or 1)
        url = f"{self.host}/?s={quote(key)}"
        if pg > 1:
            url = f"{url.rstrip('/')}/{pg}/"
        doc = pq(self._get(url).text)
        return {'list': self._parse_list(doc), 'page': pg, 'pagecount': 9999}

    def _parse_list(self, doc):
        out, seen = [], set()
        for card in doc('section.post-card-list-cloumn article.post-card-item').items():
            href = (card.find('a.post-card-item-img').attr('href') or '').strip()
            if not href.startswith('/post/'):
                continue
            vid = self._abs(href)
            if vid in seen:
                continue
            title = (card.find('h3.seo-hidden').text() or card.find('a[itemprop="description"]').text() or '').strip()
            img = (card.find('a.post-card-item-img img').attr('x-image-loader-url') or '').strip()
            if not title or not img:
                continue
            if img.startswith('//'):
                img = 'https:' + img
            seen.add(vid)
            out.append({'vod_id': vid, 'vod_name': title, 'vod_pic': self._pic(img), 'vod_remarks': ''})
            if len(out) >= 90:
                break
        return out

    # ---------------- detail/play ----------------

    def detailContent(self, ids):
        url = ids[0] if str(ids[0]).startswith('http') else self._abs(ids[0])
        r = self._get(url)
        doc = pq(r.text)

        title = (doc('h1').text() or doc('title').text()).strip()

        # actor(author) -> vod_director (clickable)
        an = (doc('.nav-user .title h2').text() or '').strip()
        ah = (doc('.nav-user a.title').attr('href') or '').strip()
        vod_director = ''
        if an and ah:
            ah = self._abs(ah)
            vod_director = f"[a=cr:{json.dumps({'id': ah, 'name': an}, ensure_ascii=False)}/]{an}[/a]"

        # tags + intro -> vod_content
        tags = []
        for a in doc('.tags-group2 a').items():
            n = (a.text() or '').strip()
            h = (a.attr('href') or '').strip()
            if n and h:
                h = self._abs(h)
                tags.append(f"[a=cr:{json.dumps({'id': h, 'name': n}, ensure_ascii=False)}/]{n}[/a]")
        intro_html = doc('div.text.text-content p').eq(0).html() or ''
        intro = re.sub(r'<br\s*/?>', '\n', intro_html, flags=re.I)
        intro = re.sub(r'<[^>]+>', '', intro).strip()
        vod_content = ('标签: ' + ' '.join(tags)).strip() if tags else ''
        if intro:
            vod_content = (vod_content + '\n\n' + intro).strip() if vod_content else intro

        # play url
        html = r.text
        m = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html, re.I) or re.search(r'(https?://[^\s"\']+\.mp4[^\s"\']*)', html, re.I)
        play_url = f"直链${m.group(1)}" if m else f"网页${url}"

        vod = {'vod_name': title, 'vod_play_from': '直链', 'vod_play_url': play_url}
        if vod_director:
            vod['vod_director'] = vod_director
        if vod_content:
            vod['vod_content'] = vod_content
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        return {'parse': 0, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{id}', 'header': self.headers} if self.isVideoFormat(id) else {'parse': 1, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{id}', 'header': self.headers}
