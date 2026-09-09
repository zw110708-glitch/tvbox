# -*- coding: utf-8 -*-

import json
import re
import sys
from base64 import b64encode, b64decode
from html import unescape
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    # 站点会从 hjsqw.com 重定向到 hjsqn.com，直接使用新域名避免 Referer/跳转问题
    host = 'https://hjsqn.com'

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36',
        'Referer': 'https://hjsqn.com/',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }

    def init(self, extend=''):
        self.proxies = json.loads(extend).get('proxy', {}) if extend else {}

    def getName(self):
        return 'hjsqw'

    # ---------- http ----------
    def abs_url(self, href: str) -> str:
        return urljoin(self.host + '/', href or '')

    def fetch(self, url: str, params=None) -> str:
        try:
            r = requests.get(url, headers=self.headers, params=params, proxies=self.proxies, timeout=15)
            r.encoding = 'utf-8'
            return r.text or ''
        except Exception:
            return ''

    def soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html or '', 'lxml')

    def build_list_url(self, tid: str, pg: str) -> str:
        tid = tid or '/'
        if not tid.startswith('/'):
            tid = '/' + tid
        if not tid.endswith('/'):
            tid += '/'
        if int(pg) <= 1:
            return self.abs_url(tid)
        if tid == '/':
            return self.abs_url(f'/page/{pg}/')
        return self.abs_url(f'{tid}page/{pg}/')

    # ---------- img proxy + decrypt (AES only) ----------
    def e64(self, text: str) -> str:
        return b64encode(str(text).encode()).decode()

    def d64(self, text: str) -> str:
        return b64decode(str(text).encode()).decode()

    def proxy_img(self, img_url: str) -> str:
        if not img_url:
            return ''
        if not str(img_url).startswith('http'):
            img_url = self.abs_url(img_url)
        return f"{self.getProxyUrl()}&url={self.e64(img_url)}&type=img"

    def aesimg(self, data: bytes) -> bytes:
        if not data or len(data) < 16:
            return data
        if data.startswith(b'\xff\xd8') or data.startswith(b'\x89PNG') or data.startswith(b'GIF8'):
            return data

        keys = [
            (b'f5d965df75336270', b'97b60394abc2fbe1'),
            (b'75336270f5d965df', b'abc2fbe197b60394'),
        ]
        for k, v in keys:
            try:
                dec = unpad(AES.new(k, AES.MODE_CBC, v).decrypt(data), 16)
                if dec.startswith(b'\xff\xd8') or dec.startswith(b'\x89PNG') or dec.startswith(b'GIF8'):
                    return dec
            except Exception:
                pass
            try:
                dec = unpad(AES.new(k, AES.MODE_ECB).decrypt(data), 16)
                if dec.startswith(b'\xff\xd8') or dec.startswith(b'\x89PNG') or dec.startswith(b'GIF8'):
                    return dec
            except Exception:
                pass
        return data

    # ---------- home ----------
    def homeContent(self, filter):
        html = self.fetch(self.host + '/')
        return {
            'class': [
                {'type_name': '海角首页', 'type_id': '/'},
                {'type_name': '海角热门', 'type_id': '/sort/hot/'},
                {'type_name': '今日更新', 'type_id': '/sort/today/'},
                {'type_name': '海角探花', 'type_id': '/category/hjth/'},
                {'type_name': '海角网黄', 'type_id': '/category/hjwh/'},
                {'type_name': '海角看片', 'type_id': '/category/kpzq/'},
                {'type_name': '海角吃瓜', 'type_id': '/category/hjcg/'},
                {'type_name': '海角原创', 'type_id': '/category/hjyc/'},
                {'type_name': '海角乱伦', 'type_id': '/category/hjll/'},
            ],
            'filters': {},
            'list': self._parse_video_list(html),
        }

    # ---------- list (精准：仅 .xqbj-list-rows) ----------
    def _parse_video_list(self, html: str):
        s = self.soup(html)
        videos = []
        seen = set()

        for a in s.select('.xqbj-list-rows a[href^="/archives/"]'):
            href = a.get('href') or ''
            if not href or 'embed' in href:
                continue
            if re.match(r'^/archives/\d+$', href):
                href += '/'
            if href in seen:
                continue

            title = (a.get('title') or '').strip()
            if not title:
                t = a.select_one('.xqbj-list-rows-image-title')
                title = t.get_text(' ', strip=True) if t else ''
            title = re.sub(r'\s+', ' ', title).strip()
            if not title:
                continue

            img = a.select_one('img[z-image-loader-url]')
            cover = (img.get('z-image-loader-url') if img else '') or ''

            seen.add(href)
            videos.append({
                'vod_id': href,
                'vod_name': title,
                'vod_pic': self.proxy_img(cover),
                'vod_remarks': '',
                'vod_tag': '',
                'style': {"type": "rect", "ratio": 1.01},
            })

        return videos

    def _parse_pagecount(self, tid: str, html: str) -> int:
        if not tid:
            tid = '/'
        if not tid.startswith('/'):
            tid = '/' + tid
        if not tid.endswith('/'):
            tid += '/'

        patt = re.escape(tid) + r'page/(\d+)/'
        pages = [int(x) for x in re.findall(patt, html)]
        return max(pages) if pages else 1

    # ---------- category/detail/player ----------
    def categoryContent(self, tid, pg, filter, extend):
        url = self.build_list_url(tid, pg)
        html = self.fetch(url)
        return {
            'list': self._parse_video_list(html),
            'page': pg,
            'pagecount': self._parse_pagecount(tid, html),
            'limit': 90,
            'total': 999999,
        }

    def detailContent(self, ids):
        vid = ids[0]
        url = self.abs_url(vid)
        html = self.fetch(url)
        s = self.soup(html)

        m = re.search(r'/archives/(\d+)', url)
        video_id = m.group(1) if m else ''

        title = (s.select_one('h1').get_text(strip=True) if s.select_one('h1') else '')
        if not title and s.title:
            title = s.title.get_text(strip=True)

        pic = ''
        og = s.select_one('meta[property="og:image"]')
        if og:
            pic = og.get('content') or ''
        if not pic:
            img = s.select_one('img[z-image-loader-url]')
            if img:
                pic = img.get('z-image-loader-url') or ''

        # 1) 标签：.tags-group2 a[href^="/tag/"] -> vod_content (a=cr:)
        tag_links = []
        tg = s.select_one('.tags-group2')
        if tg:
            for a in tg.select('a[href^="/tag/"]'):
                name = a.get_text(strip=True)
                href = a.get('href') or ''
                if name and href:
                    tag_links.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')

        # 2) 演员：可点击，写入 vod_actor（按你给的参考写法：列表 -> join）
        actors = []
        # 页面里 .nav-user 有多处（顶部用户区也有），这里必须定位到正文作者信息块
        author_wrap = s.select_one('.novel-info .text-title a[href^="/author/"]')
        if author_wrap:
            # 取作者名：优先 h2
            name_el = author_wrap.select_one('h2')
            name = (name_el.get_text(strip=True) if name_el else '').strip()
            href = (author_wrap.get('href') or '').strip()
            if name and href:
                actors.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')
        else:
            # 兜底：从正文区域找 nav-user
            nu = s.select_one('.novel-info .nav-user')
            if nu:
                for a in nu.select('a[href^="/author/"]'):
                    name_el = a.select_one('h2')
                    name = (name_el.get_text(strip=True) if name_el else '').strip()
                    href = (a.get('href') or '').strip()
                    if name and href:
                        actors.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')

        vod = {
            'vod_name': title,
            'vod_pic': self.proxy_img(pic),
            'vod_play_from': '海角',
            'vod_play_url': f'{title}${video_id}',
        }
        if tag_links:
            vod['vod_content'] = ' '.join(tag_links)
        if actors:
            vod['vod_actor'] = ' '.join(actors)

        return {'list': [vod]}

    def searchContent(self, key, quick, pg='1'):
        params = {'text': key}
        if int(pg) > 1:
            params['p'] = pg
        html = self.fetch(self.host + '/search', params=params)
        return {'list': self._parse_video_list(html), 'page': pg}

    def playerContent(self, flag, id, vipFlags):
        # 站点 embed 接口实际为 /archives/embed/?id=xxx（少了斜杠会 302 -> /archives/embed/ 丢失参数，导致播放地址为空）
        embed_url = f'{self.host}/archives/embed/?id={id}'
        html = self.fetch(embed_url)

        video_url = ''
        m = re.search(r"data-config='([^']+)'", html)
        if m:
            try:
                conf = json.loads(unescape(m.group(1)))
                video_url = (conf.get('video') or {}).get('url') or ''
            except Exception:
                pass
        if not video_url:
            m2 = re.search(r'(https?://[^\s"\']+\.(?:m3u8|mp4)(?:\?[^"\']*)?)', html)
            if m2:
                video_url = m2.group(1)

        return {
            'parse': 0,
            'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{video_url} 'or '',
            'header': {
                'User-Agent': self.headers['User-Agent'],
                'Referer': embed_url,
                'Origin': self.host,
            },
        }

    def localProxy(self, param):
        try:
            if param.get('type') != 'img':
                return [404, 'text/plain', b'']
            url = param.get('url')
            if not url:
                return [404, 'text/plain', b'']

            real_url = url if str(url).startswith('http') else self.d64(url)
            r = requests.get(real_url, headers=self.headers, proxies=self.proxies, timeout=15)
            content = self.aesimg(r.content or b'')

            ctype = 'image/jpeg'
            if content.startswith(b'\x89PNG'):
                ctype = 'image/png'
            elif content.startswith(b'GIF8'):
                ctype = 'image/gif'
            return [200, ctype, content]
        except Exception:
            return [404, 'text/plain', b'']

    # ---------- unused placeholders ----------
    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def homeVideoContent(self):
        pass

    def liveContent(self, url):
        pass
