import json
import re
import sys
import hashlib
from base64 import b64decode, b64encode
from urllib.parse import urljoin, quote

import requests
import time
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

sys.path.append('..')
from base.spider import Spider as BaseSpider

_img_cache = {}


class Spider(BaseSpider):
    """xhssex.com 精准极简解析（v4）

v6 变更：
    - 分类目录增加“首页”，并屏蔽“我的订阅”
    - 分类列表只解析主内容区 post-list-item，防止混入热榜/侧边栏
    - 分类翻页：/articles/category/xxx/2/3/...（按 rel=next 结构）
    - 详情页：
      1) 标题只取 h1.text-2xl（避免误取 header 的 h1.sr-only）
      2) vod_director：作者可点击（a=cr 识别码）
      3) vod_content：前置“标签:”可点击（a=cr 识别码）
    """

    def init(self, extend=""):
        cfg = {}
        if extend:
            try:
                cfg = json.loads(extend) if isinstance(extend, str) else (extend or {})
            except Exception:
                cfg = {}

        self.proxies = cfg.get('proxies', {}) or {          "http": "http://127.0.0.1:10172",
          "https": "http://127.0.0.1:10172"}
        self.host = (cfg.get('host') or 'https://xhssex.com').rstrip('/')

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Upgrade-Insecure-Requests': '1',
            'Origin': self.host,
            'Referer': f"{self.host}/",
        }

        # 复用连接：提升稳定性与效率
        self.session = requests.Session()

    def getName(self):
        return "小黄书(xhssex) 精准极简解析 v4"

    def destroy(self):
        _img_cache.clear()

    # ----------------------------
    # 首页分类：严格匹配（并手动加入首页）
    # ----------------------------
    def homeContent(self, filter):
        soup = self._soup(self._get_text(self.host + '/'))

        classes, seen = [], set()

        # 1) 首页（你指定的元素）
        home_name = '小黄书首页'
        home_url = self.host + '/'
        classes.append({'type_name': home_name, 'type_id': home_url})
        seen.add(home_url)

        # 2) 分类（你指定的元素结构）
        sel = 'a.app-nav-item[data-navigation_key="category"][data-type="1"][data-id]'
        for a in soup.select(sel):
            href = (a.get('href') or '').strip()
            if not re.match(r'^/articles/category/[^/]+/?$', href):
                continue

            h2 = a.select_one('h2')
            name = (h2.get_text(strip=True) if h2 else a.get_text(strip=True))
            if not name:
                continue

            # 屏蔽“我的订阅”分类
            if 'wddy' in href or '我的订阅' in name:
                continue

            full = urljoin(self.host + '/', href)
            if full in seen:
                continue

            classes.append({'type_name': name, 'type_id': full})
            seen.add(full)

        return {'class': classes, 'filters': {}, 'list': []}

    def homeVideoContent(self):
        return {'list': []}

    # ----------------------------
    # 分类列表：只解析主内容区的 post-list-item
    # ----------------------------
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        base = tid if str(tid).startswith('http') else urljoin(self.host + '/', str(tid).lstrip('/'))
        base = base.rstrip('/') + '/'

        # 翻页规则：
        # - 首页：/page/2/ /page/3/
        # - 分类：/articles/category/xxx/2/3/...
        if base.rstrip('/') == self.host:
            url = (self.host + '/') if pg == 1 else f"{self.host}/page/{pg}/"
        else:
            url = base if pg == 1 else f"{base}{pg}/"

        soup = self._soup(self._get_text(url))

        container = soup.select_one('main.app-main section.index-content ul.list-container')
        if not container:
            return {'list': [], 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 0}

        videos, seen = [], set()
        for li in container.select('li.post-list-item'):
            a_title = li.select_one('a.link[href^="/articles/"]')
            if not a_title:
                continue

            href = (a_title.get('href') or '').strip()
            if not re.match(r'^/articles/\d+/?$', href):
                continue

            full = urljoin(self.host + '/', href)
            if full in seen:
                continue

            h2 = a_title.select_one('h2')
            title = (h2.get_text(strip=True) if h2 else a_title.get_text(' ', strip=True))
            if not title:
                continue

            img_tag = li.select_one('img[data-src]')
            img = (img_tag.get('data-src') or '').strip() if img_tag else ''
            if not img:
                continue

            videos.append({
                'vod_id': full,
                'vod_name': title,
                'vod_pic': self._img_proxy(img),
                'vod_remarks': '',
                'style': {"type": "rect", "ratio": 1.01},
            })
            seen.add(full)

        return {'list': videos, 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}

    # ----------------------------
    # 详情：作者 -> vod_director；标签 -> vod_content 前缀
    # ----------------------------
    def detailContent(self, ids):
        # 虚拟条目：标签搜索结果页（用于在搜索结果中“点击后展示可点标签”）
        raw_id = str(ids[0] or '')
        if raw_id.startswith('tagsearch:'):
            try:
                _, kw_enc, pg = raw_id.split(':', 2)
            except Exception:
                kw_enc, pg = '', '1'
            # kw_enc 可能已是 URL 编码；这里只作为展示文本
            show_kw = kw_enc
            try:
                from urllib.parse import unquote
                show_kw = unquote(kw_enc)
            except Exception:
                pass

            url = f"{self.host}/search/tag/{kw_enc}/{int(pg or 1)}/"
            soup = self._soup(self._get_text(url))
            scope = soup.select_one('div.dx-tab-content--active') or soup

            tags = []
            seen = set()
            for a in scope.select('a[href^="/articles/tag/"]'):
                name = a.get_text(strip=True)
                href = (a.get('href') or '').strip()
                if not name or not href:
                    continue
                full = urljoin(self.host + '/', href)
                if full in seen:
                    continue
                seen.add(full)
                tags.append(f"[a=cr:{json.dumps({'id': full, 'name': name}, ensure_ascii=False)}/]{name}[/a]")

            vod_content = ("标签: " + ' '.join(tags)) if tags else '未找到相关标签'
            return {
                'list': [{
                    'vod_id': raw_id,
                    'vod_name': f"标签搜索：{show_kw}",
                    'vod_director': '',
                    'vod_content': vod_content,
                    'vod_play_from': '小黄书',
                    'vod_play_url': '无$null',
                }]
            }

        detail_url = raw_id if raw_id.startswith('http') else urljoin(self.host + '/', raw_id.lstrip('/'))
        html = self._get_text(detail_url)
        soup = self._soup(html)

        # 标题（该站正文标题为 h1.text-2xl...，避免误取 header 里的 h1.sr-only）
        h1 = soup.select_one('main.app-main h1.text-2xl') or soup.select_one('h1.text-2xl')
        title = h1.get_text(strip=True) if h1 else ''
        if not title:
            t = soup.select_one('title')
            title = (t.get_text(strip=True).split('|')[0] if t else '').strip()

        # 简介（meta description）
        meta_desc = soup.select_one('meta[name="description"]')
        desc = (meta_desc.get('content') or '').strip() if meta_desc else ''

        # 没有 description 时就用正文第一段作为简介（仅保留这一条必要兜底）
        if not desc:
            p = soup.select_one('main.app-main article p')
            desc = p.get_text(' ', strip=True) if p else ''

        # 作者（用 a=cr: 点击识别代码，写入 vod_director）
        director = ''
        author_a = soup.select_one('div.flex.dx-text a[href^="/articles/author/"]')
        if author_a:
            author_name = (author_a.select_one('strong').get_text(strip=True) if author_a.select_one('strong') else author_a.get_text(strip=True))
            author_href = (author_a.get('href') or '').strip()
            if author_name and author_href:
                author_url = urljoin(self.host + '/', author_href)
                director = f"[a=cr:{json.dumps({'id': author_url, 'name': author_name}, ensure_ascii=False)}/]{author_name}[/a]"

        # 标签（用 a=cr: 点击识别代码，前置到 vod_content）
        tags = []
        for a in soup.select('ul.flex.flex-wrap.gap-2 a.dx-link-button.is-tag[href]'):
            name = a.get_text(strip=True)
            href = (a.get('href') or '').strip()
            if name and href.startswith('/articles/tag/'):
                tag_url = urljoin(self.host + '/', href)
                tags.append(f"[a=cr:{json.dumps({'id': tag_url, 'name': name}, ensure_ascii=False)}/]{name}[/a]")

        if tags:
            vod_content = ("标签: " + ' '.join(tags) + "\n" + (desc or title)).strip()
        else:
            vod_content = (desc or title).strip()

        # 播放地址：只返回可直接播放的直链（m3u8/mp4）。
        # 站点多数给的是 /video/embed?id=... 或 JSON-LD contentUrl，需要再抓一次 embed 页面取直链。
        play = ''

        def _pick_direct(u: str) -> str:
            u = (u or '').strip().strip('"\'')
            if not u:
                return ''
            # 绝对化
            if u.startswith('/'):
                u = urljoin(self.host + '/', u)
            # 只接受直链
            if re.search(r'\.(m3u8|mp4)(\b|\?)', u, re.I):
                return u
            return ''

        embed = ''
        m = re.search(r'"contentUrl"\s*:\s*"([^"]+)"', html)
        if m:
            embed = m.group(1)
        else:
            m2 = re.search(r'(/video/embed\?id=\d+)', html)
            if m2:
                embed = m2.group(1)

        # 1) 如果页面里直接给了直链
        play = _pick_direct(embed)

        # 2) embed 链接则抓 embed 页再提取直链
        if not play and embed:
            embed_url = embed
            if embed_url.startswith('/'):
                embed_url = urljoin(self.host + '/', embed_url)
            embed_html = self._get_text(embed_url)
            # 常见：source/src/file/url 字段
            for pat in [
                r'"file"\s*:\s*"([^"]+)"',
                r'"url"\s*:\s*"([^"]+)"',
                r'<source[^>]+src="([^"]+)"',
                r"<source[^>]+src='([^']+)'",
                r'(https?://[^\s"\']+\.(?:m3u8|mp4)[^\s"\']*)',
            ]:
                mm = re.search(pat, embed_html, re.I)
                if mm:
                    play = _pick_direct(mm.group(1))
                    if play:
                        break

            # embed 页可能通过 pack 脚本动态加载 /video/detail_embed.js 来注入真实直链
            if not play and ('eval(function(p,a,c,k,e,d)' in embed_html):
                try:
                    packed = re.search(r'<script[^>]*>\s*(eval\(function\(p,a,c,k,e,d\).*?)</script>', embed_html, re.S | re.I)
                    script0 = packed.group(1).strip() if packed else ''
                    m_args = re.search(r"\}\((.*)\)\)\s*$", script0, re.S)
                    argstr = m_args.group(1) if m_args else ''
                    argstr = re.sub(r"'\s*\.split\('\|'\)\s*", "'", argstr)

                    parts, cur, dep, in_str, qc = [], '', 0, False, ''
                    for ch in argstr:
                        if in_str:
                            cur += ch
                            if ch == qc and not cur.endswith('\\' + qc):
                                in_str = False
                            continue
                        if ch in ('\"', "'"):
                            in_str = True
                            qc = ch
                            cur += ch
                            continue
                        if ch == '(':
                            dep += 1
                        elif ch == ')':
                            dep -= 1
                        if ch == ',' and dep == 0:
                            parts.append(cur.strip()); cur = ''
                        else:
                            cur += ch
                    if cur.strip():
                        parts.append(cur.strip())

                    import ast
                    payload = ast.literal_eval(parts[0])
                    radix = int(parts[1]); count = int(parts[2])
                    symstr = ast.literal_eval(parts[3])
                    syms = symstr.split('|')

                    # packer 可能使用 base36/base62
                    alphabet = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
                    def int2base(n, b):
                        if n == 0:
                            return '0'
                        out = ''
                        while n:
                            n, rem = divmod(n, b)
                            out = alphabet[rem] + out
                        return out
                    subs = {int2base(i, radix): (syms[i] if i < len(syms) and syms[i] else int2base(i, radix)) for i in range(count)}
                    decoded = re.sub(r'\b\w+\b', lambda mm: subs.get(mm.group(0), mm.group(0)), payload)

                    img_m = re.search(r'detail_embed\.js\?img=([^&\"]+)', decoded)
                    u_m = re.search(r'encodeURIComponent\("([^"]+)"\)', decoded)
                    if img_m and u_m:
                        img_enc = img_m.group(1)
                        u_raw = u_m.group(1)
                        t = int(time.time() / 1800)
                        detail_js_url = f"{self.host}/video/detail_embed.js?img={img_enc}&u={quote(u_raw, safe='')}&t={t}"
                        js_text = self._get_text(detail_js_url)
                        mm = re.search(r'(https?://[^\s"\']+\.(?:m3u8|mp4)[^\s"\']*)', js_text, re.I)
                        if mm:
                            play = _pick_direct(mm.group(1))
                        # detail_embed.js 也可能是 pack 过的，再解一次包
                        if not play and ('eval(function(p,a,c,k,e,d)' in js_text):
                            try:
                                s2 = js_text.strip()
                                m2_args = re.search(r"\}\((.*)\)\)\s*$", s2, re.S)
                                arg2 = m2_args.group(1) if m2_args else ''
                                arg2 = re.sub(r"'\s*\.split\('\|'\)\s*", "'", arg2)

                                parts2, cur2, dep2, in_str2, qc2 = [], '', 0, False, ''
                                for ch2 in arg2:
                                    if in_str2:
                                        cur2 += ch2
                                        if ch2 == qc2 and not cur2.endswith('\\' + qc2):
                                            in_str2 = False
                                        continue
                                    if ch2 in ('\"', "'"):
                                        in_str2 = True
                                        qc2 = ch2
                                        cur2 += ch2
                                        continue
                                    if ch2 == '(':
                                        dep2 += 1
                                    elif ch2 == ')':
                                        dep2 -= 1
                                    if ch2 == ',' and dep2 == 0:
                                        parts2.append(cur2.strip()); cur2 = ''
                                    else:
                                        cur2 += ch2
                                if cur2.strip():
                                    parts2.append(cur2.strip())

                                payload2 = ast.literal_eval(parts2[0])
                                radix2 = int(parts2[1]); count2 = int(parts2[2])
                                symstr2 = ast.literal_eval(parts2[3])
                                syms2 = symstr2.split('|')
                                subs2 = {int2base(i, radix2): (syms2[i] if i < len(syms2) and syms2[i] else int2base(i, radix2)) for i in range(count2)}
                                decoded2 = re.sub(r'\b\w+\b', lambda mm2: subs2.get(mm2.group(0), mm2.group(0)), payload2)

                                mm2 = re.search(r'(https?://[^\s"\']+\.(?:m3u8|mp4)[^\s"\']*)', decoded2, re.I)
                                if mm2:
                                    play = _pick_direct(mm2.group(1))
                            except Exception:
                                pass
                except Exception:
                    pass

        # 无源时：明确提示，不做任何兜底
        play_url = f"播放${play}" if play else "未找到视频源$null"

        return {
            'list': [{
                'vod_id': detail_url,
                'vod_name': title,
                'vod_director': director,
                'vod_content': vod_content,
                'vod_play_from': '小黄书',
                'vod_play_url': play_url,
            }]
        }

    # ----------------------------
    # 搜索（修复）
    # URL规则：/search/articles/{关键字}/{页码}/
    # 解析：只取文章tab(active)里的 post-list-item
    # ----------------------------
    def searchContent(self, key, quick, pg="1"):
        """搜索：仅返回“标签搜索入口”。

        站点不登录时搜索结果主要是 HTML 渲染；这里按你的要求：
        - 先在 /search/tag/... 中找到相关标签
        - 让用户点击进入一个“虚拟详情页”，在详情页里展示可点击标签
        - 点击标签后的列表逻辑复用本 spider 已实现的标签页列表（/articles/tag/...）
        """
        pg = int(pg or 1)
        kw = requests.utils.quote(str(key))
        # 用虚拟 id 承载：点击后走 detailContent -> 展示可点标签
        vid = f"tagsearch:{kw}:{pg}"
        # 给一个固定封面（站点自带搜索图标，缺失也不影响使用）
        pic = f"{self.host}/static/web/images/search.png"
        return {
            'list': [{
                'vod_id': vid,
                'vod_name': f"标签搜索：{key}",
                'vod_pic': pic,
                'vod_remarks': '点我查看匹配标签',
                'style': {"type": "rect", "ratio": 1.33},
            }],
            'page': 1,
            'pagecount': 1,
            'limit': 1,
            'total': 1,
        }

    # ----------------------------
    # 播放器
    # ----------------------------
    def isVideoFormat(self, url):
        u = (url or '').lower()
        return '.m3u8' in u or '.mp4' in u

    def playerContent(self, flag, id, vipFlags):
        """播放：只用直链，不做任何兜底/代理。"""
        play_id = (id or '').strip()
        if not play_id or play_id.lower() in ('null', 'none', '获取失败'):
            return {'parse': 0, 'url': '', 'header': self.headers}

        # 根据直链域名设置更合适的 Referer/Origin，提升稳定性
        headers = {'User-Agent': self.headers.get('User-Agent', '')}
        try:
            from urllib.parse import urlparse
            o = urlparse(play_id)
            origin = f"{o.scheme}://{o.netloc}" if o.scheme and o.netloc else self.host
            netloc = (o.netloc or '').lower()
        except Exception:
            origin = self.host
            netloc = ''

        if 'video.twimg.com' in netloc or netloc.endswith('twimg.com'):
            headers.update({'Referer': 'https://twitter.com/', 'Origin': 'https://twitter.com'})
        else:
            headers.update({'Referer': f"{self.host}/", 'Origin': origin})

        return {'parse': 0, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{play_id}', 'header': headers}

    # ----------------------------
    # 本地代理：仅图片解密/缓存（播放按要求只走直链）
    # ----------------------------
    def localProxy(self, param):
        try:
            type_ = param.get('type')
            url = param.get('url')

            if type_ == 'cache':
                key = param.get('key')
                if key in _img_cache:
                    return [200, 'image/jpeg', _img_cache[key]]
                return [404, 'text/plain', b'Expired']

            if type_ == 'img':
                real_url = self.d64(url) if (url and not url.startswith('http')) else url
                res = self.session.get(real_url, headers=self.headers, proxies=self.proxies, timeout=12)
                content = self._aes_decrypt_img(res.content)
                ctype = 'image/jpeg'
                if content.startswith(b'\x89PNG'):
                    ctype = 'image/png'
                elif content.startswith(b'GIF8'):
                    ctype = 'image/gif'
                return [200, ctype, content]

            return [404, 'text/plain', b'']
        except Exception:
            return [404, 'text/plain', b'']

    # ----------------------------
    # utils
    # ----------------------------
    def _get_text(self, url):
        """抓取：复用 session + 轻量重试。"""
        last_err = None
        for _ in range(2):
            try:
                r = self.session.get(url, headers=self.headers, proxies=self.proxies, timeout=15, allow_redirects=True)
                r.raise_for_status()
                r.encoding = r.apparent_encoding
                return r.text
            except Exception as e:
                last_err = e
        if last_err:
            print(f"[_get_text] {last_err}")
        return ''

    def _soup(self, html: str):
        return BeautifulSoup(html, 'lxml')

    def e64(self, text):
        return b64encode(str(text).encode()).decode()

    def d64(self, text):
        return b64decode(str(text).encode()).decode()

    def _img_proxy(self, url):
        if not url:
            return ''

        url = url.strip('"\' ')

        if url.startswith('data:'):
            try:
                _, b64_str = url.split(',', 1)
                raw = b64decode(b64_str)
                if not (raw.startswith(b'\xff\xd8') or raw.startswith(b'\x89PNG') or raw.startswith(b'GIF8')):
                    raw = self._aes_decrypt_img(raw)
                key = hashlib.md5(raw).hexdigest()
                _img_cache[key] = raw
                return f"{self.getProxyUrl()}&type=cache&key={key}"
            except Exception:
                return ''

        if not url.startswith('http'):
            url = urljoin(self.host + '/', url)

        return f"{self.getProxyUrl()}&url={self.e64(url)}&type=img"

    def _aes_decrypt_img(self, data: bytes) -> bytes:
        if not data or len(data) < 16:
            return data

        keys = [
            (b'f5d965df75336270', b'97b60394abc2fbe1'),
            (b'75336270f5d965df', b'abc2fbe197b60394'),
        ]

        for k, iv in keys:
            try:
                dec = unpad(AES.new(k, AES.MODE_CBC, iv).decrypt(data), 16)
                if dec.startswith(b'\xff\xd8') or dec.startswith(b'\x89PNG') or dec.startswith(b'GIF8'):
                    return dec
            except Exception:
                pass

        return data
