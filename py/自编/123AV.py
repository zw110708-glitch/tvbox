# 极简版：按 123AV 当前结构提取 javplayer 播放流
# 结构：详情页 player(JSON.parse(...)) -> javplayer.cc/e/<id> -> /stream?id=<id>

import base64
import gzip
import json
import re
import sys
from base64 import b64decode
from urllib.parse import quote, unquote, urlparse

import requests
from pyquery import PyQuery as pq

# 兼容沙箱独立验证：没有 TVBox 的 base.spider 时提供最小实现
try:
    sys.path.append('..')
    from base.spider import Spider as _BaseSpider  # type: ignore
except Exception:  # pragma: no cover

    class _BaseSpider:  # 最小化桩：只用于本沙箱验证
        def getProxyUrl(self):
            return ''


class Spider(_BaseSpider):
    host = 'https://123av.com'
    contr = 'cn'

    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
    }

    gcate = 'H4sIAAAAAAAAA6tWejan4dm0DUpWCkp5qeVKOkrPm9e+nL4CxM/ILwHygfIv9k8E8YtSk1PzwELTFzxf0AgSKs0DChXnF6WmwIWfbW55OWcTqqRuTmpiNljN8427n3asBsmmp+YVpRaDtO2Z8nTiDJBQYnIJUKgYLPq0Y9uTvXOeTm0DSeQCdReBRJ9vBmqfDhIqTi3KhGhf0P587T6QUElierFSLQCk4MAf0gAAAA=='
    flts = 'H4sIAAAAAAAAA23QwYrCMBAG4FeRnH0CX0WKBDJiMRpoY0WkIOtFXLQU1IoEFFHWw4qHPazgii/TRPctNKK1Ro/zz8cM/PkmKkMD5TLIZQ5HWVTFFUiNHqY1PeebyNOxAxSwCwWCOWitMxmEcttW0VKJKfKzN4kJAfLk1O9OdmemKzF+B8f2+j9aPVacEdwoeDbU3TuJd93LgdPXx1F8PmAdoEwNqTaBDFemrLAqL72hSnReqcuvDkgCRUsGkfqenw59AxaxxxybP9uRuFjkW5reai7alIOTKjoJzKoxpUnDvWG8bcnlj/obyHCcKi95JxeTeN9LEcu3zoYr9GndAQAA'

    def init(self, extend='{}'):
        c = json.loads(extend) if extend else {}
        self.plp = c.get('plp', '')
        self.proxy = c.get('proxy') or {}
        self.conh = f'{self.host}/{self.contr}'
        self._home_cache = None

        self.s = requests.Session()
        ad = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=50, max_retries=0)
        self.s.mount('http://', ad)
        self.s.mount('https://', ad)

    def destroy(self):
        try:
            self.s.close()
        except Exception:
            pass

    def getName(self):
        return 'JAVxx(123av-极简代理版)'

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def homeVideoContent(self):
        return {}

    def homeContent(self, filter):
        if self._home_cache is None:
            html = self.s.get(
                self.conh,
                headers={**self.headers, 'referer': f'{self.conh}/'},
                proxies=self.proxy,
                timeout=10,
                verify=False,
            ).text
            doc = self.getpq(html)

            cate = self.ungzip(self.gcate)
            skip = {'genres', 'makers', 'series', 'actresses', 'tags'}

            classes = []
            filters = {}
            for k, j in cate.items():
                if j in skip:
                    continue
                classes.append({'type_name': k, 'type_id': j})
                filters[j] = self.ungzip(self.flts)

            self._home_cache = {'class': classes, 'filters': filters, 'list': self.getvl(doc('.card'))}
        return self._home_cache

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        extend = extend or {}
        tid = tid.replace(f'/{self.contr}/', '')

        params = {k: v for k, v in {'filter': extend.get('filter'), 'sort': extend.get('sort'), 'page': pg}.items() if v}
        doc = self.getpq(
            self.s.get(
                f'{self.conh}/{tid}',
                params=params,
                headers={**self.headers, 'referer': f'{self.conh}/'},
                proxies=self.proxy,
                timeout=10,
                verify=False,
            ).text
        )
        return {'list': self.getvl(doc('.card')), 'page': pg, 'pagecount': self.getpgc_doc(doc), 'limit': 90, 'total': 999999}

    def searchContent(self, key, quick, pg='1'):
        pg = int(pg or 1)
        doc = self.getpq(
            self.s.get(
                f'{self.conh}/search',
                params={'keyword': key, 'page': pg},
                headers={**self.headers, 'referer': f'{self.conh}/'},
                proxies=self.proxy,
                timeout=10,
                verify=False,
            ).text
        )
        return {'list': self.getvl(doc('.card')), 'page': pg, 'pagecount': self.getpgc_doc(doc), 'limit': 90, 'total': 999999}

    def detailContent(self, ids):
        u = ids[0]
        if isinstance(u, str) and u.startswith('/'):
            u = f'{self.host}{u}'

        html0 = self.s.get(
            u,
            headers={**self.headers, 'referer': f'{self.conh}/'},
            proxies=self.proxy,
            timeout=10,
            verify=False,
        ).text
        doc = self.getpq(html0)

        src = self._ep0_html(html0)

        title = (doc('h1.watch__title').text() or doc('title').text() or '').strip()
        content = (doc('.watch__desc-text').text() or '').strip()

        pnpn = {}
        if src:
            pnpn['播放'] = f"{title or '播放'}${src}"

        vs = []
        for a in doc('a.watch__version').items():
            t = (a.text() or '').strip()
            h = (a.attr('href') or '').strip()
            if t and h:
                vs.append(f'{t}$_gggb_{h}')
        if vs:
            pnpn['版本切换'] = '#'.join(vs)

        vod = {
            'vod_content': content,
            'vod_play_from': '$$$'.join([k for k, v in pnpn.items() if v]),
            'vod_play_url': '$$$'.join([v for k, v in pnpn.items() if v]),
        }

        a, b, c, d = [], [], [], []
        for row in doc('.watch__info-row').items():
            lab = (row('dt').text() or '').strip()
            if re.search(r'发布日期', lab):
                vod['vod_year'] = (row('dd').text() or '').strip()
                continue

            items = []
            for j in row('dd a').items():
                name = (j.text() or '').strip()
                href = (j.attr('href') or '').strip()
                if name and href:
                    items.append('[a=cr:' + json.dumps({'id': href, 'name': name}) + '/]' + name + '[/a]')

            if not items:
                continue
            if re.search(r'演员', lab):
                a.extend(items)
            elif re.search(r'制作商|系列', lab):
                b.extend(items)
            elif re.search(r'标签', lab):
                c.extend(items)
            elif re.search(r'类别', lab):
                d.extend(items)

        vod.update(
            {
                'vod_actor': ' '.join(a),
                'vod_director': ' '.join(b),
                'vod_remarks': ' '.join(c),
                'vod_content': ' '.join(d) + ('\n' if d and content else '') + vod.get('vod_content', ''),
            }
        )

        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        u = (id or '').strip() if isinstance(id, str) else ''

        if u.startswith('_gggb_'):
            p = u.replace('_gggb_', '')
            page = f'{self.host}{p}' if p.startswith('/') else f'{self.host}/{p.lstrip("/")}'
            html1 = self.s.get(
                page,
                headers={**self.headers, 'referer': f'{self.conh}/'},
                timeout=10,
                verify=False,
                proxies=self.proxy,
            ).text
            u = self._ep0_html(html1)

        stream = self._javplayer_stream(u)
        ref = 'https://javplayer.cc/'
        return {'parse': 0, 'url': self._media_proxy(stream, ref, 'm3u8'), 'header': self._play_headers(ref)}

    def getvl(self, data):
        vids = []
        for it in data.items():
            href = (it('a.card__cover').attr('href') or it('a').attr('href') or '').strip()
            if (not href) or ('/v/' not in href):
                continue

            title = (it('.card__title').text() or it('.card__link').text() or it('h3').text() or '').strip()
            img = (it('img').attr('src') or '').strip()
            if img:
                img = img.replace('/s360/', '/s720/')
                if img.startswith('//'):
                    img = 'https:' + img
                elif img.startswith('/'):
                    img = self.host + img
                img = f'{self.plp}{img}'

            vids.append(
                {
                    'vod_id': href.split('#', 1)[0],
                    'vod_name': title,
                    'vod_pic': img,
                    'vod_remarks': (it('.card__dur').text() or it('.duration').text() or '').strip(),
                    'style': {'type': 'rect', 'ratio': 1.33},
                }
            )
        return vids

    def getpgc_doc(self, doc):
        try:
            pages = []
            for a in doc('a[href*="page="]').items():
                href = (a.attr('href') or '').strip()
                m = re.search(r'[?&]page=(\d+)', href)
                if m:
                    pages.append(int(m.group(1)))
            if not pages:
                pages = [int(x) for x in re.findall(r'[?&]page=(\d+)', doc.html() or '')[:200]]
            return max(pages) if pages else 1
        except Exception:
            return 1

    def _ep0_html(self, html):
        m = re.search(r'x-data="player\(JSON\.parse\(\'([\s\S]*?)\'\)', html or '', flags=re.S)
        raw = m.group(1).encode('utf-8').decode('unicode_escape').replace('\\/', '/')
        return json.loads(raw)[0]['url'].strip()

    def _javplayer_stream(self, u):
        p = urlparse(u)
        vid = p.path.rstrip('/').split('/')[-1]
        api = f'{p.scheme}://{p.netloc}/stream?id={quote(vid, safe="")}'
        if p.query:
            api += '&' + p.query
        j = self.s.get(
            api,
            headers={**self.headers, 'referer': u},
            timeout=10,
            verify=False,
            proxies=self.proxy,
        ).json()
        return j['media']['stream'].strip()

    def _root_ref(self, u):
        try:
            p = urlparse(u)
            return f'{p.scheme}://{p.netloc}/'
        except Exception:
            return ''

    def _is_direct_video(self, u):
        if not u:
            return False
        try:
            p = (urlparse(u).path or '').lower()
        except Exception:
            p = (u or '').lower()
        return ('.m3u8' in p) or ('.mp4' in p)

    def _play_headers(self, ref=''):
        h = dict(self.headers)
        if ref:
            h['Referer'] = ref
            try:
                p = urlparse(ref)
                h['Origin'] = f'{p.scheme}://{p.netloc}'
            except Exception:
                pass
        return h

    def e64(self, t):
        return quote(base64.b64encode(str(t).encode()).decode(), safe='')

    def d64(self, t):
        return base64.b64decode(unquote(str(t)).encode()).decode('utf-8', 'ignore')

    def _safe_d64(self, t):
        try:
            return self.d64(t)
        except Exception:
            return ''

    def _media_proxy(self, u, ref='', type_='m3u8'):
        p = self.getProxyUrl()
        if not p:
            return u
        s = f'{p}&type={type_}&url={self.e64(u)}'
        return s + (f'&ref={self.e64(ref)}' if ref else '')

    def localProxy(self, param):
        try:
            t = (param.get('type') or '').strip()
            u = param.get('url')
            if (not t) or (not u):
                return [404, 'text/plain', b'']

            real = self._safe_d64(u)
            if not real:
                return [404, 'text/plain', b'']

            ref = self._safe_d64(param.get('ref')) if param.get('ref') else ''
            ref = ref or self._root_ref(real)

            if t == 'auto':
                p = (urlparse(real).path or '').lower()
                if '.m3u8' in p:
                    t = 'm3u8'
                elif p.endswith('.key'):
                    t = 'key'
                elif p.endswith('.ts'):
                    t = 'ts'
                elif '.mp4' in p:
                    t = 'mp4'
                else:
                    t = 'seg'

            h = dict(self.headers)
            h['Accept'] = '*/*'
            h['Accept-Encoding'] = 'identity'
            h['Referer'] = ref
            try:
                p0 = urlparse(ref)
                h['Origin'] = f'{p0.scheme}://{p0.netloc}'
            except Exception:
                pass

            stream = t in ('seg', 'ts', 'mp4', 'key')
            r = self.s.get(real, headers=h, timeout=30, stream=stream, verify=False, proxies=self.proxy)
            try:
                if r.status_code != 200:
                    return [r.status_code, 'text/plain', r.content or b'']
                if t == 'm3u8':
                    return [200, 'application/vnd.apple.mpegurl', self._rewrite_m3u8(r.text, r.url, ref)]
                if t == 'key':
                    return [200, 'application/octet-stream', r.content or b'']
                if t == 'ts':
                    return [200, 'video/mp2t', r.content or b'']
                if t in ('seg', 'mp4'):
                    return [200, 'application/octet-stream' if t == 'seg' else 'video/mp4', r.content or b'']
                return [404, 'text/plain', b'']
            finally:
                try:
                    r.close()
                except Exception:
                    pass
        except Exception:
            return [404, 'text/plain', b'']

    def _rewrite_m3u8(self, text, final_url, ref):
        base = final_url.rsplit('/', 1)[0]
        host = '/'.join(final_url.split('/')[:3])
        uri_re = re.compile(r'URI="([^"]+)"')
        prox0 = (self.getProxyUrl() or '').split('&', 1)[0]

        def absu(u):
            u = (u or '').strip()
            if not u:
                return ''
            if u.startswith('http'):
                return u
            if u.startswith('//'):
                return 'https:' + u
            return (host + u) if u.startswith('/') else (base + '/' + u)

        def kind(u):
            p = (urlparse(u).path or '').lower()
            if '.m3u8' in p:
                return 'm3u8'
            if p.endswith('.key'):
                return 'key'
            if p.endswith('.ts'):
                return 'ts'
            if '.mp4' in p:
                return 'mp4'
            return 'seg'

        out = []
        for line in (text or '').split('\n'):
            s = (line or '').strip()
            if not s:
                out.append(line)
                continue

            if s.startswith('#') and 'URI=' in s:
                m = uri_re.search(s)
                if not m:
                    out.append(line)
                    continue

                u0 = m.group(1)
                if prox0 and (prox0 in u0):
                    out.append(line)
                    continue

                u = absu(u0)
                if s.startswith('#EXT-X-KEY') or s.startswith('#EXT-X-SESSION-KEY'):
                    tt = 'key'
                elif s.startswith('#EXT-X-MAP'):
                    tt = 'seg'
                else:
                    tt = kind(u)

                out.append(uri_re.sub(f'URI="{self._media_proxy(u, ref, tt)}"', line, count=1))
                continue

            if s.startswith('#'):
                out.append(line)
                continue

            u = absu(s)
            out.append(self._media_proxy(u, ref, kind(u)))

        return ('\n'.join(out)).encode('utf-8')

    def ungzip(self, data):
        return json.loads(gzip.decompress(b64decode(data)).decode())

    def getpq(self, data):
        try:
            return pq(data)
        except Exception:
            return pq((data or '').encode('utf-8'))
