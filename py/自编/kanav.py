# -*- coding: utf-8 -*-
# 修复版 Spider：删除标签与演员相关逻辑，仅保留简介内容（vod_content）
import json
import re
import requests
from pyquery import PyQuery as pq
import sys
sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    host = 'https://kanav.ad'
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'referer': 'https://kanav.ad/',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8'
    }

    def init(self, extend=''):
        self.proxies = json.loads(extend).get('proxy', {}) if extend else {}

    def getName(self):
        return 'kanav'

    def fetch(self, url, params=None):
        try:
            r = requests.get(url, headers=self.headers, params=params,
                             proxies=self.proxies, timeout=12)
            r.encoding = r.apparent_encoding or 'utf-8'
            return r.text
        except:
            return ''

    def homeContent(self, filter):
        hot_url = f'{self.host}/index.php/label/hot.html'
        html = self.fetch(hot_url)
        classes = [
            {'type_name': '中文字幕', 'type_id': 'vod/type/id/1'},
            {'type_name': '日韩有码', 'type_id': 'vod/type/id/2'},
            {'type_name': '日韩无码', 'type_id': 'vod/type/id/3'},
            {'type_name': '国产AV', 'type_id': 'vod/type/id/4'},
            {'type_name': '流出自拍', 'type_id': 'vod/type/id/22'},
            {'type_name': '自拍泄密', 'type_id': 'vod/type/id/30'},
            {'type_name': '探花约炮', 'type_id': 'vod/type/id/31'},
            {'type_name': '主播录制', 'type_id': 'vod/type/id/32'},
            {'type_name': '动漫番剧', 'type_id': 'vod/type/id/20'},
            {'type_name': '里番', 'type_id': 'vod/type/id/25'},
            {'type_name': '泡面番', 'type_id': 'vod/type/id/26'},
            {'type_name': 'Motion Anime', 'type_id': 'vod/type/id/27'},
            {'type_name': '3D动画', 'type_id': 'vod/type/id/28'},
            {'type_name': '同人作品', 'type_id': 'vod/type/id/29'},
            {'type_name': '热门影片', 'type_id': 'label/hot'},
        ]
        return {
            'class': classes,
            'filters': self.get_filters(),
            'list': self.parse_videos(pq(html)('.post-list .video-item'))
        }

    def get_filters(self):
        order_values = [
            {'n': '最新发布', 'v': 'time_add'},
            {'n': '最多观看', 'v': 'hits'},
            {'n': '本周热榜', 'v': 'hits_week'},
        ]
        base = [{'key': 'order', 'name': '排序', 'value': order_values}]
        keys = [
            'vod/type/id/1', 'vod/type/id/2', 'vod/type/id/3', 'vod/type/id/4',
            'vod/type/id/22', 'vod/type/id/30', 'vod/type/id/31', 'vod/type/id/32',
            'vod/type/id/20', 'vod/type/id/25', 'vod/type/id/26', 'vod/type/id/27',
            'vod/type/id/28', 'vod/type/id/29',
        ]
        filters = {k: base for k in keys}
        filters['label/hot'] = base
        return filters

    def categoryContent(self, tid, pg, filter, extend):
        order = None
        if extend and isinstance(extend, dict):
            order = extend.get('order')
        url = ''
        if tid.startswith('vod/type/id/'):
            cat_id = tid.split('/')[-1]
            if order:
                url = f"{self.host}/index.php/vod/show/by/{order}/id/{cat_id}.html"
            else:
                url = f"{self.host}/index.php/{tid}.html"
            if int(pg) > 1:
                url = url.replace('.html', f'/page/{pg}.html')
        elif tid == 'label/hot':
            url = f"{self.host}/index.php/label/hot.html"
        else:
            url = f"{self.host}/index.php/{tid}.html"
        html = self.fetch(url)
        data = pq(html)
        videos = self.parse_videos(data('.post-list .video-item'))
        pagecount = 1
        tail = data('.pagination a.extend').attr('href')
        if tail:
            m = re.search(r'/page/(\d+)\.html', tail)
            if m:
                pagecount = int(m.group(1))
        elif data('.pagination li').length:
            pagecount = data('.pagination li').length
        return {
            'list': videos,
            'page': pg,
            'pagecount': pagecount or 1,
            'limit': 90,
            'total': 999999
        }

    def detailContent(self, ids):
        # 仅保留简介内容：从 .video-title h1 抓取，写入 vod_content
        vid = ids[0]
        url = vid if vid.startswith('http') else f"{self.host}{vid}"
        html = self.fetch(url)
        data = pq(html)
        page_title = data('title').text() or ''
        show_name = re.sub(r'\s*\[.*?\]\s*$', '', (data('h3').text() or page_title)).strip()
        intro_text = (data('.video-box-ather .container').eq(0)
                      .find('.video-countext').eq(0)
                      .find('.video-title').eq(0)
                      .find('h1').text() or '').strip()
        id_match = re.search(r'id/(\d+)', vid)
        id_val = id_match.group(1) if id_match else vid
        cover = data('.video-countext .countext-img').attr('src') or data('meta[property="og:image"]').attr('content')
        vod = {
            'vod_name': show_name,
            'vod_play_from': 'dplayer',
            'vod_play_url': f"{show_name}${id_val}",
            'vod_pic': cover,
            'vod_year': ''
        }
        vod['vod_content'] = intro_text or ''
        return {'list': [vod]}

    def searchContent(self, key, quick, pg='1'):
        params = {'wd': key, 'by': 'time_add'}
        url = f"{self.host}/index.php/vod/search.html"
        html = self.fetch(url, params=params)
        if int(pg) > 1:
            url2 = f"{self.host}/index.php/vod/search/by/time_add/page/{pg}/wd/{requests.utils.quote(key)}.html"
            html = self.fetch(url2)
        return {
            'list': self.parse_videos(pq(html)('.post-list .video-item')),
            'page': pg
        }

    def _robust_unquote(self, s):
        if not s:
            return s
        import urllib.parse as _urlparse
        prev = None
        cur = s
        for _ in range(5):
            if prev == cur:
                break
            prev = cur
            cur = _urlparse.unquote(cur)
            if cur.startswith('http://') or cur.startswith('https://'):
                cur2 = _urlparse.unquote(cur)
                if cur2.startswith('http://') or cur2.startswith('https://'):
                    cur = cur2
                break
        return cur

    def playerContent(self, flag, id, vipFlags):
        import json as _json
        import base64 as _base64
        play_url = f"{self.host}/index.php/vod/play/id/{id}/sid/1/nid/1.html"
        html = self.fetch(play_url)
        video_url = ''
        m = re.search(r"var\s+player_[a-zA-Z]+\s*=\s*(\{.*?\})", html, re.S)
        if m:
            try:
                player = _json.loads(m.group(1))
                enc = int(player.get('encrypt', 0) or 0)
                raw = player.get('url', '')
                if enc == 2 and raw:
                    try:
                        raw_dec = _base64.b64decode(raw).decode('utf-8', 'ignore')
                        video_url = self._robust_unquote(raw_dec)
                    except Exception:
                        video_url = ''
                elif enc == 1 and raw:
                    video_url = self._robust_unquote(raw)
                else:
                    video_url = raw
                for sep in ['$$$', '$$', '\n', '\r', '#', '|']:
                    if video_url and sep in video_url:
                        video_url = video_url.split(sep)[0]
                        break
            except Exception:
                video_url = ''
        if not video_url:
            m2 = re.search(r"MacPlayerConfig[^\n]*?playerUrl\s*:\s*'([^']+)'", html)
            if m2:
                video_url = self._robust_unquote(m2.group(1))
        if not video_url:
            mv = re.search(r"\x3cvideo[^\x3e]+src=\"([^\"]+)\"", html)
            if mv:
                video_url = mv.group(1)
        if not video_url:
            m3 = re.search(r"\"url\"\s*:\s*\"([A-Za-z0-9+/=]+)\"", html)
            if m3:
                try:
                    tmp = _base64.b64decode(m3.group(1)).decode('utf-8', 'ignore')
                    video_url = self._robust_unquote(tmp)
                except Exception:
                    pass
        if video_url:
            video_url = video_url.strip().replace('\u0026amp;', '\u0026')
        return {
            'parse': 0,
            'url': video_url,
            'header': {
                'user-agent': self.headers['user-agent'],
                'referer': play_url,
                'origin': self.host,
            }
        } if video_url else {'parse': 0, 'url': ''}

    def parse_videos(self, items):
        videos = []
        for i in items.items():
            link = i('.featured-content-image a').attr('href') or i('a').attr('href')
            pic = i('img').attr('src')
            title = i('.entry-title a').text().strip() if i('.entry-title a') else (i('img').attr('alt') or '')
            if not link or not title:
                continue
            title = re.sub(r'\s*\|.*$', '', title).strip()
            tag = i('.model-view-left').text().strip()
            duration = i('.model-view').text().strip()
            videos.append({
                'vod_id': link,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': (duration or '').strip(),
                'vod_tag': tag,
                'style': {"type": "rect", "ratio": 1.5}
            })
        return videos

    # 占位接口
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
