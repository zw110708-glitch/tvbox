import json
import re
import sys
import time
from urllib.parse import quote

import requests

sys.path.append('..')
from base.spider import Spider as BaseSpider


def _cr(h, n):
    meta = json.dumps({'id': h, 'name': n}, ensure_ascii=False, separators=(',', ':'))
    return '[a=cr:%s/]%s[/a]' % (meta, n)


class Spider(BaseSpider):
    GEO_URL = 'https://files.iw01.xyz/edge/geo.js?json'
    CLASSES = [
        {'type_name': '最新', 'type_id': 'latest'},
        {'type_name': '最热', 'type_id': 'hottest'},
        {'type_name': '剧情片', 'type_id': 'tag:309'},
        {'type_name': '屁屁控', 'type_id': 'tag:104'},
        {'type_name': '巨尻', 'type_id': 'tag:107'},
    ]

    def init(self, extend=''):
        try:
            cfg = json.loads(extend) if isinstance(extend, str) else (extend or {})
        except Exception:
            cfg = {}
        self.hosts = ('https://www.av01.media', 'https://www.av01.xyz')
        self.api_hosts = ('https://cdn.av01.tv',) + self.hosts
        self.lang = (cfg.get('lang') or 'cn').strip('/')
        self.plp = cfg.get('plp', '')
        self.proxy = cfg.get('proxy') or {}
        ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        self.host = self.hosts[0]
        try:
            r = requests.get(
                self.host + '/api/v1/videos/types/latest?page=1&limit=1&comp=true',
                headers={'User-Agent': ua, 'Accept': 'application/json, text/plain, */*', 'Accept-Language': 'zh-CN,zh;q=0.9', 'Referer': self.host + '/' + self.lang},
                proxies=self.proxy,
                timeout=5,
            )
            if r.status_code >= 500:
                self.host = self.hosts[1]
        except Exception:
            self.host = self.hosts[1]
        self.api_host = self.host
        self.h_api = {'User-Agent': ua, 'Accept': 'application/json, text/plain, */*', 'Accept-Language': 'zh-CN,zh;q=0.9', 'Referer': self.host + '/' + self.lang}
        self.h_up = {'User-Agent': ua, 'Accept': '*/*', 'Accept-Language': 'zh-CN,zh;q=0.9', 'Referer': self.host + '/', 'Origin': self.host, 'Connection': 'keep-alive'}
        self.s = requests.Session()
        self._geo = None
        self._geo_ts = 0
        self._token_cache = {}

    def getName(self):
        return 'AV01'

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        u = (url or '').lower()
        return '.m3u8' in u or '.mp4' in u or '.ts' in u or '.m4s' in u

    def _json(self, m, u, **kw):
        r = getattr(self.s, m)(u, headers=self.h_api, proxies=self.proxy, timeout=15, **kw)
        r.raise_for_status()
        return r.json()

    def _geo_data(self):
        now = int(time.time())
        ttl = int((self._geo or {}).get('ttl') or 0)
        if self._geo and self._geo_ts and now - self._geo_ts < (max(30, ttl - 5) if ttl else 60):
            return self._geo
        self._geo = self.s.get(
            self.GEO_URL,
            headers={'User-Agent': self.h_api['User-Agent'], 'Accept': 'application/json'},
            proxies=self.proxy,
            timeout=15,
        ).json()
        self._geo_ts = now
        return self._geo

    def _signed_qs(self):
        g = self._geo_data()
        q = 'expires=%s&ip=%s&token_v2=%s' % (
            g.get('expires'),
            quote(str(g.get('ip') or '')),
            quote(str(g.get('token_v2') or g.get('token') or '')),
        )
        return q + ('&comp=true' if g.get('comp') else '')

    def _vid(self, v):
        v = str(v).strip()
        m = re.search(r'/video/(\d+)', v)
        return int(m.group(1) if m else v)

    def _token(self, vid):
        c = self._token_cache.get(vid)
        if c and time.time() - c[1] < 3000:
            return c[0]
        g = self._geo_data()
        q = 'token_v2=%s&expires=%s&ip=%s%s' % (
            quote(str(g.get('token_v2') or '')),
            g.get('expires'),
            quote(str(g.get('ip') or '')),
            '&comp=true' if g.get('comp') else '',
        )
        for h in self.api_hosts:
            try:
                t = (self._json('get', '%s/api/v1/videos/%s/cdn-access?%s' % (h, vid, q)) or {}).get('access_token') or ''
                if t:
                    self.api_host = h
                    self._token_cache[vid] = (t, time.time())
                    return t
            except Exception:
                pass
        return ''

    def _cover(self, vid):
        g = self._geo_data()
        t = 'token_v2=%s&expires=%s&ip=%s' % (
            quote(str(g.get('token_v2') or g.get('token') or '')),
            g.get('expires'),
            quote(str(g.get('ip') or '')),
        )
        return 'https://files.iw01.xyz/covers/%s/800.webp%s' % (vid, '?' + t if t else '')

    def _txt(self, d, k, x=''):
        return ((d.get(k + '_translations') or {}).get(self.lang) or d.get(k) or x).strip()

    def _links(self, a, p, t=''):
        return ' '.join(
            _cr('%s:%s' % (p, int(i)), t + n)
            for v in (a or [])
            for i, n in [(v.get('id'), self._txt(v, 'name'))]
            if i and n
        )

    def _vod(self, v, p=0):
        vid = int(v.get('id'))
        d = {
            'vod_id': str(vid),
            'vod_name': self._txt(v, 'title', str(vid)),
            'vod_remarks': '',
            'style': {'type': 'rect', 'ratio': 1.33},
        }
        if p:
            d['vod_pic'] = self.plp+self._cover(vid)
        return d

    def _page(self, pg, p=0, url=None, data=None):
        data = data or self._json('get', url)
        pag = data.get('pagination') or {}
        lst = [self._vod(v, p) for v in data.get('videos') or []]
        return {
            'list': lst,
            'page': pg,
            'pagecount': int(pag.get('totalPages') or 0) or (9999 if lst else 1),
            'limit': 20,
            'total': int(pag.get('total') or 0) or (pg * 20 if lst else 0),
        }

    def _play(self, vid, res='v3'):
        t = self._token(vid)
        if not t:
            return ''
        return '%s/api/v1/videos/%s/manifest/index90-%s-a1.m3u8?access_token=%s' % (self.api_host, vid, res, t)

    def homeContent(self, filter):
        try:
            return {
                'class': self.CLASSES,
                'filters': {},
                'list': self._page(1, 1, '%s/api/v1/videos/types/latest?page=1&limit=20&comp=true' % self.host)['list'],
            }
        except Exception:
            return {'class': self.CLASSES, 'filters': {}, 'list': []}

    def homeVideoContent(self):
        return {'list': self.homeContent(None).get('list', [])}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        tid = (tid or 'latest').strip()
        m = re.search(r'/(tag|actress|maker)/(\d+)', tid)
        if m:
            tid = '%s:%s' % (m.group(1), m.group(2))
        try:
            if tid.startswith(('tag:', 'actress:', 'maker:')):
                p, s = tid.split(':', 1)
                if s.isdigit():
                    comp = '' if p == 'maker' else '&comp=true'
                    return self._page(pg, 1, '%s/api/v1/videos/%s/%s?page=%s&limit=20%s' % (self.host, p, int(s), pg, comp))
            sort = 'hottest' if tid == 'hottest' else 'latest'
            return self._page(pg, 1, '%s/api/v1/videos/types/%s?page=%s&limit=20&comp=true' % (self.host, sort, pg))
        except Exception:
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 20, 'total': 0}

    def detailContent(self, ids):
        try:
            vid = self._vid(ids[0])
        except Exception:
            return {'list': [{'vod_play_from': 'AV01', 'vod_play_url': ''}]}
        try:
            v = self._json('get', '%s/api/v1/videos/%s' % (self.host, vid))
        except Exception:
            v = {'id': vid, 'title': 'AV01-%s' % vid}
        tags = self._links(v.get('tags'), 'tag', '#')
        desc = self._txt(v, 'description')
        mk = self._txt({'maker_translations': v.get('maker_translations'), 'maker': v.get('maker')}, 'maker')
        mid = v.get('maker_id')
        vod_content_parts = []
        if tags:
            vod_content_parts.append('标签: ' + tags)
        if desc:
            vod_content_parts.append(desc)
        vod_content = '\n\n'.join(vod_content_parts)
        return {
            'list': [{
                'vod_id': str(vid),
                'vod_name': self._txt(v, 'title', 'AV01-%s' % vid),
                'vod_pic': '',
                'vod_actor': self._links(v.get('actresses'), 'actress'),
                'vod_director': _cr('maker:%s' % int(mid), mk) if mid and mk else '',
                'vod_content': vod_content,
                'vod_play_from': 'AV01',
                'vod_play_url': '1080P$%s|v3#720P$%s|v2#480P$%s|v1' % (vid, vid, vid),
            }]
        }

    def searchContent(self, key, quick, pg='1'):
        pg = int(pg or 1)
        q = (key or '').strip()
        if not q:
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 20, 'total': 0}
        try:
            return self._page(
                pg, 1,
                data=self._json('post', '%s/api/v1/videos/search?lang=%s&comp=true' % (self.host, quote(self.lang)), json={'q': q, 'page': pg, 'limit': 20}),
            )
        except Exception:
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 20, 'total': 0}

    def playerContent(self, flag, id, vipFlags):
        s = str(id)
        if '|' in s:
            vid, res = s.split('|', 1)
        else:
            vid, res = s, 'v3'
        return {'parse': 0, 'url': self.plp+self._play(self._vid(vid), res), 'header': self.h_up, 'jx': 0}
