# -*- coding: utf-8 -*-
"""
绿帽社区网 (lvmaos.com) —— catvod / OK影视 爬虫
站点：WordPress，列表走加密 API（apiv1~3.<api_domain>/api.php），
      视频源在详情页 .dplayer 的 data-config 里；api_domain 从首页 HTML 动态更新。
图片：封面多为 AES 加密 data-URI，本地解密后内存缓存，经 localProxy 输出。

代理规则（老郑统一约定）：
  1) 内部请求（_get/_post/localProxy 抓数据）走 self.proxy，没传就直连；
  2) 播放地址加 self.plp 前缀回源；
  3) 加密图片走 localProxy 解密，图片地址用 getProxyUrl() 构造 type 分发 URL。
"""
import json
import re
import sys
import time
import hashlib
from base64 import b64decode, b64encode
from urllib.parse import quote, urljoin, urlparse

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider

# 图片解密后的内存缓存
_img_cache = {}

_DEFAULT_HOST = 'https://lvmaos.com'
_DEFAULT_API_DOMAIN = 'ooloylfs.xyz'
_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

# API 加密参数（海角系同款，改动会导致接口失效）
_API_KEY = b'2acf7e91e9864673'
_API_IV = b'1c29882d3ddfcfd6'
_API_SIGN_KEY = '5589d41f92a597d016b037ac37db243d'

# 图片解密尝试的 (key, iv) 组合与常见图片文件头
_IMG_KEYS = (
    (b'f5d965df75336270', b'97b60394abc2fbe1'),
    (b'75336270f5d965df', b'abc2fbe197b60394'),
)
_IMG_MAGIC = (b'\xff\xd8', b'\x89PNG', b'GIF8')


