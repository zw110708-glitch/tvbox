# -*- coding: utf-8 -*-
"""说明：这是用于替换你原 18.py 的修复版。

核心修复（按站点源码 image.js 反推实现）：
- 站点图片（图床 https://pic.lxgkeo.cn/...）返回的是 **AES-CBC(NoPadding) 加密后的二进制**，不是 JPEG/PNG。
- 浏览器端通过 image.js：fetch 二进制 -> FileReader 转 base64 -> AES 解密 -> 得到真实图片 base64 -> 再转 blob 显示。
- 壳/播放器不会执行这段 JS，所以你看到“图片加载不出来/解密不出来”。

本脚本的做法：
- `vod_pic` 统一返回本地代理地址（type=img）
- `localProxy(type=img)` 在本地拉取加密图片并 AES 解密，返回真实图片字节 + 正确 Content-Type

注意：此脚本依赖 `pycryptodome`（Crypto.Cipher.AES）。
"""

import json
import re
import sys
from base64 import b64decode, b64encode
from urllib.parse import quote, urljoin

import requests
from pyquery import PyQuery as pq

sys.path.append('..')
try:
    from base.spider import Spider as BaseSpider
except Exception:
    # 仅用于本地自测（无壳环境时），不影响壳内正常导入
    class BaseSpider(object):
        def getProxyUrl(self):
            return ''

# 图片解密参数（来源：站点 /usr/themes/haijiao3/assets/__base/js/image.js）
# key: "f5d965df75336270"  iv: "97b60394abc2fbe1"
_IMG_AES_KEY = b'f5d965df75336270'
_IMG_AES_IV = b'97b60394abc2fbe1'


