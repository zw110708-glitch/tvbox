# -*- coding: utf-8 -*-
# 影视交流群（修复版，适配 AV6K）
import json
import re
import requests
import urllib.parse
from pyquery import PyQuery as pq
import sys
sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    host = 'https://av6k.com'
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'referer': 'https://av6k.com/'
    }

    def init(self, extend=''):
        self.proxies = json.loads(extend).get('proxy', {}) if extend else {}

    def getName(self):
        return "av6k"

    def fetch(self, url, params=None):
        try:
            resp = requests.get(url, headers=self.headers, params=params or None,
                                proxies=self.proxies, timeout=10)
            resp.encoding = resp.apparent_encoding or 'utf-8'
            return resp.text
        except Exception:
            return ''

    def _abs_url(self, url):
        if not url:
            return ''
        if url.startswith('http://') or url.startswith('https://'):
            return url
        if url.startswith('/'):
            return f"{self.host}{url}"
        return f"{self.host}/{url}"

    def homeContent(self, filter):
        html = self.fetch(self.host + '/')
        doc = pq(html)
        return {
            'class': [
                {'type_name': '最新影片', 'type_id': ''},
                {'type_name': '日韓無碼', 'type_id': 'rihanwuma'},
                {'type_name': '日韓有碼', 'type_id': 'rihanyouma'},
                {'type_name': '中文字幕', 'type_id': 'jxny'},
                {'type_name': '國產AV', 'type_id': 'chinese-av-porn'},
                {'type_name': 'FC2無碼', 'type_id': 'fc2'},
                {'type_name': '自拍偷拍', 'type_id': 'surenzipai'},
                {'type_name': '歐美無碼', 'type_id': 'oumeiwuma'},
                {'type_name': '成人動漫', 'type_id': 'chengrendongman'},
            ],
            'filters': self.get_filters(),
            'list': self.parse_videos(doc('.listA'))
        }

    def get_filters(self):
        base = [{'key': 'order', 'name': '排序', 'value': [
            {'n': '隨機', 'v': 'random'},
            {'n': '最新', 'v': 'latest'},
            {'n': '人氣', 'v': 'views'},
        ]}]
        return {
            'rihanwuma': base,
            'rihanyouma': base,
            'jxny': base,
            'chinese-av-porn': base,
            'fc2': base,
            'surenzipai': base,
            'oumeiwuma': base,
            'chengrendongman': base,
            '': base,
        }

    def _category_root(self, tid, extend):
        # tid 为 '' 表示首页；支持传入完整路径（如 actresses/.../）
        tid_clean = (tid or '').strip('/')
        root = self.host + '/' + (tid_clean + '/' if tid_clean else '')
        order = (extend or {}).get('order') if extend else None
        # 标签页（actresses）不支持排序；其他分区支持
        if tid_clean and not tid_clean.startswith('actresses'):
            if order == 'latest':
                root += 'news/'
            elif order == 'views':
                root += 'views/'
        return root

    def _resolve_category_page_url(self, tid, pg, extend):
        # 解析真实分页链接模式（兼容 2.html / 2_2.html / search/关键词-2.html 等）
        root = self._category_root(tid, extend)
        if int(pg) <= 1:
            return root
        # 读取根页，找到与 pg 文本匹配的分页锚点链接
        html0 = self.fetch(root)
        doc0 = pq(html0)
        for a in doc0('.pages_c a').items():
            txt = (a.text() or '').strip()
            if txt == str(pg):
                href = a.attr('href')
                if href:
                    return urllib.parse.urljoin(root, href)
        # 回退常见模式
        return root + f"{pg}.html"

    def categoryContent(self, tid, pg, filter, extend):
        url = self._resolve_category_page_url(tid, pg, extend)
        html = self.fetch(url)
        doc = pq(html)
        videos = self.parse_videos(doc('.listA'))
        # 尝试解析总页数
        pagecount = 1
        try:
            pages = []
            for a in doc('.pages_c a').items():
                t = (a.text() or '').strip()
                if t.isdigit():
                    pages.append(int(t))
            if pages:
                pagecount = max(pages)
        except Exception:
            pagecount = 1
        return {
            'list': videos,
            'page': pg,
            'pagecount': pagecount or 1,
            'limit': 90,
            'total': 999999
        }

    def detailContent(self, ids):
        vid = ids[0]
        url = self._abs_url(vid)
        html = self.fetch(url)
        doc = pq(html)

        title = (doc('h2').text() or doc('title').text() or '').strip()
        # 封面图（绝对化）
        pic = self._abs_url(doc('.video-img img').attr('src') or doc('meta[property="og:image"]').attr('content'))

        # 播放地址（m3u8）
        m3u8 = ''
        m = re.search(r'var\s+sp_m3u8\s*=\s*"([^"]+)"', html)
        if m:
            m3u8 = m.group(1)
        else:
            m = re.search(r"initVideo\(\{[^}]*url:\s*'([^']+)'", html)
            if m:
                m3u8 = m.group(1)
        # 绝对化播放地址
        m3u8 = self._abs_url(m3u8) if m3u8 else ''

        # 演员/标签（.ctag a）生成可点击富文本
        tags = []
        for a in doc('.ctag a').items():
            name = a.text().strip()
            href = a.attr('href')
            if name and href:
                tags.append(f"[a=cr:{json.dumps({'id': href, 'name': name}, ensure_ascii=False)}/]{name}[/a]")

        # 简介：取页面正文段落（优先 .newVideoC 下的第一个 p），回退到 meta description
        desc = ''
        p_texts = []
        for p in doc('.newVideoC p').items():
            t = p.text().strip()
            if t:
                p_texts.append(t)
        if p_texts:
            desc = '\n'.join(p_texts)
        else:
            desc = (doc('meta[name="description"]').attr('content') or '').strip()

        # 将简介放到标签后面
        content_parts = []
        if tags:
            content_parts.append(' '.join(tags))
        if desc:
            content_parts.append(desc)

        vod = {
            'vod_name': title,
            'vod_play_from': 'AV6K',
            'vod_play_url': f"{title}${m3u8}" if m3u8 else f"{title}$",
            'vod_pic': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pic}',
            'vod_year': '',
        }
        if content_parts:
            vod['vod_content'] = '\n'.join(content_parts)

        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        # 搜索路径：/search/<keyword>-<pg>.html
        keyword = urllib.parse.quote(key, safe='')
        url = f"{self.host}/search/{keyword}-{pg}.html"
        html = self.fetch(url)
        doc = pq(html)
        return {
            'list': self.parse_videos(doc('.listA')),
            'page': pg
        }

    def playerContent(self, flag, id, vipFlags):
        # 直接播放 m3u8 或视频直链（id 即为播放地址）
        video_url = id
        return {
            'parse': 0,
            'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{video_url}',
            'header': {
                'user-agent': self.headers['user-agent'],
                'referer': self.host,
                'origin': self.host,
            }
        } if video_url else {'parse': 0, 'url': ''}

    def parse_videos(self, items):
        # 适配 AV6K 列表结构：listA > listAC
        videos = []
        for box in items.items():
            ac = box.find('.listAC')
            a = ac.find('a')
            href = a.attr('href')
            if not href:
                continue
            title = (ac.find('.listACT').text() or a.attr('title') or ac.find('.listACP img').attr('alt') or '').strip()
            pic = self._abs_url(ac.find('.listACP img').attr('src'))
            if not title:
                title = href.split('/')[-1].replace('.html', '')
            videos.append({
                'vod_id': href,
                'vod_name': re.sub(r'\s*\|.*$', '', title).strip(),
                'vod_pic': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pic}',
                'vod_remarks': '',
                'vod_tag': '',
                'style': {"type": "rect", "ratio": 1.33}
            })
        return videos

    # 以下保留空实现以兼容框架
    def parse_models(self, items):
        return []
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
