# -*- coding: utf-8 -*-
"""精简版：基于 HTML 抓取/解析的网站爬虫（无缓存/无代理/无解密）

满足你的约束：
1) 只通过抓取到的 HTML 做解析（不做补丁式兜底、无 AES/图片缓存/本地代理）。
2) 保留直链播放逻辑：拿到 m3u8/mp4 直链 => parse=0；否则保留 iframe/player 链接给宿主解析。
3) 修复“无码专区”分类：AVToday 侧边栏真实路径为 /no-mosaic。

依赖：requests + bs4（环境默认有）。
"""

import json
import re
from urllib.parse import urljoin, quote

import requests
from bs4 import BeautifulSoup

import sys
sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        elif isinstance(extend, dict):
            cfg = extend

        self.host = (cfg.get('host') or 'https://avtoday.io').rstrip('/')
        self.proxies = cfg.get('proxies') or {        "http": "http://127.0.0.1:10172",
        "https": "http://127.0.0.1:10172"}

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Referer': f'{self.host}/',
        }
        self._session = requests.Session()

    def getName(self):
        return "AVToday HTML精简版"

    def isVideoFormat(self, url):
        u = (url or '').lower()
        return any(x in u for x in ['.m3u8', '.mp4', '.flv', '.mkv', '.avi', '.webm'])

    def manualVideoCheck(self):
        return False

    # ----------------------------
    #  HTML 抓取
    # ----------------------------
    def _get(self, url: str, timeout: int = 10) -> str:
        resp = self._session.get(url, headers=self.headers, proxies=self.proxies, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        return resp.text

    def _abs(self, u: str) -> str:
        if not u:
            return ''
        return u if u.startswith('http') else urljoin(self.host + '/', u)

    def _fix_path(self, path: str) -> str:
        if not path:
            return '/'
        path = path.strip()
        if path.startswith('http://') or path.startswith('https://'):
            return path
        if not path.startswith('/'):
            path = '/' + path
        return quote(path, safe="/:?=&%")

    def _soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html or '', 'lxml')

    # ----------------------------
    #  首页 / 分类 / 搜索
    # ----------------------------
    def homeContent(self, filter):
        html = self._get(self.host)
        soup = self._soup(html)

        classes = [
            {'type_name': '新片上架', 'type_id': '/new'},
            {'type_name': '人气视频', 'type_id': '/hot'},
            {'type_name': '中文字幕', 'type_id': '/catalog/中文字幕'},
            {'type_name': '无码专区', 'type_id': '/no-mosaic'},
            {'type_name': '类型目录', 'type_id': '/catalog'},
        ]

        videos = self._parse_video_list(soup)
        return {'class': classes, 'filters': {}, 'list': videos}

    def homeVideoContent(self):
        return {'list': self.homeContent(None).get('list', [])}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if pg else 1

        if tid.startswith('http://') or tid.startswith('https://'):
            base = tid
        else:
            base = f"{self.host}{self._fix_path(tid)}"
        base = base.rstrip('/')

        if pg <= 1:
            url = base
        else:
            sep = '&' if '?' in base else '?'
            url = f"{base}{sep}page={pg}"

        html = self._get(url)
        soup = self._soup(html)
        videos = self._parse_video_list(soup)

        return {'list': videos, 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if pg else 1
        url = f"{self.host}/?s={quote(str(key))}"
        html = self._get(url)
        soup = self._soup(html)
        videos = self._parse_video_list(soup)
        return {'list': videos, 'page': pg, 'pagecount': 9999}

    # ----------------------------
    #  详情 / 播放
    # ----------------------------
    def detailContent(self, ids):
        vid = ids[0]
        url = vid if vid.startswith('http') else self._abs(vid)

        html = self._get(url)
        soup = self._soup(html)

        title = ''
        h1 = soup.select_one('h1')
        if h1:
            title = h1.get_text(' ', strip=True)
        if not title and soup.title:
            title = (soup.title.get_text() or '').strip()

        play_urls = self._extract_direct_media_urls(html)

        if not play_urls:
            iframe = soup.select_one('iframe')
            src = (iframe.get('src') or iframe.get('data-src') or '').strip() if iframe else ''
            if src:
                player_url = self._abs(src)
                player_html = self._get(player_url)
                play_urls = self._extract_direct_media_urls(player_html)
                if not play_urls:
                    play_urls = [player_url]

        vod_play_url = '#'.join([f"直链${u}" for u in play_urls]) if play_urls else ''

        return {'list': [{'vod_name': title, 'vod_play_from': '直链', 'vod_play_url': vod_play_url}]}

    def playerContent(self, flag, id, vipFlags):
        if self.isVideoFormat(id):
            return {'parse': 0, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{id}', 'header': self.headers}
        return {'parse': 1, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{id}', 'header': self.headers}

    # ----------------------------
    #  HTML 解析：列表
    # ----------------------------
    def _parse_video_list(self, soup: BeautifulSoup):
        videos = []

        # AVToday 核心卡片
        cards = soup.select('.video-card.real-card')
        if not cards:
            cards = soup.select('article, .search-result, .card')

        for card in cards:
            container = card.parent if ('video-card' in (card.get('class') or [])) else card

            a = container.select_one('a[href]')
            href = (a.get('href') or '').strip() if a else ''
            if not href:
                continue

            # title
            title = ''
            tnode = container.select_one('.video-title')
            if tnode:
                title = tnode.get_text(' ', strip=True)
            if not title and a:
                title = (a.get('title') or '').strip() or a.get_text(' ', strip=True)
            if not title:
                continue

            pic = self._extract_cover(container)
            if not pic:
                continue

            remark = ''
            rnode = container.select_one('.video-duration') or container.select_one('.video-date')
            if rnode:
                remark = rnode.get_text(' ', strip=True)

            videos.append({
                'vod_id': self._abs(href),
                'vod_name': title,
                'vod_pic': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pic}',
                'vod_remarks': remark,
                'style': {"type": "rect", "ratio": 1.33},
            })

        return videos

    def _extract_cover(self, container) -> str:
        # 1) img
        img = container.select_one('img')
        if img:
            for attr in ('data-src', 'data-original', 'src'):
                u = (img.get(attr) or '').strip()
                if u:
                    return self._abs(u)

        # 2) video style background url('...jpg')
        v = container.select_one('video')
        if v:
            style = v.get('style') or ''
            m = re.search(r"background\s*:\s*url\(['\"]?([^'\")]+)['\"]?\)", style, re.I)
            if m:
                return self._abs(m.group(1))

        # 3) 任意 background url(image)
        html = str(container)
        m = re.search(r"url\(['\"]?([^'\")]+\.(?:jpg|jpeg|png|webp))['\"]?\)", html, re.I)
        if m:
            return self._abs(m.group(1))

        return ''

    def _extract_direct_media_urls(self, html: str):
        if not html:
            return []

        urls = []

        # 1) 绝对直链
        urls += re.findall(r'https?://[^\s"\']+\.(?:m3u8|mp4)(?:\?[^\s"\']*)?', html, flags=re.I)

        # 2) 相对直链（常见在 js/json 配置里）
        rels = re.findall(
            r'(?:(?:src|url)\s*[:=]\s*["\'])(/[^"\']+\.(?:m3u8|mp4)(?:\?[^"\']*)?)(?:["\'])',
            html,
            flags=re.I,
        )
        urls += [self._abs(u) for u in rels]

        seen = set()
        out = []
        for u in urls:
            if u and u not in seen:
                seen.add(u)
                out.append(u)
        return out
