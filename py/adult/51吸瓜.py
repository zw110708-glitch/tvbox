# -*- coding: utf-8 -*-
# by @嗷呜
import json
import re
import sys
import threading
import time
import requests
from base64 import b64decode, b64encode
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from pyquery import PyQuery as pq
sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    # 固定域名池（按需增减，启动时自动测速选最快）
    FIXED_HOSTS = [
        "https://chigua.com",
        "https://51cg1.com",
    ]

    def init(self, extend="{}"):
        config = json.loads(extend)
        self.proxies = config.get('proxy', {}) or {}
        self.plp = config.get('plp', '')
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Not/A)Brand";v="8", "Chromium";v="134", "Google Chrome";v="134"',
            'Accept-Language': 'zh-CN,zh;q=0.9'
        }
        self.host = self._pick_best_host()
        self.headers.update({'Origin': self.host, 'Referer': f"{self.host}/"})

    # ---------- 固定域名测速 ----------
    def _pick_best_host(self):
        hosts = self.FIXED_HOSTS
        if len(hosts) == 1:
            return hosts[0]
        results = {}
        threads = []
        def test(url):
            try:
                start = time.time()
                requests.head(url, headers=self.headers, proxies=self.proxies, timeout=3.0, allow_redirects=False)
                results[url] = (time.time() - start) * 1000
            except Exception:
                results[url] = float('inf')
        for h in hosts:
            t = threading.Thread(target=test, args=(h,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        return min(results.items(), key=lambda x: x[1])[0]

    # ---------- 框架接口 ----------
    def getName(self):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def homeContent(self, filter):
        data = pq(requests.get(self.host, headers=self.headers, proxies=self.proxies).content)
        result = {}
        classes = []
        for k in list(data('.navbar-nav.mr-auto').children('li').items())[1:-3]:
            if k('ul'):
                for j in k('ul li').items():
                    classes.append({
                        'type_name': j('a').text(),
                        'type_id': j('a').attr('href').strip(),
                    })
            else:
                classes.append({
                    'type_name': k('a').text(),
                    'type_id': k('a').attr('href').strip(),
                })
        result['class'] = classes
        result['list'] = self.getlist(data('#index article a'))
        return result

    def homeVideoContent(self):
        pass

    def categoryContent(self, tid, pg, filter, extend):
        if '@folder' in tid:
            id = tid.replace('@folder', '')
            videos = self.getfod(id)
        else:
            data = pq(requests.get(f"{self.host}{tid}{pg}", headers=self.headers, proxies=self.proxies).content)
            videos = self.getlist(data('#archive article a'), tid)
        result = {}
        result['list'] = videos
        result['page'] = pg
        result['pagecount'] = 1 if '@folder' in tid else 99999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def detailContent(self, ids):
        url = ids[0] if ids[0].startswith("http") else f"{self.host}{ids[0]}"
        data = pq(requests.get(url, headers=self.headers, proxies=self.proxies).content)
        vod = {'vod_play_from': '51吸瓜'}
        try:
            clist = []
            if data('.tags .keywords a'):
                for k in data('.tags .keywords a').items():
                    title = k.text()
                    href = k.attr('href')
                    clist.append('[a=cr:' + json.dumps({'id': href, 'name': title}) + '/]' + title + '[/a]')
            vod['vod_content'] = '点击展开↓↓↓\n' + ' '.join(clist)
        except Exception:
            vod['vod_content'] = data('.post-title').text()
        try:
            plist = []
            if data('.dplayer'):
                for c, k in enumerate(data('.dplayer').items(), start=1):
                    config = json.loads(k.attr('data-config'))
                    plist.append(f"视频{c}${config['video']['url']}")
            vod['vod_play_url'] = '#'.join(plist)
        except Exception:
            vod['vod_play_url'] = f"请停止活塞运动，可能没有视频${url}"
        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        data = pq(requests.get(f"{self.host}/search/{key}/{pg}", headers=self.headers, proxies=self.proxies).content)
        return {'list': self.getlist(data('#archive article a')), 'page': pg}

    def playerContent(self, flag, id, vipFlags):
        p = 0 if re.search(r'\.(m3u8|mp4|flv|ts|mkv|mov|avi|webm)', id) else 1
        return {'parse': p, 'url': f"{self.plp}{id}", 'header': self.headers}

    def localProxy(self, param):
        try:
            url = self.d64(param['url'])
            match = re.search(r"loadBannerDirect\('([^']*)'", url)
            if match:
                url = match.group(1)
            res = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=10)
            return [200, res.headers.get('Content-Type'), self.aesimg(res.content)]
        except Exception as e:
            self.log(f"图片代理错误: {str(e)}")
            return [500, 'text/html', '']

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

    def getfod(self, id):
        url = f"{self.host}{id}"
        data = pq(requests.get(url, headers=self.headers, proxies=self.proxies).content)
        vdata = data('.post-content[itemprop="articleBody"]')
        for i in ['.txt-apps', '.line', 'blockquote', '.tags', '.content-tabs']:
            vdata.remove(i)
        p = vdata('p')
        videos = []
        for i, x in enumerate(vdata('h2').items()):
            c = i * 2
            videos.append({
                'vod_id': p.eq(c)('a').attr('href'),
                'vod_name': p.eq(c).text(),
                'vod_pic': f"{self.getProxyUrl()}&url={self.e64(p.eq(c+1)('img').attr('data-xkrkllgl'))}",
                'vod_remarks': x.text()
            })
        return videos

    def getlist(self, data, tid=''):
        videos = []
        l = '/mrdg' in tid
        for k in data.items():
            a = k.attr('href')
            b = k('h2').text()
            c = k('span[itemprop="datePublished"]').text()
            if a and b and c:
                videos.append({
                    'vod_id': f"{a}{'@folder' if l else ''}",
                    'vod_name': b.replace('\n', ' '),
                    'vod_pic': f"{self.getProxyUrl()}&url={self.e64(k('script').text())}",
                    'vod_remarks': c,
                    'vod_tag': 'folder' if l else '',
                    'style': {"type": "rect", "ratio": 1.33}
                })
        return videos

    def aesimg(self, word):
        key = b'f5d965df75336270'
        iv = b'97b60394abc2fbe1'
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(word), AES.block_size)