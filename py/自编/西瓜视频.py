# -*- coding: utf-8 -*-
# 西瓜视频站 OK影视 Spider
# 唯一硬编码入口：固定永久导航页 NAV_URL（站方 CDN 上的域名池文件）
# 其余站点地址（可用域名 / 图片域 / 播放域）全部运行时从导航页动态解析并探测。
import sys
import re
import json
import time
import base64
import threading
import socket
from urllib.parse import quote, unquote, urljoin, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.append('..')
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    BaseSpider = object

# ================= 唯一硬编码入口：固定永久导航页 =================
# 该地址挂在站点长期维护的 .com CDN 上，内容为「平台5(Android)可用域名池」。
# 站方更换 .cc 站点域名时，会同步更新此文件，因此域名永不写死。
NAV_URL = 'https://xgsamsw.lbjhhnu.com/static/common/domain_5.js'
PLATFORM = '5'

UA = 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36'

# AES-CBC 密钥（接口响应与封面图片共用）
KEY = b'NHboMHZerxFQ401E'
IV = b'i7JeCEIMVrj2W9xN'

CATEGORIES = [
    {'type_id': '51', 'type_name': '国产'}, {'type_id': '156', 'type_name': '国产-乱伦'},
    {'type_id': '152', 'type_name': '国产-偷情'}, {'type_id': '191', 'type_name': '国产-剧情'},
    {'type_id': '144', 'type_name': '国产-偷拍'}, {'type_id': '145', 'type_name': '国产-自拍'},
    {'type_id': '151', 'type_name': '国产-直播'}, {'type_id': '153', 'type_name': '国产-探花'},
    {'type_id': '154', 'type_name': '国产-强奸'}, {'type_id': '155', 'type_name': '国产-迷奸'},
    {'type_id': '76', 'type_name': '日韩'}, {'type_id': '169', 'type_name': '日韩-中字'},
    {'type_id': '171', 'type_name': '日韩-无码'}, {'type_id': '194', 'type_name': '日韩-乱伦'},
    {'type_id': '193', 'type_name': '日韩-人妻'}, {'type_id': '183', 'type_name': '日韩-群交'},
    {'type_id': '170', 'type_name': '日韩-OL'}, {'type_id': '196', 'type_name': '日韩-偷情'},
    {'type_id': '127', 'type_name': '欧美'}, {'type_id': '176', 'type_name': '欧美-黑白配'},
    {'type_id': '185', 'type_name': '欧美-剧情'}, {'type_id': '178', 'type_name': '欧美-中字'},
    {'type_id': '182', 'type_name': '欧美-SM'}, {'type_id': '186', 'type_name': '欧美-自拍'},
    {'type_id': '177', 'type_name': '欧美-男同'}, {'type_id': '181', 'type_name': '欧美-女同'},
    {'type_id': '93', 'type_name': '吃瓜'},
    {'type_id': '60', 'type_name': '传媒'}, {'type_id': '146', 'type_name': '传媒-麻豆'},
    {'type_id': '147', 'type_name': '传媒-天美'}, {'type_id': '148', 'type_name': '传媒-91'},
    {'type_id': '157', 'type_name': '传媒-星空'}, {'type_id': '158', 'type_name': '传媒-精东'},
    {'type_id': '159', 'type_name': '传媒-蜜桃'}, {'type_id': '160', 'type_name': '传媒-SWAG'},
    {'type_id': '187', 'type_name': '传媒-果冻'}, {'type_id': '188', 'type_name': '传媒-糖心'},
    {'type_id': '190', 'type_name': '传媒-萝莉社'}, {'type_id': '192', 'type_name': '传媒-扣扣'},
    {'type_id': '195', 'type_name': '传媒-皇家'},
    {'type_id': '137', 'type_name': 'AI视频'},
    {'type_id': '83', 'type_name': '动漫'}, {'type_id': '172', 'type_name': '动漫-中字'},
    {'type_id': '173', 'type_name': '动漫-有码'}, {'type_id': '174', 'type_name': '动漫-无码'},
    {'type_id': '189', 'type_name': '动漫-3D'},
    {'type_id': '71', 'type_name': '综艺'}, {'type_id': '198', 'type_name': '解说'},
    {'type_id': '197', 'type_name': 'VR'}, {'type_id': '199', 'type_name': '伦理'},
    {'type_id': '200', 'type_name': '猎奇'}, {'type_id': '201', 'type_name': '福利姬'},
]

