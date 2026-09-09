# -*- coding: utf-8 -*-
import base64, json, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urljoin, urlparse, unquote

import requests

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    NAV = ("https://x99dh.cc","https://x99dh.one","https://x97.icu","https://x97.one")
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    _RE_BOX = re.compile(r'<div class="video-img-box[^\"]*"[\s\S]{0,3000}?</div>\s*</div>', re.I)
    _RE_HREF = re.compile(r'href="(https?://[^\"]+/videos/[^\"]+/)"', re.I)
    _RE_TITLE = re.compile(r'<h6 class="title"[^>]*>\s*<a[^>]*>([^<]+)</a>', re.I)
    _RE_IMG = re.compile(r'data-src="(https?://[^\"]+)"', re.I)
    _RE_DUR = re.compile(r'<span class="label">\s*([^<]+)\s*</span>', re.I)
    _RE_PAGER = re.compile(r'<ul class="pagination"[\s\S]*?</ul>', re.I)

    def getName(self):
        return "javble"

    def manualVideoCheck(self):
        return False

    def init(self, extend=""):
        try:
            cfg = json.loads(extend) if isinstance(extend, str) else (extend or {})
        except Exception:
            cfg = {}
        self.plp = cfg.get('plp', '')
        self.proxy = cfg.get("proxy") or {}
        self._fixed_host = (cfg.get('host') or cfg.get('base') or '').rstrip('/')
        # 惰性探测：代理未启动时 _best_host() 会失败，这里不强求成功
        self.host = ''
        self._probed = False
        self.headers = {
            "User-Agent": self.UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
        }
        self.s = requests.Session()
        self._gethost()

    def _gethost(self):
        # 惰性重探测：代理未启动时 _best_host() 失败，host 先落兜底域名；
        # 刷新时只要没成功探测过就重试，避免 host 一直卡在被墙的兜底域名。
        if not self._probed:
            h = self._best_host()
            if h:
                self.host = h.rstrip('/')
                self._probed = True
            elif not self.host:
                self.host = (self._fixed_host or 'https://jable.cfd').rstrip('/')
            if self.host:
                self.headers['Referer'] = '%s/' % self.host
                self.headers['Origin'] = self.host
        return self.host

    def isVideoFormat(self, url):
        u = (url or '').lower()
        return ('.m3u8' in u) or ('.mp4' in u)

    def _abs(self, u):
        u = (u or "").strip()
        return u if u.startswith("http") else urljoin(self._gethost() + "/", u)

    def _origin_from(self, u):
        try:
            p = urlparse((u or '').strip())
            if p.scheme and p.netloc:
                return '%s://%s' % (p.scheme, p.netloc)
        except Exception:
            pass
        return (self._gethost() or '').rstrip('/')

    def _play_headers(self, play_url):
        origin = (self._gethost() or '').rstrip('/') or self._origin_from(play_url)
        h = dict(self.headers or {})
        h['Origin'] = origin
        h['Referer'] = origin + '/'
        return h

    def _get(self, url, timeout=10):
        try:
            r = self.s.get(url, headers=self.headers, proxies=self.proxy, timeout=timeout, allow_redirects=True)
        except Exception:
            return ""
        if r.status_code != 200:
            return ""
        return r.text or ""

    def _norm_host(self, u):
        u = (u or "").strip().rstrip('/')
        if not u:
            return ""
        if not u.startswith("http"):
            u = "https://" + u.lstrip('/')
        p = urlparse(u)
        path = (p.path or "").rstrip('/')
        if path.endswith('/enter'):
            path = path[:-6]
        return (p.scheme + '://' + p.netloc + path).rstrip('/')

    def _parse_pool(self, html):
        m = re.search(r"const\s+encodedData\s*=\s*'([^']+)'", html or "")
        if not m:
            return []
        try:
            data = json.loads(unquote(base64.b64decode(m.group(1)).decode("utf-8", "ignore")))
        except Exception:
            return []
        for it in data if isinstance(data, list) else []:
            if it.get('name') != 'Jable':
                continue
            out = []
            for u in it.get('urls') or []:
                host, test = self._norm_host(u.get('url')), (u.get('testUrl') or '').strip()
                if host and test:
                    out.append({'host': host, 'test': test})
            return out
        return []

    def _fetch_pool(self):
        headers = {"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache", "Pragma": "no-cache"}
        pool = []
        for nav in self.NAV:
            try:
                r = requests.get(nav, headers=headers, proxies=self.proxy, timeout=10, allow_redirects=True)
                pool = self._parse_pool(r.text or "")
                if pool:
                    break
            except Exception:
                pass
        seen, out = set(), []
        for it in pool:
            h = it.get('host')
            if h and h not in seen:
                seen.add(h)
                out.append(it)
        return out

    def _probe(self, url, timeout):
        t0 = time.time()
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, proxies=self.proxy, timeout=timeout)
        if r.status_code != 200 or (r.text or '').strip().lower() != 'ok':
            return None
        return time.time() - t0

    def _best_host(self):
        pool = self._fetch_pool()
        if not pool:
            return None
        threshold, timeout = 2.5, 3.0
        best_h, best_t = None, 1e9
        workers = min(12, max(4, len(pool)))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(self._probe, it['test'], timeout): it['host'] for it in pool}
            for fut in as_completed(futs):
                try:
                    t = fut.result()
                except Exception:
                    continue
                if t is None:
                    continue
                h = futs[fut]
                if t < best_t:
                    best_h, best_t = h, t
                if t <= threshold:
                    best_h = h
                    break
        return best_h

    def _videos(self, html):
        out, seen = [], set()
        for box in self._RE_BOX.findall(html or ''):
            m = self._RE_HREF.search(box)
            if not m:
                continue
            href = m.group(1).strip()
            if href in seen:
                continue
            mt = self._RE_TITLE.search(box)
            title = (mt.group(1) if mt else '').strip()
            if not title:
                continue
            mi = re.search(r'data-src="(https?://[^\"]+)"', box, re.I)
            img = (mi.group(1) if mi else '').strip()
            if not img:
                mi = re.search(r'src="(https?://[^\"]+)"', box, re.I)
                img = (mi.group(1) if mi else '').strip()
            if not img:
                continue
            mr = self._RE_DUR.search(box)
            remark = (mr.group(1) if mr else '').strip()
            seen.add(href)
            out.append({'vod_id': href, 'vod_name': title, 'vod_pic': img, 'vod_remarks': remark, 'style': {'type': 'rect', 'ratio': 1.33}})
        return out

    def _pagecount(self, html):
        m = self._RE_PAGER.search(html or '')
        if not m:
            return 1
        nums = [int(x) for x in re.findall(r'/new-release/(\d+)/', m.group(0))]
        return max(nums) if nums else 1

    def _cr(self, name, href):
        try:
            payload = json.dumps({'id': href, 'name': name}, ensure_ascii=False)
        except Exception:
            payload = json.dumps({'id': href, 'name': name})
        return "[a=cr:%s/]%s[/a]" % (payload, name)

    def homeContent(self, filter):
        classes = [
            {'type_name': '最近更新', 'type_id': '/latest-updates/'},
            {'type_name': '全新上市', 'type_id': '/new-release/'},
            {'type_name': '热门影片', 'type_id': '/hot/'},
            {'type_name': '主奴调教', 'type_id': '/categories/bdsm/'},
            {'type_name': '直接开啪', 'type_id': '/categories/sex-only/'},
            {'type_name': '中文字幕', 'type_id': '/categories/chinese-subtitle/'},
            {'type_name': '凌辱快感', 'type_id': '/categories/insult/'},
            {'type_name': '制服诱惑', 'type_id': '/categories/uniform/'},
            {'type_name': '角色剧情', 'type_id': '/categories/roleplay/'},
            {'type_name': '无码解放', 'type_id': '/categories/uncensored/'},
            {'type_name': '男友视角', 'type_id': '/categories/pov/'},
            {'type_name': '多P群交', 'type_id': '/categories/groupsex/'},
            {'type_name': '丝袜美腿', 'type_id': '/categories/pantyhose/'},
            {'type_name': '主奴调教', 'type_id': '/categories/bdsm/'},
        ]
        html = self._get(self._gethost() + '/new-release/')
        return {'class': classes, 'filters': {}, 'list': self._videos(html) if html else []}

    def homeVideoContent(self):
        return {'list': (self.homeContent(None) or {}).get('list', [])}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if pg else 1
        url = tid if str(tid).startswith('http') else self._abs(str(tid))
        base = url if url.endswith('/') else url + '/'
        if urlparse(base).path.rstrip('/') == '/new-release':
            real = base if pg == 1 else (self._gethost() + '/new-release/%d/' % pg)
        else:
            real = base if pg == 1 else (base + '%d/' % pg)
        html = self._get(real)
        videos = self._videos(html) if html else []
        pc = self._pagecount(html) if urlparse(base).path.rstrip('/') == '/new-release' else 9999
        return {'list': videos, 'page': pg, 'pagecount': pc, 'limit': 90, 'total': pc * 90 if videos else 0}

    def searchContent(self, key, quick, pg='1'):
        pg = int(pg) if pg else 1
        html = self._get("%s/search/%s/" % (self._gethost(), quote(str(key))))
        return {'list': self._videos(html) if html else [], 'page': pg, 'pagecount': 9999}

    def detailContent(self, ids):
        url = ids[0] if str(ids[0]).startswith('http') else self._abs(str(ids[0]))
        html = self._get(url)
        if not html:
            return {'list': [{'vod_id': url, 'vod_play_from': '播放', 'vod_play_url': '获取失败'}]}
        m = re.search(r'<h4[^>]*>([\s\S]*?)</h4>', html, re.I)
        title = re.sub(r'<[^>]+>', '', m.group(1)).strip() if m else ''
        picm = re.search(r'property="og:image"[^>]+content="([^"]+)"', html, re.I)
        pic = (picm.group(1) or '').strip() if picm else ''
        m3 = re.search(r"var\s+hlsUrl\s*=\s*['\"]([^'\"]+\.m3u8[^'\"]*)", html, re.I)
        play = (m3.group(1) if m3 else '').strip()
        actors = []
        for mm in re.finditer(r'<a[^>]+class="model"[^>]+href="([^"]+)"[\s\S]{0,300}?(?:data-original-title|title)="([^"]+)"', html, re.I):
            href = self._abs((mm.group(1) or '').strip())
            name = (mm.group(2) or '').strip()
            if name and href:
                actors.append(self._cr(name, href))
        return {'list': [{
            'vod_id': url,
            'vod_name': title,
            'vod_pic': pic,
            'vod_actor': ' '.join(actors) if actors else '',
            'vod_content': '',
            'vod_play_from': '播放',
            'vod_play_url': ('正片$%s' % play) if play else '获取失败',
        }]}

    def playerContent(self, flag, id, vipFlags):
        if isinstance(id, str) and id.startswith('http') and ('.m3u8' in id or '.mp4' in id):
            return {'parse': 0, 'url': f'{self.plp}{id}', 'header': self._play_headers(id)}
        return {'parse': 1, 'url': f'{self.plp}{id}', 'header': self.headers}
