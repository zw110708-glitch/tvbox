# -*- coding: utf-8 -*-
import base64, json, re, sys
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    # 导航脚本：内含 zuArr 域名池 + z(区域名) + t(模块 vod/art)。
    # 全站唯一硬编码入口，其余域名（分类/播放/封面）全部从这里动态解析。
    NAV_URLS = [
        'https://6180067.xyz/cdn-tentm-Div/react-jsx-dev-runtime.js?kk=2495955t6683'
    ]
    # 封面图片 XOR 解密：(key, 解密前 N 字节)
    IMG_KEYS = [(b'2019ysapp7527', 100), (b'\x5a', 16)]

    # 9 个视频区域子分类，顺序与导航脚本 zuArr/z/t 一致；每区第一项为默认分类
    SUBCATS = [
        [('1', '全部视频'), ('13', '香蕉精品'), ('22', '制服诱惑'), ('6', '国产视频'), ('8', '清纯少女'),
         ('9', '辣妹大奶'), ('10', '女同专属'), ('11', '素人出演'), ('12', '角色扮演'), ('20', '人妻熟女'),
         ('23', '日韩剧情'), ('21', '经典伦理'), ('7', '成人动漫'), ('14', '精品二区'), ('40', '精品三区'),
         ('53', '动漫中字'), ('52', '日本无码'), ('33', '中文字幕'), ('44', '国产传媒'), ('32', '国产自拍')],
        [('1', '全部'), ('5', '热门'), ('6', '推荐'), ('7', '字幕'), ('8', '欧美'), ('9', '动漫'),
         ('10', '传媒'), ('31', '黑料'), ('55', '网黄'), ('56', '无码'), ('57', 'JK'), ('54', '国产')],
        [('66', '一区'), ('63', '日欧'), ('64', '动漫'), ('65', '无码'), ('69', '字幕'), ('70', 'P站'),
         ('68', '厂牌'), ('71', '网黄'), ('67', 'JK'), ('72', '国产'), ('73', '热门')],
        [('5', '漫画')],
        [('2', '全部'), ('13', '热门'), ('14', '字幕'), ('15', '国产'), ('16', '无码'), ('23', '直播'),
         ('34', '探花'), ('32', '网黄'), ('11', '欧美'), ('12', '韩国'), ('58', '传媒'), ('61', 'JK')],
        [('43', '全部'), ('1', '二区'), ('45', 'JK'), ('46', '中文'), ('47', '精品'), ('48', '韩国'),
         ('59', '网黄'), ('60', '国产'), ('44', '传媒')],
        [('40', '网黄UP主'), ('13', '精品二区'), ('37', '国产AV'), ('43', '探花AV'), ('49', '绿帽淫妻'),
         ('44', '国产传媒'), ('41', '福利姬'), ('39', '字幕'), ('45', '水果π'), ('42', '主播直播'),
         ('38', '欧美'), ('66', 'FC2'), ('46', '性爱教学'), ('48', '三级'), ('47', '动漫')],
        [('66', '一区'), ('63', '日欧'), ('64', '动漫'), ('65', '无码'), ('69', '字幕'), ('70', 'P站'),
         ('68', '厂牌'), ('71', '网黄'), ('67', 'JK'), ('72', '国产'), ('73', '热门')],
        [('35', '全部'), ('2', '二区'), ('30', '韩国'), ('27', '欧美'), ('40', '无码'), ('39', '字幕'),
         ('36', '传媒'), ('37', '网黄'), ('28', '黑料'), ('26', 'JK'), ('38', '国产'), ('41', '推荐')],
    ]

    def init(self, extend=''):
        cfg = {}
        if isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend)
            except:
                pass
        elif isinstance(extend, dict):
            cfg = extend
        self.proxies = cfg.get('proxies') if 'proxies' in cfg else {
            'http': 'http://127.0.0.1:10172', 'https': 'http://127.0.0.1:10172'}
        self.s = requests.Session()
        ad = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=50, max_retries=0)
        self.s.mount('http://', ad)
        self.s.mount('https://', ad)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        self._build()

    def getName(self):
        return '618导航'

    def manualVideoCheck(self):
        return False

    # ================= 域名与区域 =================
    def _build(self):
        js = None
        for u in self.NAV_URLS:
            try:
                r = self.s.get(u, headers=self.headers, timeout=8, verify=False, proxies=self.proxies)
                if r.status_code == 200 and 'zuArr' in r.text:
                    js = r.text
                    break
            except:
                pass
        if not js:
            raise RuntimeError('导航脚本不可用')
        zuArr, zones, mods = self._parse_nav(js)
        y = self._pick_y(zuArr, mods)
        self.CLASSES = []
        self._zone = {}
        for n in range(min(len(zones), len(self.SUBCATS))):
            module = mods[n] if n < len(mods) else 'vod'
            subs = self.SUBCATS[n]
            host = 'https://618%s.xyz' % zuArr[n][y]
            tid = '%s/index.php/%s/type/id/%s.html' % (host, module, subs[0][0])
            self.CLASSES.append({'type_name': zones[n], 'type_id': tid})
            self._zone[tid] = {'host': host, 'module': module, 'subs': subs}
        self._home_classes = self.CLASSES

    def _parse_nav(self, js):
        m = re.search(r'const\s+zuArr\s*=\s*(\[.*?\]);', js, re.S)
        if not m:
            raise RuntimeError('导航脚本无zuArr')
        zuArr = json.loads(m.group(1).replace("'", '"'))
        z = re.search(r",z=\[([^\]]*)\]", js)
        t = re.search(r",t=\[([^\]]*)\]", js)
        if not z or not t:
            raise RuntimeError('导航脚本无区域定义')
        zones = [x.strip().strip("'\"") for x in z.group(1).split(',')]
        mods = [x.strip().strip("'\"") for x in t.group(1).split(',')]
        return zuArr, zones, mods

    def _pick_y(self, zuArr, mods):
        # 网站导航脚本用同一个 y 给所有区选域名（for(var y=random%95, ...)），
        # 这里同样全局选一个 y，匹配网站机制、更稳定。
        # 顺序遍历（y=0 优先）：y=0 是网站主推域名、实测全通，秒级返回。
        max_y = max((len(r) for r in zuArr), default=0)
        for y in range(max_y):
            ok = True
            for n in range(min(len(zuArr), len(self.SUBCATS))):
                if y >= len(zuArr[n]):
                    ok = False
                    break
                host = 'https://618%s.xyz' % zuArr[n][y]
                module = mods[n] if n < len(mods) else 'vod'
                default = self.SUBCATS[n][0][0]
                if not self._probe(host, module, default):
                    ok = False
                    break
            if ok:
                return y
        raise RuntimeError('无可用域名')

    def _probe(self, host, module, type_id):
        try:
            u = '%s/index.php/%s/type/id/%s.html' % (host, module, type_id)
            r = self.s.get(u, headers=self.headers, timeout=4, verify=False, proxies=self.proxies)
            return r.status_code == 200 and len(r.text) >= 500
        except:
            return False

    # ================= 首页 =================
    def homeContent(self, filter):
        if not filter:
            return {'class': self.CLASSES, 'filters': {}, 'list': []}
        filters = {}
        for c in self.CLASSES:
            tid = c['type_id']
            subs = self._zone.get(tid, {}).get('subs', [])
            vals = [{'n': n, 'v': v} for v, n in subs]
            if vals:
                filters[tid] = [{'key': 'type', 'name': '分类', 'value': vals}]
        return {'class': self.CLASSES, 'filters': filters, 'list': []}

    def homeVideoContent(self):
        return {'list': []}

    # ================= 分类页 =================
    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg) or 1
            url = tid
            sub = str((extend or {}).get('type', '') or '').strip()
            if sub and sub.isdigit():
                url = re.sub(r'/type/id/\d+\.html', '/type/id/%s.html' % sub, tid)
            url = self._page(url, pg)
            html = self._get(url)
            base = url.split('/index.php/')[0] + '/'
            return {'list': self._cards(html, base, url, 90), 'page': pg,
                    'pagecount': 9999, 'limit': 90, 'total': 999999}
        except:
            return {'list': [], 'page': int(pg or 1), 'pagecount': 9999, 'limit': 90, 'total': 0}

    # ================= 详情页 =================
    def detailContent(self, ids):
        try:
            url = self._norm(ids[0])
            qs = parse_qs(urlparse(url).query)
            title = self._title_from_url(url)
            pic = (qs.get('b') or [''])[0].strip()
            pic = self._img_proxy(pic, url) if pic.startswith('http') else ''
            return {'list': [{'vod_id': url, 'vod_name': title, 'vod_pic': pic,
                              'vod_play_from': '直链', 'vod_play_url': '播放$' + url}]}
        except:
            return {'list': []}

    # ================= 播放解析 =================
    def playerContent(self, flag, id, vipFlags):
        try:
            url = self._norm(id)
            # id 本身就是直链视频（m3u8/mp4）→ 直接播
            if self._is_video(url):
                return {'parse': 0, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{url}', 'header': self.headers}
            qs = parse_qs(urlparse(url).query)
            # 只有 dcdc（一区/七区）的 v 参数是确定的直链（详情页 JS `initPlayer(vv)`）。
            # 判断特征：值不含 `/m3u8/`（含 /m3u8/ 的是 acac 三区/八区的 cloudfront，需切换）。
            v = (qs.get('v') or [''])[0].strip()
            if v.startswith('http') and '/m3u8/' not in v:
                return {'parse': 0, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{v}', 'header': self.headers}
            # 其余（kd 二区/六区可能 qrtuv 切换、id 五区/九区、m 一区/四区、acac 的 v）
            # 一律回传详情页，让网站自己的 JS 去解析域名池/API。
            # spider 不硬编码任何播放域名池，域名池更新也不会失效。
            return {'parse': 1, 'url': url, 'header': self.headers}
        except:
            return {'parse': 1, 'url': id, 'header': self.headers}

    # ================= 搜索 =================
    def searchContent(self, key, quick, pg='1'):
        try:
            pg = int(pg) or 1
            key = (key or '').strip()
            if not key:
                return {'list': [], 'page': pg, 'pagecount': 1}
            classes = getattr(self, '_home_classes', None) or self.CLASSES
            ppz = 4
            total = len(classes) * ppz
            idx = pg - 1
            if idx < 0 or idx >= total:
                return {'list': [], 'page': pg, 'pagecount': total}
            n = idx // ppz
            zp = idx % ppz + 1
            info = self._zone.get(classes[n]['type_id'], {})
            host = info.get('host', classes[n]['type_id'].split('/index.php/')[0])
            module = info.get('module', 'vod')
            default = info.get('subs', [('1', '')])[0][0]
            wd = requests.utils.quote(key)
            url = '%s/index.php/%s/type/id/%s/wd/%s/page/%d.html' % (host, module, default, wd, zp)
            html = self._get(url)
            return {'list': self._cards(html, host + '/', host, 60), 'page': pg, 'pagecount': total}
        except:
            return {'list': [], 'page': int(pg or 1), 'pagecount': 1}

    # ================= 图片代理 =================
    def localProxy(self, param):
        try:
            if (param or {}).get('type') != 'img' or not param.get('url'):
                return [404, 'text/plain', b'']
            real = self.d64(param['url'])
            if not real:
                return [404, 'text/plain', b'']
            h = dict(self.headers)
            h.update({'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8', 'Accept-Encoding': 'identity'})
            r = self.s.get(real, headers=h, timeout=15, verify=False, proxies=self.proxies)
            data = r.content
            mime = self._mime(data)
            if mime:
                return [r.status_code, mime, data]
            # XOR 解密（各 key 解密字节数不同）
            for key, n in self.IMG_KEYS:
                buf = bytearray(data[:n])
                for i in range(len(buf)):
                    buf[i] ^= key[i % len(key)]
                mime = self._mime(bytes(buf))
                if mime:
                    full = bytearray(data)
                    for i in range(min(n, len(full))):
                        full[i] ^= key[i % len(key)]
                    return [r.status_code, mime, bytes(full)]
            return [r.status_code, 'application/octet-stream', data]
        except:
            return [404, 'text/plain', b'']

    # ================= 工具 =================
    def _get(self, url):
        url = self._norm(url)
        h = dict(self.headers)
        h['Referer'] = '%s://%s/' % (urlparse(url).scheme, urlparse(url).netloc)
        r = self.s.get(url, headers=h, timeout=10, verify=False, proxies=self.proxies)
        if r.status_code != 200:
            raise ValueError
        r.encoding = r.apparent_encoding
        return r.text

    def _page(self, url, pg):
        if pg <= 1:
            return url
        if '/page/' in url:
            return re.sub(r'/page/\d+\.html', '/page/%d.html' % pg, url)
        return url.replace('.html', '/page/%d.html' % pg)

    def _cards(self, html, base, ref, limit):
        doc = pq(html)
        out, seen = [], set()
        for a in doc('a[href*="/html/"]').items():
            href = (a.attr('href') or '').strip()
            detail = self._norm(urljoin(base, href))
            if not detail or detail in seen:
                continue
            seen.add(detail)
            title = (a.find('p').text() or a.attr('title') or '').strip()
            title = self._dec(title) if title else self._title_from_url(detail)
            if not title:
                continue
            img = a.find('img').attr('data-original') or a.find('img').attr('data-cover') or a.find('img').attr('src') or ''
            img = self._clean(img)
            if img and not img.startswith('http'):
                img = urljoin(base, img)
            if img:
                img = self._img_proxy(img, ref)
            out.append({'vod_id': detail, 'vod_name': title, 'vod_pic': img,
                        'style': {'type': 'rect', 'ratio': 1.33}})
            if len(out) >= limit:
                break
        return out

    def _dec(self, s):
        return ''.join(chr(ord(c) ^ 128) for c in s).strip()

    def _title_from_url(self, url):
        seg = urlparse(url).path.rsplit('/', 1)[-1]
        seg = unquote(seg)
        if seg.endswith('.html'):
            seg = seg[:-5]
        return self._dec(seg)

    def _clean(self, s):
        s = (s or '').strip()
        if s.startswith(('blob:', 'data:')):
            return ''
        return s.replace('\\/', '/').replace('\\', '')

    def _norm(self, u):
        u = (u or '').strip()
        try:
            return requests.utils.requote_uri(u)
        except:
            return u

    def _is_video(self, u):
        p = (urlparse(u).path or '').lower()
        return '.m3u8' in p or '.mp4' in p

    def _img_proxy(self, img, ref=''):
        proxy = self.getProxyUrl()
        if not proxy:
            return img
        p = urlparse(ref)
        rs = '%s://%s/' % (p.scheme, p.netloc) if ref else ''
        return '%s&type=img&url=%s' % (proxy, self.e64(img)) + ('&ref=%s' % self.e64(rs) if rs else '')

    def _mime(self, data):
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return 'image/png'
        if data[:3] == b'GIF':
            return 'image/gif'
        if data[:4] == b'RIFF' and b'WEBP' in data[:16]:
            return 'image/webp'
        if data[:2] == b'\xff\xd8':
            return 'image/jpeg'
        return ''

    def e64(self, t):
        return base64.urlsafe_b64encode(str(t).encode()).decode().rstrip('=')

    def d64(self, t):
        s = str(t).strip()
        if not s:
            return ''
        s += '=' * ((4 - len(s) % 4) % 4)
        return base64.urlsafe_b64decode(s.encode()).decode('utf-8', 'ignore')
