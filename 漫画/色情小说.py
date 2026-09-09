# -*- coding: utf-8 -*-
"""
情色小说 (99xs / CA情色小说) 猫影视 spider（纯小说站，WordPress hueman 主题）
- 自动域名选择：仅保留导航站 https://x97.icu / https://x97.one 两个地址，
  从域名池里选中「情色小说」，探测出最快可用域名，不硬编码任何站点域名。
- WordPress 结构：分类 /article/category/{slug}/ -> 详情 /article/{id}，
  正文在详情页 <article> 的 <p> 段落里，用 novel:// 协议交给默影视阅读模块。
"""
import base64
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urlparse, unquote

import requests

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    # 自动域名选择的两个导航站（只保留这两个，不硬编码其它站点地址）
    NAV = ("https://x99dh.cc", "https://x99dh.one","https://x97.icu", "https://x97.one")
    # 在域名池中选择的站点名
    SITE = "情色小说"
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    # 小说分类（WordPress 分类 slug，繁体）
    CLASSES = [
        {'type_name': '亂倫小說', 'type_id': '/article/category/%s/' % quote('亂倫小說')},
        {'type_name': '人妻熟女', 'type_id': '/article/category/%s/' % quote('人妻熟女')},
        {'type_name': '強暴虐待', 'type_id': '/article/category/%s/' % quote('強暴虐待')},
        {'type_name': '校園師生', 'type_id': '/article/category/%s/' % quote('校園師生')},
        {'type_name': '同志小說', 'type_id': '/article/category/%s/' % quote('同志小說')},
        {'type_name': '古典武俠', 'type_id': '/article/category/%s/' % quote('古典武俠')},
        {'type_name': '都市小品', 'type_id': '/article/category/%s/' % quote('都市小品')},
        {'type_name': '名人明星', 'type_id': '/article/category/%s/' % quote('名人明星')},
        {'type_name': '外國翻譯', 'type_id': '/article/category/%s/' % quote('外國翻譯')},
    ]

    def getName(self):
        return "情色小说"

    def manualVideoCheck(self):
        return False

    def init(self, extend=""):
        try:
            cfg = json.loads(extend) if isinstance(extend, str) else (extend or {})
        except Exception:
            cfg = {}
        self.plp = cfg.get("plp", "")
        self.proxy = cfg.get("proxy", {})
        self.headers = {
            "User-Agent": self.UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
            "Cookie": "x-index-auth=authed",
        }
        self.s = requests.Session()
        self.s.cookies.set("x-index-auth", "authed")
        self.pool = self._fetch_pool()
        self.host = (self._best_host() or (cfg.get('host') or cfg.get('base') or '')).rstrip('/')

    def isVideoFormat(self, url):
        u = (url or '').lower()
        return ('.m3u8' in u) or ('.mp4' in u)

    def _abs(self, u):
        u = (u or "").strip()
        if not u:
            return u
        if u.startswith("http"):
            return u
        if u.startswith("/"):
            return self.host + u
        return self.host + "/" + u

    def _proxy_url(self, u):
        u = (u or "").strip()
        if not u or not u.startswith("http"):
            return u
        return self.plp + u

    def _unproxy_url(self, u):
        u = (u or "").strip()
        if self.plp and u.startswith(self.plp):
            return u[len(self.plp):]
        return u

    def _host_order(self):
        # 当前域名优先，再轮换域名池里其它域名（用于故障切换）
        hosts = [it['host'].rstrip('/') for it in (self.pool or [])]
        cur = (self.host or '').rstrip('/')
        ordered = ([cur] if cur else []) + [h for h in hosts if h != cur]
        return [h for h in ordered if h]

    def _get(self, url, timeout=10):
        if not url:
            return ""
        p = urlparse(url)
        path = (p.path or '/') + (('?' + p.query) if p.query else '')
        for host in self._host_order():
            full = host + path
            for _ in range(2):
                try:
                    r = self.s.get(full, headers=self.headers, proxies=self.proxy, timeout=timeout, allow_redirects=True)
                except Exception:
                    continue
                if r.status_code != 200:
                    continue
                try:
                    t = r.content.decode('utf-8', 'ignore')
                except Exception:
                    return ""
                # 维护页/空内容：跳过，切下一个域名
                if not t or ('维护' in t and len(t) < 2000):
                    break
                return t
        return ""

    # ---------------- 自动域名选择（沿用禁漫天堂机制，仅改站点名） ----------------

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
            if it.get('name') != self.SITE:
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
            for _ in range(3):
                try:
                    r = requests.get(nav, headers=headers, proxies=self.proxy, timeout=10, allow_redirects=True)
                    pool = self._parse_pool(r.text or "")
                    if pool:
                        break
                except Exception:
                    continue
            if pool:
                break
        seen, out = set(), []
        for it in pool:
            h = it.get('host')
            if h and h not in seen:
                seen.add(h)
                out.append(it)
        return out

    def _probe(self, url, timeout):
        t0 = time.time()
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, proxies=self.proxy, timeout=timeout)
        except Exception:
            return None
        if r.status_code != 200 or (r.text or '').strip().lower() != 'ok':
            return None
        return time.time() - t0

    def _best_host(self):
        pool = self.pool
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

    # ---------------- 列表 / 详情 / 正文 ----------------

    def _cards(self, html):
        out, seen = [], set()
        for m in re.finditer(r'<h2 class="post-title entry-title">\s*<a href="([^"]+/article/(\d+))[^"]*"[^>]*>([^<]+)</a>', html or ''):
            url, aid, title = m.group(1), m.group(2), m.group(3).strip()
            if aid in seen:
                continue
            seen.add(aid)
            out.append({
                'vod_id': url,
                'vod_name': title,
                'vod_pic': '',
                'vod_remarks': '',
            })
        return out

    def _pagecount(self, html):
        nums = [int(x) for x in re.findall(r'/page/(\d+)', html or '')]
        return max(nums) if nums else 1

    def _cat_page(self, tid, pg):
        base = self._abs(tid).rstrip('/')
        return base if pg <= 1 else (base + '/page/%d/' % pg)

    def homeContent(self, filter):
        html = self._get(self.host + '/')
        return {'class': self.CLASSES, 'filters': {}, 'list': self._cards(html) if html else []}

    def homeVideoContent(self):
        return {'list': (self.homeContent(None) or {}).get('list', [])}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if pg else 1
        html = self._get(self._cat_page(str(tid), pg))
        cards = self._cards(html) if html else []
        pc = self._pagecount(html)
        return {'list': cards, 'page': pg, 'pagecount': pc, 'limit': 90, 'total': pc * 90 if cards else 0}

    def searchContent(self, key, quick, pg='1'):
        pg = int(pg) if pg else 1
        q = quote(str(key))
        url = self.host + '/?s=%s' % q
        if pg > 1:
            url = self.host + '/page/%d?s=%s' % (pg, q)
        html = self._get(url)
        cards = self._cards(html) if html else []
        return {'list': cards, 'page': pg, 'pagecount': 9999}

    def detailContent(self, ids):
        url = ids[0] if str(ids[0]).startswith('http') else self._abs(str(ids[0]))
        html = self._get(url)
        if not html:
            return {'list': [{'vod_id': url, 'vod_play_from': '阅读', 'vod_play_url': '获取失败'}]}
        # 标题
        m = re.search(r'<h1 class="post-title entry-title"[^>]*>([\s\S]*?)</h1>', html, re.I)
        title = self._clean(m.group(1)) if m else ''
        if not title:
            m = re.search(r'<title>([\s\S]*?)</title>', html, re.I)
            title = self._clean(m.group(1)) if m else ''
            title = re.split(r'\s*[-–]\s*', title)[0].strip()
        # 正文分页数（WordPress nextpage：「共 N 页」或分页链接最大页码）
        pages = 1
        m = re.search(r'共\s*(\d+)\s*页', html)
        if m:
            pages = int(m.group(1))
        if pages <= 1:
            nums = [int(x) for x in re.findall(r'/article/\d+/(\d+)', html)]
            if nums:
                pages = max(nums)
        if pages > 1:
            base = url.rstrip('/')
            eps = []
            for n in range(1, pages + 1):
                page_url = url if n == 1 else (base + '/%d' % n)
                eps.append('第%d页$%s' % (n, self._proxy_url(page_url)))
            play_url = '#'.join(eps)
        else:
            play_url = '阅读全文$%s' % self._proxy_url(url)
        return {'list': [{
            'vod_id': url,
            'vod_name': title,
            'vod_pic': '',
            'vod_play_from': '阅读',
            'vod_play_url': play_url,
        }]}

    def playerContent(self, flag, id, vipFlags):
        # 剥掉 plp 前缀还原真实 URL，再用 self.proxy 抓正文
        u = self._unproxy_url((id or '').strip())
        if '/article/' in u:
            return self._player_novel(u, flag)
        return {'parse': 1, 'url': u, 'header': self.headers}

    def _player_novel(self, url, flag):
        html = self._get(url)
        if not html:
            return {'parse': 0, 'playUrl': '', 'url': 'novel://' + json.dumps({'title': '错误', 'content': '获取失败'}, ensure_ascii=False), 'header': ''}
        # 标题优先取正文 h1（小说名），带页码
        m = re.search(r'<h1 class="post-title entry-title"[^>]*>([\s\S]*?)</h1>', html, re.I)
        title = self._clean(m.group(1)) if m else (flag or '章节').strip()
        m = re.search(r'/article/\d+/(\d+)', url)
        if m:
            title = '%s（第%s页）' % (title, m.group(1))
        content = self._novel_body(html)
        if not content:
            content = '未找到正文'
        result = {'title': title, 'content': content}
        return {'parse': 0, 'playUrl': '', 'url': 'novel://' + json.dumps(result, ensure_ascii=False), 'header': ''}

    def _novel_body(self, html):
        # 定位正文 article（含 h1 post-title）
        i = html.find('<h1 class="post-title')
        if i < 0:
            i = html.find('<h1')
        if i < 0:
            return ''
        start = html.rfind('<article', 0, i)
        end = html.find('</article>', i)
        if start < 0 or end <= 0:
            return ''
        seg = html[start:end]
        # 段落（排除 post-byline 元信息段）
        paras = re.findall(r'<p(?![^>]*post-byline)[^>]*>([\s\S]*?)</p>', seg)
        lines = []
        for p in paras:
            t = re.sub(r'<[^>]+>', ' ', p)
            t = self._unescape(t)
            t = re.sub(r'99xs\.\w+', '', t)  # 去防盗链站名
            t = re.sub(r'\s+', ' ', t).strip()
            if t and len(t) > 2:
                lines.append(t)
        return '\n'.join(lines)

    def _unescape(self, t):
        rep = {
            '&#46;': '.', '&#8211;': '-', '&#8212;': '—', '&#8216;': "'", '&#8217;': "'",
            '&#8220;': '"', '&#8221;': '"', '&#8230;': '…', '&hellip;': '…', '&mdash;': '—',
            '&ldquo;': '"', '&rdquo;': '"', '&lsquo;': "'", '&rsquo;': "'", '&nbsp;': ' ',
            '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'",
        }
        for k, v in rep.items():
            t = t.replace(k, v)
        return t

    def _clean(self, s):
        t = re.sub(r'<[^>]+>', ' ', s or '')
        t = self._unescape(t)
        return re.sub(r'\s+', ' ', t).strip()
