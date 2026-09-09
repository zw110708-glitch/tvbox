# -*- coding: utf-8 -*-
# XP天堂 https://xpxp618.com  —— OK影视 视频源（动态分类 + 图片AES解密 + m3u8直链）
import json
import re
from base64 import b64encode, b64decode
from urllib.parse import quote, urljoin

import requests
from pyquery import PyQuery as pq

from base.spider import Spider

try:
    from Crypto.Cipher import AES
except Exception:
    AES = None


class Spider(Spider):
    HOST = 'https://xpxp618.com'
    IMG_KEY = b'f5d965df75336270'   # 站点图片 AES-CBC 密钥（首页 JS 实测）
    IMG_IV = b'97b60394abc2fbe1'

    def init(self, extend=''):
        try:
            config = json.loads(extend) if isinstance(extend, str) and extend.strip() else (extend or {})
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}

        self.host = (config.get('host') or self.HOST).rstrip('/')
        self.plp = config.get('plp', '')        # 播放器/封面/播放地址 URL 前缀
        self.proxy = config.get('proxy', {})    # 内部请求代理

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.host + '/',
        }
        self._sess = requests.Session()
        self._nav = {}      # 二级分组名 -> [(标签名, url), ...]
        self._icache = {}   # 图片解密缓存  url -> (mime, bytes)

    def getName(self):
        return 'XP天堂'

    def isVideoFormat(self, url):
        return bool(url and re.search(r'\.(m3u8|mp4|ts)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        try:
            self._sess.close()
        except Exception:
            pass

    # ---------------- 请求 / 工具 ----------------
    def _get(self, url, timeout=15):
        return self._sess.get(url, headers=self.headers, proxies=self.proxy, timeout=timeout, verify=False)

    def _text(self, r):
        try:
            m = re.search(r'charset=([\w\-]+)', (r.headers or {}).get('Content-Type', ''), re.I)
            if m:
                return r.content.decode(m.group(1), 'ignore')
        except Exception:
            pass
        return r.content.decode('utf-8', 'ignore')

    def _abs(self, u):
        if not u:
            return ''
        if u.startswith('http'):
            return u
        if u.startswith('//'):
            return 'https:' + u
        return urljoin(self.host + '/', u)

    def _cr(self, href, name):
        if not href or not name:
            return ''
        return '[a=cr:%s/]%s[/a]' % (json.dumps({'id': self._abs(href), 'name': name}, ensure_ascii=False), name)

    # ---------------- 图片（AES 解密代理） ----------------
    def _proxy_img(self, pic):
        if not pic:
            return ''
        try:
            proxy = self.getProxyUrl()
        except Exception:
            proxy = ''
        if not proxy:
            return self.plp + pic
        return proxy + '&type=img&url=' + b64encode(pic.encode('utf-8')).decode()

    def localProxy(self, param):
        if not isinstance(param, dict) or param.get('type') != 'img':
            return [404, 'text/plain', b'']
        url = param.get('url') or ''
        if url and not url.startswith('http'):
            try:
                url = b64decode(url).decode('utf-8')
            except Exception:
                return [404, 'text/plain', b'']
        if not url:
            return [404, 'text/plain', b'']
        if url in self._icache:
            mime, data = self._icache[url]
            return [200, mime, data]
        try:
            r = self._get(url)
            raw = r.content or b''
        except Exception:
            return [404, 'text/plain', b'']
        data = raw if self._is_img(raw) else self._aes(raw)
        if not self._is_img(data):
            return [404, 'text/plain', b'']
        mime = self._mime(data)
        self._icache[url] = (mime, data)
        return [200, mime, data]

    def _aes(self, data):
        if not data or len(data) < 16 or AES is None:
            return data
        try:
            dec = AES.new(self.IMG_KEY, AES.MODE_CBC, self.IMG_IV).decrypt(data)
            pad = dec[-1]
            if 1 <= pad <= 16:
                dec = dec[:-pad]
            return dec
        except Exception:
            return data

    @staticmethod
    def _is_img(b):
        return bool(b) and (b.startswith(b'\xff\xd8') or b.startswith(b'\x89PNG') or b.startswith(b'GIF'))

    @staticmethod
    def _mime(b):
        if b.startswith(b'\xff\xd8'):
            return 'image/jpeg'
        if b.startswith(b'\x89PNG'):
            return 'image/png'
        if b.startswith(b'GIF'):
            return 'image/gif'
        return 'application/octet-stream'

    # ---------------- 导航解析（动态分类 + 二级分组） ----------------
    def _parse_nav(self, text):
        m = re.search(r'<nav class="app-nav.*?</nav>', text, re.S)
        nav = m.group(0) if m else ''
        classes = []
        groups = []
        parts = re.split(r'<h2[^>]*>\s*([^<]+?)\s*</h2>', nav)
        for i in range(1, len(parts), 2):
            title = parts[i].strip()
            content = parts[i + 1] if i + 1 < len(parts) else ''
            items = []
            for href, txt in re.findall(r'<a[^>]*href="(/[^"]+)"[^>]*>(.*?)</a>', content, re.S):
                name = re.sub(r'<[^>]+>', '', txt)
                name = re.sub(r'\s+', ' ', name).strip()
                name = re.sub(r'^[^\u4e00-\u9fffA-Za-z0-9]+', '', name)
                if not name:
                    continue
                if title == '选片' and '/article' in href:
                    continue
                items.append((name, href))
            if title == '选片':
                classes = items
            elif items:
                groups.append({'name': title, 'tags': items})
        return classes, groups

    def _ensure_nav(self):
        try:
            r = self._get(self.host + '/')
            _, groups = self._parse_nav(self._text(r))
            self._nav = {g['name']: g['tags'] for g in groups}
        except Exception:
            pass

    # ---------------- 列表解析 ----------------
    def _videos(self, doc):
        out = []
        seen = set()
        for a in doc('.bind_video_img a[href*="/videos/"]').items():
            href = (a.attr('href') or '').strip()
            img = a('img.zximg')
            name = (img.attr('alt') or '').strip()
            if not name:
                continue
            vid = self._abs(href)
            if vid in seen:
                continue
            seen.add(vid)
            pic = img.attr('z-image-loader-url') or img.attr('data-src') or img.attr('src') or ''
            pic = self._abs(pic)
            dur = (a('.absolute-bottom-right .label').text() or '').strip()
            out.append({
                'vod_id': vid,
                'vod_name': name,
                'vod_pic': self._proxy_img(pic) if pic else '',
                'vod_remarks': dur,
                'style': {'type': 'rect', 'ratio': 1.33},
            })
        return out

    def _themes(self, doc):
        out = []
        seen = set()
        for a in doc('div.video-img-box a[href*="/theme/detail/"]').items():
            href = (a.attr('href') or '').strip()
            m = re.search(r'/theme/detail/(\d+)', href)
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            name = (a('h4').text() or '').strip()
            if not name:
                continue
            remarks = (a('.absolute-center .label').text() or '').strip()
            img = a('img.zximg')
            pic = img.attr('z-image-loader-url') or img.attr('data-src') or ''
            pic = self._abs(pic)
            out.append({
                'vod_id': self._abs(href).rstrip('/') + '/hot/',
                'vod_name': name,
                'vod_pic': self._proxy_img(pic) if pic else '',
                'vod_remarks': remarks,
                'vod_tag': 'folder',
                'style': {'type': 'rect', 'ratio': 1.33},
            })
        return out

    def _tags(self, name):
        if not self._nav:
            self._ensure_nav()
        items = self._nav.get(name) or []
        out = []
        for n, href in items:
            out.append({
                'vod_id': self._abs(href),
                'vod_name': n,
                'vod_pic': '',
                'vod_remarks': '',
                'vod_tag': 'folder',
                'style': {'type': 'rect', 'ratio': 0.99},
            })
        return out

    # ---------------- 页面接口 ----------------
    def homeContent(self, filter):
        result = {'class': [], 'list': []}
        try:
            r = self._get(self.host + '/')
            text = self._text(r)
            doc = pq(r.content)
            classes = [
                {'type_id': '/new/', 'type_name': '最新更新'},
                {'type_id': '/popular/today/', 'type_name': '昨日热门'},
                {'type_id': '/popular/all/', 'type_name': '热门AV'},
                {'type_id': '/theme/', 'type_name': '影片主题'},
            ]
            nav_classes, nav_groups = self._parse_nav(text)
            fixed_urls = {c['type_id'] for c in classes}
            for name, href in nav_classes:
                if href in fixed_urls:
                    continue
                classes.append({'type_id': href, 'type_name': name})
            for g in nav_groups:
                classes.append({'type_id': 'taggrp:' + g['name'], 'type_name': g['name']})
            self._nav = {g['name']: g['tags'] for g in nav_groups}
            result['class'] = classes
            result['list'] = self._videos(doc)
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        try:
            r = self._get(self.host + '/')
            return {'list': self._videos(pq(r.content))}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        tid = tid or ''
        pg = int(pg or 1)
        if tid == 'home' or tid == '':
            return self._list_page(self.host + '/', pg)
        if tid.startswith('taggrp:'):
            tags = self._tags(tid[7:])
            return {'list': tags, 'page': 1, 'pagecount': 1, 'limit': 90, 'total': len(tags)}
        if tid == '/theme/' or tid.rstrip('/').endswith('/theme'):
            try:
                r = self._get(self.host + '/theme/')
                themes = self._themes(pq(r.content))
                return {'list': themes, 'page': 1, 'pagecount': 1, 'limit': 90, 'total': len(themes)}
            except Exception:
                return {'list': [], 'page': 1, 'pagecount': 1, 'limit': 90, 'total': 0}
        return self._list_page(self._abs(tid), pg)

    def _list_page(self, url, pg):
        if pg > 1:
            url = url.rstrip('/') + '/' + str(pg) + '/'
        try:
            r = self._get(url)
            text = self._text(r)
            videos = self._videos(pq(r.content))
            has_next = 'rel="next"' in text
            return {'list': videos, 'page': pg, 'pagecount': pg + 1 if has_next else pg, 'limit': 90, 'total': 999999}
        except Exception:
            return {'list': [], 'page': pg, 'pagecount': pg, 'limit': 90, 'total': 0}

    def detailContent(self, ids):
        url = self._abs(ids[0] if ids else '')
        if '/videos/' not in url:
            return self._playlist(url)
        return self._detail(url)

    def _detail(self, url):
        try:
            r = self._get(url)
            text = self._text(r)
            doc = pq(r.content)
        except Exception:
            return {'list': []}

        title = (doc('h1').eq(0).text() or '').strip()
        play = self._extract_play(text)

        # 演员（可点击）
        actors = []
        for a in doc('a.model').items():
            href = (a.attr('href') or '').strip()
            name = (a('.actress-name').text() or '').strip()
            if name and '/actress/' in href:
                cr = self._cr(href, name)
                if cr:
                    actors.append(cr)

        # 主题 + 标签（可点击，放 vod_content 前面）
        theme, tags = [], []
        for a in doc('h5.tags a').items():
            href = (a.attr('href') or '').strip()
            name = (a.text() or '').strip()
            cr = self._cr(href, name) if name and href else ''
            if not cr:
                continue
            if 'cat' in (a.attr('class') or ''):
                theme.append(cr)
            else:
                tags.append(cr)

        # 简介（去掉站点残留的 br> 及元数据行）
        intro = (doc('h6.dx-text').text() or '').strip()
        intro = intro.split('发行日期')[0].strip()
        intro = re.sub(r'\s*br>\s*', ' ', intro).strip()

        # 时长 / 浏览
        dur = (doc('meta[property="video:duration"]').attr('content') or '').strip()
        if dur.isdigit():
            s = int(dur)
            dur = '%d:%02d' % (s // 60, s % 60)
        watch = (doc('.actress-info [class*="interaction_watch_count"]').text() or '').strip()
        remarks = ' '.join(x for x in (watch, dur) if x).strip()

        content_parts = []
        if theme:
            content_parts.append('主题: ' + ' '.join(theme))
        if tags:
            content_parts.append('标签: ' + ' '.join(tags))
        if intro:
            content_parts.append(intro)

        vod = {
            'vod_name': title,
            'vod_play_from': '直链',
            'vod_play_url': '正片$' + play if play else '',
            'vod_content': '\n'.join(content_parts),
        }
        if actors:
            vod['vod_actor'] = ' '.join(actors)
        if remarks:
            vod['vod_remarks'] = remarks
        return {'list': [vod]}

    def _playlist(self, url):
        try:
            r = self._get(url)
            doc = pq(r.content)
        except Exception:
            return {'list': []}
        title = (doc('h1').eq(0).text() or '').strip()
        title = re.split(r'\s*[|\-]\s*', title)[0].strip() if title else ''
        videos = self._videos(doc)
        play = '#'.join(v['vod_name'] + '$' + v['vod_id'] for v in videos if v.get('vod_id'))
        vod = {
            'vod_id': url,
            'vod_name': title or '视频列表',
            'vod_play_from': '播放',
            'vod_play_url': play,
        }
        return {'list': [vod]}

    def searchContent(self, key, quick, pg='1'):
        pg = int(pg or 1)
        kw = quote((key or '').strip())
        if not kw:
            return {'list': [], 'page': pg}
        url = self.host + '/search/' + kw + '/'
        if pg > 1:
            url = url.rstrip('/') + '/' + str(pg) + '/'
        try:
            r = self._get(url)
            text = self._text(r)
            return {'list': self._videos(pq(r.content)), 'page': pg, 'pagecount': pg + 1 if 'rel="next"' in text else pg, 'limit': 90, 'total': 999999}
        except Exception:
            return {'list': [], 'page': pg}

    # ---------------- 播放器 ----------------
    def _extract_play(self, text):
        m = re.search(r'var\s+hlsUrl\s*=\s*["\']([^"\']+)["\']', text)
        if m:
            return m.group(1)
        m = re.search(r'https?://[^"\'\s<>]+?\.m3u8[^"\'\s<>]*', text)
        return m.group(0) if m else ''

    def playerContent(self, flag, id, vipFlags):
        url = id or ''
        if self.isVideoFormat(url):
            return {'parse': 0, 'url': self.plp + url, 'header': self.headers}
        # 列表转剧集时 id 为详情页 URL，二次请求提取 m3u8
        try:
            r = self._get(self._abs(url))
            play = self._extract_play(self._text(r))
            if play:
                return {'parse': 0, 'url': self.plp + play, 'header': self.headers}
        except Exception:
            pass
        return {'parse': 1, 'url': url, 'header': self.headers}
