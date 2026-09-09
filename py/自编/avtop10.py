import json
import re
import sys
from base64 import b64decode, b64encode
from urllib.parse import urljoin, urlparse, quote

import requests
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    """AVTOP10 专用精简版：只保留【最高画质直链播放】与【封面代理】"""

    def init(self, extend=""):
        cfg = {}
        try:
            cfg = json.loads(extend) if isinstance(extend, str) else (extend or {})
        except Exception:
            cfg = {}

        self.proxies = cfg.get('proxies', {})
        self.host = (cfg.get('host', '') or '').strip().rstrip('/') or 'https://avtop10.com'

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Referer': f"{self.host}/",
        }

    def getName(self):
        return "AVTOP10-最高画质直链"

    # ---------- base64 helpers ----------
    def e64(self, text):
        return b64encode(str(text).encode()).decode()

    def d64(self, text):
        return b64decode(str(text).encode()).decode()

    # ---------- home/category ----------
    def homeContent(self, filter):
        try:
            r = requests.get(self.host, headers=self.headers, proxies=self.proxies, timeout=10)
            if r.status_code != 200:
                return {'class': [], 'filters': {}, 'list': []}
            r.encoding = r.apparent_encoding
            doc = self.getpq(r.text)

            classes = []
            # 只取页面里明确的分类链接（避免把“作品详情链接”当分类）
            for a in doc('nav a, .menu a, .nav a, .header a, .navbar-nav a, .category-list a').items():
                href = (a.attr('href') or '').strip()
                name = (a.text() or '').strip()
                if not href or not name:
                    continue
                if name in ['登录', '注册', '搜索', '首页']:
                    continue
                if not href.startswith('http'):
                    href = urljoin(self.host + '/', href)
                try:
                    p = urlparse(href)
                    if p.netloc and p.netloc != urlparse(self.host).netloc:
                        continue
                    href = p.path or '/'
                except Exception:
                    continue
                if href in ['/', '#']:
                    continue
                classes.append({'type_name': name, 'type_id': href})
                if len(classes) >= 25:
                    break

            # 首页列表
            videos = self.getlist(doc, 'a[href]:has(img)')
            return {'class': classes, 'filters': {}, 'list': videos}
        except Exception:
            return {'class': [], 'filters': {}, 'list': []}

    def homeVideoContent(self):
        return {'list': self.homeContent(None).get('list', [])}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg) if pg else 1
            url = tid if tid.startswith('http') else f"{self.host}{tid if tid.startswith('/') else '/' + tid}"
            url = url.rstrip('/')

            # AVTOP10 分页：?page=
            real_url = url if pg == 1 else f"{url}{'&' if '?' in url else '?'}page={pg}"

            r = requests.get(real_url, headers=self.headers, proxies=self.proxies, timeout=10)
            if r.status_code != 200:
                return {'list': [], 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 0}
            r.encoding = r.apparent_encoding
            doc = self.getpq(r.text)
            videos = self.getlist(doc, 'a[href]:has(img)')
            return {'list': videos, 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}
        except Exception:
            return {'list': [], 'page': 1, 'pagecount': 9999, 'limit': 90, 'total': 0}

    # ---------- packer decode (关键：必须能解出 surrit m3u8) ----------
    def _base_n(self, num: int, b: int) -> str:
        digits = "0123456789abcdefghijklmnopqrstuvwxyz"
        if num == 0:
            return "0"
        s = ""
        while num:
            s = digits[num % b] + s
            num //= b
        return s

    def _unpack_packer(self, p: str, a: int, c: int, k_list):
        if not p or not k_list:
            return ""
        p = p.replace("\\'", "'").replace('\\\\', '\\')
        for i in range(c - 1, -1, -1):
            key = self._base_n(i, a)
            val = k_list[i] if i < len(k_list) else ""
            if val:
                p = re.sub(rf"\b{re.escape(key)}\b", val, p)
        return p

    def _extract_packed_js(self, html_text: str):
        unpacked = []
        if not html_text:
            return unpacked
        pat = re.compile(
            r"eval\(function\(p,a,c,k,e,(?:d|r)\)\{.*?\}\(\s*'(?P<p>.*?)'\s*,\s*(?P<a>\d+)\s*,\s*(?P<c>\d+)\s*,\s*'(?P<k>.*?)'\.split\('\|'\)\s*,\s*0\s*,\s*\{\}\s*\)\)",
            re.S,
        )
        for m in pat.finditer(html_text):
            try:
                p = m.group('p')
                a = int(m.group('a'))
                c = int(m.group('c'))
                k_list = m.group('k').split('|')
                js = self._unpack_packer(p, a, c, k_list)
                if js:
                    unpacked.append(js)
            except Exception:
                pass
        return unpacked

    def _pick_best_m3u8(self, urls):
        """只选最高画质 video.m3u8（不返回 playlist.m3u8）"""
        q_urls = [u for u in urls if '/video.m3u8' in (u or '')]
        if not q_urls:
            return ''

        def rank(u: str) -> int:
            u = (u or '').lower()
            if '/1080p/' in u:
                return 1080
            if '/720p/' in u:
                return 720
            if '/842x480/' in u or '/480p/' in u:
                return 480
            if '/640x360/' in u or '/360p/' in u:
                return 360
            return 0

        q_urls.sort(key=rank, reverse=True)
        return q_urls[0]

    # ---------- detail/player ----------
    def detailContent(self, ids):
        try:
            url = ids[0] if ids[0].startswith('http') else f"{self.host}{ids[0]}"
            r = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=10)
            r.encoding = r.apparent_encoding
            html = r.text

            # 1) 解包取源
            packer_urls = []
            for js in self._extract_packed_js(html):
                packer_urls += re.findall(
                    r"['\"](https?://[^'\"\s<>]+\.(?:m3u8|mp4)[^'\"\s<>]*)['\"]",
                    js,
                    flags=re.I,
                )

            best = self._pick_best_m3u8(packer_urls)
            if not best:
                return {'list': [{'vod_play_from': 'AVTOP10', 'vod_play_url': '获取失败'}]}

            # 只返回 1 条最高画质
            play_url = f"最高画质${best}"

            doc = self.getpq(html)
            title = doc('h1').text().strip() or (doc('title').text().split('|')[0].strip() if doc('title') else '')
            return {'list': [{'vod_play_from': 'AVTOP10', 'vod_play_url': play_url, 'vod_name': title}]}
        except Exception:
            return {'list': [{'vod_play_from': 'AVTOP10', 'vod_play_url': '获取失败'}]}

    def playerContent(self, flag, id, vipFlags):
        # 直链播放（Fengmi 走 Hls.js 或系统播放器）
        return {'parse': 0, 'url': id, 'header': self.headers}

    # ---------- cover (关键：用本地代理转发，确保 Fengmi 能拉到) ----------
    def _pic_proxy(self, raw_url: str) -> str:
        return f"{self.getProxyUrl()}&type=imgraw&url={self.e64(raw_url)}"

    def localProxy(self, param):
        try:
            type_ = param.get('type')
            url = param.get('url')
            if type_ == 'imgraw':
                real_url = self.d64(url) if url and not url.startswith('http') else url
                h = {
                    'User-Agent': self.headers.get('User-Agent', 'Mozilla/5.0'),
                    'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
                    'Referer': real_url,
                }
                res = requests.get(real_url, headers=h, proxies=self.proxies, timeout=10, allow_redirects=True)
                ct = res.headers.get('Content-Type') or 'image/jpeg'
                return [200, ct, res.content]
        except Exception:
            pass
        return [404, 'text/plain', b'']

    # ---------- list parsing ----------
    def getlist(self, doc, selector, tid=''):
        videos = []
        seen = set()
        for a in doc(selector).items():
            href = (a.attr('href') or '').strip()
            if not href or href in ['#', '/']:
                continue
            if not href.startswith('http'):
                href = urljoin(self.host + '/', href)
            if href in seen:
                continue
            seen.add(href)

            # title
            title = (a.attr('title') or '').strip()
            if not title:
                title = (a('img').attr('alt') or '').strip()
            if not title:
                title = a.text().strip()
            if not title:
                continue

            # cover: 优先 src/data-src，其次按 dvd_id 反推
            img = (a('img').attr('src') or a('img').attr('data-src') or '').strip()
            if not img:
                try:
                    dvd_id = urlparse(href).path.strip('/').split('/')[0]
                    if dvd_id:
                        img = f"https://ig1.pppppppp.top/?url=https://fourhoi.com/{dvd_id}/cover-t.jpg"
                except Exception:
                    img = ''

            if img.startswith('data:'):
                img = ''

            if img:
                # Fengmi 兼容：封面统一走本地 imgraw 代理
                vod_pic = self._pic_proxy(img)
            else:
                vod_pic = ''

            videos.append({
                'vod_id': href,
                'vod_name': title,
                'vod_pic': vod_pic,
                'vod_remarks': '',
                'style': {"type": "rect", "ratio": 1.33},
            })
        return videos

    def getpq(self, data):
        try:
            return pq(data)
        except Exception:
            return pq(data.encode('utf-8', errors='ignore'))
