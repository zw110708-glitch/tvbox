import json
import re
import sys
from html import unescape
from urllib.parse import quote, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def init(self, extend=""):
        self.host = 'https://x6av.com'
        self.ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        self.s = requests.Session()
        self.proxies = {          "http": "http://127.0.0.1:10172",
          "https": "http://127.0.0.1:10172"}
        self.h = {
            'User-Agent': self.ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Referer': self.host + '/',
            'Origin': self.host,
        }

    def getName(self):
        return 'X6AV'

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|ts)(\?|$)', url or '', re.I))

    def manualVideoCheck(self):
        return False

    def _norm(self, url):
        url = unescape((url or '').strip()).replace('\\/', '/')
        if url.startswith('/streamtape.com/') or url.startswith('/tapewithadblock.org/'):
            return 'https:/' + url
        if url.startswith('//'):
            return 'https:' + url
        return url

    def _abs(self, url):
        url = self._norm(url)
        return url if url.startswith('http') else urljoin(self.host + '/', url)

    def _origin(self, url):
        parsed = urlparse(self._norm(url))
        return f'{parsed.scheme}://{parsed.netloc}' if parsed.scheme and parsed.netloc else self.host

    def _hdr(self, url='', referer=''):
        headers = dict(self.h)
        headers['Origin'] = self._origin(url or self.host)
        headers['Referer'] = referer or headers['Origin'].rstrip('/') + '/'
        return headers

    def _media_hdr(self, media_url='', page_url=''):
        path = urlparse(media_url or '').path or ''
        if re.search(r'\.m3u8$', path, re.I):
            accept = 'application/vnd.apple.mpegurl,application/x-mpegURL,*/*'
        elif re.search(r'\.(mp4|ts)$', path, re.I):
            accept = 'video/*,*/*'
        else:
            accept = '*/*'
        referer = page_url or self.host + '/'
        host = (urlparse(self._norm(referer)).hostname or '').lower()
        if re.search(r'(^|\.)upns\.live$', host):
            referer = 'https://7mmtv.upns.live/'
        return {
            'User-Agent': self.ua,
            'Accept': accept,
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Referer': referer,
        }

    def _get_resp(self, url, headers=None, timeout=10, allow_redirects=True, stream=False):
        resp = self.s.get(
            url,
            headers=headers or self.h,
            proxies=self.proxies,
            timeout=timeout,
            allow_redirects=allow_redirects,
            stream=stream,
        )
        resp.raise_for_status()
        return resp

    def _get_text(self, url, headers=None, timeout=10):
        resp = self._get_resp(url, headers=headers, timeout=timeout)
        resp.encoding = resp.apparent_encoding
        return resp.text

    def _post_text(self, url, data, timeout=10):
        headers = dict(self.h)
        headers.update({
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        })
        resp = self.s.post(url, headers=headers, data=data, proxies=self.proxies, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        return resp.text

    def _soup(self, html):
        return html if hasattr(html, 'select') else BeautifulSoup(html or '', 'lxml')

    def _cards(self, html):
        cards = []
        for block in self._soup(html).select('div.th'):
            title_link = block.select_one('a.th-description')
            image = block.select_one('div.th-image img')
            mark = block.select_one('span.th-duration') or block.select_one('span.th-hd')
            if not (title_link and title_link.get('href') and title_link.get_text(strip=True)):
                continue
            cards.append({
                'vod_id': self._abs(title_link.get('href')),
                'vod_name': title_link.get_text(strip=True),
                'vod_pic': 'http://127.0.0.1:10079/p/0/127.0.0.1:10172/'+self._abs(image.get('src', '')) if image else '',
                'vod_remarks': mark.get_text(strip=True) if mark else '',
                'style': {'type': 'rect', 'ratio': 1.33},
            })
        return cards

    def _cr(self, href, name):
        return '' if not href or not name else f"[a=cr:{json.dumps({'id': href, 'name': name}, ensure_ascii=False)}/]{name}[/a]"

    def _pagecount(self, html, key):
        pages = [int(x) for x in re.findall(r'page=(\d+)(?:&|&amp;)' + key, html or '')]
        return max(pages) + 1 if pages else 9999

    def _vid_cid(self, html):
        match = re.search(r'var\s+vid\s*=\s*(\d+)\s*,\s*cid\s*=\s*(\d+)', html or '', re.I)
        if not match:
            raise RuntimeError('详情页未找到 vid/cid')
        return int(match.group(1)), int(match.group(2))

    def _paths(self, html):
        paths, seen = [], set()
        for link in self._soup(html).select('div.video-actions a.show-modal[data-pathid]'):
            pid_text = link.get('data-pathid')
            if pid_text is None or not pid_text.isdigit():
                raise RuntimeError('详情页线路 pathid 非法')
            pid = int(pid_text)
            if pid in seen:
                continue
            seen.add(pid)
            name = re.sub(r'\s+', ' ', re.sub(r'\bServer\b', '', (link.select_one('span') or link).get_text(strip=True), flags=re.I).replace('#', '')).strip() or f'线路{pid + 1}'
            if re.fullmatch(r'SP(?:\s*\(\d+\))?', name, re.I):
                continue
            paths.append((pid, name))
        return paths

    def _flag_from_name(self, name):
        base = re.sub(r'\s+', '', re.sub(r'[（(]\s*\d+\s*[)）]', '', (name or '').strip()).upper())
        if 'STREAMTAPE' in base or base == 'ST':
            return 'ST'
        return base or 'X6AV'

    def _route_sid(self, cid, vid, pid_list):
        return f"x6avroute://{cid}/{vid}/" + ','.join(str(x) for x in pid_list)

    def _parse_route_sid(self, sid):
        match = re.match(r'^x6avroute://(\d+)/(\d+)/([\d,]+)$', sid or '')
        if not match:
            return None
        pid_list = [int(x) for x in match.group(3).split(',') if x]
        return (int(match.group(1)), int(match.group(2)), pid_list) if pid_list else None

    def _grouped_routes(self, cid, vid, paths):
        groups, order = {}, []
        for pid, name in paths:
            flag = self._flag_from_name(name)
            if flag not in groups:
                groups[flag] = []
                order.append(flag)
            groups[flag].append((pid, name))

        play_from, play_urls = [], []
        for flag in order:
            items = groups[flag]
            sid = self._route_sid(cid, vid, [pid for pid, _ in items])
            label = f'{flag} 1/{len(items)}' if len(items) > 1 else items[0][1]
            play_from.append(flag)
            play_urls.append(f"{label}${quote(sid, safe=':/?&=%,')}")
        return play_from, play_urls

    def _unpack(self, text):
        match = re.search(r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\(\s*'(?P<p>.*?)'\s*,\s*(?P<a>\d+)\s*,\s*(?P<c>\d+)\s*,\s*'(?P<k>.*?)'\.split\('\|'\)", text or '', re.S)
        if not match:
            return text
        packed = match.group('p')
        base = int(match.group('a'))
        words = match.group('k').split('|')
        digits = '0123456789abcdefghijklmnopqrstuvwxyz'

        def encode(n):
            out = ''
            while n:
                out, n = digits[n % base] + out, n // base
            return out or '0'

        for i in range(int(match.group('c')) - 1, -1, -1):
            if i < len(words) and words[i]:
                packed = re.sub(rf"\b{re.escape(encode(i))}\b", words[i], packed)
        return packed

    def _resolve_streamtape(self, page):
        page = self._norm(page)
        html = self._get_resp(page, self._hdr(page, self.host + '/'), 12).content.decode('utf-8', 'ignore')
        page_id = re.search(r'/e/([A-Za-z0-9]+)', page)
        expires_ip = re.search(r'expires=(\d+)&ip=([^&"\']+)', html)
        tokens = re.findall(r'token=([A-Za-z0-9_-]+)', html)
        if not (page_id and expires_ip and tokens):
            return ''
        api = f'https://streamtape.com/get_video?id={page_id.group(1)}&expires={expires_ip.group(1)}&ip={expires_ip.group(2)}&token={tokens[-1]}'
        resp = self._get_resp(api, self._hdr(api, page), 12, allow_redirects=False, stream=True)
        return self._norm(resp.headers.get('location') or resp.headers.get('Location') or '')

    def _resolve_hls(self, page):
        page = self._norm(page)
        unpacked = self._unpack(self._get_text(page, self._hdr(page, self.host + '/'), 12))
        match = re.search(r'https?://[^"\']+/(?:hls2|hls3|hls4)/[^"\']+master\.m3u8[^"\']*', unpacked, re.I)
        return self._norm(match.group(0)) if match else ''

    def _resolve_tv(self, page):
        page = self._norm(page)
        html = self._get_text(page, self._hdr(page, self.host + '/'), 12)
        match = re.search(r'data-hash=["\'](https?://[^"\']+turboviplay\.com/[^"\']+\.m3u8(?:\?[^"\']*)?)["\']', html, re.I)
        if not match:
            match = re.search(r"var\s+urlPlay\s*=\s*'(https?://[^']+turboviplay\.com/[^']+\.m3u8(?:\?[^']*)?)'", html, re.I)
        return self._norm(match.group(1)) if match else ''

    def _upns_key_iv(self, protocol, hostname):
        protocol = protocol or 'https:'
        hostname = hostname or '7mmtv.upns.live'
        prefix, base_num, one = '10', 110, 1
        key_text = ''.join(chr(int(prefix + d)) for d in str(ord('ᵟ'))) + chr(ord(protocol[1]))
        key_text += key_text[1:3] + chr(base_num) + chr(base_num - 1) + chr(base_num + 7)
        nums = list('3579')
        key_text += chr(int(nums[3] + nums[2]))
        key_text += chr(int(nums[1] + nums[2]))
        key_text += chr(int(str(int(nums[0]) * one + one) + nums[3])) * 2
        key_text += chr(int(nums[3]) * int(prefix) + int(nums[3]) * one)
        key_text += chr(int(''.join(reversed(nums))[:2]))

        scale = len(protocol) * len(protocol + '//')
        seed = '111'
        iv_text = ''.join(chr(k + scale) for k in range(1, 10))
        iv_text += chr(scale)
        iv_text += chr(int(seed))
        iv_text += chr(len(seed) * ord(hostname[1]))
        iv_text += chr(int(seed) + len(protocol))
        iv_text += chr(int(seed) + len(protocol) + 4)
        iv_text += chr(ord(protocol[1]))
        iv_text += chr(ord(protocol[1]) - 2)
        return bytes(ord(ch) & 255 for ch in key_text), bytes(ord(ch) & 255 for ch in iv_text)

    def _resolve_us(self, page):
        parsed = urlparse(self._norm(page))
        if not parsed.fragment or not re.search(r'(^|\.)upns\.live$', parsed.hostname or '', re.I):
            return ''
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad

        api = f'{parsed.scheme}://{parsed.netloc}/api/v1/video?id={parsed.fragment}'
        key, iv = self._upns_key_iv(parsed.scheme + ':', parsed.netloc)
        raw_hex = self._get_text(api, self._hdr(api, f'{parsed.scheme}://{parsed.netloc}/'), 12).strip()
        plaintext = unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(bytes.fromhex(raw_hex)), 16)
        match = re.search(r'"source"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', plaintext.decode('utf-8', 'ignore'))
        if not match:
            return ''
        return self._norm(bytes(match.group(1), 'utf-8').decode('unicode_escape').replace('Fttp', 'http', 1))

    def _play_mmsi_like(self, page_url):
        return self._resolve_hls(page_url)

    def _play_sp(self, page_url):
        return ''

    def _play_streamtape(self, page_url):
        return self._resolve_streamtape(page_url)

    def _play_upns(self, page_url):
        return self._resolve_us(page_url)

    def _tv_page_to_m3u8(self, page_url):
        return self._resolve_tv(page_url)

    def _play_resolve(self, flag, page_url):
        page_url = self._norm(page_url)
        if not page_url:
            return {'parse': 1, 'url': '', 'header': self._media_hdr('', self.host + '/')}
        if self.isVideoFormat(page_url):
            return {'parse': 0, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{page_url}', 'header': self._media_hdr(page_url, page_url)}

        f = (flag or '').strip().upper()
        try:
            if f in ('SW', 'VH'):
                final = self._play_mmsi_like(page_url)
            elif f == 'SP':
                final = self._play_sp(page_url)
            elif f == 'ST':
                final = self._play_streamtape(page_url)
            elif f == 'US':
                final = self._play_upns(page_url)
            elif f == 'TV':
                final = self._tv_page_to_m3u8(page_url)
            else:
                final = ''
        except Exception:
            final = ''

        if final and self.isVideoFormat(final):
            return {'parse': 0, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{final}', 'header': self._media_hdr(final, page_url)}
        return {'parse': 1, 'url': page_url, 'header': self._media_hdr(page_url, page_url)}

    def _player_api(self, cid, vid, pid):
        data = json.loads(self._post_text(urljoin(self.host + '/', 'e/DownSys/Player/'), {'classid': cid, 'id': vid, 'pathid': pid}))
        match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', data.get('player') or '', re.I)
        return self._norm(match.group(1)) if match else ''

    def homeContent(self, _filter):
        classes = [
            {'type_name': name, 'type_id': cid}
            for name, cid in [('有碼', '1'), ('無碼', '2'), ('素人', '3'), ('VR', '5'), ('歐美', '7'), ('中文字幕', '16'), ('熱門電影', 'popular')]
        ]
        return {'class': classes, 'filters': {}, 'list': self._cards(self._get_text(self.host + '/'))}

    def homeVideoContent(self):
        return {'list': self.homeContent(None).get('list', [])}

    def categoryContent(self, tid, pg, _filter, _extend):
        tid = str(tid or '').strip()
        page = int(pg or 1)
        if tid == 'popular':
            url = self.host + '/popular/' if page == 1 else ''
            pagecount = 1
        elif tid.startswith('/') or tid.startswith('http'):
            url = self._abs(tid)
            pagecount = 9999
            if page > 1:
                p = urlparse(url)
                q = re.sub(r'(^|&)page=\d+&?', r'\1', p.query).strip('&')
                if '/e/tags/' in p.path:
                    url = f'{self.host}/e/tags/index.php?page={page - 1}&{q}'
                elif '/e/action/ListInfo/' in p.path:
                    url = f'{self.host}/e/action/ListInfo/index.php?page={page - 1}&{q}'
        else:
            cid = int(tid)
            url = f'{self.host}/e/action/ListInfo/?classid={cid}' if page == 1 else f'{self.host}/e/action/ListInfo/index.php?page={page - 1}&classid={cid}'
            pagecount = None
        if not url:
            return {'list': [], 'page': page, 'pagecount': 1, 'limit': 90, 'total': 0}
        html = self._get_text(url)
        cards = self._cards(html)
        if pagecount is None:
            pagecount = self._pagecount(html, 'classid=' + str(int(tid)))
        return {'list': cards, 'page': page, 'pagecount': pagecount, 'limit': 90, 'total': 999999 if pagecount != 1 else len(cards)}

    def detailContent(self, ids):
        html = self._get_text(self._abs(ids[0]))
        soup = self._soup(html)
        title_node = soup.select_one('span.inner-title') or soup.select_one('title')
        info = soup.select_one('#av-data-info')
        studio = soup.select_one('div.tags a[href*="show=studio"]')
        tags = [
            self._cr(a.get('href'), (a.select_one('span.tag') or a).get_text(strip=True))
            for a in soup.select('div.tags a[href*="/e/tags/"]')
        ]
        vid, cid = self._vid_cid(html)
        play_from, play_urls = self._grouped_routes(cid, vid, self._paths(soup))
        if not play_from:
            return {'list': []}
        vod = {
            'vod_name': title_node.get_text(strip=True) if title_node else '',
            'vod_play_from': '$$$'.join(play_from),
            'vod_play_url': '$$$'.join(play_urls),
            'vod_content': ((('标签: ' + ' '.join(tags) + '\n') if tags else '') + (info.get_text(' ', strip=True) if info else '')),
        }
        if studio:
            vod['vod_director'] = self._cr(studio.get('href'), (studio.select_one('span.studio') or studio).get_text(strip=True))
        return {'list': [vod]}

    def searchContent(self, key, quick, pg='1'):
        page = int(pg or 1)
        data = {'keyboard': key, 'show': 'title', 'tempid': '1', 'tbname': 'news', 'mid': '1', 'dopost': 'search'}
        resp = self.s.post(
            urljoin(self.host + '/', 'e/search/index.php'),
            headers=self.h,
            data=data,
            proxies=self.proxies,
            timeout=10,
            allow_redirects=True,
        )
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        html = resp.text
        match = re.search(r'searchid=(\d+)', html)
        search_id = match.group(1) if match else ''
        if page > 1 and search_id:
            html = self._get_text(f'{self.host}/e/search/result/index.php?page={page - 1}&searchid={search_id}')
        return {'list': self._cards(html), 'page': page, 'pagecount': self._pagecount(html, 'searchid=' + search_id) if search_id else 9999}

    def _play_ok(self, url, header=None):
        def ck(method, u):
            r = method(u, headers=header or {}, timeout=8, stream=(method == self.s.get), allow_redirects=False, proxies={})
            if r.status_code in (200, 206):
                return True
            if r.status_code in (301, 302):
                loc = r.headers.get('location') or r.headers.get('Location')
                if loc:
                    r = method(urljoin(u, loc), headers=header or {}, timeout=8, stream=(method == self.s.get), allow_redirects=False, proxies={})
                    return r.status_code in (200, 206)
            return False
        try:
            if ck(self.s.head, url):
                return True
        except Exception:
            pass
        try:
            return ck(self.s.get, url)
        except Exception:
            return False

    def playerContent(self, flag, id, vipFlags):
        sid = self._norm(unquote(id or '').strip())
        route = self._parse_route_sid(sid)
        if not route:
            return self._play_resolve(flag, sid)
        cid, vid, pid_list = route
        fallback = {'parse': 1, 'url': '', 'header': self._media_hdr('', self.host + '/')}
        for pid in pid_list:
            page_url = self._player_api(cid, vid, pid)
            if not page_url:
                continue
            result = self._play_resolve(flag, page_url)
            if result.get('parse') == 0 and result.get('url') and self._play_ok(result['url'], result.get('header')):
                return result
            if not fallback.get('url'):
                fallback = result
        return fallback
