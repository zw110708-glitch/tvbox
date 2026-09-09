# -*- coding: utf-8 -*-
# 推特APP —— OK影视 Python 爬虫源（catvod/pg.jar，Python 3.8）
#
# 域名机制（2026-09-06 反编译 推特APP.apk 重新梳理）：
#   稳定下发导航 = https://d16r99kkdgk8ln.cloudfront.net/tt.json
#       返回 JSON 数组，直接就是当前可用的 API 域名（随机子域 + .work 后缀）：
#       ["https://84kXg6S.jed0sgcs.work", "https://rFmsl8J.f01s6ypx.work", "https://U5R2U8k.ixz4o2cb.work"]
#   拿不到导航时，退回「后缀池 + 随机子域」并发探活兜底。
#   traveler 接口下发 token / imgDomain / signKey（signKey 用于 /api/m3u8/play 签名）。
#
# 播放线路（2026-09-06 二刷 APK + 实测确认）：
#   APP 里的「专线-HW / 专线-MN」是 /api/video/cdn/cdnList 下发的两个 CDN 专线域名：
#     专线-HW = chdkue.com（随机子域）   专线-MN = wrdykj.com（随机子域）
#   播放地址走 /api/m3u8/play?path=&token=&ts=&nonce=&sign=&domain={专线域名}&authKey=
#     sign = HMAC-SHA256(signKey, path+token+ts+nonce+"domain="+domain)
#   两条线路返回的 m3u8 都是「普通 videoUrl(jpd)」，分片是纯 MPEG-TS、AES-128-CBC(iv=0) 加密，
#   分片命名 {videoId}.{0..N}.ts 连续递增，无任何注入内容；专线域名不绑 IP、可直连或走 Clash。
#
# 关键点：
#   1) 主 API 域名从 tt.json 导航自动选，拿到新后缀往 self.suffixes 加一个即可兜底。
#   2) can/watch 返回 playPath + videoUrl + authKey。API 主机被墙，播放地址走 self.plp 转发。
#   3) 视频有「普通(videoUrl/jpd)」与「HEVC(hevcVideoUrl/lsjm3u8)」两档清晰度；
#      HEVC 档实测返回 error 1010（服务端已失效），故两条专线都用普通 videoUrl。
#   4) 详情简介的可点击标签来自列表项 tagTitles，带 # 前缀，放在简介(标题)前面、空格连接不换行。
from base.spider import Spider
import json, random, string, time, requests, hashlib, hmac, uuid, concurrent.futures
from base64 import b64decode
from urllib.parse import quote, unquote, parse_qs
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


