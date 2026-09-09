import json
import sys
from base64 import b64decode, b64encode
from html import unescape
from urllib.parse import quote, urljoin

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider as BaseSpider

IMG_AES_KEYS = [
    (b'f5d965df75336270', b'97b60394abc2fbe1'),
    (b'75336270f5d965df', b'abc2fbe197b60394'),
]


class Spider(BaseSpider):
    def init(self, extend=""):
        try:
            cfg = json.loads(extend) if isinstance(extend, str) and extend.strip() else (extend or {})
        except Exception:
            cfg = {}
        self.host = (cfg.get('host') or 'https://hl365.com').rstrip('/')
        self.plp = cfg.get('plp', '')
        self.proxy = cfg.get('proxy') or {}
        self.s = requests.Session()
        self.s.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Referer': f'{self.host}/',
        })

    def getName(self):
        return '黑料不打烊 hl365.com'

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        u = (url or '').lower()
        return '.m3u8' in u or '.mp4' in u

    def e64(self, text):
        return b64encode(str(text).encode()).decode()

    def d64(self, text):
        return b64decode(str(text).encode()).decode()

    def _get(self, url, timeout=10):
        r = self.s.get(url, proxies=self.proxy, timeout=timeout)
        r.encoding = r.apparent_encoding
        return r

    def _pq(self, html):
        try:
            return pq(html)
        except Exception:
            return pq(html.encode('utf-8', errors='ignore'))

    def _img_proxy(self, img_url):
        return f"{self.getProxyUrl()}&type=img&url={self.e64(img_url)}" if img_url else ''

    def _parse_list(self, doc):
        out, seen = [], set()
        for art in doc('article').items():
            a = art('a[href*="/archives/"]').eq(0)
            href = (a.attr('href') or '').strip()
            if not href:
                continue
            title = art('.post-card-bottom-text').text().strip() or art('.post-card-bottom-title').text().strip()
            if not title:
                continue
            vid = urljoin(self.host, href)
            if vid in seen:
                continue
            seen.add(vid)
            remark = art('[itemprop="datePublished"]').text().strip() or art('time').text().strip()
            img_el = art('img').eq(0)
            img = (img_el.attr('z-image-loader-url') or '').strip() if img_el else ''
            if not img:
                img = (art('meta[itemprop="image"]').attr('content') or '').strip()
            if img:
                if img.startswith('/'):
                    img = urljoin(self.host, img)
                out.append({
                    'vod_id': vid,
                    'vod_name': title,
                    'vod_pic': self._img_proxy(img),
                    'vod_remarks': remark,
                    'style': {"type": "rect", "ratio": 1.33},
                })
        return out

    def homeContent(self, filter):
        try:
            doc = self._pq(self._get(f'{self.host}/').text)
            classes, seen = [], set()
            for a in doc('nav a[href^="/category/"]').items():
                href = (a.attr('href') or '').strip()
                name = a.text().strip()
                if not href or not name or name == '首页' or href in seen:
                    continue
                seen.add(href)
                classes.append({'type_name': name, 'type_id': urljoin(self.host, href)})
            return {'class': classes, 'filters': {}, 'list': self._parse_list(doc)}
        except Exception:
            return {'class': [], 'filters': {}, 'list': []}

    def homeVideoContent(self):
        return {'list': self.homeContent(None).get('list', [])}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg or 1)
            base = tid if tid.startswith('http') else urljoin(self.host + '/', tid.lstrip('/'))
            if not base.endswith('/'):
                base += '/'
            url = base if pg == 1 else urljoin(base, f'{pg}/')
            doc = self._pq(self._get(url).text)
            next_link = doc('link[rel="next"]').attr('href')
            return {
                'list': self._parse_list(doc),
                'page': pg,
                'pagecount': pg + 1 if next_link else pg,
                'limit': 30,
                'total': 999999,
            }
        except Exception:
            pg = int(pg or 1)
            return {'list': [], 'page': pg, 'pagecount': pg, 'limit': 30, 'total': 0}

    def searchContent(self, key, quick, pg='1'):
        try:
            pg = int(pg or 1)
            base = f'{self.host}/search/{quote(key)}/'
            url = base if pg == 1 else urljoin(base, f'{pg}/')
            doc = self._pq(self._get(url).text)
            next_link = doc('link[rel="next"]').attr('href')
            return {'list': self._parse_list(doc), 'page': pg, 'pagecount': pg + 1 if next_link else pg}
        except Exception:
            pg = int(pg or 1)
            return {'list': [], 'page': pg, 'pagecount': pg}

    def detailContent(self, ids):
        try:
            url = ids[0]
            if not url.startswith('http'):
                url = urljoin(self.host, url)
            doc = self._pq(self._get(url).text)
            title = (doc('meta[property="og:title"]').attr('content') or doc('title').text() or '').strip()
            desc = (doc('meta[property="og:description"]').attr('content') or '').strip()
            tags = []
            for a in doc('div[itemprop="keywords"].keywords a').items():
                name = a.text().strip()
                href = (a.attr('href') or '').strip()
                if name and href:
                    href = urljoin(self.host, href)
                    tags.append(f'[a=cr:{json.dumps({"id": href, "name": name}, ensure_ascii=False)}/]{name}[/a]')
            tag_line = ('标签: ' + ' '.join(tags)) if tags else ''
            plays, seen = [], set()
            for el in doc('[data-config]').items():
                raw = el.attr('data-config')
                if not raw:
                    continue
                raw = unescape(raw).replace('&quot;', '"').replace('&amp;', '&')
                try:
                    conf = json.loads(raw)
                except Exception:
                    continue
                u = (conf.get('video') or {}).get('url') or ''
                if u and u not in seen:
                    seen.add(u)
                    plays.append(u)
            play_url = '#'.join([f'播放{i+1}${u}' for i, u in enumerate(plays)])
            vod_content = tag_line + (('\n' + desc) if (tag_line and desc) else desc)
            return {'list': [{'vod_name': title, 'vod_play_from': '直链', 'vod_play_url': play_url, 'vod_content': vod_content}]}
        except Exception:
            return {'list': [{'vod_play_from': '直链', 'vod_play_url': ''}]}

    def playerContent(self, flag, id, vipFlags):
        return {'parse': 0 if self.isVideoFormat(id) else 1, 'url': f'{self.plp}{id}', 'header': dict(self.s.headers)}

    def localProxy(self, param):
        try:
            if (param.get('type') or '') != 'img':
                return [404, 'text/plain', b'']
            url = self.d64(param.get('url') or '')
            if not url:
                return [404, 'text/plain', b'']
            raw = self.s.get(url, proxies=self.proxy, timeout=10).content
            dec = self._aesimg(raw)
            if dec.startswith(b'\x89PNG'):
                return [200, 'image/png', dec]
            if dec.startswith(b'GIF8'):
                return [200, 'image/gif', dec]
            return [200, 'image/jpeg', dec]
        except Exception:
            return [404, 'text/plain', b'']

    def _aesimg(self, data):
        if not data or len(data) < 16:
            return data
        if data.startswith(b'\xff\xd8') or data.startswith(b'\x89PNG') or data.startswith(b'GIF8'):
            return data
        for key, iv in IMG_AES_KEYS:
            try:
                dec = unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(data), 16)
                if dec.startswith(b'\xff\xd8') or dec.startswith(b'\x89PNG') or dec.startswith(b'GIF8'):
                    return dec
            except Exception:
                pass
            try:
                dec = unpad(AES.new(key, AES.MODE_ECB).decrypt(data), 16)
                if dec.startswith(b'\xff\xd8') or dec.startswith(b'\x89PNG') or dec.startswith(b'GIF8'):
                    return dec
            except Exception:
                pass
        return data
