# -*- coding: utf-8 -*-
# 7mmtv (7mmtv.sx) —— OK影视 爬虫源
# 优化版：去掉播放前逐源 HEAD/GET 探测，直接返回首个解析成功的地址，播放秒开
import ast, base64, json, re, sys
from urllib.parse import quote, unquote, urljoin, urlparse

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    # 详情页 mvarr 加密数组前缀（数字 route id -> 线路标识）
    route_map = {'37': 'SW', '40': 'TV', '38': 'VH', '42': 'SP', '41': 'US', '29': 'ST'}
    route_order = ['SW', 'TV', 'VH', 'SP', 'US', 'ST']
    route_prefix_map = {v: k for k, v in route_map.items()}
    _SEL_VIDEOS = '.row.content .col-item .video'

    def init(self, extend=''):
        try:
            config = json.loads(extend) if extend else {}
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        self.host = config.get('site', 'https://7mmtv.sx')
        self.plp = config.get('plp', '')       # 播放器/封面地址前缀
        self.proxy = config.get('proxy', {})   # 内部请求代理
        self.headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'referer': self.host + '/',
        }
        self.s = requests.Session()

    def getName(self):
        return '7mmtv'

    def _origin(self, url):
        url = (url or '').strip()
        if url.startswith('//'):
            url = 'https:' + url
        p = urlparse(url)
        return f'{p.scheme}://{p.netloc}' if p.scheme and p.netloc else self.host

    def _req_headers(self, url, ref=None):
        url = (url or '').strip()
        if url.startswith('//'):
            url = 'https:' + url
        if '.m3u8' in url.lower():
            accept = 'application/vnd.apple.mpegurl,application/x-mpegURL,application/octet-stream,*/*'
        elif '.ts' in url.lower():
            accept = 'video/mp2t,application/octet-stream,*/*'
        elif '.mp4' in url.lower():
            accept = 'video/mp4,application/octet-stream,*/*'
        else:
            accept = '*/*'
        origin = self._origin(url)
        return {
            'User-Agent': self.headers['user-agent'],
            'Accept': accept,
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.6',
            'Connection': 'keep-alive',
            'Referer': ref or origin.rstrip('/') + '/',
            'Origin': origin,
        }

    def fetch(self, url, params=None, ref=None):
        try:
            r = self.s.get(url, headers=self._req_headers(url, ref), params=params, proxies=self.proxy, timeout=12)
            r.encoding = r.apparent_encoding
            return r.text
        except Exception:
            return ''

    def _get(self, url, ref=None, allow_redirects=True, timeout=12):
        try:
            return self.s.get(url, headers=self._req_headers(url, ref), proxies=self.proxy, timeout=timeout,
                              allow_redirects=allow_redirects)
        except Exception:
            return None

    def _doc(self, url=None, html=None):
        return pq(html if html is not None else self.fetch(url) if url else '')

    def _list(self, d):
        return self.parse_videos(d(self._SEL_VIDEOS))

    def _clickable(self, name, href):
        name = (name or '').strip()
        href = (href or '').strip()
        if not name:
            return ''
        if not href:
            return name
        hid = href.replace(self.host, '').lstrip('/')
        return f'[a=cr:{json.dumps({"id": hid, "name": name}, ensure_ascii=False)}/]{name}[/a]'

    # ---- mvarr 加密播放地址解析 ----
    def _crypto_conf(self, html):
        key = re.search(r"argdeqweqweqwe\s*=\s*['\"]([^'\"]+)", html)
        iv = re.search(r"hdddedg252\s*=\s*['\"]([^'\"]+)", html)
        base_n = re.search(r"hcdeedg252\s*=\s*(\d+)", html)
        xor_key = re.search(r"hadeedg252\s*=\s*(\d+)", html)
        return {
            'key': (key.group(1) if key else '').encode(),
            'iv': (iv.group(1) if iv else '').encode(),
            'base': int(base_n.group(1)) if base_n else 20,
            'xor': int(xor_key.group(1)) if xor_key else 13,
        }

    def _decode_token(self, token, conf):
        raw = ''.join(chr(int(x, conf['base']) ^ conf['xor']) for x in token.split(chr(conf['base'] + 97)) if x)
        data = AES.new(conf['key'], AES.MODE_CBC, conf['iv']).decrypt(base64.b64decode(raw.encode()))
        return data[:-data[-1]].decode('utf-8', 'ignore')

    def _build_play_url(self, mid, domain, tail):
        mid = (mid or '').strip()
        domain = (domain or '').strip()
        tail = (tail or '').strip()
        play = mid if domain == 'https://emturbovid.com/t/' else domain + mid + tail
        if play.startswith('//'):
            return 'https:' + play
        if play.startswith('http:/') and not play.startswith('http://'):
            return play.replace('http:/', 'http://', 1)
        if play.startswith('https:/') and not play.startswith('https://'):
            return play.replace('https:/', 'https://', 1)
        return play

    def _route_sid(self, page_urls):
        payload = json.dumps([u for u in page_urls if u], ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        return '7mmtvroute://' + base64.urlsafe_b64encode(payload).decode('ascii')

    def _parse_route_sid(self, sid):
        sid = (sid or '').strip()
        if not sid.startswith('7mmtvroute://'):
            return None
        try:
            data = sid.split('://', 1)[1].encode('ascii')
            data += b'=' * (-len(data) % 4)
            page_urls = json.loads(base64.urlsafe_b64decode(data).decode('utf-8'))
            return [u for u in page_urls if isinstance(u, str) and u.strip()]
        except Exception:
            return None

    def _route_order_from_html(self, html):
        order = []
        for flag in re.findall(r'jfun_show_([A-Z]+)\s*\(', html or ''):
            if flag in self.route_order and flag not in order:
                order.append(flag)
        return order or list(self.route_order)

    def _route_keys(self, html, flag):
        prefix = self.route_prefix_map.get(flag)
        if not prefix:
            return []
        m = re.search(rf"function\s+jfun_show_{flag}\s*\(\)\s*\{{(.*?)\}}", html or '', re.S)
        body = m.group(1) if m else ''
        keys = re.findall(r"jfun_show_mvinnerHTML\\\('([^']+)'\\\)", body)
        if not keys:
            keys = re.findall(r"jfun_show_mvinnerHTML\('([^']+)'\)", body)
        seen, out = set(), []
        for key in keys:
            if key.startswith(prefix + '_') and key not in seen:
                seen.add(key)
                out.append(key)
        return out

    def _parse_mvarr(self, html):
        conf = self._crypto_conf(html)
        page_map = {}
        for key, body in re.findall(r"mvarr\['(\d+_\d+)'\]\s*=\s*(\[.*?\]);", html, re.S):
            prefix = key.split('_', 1)[0]
            if prefix not in self.route_map:
                continue
            try:
                items = ast.literal_eval(body)
            except Exception:
                continue
            page_urls = []
            for item in items:
                if len(item) < 5:
                    continue
                try:
                    mid = self._decode_token(item[1], conf)
                except Exception:
                    continue
                play = self._build_play_url(mid, item[3], item[4])
                if play and play not in page_urls:
                    page_urls.append(play)
            if page_urls:
                page_map[key] = page_urls

        routes = []
        for flag in self._route_order_from_html(html):
            prefix = self.route_prefix_map[flag]
            ordered_keys, seen = [], set()
            for key in self._route_keys(html, flag):
                if key in page_map and key not in seen:
                    seen.add(key)
                    ordered_keys.append(key)
            for key in sorted((k for k in page_map if k.startswith(prefix + '_') and k not in seen),
                              key=lambda x: int(x.split('_', 1)[1])):
                ordered_keys.append(key)

            merged_urls, merged_seen = [], set()
            for key in ordered_keys:
                for page_url in page_map[key]:
                    if page_url not in merged_seen:
                        merged_seen.add(page_url)
                        merged_urls.append(page_url)
            if merged_urls:
                label = f'{flag} 1/{len(ordered_keys)}' if len(ordered_keys) > 1 else flag
                routes.append((flag, label, self._route_sid(merged_urls)))
        return routes

    # ---- 各线路播放地址二次解析 ----
    def _unpack_packer(self, text):
        if not text or 'eval(function' not in text:
            return ''
        m = re.search(r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\(\s*'(?P<p>.*?)'\s*,\s*(?P<a>\d+)\s*,\s*(?P<c>\d+)\s*,\s*'(?P<k>.*?)'\.split\('\|'\)", text, re.S)
        if not m:
            return ''
        payload = m.group('p')
        base = int(m.group('a'))
        count = int(m.group('c'))
        words = m.group('k').split('|')
        digits = '0123456789abcdefghijklmnopqrstuvwxyz'

        def encode(n):
            out = ''
            while n:
                out = digits[n % base] + out
                n //= base
            return out or '0'

        for i in range(count - 1, -1, -1):
            if i < len(words) and words[i]:
                payload = re.sub(rf"\b{re.escape(encode(i))}\b", words[i], payload)
        return payload

    def _direct_in_text(self, text):
        m = re.search(r"(https?:)?//[^\"'\s<>]+\.(?:m3u8|mp4)(?:\?[^\"'\s<>]*)?", text or '', re.I)
        if not m:
            return ''
        url = m.group(0)
        return 'https:' + url if url.startswith('//') else url

    def _play_mmsi_like(self, page_url):
        r = self._get(page_url, ref=page_url)
        if not r:
            return ''
        text = self._unpack_packer(r.text or '')
        if not text:
            return ''
        for pattern in [r'"hls2"\s*:\s*"([^"]+master\.m3u8[^"]*)"', r'"hls4"\s*:\s*"([^"]+master\.m3u8[^"]*)"']:
            m = re.search(pattern, text, re.I)
            if m:
                return urljoin(page_url, m.group(1))
        return ''

    def _play_streamtape(self, page_url):
        def norm(url):
            url = (url or '').strip()
            if not url:
                return ''
            if url.startswith('//'):
                return 'https:' + url
            if url.startswith('/streamtape.com/') or url.startswith('/tapewithadblock.org/'):
                return 'https:/' + url
            if url.startswith('/get_video?'):
                return 'https://streamtape.com' + url
            return 'https://streamtape.com' + url if url.startswith('/') else url

        page_url = norm(page_url)
        if not page_url:
            return ''
        if 'get_video?' in page_url:
            r = self._get(page_url, ref=page_url, allow_redirects=False)
            if r:
                loc = r.headers.get('location') or r.headers.get('Location')
                if loc:
                    return norm(loc)
            r = self._get(page_url, ref=page_url)
            return r.url if r and r.url else ''

        r = self._get(page_url, ref=page_url)
        if not r:
            return ''
        html = r.text or ''
        candidates = re.findall(r'<(?:div|span) id=["\'](?:ideoo|bot|robot)link["\'][^>]*>([^<]+)</(?:div|span)>', html, re.I)
        for expr in re.findall(r"document\.getElementById\(['\"](?:ideoo|bot|robot)link['\"]\)\.innerHTML\s*=\s*([^;]+);", html, re.I):
            parts = []
            for m in re.finditer(r"(['\"])(.*?)(\1)((?:\s*\)*\s*\.substring\(\d+\))*)", expr):
                part = m.group(2)
                for n in re.findall(r'\.substring\((\d+)\)', m.group(4)):
                    part = part[int(n):]
                parts.append(part)
            if parts:
                candidates.append(''.join(parts))
        for candidate in reversed([norm(x) for x in candidates if 'get_video?' in (x or '')]):
            r = self._get(candidate, ref=page_url, allow_redirects=False)
            if not r:
                continue
            loc = r.headers.get('location') or r.headers.get('Location')
            if not loc:
                continue
            loc = norm(loc)
            if 'get_video?' not in loc:
                return loc
            r2 = self._get(loc, ref=page_url, allow_redirects=False)
            if r2:
                loc2 = r2.headers.get('location') or r2.headers.get('Location')
                if loc2:
                    return norm(loc2)
        return ''

    def _bytes_low(self, s):
        return bytes([(ord(c) & 0xff) for c in (s or '')])

    def _upns_key_iv(self, protocol, hostname):
        protocol = protocol or 'https:'
        hostname = hostname or '7mmtv.upns.live'
        P, O, q = '10', 110, 1
        digits = list(str(ord('ᵟ')))
        F = ''.join(chr(int(P + d)) for d in digits)
        F += chr(ord(protocol[1]))
        F += F[1:3]
        F += chr(O) + chr(O - 1) + chr(O + 7)
        ae = list('3579')
        F += chr(int(ae[3] + ae[2]))
        F += chr(int(ae[1] + ae[2]))
        F += chr(int(str(int(ae[0]) * q + q) + ae[3]))
        F += chr(int(str(int(ae[0]) * q + q) + ae[3]))
        F += chr(int(ae[3]) * int(P) + int(ae[3]) * q)
        F += chr(int(''.join(reversed(ae))[:2]))
        key = self._bytes_low(F)
        S, P2 = protocol, protocol + '//'
        q2 = len(S) * len(P2)
        B = ''.join(chr(k + q2) for k in range(1, 10))
        ae2 = '111'
        hch = hostname[1] if len(hostname) > 1 else hostname[0]
        pe = len(ae2) * ord(hch)
        Je = int(ae2) + len(S)
        ne = ord(S[1])
        iv = self._bytes_low(B + chr(q2) + chr(int(ae2)) + chr(pe) + chr(Je) + chr(Je + 4) + chr(ne) + chr(ne - 2))
        return key, iv

    def _upns_decrypt(self, hex_text, protocol, hostname):
        try:
            data = bytes.fromhex((hex_text or '').strip())
            key, iv = self._upns_key_iv(protocol, hostname)
            pt = AES.new(key, AES.MODE_CBC, iv).decrypt(data)
            try:
                pt = unpad(pt, 16)
            except Exception:
                pt = pt.rstrip(b'\x00')
            return pt.decode('utf-8', 'ignore')
        except Exception:
            return ''

    def _extract_upns_source(self, text):
        text = text or ''
        if not text:
            return ''
        try:
            data = json.loads(text)
            source = data.get('source') or (data.get('video') or {}).get('source') or (data.get('player') or {}).get('source')
            if source:
                return source
        except Exception:
            pass
        patterns = [
            r'["\']source["\']\s*:\s*["\']([^"\']+\.(?:m3u8|mp4)(?:\?[^"\']*)?)["\']',
            r'(https?:\\?/\\?/[^"\'\s<>]+\.(?:m3u8|mp4)(?:\?[^"\'\s<>]*)?)',
            r'(Fttp:\\?/\\?/[^"\'\s<>]+\.(?:m3u8|mp4)(?:\?[^"\'\s<>]*)?)',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if m:
                return m.group(1)
        return ''

    def _normalize_media_url(self, url):
        url = (url or '').strip().strip('\\')
        if not url:
            return ''
        try:
            url = json.loads('"' + url.replace('"', '\\"') + '"')
        except Exception:
            url = url.replace('\\/', '/')
        url = url.replace('Fttp', 'http', 1).replace('Fttps', 'https', 1)
        if url.startswith('//'):
            url = 'https:' + url
        if url.startswith('http:/') and not url.startswith('http://'):
            url = url.replace('http:/', 'http://', 1)
        if url.startswith('https:/') and not url.startswith('https://'):
            url = url.replace('https:/', 'https://', 1)
        return url

    def _play_upns(self, src):
        u = urlparse(src if not (src or '').startswith('//') else 'https:' + src)
        vid = (u.fragment or '').strip()
        if not vid:
            m = re.search(r'[#/]([A-Za-z0-9_-]{4,})/?$', src or '')
            vid = m.group(1) if m else ''
        if not vid:
            return ''
        scheme = u.scheme or 'https'
        host = u.netloc or '7mmtv.upns.live'
        api = f"{scheme}://{host}/api/v1/video?id={vid}"
        refs = [f"{scheme}://{host}/", src, self.host + '/']
        for ref in refs:
            for _ in range(2):
                r = self._get(api, ref=ref, timeout=15)
                if not r or r.status_code >= 500:
                    continue
                plain = self._upns_decrypt(r.text or '', scheme + ':', host)
                final = self._normalize_media_url(self._extract_upns_source(plain))
                if final:
                    return final
        return ''

    def _tv_page_to_m3u8(self, page_url):
        current = page_url
        for _ in range(2):
            r = self._get(current, ref=page_url)
            if not r:
                return ''
            html = r.text or ''
            direct = self._direct_in_text(html)
            if direct and '.m3u8' in direct.lower():
                return direct
            m = re.search(r'<iframe[^>]+src=["\']([^"\']+)', html, re.I)
            if not m:
                return ''
            next_url = urljoin(r.url, m.group(1))
            if next_url == current:
                return ''
            current = next_url
        return ''

    def _play_sp(self, page_url):
        r = self._get(page_url, ref=page_url)
        if not r:
            return ''
        html = r.text or ''
        best_url, best_size = '', -1
        for m in re.finditer(r"src\s*:\s*['\"]([^'\"]+\.(?:m3u8|mp4)[^'\"]*)['\"][^\}]{0,300}?size\s*:\s*(\d+)", html, re.I | re.S):
            url = urljoin(page_url, m.group(1).strip())
            size = int(m.group(2)) if m.group(2).isdigit() else 0
            if size > best_size:
                best_url, best_size = url, size
        return best_url or self._direct_in_text(html)

    def _play_resolve(self, flag, page_url):
        if flag in ('SW', 'VH'):
            final = self._play_mmsi_like(page_url)
        elif flag == 'TV':
            final = self._tv_page_to_m3u8(page_url)
        elif flag == 'SP':
            final = self._play_sp(page_url)
        elif flag == 'US':
            final = self._play_upns(page_url)
        elif flag == 'ST':
            final = self._play_streamtape(page_url)
        else:
            final = ''
        if not final:
            return {'parse': 1, 'url': page_url, 'header': self._req_headers(page_url, page_url)}
        return {'parse': 0, 'url': self.plp + final, 'header': self._req_headers(final, page_url)}

    # ---- 对外接口 ----
    def homeContent(self, filter):
        d = self._doc(url=f'{self.host}/zh/')
        classes = []
        for a in d('.header-nav > li.nav-item > a.nav-link').items():
            name = a.text().strip()
            href = a.attr('href')
            if name and href and re.search(r'/(censored|uncensored|chinese|amateurjav|reducing-mosaic|amateur)_list/', href):
                classes.append({'type_name': name, 'type_id': href.replace(self.host + '/', '')})
        return {'class': classes, 'filters': {}, 'list': self._list(d)}

    def categoryContent(self, tid, pg, filter, extend):
        path = tid if tid.startswith('zh/') else f"zh/{tid.strip('/')}"
        if re.search(r'/\d+\.html$', path):
            path = re.sub(r'/\d+\.html$', f'/{pg}.html', path)
        d = self._doc(url=f'{self.host}/{path}')
        return {
            'list': self._list(d),
            'page': pg,
            'pagecount': max(d('.pagination-row .page-item').length, 1),
            'limit': 90,
            'total': 999999,
        }

    def searchContent(self, key, quick, pg='1'):
        return {'list': self._list(self._doc(url=f'{self.host}/zh/searchall_search/all/{quote(key)}/{pg}.html')), 'page': pg}

    def detailContent(self, ids):
        url = ids[0]
        if not url.startswith('http'):
            url = self.host + url if url.startswith('/') else f'{self.host}/{url}'
        html = self.fetch(url)
        d = self._doc(html=html)
        routes = self._parse_mvarr(html)
        if not routes:
            return {'list': []}

        tags = [self._clickable(a.text(), a.attr('href')) for a in d('.d-flex.flex-wrap.categories a').items()
                if a.text().strip() and a.attr('href')]
        intro = d('.video-introduction-images-text').text().strip()
        actors = []
        for idol in d('.fullvideo-idol').items():
            a = idol('a')
            href = a.attr('href') if a else ''
            name = (a.text().strip() if a else '') or idol('span').text().strip() or idol.text().strip()
            actors.append(self._clickable(name, href) if href else name)

        maker = issuer = director = ''
        for row in d('.row.flex-lg-nowrap.g-1').items():
            label = row('strong').text().strip().strip(':：')
            if label not in ('製作商', '發行商', '導演'):
                continue
            a = row('a')
            value = self._clickable(a.text().strip(), a.attr('href')) if a and a.attr('href') else row('.flex-grow-1').text().strip()
            if label == '製作商':
                maker = value
            elif label == '發行商':
                issuer = value
            else:
                director = value

        remarks = []
        if maker:
            remarks.append(f'製作商:{maker}')
        if issuer:
            remarks.append(f'發行商:{issuer}')

        content = ' '.join(x for x in tags if x).strip()
        if intro:
            content = (content + ' ' + intro).strip() if content else intro

        pic = d('meta[property="og:image"]').attr('content') or d('meta[name="thumbnail"]').attr('content') or ''
        return {'list': [{
            'vod_id': url.replace(self.host, ''),
            'vod_name': d('h1.block-title, h1').text().strip(),
            'vod_pic': self.plp + pic if pic else '',
            'vod_year': d('meta[itemprop="datePublished"]').attr('content') or '',
            'vod_actor': ' '.join(x for x in actors if x),
            'vod_content': content,
            'vod_remarks': ' '.join(remarks),
            'vod_director': director,
            'vod_play_from': '$$$'.join(flag for flag, _, _ in routes),
            'vod_play_url': '$$$'.join(f"{label}${quote(sid, safe=':/?&=%')}" for _, label, sid in routes),
        }]}

    def playerContent(self, flag, id, vipFlags):
        src = unquote(id or '').strip()
        page_urls = self._parse_route_sid(src)
        if not page_urls:
            play_url = src if src.startswith('http') else self.host + src if src.startswith('/') else f'{self.host}/{src}'
            return self._play_resolve(flag, play_url)
        # 多个备用源：逐个解析，第一个成功的立即返回（不再做 HEAD/GET 探测，秒开）
        fallback = {'parse': 1, 'url': '', 'header': self._req_headers('', self.host + '/')}
        for page_url in page_urls:
            result = self._play_resolve(flag, page_url)
            if result.get('parse') == 0 and result.get('url'):
                return result
            if not fallback['url']:
                fallback = result
        return fallback

    def parse_videos(self, items):
        out = []
        seen = set()
        for v in items.items():
            a = v('figure a').eq(0)
            href = a.attr('href')
            if not href:
                a = v('a').eq(0)
                href = a.attr('href')
            title = v('.video-title a').text().strip() or a.attr('title') or v('img').attr('alt') or ''
            if not href or not title or href in seen:
                continue
            seen.add(href)
            tag = ''
            if '/uncensored_' in href:
                tag = '無碼'
            elif '/reducing-mosaic_' in href:
                tag = '無碼破解'
            elif '/chinese_' in href:
                tag = '中字'
            elif '/censored_' in href:
                tag = '有碼'
            elif '/amateurjav_' in href:
                tag = '素人'
            pic = v('img').attr('data-src') or v('img').attr('src') or ''
            out.append({
                'vod_id': href.replace(self.host, ''),
                'vod_name': title,
                'vod_pic': self.plp + pic if pic else '',
                'vod_remarks': v('.small.text-muted').text().strip(),
                'vod_tag': tag,
                'style': {'type': 'rect', 'ratio': 1.5},
            })
        return out
