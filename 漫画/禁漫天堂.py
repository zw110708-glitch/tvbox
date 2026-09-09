# -*- coding: utf-8 -*-
"""
禁漫天堂 (18comic / JMComic) 猫影视 spider
- 自动域名选择：仅保留导航站 https://x97.icu / https://x97.one 两个地址，
  从域名池里选中「禁漫天堂」站，探测出最快可用域名，不硬编码任何站点域名。
- 内容分类：漫画(albums) / 视频(videos) / 小说(novels) 三类全部匹配。
"""
import base64
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urljoin, urlparse, unquote

import requests

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    # 自动域名选择的两个导航站（只保留这两个，不硬编码其它站点地址）
    NAV = ("https://x97.icu", "https://x97.one")
    # 在域名池中选择的站点名
    SITE = "禁漫天堂"
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    # 播放器代理前缀：直接传递给播放器的原始 URL（封面/播放地址）都加这个前缀，
    # 让请求回到本地 10079 代理，再由内置代理 10172 转发到真实地址。
    # 普通内部请求（抓网页/接口）则走 self.proxies（requests 的 proxies 参数）转发。
    PROXY_PREFIX = "http://127.0.0.1:10079/p/0/127.0.0.1:10172/"

    # 三大内容分类：漫画 / 视频 / 小说（type_id 均为站点相对路径）
    CLASSES = [
        # ---- 漫画 ----
        {'type_name': '漫画·最新A漫', 'type_id': '/albums?o=mr'},
        {'type_name': '漫画·热门', 'type_id': '/albums?o=mv'},
        {'type_name': '漫画·本周热门', 'type_id': '/albums?o=mv&t=w'},
        {'type_name': '漫画·本月热门', 'type_id': '/albums?t=m&o=mv'},
        {'type_name': '漫画·同人', 'type_id': '/albums/doujin'},
        {'type_name': '漫画·单本', 'type_id': '/albums/single'},
        {'type_name': '漫画·短篇', 'type_id': '/albums/short'},
        {'type_name': '漫画·其他类', 'type_id': '/albums/another'},
        {'type_name': '漫画·韩漫', 'type_id': '/albums/hanman'},
        {'type_name': '漫画·美漫', 'type_id': '/albums/meiman'},
        # ---- 视频 ----
        {'type_name': '视频·H动漫', 'type_id': '/videos/cartoon'},
        {'type_name': '视频·COS片', 'type_id': '/videos_cosav'},
        {'type_name': '视频·小电影', 'type_id': '/movies'},
        # ---- 小说 ----
        {'type_name': '小说·禁漫小说', 'type_id': '/novels?o=mr'},
        {'type_name': '小说·绅夜食堂', 'type_id': '/blogs/dinner'},
        {'type_name': '小说·游戏文库', 'type_id': '/blogs/raiders'},
        {'type_name': '小说·西斯话题', 'type_id': '/blogs/sexytalk'},
    ]

    def getName(self):
        return "禁漫天堂"

    def manualVideoCheck(self):
        return False

    def init(self, extend=""):
        try:
            cfg = json.loads(extend) if isinstance(extend, str) else (extend or {})
        except Exception:
            cfg = {}
        self.proxies = cfg.get("proxies") or {}
        # 动态域名：优先探测最快域名，其次取域名池第一个，最后才用扩展配置兜底
        self.pool = self._fetch_pool()
        self.host = (self._best_host() or (self.pool[0]['host'] if self.pool else '') or (cfg.get('host') or cfg.get('base') or '')).rstrip('/')
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
        # 年龄确认 cookie（18comic 进入首页必须带）
        self.s.cookies.set("x-index-auth", "authed")

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
        # 直接传递给播放器的原始 URL 加代理前缀（封面/播放地址）
        u = (u or "").strip()
        if not u or u.startswith(self.PROXY_PREFIX) or not u.startswith("http"):
            return u
        return self.PROXY_PREFIX + u

    def _unproxy_url(self, u):
        # 从代理前缀还原真实 URL（playerContent 收到带前缀的章节地址后剥掉，再用 self.proxies 抓）
        u = (u or "").strip()
        if u.startswith(self.PROXY_PREFIX):
            return u[len(self.PROXY_PREFIX):]
        return u

    def _get(self, url, timeout=10):
        if not url:
            return ""
        for _ in range(2):
            try:
                r = self.s.get(url, headers=self.headers, proxies=self.proxies, timeout=timeout, allow_redirects=True)
            except Exception:
                continue
            if r.status_code == 200:
                try:
                    return r.content.decode('utf-8', 'ignore')
                except Exception:
                    return ""
        return ""

    # ---------------- 自动域名选择（沿用原 18.py 机制，仅改站点名） ----------------

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
            try:
                r = requests.get(nav, headers=headers, proxies=self.proxies, timeout=10, allow_redirects=True)
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
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, proxies=self.proxies, timeout=timeout)
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

    # ---------------- 通用解析 ----------------

    # 详情链接：album(漫画) / video(动漫) / video_cosav(COS) / novel(小说) / movie(小电影) / blog(博客文章)
    _RE_LINK = re.compile(r'href="(/album/\d+/[^"]*|/video/\d+/[^"]*|/video_cosav/\d+/[^"]*|/novel/\d+/[^"]*|/movie/[^"]+|/blog/\d+)"', re.I)
    _RE_IMG = re.compile(r'(data-original|data-src|src)="(https?://[^"]+|//[^"]+)"', re.I)
    _RE_ATTR_TITLE = re.compile(r'title="([^"]+)"', re.I)
    _RE_SPAN_TITLE = re.compile(r'<span class="video-title[^"]*"[^>]*>([\s\S]*?)</span>', re.I)

    def _real_img(self, tag):
        for m in self._RE_IMG.finditer(tag):
            u = m.group(2)
            if 'blank' not in u and 'logo' not in u:
                return self._fix_proto(u.strip())
        return ''

    def _clean(self, s):
        t = re.sub(r'<[^>]+>', ' ', s or '')
        return re.sub(r'\s+', ' ', t).strip()

    def _fix_proto(self, u):
        u = (u or '').strip()
        if u.startswith('//'):
            return 'https:' + u
        return u

    def _cards(self, html):
        out, seen = [], set()
        for m in self._RE_LINK.finditer(html or ''):
            href = m.group(1)
            if href in seen:
                continue
            seg = html[m.end():m.end() + 1500]
            im = re.search(r'<img[^>]*>', seg)
            img = ''
            if im:
                img = self._real_img(im.group(0))
            title = ''
            mt = self._RE_ATTR_TITLE.search(im.group(0)) if im else None
            if mt:
                title = self._clean(mt.group(1))
            if not title:
                ms = self._RE_SPAN_TITLE.search(seg)
                if ms:
                    title = self._clean(ms.group(1))
            if not title or not img:
                continue
            seen.add(href)
            out.append({
                'vod_id': self._abs(href),
                'vod_name': title,
                'vod_pic': self._proxy_url(img),
                'vod_remarks': '',
            })
        return out

    def _pagecount(self, html):
        nums = [int(x) for x in re.findall(r'(?:page=|/page/)(\d+)', html or '')]
        return max(nums) if nums else 1

    def _page_url(self, tid, pg):
        u = self._abs(tid)
        sep = '&' if '?' in u else '?'
        return u if pg <= 1 else (u + sep + 'page=%d' % pg)

    # ---------------- 首页 / 分类 / 搜索 ----------------

    def homeContent(self, filter):
        html = self._get(self.host + '/albums?o=mr')
        return {'class': self.CLASSES, 'filters': {}, 'list': self._cards(html) if html else []}

    def homeVideoContent(self):
        return {'list': (self.homeContent(None) or {}).get('list', [])}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if pg else 1
        html = self._get(self._page_url(str(tid), pg))
        cards = self._cards(html) if html else []
        pc = self._pagecount(html)
        return {'list': cards, 'page': pg, 'pagecount': pc, 'limit': 90, 'total': pc * 90 if cards else 0}

    def searchContent(self, key, quick, pg='1'):
        pg = int(pg) if pg else 1
        q = quote(str(key))
        out, seen = [], set()
        # 漫画 + 视频两类可搜索（小说站无独立搜索接口，仅浏览）
        urls = [
            self.host + '/search/photos?search_query=%s&page=%d' % (q, pg),
            self.host + '/search/videos?search_query=%s&page=%d' % (q, pg),
        ]
        for u in urls:
            html = self._get(u)
            for c in self._cards(html) if html else []:
                if c['vod_id'] not in seen:
                    seen.add(c['vod_id'])
                    out.append(c)
        return {'list': out, 'page': pg, 'pagecount': 9999}

    # ---------------- 详情 ----------------

    def detailContent(self, ids):
        url = ids[0] if str(ids[0]).startswith('http') else self._abs(str(ids[0]))
        html = self._get(url)
        if not html:
            return {'list': [{'vod_id': url, 'vod_play_from': '播放', 'vod_play_url': '获取失败'}]}
        path = (urlparse(url).path or '')
        if '/album/' in path:
            return self._detail_album(url, html)
        if '/novel/' in path:
            return self._detail_novel(url, html)
        if '/blog/' in path:
            return self._detail_blog(url, html)
        return self._detail_video(url, html)

    def _detail_album(self, url, html):
        # 标题
        m = re.search(r'id="book-name"[^>]*?>([\s\S]*?)<', html, re.I)
        title = self._clean(m.group(1)) if m else ''
        # 封面：media/albums/{id}.jpg
        pic = ''
        m = re.search(r'/album/(\d+)', url)
        aid = m.group(1) if m else ''
        if aid:
            mp = re.search(r'(?:https?:)?//[^"\']*media/albums/' + re.escape(aid) + r'[^"\']*?\.(?:jpg|webp|png)', html, re.I)
            if mp:
                pic = self._fix_proto(mp.group(0))
        # 章节列表
        eps = []
        for m in re.finditer(r'href="(/photo/(\d+))"[^>]*data-album="(\d+)"[^>]*>[\s\S]*?<h3 class="h2_series">\s*([\s\S]*?)</h3>', html, re.I):
            pid = m.group(2)
            name = self._clean(m.group(4)) or ('第%s話' % m.group(3))
            if name in eps:
                continue
            eps.append((name, self._proxy_url(self._abs('/photo/' + pid))))
        if not eps:
            # 单章/单行本：仅一个 photo
            for m in re.finditer(r'href="(/photo/(\d+))"', html, re.I):
                pid = m.group(2)
                eps.append(('第1話', self._proxy_url(self._abs('/photo/' + pid))))
                break
        play_url = '#'.join(['%s$%s' % (n, u) for n, u in eps])
        return {'list': [{
            'vod_id': url,
            'vod_name': title,
            'vod_pic': self._proxy_url(pic),
            'vod_play_from': '章节',
            'vod_play_url': play_url or '获取失败',
        }]}

    def _detail_novel(self, url, html):
        m = re.search(r'<title>([\s\S]*?)</title>', html, re.I)
        title = self._clean(m.group(1)) if m else ''
        title = re.split(r'\s*[-|]\s*禁漫天堂', title)[0].strip()
        # 封面：media/novels/{id}.jpg / {id}_tmb.jpg
        pic = ''
        m = re.search(r'/novel/(\d+)', url)
        nid = m.group(1) if m else ''
        if nid:
            mp = re.search(r'(?:https?:)?//[^"\']*media/novels/' + re.escape(nid) + r'[^"\']*?\.(?:jpg|webp|png)', html, re.I)
            if mp:
                pic = self._fix_proto(mp.group(0))
        # 章节列表
        eps = []
        for m in re.finditer(r'href="(/novelchapters/(\d+))"[^>]*data-album="(\d+)"[^>]*>[\s\S]*?<li>\s*([\s\S]*?)</li>', html, re.I):
            cid = m.group(2)
            name = self._clean(m.group(4)) or ('第%s話' % m.group(3))
            if name in eps:
                continue
            eps.append((name, self._proxy_url(self._abs('/novelchapters/' + cid))))
        play_url = '#'.join(['%s$%s' % (n, u) for n, u in eps])
        return {'list': [{
            'vod_id': url,
            'vod_name': title,
            'vod_pic': self._proxy_url(pic),
            'vod_play_from': '章节',
            'vod_play_url': play_url or '获取失败',
        }]}

    def _detail_video(self, url, html):
        m = re.search(r'<title>([\s\S]*?)</title>', html, re.I)
        title = self._clean(m.group(1)) if m else ''
        title = re.split(r'\s*[-|]\s*禁漫天堂', title)[0].strip()
        pic = ''
        mp = re.search(r'poster="([^"]+)"', html, re.I)
        if mp:
            pic = self._fix_proto(mp.group(1))
        m3u8 = re.search(r'<source\s+src="(https?://[^"]*\.m3u8[^"]*)"', html, re.I)
        mp4 = re.search(r'<source\s+src="(https?://[^"]*\.mp4[^"]*)"', html, re.I)
        play = []
        if m3u8:
            play.append('HLS$%s' % self._proxy_url(m3u8.group(1)))
        if mp4:
            play.append('MP4$%s' % self._proxy_url(mp4.group(1)))
        return {'list': [{
            'vod_id': url,
            'vod_name': title,
            'vod_pic': self._proxy_url(pic),
            'vod_play_from': '播放',
            'vod_play_url': '#'.join(play) if play else '获取失败',
        }]}

    def _detail_blog(self, url, html):
        # 标题：h1 或 title
        m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html, re.I)
        title = self._clean(m.group(1)) if m else ''
        if not title:
            m = re.search(r'<title>([\s\S]*?)</title>', html, re.I)
            title = self._clean(m.group(1)) if m else ''
            title = re.split(r'\s*[-|]\s*禁漫天堂', title)[0].strip()
        # 封面：og:image 或文章首图
        pic = ''
        mp = re.search(r'property="og:image"[^>]+content="([^"]+)"', html, re.I)
        if mp:
            pic = self._fix_proto(mp.group(1))
        if not pic:
            mp = re.search(r'<img[^>]+(?:src|data-original|data-src)="([^"]*static/resources/images/[^"]+)"', html, re.I)
            if mp:
                pic = self._fix_proto(mp.group(1))
        return {'list': [{
            'vod_id': url,
            'vod_name': title,
            'vod_pic': self._proxy_url(pic),
            'vod_play_from': '阅读',
            'vod_play_url': '阅读$%s' % self._proxy_url(url),
        }]}

    # ---------------- 播放 ----------------

    def playerContent(self, flag, id, vipFlags):
        u = (id or '').strip()
        # 视频直链：m3u8 / mp4（保持代理前缀，播放器直接加载）
        if '.m3u8' in u or '.mp4' in u:
            return {'parse': 0, 'url': u, 'header': self._play_headers(u)}
        # 漫画/小说章节、博客：剥掉代理前缀，spider 用 self.proxies 抓正文
        real = self._unproxy_url(u)
        if '/photo/' in real:
            return self._player_manga(real)
        if '/novelchapters/' in real:
            return self._player_novel(real, flag)
        if '/blog/' in real:
            return self._player_blog(real, flag)
        # 兜底：视频网页
        return {'parse': 1, 'url': real, 'header': self.headers}

    def _player_manga(self, url):
        html = self._get(url)
        if not html:
            return {'parse': 1, 'url': url, 'header': self.headers}
        # 图片 CDN 域名（从占位图 src 提取，动态不硬编码）
        m = re.search(r'src="https://([^"]+)/media/albums/blank', html)
        domain = m.group(1) if m else ''
        # scramble_id（用于图片切割还原）
        sid = '0'
        m = re.search(r'var scramble_id = (\d+);', html)
        if m:
            sid = m.group(1)
        # 图片文件名列表（正确顺序）
        arr = []
        m = re.search(r'var page_arr = (\[[^\]]*\]);', html)
        if m:
            try:
                arr = json.loads(m.group(1))
            except Exception:
                arr = []
        m = re.search(r'/photo/(\d+)', url)
        pid = m.group(1) if m else ''
        imgs = []
        if domain and pid and arr:
            for fn in arr:
                imgs.append('https://%s/media/photos/%s/%s' % (domain, pid, fn))
        # 兜底：直接抓 data-original 里的图片
        if not imgs and pid:
            imgs = re.findall(r'data-original="(https?://[^"]*media/photos/' + re.escape(pid) + r'[^"]*)"', html)
            if not imgs:
                imgs = re.findall(r'(?:https?:)?//[^"\']*media/photos/' + re.escape(pid) + r'[^"\']*\.(?:jpg|webp|png)', html)
                imgs = [self._fix_proto(x) for x in imgs]
        if imgs:
            # 走图片代理，localProxy 里按 scramble_id 做分片还原
            proxied = [self._img_proxy(img, sid) for img in imgs]
            return {'parse': 0, 'playUrl': '', 'url': 'pics://' + '&&'.join(proxied), 'header': ''}
        return {'parse': 1, 'url': url, 'header': self.headers}

    def _player_novel(self, url, flag):
        html = self._get(url)
        if not html:
            return {'parse': 0, 'playUrl': '', 'url': 'novel://' + json.dumps({'title': '错误', 'content': '获取失败'}, ensure_ascii=False), 'header': ''}
        title = (flag or '').strip()
        if not title:
            m = re.search(r'<title>([\s\S]*?)</title>', html, re.I)
            title = self._clean(m.group(1)) if m else '章节'
        content = self._novel_text(html)
        if not content:
            content = '未找到章节内容'
        result = {'title': title, 'content': content}
        return {'parse': 0, 'playUrl': '', 'url': 'novel://' + json.dumps(result, ensure_ascii=False), 'header': ''}

    def _novel_text(self, html):
        parts = []
        for nid in ('ncc1', 'ncc2'):
            m = re.search(r'id="%s"[^>]*>([\s\S]*?)</div>' % nid, html, re.I)
            if not m:
                continue
            t = m.group(1)
            t = re.sub(r'<br\s*/?>', '\n', t, flags=re.I)
            t = re.sub(r'</p>', '\n', t, flags=re.I)
            t = re.sub(r'<[^>]+>', '', t)
            t = (t.replace('&nbsp;', ' ').replace('&amp;', '&')
                   .replace('&hellip;', '…').replace('&mdash;', '—')
                   .replace('&ldquo;', '"').replace('&rdquo;', '"')
                   .replace('&lsquo;', "'").replace('&rsquo;', "'"))
            t = re.sub(r'[ \t]+', ' ', t)
            t = re.sub(r'\n\s*\n', '\n\n', t).strip()
            if t:
                parts.append(t)
        return '\n\n'.join(parts)

    def _player_blog(self, url, flag):
        html = self._get(url)
        if not html:
            return {'parse': 0, 'playUrl': '', 'url': 'novel://' + json.dumps({'title': '错误', 'content': '获取失败'}, ensure_ascii=False), 'header': ''}
        title = (flag or '').strip()
        if not title:
            m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html, re.I)
            title = self._clean(m.group(1)) if m else '文章'
        content = self._blog_text(html)
        if not content:
            content = '未找到正文'
        result = {'title': title, 'content': content}
        return {'parse': 0, 'playUrl': '', 'url': 'novel://' + json.dumps(result, ensure_ascii=False), 'header': ''}

    def _blog_text(self, html):
        m = re.search(r'<article[\s\S]*?</article>', html, re.I)
        seg = m.group(0) if m else html
        seg = re.sub(r'<script[\s\S]*?</script>', '', seg)
        seg = re.sub(r'<style[\s\S]*?</style>', '', seg)
        t = re.sub(r'<br\s*/?>', '\n', seg, flags=re.I)
        t = re.sub(r'</p>', '\n', t, flags=re.I)
        t = re.sub(r'<[^>]+>', '', t)
        t = (t.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&hellip;', '…').replace('&mdash;', '—')
               .replace('&ldquo;', '"').replace('&rdquo;', '"'))
        t = re.sub(r'[ \t]+', ' ', t)
        t = re.sub(r'\n\s*\n', '\n\n', t).strip()
        return t

    # ---------------- 图片代理 / 漫画 scramble 还原 ----------------

    def _img_proxy(self, img, sid='0'):
        try:
            proxy = self.getProxyUrl()
        except Exception:
            proxy = ''
        if not proxy:
            return img
        return '%s&type=img&url=%s&sid=%s' % (proxy, self.e64(img), sid)

    def e64(self, t):
        return base64.urlsafe_b64encode(str(t).encode()).decode().rstrip('=')

    def d64(self, t):
        s = str(t).strip()
        if not s:
            return ''
        s += '=' * ((4 - len(s) % 4) % 4)
        return base64.urlsafe_b64decode(s.encode()).decode('utf-8', 'ignore')

    def _mime(self, data):
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return 'image/png'
        if data[:3] == b'GIF':
            return 'image/gif'
        if data[:4] == b'RIFF' and b'WEBP' in data[:16]:
            return 'image/webp'
        if data[:2] == b'\xff\xd8':
            return 'image/jpeg'
        return ''

    def _scramble_num(self, sid, pid, fn):
        try:
            sid = int(sid or 0)
            pid = int(pid or 0)
        except Exception:
            return 0
        if pid < sid:
            return 0
        if pid < 268850:
            return 10
        x = 10 if pid < 421926 else 8
        s = hashlib.md5((str(pid) + fn).encode()).hexdigest()
        return (ord(s[-1]) % x) * 2 + 2

    def _descramble(self, data, num):
        if num <= 0:
            return data
        try:
            from PIL import Image
            import io as _io
            img = Image.open(_io.BytesIO(data)).convert('RGB')
            w, h = img.size
            out = Image.new('RGB', (w, h))
            over = h % num
            for i in range(num):
                move = h // num
                y_src = h - move * (i + 1) - over
                y_dst = move * i
                if i == 0:
                    move += over
                else:
                    y_dst += over
                out.paste(img.crop((0, y_src, w, y_src + move)), (0, y_dst, w, y_dst + move))
            buf = _io.BytesIO()
            out.save(buf, format='JPEG', quality=90)
            return buf.getvalue()
        except Exception:
            return data

    def localProxy(self, param):
        try:
            if (param or {}).get('type') != 'img' or not param.get('url'):
                return [404, 'text/plain', b'']
            real = self.d64(param['url'])
            if not real:
                return [404, 'text/plain', b'']
            h = dict(self.headers or {})
            h['Accept'] = 'image/webp,image/apng,image/*,*/*;q=0.8'
            r = self.s.get(real, headers=h, timeout=15, proxies=self.proxies)
            data = r.content
            mime = self._mime(data) or 'image/jpeg'
            # scramble 还原（PIL 可用时）
            sid = param.get('sid') or '0'
            m = re.search(r'/photos/(\d+)/([^/?#]+)', real)
            if m and sid:
                pid = m.group(1)
                fn = m.group(2).split('.')[0]
                num = self._scramble_num(sid, pid, fn)
                if num > 0:
                    nd = self._descramble(data, num)
                    if nd is not data:
                        data = nd
                        mime = 'image/jpeg'
            return [r.status_code, mime, data]
        except Exception:
            return [404, 'text/plain', b'']

    def _play_headers(self, play_url):
        origin = (self.host or '').rstrip('/')
        h = dict(self.headers or {})
        h['Origin'] = origin
        h['Referer'] = origin + '/'
        return h
