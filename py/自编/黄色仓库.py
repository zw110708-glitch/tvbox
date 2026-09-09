import re
import sys
import json
import urllib.parse

import requests

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    candidates = ['https://hsck123.com', 'http://cctv12306.com', 'https://njav.sbs']

    config = {'player': {}, 'filter': {}}

    def __init__(self):
        self.proxy = {}
        self.host = self.candidates[0].rstrip('/')
        self.header = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
            'Referer': self.host + '/',
        }

    def getName(self):
        return '黄色仓库'

    def init(self, extend):
        cfg = {}
        if extend:
            if isinstance(extend, dict):
                cfg = extend
            else:
                try:
                    cfg = json.loads(extend)
                except Exception:
                    cfg = {}
        self.plp = cfg.get('plp', '')
        self.proxy = cfg.get('proxy', {})
        self._select_host()

    def _select_host(self):
        for h in self.candidates:
            h = h.rstrip('/')
            try:
                r = requests.get(h + '/?type=ycgc&p=1', headers={'User-Agent': self.header['User-Agent'], 'Referer': h + '/'}, proxies=self.proxy, timeout=8)
                if r.status_code == 200 and 'stui-vodlist' in r.text and '/view/?id=' in r.text:
                    self.host = h
                    self.header['Referer'] = h + '/'
                    return
            except Exception:
                pass
        self.host = self.candidates[0].rstrip('/')
        self.header['Referer'] = self.host + '/'

    def fetch(self, url):
        return requests.get(url, headers=self.header, proxies=self.proxy, timeout=10)

    def homeContent(self, filter):
        return {
            'class': [
                {'type_name': '国产新片', 'type_id': 'ycgc'},
                {'type_name': '无码中文字幕', 'type_id': 'wz'},
                {'type_name': '有码中文字幕', 'type_id': 'yz'},
                {'type_name': '日本无码', 'type_id': 'rw'},
                {'type_name': '日本有码', 'type_id': 'ry'},
                {'type_name': '骑兵破解', 'type_id': 'qp'},
                {'type_name': '国产视频', 'type_id': 'gc'},
                {'type_name': '欧美高清', 'type_id': 'om'},
                {'type_name': '动漫剧情', 'type_id': 'dm'},
            ]
        }

    def _parse_list(self, html):
        out = []
        seen = set()
        for m in re.finditer(r'href="/view/\?id=([^"]+)"[^>]*?title="([^"]+)"[^>]*?data-original="([^"]+)"', html):
            vid = m.group(1).strip()
            if not vid or vid in seen:
                continue
            seen.add(vid)
            name = m.group(2).strip()
            pic = m.group(3).strip()
            if name:
                out.append({'vod_id': vid, 'vod_name': name, 'vod_pic': pic, 'vod_remarks': ''})
        if out:
            return out
        for m in re.finditer(r'href="/view/\?id=([^"]+)"[^>]*?title="([^"]+)"', html):
            vid = m.group(1).strip()
            if not vid or vid in seen:
                continue
            seen.add(vid)
            name = m.group(2).strip()
            if name:
                out.append({'vod_id': vid, 'vod_name': name, 'vod_pic': '', 'vod_remarks': ''})
        return out

    def homeVideoContent(self):
        r = self.fetch(self.host + '/?type=ycgc&p=1')
        return {'list': self._parse_list(r.text)}

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or '')
        pg = str(pg or '1')
        url = self.host + '/?type=' + urllib.parse.quote(tid) + '&p=' + urllib.parse.quote(pg)
        r = self.fetch(url)
        return {'list': self._parse_list(r.text), 'page': int(pg), 'pagecount': 9999, 'limit': 30, 'total': 999999}

    def detailContent(self, array):
        vid = array[0]
        if str(vid).startswith('http'):
            url = str(vid)
        else:
            url = self.host + '/view/?id=' + urllib.parse.quote(str(vid))

        r = self.fetch(url)
        html = r.text

        title = ''
        m = re.search(r'<title>(.*?)</title>', html, re.S | re.I)
        if m:
            title = re.sub(r'\s+', ' ', m.group(1)).split('-')[0].strip()

        m3u8 = ''
        m = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html)
        if m:
            m3u8 = m.group(0)

        pic = ''
        m = re.search(r'<img[^>]+src="[^\"]*\.m3u8[^\"]*"[^>]*>', html, re.I)
        if m:
            a = re.search(r'alt="([^"]+)"', m.group(0), re.I)
            if a and a.group(1).startswith('http'):
                pic = a.group(1).strip()

        vod = {'vod_id': vid, 'vod_name': title, 'vod_pic': pic, 'vod_content': '', 'vod_play_from': '黄色仓库', 'vod_play_url': ('直链$' + m3u8) if m3u8 else ''}
        return {'list': [vod]}

    def searchContent(self, key, quick, page='1'):
        page = str(page or '1')
        url = self.host + '/?search2=ndafeoafa&search=' + urllib.parse.quote(key) + '&p=' + urllib.parse.quote(page)
        r = self.fetch(url)
        return {'list': self._parse_list(r.text)}

    def playerContent(self, flag, id, vipFlags):
        if str(id).startswith('http') and '.m3u8' in str(id):
            return {'parse': 0, 'playUrl': '', 'url': self.plp + str(id), 'header': self.header}
        det = self.detailContent([id])
        pu = det.get('list', [{}])[0].get('vod_play_url', '')
        if '$' in pu:
            real = pu.split('$', 1)[1]
            if real:
                return {'parse': 0, 'playUrl': '', 'url': f'{self.plp}{real}', 'header': self.header}
        return {}
