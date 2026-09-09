# -*- coding: utf-8 -*-
# 小红薯APP（短剧/短视频站，接口加密：JWT头 AES-CBC 解密 + 时间戳md5签名）
#
# 域名机制（2026-09-06 反编译 小红薯.apk 重新梳理）：
#   稳定下发导航 = https://d2g44ha76f4f11.cloudfront.net/xhs.json
#       返回 JSON 数组，直接就是当前可用 API 域名（随机子域 + .work 后缀）：
#       ["https://rYbni23.el4g8wdk.work", "https://I4rr0Ru.5vrc89bh.work", "https://7IwoPvF.zxse3k8e.work"]
#   拿不到导航时，退回「后缀池 + 随机子域」兜底。traveler 下发 token / imgDomain / signKey。
#
# 播放线路（与推特APP 同框架）：
#   详情 getVideoById 返回 videoUrl(lsjm3u8 路径) + authKey + cdnList（专线-HW / 专线-MN 两个 CDN 域名）。
#   播放接口 /api/m3u8/decode/authPath?auth_key={authKey}&path={videoUrl}&domain={专线域名}，靠 domain 选线路：
#     专线-HW = bdkabs.com   专线-MN = wosvoj.com（随机子域，cdnList 动态下发）
#   分片是纯 MPEG-TS、AES-128 加密，命名 {videoId}-m{0..N}.ts 连续递增，无注入内容。
#
# 关键点：
#   1) API 域名从 xhs.json 导航自动选；API 主机被墙，播放地址走 self.plp 转发，分片在专线域名直连。
#   2) 详情简介的可点击标签来自 videoTags（带 key），带 # 前缀，放在简介(标题)前面、空格连接不换行。
from base.spider import Spider
import json, random, string, time, requests, hashlib
from base64 import b64decode
from urllib.parse import quote, unquote, parse_qs
from Crypto.Cipher import AES

