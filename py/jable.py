import json
import re
import sys
from html import unescape
from urllib.parse import quote, urljoin, urlparse

import requests

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def init(self, extend=""):
        cfg = json.loads(extend) if extend else {}
        self.host = (cfg.get('host') or 'https://jable.tv').rstrip('/')
        self.proxies = cfg.get('proxies') or {          "http": "http://127.0.0.1:10172",
          "https": "http://127.0.0.1:10172"}
        self.headers = {'User-Agent': 'Mozilla/5.0', 'Referer': self.host + '/'}

    def getName(self):
        return 'Jable'

    def manualVideoCheck(self):
        return False

    def _abs(self, u):
        return u if str(u).startswith('http') else urljoin(self.host + '/', str(u or '').strip())

    def clean(self, s):
        return unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', s or ''))).strip()

    def html(self, url):
        r = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=15)
        return r.content.decode('utf-8', 'ignore') if r.status_code == 200 else ''

    def homeContent(self, filter):
        return {'class': [
            {'type_name': '最近更新', 'type_id': '/latest-updates/'},
          {'type_name': '最新发布', 'type_id': '/new-release/'},
            {'type_name': '热门影片', 'type_id': '/hot/'},
            {'type_name': '影片主题', 'type_id': '/categories/'}], 'filters': {}, 'list': self.videos(self.html(self.host + '/latest-updates/'))}

    def homeVideoContent(self):
        return {'list': self.homeContent(None)['list']}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        tid = str(tid or '')
        if tid.endswith('@folder'):
            tid = tid[:-7]
        url = self._abs(tid).rstrip('/') + '/'
        if urlparse(url).path.rstrip('/') == '/categories':
            data = self.folders(self.html(url))
            return {'list': data, 'page': 1, 'pagecount': 1, 'limit': 90, 'total': len(data)}
        data = self.videos(self.html(url if pg == 1 else url + str(pg) + '/'))
        return {'list': data, 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}

    def videos(self, html):
        out, seen = [], set()
        for b in re.findall(r'<div class="video-img-box[\s\S]*?</h6>[\s\S]*?</div>\s*</div>', html):
            href = self._abs(re.search(r'<a href="([^"]+/videos/[^"]+)"', b).group(1))
            if href in seen:
                continue
            seen.add(href)
            img = re.search(r'<img[^>]+data-src="([^"]+)"', b).group(1)
            name = self.clean(re.search(r'<h6 class="title">\s*<a[^>]*>([\s\S]*?)</a>', b).group(1))
            remark = re.search(r'<span class="label">([\s\S]*?)</span>', b)
            out.append({'vod_id': href, 'vod_name': name, 'vod_pic': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{img}', 'vod_remarks': self.clean(remark.group(1)) if remark else '', 'style': {'type': 'rect', 'ratio': 1.33}})
        return out

    def folders(self, html):
        out = []
        for b in re.findall(r'<div class="video-img-box[\s\S]*?</h4>[\s\S]*?</div>\s*</div>', html):
            href = self._abs(re.search(r'<a href="([^"]+/categories/[^"]+)"', b).group(1))
            img = re.search(r'<img src="([^"]+)"', b).group(1)
            name = self.clean(re.search(r'<h4>([\s\S]*?)</h4>', b).group(1))
            out.append({'vod_id': href + '@folder', 'vod_name': name, 'vod_pic': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{img}', 'vod_remarks': '', 'vod_tag': 'folder', 'style': {'type': 'rect', 'ratio': 1.33}})
        return out

    def searchContent(self, key, quick, pg='1'):
        pg = int(pg or 1)
        url = self.host + '/search/' + quote(str(key)) + '/'
        return {'list': self.videos(self.html(url if pg == 1 else url + str(pg) + '/')), 'page': pg, 'pagecount': 9999}

    def cr(self, href, name):
        return '[a=cr:%s/]%s[/a]' % (json.dumps({'id': self._abs(href), 'name': name}, ensure_ascii=False), name)

    def detailContent(self, ids):
        url = self._abs(ids[0])
        h = self.html(url)
        name = self.clean(re.search(r'<section class="video-info pb-3">[\s\S]*?<h4>([\s\S]*?)</h4>', h).group(1))
        pic = re.search(r'<meta property="og:image" content="([^"]+)"', h).group(1)
        play = re.search(r"var\s+hlsUrl\s*=\s*['\"]([^'\"]+\.m3u8[^'\"]*)", h).group(1)
        cats, tags, actors = [], [], []
        for a in re.findall(r'<h5 class="tags h6-md">([\s\S]*?)</h5>', h):
            for href, cls, text in re.findall(r'<a href="([^"]+)"(?: class="([^"]*)")?>([\s\S]*?)</a>', a):
                item = self.cr(href, self.clean(text))
                if 'cat' in cls.split():
                    cats.append(item)
                else:
                    tags.append(item)
        for href, body in re.findall(r'<a class="model" href="([^"]+)"[^>]*>([\s\S]*?)</a>', h):
            title = re.search(r'title="([^"]+)"', body)
            if title:
                actors.append(self.cr(href, self.clean(title.group(1))))
        return {'list': [{'vod_id': url, 'vod_name': name, 'vod_pic': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pic}', 'vod_director': ' '.join(cats), 'vod_actor': ' '.join(actors), 'vod_content': '标签：' + ' '.join(tags) if tags else '', 'vod_play_from': '播放', 'vod_play_url': '正片$' + play}]}

    def playerContent(self, flag, id, vipFlags):
        return {'parse': 0, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{id}', 'header': self.headers}
