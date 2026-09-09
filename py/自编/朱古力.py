import json
import sys
from urllib.parse import quote, urlparse, parse_qs

import requests

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        elif isinstance(extend, dict):
            cfg = extend

        self.proxies = cfg.get('proxies') or {          "http": "http://127.0.0.1:10172",
          "https": "http://127.0.0.1:10172"}
        self.host = (cfg.get('host') or 'https://pigav.ws').rstrip('/')

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': f'{self.host}/home',
        }

        r = requests.get(f'{self.host}/api/v1/config', headers=self.headers, proxies=self.proxies, timeout=10)
        if r.status_code != 200:
            raise RuntimeError(f"站点不可用: {self.host} status={r.status_code}")

    def getName(self):
        return "PIGAV(PeerTube)最高画质直链"

    def isVideoFormat(self, url):
        url = (url or '').lower()
        return any(url.endswith(x) or x in url for x in ['.m3u8', '.mp4'])

    def manualVideoCheck(self):
        return False

    def _api_get(self, path, params=None):
        url = f"{self.host}{path}"
        r = requests.get(url, headers=self.headers, proxies=self.proxies, params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def _abs(self, maybe_path):
        if not maybe_path:
            return ''
        if maybe_path.startswith('http'):
            return maybe_path
        return f"{self.host}{maybe_path}"

    def _to_vod(self, v):
        short_id = v.get('shortUUID') or v.get('uuid') or str(v.get('id'))
        thumb = v.get('thumbnailPath') or v.get('previewPath')
        return {
            'vod_id': short_id,
            'vod_name': (v.get('name') or '').strip(),
            'vod_pic': self._abs(thumb),
            'vod_remarks': str(v.get('duration') or ''),
            'style': {"type": "rect", "ratio": 1.33},
        }

    def _pick_best_variant_m3u8(self, obj):
        sps = obj.get('streamingPlaylists') or []
        if not sps:
            raise RuntimeError('视频无 streamingPlaylists')

        files = (sps[0] or {}).get('files') or []
        if not files:
            raise RuntimeError('streamingPlaylists 无 files')

        def score(it):
            r = it.get('resolution')
            if isinstance(r, dict):
                r = r.get('id') or r.get('label')
            try:
                return int(r)
            except Exception:
                return 0

        best = sorted(files, key=score, reverse=True)[0]
        url = best.get('playlistUrl')
        if not url:
            raise RuntimeError('best file 无 playlistUrl')

        res = best.get('resolution')
        if isinstance(res, dict):
            res = res.get('id') or res.get('label')
        name = f"HLS-{res}p" if res else 'HLS'
        return name, url

    def homeContent(self, filter):
        classes = [
            {'type_name': '探索', 'type_id': '-publishedAt'},
            {'type_name': '人氣熱播', 'type_id': '-trending'},
            {'type_name': '最新片源', 'type_id': '-publishedAt'},
            {'type_name': '最多收藏', 'type_id': '-likes'},
            {'type_name': '全站觀看', 'type_id': '-views'},
            {'type_name': '留言最多', 'type_id': '-comments'},
            {'type_name': '名稱排序', 'type_id': 'name'},
        ]

        data = self._api_get('/api/v1/videos', params={
            'sort': '-publishedAt',
            'start': 0,
            'count': 30,
            'nsfw': 'both',
        })
        videos = [self._to_vod(v) for v in (data.get('data') or []) if v.get('name')]
        return {'class': classes, 'filters': {}, 'list': videos}

    def homeVideoContent(self):
        res = self.homeContent(None)
        return {'list': res.get('list', [])}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        page_size = 30
        start = (pg - 1) * page_size

        tid_str = (tid or '').strip() if isinstance(tid, str) else ''

        path = ''
        query = ''
        if tid_str.startswith('http://') or tid_str.startswith('https://'):
            u = urlparse(tid_str)
            path = u.path or ''
            query = u.query or ''
        else:
            if tid_str.startswith('/'):
                u = urlparse(tid_str)
                path = u.path or ''
                query = u.query or ''

        if path.startswith('/c/'):
            handle = path[len('/c/'):].strip('/')
            data = self._api_get(f'/api/v1/video-channels/{quote(handle, safe="@.")}/videos', params={
                'sort': '-publishedAt',
                'start': start,
                'count': page_size,
                'nsfw': 'both',
            })
        elif path.startswith('/search') and 'tagsOneOf=' in (query or ''):
            qs = parse_qs(query, keep_blank_values=False)
            tag = (qs.get('tagsOneOf') or [''])[0]
            data = self._api_get('/api/v1/videos', params={
                'tagsOneOf': tag,
                'sort': '-publishedAt',
                'start': start,
                'count': page_size,
                'nsfw': 'both',
            })
        else:
            sort_key = tid_str or '-publishedAt'
            data = self._api_get('/api/v1/videos', params={
                'sort': sort_key,
                'start': start,
                'count': page_size,
                'nsfw': 'both',
            })

        total = int(data.get('total') or 0)
        videos = [self._to_vod(v) for v in (data.get('data') or []) if v.get('name')]
        pagecount = (total + page_size - 1) // page_size if total else 1

        return {
            'list': videos,
            'page': pg,
            'pagecount': pagecount,
            'limit': page_size,
            'total': total,
        }

    def detailContent(self, ids):
        vid = ids[0]
        obj = self._api_get(f'/api/v1/videos/{vid}')

        title = (obj.get('name') or '').strip()
        desc = (obj.get('description') or '').strip()

        channel = obj.get('channel') or {}
        ch_name = (channel.get('displayName') or channel.get('name') or '').strip()
        ch_host = (channel.get('host') or '').strip()
        ch_raw_name = (channel.get('name') or '').strip()

        director_id = ''
        if ch_raw_name and ch_host:
            director_id = f"{self.host}/c/{ch_raw_name}@{ch_host}"

        director_click = ''
        if ch_name and director_id:
            director_click = f'[a=cr:{json.dumps({"id": director_id, "name": ch_name}, ensure_ascii=False)}/]{ch_name}[/a]'

        name, m3u8_url = self._pick_best_variant_m3u8(obj)
        play_url = f"{name}${m3u8_url}"

        tags = obj.get('tags') or []
        tag_clicks = []
        for t in tags:
            if not t:
                continue
            q = quote(str(t))
            href = f"{self.host}/search?tagsOneOf={q}&resultType=videos"
            tag_clicks.append(f'[a=cr:{json.dumps({"id": href, "name": str(t)}, ensure_ascii=False)}/]{t}[/a]')

        tag_label = '标签:'
        intro = (desc or '').strip() or title
        vod_content_text = (tag_label + (' ' + ' '.join(tag_clicks) if tag_clicks else ''))
        vod_content_text += "\n\n劇情：\n" + intro

        return {
            'list': [{
                'vod_id': vid,
                'vod_name': title,
                'vod_play_from': 'PeerTube',
                'vod_play_url': play_url,
                'vod_director': director_click,
                'vod_content': vod_content_text,
            }]
        }

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg or 1)
        page_size = 30
        start = (pg - 1) * page_size

        data = self._api_get('/api/v1/search/videos', params={
            'search': key,
            'start': start,
            'count': page_size,
            'nsfw': 'both',
        })

        total = int(data.get('total') or 0)
        pagecount = (total + page_size - 1) // page_size if total else 1
        videos = [self._to_vod(v) for v in (data.get('data') or []) if v.get('name')]

        return {'list': videos, 'page': pg, 'pagecount': pagecount, 'total': total}

    def playerContent(self, flag, id, vipFlags):
        parse = 0 if self.isVideoFormat(id) else 1
        return {'parse': parse, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{id}', 'header': self.headers}
