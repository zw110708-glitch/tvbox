import base64, json, re, sys, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urljoin, urlparse
import requests
try:
    from pyquery import PyQuery as pq
except Exception:
    pq = None
sys.path.append('..')
from base.spider import Spider as BaseSpider
class Spider(BaseSpider):
    NAV = ("https://x97.icu", "https://x97.one")
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    def init(self, extend=''):
        try: cfg = json.loads(extend) if isinstance(extend, str) and extend.strip() else (extend or {})
        except Exception: cfg = {}
        self.proxies = cfg.get('proxies') or {}
        self.host = self.base = ''
        self.locale = 'cn'
        self.headers = {'User-Agent': self.UA, 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'Accept-Language': 'zh-CN,zh;q=0.9', 'Connection': 'keep-alive'}
        self.s = requests.Session()
        self.s.headers.update(self.headers)
    def getName(self): return 'MissAV'
    def manualVideoCheck(self): return False
    def isVideoFormat(self, url): return '.m3u8' in (url or '').lower() or '.mp4' in (url or '').lower()
    def _apply_host(self, host):
        host = (host or '').rstrip('/')
        if not host: return False
        self.host = host
        u = urlparse(host)
        self.base = u.scheme + '://' + u.netloc
        self.locale = ((u.path or '').strip('/').split('/')[:1] or ['cn'])[0] or 'cn'
        self.headers.update({'Referer': host + '/', 'Origin': self.base})
        self.s.headers.update(self.headers)
        if u.hostname: self.s.cookies.set('x-index-auth', 'authed', domain=u.hostname, path='/')
        return True
    def _ensure_host(self):
        h = (self._best_host() or '').rstrip('/')
        return self._apply_host(h) if h else False
    def _abs(self, p):
        if not p or p.startswith('http'): return p or ''
        if not self.base: self._ensure_host()
        return urljoin(self.base + '/', p.lstrip('/')) if self.base else p
    def _get(self, url):
        if not self.base: self._ensure_host()
        r = self.s.get(url, proxies=self.proxies, timeout=15, allow_redirects=True)
        r.encoding = 'utf-8'
        return r.text or ''
    def _parse_pool(self, html):
        m = re.search(r"const\s+encodedData\s*=\s*'([^']+)'", html or '')
        if not m: return []
        try: data = json.loads(urllib.parse.unquote(base64.b64decode(m.group(1)).decode('utf-8', 'ignore')))
        except Exception: return []
        for it in data:
            if it.get('name') != 'MissAV': continue
            out, seen = [], set()
            for u in it.get('urls') or []:
                raw = (u.get('url') or '').strip().rstrip('/')
                if not raw: continue
                if not raw.startswith('http'): raw = 'https://' + raw.lstrip('/')
                p = urlparse(raw)
                host = p.scheme + '://' + p.netloc + (p.path or '').rstrip('/')
                test = (u.get('testUrl') or '').strip()
                if host and test and host not in seen:
                    seen.add(host); out.append({'host': host, 'test': test})
            return out
        return []
    def _probe(self, url, timeout):
        t0 = time.time()
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, proxies=self.proxies, timeout=timeout)
        if r.status_code == 200 and (r.text or '').strip().lower() == 'ok': return time.time() - t0
        return None
    def _best_host(self):
        h = {'User-Agent': 'Mozilla/5.0', 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'Accept-Language': 'zh-CN,zh;q=0.9'}
        pool = []
        for nav in self.NAV:
            try:
                r = requests.get(nav, headers=h, proxies=self.proxies, timeout=10, allow_redirects=True)
                pool = self._parse_pool(r.text or '')
                if pool: break
            except Exception: pass
        if not pool: return None
        best_h, best_t = None, 1e9
        with ThreadPoolExecutor(max_workers=min(16, len(pool))) as ex:
            futs = {ex.submit(self._probe, it['test'], 2.0): it['host'] for it in pool}
            for fut in as_completed(futs):
                try: t = fut.result()
                except Exception: continue
                if t is not None and t < best_t: best_h, best_t = futs[fut], t
        return best_h
    def _cards(self, html):
        out, seen = [], set()
        for cdn_num, cdn_dom, dvd in re.findall(r'data-src="https?://(imgcdn\d+)\.([^/]+)\.top/([^/]+)/cover-t\.jpg"', html or '', re.I):
            dvd = dvd.strip()
            if not dvd or dvd in seen: continue
            seen.add(dvd)
            pat = r'(?:data-src="https?://%s\.%s\.top/%s/cover-t\.jpg"[^>]*|[^>]*data-src="https?://%s\.%s\.top/%s/cover-t\.jpg")[^>]*alt="([^"]+)"' % (re.escape(cdn_num), re.escape(cdn_dom), re.escape(dvd), re.escape(cdn_num), re.escape(cdn_dom), re.escape(dvd))
            m = re.search(pat, html, re.I)
            out.append({'vod_id': self._abs('/%s/%s' % (self.locale, dvd)), 'vod_name': m.group(1).strip() if m else dvd, 'vod_pic': 'https://%s.%s.top/%s/cover-t.jpg' % (cdn_num, cdn_dom, dvd), 'vod_remarks': '', 'style': {"type": "rect", "ratio": 1.78}})
        return out
    def _unpack(self, text):
        m = re.search(r"\}\('\s*((?:\\'|[^'])*)\s*'\s*,\s*(\d+)\s*,\s*\d+\s*,\s*'([^']*)'\.split\('\|'\)\s*,\s*\d+\s*,\s*\{\}\s*\)", text or '', re.S)
        if not m: return ''
        payload, c, k = m.group(1), int(m.group(2)), (m.group(3) or '').split('|')
        CH = '0123456789abcdefghijklmnopqrstuvwxyz'
        def b36(n):
            if n == 0: return '0'
            s = ''
            while n: n, r = divmod(n, 36); s = CH[r] + s
            return s
        for i in range(c - 1, -1, -1):
            if i < len(k) and k[i]: payload = re.sub(r'\b%s\b' % re.escape(b36(i)), k[i], payload)
        return payload
    def _m3u8(self, html):
        ms = re.findall(r'https?://[^"\']+playlist\.m3u8[^"\']*', html or '')
        if not ms: ms = re.findall(r'https?://[^"\']+playlist\.m3u8[^"\']*', self._unpack(html or ''))
        if not ms: return ''
        p = urlparse(ms[0].rstrip('\\'))
        return self.base + '/jmpres/' + p.netloc + (p.path or '')
    def _play_headers(self):
        return {'User-Agent': self.UA, 'Accept': '*/*', 'Accept-Language': 'zh-CN,zh;q=0.9', 'Connection': 'keep-alive', 'Referer': (self.host + '/') if self.host else '', 'Origin': self.base or ''}
    def _cat_url(self, tid, pg):
        s = str(tid or '').strip()
        if s.startswith('http'): return s
        if not s.startswith('/'): s = '/%s/%s' % (self.locale, s.lstrip('/'))
        elif not re.match(r'^/[a-z]{2}(?:/|$)', s, re.I): s = '/%s%s' % (self.locale, s)
        url = self._abs(s)
        if 'page=' not in url: url += ('&' if '?' in url else '?') + 'page=%d' % int(pg or 1)
        return url
    def _nav_classes(self, html):
        classes = []
        seen = set()
        for href, text in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', html or ''):
            href = (href or '').strip()
            text = (text or '').strip()
            if not text or len(text) > 20 or not href: continue
            p = urlparse(href)
            path = (p.path or '').strip('/')
            if not path or path in seen: continue
            parts = path.split('/')
            if len(parts) < 2: continue
            tid = ''
            if parts[0] == self.locale and parts[1] and parts[1] not in ('vip', 'actresses', 'makers', 'genres', 'saved', 'playlists', 'history', 'klive', 'clive'):
                tid = '/'.join(parts[1:])
            elif len(parts) >= 3 and parts[1] == self.locale and parts[2] and not re.match(r'^dm\d+$', parts[0]):
                tid = '/'.join(parts[2:])
            elif re.match(r'^dm\d+$', parts[0]) and len(parts) >= 3 and parts[1] == self.locale:
                tid = '/'.join(parts[2:])
            if tid and tid not in seen:
                seen.add(tid)
                classes.append({'type_name': text, 'type_id': tid})
        return classes
    def homeContent(self, filter):
        self._ensure_host()
        html = self._get(self._cat_url('new', 1))
        classes = self._nav_classes(html)
        if not classes:
            classes = [{'type_name': '最新', 'type_id': 'new'}, {'type_name': '发行', 'type_id': 'release'}, {'type_name': 'FC2', 'type_id': 'fc2'}, {'type_name': 'VR', 'type_id': 'genres/VR'}]
        return {'class': classes, 'filters': {}, 'list': self._cards(html)}
    def homeVideoContent(self):
        return {'list': self.homeContent(None).get('list', [])}
    def categoryContent(self, tid, pg, filter, extend):
        self._ensure_host()
        pg = int(pg or 1)
        return {'list': self._cards(self._get(self._cat_url(tid, pg))), 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}
    def detailContent(self, ids):
        self._ensure_host()
        url = ids[0]
        url = url if str(url).startswith('http') else self._abs(str(url))
        html = self._get(url)
        m = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html, re.I)
        title = m.group(1).strip() if m else ''
        if not title:
            m = re.search(r'<title>(.*?)</title>', html, re.S | re.I)
            title = (m.group(1).split('|')[0].strip() if m else url)
        m = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html, re.I)
        pic = self._abs(m.group(1).strip()) if m else ''
        vod_year = type_name = vod_content = vod_actor = vod_director = vod_remarks = ''
        if pq:
            try:
                v = pq(html); c = v('.space-y-2 .text-secondary')
                MAP = {'导演:': 'dt', '发行商:': 'dt', '女优:': 'ac', '类型:': 'bq', '系列:': 'bq', '标籤:': 'cd'}
                bk = {'dt': [], 'ac': [], 'cd': [], 'bq': ['点击展开↓↓↓\n']}
                for item in c.items():
                    lb = item('span').text() or ''
                    b = next((MAP[k] for k in MAP if k in lb), None)
                    if b:
                        for j in item('a').items():
                            href = j.attr('href') or ''
                            name = j.text() or ''
                            p = urlparse(href)
                            path = (p.path or '').strip('/')
                            parts = path.split('/')
                            if re.match(r'^dm\d+$', parts[0]) and len(parts) >= 3 and parts[1] == self.locale:
                                link_id = '/'.join(parts[2:])
                            elif len(parts) >= 3 and parts[0] == self.locale:
                                link_id = '/'.join(parts[1:])
                            elif len(parts) >= 2:
                                link_id = parts[-1]
                            else:
                                link_id = parts[-1] if parts else ''
                            bk[b].append('[a=cr:' + json.dumps({'id': link_id, 'name': name}, ensure_ascii=False) + '/]' + name + '[/a]')
                try: type_name = c.eq(-3)('a').text()
                except Exception: pass
                try: vod_year = c.eq(0)('time').text()
                except Exception: pass
                vod_remarks = ' '.join(bk['cd']); vod_actor = ' '.join(bk['ac']); vod_director = ' '.join(bk['dt'])
                vod_content = '%s\n%s' % (' '.join(bk['bq']), v('.text-secondary.break-all').text())
            except Exception: pass
        m3u8 = self._m3u8(html)
        return {'list': [{'vod_id': url, 'vod_name': title, 'vod_pic': pic, 'type_name': type_name, 'vod_year': vod_year, 'vod_remarks': vod_remarks, 'vod_actor': vod_actor, 'vod_director': vod_director, 'vod_content': vod_content or '', 'vod_play_from': 'MissAV', 'vod_play_url': ('直链$%s' % m3u8) if m3u8 else ''}]}
    def searchContent(self, key, quick, pg='1'):
        self._ensure_host()
        pg = int(pg or 1)
        return {'list': self._cards(self._get(self._abs('/%s/search/%s?page=%d' % (self.locale, quote((key or '').strip()), pg)))), 'page': pg, 'pagecount': 9999}
    def playerContent(self, flag, id, vipFlags):
        return {'parse': 0, 'url': id, 'header': self._play_headers()}
