# -*- coding: utf-8 -*-
# 影视交流群

import base64
import json
import re
import time
import urllib.parse

import requests
from pyquery import PyQuery as pq

import sys
sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    host = 'https://memojav.com'
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'referer': 'https://memojav.com/',
    }

    def init(self, extend=''):
        self.plp = json.loads(extend).get('plp', '')
        self.proxy = json.loads(extend).get('proxy', {}) if extend else {}

    def getName(self):
        return "memo"

    def fetch(self, url, params=None):
        try:
            r = requests.get(
                url,
                headers=self.headers,
                params=params,
                proxies=self.proxy,
                timeout=15,
            )
            return r.text
        except Exception:
            return ''

    # ---------- helpers ----------
    def _norm_path(self, tid: str) -> str:
        tid = (tid or '').strip()
        if not tid:
            return '/'
        if tid.startswith('http://') or tid.startswith('https://'):
            tid = re.sub(r'^https?://[^/]+', '', tid)
        if not tid.startswith('/'):
            tid = '/' + tid
        return tid

    def _build_list_url(self, tid: str, pg: str):
        pg = int(pg or 1)
        path = self._norm_path(tid)

        # 一级：/video/ /best/
        if path in ['/video', '/video/']:
            return f"{self.host}/video/" if pg == 1 else f"{self.host}/video/page-{pg}"
        if path in ['/best', '/best/']:
            return f"{self.host}/best/" if pg == 1 else f"{self.host}/best/page-{pg}"

        # 其它列表页：站点使用 /xxx/page-N 形式（page-1 通常不存在）
        path = path.rstrip('/')
        if pg == 1:
            return f"{self.host}{path}"
        return f"{self.host}{path}/page-{pg}"

    def _get_pagecount(self, doc: pq):
        # 优先取页面跳转输入框 max
        mx = doc('input.inputNumber_nav').attr('max')
        if mx and str(mx).isdigit():
            return int(mx)

        # 兜底：取分页最后一个数字
        nums = []
        for a in doc('ul.pageNav-main a').items():
            t = a.text().strip()
            if t.isdigit():
                nums.append(int(t))
        return max(nums) if nums else 1

    # ---------- core ----------
    def homeContent(self, filter):
        html = self.fetch(self.host)
        return {
            'class': [
                {'type_name': '新视频', 'type_id': 'video'},
                {'type_name': '最佳视频', 'type_id': 'best'},
                {'type_name': '女演员', 'type_id': 'actress'},
                {'type_name': '工作室', 'type_id': 'studio'},
            ],
            'list': self.parse_videos(pq(html)('.video-item')),
        }

    def categoryContent(self, tid, pg, filter, extend):
        url = self._build_list_url(tid, pg)
        html = self.fetch(url)
        doc = pq(html)

        # 1) 视频列表页：.video-item
        if doc('.video-item').length:
            videos = self.parse_videos(doc('.video-item'))
        # 2) 女演员/工作室 一级列表：.description-block
        else:
            videos = self.parse_folders(doc('a:has(.description-block)'))

        return {
            'list': videos,
            'page': pg,
            'pagecount': self._get_pagecount(doc),
            'limit': 90,
            'total': 999999,
        }

    def detailContent(self, ids):
        vid = (ids[0] or '').strip()
        if not vid:
            return {'list': []}

        # vid 可能是 /video/XXX 或 XXX
        if vid.startswith('http://') or vid.startswith('https://'):
            url = vid
        elif vid.startswith('/'):
            url = f"{self.host}{vid}"
        else:
            url = f"{self.host}/video/{vid}" if not vid.startswith('video/') else f"{self.host}/{vid}"

        html = self.fetch(url)
        doc = pq(html)

        # video id
        video_id = ''
        m = re.search(r'/video/([^/?#]+)', url)
        if m:
            video_id = m.group(1)
        else:
            video_id = url.rstrip('/').split('/')[-1].split('?')[0]

        title = doc('#title').text() or doc('h1').text() or doc('title').text() or ''
        title = re.sub(r'\s*\|\s*page\s*\d+.*$', '', title, flags=re.I).strip()
        title = re.sub(r'\s*\|.*$', '', title).strip()

        vod = {
            'vod_name': title,
            'vod_play_from': 'MemoJav',
            'vod_play_url': f"{title}${video_id}",
            'vod_pic': doc('meta[property="og:image"]').attr('content')
            or doc('#poster').attr('src')
            or doc('img#poster').attr('src'),
            'vod_year': doc('table.details tr:contains("Release Date") td').text().strip(),
        }

        def _row_by_th(th_name: str):
            """精确定位 table.details 的行：th 文本必须等于 th_name（忽略两端空白）。"""
            th_name = (th_name or '').strip().rstrip(':')
            for tr in doc('table.details tr').items():
                th_text = tr('th').text().strip().rstrip(':')
                if th_text == th_name:
                    return tr
            return pq('')

        def _collect_row_links_exact(th_name: str):
            """从精确 th 行中提取 a 标签（用于 Series/Studio 等）。"""
            out = []
            tr = _row_by_th(th_name)
            for a in tr('a').items():
                href = (a.attr('href') or '').strip()
                if not href:
                    continue
                name = a.find('span').eq(-1).text().strip() or a.text().strip()
                if name:
                    out.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')
            return out

        # 演员（严格只取 /actress/ 链接，避免误抓简介标签）
        actresses = []
        tr_act = _row_by_th('Actress')
        for a in tr_act('a').items():
            href = (a.attr('href') or '').strip()
            if not href or '/actress/' not in href:
                continue
            name = a.find('span').eq(-1).text().strip() or a.text().strip()
            if name:
                actresses.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')
        if actresses:
            vod['vod_actor'] = ' '.join(actresses)

        # 系列（精确行提取）
        series = _collect_row_links_exact('Series')

        # 简介标签（Categories，可点击）
        categories = []
        tr_cat = _row_by_th('Categories')
        for a in tr_cat('a.box-tag').items():
            href = (a.attr('href') or '').strip()
            name = a.text().strip()
            if name and href:
                categories.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')

        # vod_content：系列在前，"标签:" 在后，换行显示
        content_lines = []
        if series:
            content_lines.append('系列：' + ' '.join(series))
        if categories:
            content_lines.append('标签: ' + ' '.join(categories))
        if content_lines:
            vod['vod_content'] = '\n'.join(content_lines)

        # 发行商：按你给的片段，其实在 Studio 行（精确行提取）
        pub = _collect_row_links_exact('Studio')
        if pub:
            # vod_remarks 只显示发行商
            vod['vod_remarks'] = '发行商：' + ' '.join(pub)

        # 导演（可点击）
        director = _collect_row_links_exact('Director')
        if director:
            vod['vod_director'] = ' '.join(director)

        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        # 站点本身没有开放 JSON 搜索，这里尽量兼容旧逻辑
        params = {'text': key}
        if int(pg) > 1:
            params['p'] = pg
        html = self.fetch(f"{self.host}/search", params)
        doc = pq(html)
        return {'list': self.parse_videos(doc('.video-item')), 'page': pg}

    def _video_sig(self):
        # JS 逻辑来自 /static/main.js：video_sig()
        t = int(time.time() * 1000)
        sig = base64.b64encode(str(t).encode('utf-8')).decode('utf-8')
        # JS: s=sig.length-12; sig=sig.substr(s,10)  => sig[-12:-2]
        sig = sig[-12:-2]
        sts = 1
        for i, ch in enumerate(sig[:10]):
            sts += ord(ch) * i * 1743
        return sig, sts

    def playerContent(self, flag, id, vipFlags):
        vid = (id or '').strip()
        if not vid:
            return {'parse': 0, 'url': ''}

        sig, sts = self._video_sig()
        api = f"{self.host}/hls/get_video_info.php?id={urllib.parse.quote(vid)}&sig={sig}&sts={sts}"
        raw = self.fetch(api)

        # 返回格式：for (;;);{json}
        if 'for (;;);' in raw:
            raw = raw.split('for (;;);', 1)[1]

        video_url = ''
        try:
            data = json.loads(raw)
            if data.get('success') and data.get('url'):
                video_url = urllib.parse.unquote(str(data.get('url')))
        except Exception:
            video_url = ''

        # 代理前缀（用户指定）
        proxy_prefix = self.plp
        proxied_url = proxy_prefix + video_url if video_url else ''

        return {
            'parse': 0,
            'url': proxied_url,
            'header': {
                'user-agent': self.headers['user-agent'],
                'referer': f"{self.host}/embed/{vid}",
                'origin': self.host,
            },
        } if proxied_url else {'parse': 0, 'url': ''}

    # ---------- parsers ----------
    def parse_videos(self, items):
        videos = []
        for it in items.items():
            # memojav: <a class="video-item" href="/video/XXX"> ... </a>
            link = it.attr('href') or it('a').attr('href')
            title = it('.video-title').text() or it('.video-item-title').text() or it('img').attr('alt')
            if not link or not title:
                continue

            title = re.sub(r'\s*HoHoJ.*$', '', title)
            title = re.sub(r'\s*\|.*$', '', title).strip()

            pic = it('img').attr('src')

            videos.append({
                'vod_id': link,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': '',
                'style': {"type": "rect", "ratio": 1.5},
            })
        return videos

    def parse_folders(self, a_items):
        """解析女演员/工作室等一级列表。"""
        out = []
        for a in a_items.items():
            href = a.attr('href')
            if not href:
                continue

            # 头像
            pic = a('img.actress-icon').attr('src') or a('img').attr('src')

            spans = [s.text().strip() for s in a.find('span').items() if s.text().strip()]
            # 女演员列表：优先用第一个 span（日文名），如：瀬戸環奈
            if href.startswith('/actress') and spans:
                name = spans[0]
            else:
                name = spans[-1] if spans else (a.text().strip().split('\n')[-1] if a.text().strip() else href.split('/')[-1])

            out.append({
                'vod_id': href,
                'vod_name': name,
                'vod_pic': f'{self.plp}{pic}',
                'vod_tag': 'folder',
                'style': {"type": "rect", "ratio": 0.75},
            })
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
