# -*- coding: utf-8 -*-
import json, re, requests, sys, base64
sys.path.append('..')
from base.spider import Spider
from pyquery import PyQuery as pq


class Spider(Spider):
    host = 'https://javmove.com'
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'referer': 'https://javmove.com/'
    }
    VIDEO_FMTS = ('.mp4', '.m3u8', '.flv', '.avi', '.mkv', '.mov', '.wmv')

    def init(self, extend=''):
        self.plp = json.loads(extend).get('plp', '')
        self.proxy = json.loads(extend).get('proxy', {}) if extend else {}

    def getName(self):
        return "JavMove"

    def fetch(self, url, params=None):
        try:
            r = requests.get(url, headers=self.headers, proxies=self.proxy, params=params, timeout=15)
            r.encoding = 'utf-8'
            return r.text
        except:
            return ''

    def homeContent(self, filter):
        data = pq(self.fetch(self.host))
        classes = [
            {'type_name': '最新AV', 'type_id': 'release'},
            {'type_name': '即将上映', 'type_id': 'upcoming'}
        ]
        filters = {c['type_id']: [{'key': 'order', 'name': '排序',
                    'value': [{'n': '最新', 'v': 'latest'}, {'n': '最热', 'v': 'hot'}]}] for c in classes}
        return {'class': classes, 'filters': filters, 'list': self.parse_videos(data('#movie-list article'))}

    def categoryContent(self, tid, pg, filter, extend):
        params = dict(extend) if extend else {}
        if int(pg) > 1:
            params['page'] = pg
        if filter and isinstance(filter, dict):
            params.update(filter)
        data = pq(self.fetch(f'{self.host}/{tid}', params))
        articles = data('#movie-list article')
        has_next = (
            data('.pagination .next').length > 0 or
            data('.pagination a.next').length > 0 or
            data('.pagination li.next a').length > 0 or
            data('a.next-page, a[rel="next"]').length > 0
        )
        return {'list': self.parse_videos(articles), 'page': int(pg),
                'pagecount': 9999 if has_next else int(pg), 'limit': 20, 'total': 999999}

    # ========== 唯一改动：detailContent 增加 vod_year / vod_actor / vod_content 可点击标签 ==========
    def detailContent(self, ids):
        vid = ids[0]
        url = f'{self.host}{vid}' if vid.startswith('/') else f'{self.host}/{vid}'
        d = pq(self.fetch(url))

        title = (d('h2').attr('title') or d('h2').text() or '').strip()
        img = d('.movie-image')
        cover = (img.attr('data-srcset') or img.attr('src') or '') if img else ''

        # ---- 1. 提取日期 → vod_year ----
        # 结构: <li><div class="flex items-center"><i ... title="Release Date"></i>
        #         <span class="bg-gray-700 ..."> 15/08/2026 </span></div></li>
        vod_year = ''
        for li in d('li').items():
            if li.find('i[title="Release Date"]'):
                span = li.find('span.bg-gray-700')
                if span:
                    date_raw = span.text().strip()          # "15/08/2026"
                    parts = date_raw.split('/')
                    if len(parts) == 3:
                        # DD/MM/YYYY → YYYY-MM-DD
                        vod_year = f'{parts[2]}-{parts[1]}-{parts[0]}'
                break

        data_id = d('#video-player').attr('data-id') or ''
        desc = d('.movie-description, .description, .summary')
        content = desc.text().strip() if desc else ''

        # ---- 2. 提取演员 → vod_actor（可点击） ----
        # 结构: <a href="/stars/xxx/name" ...>Name</a>
        actors = []
        for a in d('a[href^="/stars/"]').items():   # 只匹配演员链接
            name = a.text().strip()
            href = a.attr('href')
            if name and href:
                actors.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')

        # ---- 3. 提取标签 → vod_content（可点击，追加在简介后） ----
        # 结构: <a class="hover:text-primary-500" href="/genres/xxx/tag" rel="tag">Tag</a>
        tags = []
        for a in d('a[href^="/genres/"]').items():   # 只匹配类型标签链接
            name = a.text().strip()
            href = a.attr('href')
            if name and href:
                tags.append(f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]')

        # 拼接 vod_content：原有简介 + 换行 + "标签:" + 可点击标签
        if tags:
            tag_line = '\n标签: ' + ' '.join(tags)
            content = (content + tag_line).strip() if content else tag_line.strip()

        # ---- 播放源解析（保持不变） ----
        play_from, play_url = [], []
        fmt_groups = d('.video-format')

        if not fmt_groups and data_id:
            play_from = ['默认']
            play_url = [f'part1${data_id}']
        else:
            groups = []
            for div in fmt_groups.items():
                hdr = div.find('.video-format-header')
                name = hdr.text().strip() if hdr else '默认'
                tracks = []
                for btn in div.find('.video-source-btn').items():
                    t = btn.attr('title') or ''
                    m = re.search(r'part\s*(\d+)', t, re.I)
                    p = int(m.group(1)) if m else len(tracks) + 1
                    pid = data_id
                    h = btn.attr('href') or ''
                    if h and not h.startswith('#'):
                        vp = pq(self.fetch(f'{self.host}{h}'))('#video-player')
                        pid = vp.attr('data-id') or data_id
                    tracks.append((p, f'part {p}', pid))
                tracks.sort()
                groups.append((name, tracks))

            prio = {'fullhd': 1, 'hd': 2, 'sd': 3}
            groups.sort(key=lambda g: prio.get(next((k for k in prio if g[0].lower().startswith(k)), ''), 999))
            for name, tracks in groups:
                play_from.append(name)
                play_url.append('#'.join(f"{n}${i}" for _, n, i in tracks))

        vod = {
            'vod_id': vid,
            'vod_name': title,
            'vod_pic': cover,
            'vod_year': vod_year,          # ← 新增：发行年份
            'vod_actor': ' '.join(actors),  # ← 新增：可点击演员
            'vod_remarks': vod_year,
            'vod_pubdate': vod_year,
            'vod_content': content,         # ← 修改：追加可点击标签
            'vod_play_from': '$$$'.join(play_from),
            'vod_play_url': '$$$'.join(play_url),
        }

        return {'list': [vod]}
    # =====================================================================================

    def searchContent(self, key, quick, pg="1"):
        params = {'q': key, **({'page': pg} if int(pg) > 1 else {})}
        return {'list': self.parse_videos(pq(self.fetch(f'{self.host}/search', params))('#movie-list article')), 'page': int(pg)}

    def playerContent(self, flag, id, vipFlags):
        h = {**self.headers, 'referer': 'https://javquick.com/', 'origin': 'https://javquick.com'}

        if self._is_video(id):
            raw_url = id
        else:
            token = id.split('$')[-1] if '$' in id else id
            try:
                r = requests.get(f'{self.host}/watch?token={token}', headers=h, timeout=15)
                r.encoding = 'utf-8'
                raw_url = r.text.strip()
            except:
                raw_url = ''

        if not self._is_video(raw_url):
            return {'parse': 1, 'url': raw_url or f'{self.host}/watch?token={token}', 'header': h}

        encoded = base64.urlsafe_b64encode(raw_url.encode()).decode().rstrip('=')
        return {'parse': 0, 'url': f'{self.plp}{encoded}', 'header': h}

    def parse_videos(self, items):
        videos = []
        for i in items.items():
            a = i.find('a[rel="bookmark"]') or i.find('a')
            if not a: continue
            link = a.attr('href')
            h2 = i.find('h2')
            title = ((h2.attr('title') or h2.text() or '') if h2 else '') or i.find('img').attr('alt') or ''
            if not link or not title: continue
            img = i.find('.movie-image')
            cover = (img.attr('data-srcset') or img.attr('src') or '') if img else ''
            t = i.find('time')
            dt = (t.attr('datetime') or '') if t else ''
            pd = dt.split('T')[0] if dt else ''
            videos.append({'vod_id': link, 'vod_name': title.strip(), 'vod_pic': f'{self.plp}{cover}',
                           'vod_remarks': pd, 'vod_pubdate': pd, 'style': {'type': 'rect', 'ratio': 1.5}})
        return videos

    @staticmethod
    def _is_video(url):
        return bool(url) and any(f in url.lower() for f in Spider.VIDEO_FMTS)
