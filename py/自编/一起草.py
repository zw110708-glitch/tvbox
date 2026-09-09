# -*- coding: utf-8 -*-
# 一起草（17c 系）OK影视 Python 源
# 动态域名 /v1/* JSON + RSA/AES 加密，静态资源 XOR 0x88
import sys, re, json, time, base64
import requests
from urllib.parse import quote, unquote

sys.path.append('..')
from base.spider import Spider

UA = ('Mozilla/5.0 (Linux; Android 15; 23013RK75C Build/AQ3A.250226.002; wv) '
      'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/146.0.7680.177 '
      'Mobile Safari/537.36')

CANDIDATES = [
    'https://www.qerigrc.com:2087',
    'https://www.qluiwxu.com:2087',
    'https://www.qluewxu.com:2087',
    'https://www.guwvdfy.com:2087',
    'https://www.zgvjeuu.com:2087',
]

RSA_N = 'd04f4db2ecfa8d817e25e2ea29a2f52e46728345a5e313c8c04ce50eb3b850e318197d561be9ea7fda2fa699604e180b732a11335605b211853ab900887119ab'
RSA_D = '01bc47677035fe2bd0033ccabaa212ecd9c5667694153a3af7ef2c115d49f1d28eac923337620e39bb0de5a686eb91c91ea74371aab20d792b2b636f61037641'

C_MAP = {
    'e': 'P', 'w': 'D', 'T': 'y', '+': 'J', 'l': '!', 't': 'L', 'E': 'E', '@': '2',
    'd': 'a', 'b': '%', 'q': 'l', 'X': 'v', '~': 'R', '5': 'r', '&': 'X', 'C': 'j',
    ']': 'F', 'a': ')', '^': 'm', ',': '~', '}': '1', 'x': 'C', 'c': '(', 'G': '@',
    'h': 'h', '.': '*', 'L': 's', '=': ',', 'p': 'g', 'I': 'Q', '1': '7', '_': 'u',
    'K': '6', 'F': 't', '2': 'n', '8': '=', 'k': 'G', 'Z': ']', ')': 'b', 'P': '}',
    'B': 'U', 'S': 'k', '6': 'i', 'g': ':', 'N': 'N', 'i': 'S', '%': '+', '-': 'Y',
    '?': '|', '4': 'z', '*': '-', '3': '^', '[': '{', '(': 'c', 'u': 'B', 'y': 'M',
    'U': 'Z', 'H': '[', 'z': 'K', '9': 'H', '7': 'f', 'R': 'x', 'v': '&', '!': ';',
    'M': '_', 'Q': '9', 'Y': 'e', 'o': '4', 'r': 'A', 'm': '.', 'O': 'o', 'V': 'W',
    'J': 'p', 'f': 'd', ':': 'q', '{': '8', 'W': 'I', 'j': '?', 'n': '5', 's': '3',
    '|': 'T', 'A': 'V', 'D': 'w', ';': 'O',
}

_BAD_RE = re.compile(
    r'同城|外围|约炮|招嫖|春药|催情|直播|游戏|棋牌|体育|博彩|澳门|葡京|威尼斯人|皇冠|PG|APP|浏览器|下载|邮箱|永久|发布|Telegram|广告|客服|上门|兼职')

XOR_KEY = 0x88
PAGE_SIZE = 24
PAGE_SIZE_OTHER = 12
PLAY_FROM = '一起草'


