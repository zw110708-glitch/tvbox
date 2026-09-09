import json
import re
import sys
import time
import hashlib
from base64 import b64decode, b64encode
from urllib.parse import urljoin, urlparse, unquote, quote
import random

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    """sfktv66.com 专用（去依赖、稳定可用版）

    解决两类问题：
    1) 乱码（ä¸èº«...）：统一按 bytes 强制 UTF-8 解码，并对“已乱码字符串”做二次修复。
    2) 分类/列表为空：按站点真实 HTML（div.tags + a[href*=/archives/]）解析。
    """

    def init(self, extend=""):
        cfg = {}
        try:
            cfg = json.loads(extend) if isinstance(extend, str) and extend.strip() else (extend or {})
        except:
            cfg = {}

        self.host = (cfg.get('host') or 'https://sfktv66.com').rstrip('/')
        self.proxies = cfg.get('proxies') or {        "http": "http://127.0.0.1:10172",
        "https": "http://127.0.0.1:10172"}

        # API（搜索/作者列表为前端接口，需要加密请求）
        self.api_domain = cfg.get('api_domain') or 'lqcqgrkq.cc'
        self.api_hosts = [f"https://apiv{i}.{self.api_domain}" for i in (1, 2, 3)]
        random.shuffle(self.api_hosts)
        self.api_host = self.api_hosts[0]  # 当前使用的节点

        self.session = requests.Session()

        # 连接复用 + 自动重试（提升站点波动时稳定性）
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("HEAD", "GET", "POST"),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=50, pool_maxsize=50)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Upgrade-Insecure-Requests': '1',
            'Referer': f"{self.host}/",
        }

        # 标题包含这些词，判定为导流/广告，直接丢弃
        self.ad_words = [
            # 博彩/推广
            '棋牌', '彩票', '博彩', '太阳城', '澳门', '葡京', '充值', '推广', '广告', '商务','4990',
            # 导流/外站
            '直播', '免费转', '福利', '导航', '回家的路', '邮箱', 'TG', '推特', 'QQ群',
            'PG', 'YAOBA', '抖阴', '禁漫', 'cloudfront',
            # 站内公告
            '官方公告',
        ]

    def getName(self):
        return "私房KTV(sfktv66.com) 稳定版"

    # -----------------
    # Encoding helpers
    # -----------------
    def _cc_str(self, s: str) -> str:
        """把 50_97_... 这种数字串转回明文字符串。"""
        return ''.join(chr(int(x)) for x in (s or '').split('_') if x.isdigit())

    def _fix_mojibake(self, s: str) -> str:
        """把 ä¸èº«... 这种 UTF-8 被当 latin1 的乱码修回来。"""
        if not s:
            return ''
        s = s.strip()
        # 典型乱码字符特征
        if not re.search(r'[ÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßäåæçèéêëìíîïðñòóôõöøùúûüýþÿ]', s):
            return s
        try:
            return s.encode('latin1', errors='ignore').decode('utf-8', errors='ignore').strip()
        except:
            return s

    def _clean_text(self, s: str) -> str:
        s = (s or '').strip()
        s = self._fix_mojibake(s)
        s = re.sub(r'\s+', ' ', s)
        return s.strip()

    # -----------------
    # Network / parse
    # -----------------
    def _fetch_html(self, url: str, timeout=12) -> str:
        """强制按 UTF-8 解码（不使用 response.text / apparent_encoding）。"""
        try:
            r = self._request('GET', url, timeout=timeout)
            if r.status_code != 200:
                return ''
            return r.content.decode('utf-8', errors='ignore')
        except Exception as e:
            print('[fetch] Error:', e)
            return ''

    def _soup(self, html: str):
        return BeautifulSoup(html or '', 'lxml')

    def _request(self, method: str, url: str, **kwargs):
        """统一网络请求入口：复用 Session + 重试 + 超时默认值。"""
        sess = getattr(self, 'session', None) or requests
        timeout = kwargs.pop('timeout', 12)
        headers = kwargs.pop('headers', None) or self.headers
        proxies = kwargs.pop('proxies', None) if 'proxies' in kwargs else getattr(self, 'proxies', None)
        return sess.request(method, url, headers=headers, proxies=proxies, timeout=timeout, **kwargs)

    # -----------------
    # API crypto (for /author/ lists)
    # -----------------
    def _api_encrypt(self, data: dict) -> str:
        """对齐站点 crypto.js 的 Encrypt()，返回 form-urlencoded 字符串。"""
        key = self._cc_str('50_97_99_102_55_101_57_49_101_57_56_54_52_54_55_51').encode('utf-8')
        iv = self._cc_str('49_99_50_57_56_56_50_100_51_100_100_102_99_102_100_54').encode('utf-8')
        sign_key = self._cc_str('53_53_56_57_100_52_49_102_57_50_97_53_57_55_100_48_49_54_98_48_51_55_97_99_51_55_100_98_50_52_51_100')

        plain = json.dumps(data or {}, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        cipher = AES.new(key, AES.MODE_CBC, iv).encrypt(self._pkcs7_pad(plain))
        ciphertext_b64 = b64encode(cipher).decode('utf-8')

        ts = int(time.time())
        client = 'ios'
        sign_text = f"client={client}&data={ciphertext_b64}&timestamp={ts}" + sign_key
        sha = hashlib.sha256(sign_text.encode('utf-8')).hexdigest()
        sign = hashlib.md5(sha.encode('utf-8')).hexdigest()

        # 关键：Base64 里可能包含 '+'，在 form-urlencoded 中会被当空格，必须 url-encode
        return f"client={client}&data={quote(ciphertext_b64, safe='')}&sign={sign}&timestamp={ts}"

    def _api_decrypt(self, ciphertext_b64: str, msg: str = '') -> dict:
        key = self._cc_str('50_97_99_102_55_101_57_49_101_57_56_54_52_54_55_51').encode('utf-8')
        iv = self._cc_str('49_99_50_57_56_56_50_100_51_100_100_102_99_102_100_54').encode('utf-8')
        try:
            ct = b64decode((ciphertext_b64 or '').encode('utf-8'))
            pt = unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(ct), 16)
            return json.loads(pt.decode('utf-8', errors='ignore') or '{}')
        except:
            return {'data': None, 'msg': msg, 'status': 0}

    def _pkcs7_pad(self, b: bytes, block=16) -> bytes:
        pad = block - (len(b) % block)
        return b + bytes([pad]) * pad

    def _api_post(self, api_path: str, data: dict) -> dict:
        """POST 到 apiv*.domain/api.php + api_path，并解密返回。"""
        body = self._api_encrypt(data)
        h = {
            'User-Agent': self.headers.get('User-Agent'),
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': self.host,
            'Referer': self.host + '/',
        }

        # apiv1/2/3 轮询（任一节点短暂不可用时更稳）
        hosts = getattr(self, 'api_hosts', None) or [self.api_host]
        for host in hosts:
            try:
                url = f"{host}/api.php{api_path}"
                r = (self.session.post(url, data=body, headers=h, proxies=self.proxies, timeout=15)
                     if getattr(self, 'session', None) else
                     requests.post(url, data=body, headers=h, proxies=self.proxies, timeout=15))
                if r.status_code != 200:
                    continue
                j = r.json()
                dec = self._api_decrypt(j.get('data') or '', j.get('msg') or '')
                if dec.get('status') == 1:
                    self.api_host = host
                    return dec
            except Exception:
                continue

        return {}

    def _abs(self, href: str) -> str:
        return href if href.startswith('http') else urljoin(self.host + '/', (href or '').lstrip('/'))

    def _is_post_path(self, href: str) -> bool:
        if not href:
            return False
        if href.startswith('http'):
            p = urlparse(href)
            if p.netloc != urlparse(self.host).netloc:
                return False
            href = p.path
        return bool(re.match(r'^/archives/\d+/?$', href))

    # -----------------
    # Home / Category
    # -----------------
    def homeContent(self, filter):
        html = self._fetch_html(self.host + '/')
        if not html:
            return {'class': [], 'filters': {}, 'list': []}

        soup = self._soup(html)

        # 分类：严格按你给的 tablist（van-tabs）解析，避免混入其它链接
        classes = []
        seen = set()
        for a in soup.select('div[role="tablist"] a[href]'):
            href = (a.get('href') or '').strip()
            name = self._clean_text(a.get_text(' ', strip=True))

            if not href or not name:
                continue

            # 屏蔽“私房广场”分类
            if name == '私房广场':
                continue

            # 仅保留：首页/分类/榜单
            if href == '/':
                pass
            elif href.startswith('/category/'):
                pass
            elif href.startswith('/order/'):
                pass
            else:
                continue

            if href in seen:
                continue
            classes.append({'type_name': name, 'type_id': href})
            seen.add(href)

        # 列表
        videos = self._parse_list(soup)

        return {'class': classes, 'filters': {}, 'list': videos}

    def homeVideoContent(self):
        return {'list': self.homeContent(None).get('list', [])}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg or 1)
        except:
            pg = 1

        # tid 统一为相对路径
        if (tid or '').startswith('http'):
            p = urlparse(tid)
            tid = p.path + (('?' + p.query) if p.query else '')

        # 分页规则按页面真实 href：
        # - 首页：/page/2/
        # - 分类：/category/xxx/2/
        # - 榜单：/order/today/page/2/
        if tid == '/':
            url = f"{self.host}/page/{pg}/" if pg > 1 else f"{self.host}/"
        elif (tid or '').startswith('/category/'):
            base = f"{self.host}{tid.rstrip('/')}/"
            url = f"{base}{pg}/" if pg > 1 else base
        elif (tid or '').startswith('/order/'):
            base = f"{self.host}{tid.rstrip('/')}/"
            url = f"{base}page/{pg}/" if pg > 1 else base
        elif (tid or '').startswith('/tag/'):
            base = f"{self.host}{tid.rstrip('/')}/"
            url = f"{base}{pg}/" if pg > 1 else base
        elif (tid or '').startswith('/author/'):
            # author 页前端渲染：走接口拿列表
            m = re.search(r'/author/(\d+)', tid or '')
            uid = int(m.group(1)) if m else 0
            if not uid:
                return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 90, 'total': 0}

            api = self._api_post('/api/tcontent/author_contents', {
                'sort': 'new',
                'uid': uid,
                'page': pg,
                'limit': 24,
            })
            data = api.get('data') or {}
            if isinstance(data, str):
                # 极端情况下 data 可能是错误文本
                return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 90, 'total': 0}

            lst = data.get('list') or []
            out = []
            for it in lst:
                cid = it.get('cid') or it.get('slug') or it.get('id')
                title = self._clean_text(it.get('title') or it.get('name') or '')
                if not cid or not title or any(w in title for w in self.ad_words):
                    continue
                pic = ''
                imgs = it.get('images')
                if isinstance(imgs, list) and imgs:
                    pic = imgs[0]
                if pic and not pic.startswith('http'):
                    pic = self._abs(pic)

                out.append({
                    'vod_id': self._abs(f"/archives/{cid}/"),
                    'vod_name': title,
                    'vod_pic': self._img_proxy_url(pic) if pic else '',
                    'vod_remarks': ''
                })

            total = int(data.get('total') or 0)
            pagecount = max(1, (total + 24 - 1) // 24) if total else 9999
            return {'list': out, 'page': pg, 'pagecount': pagecount, 'limit': 90, 'total': total or 999999}
        else:
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 90, 'total': 0}

        html = self._fetch_html(url)
        if not html:
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 90, 'total': 0}

        soup = self._soup(html)
        videos = self._parse_list(soup)

        return {'list': videos, 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}

    def searchContent(self, key, quick, pg="1"):
        """搜索：删除HTML搜索，只走加密 API（参考 51fans1.py）。

        接口：POST /api/tcontent/searchContents
        参数：word, page, limit
        """
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1

        try:
            word = self._clean_text(str(key))
            if not word:
                return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 20, 'total': 0}

            api = self._api_post('/api/tcontent/searchContents', {
                'word': word,
                'page': pg,
                'limit': 24,
            })
            data = api.get('data') or {}
            if not isinstance(data, dict):
                return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 24, 'total': 0}

            lst = data.get('list') or []
            total = int(data.get('total') or 0)

            out = []
            for it in lst:
                try:
                    cid = it.get('cid') or it.get('slug') or it.get('id')
                    title = self._clean_text(it.get('title') or it.get('name') or '')
                    if not cid or not title or any(w in title for w in self.ad_words):
                        continue

                    pic = ''
                    imgs = it.get('images')
                    if isinstance(imgs, list) and imgs:
                        pic = imgs[0]
                    if pic and not str(pic).startswith('http'):
                        pic = self._abs(str(pic))

                    out.append({
                        'vod_id': self._abs(f"/archives/{cid}/"),
                        'vod_name': title,
                        'vod_pic': self._img_proxy_url(pic) if pic else '',
                        'vod_remarks': ''
                    })
                except Exception:
                    continue

            pagecount = max(1, (total + 24 - 1) // 24) if total else 9999
            return {'list': out, 'page': pg, 'pagecount': pagecount, 'limit': 24, 'total': total or 999999}
        except Exception as e:
            print('[searchContent] Error:', e)
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 24, 'total': 0}

    def _norm_img(self, img: str) -> str:
        """极简图片URL标准化：
        - 优先使用 z-image-loader-url（真实图床地址）
        - 忽略 src=blob:...
        - 处理 `...` 反引号包裹
        - 最终统一走本地代理 type=img（防盗链）
        """
        img = (img or '').strip().strip('"\'')
        if not img or img.startswith('blob:'):
            return ''

        img = unquote(img).strip('`')

        # 站点常见：/`https://xxx` 或 /%60https://xxx%60
        if img.startswith('/') and 'http' in img:
            img = img.lstrip('/').strip('`')

        if img.startswith('//'):
            img = 'https:' + img
        if not img.startswith('http'):
            img = self._abs(img)

        return self._img_proxy_url(img)

    def _extract_img_from_anchor(self, a) -> str:
        img_el = a.select_one('img')
        if not img_el:
            return ''

        # 站点图片真实地址在 z-image-loader-url
        url = (img_el.get('z-image-loader-url') or img_el.get('data-src') or img_el.get('data-original') or '')
        if not url:
            # 只有当 src 不是 blob: 时才用
            src = (img_el.get('src') or '').strip()
            if src and not src.startswith('blob:'):
                url = src

        return self._norm_img(url)

    def _parse_list(self, soup: BeautifulSoup):
        """只解析主列表（xqbj-list-rows），避免混入推荐/广告块。"""
        videos = []
        seen = set()

        def handle(a):
            href = (a.get('href') or '').strip()
            if not self._is_post_path(href) or href in seen:
                return

            title = self._clean_text(a.get('title') or '')
            if not title:
                h = a.select_one('h1,h2,h3')
                title = self._clean_text(h.get_text(' ', strip=True) if h else a.get_text(' ', strip=True))
            if not title or len(title) < 2:
                return
            if any(w in title for w in self.ad_words):
                return

            img = self._extract_img_from_anchor(a)

            videos.append({
                'vod_id': self._abs(href),
                'vod_name': title,
                'vod_pic': img,
                'vod_remarks': ''
            })
            seen.add(href)

        rows = soup.select('div.xqbj-list-rows')
        if rows:
            for row in rows:
                a = row.select_one('a[href^="/archives/"]')
                if a:
                    handle(a)
        else:
            # 极少数页面无 rows 才退回全局扫描
            for a in soup.select('a[href^="/archives/"]'):
                handle(a)

        return videos

    # -----------------
    # Detail / Player
    # -----------------
    def detailContent(self, ids):
        """详情页：
        - 导演/演员：从 .novel-info 提取作者（可点击）
        - 标签：从 .tags-group2 提取（可点击）
        - 播放源：DPlayer data-config
        """
        try:
            url = ids[0]
            url = url if url.startswith('http') else self._abs(url)
            html = self._fetch_html(url)
            if not html:
                return {'list': [{'vod_play_from': 'dplayer', 'vod_play_url': '获取失败'}]}

            soup = self._soup(html)

            # 标题
            title = self._clean_text(
                (soup.select_one('h1') or soup.select_one('title')).get_text(' ', strip=True)
                if (soup.select_one('h1') or soup.select_one('title')) else ''
            )

            # 导演/演员（站点作者，可点击 cr:）
            director = ''
            director_name = ''
            director_href = ''

            novel = soup.select_one('.novel-info')
            if novel:
                # 优先取带 h2 的作者链接（移动/桌面都有）
                a2 = novel.select_one('a[href^="/author/"] h2')
                if a2:
                    director_name = self._clean_text(a2.get_text(' ', strip=True))
                    a_link = a2.find_parent('a')
                    director_href = (a_link.get('href') or '').strip() if a_link else ''

                # 兜底：取头像 img alt（形如 ">桥本香菜"）
                if not director_name:
                    img = novel.select_one('a[href^="/author/"] img')
                    if img:
                        director_name = self._clean_text((img.get('alt') or '').lstrip('>'))
                        a_link = img.find_parent('a')
                        director_href = (a_link.get('href') or '').strip() if a_link else ''

            if director_name and director_href:
                director_href = self._abs(director_href)
                director = f"[a=cr:{json.dumps({'id': director_href, 'name': director_name}, ensure_ascii=False)}/]{director_name}[/a]"

            # 标签（可点击 cr:）
            tags = []
            for a in soup.select('.tags-group2 a[href^="/tag/"]'):
                name = self._clean_text(a.get_text(' ', strip=True))
                href = (a.get('href') or '').strip()
                if name and href:
                    href = self._abs(href)
                    tags.append(f"[a=cr:{json.dumps({'id': href, 'name': name}, ensure_ascii=False)}/]{name}[/a]")
            tags_line = ('标签：' + ' '.join(tags)) if tags else ''

            # 简介：取页面正文（尽量短）
            intro = ''
            intro_el = soup.select_one('.post-content, .module-info-introduction-content, .video-desc, article')
            if intro_el:
                intro = self._clean_text(intro_el.get_text(' ', strip=True))

            # vod_content：导演(作者) + 标签 放在简介前
            # vod_content：只在简介前显示“标签”（按你的要求移除“导演”行）
            prefix = []
            if tags_line:
                prefix.append(tags_line)
            vod_content = ('\n'.join(prefix) + ('\n' if prefix and intro else '') + intro) if (prefix or intro) else title
            # 播放源：仅取直链（不再使用网页兜底）
            dplayer = soup.select_one('.dplayer')
            cfg = (dplayer.get('data-config') if dplayer else '') or ''

            def _loads_dplayer_cfg(raw: str) -> dict:
                raw = (raw or '').strip()
                if not raw:
                    return {}
                # 1) 直接 JSON
                try:
                    return json.loads(raw)
                except Exception:
                    pass
                # 2) 尝试提取 JSON 子串
                try:
                    m = re.search(r'(\{.*\})', raw, re.S)
                    if m:
                        return json.loads(m.group(1))
                except Exception:
                    pass
                return {}

            play = ''
            if cfg:
                obj = _loads_dplayer_cfg(cfg)
                play = ((obj.get('video') or {}).get('url') or '').strip()

            # 直链标准化（//、相对路径、反引号包裹等）
            if play:
                play = unquote(str(play)).strip().strip('`').strip('"\'')
                if play.startswith('//'):
                    play = 'https:' + play
                if not play.startswith('http'):
                    play = self._abs(play)

            vod_play_url = f"正片${play}" if play else '正片$'

            return {
                'list': [{
                    'vod_id': url,
                    'vod_name': title,
                    'vod_director': director,
                    'vod_content': vod_content,
                    'vod_play_from': 'dplayer',
                    'vod_play_url': vod_play_url,
                }]
            }
        except Exception as e:
            print('[detailContent] Error:', e)
            return {'list': [{'vod_play_from': 'dplayer', 'vod_play_url': '获取失败'}]}

    def playerContent(self, flag, id, vipFlags):
        """播放器：只输出直链（不再做 m3u8/网页等兜底或改写）。

        - 由 `detailContent()` 负责尽力提取直链
        - 这里不再把 m3u8 改写为本地代理
        """
        if not id:
            return {'parse': 0, 'url': '', 'header': self.headers}
        return {'parse': 0, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{id}', 'header': self.headers}

    # -----------------
    # Local Proxy (m3u8/ts)
    # -----------------
    def localProxy(self, param):
        try:
            t = param.get('type')
            u = param.get('url')
            if t == 'm3u8':
                return self._m3u8_proxy(u)
            if t == 'ts':
                return self._ts_proxy(u)
            if t == 'img':
                return self._img_proxy(u)
            return [404, 'text/plain', b'']
        except Exception as e:
            print('[localProxy] Error:', e)
            return [404, 'text/plain', b'']

    def proxy(self, url, type='m3u8'):
        return f"{self.getProxyUrl()}&url={self.e64(url)}&type={type}"

    def _img_proxy_url(self, url: str) -> str:
        # 图片统一走本地代理，避免防盗链/Referer导致加载失败
        return self.proxy(url, 'img')

    def _m3u8_proxy(self, url_b64):
        url = self.d64(url_b64)
        r = self._request('GET', url, timeout=10)
        r.raise_for_status()
        txt = r.text

        base = r.url.rsplit('/', 1)[0]
        host_base = '/'.join(r.url.split('/')[:3])

        out = []
        for line in txt.split('\n'):
            s = line.strip()
            if not s or s.startswith('#'):
                out.append(line)
                continue
            if s.startswith('http'):
                abs_ts = s
            elif s.startswith('/'):
                abs_ts = host_base + s
            else:
                abs_ts = base + '/' + s
            out.append(self.proxy(abs_ts, 'ts'))

        return [200, 'application/vnd.apple.mpegurl', '\n'.join(out)]

    def _ts_proxy(self, url_b64):
        url = self.d64(url_b64)
        content = self._request('GET', url, timeout=10).content
        return [200, 'video/mp2t', content]

    def _aesimg(self, data: bytes) -> bytes:
        """极简图片解密（沿用原始可用密钥，自动识别是否已是图片）"""
        if not data or len(data) < 16:
            return data
        if data.startswith(b'\xff\xd8') or data.startswith(b'\x89PNG') or data.startswith(b'GIF8'):
            return data

        keys = [
            (b'f5d965df75336270', b'97b60394abc2fbe1'),
            (b'75336270f5d965df', b'abc2fbe197b60394'),
        ]

        for k, iv in keys:
            # CBC
            try:
                dec = unpad(AES.new(k, AES.MODE_CBC, iv).decrypt(data), 16)
                if dec.startswith(b'\xff\xd8') or dec.startswith(b'\x89PNG') or dec.startswith(b'GIF8'):
                    return dec
            except:
                pass
            # ECB
            try:
                dec = unpad(AES.new(k, AES.MODE_ECB).decrypt(data), 16)
                if dec.startswith(b'\xff\xd8') or dec.startswith(b'\x89PNG') or dec.startswith(b'GIF8'):
                    return dec
            except:
                pass
        return data

    def _img_proxy(self, url_b64):
        url = self.d64(url_b64)
        h = dict(self.headers)
        h['Referer'] = self.host + '/'
        h['Origin'] = self.host
        r = self._request('GET', url, headers=h, timeout=10)
        raw = r.content
        dec = self._aesimg(raw)

        # content-type 探测
        if dec.startswith(b'\xff\xd8'):
            ct = 'image/jpeg'
        elif dec.startswith(b'\x89PNG'):
            ct = 'image/png'
        elif dec.startswith(b'GIF8'):
            ct = 'image/gif'
        else:
            ct = 'application/octet-stream'

        return [200, ct, dec]

    def e64(self, text):
        return b64encode(str(text).encode()).decode()

    def d64(self, text):
        return b64decode(str(text).encode()).decode(errors='ignore')
