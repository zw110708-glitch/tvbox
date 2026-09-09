import json
import re
import sys
from base64 import b64decode
from urllib.parse import urljoin, quote

import requests
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    """Javhd.today 专用（极简版）：仅保留分类/列表/播放线路解析"""

    def init(self, extend=""):
        cfg = {}
        if extend:
            try:
                cfg = json.loads(extend) if isinstance(extend, str) else (extend or {})
            except Exception:
                cfg = {}

        self.proxies = cfg.get('proxies') or {}
        self.host = (cfg.get('host') or 'https://javhd.today').rstrip('/')
        self.lang = cfg.get('lang') or 'cn'  # 默认中文路径 /cn/

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': f'{self.host}/',
        }

    def getName(self):
        return 'Javhd.today(极简精准)'

    def isVideoFormat(self, url):
        u = (url or '').lower()
        return any(x in u for x in ('.m3u8', '.mp4'))

    def manualVideoCheck(self):
        return False

    # -------- helpers --------
    def _get(self, url):
        r = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=10)
        r.encoding = r.apparent_encoding
        return r.text

    def _soup(self, html):
        return BeautifulSoup(html, 'lxml')

    def _abs(self, href):
        return urljoin(f'{self.host}/', href)

    def _base_cn(self):
        return f"{self.host}/{self.lang}".rstrip('/')

    def _parse_videos(self, soup):
        """解析页面里的视频卡片（站点统一结构：ul.videos > li#video-xxx）"""
        out = []
        seen = set()

        for li in soup.select('ul.videos > li[id^="video-"]'):
            a = li.select_one('a.thumbnail[href]')
            if not a:
                continue

            href = a.get('href', '').strip()
            if not href:
                continue
            vod_id = self._abs(href)
            if vod_id in seen:
                continue

            title = (a.get('title') or '').strip()
            if not title:
                continue

            img = li.select_one('img')
            pic = (img.get('src') or img.get('data-src') or '').strip() if img else ''
            if pic and not pic.startswith('http'):
                pic = self._abs(pic)

            remark = ''
            badge = li.select_one('.video-overlay2')
            if badge:
                remark = badge.get_text(' ', strip=True)

            out.append({
                'vod_id': vod_id,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': remark,
            })
            seen.add(vod_id)

        return out

    # -------- main --------
    def homeContent(self, filter):
        html = self._get(self._base_cn() + '/')
        soup = self._soup(html)

        # 分类：只取 /cn/<slug>/ 的一级分类，排除导航页
        exclude = {
            'releaseday', 'recent', 'playlists', 'request', 'photo', 'categories',
        }

        classes = []
        seen = set()
        for a in soup.select('#menu-main a[href^="/cn/"]'):
            href = (a.get('href') or '').strip()
            m = re.fullmatch(r'/cn/([a-z0-9-]+)/', href)
            if not m:
                continue
            slug = m.group(1)
            if slug in exclude or slug in seen:
                continue

            name = a.get_text(' ', strip=True)
            # 菜单里很多叫“最新更新”，用 slug 兜底成可区分名称
            if not name or name == '最新更新':
                name = slug

            classes.append({'type_name': name, 'type_id': href})
            seen.add(slug)

        # 首页列表（今天上传的Jav等模块，结构统一）
        videos = self._parse_videos(soup)

        return {'class': classes, 'filters': {}, 'list': videos}

    def homeVideoContent(self):
        return {'list': self.homeContent(None).get('list', [])}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        base = tid if tid.startswith('http') else self._abs(tid)
        url = base if pg == 1 else base.rstrip('/') + f'/{pg}/'

        html = self._get(url)
        soup = self._soup(html)
        videos = self._parse_videos(soup)

        return {
            'list': videos,
            'page': pg,
            'pagecount': 9999,
            'limit': 90,
            'total': 999999,
        }

    def detailContent(self, ids):
        url = ids[0] if ids[0].startswith('http') else self._abs(ids[0])
        html = self._get(url)
        soup = self._soup(html)

        title = (soup.select_one('h1') or soup.select_one('title'))
        vod_title = title.get_text(' ', strip=True) if title else ''
        vod_title = vod_title.split('|')[0].strip() if vod_title else ''

        # 播放线路：button.button_choice_server[data-embed]（base64）
        plist = []
        seen = set()
        for btn in soup.select('.button_choice_server[data-embed]'):
            enc = (btn.get('data-embed') or '').strip()
            if not enc:
                continue
            enc += '=' * (-len(enc) % 4)
            try:
                play = b64decode(enc.encode()).decode('utf-8', 'ignore').strip()
            except Exception:
                continue

            if not play or play in seen:
                continue

            # 重要：vod_play_url 的分隔符使用 "#" 和 "$"，URL/名称里一旦包含这些字符会导致后续线路被切碎。
            # 典型：Upnshare 的链接包含 "#t16maf"。
            play = play.replace('#', '%23').replace('$', '%24')

            name = (btn.get('data-name') or btn.get_text(' ', strip=True) or '线路').strip()
            name = name.replace('#', ' ').replace('$', ' ').strip()

            plist.append(f'{name}${play}')
            seen.add(play)

        play_url = '#'.join(plist) if plist else f'网页播放${url}'

        return {'list': [{'vod_play_from': 'Javhd', 'vod_play_url': play_url, 'vod_content': vod_title}]}

    def searchContent(self, key, quick, pg="1"):
        # 站点搜索：/cn/search/video/?s=xxx
        pg = int(pg or 1)
        url = f"{self._base_cn()}/search/video/?s={quote(key)}"
        html = self._get(url)
        soup = self._soup(html)
        videos = self._parse_videos(soup)
        return {'list': videos, 'page': pg, 'pagecount': 9999}

    def _unpack_packer(self, html: str) -> str:
        """解包 Dean Edwards packer：eval(function(p,a,c,k,e,d){...}('payload',a,c,'k|...'.split('|')))
        只为 mycloudz/cloudwish 这类 jwplayer 页面服务。
        """
        m = re.search(
            r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\('(.+?)',(\d+),(\d+),'(.+?)'\.split\('\|'\)\)\)",
            html,
            re.S,
        )
        if not m:
            return ''
        payload, a, c, k = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4).split('|')
        payload = payload.replace("\\'", "'").replace('\\\\', '\\')

        chars = '0123456789abcdefghijklmnopqrstuvwxyz'

        def to_base(n: int, base: int) -> str:
            if n == 0:
                return '0'
            s = ''
            while n:
                n, r = divmod(n, base)
                s = chars[r] + s
            return s

        for i in range(c - 1, -1, -1):
            if i < len(k) and k[i]:
                token = to_base(i, a)
                payload = re.sub(rf"\b{re.escape(token)}\b", k[i], payload)
        return payload

    def _extract_m3u8(self, page_url: str) -> str:
        """从第三方播放页提取可直播 m3u8（精准：仅处理已验证的站点结构）"""
        try:
            html = self._get(page_url)
        except Exception:
            # 少数域名证书链异常（如 dooood），不强行处理
            return ''

        # 1) 页面本身就包含 m3u8（turbovid 等）
        m = re.search(r'https?://[^"\s\']+\.m3u8[^"\s\']*', html)
        if m:
            return m.group(0)

        # 2) mycloudz/cloudwish：m3u8 在 packer 解包后的脚本里
        js = self._unpack_packer(html)
        if js:
            m = re.search(r'https?://[^"\s\']+\.m3u8[^"\s\']*', js)
            if m:
                return m.group(0)

        return ''

    def playerContent(self, flag, id, vipFlags):
        """播放器（精准版）

        关键点：
        - HOST/LIVE 只是按钮标签，对地址无影响
        - 除了少数站点外，给的都是“播放页”，需要提取 m3u8 才稳定
        """
        from urllib.parse import urlparse

        u = (id or '').strip()
        if not u.startswith('http'):
            u = self._abs(u)

        # 直链直接播
        if self.isVideoFormat(u):
            return {'parse': 0, 'url': u, 'header': self.headers}

        p = urlparse(u)
        origin = f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else self.host

        # 对已验证可提取的站点，直接转成 m3u8 返回（parse=0）
        if p.netloc in {'mycloudz.cc', 'cloudwish.xyz', 'turbovid.vip'}:
            m3u8 = self._extract_m3u8(u)
            if m3u8:
                hdr = dict(self.headers)
                # CDN 常要求 referer 为原播放页域名
                hdr['Referer'] = origin + '/'
                hdr['Origin'] = origin
                return {'parse': 0, 'url': m3u8, 'header': hdr}

        # 其他站点（如 upnshare/dood）结构更复杂，交给外部解析
        hdr = dict(self.headers)
        hdr['Referer'] = origin + '/'
        hdr['Origin'] = origin
        return {'parse': 1, 'url': u, 'header': hdr}
