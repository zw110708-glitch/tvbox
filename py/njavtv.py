# -*- coding: utf-8 -*-
"""18.py (direct-link)

面向 **njavtv.sbs/zh-hans** 的极简版本：
- 仅保留：分类/列表解析、详情页直链播放地址提取、搜索

实现思路（直链）：
- 详情页找到真正播放器 iframe（过滤广告 iframe）
- 若 iframe 为 /player/xxx?data=... 播放器页：请求该页并解析 MASPlayer 配置，拼出真实 m3u8 直链
- 直接把 m3u8 直链写入 vod_play_url；playerContent 只做直链透传

"""

import base64
import json
import re
import sys
from urllib.parse import quote, urljoin, urlparse, urlencode, urlsplit, urlunsplit, parse_qsl

import requests
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    _UA = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )

    _DEFAULT_HOST = 'https://njavtv.sbs/zh-hans'
    _LIST_SELECTOR = '.video-block'

    def init(self, extend=""):
        cfg = {}
        if extend:
            try:
                cfg = json.loads(extend) if isinstance(extend, str) else (extend or {})
            except Exception:
                cfg = {}

        self.proxies = cfg.get('proxies') or {}
        self.host = (cfg.get('host') or self._DEFAULT_HOST).rstrip('/')

        self.session = requests.Session()
        self.session.headers.update(
            {
                'User-Agent': self._UA,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Referer': f'{self.host}/',
                # 不要默认携带 Origin：会导致部分 CDN 返回 security error

            }
        )

    def getName(self):
        return 'njavtv 直链解析'

    def isVideoFormat(self, url):
        u = (url or '').lower()
        return (
            any(ext in u for ext in ('.m3u8', '.mp4', '.ts', 'master.m3u8', 'master.txt'))
            or '/hls/' in u
            or '/api/files/' in u
        )

    def manualVideoCheck(self):
        return False

    # --- internal ---
    def _get(self, url: str, timeout: int = 12, referer: str = ''):
        # 对不同资源类型使用更合适的请求头：
        # - HTML 页面：沿用 session 默认 Accept
        # - m3u8/分片等二进制资源：避免发送 HTML Accept/Origin 触发“security error”
        headers = {}
        if referer:
            headers['Referer'] = referer

        low = (url or '').lower()
        if any(k in low for k in ('.m3u8', 'master.txt', '/hls/', '/api/files/')):
            headers.update({'Accept': '*/*'})
            # 不发送 Origin（部分边缘节点会据此拦截）
            headers.pop('Origin', None)

        r = self.session.get(url, proxies=self.proxies, timeout=timeout, headers=headers)
        r.encoding = r.apparent_encoding or r.encoding
        return r

    @staticmethod
    def _soup(html: str):
        return BeautifulSoup(html, 'lxml')

    def _abs(self, u: str, base: str):
        u = (u or '').strip()
        if not u:
            return ''
        return u if u.startswith('http') else urljoin(base, u)

    def _pick_player_iframe(self, soup: BeautifulSoup):
        """只做必要过滤：去广告 iframe，优先命中 /player/ 或 data= 播放入口。"""
        best = ''
        for fr in soup.find_all('iframe'):
            s = (
                fr.get('src')
                or fr.get('data-src')
                or fr.get('data-lazy-src')
                or fr.get('data-original')
                or ''
            ).strip()
            if not s:
                continue
            low = s.lower()
            if 'herebyad' in low or low.startswith('/hereby'):
                continue
            if any(k in low for k in ('/player/', 'data=', 'player.php', 'embed')):
                return s
            if not best and s.startswith('http'):
                best = s
        return best

    @staticmethod
    def _append_query(url: str, params: dict):
        """安全追加 query 参数（避免已有 ? 时重复）。"""
        if not params:
            return url
        sp = urlsplit(url)
        q = dict(parse_qsl(sp.query, keep_blank_values=True))
        q.update({k: str(v) for k, v in params.items()})
        return urlunsplit((sp.scheme, sp.netloc, sp.path, urlencode(q, doseq=True), sp.fragment))

    def _extract_masplayer_config(self, html: str):
        """从播放器 HTML 中提取 MASPlayer 的配置对象（dict）。"""
        if not html:
            return {}
        s = html.replace('\\/', '/').strip()

        # 1) 直接抓 MASPlayer(vhash, {...})
        m = re.search(r'MASPlayer\([^,]+,\s*(\{.*?\})\s*\)\s*;?', s, re.S)
        if m:
            blob = m.group(1)
            try:
                return json.loads(blob)
            except Exception:
                pass

        # 2) 兜底：正则抓关键字段
        cfg = {}
        m_url = re.search(r'"videoUrl"\s*:\s*"([^\"]+)"', s)
        if m_url:
            cfg['videoUrl'] = m_url.group(1)
        m_srv = re.search(r'"videoServer"\s*:\s*"?(\d+)"?', s)
        if m_srv:
            cfg['videoServer'] = m_srv.group(1)
        m_disk = re.search(r'"videoDisk"\s*:\s*(null|"([^\"]*)")', s)
        if m_disk and m_disk.group(2):
            cfg['videoDisk'] = m_disk.group(2)
        return cfg

    def _player_page_to_m3u8(self, player_url: str):
        """把 /player/...data=... 播放器页解析为可播放 m3u8 直链。"""
        u = (player_url or '').strip()
        if not u:
            return ''

        low = u.lower()
        # njav 的播放器入口一般包含 /player/ 且带 data=（或旧版 index.php?data=）
        if '/player/' not in low and 'data=' not in low:
            return ''

        pr = urlparse(u)
        host = pr.netloc
        scheme = pr.scheme or 'https'

        r = self._get(u, referer=self.host + '/')
        html = (r.text or '').replace('\\/', '/')

        cfg = self._extract_masplayer_config(html)
        video_url = (cfg.get('videoUrl') or '').strip()
        video_server = str(cfg.get('videoServer') or '1').strip()
        video_disk = (cfg.get('videoDisk') or '')

        if not video_url:
            return ''

        # videoUrl 可能是绝对地址、相对地址、或以 // 开头
        if video_url.startswith('http'):
            base = video_url
        elif video_url.startswith('//'):
            base = f'{scheme}:{video_url}'
        else:
            base = urljoin(f'{scheme}://{host}/', video_url)

        # 官方播放器会在 videoUrl 上追加 s/d 作为路由参数
        d = base64.b64encode((video_disk or '').encode()).decode()
        base = self._append_query(base, {'s': video_server, 'd': d})

        # 兼容：部分播放器只认 .m3u8，不认 master.txt
        # 该站点通常同时提供 master.m3u8 与 master.txt（内容一致）
        base = re.sub(r'/master\.txt(\?|$)', r'/master.m3u8\1', base)

        # 进一步兼容：不少播放器/代理不支持 master playlist（多码率），
        # 这里尝试自动下探到第一个变体清单（通常是 720p）。
        try:
            rr = self._get(base, timeout=12, referer=self.host + '/')
            text = (rr.text or '').strip()
            if '#EXT-X-STREAM-INF' in text:
                # 取第一个 URL 行作为变体清单地址
                urls = re.findall(r'^(https?://\S+)$', text, re.M)
                if urls:
                    return urls[0].strip()
        except Exception:
            pass

        return base

    # --- home ---
    def homeContent(self, filter):
        try:
            r = self._get(f'{self.host}/')
            if r.status_code != 200:
                return {'class': [], 'filters': {}, 'list': []}

            soup = self._soup(r.text)

            classes = []
            for a in soup.select('#menu-main-menu li.menu-item-object-category > a'):
                name = a.get_text(strip=True)
                href = (a.get('href') or '').strip()
                if name and href:
                    classes.append({'type_name': name, 'type_id': href})

            return {'class': classes, 'filters': {}, 'list': self._parse_list(soup)}
        except Exception as e:
            print(f'[homeContent] {e}')
            return {'class': [], 'filters': {}, 'list': []}

    def homeVideoContent(self):
        return {'list': (self.homeContent(None) or {}).get('list', [])}

    # --- category ---
    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg) if pg else 1
            url = tid if tid.startswith('http') else urljoin(f'{self.host}/', tid.lstrip('/'))
            url = url.rstrip('/') + ('/' if pg == 1 else f'/page/{pg}/')

            r = self._get(url)
            if r.status_code != 200:
                return {'list': [], 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 0}

            return {
                'list': self._parse_list(self._soup(r.text)),
                'page': pg,
                'pagecount': 9999,
                'limit': 90,
                'total': 999999,
            }
        except Exception as e:
            print(f'[categoryContent] {e}')
            return {'list': [], 'page': int(pg) if pg else 1, 'pagecount': 9999, 'limit': 90, 'total': 0}

    # --- detail ---
    def detailContent(self, ids):
        try:
            raw_id = ((ids[0] if ids else '') or '').strip()
            raw_id = raw_id.split('@', 1)[0].strip()
            url = raw_id if raw_id.lower().startswith('http') else urljoin(f'{self.host}/', raw_id.lstrip('/'))
            if not url:
                url = f'{self.host}/'

            r = self._get(url)
            soup = self._soup(r.text)

            title = (soup.select_one('h1') or soup.select_one('title'))
            title = (title.get_text(strip=True) if title else '').split('|')[0].strip()

            iframe_src = self._pick_player_iframe(soup)
            iframe_url = self._abs(iframe_src, self.host + '/')

            # 直链解析：播放器页 -> m3u8 (master.txt 也是 HLS 播放清单)
            play_url = self._player_page_to_m3u8(iframe_url) or iframe_url or url

            # --- 标签/简介 ---
            tags = []
            try:
                tags_box = soup.select_one('.tags-list .list')
                if tags_box:
                    for a in tags_box.select('a.label[href]'):
                        name = (a.get_text(strip=True) or '').strip()
                        href = (a.get('href') or '').strip()
                        if name and href:
                            href = self._abs(href, self.host + '/')
                            tags.append(
                                f'[a=cr:{json.dumps({"id": href, "name": name}, ensure_ascii=False)}/]{name}[/a]'
                            )
            except Exception:
                tags = []

            desc = ''
            try:
                p = soup.select_one('.video-description p')
                if p:
                    desc = p.get_text(' ', strip=True)
                if not desc:
                    m = soup.select_one('meta[itemprop="description"]')
                    if m:
                        desc = (m.get('content') or '').strip()
            except Exception:
                desc = ''

            vod_content = ''
            if tags:
                vod_content = '标签: ' + ' '.join(tags)
            if desc:
                vod_content = (vod_content + ('\n' if vod_content else '') + desc).strip()

            play = f'播放${play_url}'
            return {
                'list': [
                    {
                        'vod_name': title,
                        'vod_play_from': '直链',
                        'vod_play_url': play,
                        'vod_content': vod_content,
                    }
                ]
            }
        except Exception as e:
            print(f'[detailContent] {e}')
            raw_id = ((ids[0] if ids else '') or '').strip()
            raw_id = raw_id.split('@', 1)[0].strip()
            url = raw_id if raw_id.lower().startswith('http') else urljoin(f'{self.host}/', raw_id.lstrip('/'))
            return {'list': [{'vod_play_from': '直链', 'vod_play_url': f'播放${url or self.host}', 'vod_content': ''}]}

    # --- search ---
    def searchContent(self, key, quick, pg='1'):
        try:
            pg = int(pg) if pg else 1
            r = self._get(f'{self.host}/?s={quote(key)}')
            return {'list': self._parse_list(self._soup(r.text)), 'page': pg, 'pagecount': 9999}
        except Exception as e:
            print(f'[searchContent] {e}')
            return {'list': [], 'page': int(pg) if pg else 1, 'pagecount': 9999}

    # --- player ---
    def playerContent(self, flag, id, vipFlags):
        """只做直链透传：detailContent 已尽量给到 m3u8/mp4 直链。"""
        u = (id or '').strip()
        if not u:
            return {'parse': 1, 'url': '', 'header': {}}

        # 关键修复：不要把 HTML 请求头（Accept: text/html、Origin 等）带给 m3u8/分片请求，
        # 否则 fembeqv2 的边缘节点会返回 "security error"，导致播放器无法拉到清单/分片。
        header = {
            'User-Agent': self._UA,
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        try:
            pr = urlparse(u)
            if pr.scheme and pr.netloc:
                header['Referer'] = f'{pr.scheme}://{pr.netloc}/'
        except Exception:
            pass

        return {'parse': 0 if self.isVideoFormat(u) else 1, 'url': u, 'header': header}

    # --- list parser ---
    def _parse_list(self, soup: BeautifulSoup):
        videos = []
        for it in soup.select(self._LIST_SELECTOR):
            a = it.select_one('a.thumb[href]')
            if not a:
                continue
            href = (a.get('href') or '').strip()
            if not href:
                continue

            title_el = it.select_one('a.infos span.title') or it.select_one('img[alt]')
            title = (
                title_el.get_text(strip=True)
                if title_el and title_el.name != 'img'
                else (title_el.get('alt') if title_el else '')
            )
            title = (title or '').strip()
            if not title:
                continue

            img = it.select_one('img')
            img = ((img.get('data-src') or img.get('src')) if img else '') or ''
            img = img.strip()
            if not img:
                continue

            href = self._abs(href, self.host + '/')
            img = self._abs(img, self.host + '/')

            videos.append(
                {
                    'vod_id': href,
                    'vod_name': title,
                    'vod_pic': img,
                    'vod_remarks': '',
                    'style': {"type": "rect", "ratio": 1.33},
                }
            )
        return videos