class Spider(BaseSpider):
    def init(self, extend=""):
        cfg = {}
        try:
            if isinstance(extend, str) and extend.strip():
                cfg = json.loads(extend)
            elif isinstance(extend, dict):
                cfg = extend
        except Exception:
            cfg = {}

        self.proxies = cfg.get('proxies') or {          "http": "http://127.0.0.1:10172",
          "https": "http://127.0.0.1:10172"}
        self.host = (cfg.get('host') or 'https://mitaoweb.com').strip().rstrip('/')

        # 搜索 API 域名（来自页面 localStorage apiDomain）
        self.api_domain = (cfg.get('api_domain') or 'gcocusly.com').strip()

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36',
            'Referer': self.host + '/',
        }

    def getName(self):
        return '通用视频解析器(图片AES解密修复版)'

    # ---------------- 搜索 API（请求加密/响应解密） ----------------

    _API_KEY = b'2acf7e91e9864673'
    _API_IV = b'1c29882d3ddfcfd6'
    _API_SIGN_KEY = '5589d41f92a597d016b037ac37db243d'

    def _pkcs7_pad(self, b: bytes, bs: int = 16) -> bytes:
        pad = bs - (len(b) % bs)
        return b + bytes([pad]) * pad

    def _pkcs7_unpad(self, b: bytes) -> bytes:
        if not b:
            return b
        pad = b[-1]
        if pad < 1 or pad > 16:
            return b
        return b[:-pad]

    def _api_encrypt(self, obj: dict) -> str:
        """对齐 crypto.js：AES-CBC(Pkcs7) -> base64(ciphertext)"""
        from Crypto.Cipher import AES

        s = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        cipher = AES.new(self._API_KEY, AES.MODE_CBC, self._API_IV)
        ct = cipher.encrypt(self._pkcs7_pad(s, 16))
        return b64encode(ct).decode('utf-8')

    def _api_decrypt(self, ct_b64: str, msg: str = '') -> dict:
        from Crypto.Cipher import AES

        try:
            ct = b64decode(ct_b64)
            cipher = AES.new(self._API_KEY, AES.MODE_CBC, self._API_IV)
            pt = self._pkcs7_unpad(cipher.decrypt(ct))
            return json.loads(pt.decode('utf-8', errors='ignore'))
        except Exception:
            return {'data': None, 'msg': msg, 'status': 0}

    def _api_sign(self, data_b64: str, ts: int, client: str = 'ios') -> str:
        import hashlib

        text = f'client={client}&data={data_b64}&timestamp={ts}' + self._API_SIGN_KEY
        sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
        md5 = hashlib.md5(sha.encode('utf-8')).hexdigest()
        return md5

    def _api_post(self, path: str, payload: dict) -> dict:
        """对齐 http.js：POST {client,data,sign,timestamp} 到 /api.php{path}，返回解密后的 dict"""
        import time

        ts = int(time.time())
        data_b64 = self._api_encrypt(payload)
        sig = self._api_sign(data_b64, ts)

        body = 'client=ios&data=%s&sign=%s&timestamp=%s' % (quote(data_b64, safe=''), sig, ts)
        headers = {
            'User-Agent': self.headers.get('User-Agent'),
            'Referer': self.host + '/',
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        last_err = None
        # 站点 app.config.js：随机 apiv1~apiv3
        for i in (1, 2, 3):
            url = f'https://apiv{i}.{self.api_domain}/api.php{path}'
            try:
                r = requests.post(url, data=body, headers=headers, proxies=self.proxies, timeout=20)
                if r.status_code != 200:
                    last_err = f'http {r.status_code}'
                    continue
                j = r.json()
                dec = self._api_decrypt(j.get('data') or '', j.get('msg') or '')
                return dec
            except Exception as e:
                last_err = str(e)
                continue

        return {'data': None, 'status': 0, 'msg': last_err or 'api_failed'}

    # ---------------- 文本纠错/过滤 ----------------

    def _fix_mojibake(self, s: str) -> str:
        """修复 UTF-8 被当 latin-1 显示的乱码（例如：æ æ¯）。

        策略：尝试 latin-1 -> utf-8 反解；若反解后中文字符更多，则采用反解结果。
        """
        s = (s or '').strip()
        if not s:
            return ''

        def cjk_count(x: str) -> int:
            return sum(1 for ch in x if '\u4e00' <= ch <= '\u9fff')

        try:
            fixed = s.encode('latin-1', errors='ignore').decode('utf-8', errors='ignore').strip()
        except Exception:
            return s

        return fixed if cjk_count(fixed) > cjk_count(s) else s


    def isVideoFormat(self, url):
        u = (url or '').lower()
        return any(x in u for x in ('.m3u8', '.mp4', '.ts', '.flv', '.mkv', '.avi', '.webm'))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ---------------- 首页/分类/搜索 ----------------

    def homeContent(self, _filter):
        doc = self._get(self.host + '/')

        # 站点“分类”真实直连一般在菜单里（/category/...、/order/today/ 等）。
        # 之前抓 ul.tags 容易混入标签/订阅/作者等入口，导致“分类内容串台”。
        classes = []
        seen = set()

        # 优先：菜单/分类入口
        for a in doc('a[href^="/category/"], a[href^="/order/"] , a[href^="/tag/"] , a[href^="/tags/"]').items():
            name = (a.text() or '').strip()
            href = (a.attr('href') or '').strip()
            if not name or not href:
                continue

            # 只保留明确可直达列表的入口：category 与 today；
            # tags(tag聚合页) 容易是导航页而不是列表页，这里默认不作为分类。
            if href.startswith('/category/'):
                pass
            elif href == '/order/today/':
                pass
            else:
                continue

            if name in ('我的订阅', '全部分类'):
                continue

            href = self._norm_path(href)
            if not href or href in seen:
                continue
            seen.add(href)
            classes.append({'type_name': name, 'type_id': href})
            if len(classes) >= 30:
                break

        # 兜底：至少给首页
        if not classes:
            classes = [{'type_name': '蜜桃首页', 'type_id': '/'}]

        return {
            'class': classes,
            'filters': {},
            'list': self.getlist(doc, tid='/'),
        }

    def homeVideoContent(self):
        return {'list': self.homeContent(None).get('list', [])}

    def categoryContent(self, tid, pg, _filter, extend):
        pg = int(pg or 1)

        # tid 可能是相对路径或绝对链接
        tid = self._norm_path(tid or '/')
        tid = self._strip_paged_suffix(tid)
        base = urljoin(self.host + '/', tid.lstrip('/'))

        url = self._build_paged_url(base, tid, pg)
        doc = self._get(url)
        videos = self.getlist(doc, tid=tid)
        return {'list': videos, 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}

    def searchContent(self, key, quick, pg='1'):
        """搜索功能（深入解析后的“API 解密”实现）：

        前端逻辑：$Http.post('/api/tcontent/searchContents', {word,limit,page})
        - 请求参数会先 AES-CBC(Pkcs7) 加密，再按 client/data/sign/timestamp form 提交
        - 响应 data 字段是 AES 加密串，需要解密得到 {status,data:{list,total}}
        """
        pg = int(pg or 1)
        limit = 90

        dec = self._api_post('/api/tcontent/searchContents', {'word': str(key), 'limit': limit, 'page': pg})
        if not isinstance(dec, dict) or dec.get('status') != 1:
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': limit, 'total': 0}

        data = dec.get('data') or {}
        items = data.get('list') or []
        videos = []
        seen = set()

        for it in items:
            cid = it.get('cid')
            title = self._fix_mojibake((it.get('title') or '').strip())
            if not cid or not title:
                continue

            vid = f'{self.host}/archives/{cid}/'
            if vid in seen:
                continue
            seen.add(vid)

            # API 返回 images 为图床直链（仍需走本地代理解密才能在壳里显示）
            img = ''
            imgs = it.get('images') or []
            if isinstance(imgs, list) and imgs:
                img = str(imgs[0]).strip()
            if img:
                img = self.proxy(img, type='img')

            videos.append({'vod_id': vid, 'vod_name': title, 'vod_pic': img, 'vod_remarks': ''})
            if len(videos) >= limit:
                break

        total = data.get('total') if isinstance(data.get('total'), int) else len(videos)
        return {'list': videos, 'page': pg, 'pagecount': 9999, 'limit': limit, 'total': total}

    # ---------------- 详情/播放 ----------------

    def detailContent(self, ids):
        """详情页：补齐演员/标签/视频介绍，并保留原有通用播放解析。"""
        try:
            url = ids[0]
            if not url.startswith('http'):
                url = urljoin(self.host + '/', url.lstrip('/'))

            html = self._get_text(url)
            doc = self.getpq(html)

            title = self._fix_mojibake((doc('h1').text() or doc('title').text()).strip())

            # ---------------- 演员（可点击） ----------------
            actors = []
            actor_seen = set()

            def add_actor(name, href):
                name = self._fix_mojibake(name)
                href = self._fix_mojibake(href)
                if not name or not href:
                    return
                href = self._norm_path(href)
                key = name + '|' + href
                if key in actor_seen:
                    return
                actor_seen.add(key)

                # 壳通常更喜欢 id 是 URL 编码后的路径
                href_q = quote(href, safe='/:?=&%')
                actors.append('[a=cr:%s/]%s[/a]' % (
                    json.dumps({"id": href_q, "name": name}, ensure_ascii=False, separators=(',', ':')),
                    name,
                ))

            # 适配你给的片段：/author/410/ + h2
            for a in doc('a[href^="/author/"]').items():
                name = (a.find('h2').text() or a.text() or '').strip()
                href = a.attr('href')
                # 避免把“发布/浏览”等也误判为演员
                if name and len(name) <= 30:
                    add_actor(name, href)

            # 兼容旧选择器（参考代码里 .model a / .model-name）
            for a in doc('.model a').items():
                name = (a('.model-name').text() or a.text() or '').strip()
                href = a.attr('href')
                add_actor(name, href)

            vod_actor = ' '.join(actors)

            # ---------------- 标签（可点击） + 视频介绍 ----------------
            tags = []
            tag_seen = set()

            def add_tag(name, href):
                name = self._fix_mojibake(name)
                href = self._fix_mojibake(href)
                if not name or not href:
                    return
                href = self._norm_path(href)
                key = name + '|' + href
                if key in tag_seen:
                    return
                tag_seen.add(key)

                href_q = quote(href, safe='/:?=&%')
                tags.append('[a=cr:%s/]%s[/a]' % (
                    json.dumps({"id": href_q, "name": name}, ensure_ascii=False, separators=(',', ':')),
                    name,
                ))

            # 适配你给的片段：.tags-group2 a[href^="/tag/"]
            for a in doc('.tags-group2 a[href^="/tag/"]').items():
                add_tag(a.text(), a.attr('href'))

            # 兜底：只要是 /tag/ 的链接都算标签（避免 class 变更导致漏抓）
            if not tags:
                for a in doc('a[href^="/tag/"]').items():
                    add_tag(a.text(), a.attr('href'))

            # 兼容旧选择器（参考代码里 span.ctg a）
            for ctg_span in doc('span.ctg').items():
                a = ctg_span.find('a')
                if a:
                    add_tag(a.text(), a.attr('href'))


            content_parts = []
            if tags:
                content_parts.append('标签: ' + ' '.join(tags))


            # 壳端有的对换行支持不一致，这里用换行分隔（标签行 + 简介行），并确保纯文本不夹杂 URL 广告
            vod_content = ('\n'.join([x for x in content_parts if x])).strip() or title

            # ---------------- 通用播放源抓取（原逻辑保留） ----------------
            plist = []
            seen = set()

            def add_play(name, u):
                if not u:
                    return
                u = u.strip()
                if not u.startswith('http'):
                    u = urljoin(url, u)
                if u in seen:
                    return
                seen.add(u)
                plist.append('%s$%s' % (name, u))

            for v in doc('video').items():
                add_play('video', v.attr('src'))
                for s in v('source').items():
                    add_play('source', s.attr('src'))

            for s in doc('script').items():
                t = s.text() or ''
                ms = re.findall(r'(https?://[^\s\"\']+\.(?:m3u8|mp4)[^\s\"\']*)', t, flags=re.I)
                for m in ms[:3]:
                    add_play('script', m)

            for f in doc('iframe').items():
                add_play('iframe', f.attr('src') or f.attr('data-src'))

            play_url = '#'.join(plist) if plist else ('网页播放$%s' % url)

            vod = {
                'vod_id': url,
                'vod_name': self._fix_mojibake(title) or url,
                'vod_play_from': '通用解析',
                'vod_play_url': play_url,
                'vod_content': vod_content,
            }
            if vod_actor:
                vod['vod_actor'] = vod_actor

            return {'list': [vod]}
        except Exception:
            return {'list': [{'vod_play_from': '通用解析', 'vod_play_url': '获取失败'}]}

    def playerContent(self, flag, id, vipFlags):
        parse = 0 if self.isVideoFormat(id) else 1
        url = self.proxy(id, type='m3u8') if ('.m3u8' in (id or '') and self.proxies) else id
        return {'parse': parse, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{url}', 'header': self.headers}

    # ---------------- 本地代理（关键：img 解密） ----------------

    def localProxy(self, param):
        try:
            t = (param or {}).get('type')
            u = (param or {}).get('url')
            url = self.d64(u)

            if t == 'm3u8':
                r = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=10)
                return [r.status_code, 'application/vnd.apple.mpegurl', r.text]

            if t == 'ts':
                r = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=10)
                return [r.status_code, 'video/mp2t', r.content]

            if t == 'img':
                r = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=15)
                if r.status_code != 200 or not r.content:
                    return [r.status_code, 'text/plain', b'']
                img_bytes = self._decrypt_image_bytes(r.content)
                ct = self._guess_img_content_type(url, img_bytes)
                return [200, ct, img_bytes]

            return [404, 'text/plain', b'']
        except Exception:
            return [404, 'text/plain', b'']

    def proxy(self, data, type='m3u8'):
        if not data:
            return data
        return '%s&url=%s&type=%s' % (self.getProxyUrl(), self.e64(data), type)

    def e64(self, text):
        return b64encode(str(text).encode('utf-8')).decode('utf-8')

    def d64(self, text):
        return b64decode(str(text).encode('utf-8')).decode('utf-8')

    # ---------------- URL 规范化/分页 ----------------

    def _norm_path(self, href: str) -> str:
        """把 tid/href 统一成以 / 开头的站内路径（去掉 host、query、#）。"""
        href = (href or '').strip()
        if not href:
            return ''
        # 去掉反引号（站点里偶发用 `url` 包住）
        href = href.strip('`').strip('"').strip("'")

        # 绝对链接 -> 相对路径
        if href.startswith('http'):
            try:
                m = re.match(r'^https?://[^/]+(.*)$', href)
                href = m.group(1) if m else href
            except Exception:
                pass

        # 只保留 path
        href = href.split('#', 1)[0]
        href = href.split('?', 1)[0]

        if not href.startswith('/'):
            href = '/' + href
        # 站内首页统一 /
        if href in ('', '//'):
            href = '/'
        return href

    def _strip_paged_suffix(self, tid_path: str) -> str:
        """防止 tid 自带 page 段，导致翻页时重复拼接。"""
        t = (tid_path or '').strip()
        if not t:
            return t

        # /order/today/page/2/ -> /order/today/
        t = re.sub(r'(/page/\d+/?$)', '/', t)

        # /category/xxx/2/ -> /category/xxx/
        if t.startswith('/category/') or t.startswith('/tag/'):
            t = re.sub(r'/\d+/?$', '/', t)

        # 规整双斜杠
        t = re.sub(r'//+', '/', t)
        if not t.startswith('/'):
            t = '/' + t
        return t

    def _build_paged_url(self, base_abs: str, tid_path: str, pg: int) -> str:
        """根据不同列表类型生成翻页 URL。"""
        # 首页：/page/2/
        if tid_path in ('/', ''):
            return self.host + '/' if pg == 1 else (self.host + '/page/%s/' % pg)

        # 分类页：/category/xxx/2/
        if tid_path.startswith('/category/'):
            return (base_abs.rstrip('/') + '/') if pg == 1 else (base_abs.rstrip('/') + '/%s/' % pg)

        # 标签页：/tag/xxx/2/
        if tid_path.startswith('/tag/'):
            return (base_abs.rstrip('/') + '/') if pg == 1 else (base_abs.rstrip('/') + '/%s/' % pg)

        # 今日更新等排序页：/order/today/page/2/
        if tid_path.startswith('/order/'):
            return (base_abs.rstrip('/') + '/') if pg == 1 else (base_abs.rstrip('/') + '/page/%s/' % pg)

        # 默认：按 WP 风格 /page/2/
        return (base_abs.rstrip('/') + '/') if pg == 1 else (base_abs.rstrip('/') + '/page/%s/' % pg)

    # ---------------- 列表/图片 ----------------

    def getlist(self, data_pq, tid=''):
        videos = []
        seen = set()

        # 只抓主列表区域，避免把“热榜/推荐”等模块的 archives 混进分类结果
        scope = data_pq
        if data_pq('.main-container').length:
            scope = data_pq('.main-container')
        elif data_pq('.xqbj-list').length:
            scope = data_pq('.xqbj-list')

        items = scope('a[href*="/archives/"]')
        if len(items) == 0:
            items = data_pq('article a[href]')
        if len(items) == 0:
            items = data_pq('a[href]:has(img)')

        for a in items.items():
            href = (a.attr('href') or '').strip()
            if not href or href in ('#', '/', ''):
                continue
            if '/archives/' not in href and href.startswith('/') and tid == '/':
                continue

            title = (a.attr('title') or a.find('img').attr('alt') or a.text() or '').strip()
            if len(title) < 2:
                continue

            # 屏蔽分类/首页列表中的广告与导流内容
            # （示例：直播、18YAOBA 等）
            bad_kw = (
                '直播', '18YAOBA', '官方约炮','YAOBA', 'yaoba',
                '广告', '推广', '充值', 'VIP', '高端约炮','官方群', '加群',
            )
            if any(k.lower() in title.lower() for k in bad_kw):
                continue

            img = self.getimg(a)
            if not img:
                continue

            if not href.startswith('http'):
                href = urljoin(self.host + '/', href.lstrip('/'))

            # 进一步按链接过滤广告/导流
            href_l = href.lower()
            if any(x in href_l for x in ('yaoba', '/live', 'zhibo', 'ads', 'ad=')):
                continue

            if href in seen:
                continue
            seen.add(href)

            videos.append({'vod_id': href, 'vod_name': title, 'vod_pic': img, 'vod_remarks': ''})
            if len(videos) >= 90:
                break

        return videos

    def getimg(self, a):
        img = a.find('img')
        if not img or len(img) == 0:
            return ''

        # API 解密方式：只使用 z-image-loader-url（真实加密图片地址）
        u = (img.attr('z-image-loader-url') or '').strip().strip('`').strip('"').strip("'")
        if not u:
            return ''

        if u.startswith('//'):
            u = 'https:' + u
        elif not u.startswith('http'):
            u = urljoin(self.host + '/', u.lstrip('/'))

        # 关键：封面必须走本地代理，让 localProxy(type=img) 解密后再返回
        return self.proxy(u, type='img')

    # ---------------- 图片解密实现 ----------------

    def _guess_img_content_type(self, url, img_bytes: bytes):
        if img_bytes.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg'
        if img_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'image/png'
        if img_bytes.startswith(b'GIF87a') or img_bytes.startswith(b'GIF89a'):
            return 'image/gif'
        if img_bytes.startswith(b'RIFF') and b'WEBP' in img_bytes[:16]:
            return 'image/webp'

        u2 = (url or '').lower().split('?', 1)[0]
        if u2.endswith('.png'):
            return 'image/png'
        if u2.endswith('.webp'):
            return 'image/webp'
        if u2.endswith('.gif'):
            return 'image/gif'
        return 'image/jpeg'

    def _decrypt_image_bytes(self, ciphertext: bytes) -> bytes:
        """AES-CBC(NoPadding) 解密，完全对齐站点 image.js 的 decryptjs 逻辑。"""
        try:
            from Crypto.Cipher import AES
        except Exception:
            return ciphertext

        if not ciphertext:
            return b''

        if len(ciphertext) % 16 != 0:
            pad = 16 - (len(ciphertext) % 16)
            ciphertext = ciphertext + (b'\x00' * pad)

        cipher = AES.new(_IMG_AES_KEY, AES.MODE_CBC, _IMG_AES_IV)
        plaintext = cipher.decrypt(ciphertext)
        return plaintext.rstrip(b'\x00')

    # ---------------- HTTP 封装 ----------------

    def getpq(self, data):
        try:
            return pq(data)
        except Exception:
            return pq((data or '').encode('utf-8'))

    def _get(self, url):
        return self.getpq(self._get_text(url))

    def _get_text(self, url):
        r = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=10)
        if r.status_code != 200:
            return ''

        # 彻底规避 requests 的编码猜测/缓存：直接用 bytes 按 UTF-8 解码。
        # 你看到的“ä¸­åº”= UTF-8 字节被当 latin-1 显示的典型症状。
        try:
            return (r.content or b'').decode('utf-8', errors='ignore')
        except Exception:
            # 兜底
            r.encoding = 'utf-8'
            return r.text
