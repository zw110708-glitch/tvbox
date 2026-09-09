import json
import re
import sys
from urllib.parse import urljoin, urlparse, quote

import requests
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    """JAVDAY 直链精简版（无本地代理/转发）"""

    LIST_SELECTOR = '.col-style a.videoBox'

    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, str) and extend.strip():
            cfg = json.loads(extend)
        elif isinstance(extend, dict):
            cfg = extend

        self.host = (cfg.get('host') or 'https://javday.app').rstrip('/')
        self.proxies = cfg.get('proxies') or {}

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Referer': f"{self.host}/",
        }

    def getName(self):
        return "JAVDAY-直链"

    def manualVideoCheck(self):
        return False

    # ------------------------ 核心接口 ------------------------

    def homeContent(self, filter):
        doc = pq(self._get(self.host))
        return {
            'class': self._parse_nav_classes(doc),
            'filters': {},
            'list': self._parse_video_list(doc),
        }

    def homeVideoContent(self):
        return {'list': self.homeContent(None).get('list', [])}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if pg else 1
        base = self._abs(tid).rstrip('/')
        url = f"{base}/" if pg == 1 else f"{base}/page/{pg}/"

        # 可选排序：extend['by'] 兼容 hits/time
        if isinstance(extend, dict) and extend.get('by'):
            slug = self._extract_category_slug(tid)
            by = str(extend.get('by')).strip()
            if slug and by in ('hits', 'time'):
                url = f"{self.host}/fiter/by/{by}/id/{slug}/" if pg == 1 else f"{self.host}/fiter/by/{by}/id/{slug}/page/{pg}/"

        doc = pq(self._get(url))
        videos = self._parse_video_list(doc)
        return {'list': videos, 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}

    def detailContent(self, ids):
        url = self._abs(ids[0])
        html = self._get(url)
        data = pq(html)

        vod = {}
        vod['vod_id'] = url
        vod['vod_name'] = (data('h1.video-title').text() or data('h1').text() or data('title').text()).strip()

        # 演员（可点击）
        actors = []
        for a in data('span.vod_actor a').items():
            name = a.text().strip()
            href = a.attr('href')
            if name and href:
                actors.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')
        if actors:
            vod['vod_actor'] = ' '.join(actors)

        # 标签（可点击，放入简介字段）
        tags = []
        for a in data('span.tag a').items():
            name = a.text().strip()
            href = a.attr('href')
            if name and href:
                tags.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')
        if tags:
            vod['vod_content'] = ' '.join(tags)
        else:
            vod['vod_content'] = (data('#videoInfo').text() or data('.videoInfo').text() or '').strip() or vod['vod_name']

        play = self._extract_play_urls(html)
        vod['vod_play_from'] = 'JAVDAY'
        vod['vod_play_url'] = '#'.join(play) if play else f"网页播放${url}"

        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        # JAVDAY 搜索：/search/wd/<keyword>/
        url = f"{self.host}/search/wd/{quote(key)}/"
        doc = pq(self._get(url))
        return {'list': self._parse_video_list(doc), 'page': 1, 'pagecount': 1}

    def playerContent(self, flag, id, vipFlags):
        # 直链传递给播放器
        return {'parse': 0, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{id}', 'header': self.headers}

    # ------------------------ 解析逻辑 ------------------------

    def _parse_nav_classes(self, doc: pq):
        classes = []
        seen = set()
        host_netloc = urlparse(self.host).netloc

        for a in doc('nav.path_bar a.type').items():
            name = a.text().strip()
            href = (a.attr('href') or '').strip()
            if not name or not href or href in ('#', '/'):
                continue

            abs_url = self._abs(href)
            p = urlparse(abs_url)
            if p.netloc and p.netloc != host_netloc:
                continue

            if not (p.path.startswith('/category/') or p.path.startswith('/label/')):
                continue

            path = p.path if p.path.endswith('/') else p.path + '/'
            if path in seen:
                continue

            seen.add(path)
            classes.append({'type_name': name, 'type_id': path})

        return classes

    def _parse_video_list(self, doc: pq):
        videos = []
        seen = set()

        for a in doc(self.LIST_SELECTOR).items():
            href = (a.attr('href') or '').strip()
            if not href:
                continue

            vod_id = self._abs(href).split('#', 1)[0].rstrip('/')
            if vod_id in seen:
                continue
            seen.add(vod_id)

            title = (a.find('.videoBox-info .title').text() or a.attr('title') or '').strip()
            if not title:
                continue

            style = a.find('.videoBox-cover').attr('style') or ''
            m = re.search(r'url\(([^)]+)\)', style)
            pic = m.group(1).strip('"\' ') if m else ''
            if not pic:
                pic = a.find('img').attr('data-src') or a.find('img').attr('src') or ''
            pic = self._abs(pic)

            remark = (a.find('.videoBox-action .views .number').text() or '').strip()

            videos.append({
                'vod_id': vod_id,
                'vod_name': title,
                'vod_pic': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pic}',
                'vod_remarks': remark,
                'style': {"type": "rect", "ratio": 1.33},
            })

        return videos

    def _extract_play_urls(self, html: str):
        # JAVDAY 播放页：DPlayer config 的 video.url
        out = []
        seen = set()

        for m in re.finditer(r"video\s*:\s*\{[^}]*?url\s*:\s*['\"]([^'\"]+)['\"]", html, re.I | re.S):
            u = self._abs(m.group(1).strip())
            if u and u not in seen:
                seen.add(u)
                out.append(f"默认${u}")

        return out

    # ------------------------ 小工具 ------------------------

    def _get(self, url: str) -> str:
        res = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=10)
        res.encoding = res.apparent_encoding
        return res.text

    def _abs(self, url: str) -> str:
        url = (url or '').strip('"\' ')
        if not url:
            return ''
        return url if url.startswith('http') else urljoin(self.host, url)

    def _extract_category_slug(self, tid: str) -> str:
        p = urlparse(self._abs(tid)).path
        m = re.search(r"/category/([^/]+)/?", p)
        return m.group(1) if m else ''