class Spider(Spider):
    def getName(self):
        return '小红薯APP'

    def init(self, extend="{}"):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        # ---- 代理三行（照抄，由 extend 传，没传就直连）----
        self.plp = config.get('plp', '')       # 播放器/封面/播放地址 URL 前缀
        self.proxy = config.get('proxy', {})   # 内部请求代理

        # 稳定下发导航（xhs.json，返回当前可用 API 域名数组）
        self.navs = [
            'https://d2g44ha76f4f11.cloudfront.net/xhs.json',
            'https://tc-jp-alijs-1375272368.cos.ap-tokyo.myqcloud.com/xhs.json',
        ]
        # 兜底后缀池（导航全挂时用，活跃的放最前；拿到新后缀往这里追加即可）
        self.hs = ['el4g8wdk', '5vrc89bh', 'zxse3k8e', '7bd6g1n', '85bx047', '8vje4ee', '9ij77hy']
        self.ua = 'Mozilla/5.0 (Linux; Android 11; M2012K10C Build/RP1A.200720.011; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/87.0.4280.141 Mobile Safari/537.36;SuiRui/xhs/ver=1.2.6'
        self.did = self._did()
        self.session = requests.Session()
        self.token = ''
        self.phost = ''   # 图片域名（traveler 动态下发）
        self.host = ''    # API 主域名
        self.api_cache = {}
        self.img_cache = {}
        self.class_cache = []
        self._gethost()   # 尝试一次，失败不固化（代理起来后刷新即恢复）

    # ---- 惰性域名探测：host 空则重测 ----
    def _gethost(self):
        if not self.host:
            self.token, self.phost, self.host = self._token()
        return self.host

    def homeContent(self, filter):
        data = self._api('/api/video/queryClassifyList?mark=4')
        classes = []
        for k in data.get('data', []) if isinstance(data, dict) else []:
            tid = str(k.get('classifyId', ''))
            name = k.get('classifyTitle', '')
            if tid and name:
                classes.append({'type_name': name, 'type_id': tid})
        if not classes:
            classes = [{'type_name': '推荐', 'type_id': '0'}]
        self.class_cache = classes
        res = {'class': classes, 'filters': {}}
        if classes:
            res['list'] = self.categoryContent(classes[0]['type_id'], '1', False, {}).get('list', [])
        return res

    def homeVideoContent(self):
        tid = self.class_cache[0]['type_id'] if self.class_cache else '0'
        return {'list': self.categoryContent(tid, '1', False, {}).get('list', [])}

    # 支持三类：裸分类id / tag_标签key / author_作者id
    def categoryContent(self, tid, pg, filter, extend):
        pg = str(pg or '1')
        tid = str(tid or '')
        params = {'videoMark': '4', 'page': pg, 'pageSize': '20'}
        if tid.startswith('tag_'):
            params['videoTagKey'] = tid[4:]
        elif tid.startswith('author_'):
            params['userId'] = tid[7:]
        elif tid and tid != '0':
            params['classifyId'] = tid
        path = '/api/short/video/getShortVideos?' + '&'.join('%s=%s' % (k, v) for k, v in params.items())
        data = self._api(path)
        arr = data.get('data', []) if isinstance(data.get('data', []), list) else data.get('list', [])
        return {'list': self._items(arr), 'page': int(pg), 'pagecount': 9999, 'limit': 20, 'total': 999999}

    def detailContent(self, ids):
        raw = str(ids[0])
        pp = raw.split('?', 1)
        vid = pp[0]
        data = self._api('/api/video/getVideoById?videoId=%s' % vid)
        if not data or not data.get('title'):
            # 搜索结果的动态视频（hex ID）拿不到详情，用 vod_id 里编码的标题兜底
            title = unquote(pp[1]) if len(pp) > 1 else vid
            return {'list': [{'vod_id': raw, 'vod_name': title, 'vod_play_from': '小红书官方', 'vod_play_url': title + '$'}]}
        name = data.get('title') or vid
        auth = data.get('authKey', '')
        path = data.get('videoUrl', '') or data.get('playPath', '') or data.get('url', '')
        # 两条专线线路（cdnList：专线-HW / 专线-MN，靠 domain 参数选线路）
        play_lines = []
        for c in (data.get('cdnList') or []):
            dom = (c.get('domain') or '').rstrip('/').replace('https://', '').replace('http://', '')
            if c.get('status') and dom and auth and path:
                play_lines.append((c.get('line') or '线路', 'auth_key=%s&path=%s&domain=%s' % (auth, path, dom)))
        if not play_lines and auth and path:
            play_lines.append(('播放', 'auth_key=%s&path=%s' % (auth, path)))

        # 分类（classify 对象）
        cls = data.get('classify') or {}
        type_name = cls.get('classifyTitle', '') if isinstance(cls, dict) else ''

        # 作者（可点击 → author_<userId>）
        uid = data.get('userId', '')
        nick = data.get('nickName') or ''
        actor = self._cr('author_%s' % uid, nick or '作者%s' % uid) if uid else ''

        # 标签（可点击 → tag_<videoTagKey>，带 # 前缀）
        tags = data.get('videoTags') or []
        tag_parts = []
        if isinstance(tags, list):
            for t in tags:
                if isinstance(t, dict) and t.get('videoTagKey'):
                    tag_parts.append(self._tag('tag_%s' % t['videoTagKey'], t.get('videoTagValue') or ''))
        if not tag_parts:
            tt = data.get('tagTitles') or []
            if isinstance(tt, list):
                tag_parts = ['#' + str(x) for x in tt if x]
        tag_html = ' '.join(tag_parts)
        # 简介：# 标签放前面、空格连接（不换行），再换行接标题
        content = (tag_html + '\n' + name) if tag_html else name

        # 年份
        year = ''
        dt = data.get('reviewDate') or data.get('createdAt') or ''
        if dt:
            year = str(dt)[:4]

        # 计数 + 时长
        watch = self._num(data.get('fakeWatchNum'))
        likes = self._num(data.get('fakeLikes'))
        play_time = self._time(data.get('playTime'))
        remarks = play_time
        if watch:
            remarks = (remarks + ' 观看' + watch) if remarks else ('观看' + watch)
        if likes:
            remarks = remarks + ' 赞' + likes

        score = data.get('score')

        vod = {
            'vod_id': vid,
            'vod_name': name,
            'vod_pic': self._proxy(data.get('coverImg', ''), 'img'),
            'type_name': type_name,
            'vod_year': year,
            'vod_actor': actor,
            'vod_content': content,
            'vod_remarks': remarks,
            'vod_score': str(score) if score is not None else '',
            'vod_play_from': '$$$'.join([p[0] for p in play_lines]) if play_lines else (nick or '小红书官方'),
            'vod_play_url': '$$$'.join([name + '$' + p[1] for p in play_lines]) if play_lines else (name + '$' + path),
        }
        return {'list': [vod]}

    def searchContent(self, key, quick, pg='1'):
        pg = str(pg or '1')
        data = self._api('/api/search/keyWord?pageSize=20&page=%s&searchWord=%s&searchType=1' % (pg, quote(key)))
        arr = []
        # 视频结果（videoList，数字 videoId）
        vl = data.get('videoList') or []
        if isinstance(vl, list):
            for v in vl:
                vid = str(v.get('videoId') or '')
                if not vid:
                    continue
                pic = v.get('coverImg') or ''
                if isinstance(pic, list):
                    pic = pic[0] if pic else ''
                arr.append({'vod_id': vid, 'vod_name': v.get('title') or vid,
                            'vod_pic': self._proxy(pic, 'img'), 'vod_remarks': self._time(v.get('playTime'))})
        # 动态结果（dynamicList 里的 video 字段是视频，id 是 hex，无法直接调 getVideoById）
        if not arr:
            for d in (data.get('dynamicList') or []):
                v = d.get('video') or {}
                if not isinstance(v, dict) or not v.get('id'):
                    continue
                vid = str(v.get('id'))
                title = v.get('title') or d.get('title') or vid
                pic = v.get('coverImg') or ''
                if isinstance(pic, list):
                    pic = pic[0] if pic else ''
                # 把标题编码进 vod_id，详情时 hex 拿不到详情也能显示标题
                arr.append({'vod_id': vid + '?' + quote(title), 'vod_name': title,
                            'vod_pic': self._proxy(pic, 'img'),
                            'vod_remarks': self._time(v.get('playTime') or d.get('playTime'))})
        return {'list': arr, 'page': int(pg), 'pagecount': 9999, 'limit': 20, 'total': 999999}

    def playerContent(self, flag, id, vipFlags):
        h = self._headers()
        if h.get('aut'):
            h['Authorization'] = h.pop('aut')
        if 'deviceid' in h:
            del h['deviceid']
        host = self._gethost()
        # decode 接口返回 m3u8 文本；接口在主域名（被墙），必须加 plp 走代理。
        # m3u8 内部分片/enc.key 是 CDN 动态域名，国内直连可达，无需代理。
        url = host + '/api/m3u8/decode/authPath?' + id if host and id.startswith('auth_key=') else id
        return {'parse': 0, 'playUrl': '', 'url': self.plp + url, 'header': h}

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

    # ---- 可点击标签封装 ----
    def _cr(self, href, name):
        return '[a=cr:%s/]%s[/a]' % (json.dumps({'id': href, 'name': name}, ensure_ascii=False), name)

    # ---- 带 # 前缀的可点击标签 ----
    def _tag(self, href, name):
        return '[a=cr:%s/]#%s[/a]' % (json.dumps({'id': href, 'name': name}, ensure_ascii=False), name)

    def _items(self, arr):
        res = []
        for k in arr or []:
            vid = str(k.get('videoId') or k.get('id') or '')
            if not vid:
                continue
            res.append({
                'vod_id': vid,
                'vod_name': k.get('title') or vid,
                'vod_pic': self._proxy(k.get('coverImg', ''), 'img'),
                'vod_remarks': self._time(k.get('playTime')),
                'style': {'type': 'rect', 'ratio': 1.33},
            })
        return res

    def _api(self, path):
        host = self._gethost()
        if not host:
            return {}
        url = host + path if path.startswith('/') else path
        if url in self.api_cache:
            return self.api_cache[url]
        try:
            r = self.session.get(url, headers=self._headers(), proxies=self.proxy, timeout=12, verify=False)
            j = r.json()
            data = self._aes(j.get('encData', '')) if isinstance(j, dict) and j.get('encData') else j
            if len(self.api_cache) > 80:
                self.api_cache.clear()
            self.api_cache[url] = data
            return data
        except Exception:
            return {}

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

    def _token(self):
        # 1) 导航站拿域名（xhs.json 下发）
        domains = self._nav_domains()
        # 2) 兜底：后缀池 + 随机子域
        if not domains:
            for h in self.hs:
                domains.append('https://%s.%s.work' % (''.join(random.choices(string.ascii_lowercase + string.digits, k=8)), h))
        for domain in domains:
            for _ in range(2):
                try:
                    sign, t = self._sign()
                    hd = {'User-Agent': self.ua, 'deviceid': self.did, 't': t, 's': sign}
                    body = {'deviceId': self.did, 'tt': 'U', 'code': '', 'chCode': 'dafe13'}
                    r = self.session.post(domain + '/api/user/traveler', json=body, headers=hd, proxies=self.proxy, timeout=8, verify=False)
                    d = r.json().get('data', {})
                    if d.get('token') and d.get('imgDomain'):
                        return d.get('token', ''), d.get('imgDomain', ''), domain
                except Exception:
                    continue
        return '', '', ''

    def _headers(self):
        sign, t = self._sign()
        h = {'User-Agent': self.ua, 'deviceid': self.did, 't': t, 's': sign}
        if self.token:
            h['aut'] = self.token
        return h

    def _sign(self):
        t = str(int(time.time() * 1000))
        return self._md5(t[3:8]), t

    def _aes(self, word):
        try:
            key = b64decode('SmhiR2NpT2lKSVV6STFOaQ==')
            raw = AES.new(key, AES.MODE_CBC, key).decrypt(b64decode(word))
            n = raw[-1] if raw else 0
            if 1 <= n <= 16:
                raw = raw[:-n]
            return json.loads(raw.decode('utf-8'))
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

    def _num(self, n):
        try:
            n = int(n or 0)
        except Exception:
            return ''
        if n >= 10000:
            return '%.1f万' % (n / 10000.0)
        return str(n)

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
            r = self.session.get(self._img_url(u), headers={'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 11; M2012K10C Build/RP1A.200720.011)'}, proxies=self.proxy, timeout=15, verify=False)
            body = self._img_decode(r.content, 100, '2020-zq3-888')
            ct = (r.headers.get('Content-Type') or 'image/jpeg').split(';')[0]
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
