# -*- coding: utf-8 -*-
import json
import re
import sys
import time
from base64 import b64encode, b64decode
from urllib.parse import urlparse

import requests
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    def init(self, extend=""):
        if not getattr(self, 'session', None):
            self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
            'sec-ch-ua-platform': '"Android"',
            'sec-ch-ua': '"Not/A)Brand";v="8", "Chromium";v="130", "Google Chrome";v="130"',
            'dnt': '1',
            'sec-ch-ua-mobile': '?1',
            'accept-language': 'zh-CN,zh;q=0.9',
            'priority': 'u=2',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        }
        try:
            cfg = json.loads(extend) if isinstance(extend, str) else (extend or {})
        except Exception:
            cfg = {}
        self.proxies = (cfg.get('proxies') if isinstance(cfg, dict) else None) or (cfg if isinstance(cfg, dict) else {})
        self.session.proxies.update(self.proxies)
        self.session.headers.update(self.headers)
        self.hsot = self.gethost()
        self.headers['referer'] = f"{self.hsot}/"
        self.session.headers.update(self.headers)

    def getName(self):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    pheader = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        'sec-ch-ua-platform': '"Android"',
        'sec-ch-ua': '"Not/A)Brand";v="8", "Chromium";v="130", "Google Chrome";v="130"',
        'dnt': '1',
        'sec-ch-ua-mobile': '?1',
        'origin': 'https://jx.8852.top',
        'sec-fetch-site': 'cross-site',
        'sec-fetch-mode': 'cors',
        'sec-fetch-dest': 'empty',
        'accept-language': 'zh-CN,zh;q=0.9',
        'priority': 'u=1, i',
    }

    def homeContent(self, filter):
        data = self.getpq(self.session.get(self.hsot))
        cdata = data('.stui-header__menu.type-slide li')
        ldata = data('.stui-vodlist.clearfix li')
        classes = []
        for k in cdata.items():
            i = k('a').attr('href')
            if i and 'type' in i:
                classes.append({'type_name': k.text(), 'type_id': re.search(r'\d+', i).group(0)})
        return {'class': classes, 'list': self.getlist(ldata)}

    def homeVideoContent(self):
        return {'list': ''}

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or '').strip()
        if tid.startswith('/vodsearch/'):
            key = tid[len('/vodsearch/'):]
            key = key.split('-------------')[0]
            data = self.getpq(self.session.get(f"{self.hsot}/vodsearch/{key}----------{pg}---.html"))
            return {'list': self.getlist(data('.stui-vodlist.clearfix li')), 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}
        data = self.getpq(self.session.get(f"{self.hsot}/vodshow/{tid}--------{pg}---.html"))
        return {'list': self.getlist(data('.stui-vodlist.clearfix li')), 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}

    def detailContent(self, ids):
        data = self.getpq(self.session.get(f"{self.hsot}{ids[0]}"))
        play_a = data('.stui-vodlist__box a').eq(0)
        play_name = play_a('img').attr('alt')
        play_url = play_a.attr('href')
        vod = {'vod_play_from': '花都影视', 'vod_play_url': f"{play_name}${play_url}"}
        try:
            vod_name = data('li.title:contains("名称") span').text().strip()
            if vod_name:
                vod['vod_name'] = vod_name
        except Exception:
            pass
        try:
            vod_pic = play_a('img').attr('data-original') or play_a('img').attr('src')
            if vod_pic:
                vod['vod_pic'] = self.proxy(vod_pic)
        except Exception:
            pass
        actors = []
        for a in data('li.title:contains("演员") span a').items():
            name = a.text().strip()
            href = (a.attr('href') or '').strip()
            if name and href and href.startswith('/'):
                actors.append(f'[a=cr:{json.dumps({"id": href, "name": name}, ensure_ascii=False)}/]{name}[/a]')
        if actors:
            vod['vod_actor'] = ' '.join(actors)
        tags = []
        for a in data('li.title:contains("类别") span a').items():
            name = a.text().strip()
            href = (a.attr('href') or '').strip()
            if name and href and href.startswith('/') and 'vodsearch' in href:
                tags.append(f'[a=cr:{json.dumps({"id": href, "name": name}, ensure_ascii=False)}/]{name}[/a]')
        title_text = data('li.title:contains("标题") span').text().strip()
        if tags:
            vod['vod_content'] = '标签:' + ' '.join(tags) + (('\n' + title_text) if title_text else '')
        elif title_text:
            vod['vod_content'] = title_text
        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        data = self.getpq(self.session.get(f"{self.hsot}/vodsearch/{key}----------{pg}---.html"))
        return {'list': self.getlist(data('.stui-vodlist.clearfix li')), 'page': pg}

    def playerContent(self, flag, id, vipFlags):
        html = self.session.get(f"{self.hsot}{id}").text
        m = re.search(r"var\s+player_(?:data|\w+)\s*=\s*(\{[\s\S]*?\})\s*(?:;|\u003c/script\u003e)", html, re.I)
        if not m:
            m = re.search(r"player_(?:data|\w+)\s*=\s*(\{[\s\S]*?\})\s*(?:;|\u003c/script\u003e)", html, re.I)
        if not m:
            raise Exception("未找到播放数据")
        jsdata = json.loads(m.group(1))
        url = jsdata.get('url', '')
        encrypt = int(jsdata.get('encrypt', 0) or 0)
        from urllib.parse import unquote, parse_qs
        if encrypt == 1:
            url = unquote(url)
        elif encrypt == 2:
            url = unquote(self.d64(url))
        if not url:
            raise Exception("播放地址为空")
        try:
            if ('/static/player/' in url or 'dplayer' in url.lower()) and 'url=' in url:
                q = parse_qs(urlparse(url).query)
                u = q.get('url', [''])[0]
                if u:
                    url = unquote(u)
        except Exception:
            pass
        return {'parse': 0, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{url}', 'header': self.pheader}

    def liveContent(self, url):
        pass

    def localProxy(self, param):
        url = self.d64(param['url'])
        return self.m3Proxy(url) if param.get('type') == 'm3u8' else self.tsProxy(url, param['type'])

    def gethost(self):
        deadline = time.time() + 20
        last = None
        while time.time() < deadline:
            try:
                cfg = self.session.get(
                    'https://ab.hdfby.com/js/config.js',
                    params={'v': '1'},
                    headers={'referer': 'https://ab.hdfby.com/', 'User-Agent': self.headers.get('User-Agent', 'Mozilla/5.0')},
                    timeout=(3, 5),
                    allow_redirects=True,
                    verify=False,
                )
                if cfg.status_code != 200 or not cfg.text:
                    raise Exception(str(cfg.status_code))
                for host in self._extract_urls(cfg.text):
                    if self._ok(host):
                        return host
                raise Exception('no_host')
            except Exception as e:
                last = e
                time.sleep(1)
        raise Exception(f"无可用域名:{last}")

    @staticmethod
    def _extract_urls(text):
        if not text:
            return []
        urls = re.findall(r"['\"](https?://[^'\"\s]+)['\"]", text, flags=re.I)
        if not urls:
            urls = re.findall(r"(https?://[^\s;]+)", text, flags=re.I)
        out, seen = [], set()
        for u in urls:
            u = (u or '').strip().rstrip('/')
            if u and u not in seen:
                seen.add(u)
                out.append(u)
        return out

    def _ok(self, host):
        try:
            h = {'User-Agent': self.headers.get('User-Agent', 'Mozilla/5.0'), 'referer': host + '/'}
            r = self.session.get(host + '/', headers=h, timeout=(2, 3), allow_redirects=True, verify=False, stream=True)
            if r.status_code in (403, 444) or r.status_code >= 500:
                return False
            return True
        except Exception:
            return False

    def getlist(self, data):
        videos = []
        for i in data.items():
            videos.append({
                'vod_id': i('a').attr('href'),
                'vod_name': i('img').attr('alt'),
                'vod_pic': self.proxy(i('img').attr('data-original')),
                'vod_year': i('.pic-tag-t').text(),
                'vod_remarks': i('.pic-tag-b').text()
            })
        return videos

    def getpq(self, data):
        try:
            return pq(data.text)
        except Exception:
            return pq(data.text.encode('utf-8'))

    def m3Proxy(self, url):
        ydata = requests.get(url, headers=self.pheader, proxies=self.proxies, allow_redirects=False, verify=False)
        data = ydata.content.decode('utf-8')
        if ydata.headers.get('Location'):
            url = ydata.headers['Location']
            data = requests.get(url, headers=self.pheader, proxies=self.proxies, verify=False).content.decode('utf-8')
        lines = data.strip().split('\n')
        last_r = url[:url.rfind('/')]
        parsed_url = urlparse(url)
        durl = parsed_url.scheme + "://" + parsed_url.netloc
        for index, string in enumerate(lines):
            if '#EXT' not in string:
                if 'http' not in string:
                    domain = last_r if string.count('/') < 2 else durl
                    string = domain + ('' if string.startswith('/') else '/') + string
                lines[index] = self.proxy(string, string.split('.')[-1].split('?')[0])
        return [200, "application/vnd.apple.mpegur", '\n'.join(lines)]

    def tsProxy(self, url, type):
        h = self.pheader.copy()
        if type == 'img':
            h = self.headers.copy()
        data = requests.get(url, headers=h, proxies=self.proxies, stream=True, verify=False)
        return [200, data.headers.get('Content-Type', 'application/octet-stream'), data.content]

    def proxy(self, data, type='img'):
        return f"{self.getProxyUrl()}&url={self.e64(data)}&type={type}" if data and len(self.proxies) else data

    def e64(self, text):
        try:
            return b64encode(text.encode('utf-8')).decode('utf-8')
        except Exception:
            return ""

    def d64(self, encoded_text):
        try:
            return b64decode(encoded_text.encode('utf-8')).decode('utf-8')
        except Exception:
            return ""
