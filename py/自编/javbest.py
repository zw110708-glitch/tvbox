# -*- coding: utf-8 -*-
# 影视交流群
import json
import re
import requests
from pyquery import PyQuery as pq
import sys
import urllib.parse

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    host = 'https://javbest.live'
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'referer': 'https://javbest.live/'
    }

    def init(self, extend=''):
        self.proxies = json.loads(extend).get('proxy', {}) if extend else {}

    def getName(self):
        return "javbest"

    def fetch(self, url, params=None):
        try:
            return requests.get(
                url,
                headers=self.headers,
                params=params,
                proxies=self.proxies,
                timeout=10
            ).text
        except:
            return ''

    def _abs_url(self, tid_or_url: str) -> str:
        """把 tid / path 统一成绝对 URL"""
        if not tid_or_url:
            return self.host
        if tid_or_url.startswith('http://') or tid_or_url.startswith('https://'):
            return tid_or_url
        if tid_or_url.startswith('/'):
            return f"{self.host}{tid_or_url}"
        return f"{self.host}/{tid_or_url}"

    def _page_url(self, url: str, pg: str) -> str:
        """将分页统一修正为 /page/{pg}/ 形式（站点不识别 ?p=2）"""
        try:
            pg_i = int(pg)
        except:
            pg_i = 1
        if pg_i <= 1:
            return url

        if '?' in url:
            path, qs = url.split('?', 1)
            if not path.endswith('/'):
                path += '/'
            return f"{path}page/{pg_i}/?{qs}"

        if not url.endswith('/'):
            url += '/'
        return f"{url}page/{pg_i}/"

    def homeContent(self, filter):
        html = self.fetch(f"{self.host}/zh-CN/")
        doc = pq(html)

        # 首页两套结构兼容：.video-item（旧）与 .thumb-block（新）
        items = doc('.video-item')
        if items.length == 0:
            items = doc('.thumb-block')

        return {
            'class': [
                # 首页三大排序
                {'type_name': '最新上传', 'type_id': '/zh-CN/?filter=random'},
                {'type_name': '观看次数最多', 'type_id': '/zh-CN/?filter=most-viewed'},
                {'type_name': '最热门', 'type_id': '/zh-CN/?filter=popular'},

                # 二级入口
                {'type_name': '分类', 'type_id': '/zh-CN/categories/'},
                {'type_name': '演员', 'type_id': '/zh-CN/actors/'},
                {'type_name': '中国色情', 'type_id': '/zh-CN/chinese/'},
                {'type_name': '未审查', 'type_id': '/zh-CN/uncensored/'},
            ],
            'filters': self.get_filters(),
            'list': self.parse_videos(items)
        }

    def get_filters(self):
        return {}

    def _is_root_folder(self, tid_or_url: str) -> str:
        """判断是否为一级入口页：categories / actors"""
        if not tid_or_url:
            return ''
        t = str(tid_or_url)
        # 允许传入 path 或完整 url
        if '/zh-CN/categories' in t and t.rstrip('/').endswith('/zh-CN/categories'):
            return 'categories'
        if '/zh-CN/actors' in t and t.rstrip('/').endswith('/zh-CN/actors'):
            return 'actors'
        return ''

    def categoryContent(self, tid, pg, filter, extend):
        root_type = self._is_root_folder(tid)
        url = self._abs_url(tid)
        url = self._page_url(url, pg)

        html = self.fetch(url)
        data = pq(html)

        # 一级：返回卡片(folder)
        if root_type in ('categories', 'actors'):
            cards = self.parse_folders(data('article.thumb-block'))
            pagecount = data('.pagination a').length or 1
            return {
                'list': cards,
                'page': pg,
                'pagecount': pagecount,
                'limit': 90,
                'total': 999999
            }

        # 二级：返回视频列表
        items = data('.video-item')
        if items.length == 0:
            items = data('.thumb-block')

        videos = self.parse_videos(items)
        pagecount = data('.pagination a').length or 1
        return {
            'list': videos,
            'page': pg,
            'pagecount': pagecount,
            'limit': 90,
            'total': 999999
        }

    def detailContent(self, ids):
        vid = ids[0]
        url = self._abs_url(vid)
        html = self.fetch(url)
        data = pq(html)

        # 播放ID：新站点在详情页 iframe 的 data-src / src 中（32位hash）
        video_id = ''
        iframe_src = data('iframe').attr('data-src') or data('iframe').attr('src') or ''
        m = re.search(r'/video/([0-9a-f]{32})', iframe_src)
        if m:
            video_id = m.group(1)
        elif 'id=' in vid:
            video_id = vid.split('id=')[-1].split('&')[0].split('&')[0]

        title = data('h1').text() or data('title').text() or ''
        title = re.sub(r'\s*HoHoJ.*$', '', title)
        title = re.sub(r'\s*\|.*$', '', title)
        title = title.strip()

        vod = {
            'vod_name': title,
            'vod_play_from': '撸出血',
            'vod_play_url': f"{title}${video_id}",
            'vod_pic': data('.video-player img').attr('src') or data('meta[property="og:image"]').attr('content'),
            'vod_year': data('.info span').eq(-1).text(),
        }

        # 精准抓取：演员（#video-actors 区域）
        actors = []
        for a in data('#video-actors a').items():
            name = a.text().strip()
            href = a.attr('href')
            if name and href:
                actors.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')
        if actors:
            vod['vod_actor'] = ' '.join(dict.fromkeys(actors))

        # 精准抓取：标签（.tags-list 区域）
        tags = []
        for a in data('.tags-list a').items():
            name = a.text().strip()
            href = a.attr('href')
            if name and href:
                tags.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')

        # 影片介绍：标签后追加正文首段
        intro = (
            data('.entry-content p').eq(0).text().strip()
            or data('.entry-content').text().strip()
        )
        intro = re.sub(r'\s+', ' ', intro).strip()

        if tags or intro:
            vod_content = ''
            if tags:
                vod_content += ' '.join(dict.fromkeys(tags))
            if intro:
                vod_content += ('\n' if vod_content else '') + intro
            vod['vod_content'] = vod_content

        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        # WordPress 搜索：/?s=xxx ，分页可用 /page/{pg}/?s=xxx
        q = urllib.parse.quote(key)
        url = f"{self.host}/?s={q}"
        url = self._page_url(url, pg)

        html = self.fetch(url)
        doc = pq(html)
        items = doc('.video-item')
        if items.length == 0:
            items = doc('.thumb-block')
        return {'list': self.parse_videos(items), 'page': pg}

    def playerContent(self, flag, id, vipFlags):
        """解析真实播放地址

        2026年前后站点播放页改为第三方域 javbest.cc，需通过接口拿到 m3u8。
        """
        # 新版：id 为 32位 hash（来自详情页 iframe /video/{hash}）
        if re.fullmatch(r'[0-9a-f]{32}', str(id or '')):
            base = 'https://javbest.cc'
            api = f"{base}/player/index.php?data={id}&do=getVideo"
            try:
                r = requests.post(
                    api,
                    headers={
                        'user-agent': self.headers['user-agent'],
                        'referer': f"{base}/video/{id}",
                        'x-requested-with': 'XMLHttpRequest',
                    },
                    proxies=self.proxies,
                    timeout=15
                )
                # 返回是 JSON 字符串（content-type 可能还是 text/html）
                js = r.json() if hasattr(r, 'json') else json.loads(r.text)
            except:
                js = {}

            video_url = js.get('securedLink') or js.get('videoSource') or ''
            return {
                'parse': 0,
                'url': video_url,
                'header': {
                    'user-agent': self.headers['user-agent'],
                    'referer': f"{base}/video/{id}",
                    'origin': base,
                }
            } if video_url else {'parse': 0, 'url': ''}

        # 旧版兜底：/embed?id=xxx
        html = self.fetch(f"{self.host}/embed?id={id}")

        video_url = ''
        match = re.search(r'<video[^>]+src="([^"]+)"', html)
        if match:
            video_url = match.group(1)
        else:
            match = re.search(r'var\s+videoSrc\s*=\s*["\']([^"\']+)["\']', html)
            video_url = match.group(1) if match else pq(html)('video').attr('src') or ''

        return {
            'parse': 0,
            'url': video_url,
            'header': {
                'user-agent': self.headers['user-agent'],
                'referer': f"{self.host}/embed?id={id}",
                'origin': self.host,
            }
        } if video_url else {'parse': 0, 'url': ''}

    def parse_folders(self, items):
        """解析一级入口页的卡片（分类/演员），点击进入二级视频列表"""
        folders = []
        for i in items.items():
            a = i('a')
            link = a.attr('href')
            if not link:
                continue
            img = i('img')
            name = (a.attr('title') or img.attr('alt') or a.text() or '').strip()
            if not name:
                continue
            pic = (
                img.attr('data-src-webp')
                or img.attr('data-src-img')
                or img.attr('data-src')
                or img.attr('src')
                or ''
            )
            folders.append({
                'vod_id': link,
                'vod_name': name,
                'vod_pic': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pic}',
                'vod_tag': 'folder',
                'vod_remarks': '',
                'style': {"type": "rect", "ratio": 1.5}
            })
        return folders

    def parse_videos(self, items):
        videos = []
        for i in items.items():
            cls = i.attr('class') or ''

            # 结构1：.video-item（首页常见）
            if 'video-item' in cls:
                link = i('a').attr('href')
                title = i('.video-item-title').text() or i('img').attr('alt')
                if not link or not title:
                    continue

                title = re.sub(r'\s*HoHoJ.*$', '', title)
                title = re.sub(r'\s*\|.*$', '', title).strip()

                rating = i('.video-item-rating')
                views = rating.find('.fa-eye').parent().text().strip()
                likes = rating.find('.fa-heart').parent().text().strip()

                videos.append({
                    'vod_id': link,
                    'vod_name': title,
                    'vod_pic': i('img').attr('src'),
                    'vod_remarks': f"👁 {views} ❤ {likes}",
                    'vod_tag': '无码' if i('.video-item-badge').length else '',
                    'style': {"type": "rect", "ratio": 1.5}
                })
                continue

            # 结构2：.thumb-block（分类页/演员页常见）
            link = i('a').attr('href')
            img = i('img')
            title = (img.attr('alt') or i('a').attr('title') or '').strip()
            if not link or not title:
                continue

            title = re.sub(r'\s*HoHoJ.*$', '', title)
            title = re.sub(r'\s*\|.*$', '', title).strip()

            pic = (
                img.attr('data-src-webp')
                or img.attr('data-src-img')
                or img.attr('data-src')
                or img.attr('src')
                or ''
            )

            videos.append({
                'vod_id': link,
                'vod_name': title,
                'vod_pic': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pic}',
                'vod_remarks': '',
                'vod_tag': '',
                'style': {"type": "rect", "ratio": 1.5}
            })

        return videos

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
