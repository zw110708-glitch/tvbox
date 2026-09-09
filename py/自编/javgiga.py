# -*- coding: utf-8 -*-
# 影视交流群
import json
import re
import requests
from pyquery import PyQuery as pq
import sys

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    host = 'https://javgiga.com'
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'referer': 'https://javgiga.com/'
    }

    def init(self, extend=''):
        self.proxies = json.loads(extend).get('proxy', {}) if extend else {}

    def getName(self):
        return 'javgiga'

    def fetch(self, url, params=None):
        try:
            return requests.get(
                url,
                headers=self.headers,
                params=params,
                proxies=getattr(self, 'proxies', {}) or {},
                timeout=15
            ).text
        except:
            return ''

    def homeContent(self, filter):
        # 最新视频用 filter=latest 才有正确分页
        d = pq(self.fetch(self.host + '/?filter=latest'))
        return {
            'class': [
                {'type_name': '最新视频', 'type_id': '/'},
                {'type_name': '有码', 'type_id': '/censored/'},
                {'type_name': '无码', 'type_id': '/uncensored/'},
                {'type_name': '无删减', 'type_id': '/uncensored-leaked/'},
            ],
            'filters': self.get_filters(),
            'list': self.parse_list(self._list_items(d))
        }

    def get_filters(self):
        base = [{
            'key': 'order', 'name': '排序',
            'value': [
                {'n': '随机', 'v': '?filter=random'},
                {'n': '最新', 'v': '?filter=latest'},
            ]
        }]
        return {'/': base, '/censored/': base, '/uncensored/': base, '/uncensored-leaked/': base}

    def _cat_url(self, tid, pg, extend):
        """分类/筛选页地址
        - tid 可能是站内 path（/censored/）
        - 也可能是完整 URL（演员/标签点击传入）
        - 翻页：/page/{pg}/
        - 排序：?filter=random/latest
        """
        from urllib.parse import urlsplit, urlunsplit

        tid = tid or '/'

        # 1) 先把 tid 归一化成 (scheme, netloc, path, query)
        if tid.startswith('http://') or tid.startswith('https://'):
            u = urlsplit(tid)
            scheme, netloc, path, query = u.scheme, u.netloc, u.path, u.query
        else:
            scheme, netloc = 'https', urlsplit(self.host).netloc
            path = tid if tid.startswith('/') else f'/{tid}/'
            # 最新视频（/）默认走 filter=latest（否则 /page/2/ 会重复第一页）
            query = 'filter=latest' if path == '/' else ''

        if not path.endswith('/') and path != '/':
            path += '/'

        # 2) 翻页
        if int(pg) > 1:
            if path == '/':
                path = f'/page/{pg}/'
            else:
                path = path.rstrip('/') + f'/page/{pg}/'

        base = urlunsplit((scheme, netloc, path, query, ''))

        # 3) 排序参数（只处理本站 filter）
        order = (extend or {}).get('order') if isinstance(extend, dict) else ''
        if order:
            if order.startswith('/'):
                order = order[1:]
            if not order.startswith('?'):
                order = '?' + order.lstrip('?')
            base = base.split('?', 1)[0].rstrip('/') + '/' + order

        return base

    def categoryContent(self, tid, pg, filter, extend):
        d = pq(self.fetch(self._cat_url(tid, pg, extend)))
        lst = self.parse_list(self._list_items(d))

        pages = []
        for a in d('.pagination a').items():
            m = re.search(r'/page/(\d+)/', a.attr('href') or '')
            if m:
                pages.append(int(m.group(1)))

        # 首页/部分归档页没有分页区块，但 /page/2/ 实际存在：
        # 这里用“主列表数量是否满 20”来判断是否可能还有下一页。
        if pages:
            pagecount = max(pages)
        else:
            pagecount = 9999 if len(lst) >= 20 else 1

        return {'list': lst, 'page': pg, 'pagecount': pagecount, 'limit': 90, 'total': 999999}

    def searchContent(self, key, quick, pg='1'):
        base = f"{self.host}/page/{pg}/" if int(pg) > 1 else f"{self.host}/"
        d = pq(self.fetch(base, params={'s': key}))
        return {'list': self.parse_list(self._list_items(d)), 'page': pg}

    def _abs(self, url):
        if not url:
            return ''
        if url.startswith('//'):
            return 'https:' + url
        return url

    def _list_items(self, d):
        """精准抓取主列表，避免页面其它模块混入。"""
        items = d('main#main .videos-list article.loop-video')
        return items if items.length else d('#content article.loop-video')

    def _extract_server_map(self, html):
        """从详情页提取 线路名 -> iframe/src(中转页或直链)"""
        d = pq(html)
        mp = {}
        for sp in d('.vsf-tab .tablink').items():
            name = sp.text().strip()
            onclick = sp.attr('onclick') or ''
            m = re.search(r'myFunctionServer(\d+)', onclick)
            if not name or not m:
                continue
            num = m.group(1)
            fm = re.search(r'function\s+myFunctionServer%s\s*\([^)]*\)\s*\{([\s\S]{0,400}?)\}' % num, html)
            if not fm:
                continue
            body = fm.group(1)
            um = re.search(r'\.src\s*=\s*["\']([^"\']+)["\']', body)
            if um:
                mp[name] = self._abs(um.group(1).strip())
        return mp

    def detailContent(self, ids):
        vid = ids[0]
        url = vid if vid.startswith('http') else (self.host + vid if vid.startswith('/') else f"{self.host}/{vid}")
        html = self.fetch(url)
        d = pq(html)

        title = d('h1').text() or d('meta[property="og:title"]').attr('content') or d('title').text() or ''
        title = re.sub(r'\s*\|.*$', '', title).strip()
        pic = d('meta[property="og:image"]').attr('content') or ''

        servers = self._extract_server_map(html)
        if servers:
            play_from = '$$$'.join(servers.keys())
            play_url = '$$$'.join([f"{k}${v}" for k, v in servers.items()])
        else:
            play_from = '默认'
            play_url = f"{title}${url}"

        # 演员（可点击）
        actors = []
        for a in d('#video-actors a').items():
            name = a.text().strip()
            href = a.attr('href')
            if name and href:
                actors.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')

        # 标签（可点击）
        tags = []
        for a in d('.tags-list a').items():
            name = a.text().strip()
            href = a.attr('href')
            if name and href:
                tags.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')

        vod = {
            'vod_name': title,
            'vod_pic': pic,
            'vod_play_from': play_from,
            'vod_play_url': play_url,
        }
        if actors:
            vod['vod_actor'] = ' '.join(actors)
        if tags:
            vod['vod_content'] = ' '.join(tags)

        return {'list': [vod]}

    def _unpack_packer(self, src):
        # 兼容 eval(function(p,a,c,k,e,d){...})(...) 这种 Dean Edwards Packer
        m = re.search(r"eval\(function\(p,a,c,k,e,d\)\{[\s\S]+?\}\((['\"])([\s\S]*?)\1,(\d+),(\d+),(['\"])([\s\S]*?)\5\.split\('\|'\)\)", src)
        if not m:
            return ''
        p = m.group(2)
        try:
            p = bytes(p, 'utf-8').decode('unicode_escape')
        except:
            pass
        a = int(m.group(3))
        c = int(m.group(4))
        k = m.group(6).split('|')

        def _base(n, b):
            s = ''
            while n:
                n, r = divmod(n, b)
                s = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"[r] + s
            return s or '0'

        for i in range(c - 1, -1, -1):
            key = k[i] if i < len(k) else ''
            if not key:
                continue
            p = re.sub(r"\b" + re.escape(_base(i, a)) + r"\b", key, p)
        return p

    def _resolve_media(self, url):
        url = self._abs(url)
        if not url:
            return ''
        if re.search(r'\.(m3u8|mp4)(\?|$)', url):
            return url
        html = self.fetch(url)

        # 处理pack混淆脚本（常见于中转播放页）
        if 'eval(function(p,a,c,k,e,d)' in html:
            unpacked = self._unpack_packer(html)
            if unpacked:
                html += '\n' + unpacked

        m3u8 = re.findall(r'https?://[^\s"\']+\.m3u8[^\s"\']*', html)
        if m3u8:
            return m3u8[0]
        mp4 = re.findall(r'https?://[^\s"\']+\.mp4[^\s"\']*', html)
        if mp4:
            return mp4[0]

        # 兜底：找iframe src
        im = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html)
        if im:
            return self._resolve_media(im.group(1))
        return ''

    def playerContent(self, flag, id, vipFlags):
        media = self._resolve_media(id)
        return {'parse': 0, 'url': media} if media else {'parse': 0, 'url': ''}

    def parse_list(self, items):
        out = []
        for it in items.items():
            a = it('a').eq(0)
            href = a.attr('href')
            if not href:
                continue
            title = a.text().strip() or it('meta[itemprop="name"]').attr('content') or ''
            img = it('img').attr('data-src') or it('img').attr('src') or ''
            vid = href.replace(self.host, '') if href.startswith(self.host) else href
            out.append({'vod_id': vid, 'vod_name': title, 'vod_pic': img, 'vod_remarks': '', 'style': {"type": "rect", "ratio": 1.5}})
        return out

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def homeVideoContent(self):
        pass

    def localProxy(self, param):
        pass

    def liveContent(self, url):
        pass
