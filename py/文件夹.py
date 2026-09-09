# -*- coding: utf-8 -*-
import json
import re
import requests
from urllib.parse import quote
from pyquery import PyQuery as pq
import sys
sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    host = 'https://avfolder.com'
    lang = 'zh'
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'referer': 'https://avfolder.com/'
    }

    def init(self, extend=''):
        self.proxies = json.loads(extend).get('proxy', {}) if extend else {}

    def getName(self):
        return "avfolder"

    def fetch(self, url, params=None):
        try:
            return requests.get(url, headers=self.headers, params=params,
                                proxies=self.proxies, timeout=10).text
        except Exception:
            return ''

    def homeContent(self, filter):
        # Correct category endpoints as per site HTML
        classes = [
            {'type_name': '有码', 'type_id': f'{self.lang}/censored/online'},
            {'type_name': '无码', 'type_id': f'{self.lang}/uncensored/online'},
            {'type_name': '欧美', 'type_id': f'{self.lang}/western/online'},
            {'type_name': 'FC2', 'type_id': f'{self.lang}/fc2/online'},
            {'type_name': '成人动画', 'type_id': f'{self.lang}/hanime/online'},
            {'type_name': '国产', 'type_id': f'{self.lang}/chinese/online'},
        ]
        html = self.fetch(f"{self.host}/{self.lang}/censored/online")
        return {
            'class': classes,

            'list': self.parse_videos(pq(html)('.video-list-item'))
        }

    def categoryContent(self, tid, pg, filter, extend):
        params = {}
        if int(pg) > 1:
            params['page'] = pg

        # Expect paths like zh/censored/online, zh/uncensored/online, zh/western/online, etc.
        url = f"{self.host}/{tid}" if not tid.startswith('http') else tid
        html = self.fetch(url, params)
        data = pq(html)
        videos = self.parse_videos(data('.video-list-item'))

        # Estimate pagecount using pagination language links with ?page=
        page_links = data('a[href*="?page="]')
        pagecount = max(len(page_links), 1)

        return {
            'list': videos,
            'page': pg,
            'pagecount': pagecount,
            'limit': 90,
            'total': 999999
        }

    def detailContent(self, ids):
        vid = ids[0]
        # Normalize URL
        if vid.startswith('http'):
            url = vid
        else:
            url = f"{self.host}/{vid.lstrip('/')}"
        html = self.fetch(url)
        data = pq(html)

        # Title and long title from info header
        h2 = data('.view-cam-info-goal__title')
        code_text = h2.find('#view-cam-goal-amount .goal-amount').text().strip()
        long_title = ''
        spans = [s.text().strip() for s in h2.find('span').items() if s.text().strip()]
        if len(spans) >= 2:
            long_title = spans[-1]
        title = long_title or data('meta[property="og:title"]').attr('content') or code_text or ''
        title = re.sub(r'\s*HoHoJ.*$', '', title)
        title = re.sub(r'\s*\|.*$', '', title)
        title = title.strip()

        # Poster image
        poster = data('meta[property="og:image"]').attr('content') or data('img.image-background__image').attr('data-src')

        # Publish date
        pub_date = ''
        for item in data('.video-info .video-info-item-wrapper').items():
            name = item.find('.video-info-name').text().strip()
            if '发佈于' in name or '发布于' in name:
                pub_date = item.find('.video-info-text').text().strip()
                break
        year = ''
        m = re.search(r'(20\d{2})', pub_date)
        if m:
            year = m.group(1)

        # Actors
        actors = []
        for a in data('.video-info-actor').items():
            name = a.text().strip()
            href = a.attr('href')
            if name:
                if href:
                    actors.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')
                else:
                    actors.append(name)
        # Categories
        tags = []
        for a in data('.video-info-category').items():
            name = a.text().strip()
            href = a.attr('href')
            if name:
                if href:
                    tags.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')
                else:
                    tags.append(name)
        # Synopsis: use long title line if available
        synopsis = long_title or ''

        code = code_text or vid.split('/')[-1]

        vod = {
            'vod_name': title,
            'vod_play_from': '撸出血',
            'vod_play_url': f"{title}${code}",
            'vod_pic': poster,
            'vod_year': year,
        }
        if actors:
            vod['vod_actor'] = ' '.join(actors)
        if tags or synopsis:
            # Put categories + synopsis as content
            vod['vod_content'] = ' '.join(tags + ([synopsis] if synopsis else []))

        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        params = {'wd': key}
        if int(pg) > 1:
            params['page'] = pg
        html = self.fetch(f"{self.host}/{self.lang}/search", params)
        return {'list': self.parse_videos(pq(html)('.video-list-item')), 'page': pg}

    def playerContent(self, flag, id, vipFlags):
        # Extract playable URLs from play page m3u8 array scripts
        # id here should be the code like MIMK-198; construct page URL then parse m3u8
        page_url = f"{self.host}/{self.lang}/{id}" if not id.startswith('http') else id
        html = self.fetch(page_url)

        # Capture m3u8.push("...") entries
        m3u8_urls = re.findall(r'm3u8\.push\("([^"]+)"\)', html)
        video_url = m3u8_urls[0] if m3u8_urls else ''

        # Fallback: try <source src> inside preview video
        if not video_url:
            match = re.search(r'<source[^>]+src="([^"]+)"', html)
            if match:
                video_url = match.group(1)

        return {
            'parse': 0,
            'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{video_url}',
            'header': {
                'user-agent': self.headers['user-agent'],
                'referer': page_url,
                'origin': self.host,
            }
        } if video_url else {'parse': 0, 'url': ''}

    def parse_videos(self, items):
        videos = []
        for i in items.items():
            link = i('a.video-list-item-link').attr('href')
            # Title text
            title = i('.video-list-item-username span.fw-bold').text() or i('.video-list-item-username').text()
            if not link or not title:
                # Some list blocks use plain span without fw-bold
                title = i('.video-list-item-username span').text() or title
            if not link or not title:
                continue

            title = re.sub(r'\s*HoHoJ.*$', '', title)
            title = re.sub(r'\s*\|.*$', '', title).strip()

            # Lazyload image
            img = i('img.image-background__image').attr('data-src') or i('img').attr('src')

            badge_new = i('.video-list-item-bagde-new').text().strip() if i('.video-list-item-bagde-new') else ''
            badge_tag = i('.video-list-item-bagde-tag').text().strip() if i('.video-list-item-bagde-tag') else ''
            remarks = ' '.join([t for t in [badge_new, badge_tag] if t])

            videos.append({
                'vod_id': link,
                'vod_name': title,
                'vod_pic': img,
                'vod_remarks': remarks,
                'vod_tag': badge_tag or '',
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
