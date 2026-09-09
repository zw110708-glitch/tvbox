# -*- coding: utf-8 -*-
# by @嗷呜
import gzip
import json
import re
import sys
import time
import uuid
import requests
from base64 import b64decode
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import unquote, urlparse
from Crypto.Hash import SHA1, HMAC
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    # 域名导航（用于获取可用域名池）
    NAV = ("https://x99dh.cc","https://x99dh.one","https://x97.icu","https://x97.one")
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    # 推荐接口
    xhost = 'https://client-rapi-missav.recombee.com'

    # 分类
    ccccc = 'H4sIAAAAAAAAA6WVW0sbQRTHv4rk2WB2s7ls34JEG6hticamLaWMu6NZkp0Ne9GkRUhEtGihqBihTdtY0AdJisEW0qTSL5PZxG/RvZSieyZ96UPYwPx/5z5nnr8OmdUyfkmQikP3pkLDXsdu7NLOCf1xHJr2zxTZPZFVPh6bkciMVFAINnDYsFZMxSzh0OZ0wIjdrI1/HdgfvtmNy6CRGCe4RgjeYHCNy+F1c9jbo70twCWTLqfjEkYGw+do+3T05af9vU53+0E2znMuaxEJE0PTsRx2jBShDXp2Rbcvhr3a+Pz6rg2HRpKpY8PABsN3d0A/7QNiDROdJafvDsanb+nxDiBUVMQ6g1jOgl5ERC8n38eMIwDQcLBnn5yNdro3jRrAfdrUZFQNFzST1cP2Ta3Lprm46NIbGBdLk3G7+WaC81jCxVWNmIVJ/GIm+whwURczFF2D+ge5fA7WyNWXrIoF9fOphymQlhfWGiII6h9n04tLmfm0813I5BaCaDLOeykhRBi5hGdzS+kJ2UiWyZjmVBZG59Uc6Yzg7JPWqFX/v9mfm+WDqOh5XJV4qL6ffvoM9CfKiaLorYgCrr5iNMn+2B32285QwHH0p7FY1ZjT4FxJdx7rRyA7MRZLeDBX1ojM8DmLdGVlBSMiaSooKZ/g+KiHS7dl/zRS1oEZIZLkgkYcGTDDRVTLsJz/QQMcl+AFb7/9lQC4jCTN/alIRaDyiYjg79U7Kjj1yF3ekgYCiMb80f9zvDk9FSDz+Xw4tczuW6VSQeuMpvX79HxgN9qAEpyLousKlo0SMgqQvGkdjN5/FeJchH0JCLLWCmbVE0yAI2IUwDx/C/YEEO4Pxt0dunVFLw5BkQX/issaY58sPYHV8feJucEqzpylW0U4CF4bVv0zGNznI9rcHznP6mEHPB3FkrLOYJz3fDIj+cyL38kN2ZoFCAAA'
    # 通用筛选
    fts = 'H4sIAAAAAAAAA23P30rDMBQG8FeRXM8X8FVGGZk90rA0HU3SMcZgXjn8V6p2BS2KoOiFAwUn2iK+TBP7GBpYXbG9/c6Pc77TnaABjNHOFtojVIDPUQcx7IJJvl9ydX30GwSYSpN0J4iZgTqJiywrPlN1vm/GJiPMJgGxJaZo2qnc3WXDuZIKMqSwUcX7Ui8O1DJRH3Gldh3CgMM2l31BhNGW8euq3PNFrac+PVNZ2NYzjMrbY53c6/Sm2uwDBczB7mGxqaDTWfkV6atXvXiu4FD2KeHOf3nxViahjv8YxwHYtWfyQ3NvFZYP85oSno3HvYDAiNevPqnosWFHAAPahnU6b2DXY8Jp0bO8QdfEmlo/SBd5PPUBAAA='
    # 女优筛选
    actfts = 'H4sIAAAAAAAAA5WVS2sUQRRG/0rT6xTcqq5Xiwjm/X6sQxZjbBLRBBeOIEGIIEgWrtwI4lJEQsjGhU6Iv2bGcf6FVUUydW/d1SxT55sDfbpmsn9WP+/e1A+q+rh7dnT8qp6rT3snXTz4N7icXH4OB697L/rxZP+sPo1g+Ot8PPg+vvoyOb+IOJ7Vb+fuqGxkJSrZmMOTexiORDjAGxs3GvDGinCANjp5NPbo4NHYo5PHYI8OHoM9JnkM9pjgMdhjksdijwkeiz02eSz22OCx2GOTx2GPDR6HPS55HPa44HHY45LHY48LHo89Pnk89vjg8djjk6fFHh88bfAcxNXduz/sv0Qvfnz74+/X65lf/OMqfzD9ndF8geYzWijQQkaLBVrMaKlASxktF2g5o5UCrWS0WqDVjNYKtJbReoHWM9oo0EZGmwXazGirQFsZbRdoO6OdAu1ktFug3Yz2CrRH70TvqEN3YvT75+TP+5nvxMNKwf0pCIWur4JwM5spVCAaRJtI9ZQ2IPBPg47UTKkGgb/wJlI7pQYE/ho/QsiCaFv61E+7J338Izj6MJi8+xSefnhzO/PTK1CmGt58G118zM+pDBloPtBk0PBBQwaKDxQZSD6QZAB8QN6UbNlAtmTg+cCTgeMDRwaWDywZ8JKSlJS8pCQlJS8pSUnJS0pSUvKSkpSUvKQkJYGXBFISeEkgJYGXBFISeEkgJYGXBFISeEkgJYGXBFISeEkgJYGXBFISeElI/7QO/gOZ7bAksggAAA=='

    def init(self, extend="{}"):
        try:
            cfg = json.loads(extend) if isinstance(extend, str) else (extend or {})
        except Exception:
            cfg = {}
        self.plp = cfg.get('plp', '')
        self.proxies = cfg.get('proxy', {})
        self.s = requests.Session()
        self.host = self._best_host()
        self.headers = {
            "User-Agent": self.UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            # 播放地址必须带 missav.ai 的 Referer，否则 m3u8 返回 403
            "Referer": "https://missav.ai",
            "Origin": "https://missav.ai",
        }

    def getName(self):
        return "MissAV"

    def isVideoFormat(self, url):
        u = (url or '').lower()
        return '.m3u8' in u or '.mp4' in u

    # ---------- 自动域名 ----------
    def _norm_host(self, u):
        p = urlparse((u or '').strip().rstrip('/'))
        path = (p.path or '').rstrip('/')
        if path.endswith('/cn'):
            path = path[:-3]
        return (p.scheme + '://' + p.netloc + path).rstrip('/')

    def _parse_pool(self, html):
        m = re.search(r"encodedData\s*=\s*'([^']+)'", html or '')
        if not m:
            return []
        try:
            data = json.loads(unquote(b64decode(m.group(1)).decode('utf-8', 'ignore')))
        except Exception:
            return []
        pool, seen = [], set()
        for it in data if isinstance(data, list) else []:
            if it.get('name') != 'MissAV':
                continue
            for u in it.get('urls') or []:
                host, test = self._norm_host(u.get('url')), (u.get('testUrl') or '').strip()
                if host and test and host not in seen:
                    seen.add(host)
                    pool.append((host, test))
        return pool

    def _probe(self, url):
        try:
            r = requests.get(url, headers={"User-Agent": self.UA}, proxies=self.proxies, timeout=5)
            return r.status_code == 200 and (r.text or '').strip().lower() == 'ok'
        except Exception:
            return False

    def _best_host(self):
        pool = []
        for nav in self.NAV:
            try:
                r = requests.get(nav, headers={"User-Agent": self.UA}, proxies=self.proxies, timeout=10)
                pool = self._parse_pool(r.text or '')
                if pool:
                    break
            except Exception:
                continue
        if not pool:
            return None
        with ThreadPoolExecutor(max_workers=min(12, len(pool))) as ex:
            futs = {ex.submit(self._probe, t): h for h, t in pool}
            for fut in as_completed(futs):
                if fut.result():
                    return futs[fut]
        return None

    def _gethost(self):
        # 惰性重探测：代理/网络未就绪时 init 里 _best_host() 会返回 None，
        # 刷新源时不会再跑 init，若这里不重试，self.host 会一直是 None，列表永远空。
        if not self.host:
            self.host = self._best_host()
        return self.host

    def _get(self, url, timeout=10):
        try:
            r = self.s.get(url, headers=self.headers, proxies=self.proxies, timeout=timeout, allow_redirects=True)
            return r.text if r.status_code == 200 else ""
        except Exception:
            return ""

    # ---------- 首页 / 分类 ----------
    def homeContent(self, filter):
        classes = self.ungzip(self.ccccc)
        filters = {}
        for i in classes:
            fid = i['type_id']
            f = self.ungzip(self.fts)
            if 'cn/actresses' in fid:
                f += self.ungzip(self.actfts)
            filters[fid] = f
        html = pq(self._get("%s/cn" % self._gethost()))
        return {
            'class': classes,
            'filters': filters,
            'list': self.getlist(html('.grid-cols-2.md\\:grid-cols-3 .thumbnail.group')),
        }

    def categoryContent(self, tid, pg, filter, extend):
        params = {'page': pg}
        if tid == 'cn/actresses':
            params.update({k: extend.get(k, '') for k in ('height', 'cup', 'debut', 'age', 'sort')})
        elif tid not in ('cn/genres', 'cn/makers'):
            params.update({'filters': extend.get('filters', ''), 'sort': extend.get('sort', '')})
        params = {k: v for k, v in params.items() if v}
        url = requests.Request(url="%s/%s" % (self._gethost(), tid), params=params).prepare().url
        data = pq(self._get(url))
        if tid in ('cn/genres', 'cn/makers'):
            videos = self.gmsca(data)
        elif tid == 'cn/actresses':
            videos = self.actca(data)
        else:
            videos = self.getlist(data('.grid-cols-2.md\\:grid-cols-3 .thumbnail.group'))
        return {'list': videos, 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}

    # ---------- 详情 ----------
    def detailContent(self, ids):
        vid = ids[0]
        # 搜索结果链接不带 /cn，会返回繁体页导致下方中文标签匹配不到，统一补 /cn 走简体页
        if '/cn/' not in vid and not vid.startswith('cn/'):
            vid = 'cn/' + vid
        url = "%s/%s" % (self._gethost(), vid)
        v = pq(self._get(url))
        urls = self.execute_js(v('body script').text()) or ("嗅探$%s" % url)
        c = v('.space-y-2 .text-secondary')
        ac, dt, cd, bq = [], [], [], ['点击展开↓↓↓\n']
        for i in c.items():
            label = i('span').text()
            links = ['[a=cr:' + json.dumps({'id': j.attr('href').split('/', 3)[-1], 'name': j.text()}) + '/]' + j.text() + '[/a]' for j in i('a').items()]
            if re.search(r"导演:|发行商:", label):
                dt += links
            elif re.search(r"女优:", label):
                ac += links
            elif re.search(r"类型:|系列:", label):
                bq += links
            elif re.search(r"标籤:", label):
                cd += links
        vod = {
            'type_name': c.eq(-3)('a').text(),
            'vod_year': c.eq(0)('time').text(),
            'vod_remarks': ' '.join(cd),
            'vod_actor': ' '.join(ac),
            'vod_director': ' '.join(dt),
            'vod_content': "%s\n%s" % (' '.join(bq), v('.text-secondary.break-all').text()),
        }
        names, plist = [], []
        for k, val in (('MissAV', urls), ('Recommend', self.getfov(vid))):
            if val:
                names.append(k)
                plist.append(val)
        vod['vod_play_from'] = '$$$'.join(names)
        vod['vod_play_url'] = '$$$'.join(plist)
        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        url = requests.Request(url="%s/search/%s" % (self._gethost(), key), params={'page': pg}).prepare().url
        data = pq(self._get(url))
        return {'list': self.getlist(data('.grid-cols-2.md\\:grid-cols-3 .thumbnail.group')), 'page': pg}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        p = 0 if '.m3u8' in id else 1
        if flag == 'Recommend':
            vid = id if (id.startswith('cn/') or '/cn/' in id) else 'cn/' + id
            url = "%s/%s" % (self._gethost(), vid)
            try:
                v = pq(self._get(url))
                url = self.execute_js(v('body script').text())
                if not url:
                    raise Exception("没有找到地址")
                p, id = 0, url.split('$')[-1]
            except Exception:
                p, id = 1, url
        return {'parse': p, 'url': id if p else "%s%s" % (self.plp, id), 'header': self.headers}

    # ---------- 列表解析 ----------
    def getlist(self, data):
        videos, seen = [], set()
        for i in data.items():
            a = i('.overflow-hidden.shadow-lg a').eq(0)
            href, name = a.attr('href'), i('.text-secondary').text()
            if not href or href in seen:
                continue
            seen.add(href)
            videos.append({
                'vod_id': href.split('/', 3)[-1],
                'vod_name': name,
                'vod_pic': self.plp + (a('img').attr('data-src') or ''),
                'vod_remarks': i('.overflow-hidden.shadow-lg a span').text(),
                'style': {"type": "rect", "ratio": 1.33},
            })
        return videos

    def gmsca(self, data):
        acts = []
        for i in data('.grid.grid-cols-2.md\\:grid-cols-3 div').items():
            id = i('.text-nord13').attr('href')
            acts.append({
                'vod_id': id.split('/', 3)[-1] if id else id,
                'vod_name': i('.text-nord13').text(),
                'vod_pic': '',
                'vod_remarks': i('.text-nord10').text(),
                'vod_tag': 'folder',
                'style': {"type": "rect", "ratio": 2},
            })
        return acts

    def actca(self, data):
        acts = []
        for i in data('.max-w-full ul li').items():
            id = i('a').attr('href')
            acts.append({
                'vod_id': id.split('/', 3)[-1] if id else id,
                'vod_name': i('img').attr('alt'),
                'vod_pic': self.plp + (i('img').attr('src') or ''),
                'vod_year': i('.text-nord10').eq(-1).text(),
                'vod_remarks': i('.text-nord10').eq(0).text(),
                'vod_tag': 'folder',
                'style': {"type": "oval"},
            })
        return acts

    # ---------- 推荐 ----------
    def getfov(self, url):
        try:
            h = self.headers.copy()
            h['Referer'] = '%s/%s/' % (self._gethost(), url)
            t = str(int(time.time()))
            params = {
                'frontend_timestamp': t,
                'frontend_sign': self.getsign("/missav-default/batch/?frontend_timestamp=%s" % t),
            }
            uid = str(uuid.uuid4())

            def req(count, scenario):
                return {
                    'method': 'POST',
                    'path': '/recomms/items/%s/items/' % url.split('/')[-1],
                    'params': {
                        'targetUserId': uid, 'count': count, 'scenario': scenario,
                        'returnProperties': True,
                        'includedProperties': ['title_cn', 'duration', 'has_chinese_subtitle', 'has_english_subtitle', 'is_uncensored_leak', 'dm'],
                        'cascadeCreate': True,
                    },
                }
            json_data = {
                'requests': [req(13, 'desktop-watch-next-side'), req(12, 'desktop-watch-next-bottom')],
                'distinctRecomms': True,
            }
            data = requests.post('%s/missav-default/batch/' % self.xhost, params=params, headers=h, json=json_data, proxies=self.proxies).json()
            vdata = []
            for i in data:
                for j in i['json'].get('recomms', []):
                    if j.get('id'):
                        vdata.append("%s$%s" % (j['values']['title_cn'], j['id']))
            return '#'.join(vdata)
        except Exception as e:
            self.log("获取推荐失败: %s" % e)
            return ''

    def getsign(self, text):
        h = HMAC.new(b'Ikkg568nlM51RHvldlPvc2GzZPE9R4XGzaH9Qj4zK9npbbbTly1gj9K4mgRn0QlV', digestmod=SHA1)
        h.update(text.encode('utf-8'))
        return h.hexdigest()

    def ungzip(self, data):
        return json.loads(gzip.decompress(b64decode(data)).decode('utf-8'))

    def execute_js(self, jstxt):
        m = re.search(r"eval\(function\(p,a,c,k,e,d\).*?return p}(.*?)\)\)", jstxt)
        if not m:
            return None
        try:
            from com.whl.quickjs.wrapper import QuickJSContext
            ctx = QuickJSContext.create()
            result = ctx.evaluate("%s\nsource" % m.group(0))
            ctx.destroy()
            return "多画质$%s" % result
        except Exception as e:
            self.log("执行失败: %s" % e)
            return None