class Spider(Spider):
    def getName(self):
        return '推特APP'

    def init(self, extend=""):
        try:
            config = json.loads(extend) if isinstance(extend, str) and extend else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}

        # ---- 代理三行（照抄，由 extend 传，没传就直连）----
        self.plp = config.get('plp', '')       # 播放器/封面/播放地址 URL 前缀
        self.proxy = config.get('proxy', {})   # 内部请求代理

        self.ua = 'Mozilla/5.0 (Linux; Android 11; M2012K10C Build/RP1A.200720.011; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/87.0.4280.141 Mobile Safari/537.36;SuiRui/twitter/ver=1.4.4'
        self.did = self._did()
        self.session = requests.Session()
        self.token = ''
        self.signkey = ''     # /api/m3u8/play 的 HMAC-SHA256 签名密钥（traveler 下发）
        self.phost = ''       # 图片域名（traveler 下发）
        self.host = ''        # 主 API 域名，不在这里硬探测，先留空
        self.api_cache = {}
        self.img_cache = {}
        self._probed = False
        self._cdn_cache = []   # 专线线路列表（cdnList 下发，缓存）

        # 稳定下发导航（tt.json，返回当前可用 API 域名数组）
        self.navs = [
            'https://d16r99kkdgk8ln.cloudfront.net/tt.json',
            'https://tc-jp-alijss-1375272368.cos.ap-tokyo.myqcloud.com/tt.json',
            'https://tt.kjbiin.xyz',
            'https://tt.pisemx.xyz',
            'https://tt.un7zbn.xyz',
        ]
        # 兜底后缀池（导航全挂时用，活跃的放最前；拿到新后缀往这里追加即可）
        self.suffixes = ['jed0sgcs', 'f01s6ypx', 'ixz4o2cb', 'bqeaaxzplt', 'hfbtpixjso', 'wcyfhknomg', 'pdcqllfomw', 'alxhzjvean']

        self._gethost()        # 尝试一次，失败也不抛

    # ---- 惰性探测：host 空/无 token 就重测（代理起来后刷新即恢复）----
    def _gethost(self):
        if self.host and self.token:
            return self.host
        r = self._probe()
        if r:
            self.host, self.token, self.phost, self.signkey = r
            self._probed = True
        return self.host or ''

    # ---- 域名导航：拉 tt.json 拿可用域名数组 ----
    def _nav_domains(self):
        pool = []
        for nav in self.navs:
            try:
                r = self.session.get(nav, timeout=8, verify=False, proxies=self.proxy)
                arr = r.json()
                for d in arr:
                    if isinstance(d, str) and d.startswith('http'):
                        d = d.rstrip('/')
                        if d not in pool:
                            pool.append(d)
                if pool:
                    break
            except Exception:
                continue
        return pool

    # ---- 并发探活：导航域名优先，全挂则退回后缀池随机子域 ----
    def _probe(self):
        domains = self._nav_domains()
        if not domains:
            for suf in self.suffixes:
                sub = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
                domains.append('https://%s.%s.work' % (sub, suf))

        def one(dom):
            tok, img, sk = self._traveler(dom)
            if tok:
                return dom, tok, img, sk
            return None
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(domains)) as ex:
                futures = [ex.submit(one, d) for d in domains]
                for fut in concurrent.futures.as_completed(futures):
                    r = fut.result()
                    if r:
                        return r
        except Exception:
            pass
        return None

    # ---- traveler：拿 token + 图片域名 + 签名密钥 ----
    def _traveler(self, domain):
        sign, t = self._sign()
        hd = {'User-Agent': self.ua, 'Accept': 'application/json', 'deviceid': self.did, 't': t, 's': sign}
        body = {'deviceId': self.did, 'tt': 'U', 'code': '##X-4m6Goo4zzPi1hF##', 'chCode': 'tt09'}
        try:
            r = self.session.post(domain + '/api/user/traveler', json=body, headers=hd, timeout=10, verify=False, proxies=self.proxy)
            d = r.json().get('data', {})
            return d.get('token', ''), d.get('imgDomain', ''), d.get('signKey', '')
        except Exception:
            return '', '', ''

    # ---- 专线线路列表（cdnList 下发：专线-HW / 专线-MN，带各自 CDN 域名）----
    def _cdns(self):
        if self._cdn_cache:
            return self._cdn_cache
        try:
            data = self._api('/api/video/cdn/cdnList')
            lines = []
            for c in data.get('data', []):
                dom = (c.get('domain', '') or '').rstrip('/')
                name = c.get('line', '')
                if c.get('status') and dom and name:
                    dom = dom.replace('https://', '').replace('http://', '')
                    lines.append({'line': name, 'domain': dom})
            if lines:
                self._cdn_cache = lines
        except Exception:
            pass
        return self._cdn_cache

    def homeContent(self, filter):
        data = self._api('/api/video/classifyList')
        classes = [{'type_name': '精选', 'type_id': 'jx'}]
        for i in data.get('data', []):
            tid = str(i.get('classifyId', ''))
            name = i.get('classifyTitle', '')
            if tid and name:
                classes.append({'type_name': name, 'type_id': tid})
        sort = [{'key': 'fl', 'name': '分类', 'value': [{'n': '最近更新', 'v': '1'}, {'n': '最多播放', 'v': '2'}, {'n': '好评榜', 'v': '3'}]}]
        filters = {}
        for c in classes:
            if c['type_id'] != 'jx':
                filters[c['type_id']] = sort
        filters['jx'] = [{'key': 'type', 'name': '精选', 'value': [{'n': '日榜', 'v': '1'}, {'n': '周榜', 'v': '2'}, {'n': '月榜', 'v': '3'}, {'n': '总榜', 'v': '4'}]}]
        return {'class': classes, 'filters': filters}

    def homeVideoContent(self):
        return {'list': self.categoryContent('jx', '1', False, {'type': '1'}).get('list', [])}

    def categoryContent(self, tid, pg, filter, extend):
        pg = str(pg or '1')
        ext = extend or {}
        tid = str(tid)
        if tid.startswith('tag:'):
            # 点标签 → 按标签搜索视频
            path = '/api/video/queryVideoByTag?pageSize=20&page=%s&videoTagName=%s' % (pg, quote(tid[4:]))
        elif tid == 'jx':
            path = '/api/video/getRankVideos?pageSize=20&page=%s&type=%s' % (pg, ext.get('type', '1'))
        elif 'click' in tid:
            path = '/api/video/queryPersonVideoByType?pageSize=20&page=%s&userId=%s' % (pg, tid.replace('click', ''))
        else:
            path = '/api/video/queryVideoByClassifyId?pageSize=20&page=%s&classifyId=%s&sortType=%s' % (pg, tid, ext.get('fl', '1'))
        data = self._api(path)
        arr = data.get('data', []) if isinstance(data.get('data', []), list) else data.get('videoList', [])
        return {'list': self._items(arr, 'click' in tid), 'page': int(pg), 'pagecount': 9999, 'limit': 20, 'total': 999999}

    def detailContent(self, array):
        raw = str(array[0])
        click = 'click' in raw
        pp = raw.replace('click', '').split('?', 3)
        vid = pp[0] if len(pp) > 0 else raw
        uid = pp[1] if len(pp) > 1 else ''
        name = unquote(pp[2]) if len(pp) > 2 else '推特APP'
        tagstr = unquote(pp[3]) if len(pp) > 3 else ''
        tags = [t for t in tagstr.split('|') if t] if tagstr else []

        data = self._api('/api/video/can/watch?videoId=%s' % vid)
        play_path = data.get('playPath', '') or data.get('url', '') or data.get('playUrl', '')
        video_url = data.get('videoUrl', '')
        auth_key = data.get('authKey', '')

        # 作者（可点击进 TA 的主页）；点击进来的不再可点，避免死循环
        director = name
        if not click and uid:
            director = '[a=cr:%s/]%s[/a]' % (json.dumps({'id': uid + 'click', 'name': name}, ensure_ascii=False), name)

        # 简介：# 标签放前面、空格连接（不换行），再换行接标题
        tag_html = ' '.join([self._tag(t) for t in tags])
        content = (tag_html + '\n' + name) if tag_html else name

        # 两条播放线路：专线-HW / 专线-MN（cdnList 下发的专线域名 + /api/m3u8/play 签名）
        lines = self._play_lines(video_url, play_path, auth_key)
        froms = [p[0] for p in lines]
        urls = [name + '$' + p[1] for p in lines]
        play_from = '$$$'.join(froms) if froms else '直连'
        play_url = '$$$'.join(urls) if urls else (name + '$' + play_path)

        vod = {
            'vod_id': raw,
            'vod_name': name,
            'vod_pic': '',
            'vod_director': director,
            'vod_content': content,
            'vod_play_from': play_from,
            'vod_play_url': play_url
        }
        return {'list': [vod]}

    def searchContent(self, key, quick, pg='1'):
        data = self._api('/api/search/keyWord?pageSize=20&page=%s&searchWord=%s&searchType=1' % (pg, quote(key)))
        return {'list': self._items(data.get('videoList', []), False), 'page': int(pg), 'pagecount': 9999, 'limit': 20, 'total': 999999}

    def playerContent(self, flag, id, vipFlags):
        # 播放地址是 API 主机上的 /api/m3u8/play 或 decode 路由，API 主机被墙，必须走 plp 转发
        return {'parse': 0, 'playUrl': '', 'url': self.plp + id, 'header': self._headers()}

    def localProxy(self, param):
        tp, u = self._proxy_param(param)
        if not u:
            return [404, 'text/plain', '']
        ct, body = self._img_asset(u)
        return [200, ct or 'image/jpeg', body]

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    # ---- 可点击 # 标签 ----
    def _tag(self, t):
        return '[a=cr:%s/]#%s[/a]' % (json.dumps({'id': 'tag:' + t, 'name': t}, ensure_ascii=False), t)

    # ---- 组装播放线路：专线-HW / 专线-MN（cdnList），兜底 decode 路由 / playPath ----
    def _play_lines(self, video_url, play_path, auth_key):
        res = []
        # 1) 专线线路（cdnList 下发的专线域名，走 /api/m3u8/play 签名）
        for ln in self._cdns():
            u = self._play_url(video_url, ln['domain'], auth_key)
            if u:
                res.append((ln['line'], u))
        # 2) 兜底：decode 路由（无需签名，decode=MN、decode/dynamic=HW）
        if not res and video_url:
            host = self._gethost()
            if host:
                res.append(('专线-MN', host + '/api/m3u8/decode?path=' + quote(video_url, safe='')))
                res.append(('专线-HW', host + '/api/m3u8/decode/dynamic?path=' + quote(video_url, safe='')))
        # 3) 最后兜底：playPath 直连
        if not res and play_path:
            res.append(('直连', play_path))
        return res

    # ---- /api/m3u8/play 签名播放地址（HMAC-SHA256，signKey 由 traveler 下发）----
    def _play_url(self, path, cdn, auth_key):
        if not path or not self.signkey:
            return ''
        host = self._gethost()
        if not host:
            return ''
        try:
            ts = str(int(time.time()))
            nonce = str(uuid.uuid4())
            signstr = path + self.token + ts + nonce
            if cdn:
                signstr += 'domain=' + cdn
            sg = hmac.new(self.signkey.encode('utf-8'), signstr.encode('utf-8'), hashlib.sha256).hexdigest()
            u = host + '/api/m3u8/play?path=' + quote(path, safe='') + '&token=' + quote(self.token, safe='') + '&ts=' + ts + '&nonce=' + nonce + '&sign=' + sg
            if cdn:
                u += '&domain=' + quote(cdn, safe='')
            if auth_key:
                u += '&authKey=' + quote(auth_key, safe='')
            return u
        except Exception:
            return ''

    # ---- 列表项 ----
    def _items(self, arr, clicked=False):
        res = []
        for k in arr or []:
            cover = k.get('coverImg') or []
            pic = cover[0] if isinstance(cover, list) and cover else cover if isinstance(cover, str) else ''
            vid = str(k.get('videoId', ''))
            uid = str(k.get('userId', ''))
            nick = str(k.get('nickName', ''))
            if not vid:
                continue
            tags = k.get('tagTitles') or []
            tagstr = '|'.join([str(t) for t in tags]) if isinstance(tags, list) else ''
            vod_id = '%s?%s?%s?%s%s' % (vid, uid, quote(nick), quote(tagstr), 'click' if clicked else '')
            res.append({
                'vod_id': vod_id,
                'vod_name': k.get('title') or nick or vid,
                'vod_pic': self._proxy(pic, 'img'),
                'vod_remarks': self._time(k.get('playTime')),
                'style': {'type': 'rect', 'ratio': 1.33}
            })
        return res

    # ---- 统一 API 请求：走 proxy，host 空则重测，失败清空自愈 ----
    def _api(self, path, post=None):
        host = self._gethost()
        if not host:
            return {}
        url = host + path if path.startswith('/') else path
        key = ('POST:' if post is not None else 'GET:') + url
        if post is not None:
            key += json.dumps(post, sort_keys=True, ensure_ascii=False)
        if key in self.api_cache:
            return self.api_cache[key]
        try:
            if post is not None:
                r = self.session.post(url, json=post, headers=self._headers(), timeout=12, verify=False, proxies=self.proxy)
            else:
                r = self.session.get(url, headers=self._headers(), timeout=12, verify=False, proxies=self.proxy)
            j = r.json()
            data = self._aes(j.get('encData', '')) if j.get('encData') else j
            if len(self.api_cache) > 80:
                self.api_cache.clear()
            self.api_cache[key] = data
            return data
        except Exception:
            # 请求失败：域名可能挂了或 token 失效，清空后下次自动重测
            self.host = ''
            self.token = ''
            return {}

    def _headers(self):
        sign, t = self._sign()
        h = {'User-Agent': self.ua, 'deviceid': self.did, 't': t, 's': sign}
        if self.token:
            h['aut'] = self.token
        return h

    def _sign(self):
        t = str(int(time.time() * 1000))
        return self._md5(t), t

    def _aes(self, word):
        try:
            key = b64decode('SmhiR2NpT2lKSVV6STFOaQ==')
            return json.loads(unpad(AES.new(key, AES.MODE_CBC, key).decrypt(b64decode(word)), AES.block_size).decode('utf-8'))
        except Exception:
            return {}

    def _did(self):
        did = self.getCache('did')
        if not did:
            did = self._md5(str(int(time.time())))
            self.setCache('did', did)
        return did

    def _md5(self, text):
        return hashlib.md5(str(text).encode('utf-8')).hexdigest()

    def _time(self, seconds):
        try:
            s = int(seconds or 0)
            h = s // 3600
            m = s % 3600 // 60
            sec = s % 60
            return '%02d:%02d:%02d' % (h, m, sec) if h else '%02d:%02d' % (m, sec)
        except Exception:
            return ''

    # ---- 图片走本地代理（localProxy 下载 + 异或解码）----
    def _proxy(self, u, tp):
        if not u:
            return ''
        try:
            p = self.getProxyUrl()
            s = '&' if '?' in p else '?'
            return p + s + 'do=%s&type=%s&u=%s&url=%s' % (tp, tp, quote(u, safe=''), quote(u, safe=''))
        except Exception:
            return self._img_url(u)

    def _proxy_param(self, param):
        if isinstance(param, dict):
            if param.get('u') or param.get('url'):
                return param.get('do') or param.get('type') or 'img', unquote(param.get('u') or param.get('url') or '')
            q = parse_qs(param.get('query', '') or param.get('params', '') or '')
        else:
            q = parse_qs(str(param))
        return (q.get('do') or q.get('type') or ['img'])[0], unquote((q.get('u') or q.get('url') or [''])[0])

    def _img_url(self, u):
        if not u:
            return ''
        if u.startswith('http'):
            return u
        return (self.phost or '') + u

    def _img_asset(self, u):
        if u in self.img_cache:
            return self.img_cache[u]
        try:
            r = self.session.get(self._img_url(u), headers={'User-Agent': self.ua}, timeout=15, verify=False, proxies=self.proxy)
            body = self._img_decode(r.content, 100, '2020-zq3-888')
            ct = r.headers.get('Content-Type', 'image/jpeg')
            if len(self.img_cache) > 160:
                self.img_cache.clear()
            self.img_cache[u] = (ct, body)
            return ct, body
        except Exception:
            return 'text/plain', b''

    def _img_decode(self, data, length, key):
        if len(data) > 7 and (data[:3] == b'GIF' or data[:3] == b'\xff\xd8\xff' or data[1:8] == b'PNG\r\n\x1a\n'):
            return data
        kb = key.encode('utf-8')
        arr = bytearray(data)
        for i in range(min(length, len(arr))):
            arr[i] ^= kb[i % len(kb)]
        return bytes(arr)