# ================= AES-128-CBC 纯 Python 解密 =================
SBOX = bytes([
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16])
INV_SBOX = bytes([SBOX.index(i) for i in range(256)])
RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]

_CRYPTO = None


def _xtime(a):
    return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1) & 0xff


def _gmul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        b >>= 1
        a = _xtime(a)
    return r


def _key_expand(key):
    nk = len(key) // 4
    w = [int.from_bytes(key[i:i + 4], 'big') for i in range(0, len(key), 4)]
    for i in range(nk, 44):
        t = w[i - 1]
        if i % nk == 0:
            t = ((t << 8) | (t >> 24)) & 0xffffffff
            t = ((SBOX[(t >> 24) & 0xff] << 24) | (SBOX[(t >> 16) & 0xff] << 16) |
                 (SBOX[(t >> 8) & 0xff] << 8) | SBOX[t & 0xff]) ^ (RCON[i // nk - 1] << 24)
        w.append(w[i - nk] ^ t)
    return [[(x >> 24) & 0xff, (x >> 16) & 0xff, (x >> 8) & 0xff, x & 0xff] for x in w]


def _dec_block(key, block):
    w = _key_expand(key)
    s = list(block)

    def ark(rnd):
        for c in range(4):
            for r in range(4):
                s[4 * c + r] ^= w[rnd * 4 + c][r]

    def isb():
        for i in range(16):
            s[i] = INV_SBOX[s[i]]

    def isr():
        t = s[:]
        for r in range(1, 4):
            for c in range(4):
                s[4 * c + r] = t[4 * ((c - r) % 4) + r]

    def imc():
        for c in range(4):
            a0, a1, a2, a3 = s[4 * c], s[4 * c + 1], s[4 * c + 2], s[4 * c + 3]
            s[4 * c] = _gmul(a0, 0x0e) ^ _gmul(a1, 0x0b) ^ _gmul(a2, 0x0d) ^ _gmul(a3, 0x09)
            s[4 * c + 1] = _gmul(a0, 0x09) ^ _gmul(a1, 0x0e) ^ _gmul(a2, 0x0b) ^ _gmul(a3, 0x0d)
            s[4 * c + 2] = _gmul(a0, 0x0d) ^ _gmul(a1, 0x09) ^ _gmul(a2, 0x0e) ^ _gmul(a3, 0x0b)
            s[4 * c + 3] = _gmul(a0, 0x0b) ^ _gmul(a1, 0x0d) ^ _gmul(a2, 0x09) ^ _gmul(a3, 0x0e)

    ark(10)
    for rnd in range(9, 0, -1):
        isr()
        isb()
        ark(rnd)
        imc()
    isr()
    isb()
    ark(0)
    return bytes(s)


def _aes_cbc_decrypt(key, iv, data):
    global _CRYPTO
    if _CRYPTO is None:
        try:
            from Crypto.Cipher import AES
            _CRYPTO = AES
        except Exception:
            _CRYPTO = False
    if _CRYPTO:
        try:
            return _CRYPTO.new(key, _CRYPTO.MODE_CBC, iv).decrypt(data)
        except Exception:
            pass
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        blk = data[i:i + 16]
        out += bytes(a ^ b for a, b in zip(_dec_block(key, blk), prev))
        prev = blk
    return bytes(out)


def _decode(data):
    """接口响应解密：base64 -> AES-CBC -> 去 PKCS7 padding -> utf-8"""
    raw = _aes_cbc_decrypt(KEY, IV, base64.b64decode(data))
    pad = raw[-1] if raw else 0
    if 1 <= pad <= 16:
        raw = raw[:-pad]
    return raw.decode('utf-8', 'ignore')


# ================= 通用请求 =================
def _fetch(u, headers=None, proxies=None, timeout=8):
    import urllib.request
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    handlers = [urllib.request.HTTPSHandler(context=ctx)]
    if proxies:
        handlers.append(urllib.request.ProxyHandler(proxies))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(u, headers=headers or {})
    return opener.open(req, timeout=timeout)


# ================= 封面图片解密 / 转码 =================
_PLACEHOLDER = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')


def _guess_img(b):
    if b[:4] == b'RIFF' and b[8:12] == b'WEBP':
        return 'image/webp'
    if b[:2] == b'\xff\xd8':
        return 'image/jpeg'
    if b[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if b[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    return ''


def _webp_to_jpeg(b):
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(b)).convert('RGB')
        out = io.BytesIO()
        im.save(out, 'JPEG', quality=85)
        return out.getvalue()
    except Exception:
        return None


def _img_process(body):
    """图片处理：明文直出；AES 加密则解密；webp 尽力转 jpeg（老设备兼容）"""
    ct = _guess_img(body)
    if ct:
        return ct, body
    if len(body) >= 16 and len(body) % 16 == 0:
        raw = _aes_cbc_decrypt(KEY, IV, body)
        pad = raw[-1] if raw else 0
        if 1 <= pad <= 16 and raw[-pad:] == bytes([pad]) * pad:
            raw = raw[:-pad]
            ct = _guess_img(raw)
            if ct:
                if ct == 'image/webp':
                    jpeg = _webp_to_jpeg(raw)
                    if jpeg:
                        return 'image/jpeg', jpeg
                return ct, raw
    return 'application/octet-stream', body


# ================= 封面本地代理 =================
class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        qs = self.path.split('?', 1)[1] if '?' in self.path else ''
        q = parse_qs(qs)
        u = unquote(q.get('url', [''])[0]) if q else ''
        if not u and qs and 'url=' in qs:
            u = unquote(qs.split('url=', 1)[1])
        sp = Spider._instance
        if not u or sp is None:
            self.send_response(404)
            self.end_headers()
            return
        status, ct, body = sp._pic_proxy(u)
        self.send_response(status)
        self.send_header('Content-Type', ct)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'public, max-age=86400')
        self.end_headers()
        if body:
            self.wfile.write(body)


def _start_proxy():
    if Spider._server_started:
        return Spider._port
    for port in range(9978, 9988):
        try:
            srv = ThreadingHTTPServer(('127.0.0.1', port), _Handler)
            srv.daemon_threads = True
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            Spider._port = port
            Spider._server_started = True
            return port
        except OSError:
            continue
    return 9978


# ================= Spider =================
class Spider(BaseSpider):
    _instance = None
    _port = 0
    _server_started = False

    def __init__(self):
        self.host = ''       # 运行时探测出的可用站点域名
        self.img = ''        # 图片域 imgdomain
        self.play = ''       # 播放域 playdomain
        self.plp = ''        # 播放器/图片 URL 前缀，空=直连
        self.proxy = {}      # 内部请求代理，空=直连
        self._cfg = None     # getSetting 缓存
        self._lock = threading.Lock()

    # ---------- OK影视 标准接口 ----------
    def getName(self):
        return '西瓜'

    def isVideoFormat(self, url):
        return bool(url and ('.m3u8' in url or '.mp4' in url or '127.0.0.1' in url))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        return None

    def init(self, extend=''):
        Spider._instance = self
        if extend:
            if isinstance(extend, str) and extend.startswith('http'):
                # 直接指定站点域名（跳过导航页发现）
                self.host = extend.rstrip('/')
            else:
                try:
                    cfg = json.loads(extend) if isinstance(extend, str) else extend
                    if isinstance(cfg, dict):
                        self.plp = cfg.get('plp', '')
                        self.proxy = cfg.get('proxy') or {}
                        if cfg.get('host'):
                            self.host = str(cfg['host']).rstrip('/')
                except Exception:
                    pass
        socket.setdefaulttimeout(8)

    # ---------- 域名发现（导航页 -> 域名池 -> 探测） ----------
    def _nav_domains(self):
        """从固定导航页解析可用域名列表（双层 base64）"""
        try:
            r = _fetch(NAV_URL, headers={'User-Agent': UA}, proxies=self.proxy, timeout=10)
            con = r.read().decode('utf-8', 'ignore').strip()
            inner = base64.b64decode(con[1:-1])
            arr = json.loads(base64.b64decode(inner).decode('utf-8'))
            return [x.get('url') for x in arr if isinstance(x, dict) and x.get('url')]
        except Exception:
            return []

    def _headers(self, domain=None):
        host = domain or self.host or NAV_URL.split('//')[1].split('/')[0]
        ch = host.split('//')[-1].split('.')[0]
        return {'User-Agent': UA, 'platform': PLATFORM, 'Channel-Code': ch, 'uuid': '__UUID'}

    def _probe(self, domain):
        """探测域名，成功返回 (domain, img, play, cfg)，失败返回 None（不修改实例，供并发调用）"""
        domain = domain.rstrip('/')
        try:
            url = domain + '/app/common/getSetting?platform=' + PLATFORM
            r = _fetch(url, headers=self._headers(domain), proxies=self.proxy, timeout=4)
            cfg = json.loads(_decode(r.read())).get('data', {})
            if cfg:
                return domain, cfg.get('imgdomain', '') or '', cfg.get('playdomain', '') or '', cfg
        except Exception:
            pass
        return None

    def _discover(self):
        """确保已获得可用站点域名：并发探测域名池，第一个可用立即选中并返回"""
        if self.host:
            return True
        with self._lock:
            if self.host:
                return True
            domains = self._nav_domains()
            if not domains:
                return False
            winner = [None]
            lock = threading.Lock()
            event = threading.Event()

            def worker(d):
                r = self._probe(d)
                if r:
                    with lock:
                        if winner[0] is None:
                            winner[0] = r
                    event.set()

            for d in domains:
                t = threading.Thread(target=worker, args=(d,))
                t.daemon = True
                t.start()
            event.wait(timeout=6)
            if winner[0]:
                self.host, self.img, self.play, self._cfg = winner[0]
                return True
        return False

    # ---------- 接口请求 ----------
    def _get(self, url):
        try:
            r = _fetch(url, headers=self._headers(), proxies=self.proxy, timeout=8)
            if r.status == 200:
                return _decode(r.read())
        except Exception:
            pass
        return ''

    def _pic(self, poster):
        if not poster:
            return ''
        u = poster if poster.startswith('http') else (self.img or '') + poster
        _start_proxy()
        return 'http://127.0.0.1:%d/pic?url=%s' % (Spider._port, quote(u, safe=''))

    def _pic_proxy(self, u):
        """抓取并解密封面图片（被本地代理回调）"""
        m = re.search(r'/([0-9a-f]{32})/', u)
        ref = self.host + '/poster.html?viewkey=' + (m.group(1) if m else '')
        try:
            r = _fetch(u, headers={'User-Agent': UA, 'Referer': ref}, proxies=self.proxy, timeout=10)
            ct, body = _img_process(r.read())
            return 200, ct, body
        except Exception:
            return 200, 'image/gif', _PLACEHOLDER

    def _list(self, page, cid='', keyword=''):
        if not self._discover():
            return {'list': [], 'page': page, 'pagecount': page, 'limit': 18, 'total': 0}
        params = {'page': page, 'pageSize': 18, 'sort': 1}
        if cid:
            params['cid'] = cid
        if keyword:
            params['keyword'] = quote(keyword)
        url = self.host + '/app/movie/getList?' + '&'.join('%s=%s' % (k, v) for k, v in params.items())
        html = self._get(url)
        if not html:
            return {'list': [], 'page': page, 'pagecount': page, 'limit': 18, 'total': 0}
        try:
            j = json.loads(html)
        except Exception:
            return {'list': [], 'page': page, 'pagecount': page, 'limit': 18, 'total': 0}
        vlist = []
        for r in j.get('records', []):
            vlist.append({
                'vod_id': r.get('viewKey', ''),
                'vod_name': r.get('title', ''),
                'vod_pic': self._pic(r.get('poster', '')),
                'vod_remarks': '',
                'vod_year': '',
            })
        pc = j.get('pageCount', page) or page
        return {'list': vlist, 'page': page, 'pagecount': pc, 'limit': 18, 'total': pc * 18}

    # ---------- 内容接口 ----------
    def homeContent(self, filter=False):
        return {'class': CATEGORIES, 'list': []}

    def homeVideoContent(self):
        return self._list(1)

    def categoryContent(self, tid, pg=1, filter=False, extend=''):
        tid = str(tid).strip()
        page = int(pg or 1)
        if tid.isdigit():
            return self._list(page, tid)          # 数字分类 id
        cid = self._cid_of(tid)                    # 分类名 → id
        if cid:
            return self._list(page, cid)
        return self._list(page, '', tid)           # 标签词/分类名 → 按关键词搜索

    def searchContent(self, key, quick=False, pg='1'):
        return self._list(int(pg or 1), '', str(key))

    # ---------- 分类 id / 名称互查 ----------
    def _cname_of(self, cid):
        cid = str(cid)
        for c in CATEGORIES:
            if c['type_id'] == cid:
                return c['type_name']
        return ''

    def _cid_of(self, name):
        name = str(name).strip()
        for c in CATEGORIES:
            if c['type_name'] == name:
                return c['type_id']
        return ''

    def _fmt_dur(self, sec):
        try:
            sec = int(sec)
        except Exception:
            return ''
        if sec < 60:
            return '%d秒' % sec if sec > 0 else ''
        if sec < 3600:
            return '%d分钟' % (sec // 60)
        return '%d小时%d分' % (sec // 3600, (sec % 3600) // 60)

    def _fmt_hits(self, n):
        try:
            n = int(n)
        except Exception:
            return ''
        if n >= 10000:
            return '%.1f万播放' % (n / 10000.0)
        if n > 0:
            return '%d播放' % n
        return ''

    def _clickable(self, text):
        """把逗号分隔的标签词转成 OK影视 可点击标签 [a=cr:{id,name}/]词[/a]。
        点击后前端调 categoryContent(tid=id)，故 id 直接放标签词，由 categoryContent 兜底搜索。"""
        out = []
        for t in (text or '').split(','):
            t = t.strip()
            if t:
                out.append('[a=cr:%s/]%s[/a]' % (json.dumps({'id': t, 'name': t}, ensure_ascii=False), t))
        return ' '.join(out)

    def detailContent(self, ids):
        if not ids or not self._discover():
            return {'list': []}
        vid = ids[0]
        url = self.host + '/app/movie/getDetail?viewKey=' + quote(vid)
        html = self._get(url)
        if not html:
            return {'list': []}
        try:
            d = json.loads(html).get('data', {}) or {}
        except Exception:
            return {'list': []}
        title = d.get('title', '') or vid
        tags = (d.get('tags', '') or '').strip()
        desc = (d.get('description', '') or '').strip()
        if not desc or desc.lower() == 'unkown':
            desc = ''                              # 站点简介字段恒为 unkown，无真实简介
        cname = self._cname_of(d.get('cid', ''))
        year = (d.get('releaseDate', '') or '')[:4]
        remarks = self._fmt_dur(d.get('duration'))
        hits = self._fmt_hits(d.get('hits'))
        if remarks and hits:
            remarks = remarks + ' · ' + hits
        elif hits:
            remarks = hits
        play_url = (self.play or '') + (d.get('playUrl', '') or '')
        # 播放地址加内置代理前缀，直接交给播放器
        vod = {
            'vod_id': vid,
            'vod_name': title,
            'vod_pic': self._pic(d.get('poster', '')),
            'type_name': cname,                    # 主分类，点击进分类列表
            'vod_year': year,
            'vod_area': '',
            'vod_class': tags,                     # 分类/标签（逗号分隔）
            'vod_director': '',
            'vod_actor': self._clickable(tags),    # 可点击标签：[a=cr:...]语法，点击某词即搜索出二级列表
            'vod_content': desc if desc else tags,  # 简介：站点无则退回标签
            'vod_remarks': remarks,                 # 时长 · 播放量
            'vod_play_from': '西瓜',
            'vod_play_url': '正片$' + self.plp + play_url,
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags=None):
        m = re.search(r'/([0-9a-f]{32})/', id or '')
        ref = self.host + '/poster.html?viewkey=' + (m.group(1) if m else '')
        return {'parse': 0, 'url': id, 'header': {'User-Agent': UA, 'Referer': ref}}

    def localProxy(self, param):
        p = param.split('//', 1)[1] if param.startswith('http') else param
        qs = p.split('?', 1)[1] if '?' in p else ''
        u = unquote(parse_qs(qs).get('url', [''])[0]) if qs else ''
        if not u:
            return [404, 'text/plain', '']
        status, ct, body = self._pic_proxy(u)
        return [status, ct, body]