class Spider(Spider):
    def init(self, extend="{}"):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}

        self.host = (config.get('site') or _DEFAULT_HOST).strip().rstrip('/')
        self.plp = config.get('plp', '')        # 播放器/图片 URL 前缀，空=直连
        self.proxy = config.get('proxy', {})    # 内部请求代理，空=直连

        self.headers = {
            'User-Agent': _UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Origin': self.host,
            'Referer': self.host + '/',
        }

        self.api_domain = config.get('api_domain') or _DEFAULT_API_DOMAIN
        self.api_bases = ['https://apiv%d.%s/api.php' % (i, self.api_domain) for i in (1, 2, 3)]
        self.session = requests.Session()

    # ---------------- 生命周期 ----------------
    def getName(self):
        return '绿帽社区网'

    def isVideoFormat(self, url):
        return bool(url and re.search(r'\.(m3u8|mp4|ts|flv|mkv|avi|webm)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        _img_cache.clear()
        s = getattr(self, 'session', None)
        if s:
            try:
                s.close()
            except Exception:
                pass

    # ---------------- HTTP ----------------
    def _get(self, url, timeout=15):
        return self.session.get(url, headers=self.headers, proxies=self.proxy, timeout=timeout)

    def _post(self, url, data, timeout=20, headers=None):
        return self.session.post(url, data=data, headers=headers or {}, proxies=self.proxy, timeout=timeout)

    @staticmethod
    def _decode_html(content, headers=None):
        if not content:
            return ''
        ctype = (headers or {}).get('Content-Type', '')
        m = re.search(r'charset\s*=\s*([\w\-]+)', ctype, re.I)
        if m:
            try:
                return content.decode(m.group(1), errors='replace')
            except Exception:
                pass
        for enc in ('utf-8', 'gb18030'):
            try:
                return content.decode(enc)
            except Exception:
                pass
        return content.decode('utf-8', errors='replace')

    def _rtext(self, r):
        try:
            return self._decode_html(r.content, getattr(r, 'headers', None))
        except Exception:
            return ''

    @staticmethod
    def getpq(data):
        try:
            return pq(data)
        except Exception:
            return pq(data.encode('utf-8'))

    # ---------------- 工具 ----------------
    @staticmethod
    def _fix_text(s):
        if not s:
            return ''
        s = str(s).strip()
        if any(c in s for c in ('Ã', 'Â', 'æ', 'å', 'ä', 'è', '£', 'ð', 'Ÿ', '™', '\ufffd')):
            for enc in ('latin1', 'cp1252'):
                try:
                    s2 = s.encode(enc, errors='ignore').decode('utf-8', errors='ignore').strip()
                    if s2 and not any(c in s2 for c in ('Ã', 'Â', '\ufffd')):
                        return s2
                except Exception:
                    pass
        return s

    @staticmethod
    def _safe_int(v, default=1):
        try:
            return int(v)
        except Exception:
            return default

    @staticmethod
    def _pick(adict, *keys, default=''):
        if not isinstance(adict, dict):
            return default
        for k in keys:
            v = adict.get(k)
            if v:
                return v
        return default

    @staticmethod
    def _cr_tag(href, name):
        target = json.dumps({'id': href, 'name': name}, ensure_ascii=False)
        return '[a=cr:%s/]%s[/a]' % (target, name)

    def _make_abs(self, href):
        href = (href or '').strip().strip('"\'`')
        if not href:
            return ''
        if href.startswith('http'):
            return href
        return self.host + href if href.startswith('/') else self.host + '/' + href

    def _v(self, vid, name, pic='', remark=''):
        return {
            'vod_id': vid,
            'vod_name': self._fix_text(name),
            'vod_pic': pic,
            'vod_remarks': remark,
            'style': {'type': 'rect', 'ratio': 1.33},
        }

    @staticmethod
    def _page_result(lst, page, pagecount, limit, total):
        return {'list': lst, 'page': page, 'pagecount': pagecount, 'limit': limit, 'total': total}

    # ---------------- API 加解密 ----------------
    def _update_api_domain(self, text):
        text = text or ''
        m = re.search(r"apiDomain\s*'\s*,\s*'([^']+)'", text) or \
            re.search(r"localStorage\.setItem\(\s*'apiDomain'\s*,\s*'([^']+)'\s*\)", text)
        if m:
            d = m.group(1).strip()
            if d and d != self.api_domain:
                self.api_domain = d
                self.api_bases = ['https://apiv%d.%s/api.php' % (i, d) for i in (1, 2, 3)]

    @staticmethod
    def _api_encrypt(obj):
        raw = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        return b64encode(AES.new(_API_KEY, AES.MODE_CBC, _API_IV).encrypt(pad(raw, 16))).decode('utf-8')

    @staticmethod
    def _api_decrypt(b64_s):
        raw = AES.new(_API_KEY, AES.MODE_CBC, _API_IV).decrypt(b64decode(b64_s))
        return json.loads(unpad(raw, 16).decode('utf-8'))

    @staticmethod
    def _api_sign(client, data_b64, ts):
        text = 'client=%s&data=%s&timestamp=%s%s' % (client, data_b64, ts, _API_SIGN_KEY)
        return hashlib.md5(hashlib.sha256(text.encode('utf-8')).hexdigest().encode('utf-8')).hexdigest()

    def _api_post(self, path, params):
        """加密 API 请求：apiv1→3 轮询，第一个成功即返回。"""
        payload = {
            'bundleId': 'com.pwa.Chaguaner', 'version': '3.3.1',
            'oauth_id': '', 'oauth_type': 'web', 'language': 'zh', 'via': 'pch', 'token': '',
        }
        payload.update(params or {})

        ts = int(time.time())
        enc = self._api_encrypt(payload)
        sign = self._api_sign('ios', enc, ts)
        form = 'client=ios&data=%s&sign=%s&timestamp=%d' % (quote(enc, safe=''), sign, ts)

        for base in self.api_bases:
            url = base.rstrip('/') + (path if path.startswith('/') else '/' + path)
            try:
                r = self._post(url, form, headers={'User-Agent': _UA, 'Content-Type': 'application/x-www-form-urlencoded'})
                dec = self._api_decrypt(r.json().get('data') or '')
            except Exception:
                continue
            if dec.get('status') == 1:
                return dec.get('data') or {}
        return {}

    def _api_item(self, it):
        """把 API 返回的条目转成标准视频结构。"""
        slug = str(self._pick(it, 'slug', 'cid')).strip()
        title = self._fix_text(it.get('title') or '')
        if not slug or not title:
            return None
        images = it.get('images') or []
        pic = images[0] if isinstance(images, list) and images else ''
        return self._v(urljoin(self.host + '/', 'archives/%s/' % slug), title,
                       self._pic(str(pic)) if pic else '')

    # ---------------- 首页 / 分类 ----------------
    def homeContent(self, filter):
        try:
            r = self._get(self.host, timeout=10)
            if r.status_code != 200:
                return {'class': [], 'list': []}
            text = self._rtext(r)
            self._update_api_domain(text)
            doc = self.getpq(text)
            return {'class': self._classes(doc), 'list': self.getlist(doc)}
        except Exception:
            return {'class': [], 'list': []}

    def homeVideoContent(self):
        return {'list': self.homeContent(None).get('list', [])}

    def _classes(self, doc):
        out, seen = [], set()
        for a in doc('#collapseTag1Stop .tags a').items():
            name = (a.text() or '').strip()
            href = (a.attr('href') or '').strip()
            if not name or name in ('绿帽社社区', '我的订阅'):
                continue
            if not href or href == '#' or 'javascript' in href:
                continue
            if not href.startswith('/'):
                href = urljoin(self.host + '/', href).replace(self.host, '')
            if href in seen:
                continue
            seen.add(href)
            out.append({'type_name': name, 'type_id': href})
        return out

    def _tag_path(self, value):
        value = (value or '').strip()
        if value.startswith('http'):
            value = urlparse(value).path
        if not value.startswith('/tag/'):
            return value
        name = self._fix_text(value[5:].strip('/'))
        if re.search(r'%[0-9A-Fa-f]{2}', name):
            return '/tag/%s/' % name
        return '/tag/%s/' % quote(name, safe='')

    def _build_url(self, tid, page):
        tid = tid or '/'
        if tid.startswith('http'):
            tid = urlparse(tid).path
        if tid.startswith('/tag/'):
            tid = self._tag_path(tid)
        if tid == '/':
            return '%s/page/%d/' % (self.host, page) if page > 1 else self.host + '/'
        path = tid.rstrip('/') + '/'
        if page < 2:
            return self.host + path
        if path.startswith('/order/'):
            return self.host + path + 'page/%d/' % page
        return self.host + path + '%d/' % page

    def categoryContent(self, tid, pg, filter, extend):
        page = self._safe_int(pg, 1)
        try:
            if (tid or '').startswith('/author/'):
                return self._author_list(tid, page)
            r = self._get(self._build_url(tid, page), timeout=15)
            if r.status_code != 200:
                return self._page_result([], page, 1, 90, 0)
            doc = self.getpq(self._rtext(r))
            pagecount = self._pagecount(doc, page)
            return self._page_result(self.getlist(doc), page, pagecount, 90, pagecount * 90)
        except Exception:
            return self._page_result([], page, 1, 90, 0)

    def _author_list(self, tid, page):
        m = re.search(r'^/author/(\d+)/', tid)
        if not m:
            return self._page_result([], page, 1, 20, 0)
        data = self._api_post('/api/tcontent/author_contents',
                              {'sort': 'new', 'uid': int(m.group(1)), 'page': page, 'limit': 20})
        total = int(data.get('total') or 0) if isinstance(data, dict) else 0
        items = [x for x in (self._api_item(i) for i in (data.get('list') or [])) if x]
        pagecount = max(1, (total + 19) // 20) if total else 9999
        return self._page_result(items, page, pagecount, 20, total)

    def _pagecount(self, doc, page):
        nums = []
        for a in doc('.van-pagination__item--page a, a.page-numbers, .pagination a, .wp-pagenavi a').items():
            t = (a.text() or '').strip()
            if t.isdigit():
                nums.append(int(t))
        has_next = doc('link[rel="next"], li.van-pagination__item.next a[href], '
                       'a.next, a.page-numbers.next, .pagination a[rel="next"]').length
        return max(nums) if nums else (page + 1 if has_next else page)

    # ---------------- 详情 ----------------
    def detailContent(self, ids):
        url = ids[0] if ids[0].startswith('http') else self.host + ids[0]
        try:
            r = self._get(url, timeout=15)
            if r.status_code != 200:
                raise Exception('http %d' % r.status_code)
            return {'list': [self._detail(self.getpq(self._rtext(r)), url)]}
        except Exception:
            return {'list': [{'vod_play_from': '绿帽社区网', 'vod_play_url': '获取失败'}]}

    def _detail(self, doc, url):
        title = self._fix_text(doc('h1').text() or doc('.novel-title').text())

        # 播放源（.dplayer 的 data-config，优先 video_h265，退回 video）
        play = []
        cfg = doc('.dplayer').eq(0).attr('data-config') or ''
        if cfg:
            try:
                js = json.loads(cfg)
            except Exception:
                js = {}
            v = js.get('video_h265')
            vurl = v.get('url', '') if isinstance(v, dict) else ''
            if not vurl:
                vurl = (js.get('video') or {}).get('url', '')
            vurl = (vurl or '').strip()
            if vurl:
                play.append('播放$' + (vurl if vurl.startswith('http') else urljoin(self.host, vurl)))

        p0 = doc('.text-content img[data-image-preview][z-image-loader-url], '
                 '.defaultimg img[z-image-loader-url]').eq(0)
        pic = self._pic(((p0.attr('z-image-loader-url') or '').strip()).strip('`'))

        cat = doc('.detail-info-desc a[href^="/category/"]').eq(0)
        type_name = self._fix_text(cat.text())
        type_id = (cat.attr('href') or '').strip()

        spans = [self._fix_text(s.text()) for s in doc('.detail-info-desc span').items() if (s.text() or '').strip()]
        pub = next((s for s in spans if '发布' in s), '')
        views = next((s for s in spans if '浏览' in s), '')
        remark = ' | '.join(x for x in (type_name, views, pub) if x)

        year = ''
        m = re.search(r'(20\d{2})', pub)
        if m:
            year = m.group(1)

        # 作者（可点击）
        director = ''
        au = doc('.nav-user a[href^="/author/"]').eq(0)
        ah = (au.attr('href') or '').strip()
        an = self._fix_text(doc('.nav-user h2').eq(0).text() or au.text())
        if ah and an:
            director = self._cr_tag(urljoin(self.host + '/', ah.lstrip('/')), an)

        # 标签（可点击）
        tags, tag_names = [], []
        for a in doc('.tags-group2 a[href^="/tag/"]').items():
            href = self._tag_path((a.attr('href') or '').strip())
            name = self._fix_text(a.text())
            if href and name:
                tag_names.append(name)
                tags.append(self._cr_tag(urljoin(self.host + '/', href.lstrip('/')), name))

        intro = self._fix_text(doc('meta[name="description"]').attr('content') or '')
        content = ('标签: ' + ' '.join(tags) + '\n' + intro).strip() if tags else intro

        item = {
            'vod_id': url,
            'vod_name': title,
            'vod_pic': pic,
            'type_name': type_name,
            'type_id': type_id,
            'vod_year': year,
            'vod_remarks': remark,
            'vod_director': director,
            'vod_play_from': '绿帽社区网',
            'vod_play_url': '#'.join(play) if play else '未找到视频源$null',
            'vod_content': content or title,
        }
        if tag_names:
            item['vod_tag'] = ' '.join(tag_names)
        return item

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick, pg="1"):
        page = self._safe_int(pg, 1)
        word = self._fix_text(str(key))
        if not word:
            return self._page_result([], page, 1, 20, 0)
        try:
            data = self._api_post('/api/tcontent/searchContents', {'word': word, 'page': page, 'limit': 20})
            total = int(data.get('total') or 0) if isinstance(data, dict) else 0
            items = [x for x in (self._api_item(i) for i in (data.get('list') or [])) if x]
            pagecount = max(1, (total + 19) // 20) if total else 9999
            return self._page_result(items, page, pagecount, 20, total)
        except Exception:
            return self._page_result([], page, 1, 20, 0)

    # ---------------- 播放 ----------------
    def playerContent(self, flag, id, vipFlags):
        url = (id or '').strip()
        if not url or url.lower() in ('null', 'none', '获取失败'):
            return {'parse': 0, 'url': '', 'header': self.headers}
        return {'parse': 0, 'url': self.plp + url, 'header': self.headers}

    # ---------------- 图片 ----------------
    def localProxy(self, param):
        try:
            t = param.get('type')
            if t == 'cache':
                content = _img_cache.get(param.get('key'))
                return [200, 'image/jpeg', content] if content else [404, 'text/plain', b'Expired']
            if t == 'img':
                url = param.get('url')
                real = self.d64(url) if url and not str(url).startswith('http') else url
                content = self.aesimg(requests.get(real, headers=self.headers, proxies=self.proxy, timeout=10).content)
                ctype = 'image/jpeg'
                if content.startswith(b'\x89PNG'):
                    ctype = 'image/png'
                elif content.startswith(b'GIF8'):
                    ctype = 'image/gif'
                return [200, ctype, content]
        except Exception:
            pass
        return [404, 'text/plain', b'']

    @staticmethod
    def e64(text):
        return b64encode(str(text).encode()).decode()

    @staticmethod
    def d64(text):
        return b64decode(str(text).encode()).decode()

    @staticmethod
    def aesimg(data):
        if not data or len(data) < 16:
            return data
        for k, v in _IMG_KEYS:
            for mode in (AES.MODE_CBC, AES.MODE_ECB):
                try:
                    cipher = AES.new(k, mode, v) if mode == AES.MODE_CBC else AES.new(k, mode)
                    dec = unpad(cipher.decrypt(data), 16)
                    if dec.startswith(_IMG_MAGIC):
                        return dec
                except Exception:
                    continue
        return data

    def _pic(self, url):
        if not url:
            return ''
        url = str(url).strip('"\'` ')
        if url.startswith('data:'):
            try:
                raw = b64decode(url.split(',', 1)[1])
                if not raw.startswith(_IMG_MAGIC):
                    raw = self.aesimg(raw)
                key = hashlib.md5(raw).hexdigest()
                _img_cache[key] = raw
                return '%s&type=cache&key=%s' % (self.getProxyUrl(), key)
            except Exception:
                return ''
        if not url.startswith('http'):
            url = self._make_abs(url)
        return '%s&url=%s&type=img' % (self.getProxyUrl(), self.e64(url))

    # ---------------- 列表 ----------------
    def getlist(self, doc):
        out, seen = [], set()
        for row in doc('.xqbj-list .xqbj-list-rows').items():
            a = row('a[href^="/archives/"]').eq(0)
            href = (a.attr('href') or '').strip()
            rel = (a.attr('rel') or '')
            cls = (a.attr('class') or '')
            if not href or 'sponsored' in rel or 'nofollow' in rel:
                continue
            if 'tjtagmanager' in cls or a.attr('data-event') == 'ad_click':
                continue
            vid = urljoin(self.host + '/', href)
            name = (a.attr('title') or '').strip()
            pic = self.getimg(row)
            if not name or not pic or vid in seen:
                continue
            seen.add(vid)
            out.append(self._v(vid, name, pic, (row.find('time').text() or '').strip()))
        return out

    def getimg(self, row):
        img = row('img[z-image-loader-url], img[x-image-loader-url]').eq(0)
        url = ((img.attr('z-image-loader-url') or img.attr('x-image-loader-url') or '').strip()).strip('`')
        return self._pic(url) if url else ''
