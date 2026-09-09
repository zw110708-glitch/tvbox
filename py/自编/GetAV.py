# -*- coding: utf-8 -*-
"""
GetAV (getav.net) 采集器。

站点是 Next.js，列表/详情数据都在 self.__next_f.push 的 flight data 里；
视频源是 m3u8（伪装成 index.txt）。网页/图片/视频都被 Cloudflare 拦截，
统一走 pg.jar 内置代理 10172（p/0/null = 内置默认代理，浏览器 TLS 指纹过 CF）。
"""
import json
import re
import sys
from urllib.parse import parse_qs, quote, urljoin, urlparse

import requests

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def init(self, extend=""):
        cfg = {}
        try:
            cfg = json.loads(extend) if isinstance(extend, str) and extend.strip() else (extend or {})
        except Exception:
            cfg = {}

        self.host = (cfg.get('host') or 'https://getav.net').rstrip('/')
        self.locale_path = (cfg.get('locale_path') or '/zh').rstrip('/') or '/zh'
        self.lang = self.locale_path.strip('/').split('/')[0] or 'zh'

        # 内置代理 10172：null = 用 pg.jar 默认代理（浏览器 TLS 指纹，过 Cloudflare）
        self.proxy = (cfg.get('proxy') or 'http://127.0.0.1:10079/p/0/proxy/').rstrip('/') + '/'

        self.headers = {
            'User-Agent': cfg.get('ua')
            or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        self.s = requests.Session()

    def getName(self):
        return 'GetAV'

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        u = (url or '').lower()
        return u.endswith('.m3u8') or u.endswith('.mp4')

    # ---- 工具 ----
    def _wrap(self, u):
        """加内置代理前缀（幂等）"""
        u = (u or '').strip()
        return u if not u or u.startswith(self.proxy) else self.proxy + u

    def _unwrap(self, u):
        """去代理前缀 + 相对地址转绝对"""
        u = (u or '').strip()
        if u.startswith(self.proxy):
            u = u[len(self.proxy):]
        return u if u.startswith('http') else urljoin(self.host + '/', u)

    def _img(self, u):
        """图片：/xx 是 static.worldstatic.com，再走代理"""
        u = (u or '').strip()
        if not u or u.startswith(self.proxy):
            return u
        if u.startswith('//'):
            u = 'https:' + u
        elif u.startswith('/'):
            u = 'https://static.worldstatic.com' + u
        elif not u.startswith('http'):
            u = urljoin(self.host + '/', u)
        return self.proxy + u

    def _fetch(self, url):
        try:
            r = self.s.get(self._wrap(url), headers=self.headers, timeout=40)
            return r.text if r.status_code == 200 else ''
        except Exception:
            return ''

    # ---- flight data 解析 ----
    def _flight(self, html):
        parts = []
        for m in re.finditer(r'self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)', html or ''):
            try:
                parts.append(json.loads('"' + m.group(1) + '"'))
            except Exception:
                continue
        return '\n'.join(parts)

    def _json_array(self, text, key):
        pos = (text or '').find('"%s":' % key)
        if pos < 0:
            return []
        i = text.find('[', pos)
        if i < 0:
            return []
        depth, in_str, esc = 0, False, False
        for j in range(i, len(text)):
            c = text[j]
            if in_str:
                if esc:
                    esc = False
                elif c == '\\':
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == '[':
                depth += 1
            elif c == ']':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[i:j + 1])
                    except Exception:
                        return []
        return []

    # ---- 列表 ----
    def _extract_cards(self, html):
        flight = self._flight(html)
        if not flight:
            return []
        cards, seen = [], set()
        for m in re.finditer(
            r'"id":"([^"]{2,32})","title":"((?:\\.|[^"\\]){1,300})"(?:(?!"id":).){0,1200}?"localImg":"((?:\\.|[^"\\])*)"',
            flight,
        ):
            vid = m.group(1).lower()
            if vid in seen:
                continue
            seen.add(vid)
            cards.append({
                'vod_id': self._wrap(f'{self.host}/{self.lang}/videos/{vid}'),
                'vod_name': m.group(2) or vid,
                'vod_pic': self._img(m.group(3)),
                'vod_remarks': '',
                'style': {'type': 'rect', 'ratio': 1.33},
            })
            if len(cards) >= 60:
                break
        return cards

    # ---- 详情 ----
    def _extract_movie(self, html):
        flight = self._flight(html)
        if not flight:
            return {}
        start = flight.find('"movie":{"id":"')
        if start < 0:
            return {}
        seg = flight[start:start + 300000]

        def grab(key):
            m = re.search(r'"%s":"((?:\\.|[^"\\])*)"' % key, seg)
            return m.group(1) if m else ''

        movie = {}
        m = re.search(r'"movie":\{"id":"[^"]*","title":"((?:\\.|[^"\\])*)"', seg)
        movie['title'] = m.group(1) if m else ''
        movie['localImg'] = grab('localImg')
        movie['date'] = grab('date')
        movie['plot'] = grab('plot')
        for k in ('director', 'producer', 'publisher', 'series'):
            mm = re.search(r'"%s":\{"id":"([^"]*)","name":"((?:\\.|[^"\\])*)"\}' % k, seg)
            movie[k] = {'id': mm.group(1), 'name': mm.group(2)} if mm else {'id': '', 'name': ''}
        movie['videoSources'] = self._json_array(seg, 'videoSources')
        movie['stars'] = self._json_array(seg, 'stars')
        movie['genres'] = re.findall(
            r'"href":"/%s/genres/([^"]+)"[^{}]*"children":\["[^"]*","([^"]+)"\]' % self.lang,
            flight,
        )
        return movie

    @staticmethod
    def _star_name(star):
        for t in (star or {}).get('translations') or []:
            if t.get('locale') == 'zh-CN' and t.get('name'):
                return t['name']
        return (star or {}).get('name') or ''

    # ---- 接口 ----
    def homeContent(self, filter):
        cats = [
            ('热门影片', '/hot'), ('最近更新', '/latest'), ('新片上市', '/new-releases'),
            ('有码影片', '/censored'), ('无码影片', '/uncensored'),
            ('字幕影片', '/subtitle'), ('4K 视频', '/4k'),
        ]
        classes = [{'type_name': n, 'type_id': f'{self.locale_path}{p}'} for n, p in cats]
        html = self._fetch(f'{self.host}{self.locale_path}')
        return {'class': classes, 'filters': {}, 'list': self._extract_cards(html)}

    def homeVideoContent(self):
        html = self._fetch(f'{self.host}{self.locale_path}')
        return {'list': self._extract_cards(html)}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        u = urlparse(self._unwrap(tid))
        q = parse_qs(u.query)
        q['page'] = [str(pg)]
        real = u._replace(query='&'.join(f'{k}={quote(v[0], safe="")}' for k, v in q.items() if v)).geturl()
        html = self._fetch(real)
        return {'list': self._extract_cards(html), 'page': pg, 'pagecount': 9999, 'limit': 60, 'total': 999999}

    def detailContent(self, ids):
        url = self._unwrap(ids[0] if isinstance(ids, list) else ids)
        html = self._fetch(url)
        movie = self._extract_movie(html)

        def click(name, href):
            name, href = (name or '').strip(), (href or '').strip()
            if not name or not href:
                return ''
            return f'[a=cr:{json.dumps({"id": self._wrap(self._unwrap(href)), "name": name}, ensure_ascii=False)}/]{name}[/a]'

        title = ' '.join((movie.get('title') or '').split()) or url

        director = movie.get('director') or {}

        actors = []
        for st in movie.get('stars') or []:
            x = click(self._star_name(st), f'/{self.lang}/stars/{st.get("id")}')
            if x and x not in actors:
                actors.append(x)

        tags = []
        for gid, name in movie.get('genres') or []:
            x = click(name, f'/{self.lang}/genres/{gid}')
            if x and x not in tags:
                tags.append(x)

        desc = movie.get('plot') or ''
        if not desc:
            m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', html)
            desc = m.group(1) if m else ''
        # 简介顺序：标签 > 片商 > 系列 > 发行商 > 视频简介
        infos = [('标签: ' + ' '.join(tags)) if tags else '']
        for label, k, path in (
            ('片商', 'producer', 'studios'),
            ('系列', 'series', 'series'),
            ('发行商', 'publisher', 'publishers'),
        ):
            o = movie.get(k) or {}
            if o.get('name'):
                infos.append(f'{label}:{click(o["name"], "/" + self.lang + "/" + path + "/" + o["id"])}')
        if desc:
            infos.append(desc)
        content = '\n'.join(filter(None, infos)) or title

        prefer = ['raw_2160p', 'raw_1440p', 'raw_1080p', 'raw_720p', 'raw_480p', 'raw_360p']
        label = {'raw_2160p': '4K', 'raw_1440p': '2K', 'raw_1080p': '1080P', 'raw_720p': '720P', 'raw_480p': '480P', 'raw_360p': '360P'}
        ordered = sorted(
            movie.get('videoSources') or [],
            key=lambda x: prefer.index(x.get('type', '')) if x.get('type', '') in prefer else 999,
        )
        play_lines = []
        for s in ordered:
            u = (s.get('url') or '').strip()
            if not u:
                continue
            t = s.get('type') or ''
            play_lines.append(f'{label.get(t) or t.upper() or "播放"}${u}')
        if not play_lines:
            play_lines.append(f'播放${url}')

        return {'list': [{
            'vod_id': self._wrap(url),
            'vod_name': title,
            'vod_year': (movie.get('date') or '')[:4],
            'vod_director': click(director.get('name'), f'/{self.lang}/directors/{director.get("id")}'),
            'vod_actor': ' '.join(actors),
            'vod_remarks': '',
            'vod_content': content,
            'vod_pic': self._img(movie.get('localImg') or ''),
            'vod_play_from': 'GetAV',
            'vod_play_url': '#'.join(play_lines),
        }]}

    def searchContent(self, key, quick, pg='1'):
        pg = int(pg or 1)
        html = self._fetch(f'{self.host}{self.locale_path}/search?q={quote(key)}&page={pg}')
        return {'list': self._extract_cards(html), 'page': pg, 'pagecount': 9999}

    def playerContent(self, flag, id, vipFlags):
        real_id = (id or '').strip()
        if not real_id:
            return {'parse': 0, 'url': ''}
        headers = dict(self.headers)
        headers['Referer'] = f'{self.host}/'
        headers['Origin'] = self.host
        if real_id.startswith(self.proxy) or self.isVideoFormat(real_id) or '/index.txt' in real_id or '/cdn/assets/deliveries/' in real_id:
            return {'parse': 0, 'url': self._wrap(real_id), 'header': headers}
        return {'parse': 1, 'url': real_id, 'header': headers}