class Spider(Spider):

    def init(self, extend="{}"):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        self.site = (config.get('site') or '').strip() or CANDIDATES[0]
        self.plp = config.get('plp', '')
        self.proxy = config.get('proxy', {})
        self.ua = UA
        self.c = '0'
        self._host = ''
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': self.ua,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'X-Requested-With': 'XMLHttpRequest',
        })
        self._blist = None
        self._classes = None
        self._filters = None

    def getName(self):
        return '一起草'

    def isVideoFormat(self, url):
        return bool(url and re.search(r'\.(m3u8|mp4|flv|webm|ts)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ---------------- 工具 ----------------

    def _clean_name(self, t):
        t = re.sub(r'<[^>]+>', '', str(t or '')).replace('&nbsp;', ' ')
        return re.sub(r'\s+', ' ', t).strip()

    def _clean_text(self, t):
        return re.sub(r'永久官网：?17c\.com', '', str(t or '')).strip()

    def _bad(self, name):
        return bool(_BAD_RE.search(str(name or '')))

    def _c_decode(self, s):
        try:
            return unquote(''.join(C_MAP.get(ch, ch) for ch in (s or '')))
        except Exception:
            return s

    def _add_candidate(self, lst, url):
        if not url:
            return
        url = str(url).replace('\\', '').rstrip('/')
        if re.match(r'^https?://', url) and url not in lst:
            lst.append(url)

    def _fix_url(self, url):
        if not url or url.startswith('http'):
            return url or ''
        host = (self._host or self.site).rstrip('/')
        if url.startswith('//'):
            return 'https:' + url
        return host + (url if url.startswith('/') else '/' + url)

    def _cover(self, pic):
        pic = self._fix_url(pic)
        if not pic or not pic.startswith('http'):
            return pic
        try:
            return self.getProxyUrl() + '&type=img&url=' + quote(pic, safe='')
        except Exception:
            return pic

    def _cr(self, vid, name):
        return '[a=cr:%s/]%s[/a]' % (json.dumps({'id': vid, 'name': name}, ensure_ascii=False), name)

    # ---------------- 请求 ----------------

    def _fetch(self, url, params=None, referer='', timeout=15):
        headers = {'Referer': referer} if referer else {}
        return self._session.get(url, params=params, headers=headers,
                                 proxies=self.proxy, timeout=timeout, verify=False)

    def _cache_get(self, key):
        try:
            v = self.getCache(key)
            return v if isinstance(v, str) else str(v)
        except Exception:
            return ''

    def _cache_set(self, key, value):
        try:
            self.setCache(key, value)
        except Exception:
            pass

    # ---------------- 域名选择 ----------------

    def _check_host(self, host):
        if not host:
            return False
        try:
            r = self._fetch(host.rstrip('/') + '/v1/blist', params={'c': self.c},
                            referer=host.rstrip('/') + '/', timeout=10)
            t = r.text or ''
            return ('"data"' in t) and ('"key"' in t)
        except Exception:
            return False

    def _discover_hosts(self):
        hosts = []
        for u in ([self.site] if self.site else []) + CANDIDATES:
            self._add_candidate(hosts, u)
        try:
            html = self._fetch('https://17c.com/', referer='https://17c.com/', timeout=8).text
            m = re.search(r'https://c\d+\.17czz\.17ctz\.com/index\.html', html)
            if m:
                for u in (m.group(0), m.group(0).replace('17czz', '17cfb')):
                    try:
                        h = self._fetch(u, referer='https://17c.com/', timeout=8).text
                        for x in re.findall(r'https://www\.[^"\'<>\s]+:2087/?', h):
                            self._add_candidate(hosts, x)
                    except Exception:
                        pass
        except Exception:
            pass
        more = []
        for u in list(hosts):
            try:
                h = self._fetch(u + '/', referer=u + '/', timeout=8).text
                m = re.search(r'en\(["\']([^"\']+)["\']\)', h) or re.search(r'href\s*=\s*["\']([^"\']+)["\']', h)
                if m and m.group(1):
                    self._add_candidate(more, m.group(1) if re.match(r'^https?://', m.group(1))
                                        else self._c_decode(m.group(1)))
            except Exception:
                pass
        for u in more:
            self._add_candidate(hosts, u)
        return hosts

    def _resolve_host(self, force=False):
        if not force and self._host:
            return self._host
        today = time.strftime('%Y-%m-%d')
        cached = self._cache_get('yqc_host').strip().rstrip('/')
        if not force and cached and self._cache_get('yqc_host_day').strip() == today:
            self._host = cached
            return self._host
        if not force and cached and self._check_host(cached):
            self._host = cached
            self._cache_set('yqc_host_day', today)
            return self._host
        for h in self._discover_hosts():
            if self._check_host(h):
                self._host = h.rstrip('/')
                self._cache_set('yqc_host', self._host)
                self._cache_set('yqc_host_day', today)
                return self._host
        self._host = (cached or self.site or CANDIDATES[0]).rstrip('/')
        return self._host

    # ---------------- 解密 ----------------

    def _rsa_decrypt(self, key_b64):
        try:
            c = int.from_bytes(base64.b64decode(key_b64), 'big')
            m = pow(c, int(RSA_D, 16), int(RSA_N, 16))
            hx = format(m, 'x')
            if len(hx) < 128:
                hx = '0' * (128 - len(hx)) + hx
            arr = bytes.fromhex(hx)
            p = 2
            while p < len(arr) and arr[p] != 0:
                p += 1
            return arr[p + 1:].decode('utf-8', 'ignore')
        except Exception:
            return ''

    def _aes_decrypt(self, data_b64, aes_key):
        try:
            from Crypto.Cipher import AES
            key = aes_key.encode('utf-8')
            if len(key) not in (16, 24, 32):
                key = (key + b'\x00' * 32)[:32]
            iv = (aes_key[::-1][:16] + '\x00' * 16)[:16].encode('utf-8')
            ct = base64.b64decode(data_b64)
            plain = AES.new(key, AES.MODE_CBC, iv).decrypt(ct)
            if plain:
                pad = plain[-1]
                if 1 <= pad <= 16:
                    plain = plain[:-pad]
            return plain
        except Exception:
            return b''

    def _api_get(self, path, params=None):
        params = dict(params or {})
        params.setdefault('c', self.c)
        for attempt in (0, 1):
            try:
                host = self._resolve_host(force=(attempt == 1))
            except Exception:
                host = ''
            if not host:
                continue
            url = host.rstrip('/') + '/v1/' + path.lstrip('/')
            try:
                rsp = self._session.get(url, params=params, headers={'Referer': host.rstrip('/') + '/'},
                                        proxies=self.proxy, timeout=20, verify=False)
                body = rsp.json()
            except Exception:
                self._host = ''
                continue
            if isinstance(body, dict) and isinstance(body.get('data'), str) and isinstance(body.get('key'), str):
                try:
                    key = self._rsa_decrypt(body['key'])
                    if key:
                        plain = self._aes_decrypt(body['data'], key)
                        if plain:
                            body = json.loads(plain.decode('utf-8'))
                except Exception:
                    pass
            if isinstance(body, dict) and 'data' in body:
                body = body['data']
            if body is not None:
                return body
            self._host = ''
        return {}

    # ---------------- 分类 ----------------

    def _get_blist(self):
        if self._blist is None:
            self._blist = self._api_get('blist') or {}
        return self._blist

    def _build_classes(self):
        if self._classes is not None:
            return self._classes, self._filters
        classes, filters = [], {}
        for m in (self._get_blist().get('menu_cates') or []):
            if not isinstance(m, dict):
                continue
            nm = self._clean_name(m.get('name'))
            if not nm or nm == '首页' or self._bad(nm):
                continue
            subs = []
            for s in (m.get('sub_cates') or m.get('sub_menu') or []):
                if isinstance(s, dict):
                    sn = self._clean_name(s.get('name') or s.get('title'))
                    if sn and not self._bad(sn):
                        subs.append({'id': s.get('id') if s.get('id') is not None else '', 'name': sn})
            mid, path = m.get('id'), m.get('path') or ''
            if mid is not None:
                tid = 'vod_' + str(mid)
            elif path in ('cg_list', 'novel', 'comic'):
                tid = path
            else:
                continue
            classes.append({'type_id': tid, 'type_name': nm})
            if subs:
                filters[tid] = [{'key': 'sub', 'name': '子分类',
                                 'value': [{'n': '全部', 'v': ''}]
                                 + [{'n': s['name'], 'v': str(s['id'])} for s in subs if s['id'] != '']}]
        self._classes, self._filters = classes, filters
        return classes, filters

    def homeContent(self, filter):
        result = {'class': [], 'filters': {}}
        try:
            result['class'], result['filters'] = self._build_classes()
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        items, seen = [], set()
        try:
            rel = self._api_get('relist') or {}
            for key in ('recommend_videos', 'rank_videos'):
                blk = rel.get(key)
                if isinstance(blk, dict) and isinstance(blk.get('videos'), list):
                    for v in blk['videos']:
                        it = self._to_item(v)
                        if it and it['vod_id'] not in seen:
                            seen.add(it['vod_id'])
                            items.append(it)
        except Exception:
            pass
        if not items:
            try:
                items = self._parse_videos(self._api_get('vod', {'page': '1', 'limit': PAGE_SIZE}))
            except Exception:
                pass
        return {'list': items}

    # ---------------- 列表解析 ----------------

    def _to_item(self, v):
        if not isinstance(v, dict):
            return None
        vid = v.get('id') or v.get('vod_id') or v.get('video_id')
        name = self._clean_text(v.get('name') or v.get('title') or v.get('vod_name'))
        if vid is None or not name or v.get('href') or v.get('is_yp') or self._bad(name):
            return None
        # 副标题只保留时长，删掉日期(create_time)和播放次数(eye)
        remark = str(v.get('time') or '')
        return {
            'vod_id': 'vod_' + str(vid),
            'vod_name': str(name)[:200],
            'vod_pic': self._cover(v.get('enc_img') or v.get('pic') or v.get('cover') or v.get('img') or ''),
            'vod_remarks': remark,
        }

    def _parse_videos(self, data):
        items, seen = [], set()

        def add(v):
            it = self._to_item(v)
            if it and it['vod_id'] not in seen:
                seen.add(it['vod_id'])
                items.append(it)

        if isinstance(data, dict):
            for key in ('recommend_videos', 'rank_videos'):
                blk = data.get(key)
                if isinstance(blk, dict) and isinstance(blk.get('videos'), list):
                    for v in blk['videos']:
                        add(v)
            for key in ('videos', 'list', 'records', 'data'):
                if isinstance(data.get(key), list):
                    for v in data[key]:
                        add(v)
        elif isinstance(data, list):
            for v in data:
                add(v)
        return items

    def _to_simple(self, x, kind):
        if not isinstance(x, dict):
            return None
        sid, sname = x.get('id'), x.get('name') or x.get('title')
        if sid is None or not sname or x.get('href') or self._bad(str(sname)):
            return None
        cc = x.get('chapters_count')
        desc = self._clean_text(x.get('subtitle') or x.get('cate_name') or ('章节：' + str(cc) if cc is not None else ''))
        return {
            'vod_id': kind + '_' + str(sid),
            'vod_name': self._clean_text(str(sname))[:200],
            'vod_pic': self._cover(x.get('enc_img') or ''),
            'vod_remarks': str(desc),
        }

    def _parse_simple(self, data, kind):
        keys = {'cg': ('chiguas',), 'novel': ('novels',), 'comic': ('comics',)}.get(kind, ())
        items, seen = [], set()

        def add(x):
            it = self._to_simple(x, kind)
            if it and it['vod_id'] not in seen:
                seen.add(it['vod_id'])
                items.append(it)

        if isinstance(data, dict):
            for k in keys + ('list', 'records', 'data'):
                if isinstance(data.get(k), list):
                    for x in data[k]:
                        add(x)
        elif isinstance(data, list):
            for x in data:
                add(x)
        return items

    def _pagination(self, data, items, pg):
        data = data if isinstance(data, dict) else {}
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        last = 0
        for k in ('last_page', 'total_page', 'total_pages', 'page_count', 'pagecount', 'pages'):
            if data.get(k) is not None:
                try:
                    last = int(data[k])
                except Exception:
                    last = 0
                if last:
                    break
        total = 0
        for k in ('total', 'total_count', 'count'):
            if data.get(k) is not None:
                try:
                    total = int(data[k])
                except Exception:
                    total = 0
                if total:
                    break
        if not last and total:
            try:
                limit = int(data.get('limit') or PAGE_SIZE)
            except Exception:
                limit = PAGE_SIZE
            if limit > 0:
                last = max(1, (total + limit - 1) // limit)
        if not last:
            last = pg + (1 if items else 0)
        return {'list': items, 'page': pg, 'pagecount': last, 'limit': PAGE_SIZE, 'total': total or len(items)}

    def _parse_extend(self, extend):
        if isinstance(extend, dict):
            return extend
        if isinstance(extend, str) and extend.strip():
            try:
                return json.loads(extend)
            except Exception:
                return {}
        return {}

    # ---------------- 分类列表 / 搜索 ----------------

    def categoryContent(self, tid, pg, filter, extend):
        pg = str(pg or '1')
        ext = self._parse_extend(extend)
        try:
            if isinstance(tid, str) and tid.startswith('cate_'):
                # 详情页分类可点击标签 [a=cr:cate_<id>] 点击后走 categoryContent，按 cate_id 抓视频列表
                data = self._api_get('vod', {'cate_id': tid[5:], 'page': pg, 'limit': PAGE_SIZE}) or {}
                return self._pagination(data, self._parse_videos(data), pg)
            if isinstance(tid, str) and tid.startswith('vod_'):
                params = {'page': pg, 'limit': PAGE_SIZE, 'cate_id': tid[4:]}
                if ext.get('sub'):
                    params['cate_id'] = str(ext['sub'])
                    params['cate_pid'] = tid[4:]
                data = self._api_get('vod', params) or {}
                return self._pagination(data, self._parse_videos(data), pg)
            if tid == 'cg_list':
                data = self._api_get('cg', {'page': pg, 'limit': PAGE_SIZE_OTHER}) or {}
                return self._pagination(data, self._parse_simple(data, 'cg'), pg)
            if tid in ('novel', 'comic'):
                data = self._api_get(tid, {'page': pg, 'limit': PAGE_SIZE_OTHER}) or {}
                return self._pagination(data, self._parse_simple(data, tid), pg)
        except Exception:
            pass
        return {'list': [], 'page': int(pg), 'pagecount': 1, 'limit': PAGE_SIZE, 'total': 0}

    def searchContent(self, key, quick, pg='1'):
        pg = str(pg or '1')
        try:
            data = self._api_get('vod', {'name': str(key), 'page': pg, 'limit': PAGE_SIZE}) or {}
            return self._pagination(data, self._parse_videos(data), pg)
        except Exception:
            return {'list': [], 'page': int(pg), 'pagecount': 1, 'limit': PAGE_SIZE, 'total': 0}

    # ---------------- 详情 ----------------

    def _split_vod_id(self, vid):
        kind, raw = 'vod', str(vid or '')
        if '_' in raw:
            head, tail = raw.split('_', 1)
            if head in ('vod', 'cg', 'novel', 'comic'):
                kind, raw = head, tail
        m = re.search(r'(\d+)', raw)
        return kind, (m.group(1) if m else raw)

    def _vod_detail(self, raw_id, vid):
        data = self._api_get('vod/' + raw_id) or {}
        v = data.get('video') if isinstance(data.get('video'), dict) else data
        cate = v.get('cate') if isinstance(v.get('cate'), dict) else {}
        # 分类可点击标签 [a=cr:cate_<id>] 放简介(vod_content)最前面；点击后走 categoryContent 按 cate_id 抓分类列表
        content = self._cr('cate_' + str(v.get('cate_id') or cate.get('id')), str(cate.get('name'))) if cate.get('name') else ''
        return {'list': [{
            'vod_id': vid,
            'vod_name': self._clean_text(str(v.get('name') or raw_id))[:200],
            'vod_pic': self._cover(v.get('enc_img') or ''),
            'vod_remarks': '',
            'vod_content': content,
            'vod_play_from': PLAY_FROM,
            'vod_play_url': '播放$' + str(raw_id),
        }]}

    def _cg_detail(self, raw_id, vid):
        data = self._api_get('cg/' + raw_id) or {}
        cg = data.get('chigua') if isinstance(data.get('chigua'), dict) else data
        return {'list': [{
            'vod_id': vid,
            'vod_name': self._clean_text(str(cg.get('title') or raw_id))[:200],
            'vod_pic': self._cover(cg.get('enc_img') or ''),
            'vod_remarks': self._clean_text(cg.get('subtitle') or ''),
            'vod_content': str(cg.get('content') or ''),
            'vod_play_from': PLAY_FROM,
            'vod_play_url': ('播放$cg:' + str(raw_id)) if cg.get('url') else '',
        }]}

    def _book_detail(self, kind, raw_id, vid):
        data = self._api_get(kind + '/' + raw_id) or {}
        b = data.get(kind) if isinstance(data.get(kind), dict) else data
        unit = '章' if kind == 'novel' else '话'
        proto = 'novel://' if kind == 'novel' else 'manga://'
        desc = ('作者：' + str(b.get('author'))) if b.get('author') else ''
        tags = [t for t in (b.get('tag') or []) if t]
        if tags:
            ts = '  '.join(self._cr(str(t), str(t)) for t in tags)
            desc = (desc + '\n标签：' + ts) if desc else ('标签：' + ts)
        if b.get('content'):
            desc = (desc + '\n' + str(b.get('content'))) if desc else str(b.get('content'))
        ep = ''
        for ch in (b.get('chapters') or []):
            if not isinstance(ch, dict):
                continue
            cname = ch.get('name') or ('第' + str(ch.get('serial') or '') + unit)
            ep += cname + '$' + proto + json.dumps(
                {'id': raw_id, 'serial': ch.get('serial'), 'name': cname}, ensure_ascii=False) + '#'
        return {'list': [{
            'vod_id': vid,
            'vod_name': self._clean_text(str(b.get('name') or raw_id))[:200],
            'vod_pic': self._cover(b.get('enc_img') or ''),
            'vod_content': desc,
            'vod_play_from': PLAY_FROM,
            'vod_play_url': ep.rstrip('#'),
        }]}

    def detailContent(self, array):
        vid = str(array[0]) if array else ''
        try:
            if vid and '_' not in vid and not vid[:1].isdigit():
                return self.searchContent(vid, False, '1')
            kind, raw_id = self._split_vod_id(vid)
            if kind == 'vod':
                return self._vod_detail(raw_id, vid)
            if kind == 'cg':
                return self._cg_detail(raw_id, vid)
            if kind in ('novel', 'comic'):
                return self._book_detail(kind, raw_id, vid)
        except Exception:
            pass
        return {'list': []}

    # ---------------- 播放 ----------------

    def _play_cookie(self, host):
        try:
            self._fetch(host.rstrip('/') + '/', referer=host.rstrip('/') + '/', timeout=8)
        except Exception:
            pass
        try:
            ck = '; '.join('%s=%s' % (c.name, c.value) for c in self._session.cookies)
        except Exception:
            ck = ''
        return ck or 'ks_iscookie=1; ks_show_number3713=1; df_iscookie=1; df_show_number4666=1'

    def _video_play(self, url):
        url = self._fix_url(url)
        if not url:
            return {'parse': 1, 'url': '', 'header': {}}
        host = (self._host or self.site).rstrip('/')
        headers = {'User-Agent': self.ua, 'Referer': host + '/', 'Origin': host, 'Cookie': self._play_cookie(host)}
        return {'parse': 0, 'url': self.plp + url, 'header': headers}

    def playerContent(self, flag, id, vipFlags):
        sid = str(id or '')
        try:
            if sid.startswith('cg:'):
                data = self._api_get('cg/' + sid[3:]) or {}
                cg = data.get('chigua') if isinstance(data.get('chigua'), dict) else data
                return self._video_play(str(cg.get('url') or '').replace('&amp;', '&').strip())

            if sid.startswith('novel://'):
                o = json.loads(sid[len('novel://'):])
                data = self._api_get('novel/%s/chapter/%s' % (o.get('id'), o.get('serial'))) or {}
                ch = data.get('novel_chapter') if isinstance(data.get('novel_chapter'), dict) else data
                content = ''
                if ch.get('url'):
                    try:
                        r = self._fetch(str(ch.get('url')), referer=(self._host or self.site) + '/', timeout=12)
                        content = bytes([x ^ XOR_KEY for x in r.content]).decode('utf-8', 'ignore')
                    except Exception:
                        content = ''
                if not content:
                    return {'parse': 1, 'url': '', 'header': {}}
                return {'parse': 0, 'playUrl': '',
                        'url': 'novel://' + json.dumps({'title': o.get('name') or '', 'content': content}, ensure_ascii=False),
                        'header': ''}

            if sid.startswith('manga://'):
                o = json.loads(sid[len('manga://'):])
                data = self._api_get('comic/%s/chapter/%s' % (o.get('id'), o.get('serial'))) or {}
                ch = data.get('comic_chapter') if isinstance(data.get('comic_chapter'), dict) else data
                imgs = [self._cover(x) for x in (ch.get('contents') or []) if x]
                if not imgs:
                    return {'parse': 1, 'url': '', 'header': {}}
                return {'parse': 0, 'playUrl': '', 'url': 'manga://' + '&&'.join(imgs), 'header': ''}

            m = re.search(r'(\d+)', sid)
            raw_id = m.group(1) if m else sid
            data = self._api_get('vod/' + raw_id) or {}
            v = data.get('video') if isinstance(data.get('video'), dict) else data
            return self._video_play(str(v.get('url') or '').replace('&amp;', '&').strip())
        except Exception:
            return {'parse': 1, 'url': sid, 'header': {}}

    # ---------------- 封面代理（XOR 0x88 还原） ----------------

    @staticmethod
    def _looks_image(b):
        return (b[:3] == b'\xff\xd8\xff' or b[:4] == b'\x89PNG' or b[:3] == b'GIF'
                or b[:2] == b'BM' or b[:4] == b'RIFF')

    def _mime(self, body):
        if body[:3] == b'\xff\xd8\xff':
            return 'image/jpeg'
        if body[:4] == b'\x89PNG':
            return 'image/png'
        if body[:3] == b'GIF':
            return 'image/gif'
        if body[:4] == b'RIFF' and body[8:12] == b'WEBP':
            return 'image/webp'
        return 'image/jpeg'

    def localProxy(self, param):
        try:
            url = param.get('url') or '' if isinstance(param, dict) else (param if isinstance(param, str) else '')
            if not url:
                return [404, 'text/plain', b'', 'no url']
            if not url.startswith('http'):
                try:
                    url = base64.b64decode(url).decode('utf-8')
                except Exception:
                    try:
                        url = unquote(url)
                    except Exception:
                        pass
            if not url.startswith('http'):
                return [404, 'text/plain', b'', 'invalid url']
            headers = {'User-Agent': self.ua, 'Referer': (self._host or self.site).rstrip('/') + '/'}
            body = self._session.get(url, headers=headers, proxies=self.proxy, timeout=15, verify=False).content
            if body and not self._looks_image(body[:16]):
                xored = bytes([x ^ XOR_KEY for x in body])
                if self._looks_image(xored[:16]):
                    body = xored
            ctype = self._mime(body)
            extra = 'Content-Type: %s\r\nCache-Control: public, max-age=86400\r\nContent-Length: %d\r\n' % (ctype, len(body))
            return [200, ctype, body, extra]
        except Exception as e:
            return [500, 'text/plain', b'', str(e)]


if __name__ == '__main__':
    sp = Spider()
    sp.init('{}')
    print('站点:', sp.getName(), '| 域名:', sp._resolve_host())
    r = sp.homeContent(True)
    print('分类数:', len(r.get('class', [])))
    hv = sp.homeVideoContent()
    print('首页条数:', len(hv.get('list', [])))
