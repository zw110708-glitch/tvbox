# coding=utf-8
# !/usr/bin/python
from Crypto.Util.Padding import unpad
from Crypto.Cipher import AES
from bs4 import BeautifulSoup
import base64
import requests
import re
import json

sys_path_added = False
try:
    import sys
    sys.path.append('..')
    sys_path_added = True
except Exception:
    pass

from base.spider import Spider as BaseSpider

xurl = "https://mjv009.com"

DEFAULT_HEADERS = {
    "Referer": xurl,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


class Spider(BaseSpider):

    def __init__(self):
        super().__init__()
        self.sess = requests.Session()
        self.sess.headers.update(DEFAULT_HEADERS)
        self.cached_base_url = None
        # 代理：与 hohoj 示例一致，来自 extend JSON 的 proxy 字段
        self.proxies = {}

    def getName(self):
        return "丢丢喵"

    # -------------------------
    # CatVod/TVBox 常用必备接口（避免壳调用时报错导致“加载不出内容”）
    # -------------------------

    def init(self, extend=""):
        """壳会在加载 spider 时调用。

        代理逻辑参考你给的 hohoj：extend 为 JSON 字符串时，读取其中 proxy 字段。
        例如：{"proxy": {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}}
        """
        try:
            if extend:
                cfg = json.loads(extend) if isinstance(extend, str) else (extend or {})
                self.proxies = cfg.get('proxy', {}) or {}
        except Exception:
            self.proxies = {}

        if not self.cached_base_url:
            self.refresh_session()

    def isVideoFormat(self, url):
        """用于判断是否直链。站点播放一般走解析后的真实直链。"""
        if not url:
            return False
        u = str(url).lower()
        return any(u.endswith(ext) for ext in [".m3u8", ".mp4", ".flv", ".webm"]) or ".m3u8" in u

    def manualVideoCheck(self):
        # 返回 False/True 取决于壳的要求；一般 True 更稳妥
        return True

    def homeVideoContent(self):
        """部分壳会调用首页推荐。这里给一个最小可用实现：返回空列表而不是抛异常。"""
        return {"list": []}

    # -------------------------
    # 通用工具
    # -------------------------

    @staticmethod
    def extract_between(text: str, start: str, end: str, index: int = 0) -> str:
        try:
            return text.split(start)[index + 1].split(end)[0]
        except Exception:
            return ""

    @staticmethod
    def soup(html: str):
        return BeautifulSoup(html, "lxml")

    # -------------------------
    # 会话刷新（动态跳转/挑战页）
    # -------------------------

    def refresh_session(self) -> bool:
        """访问 /zh/，如果返回 window.location 跳转，则跟随一次并缓存最终 base url。"""
        try:
            r = self.sess.get(f"{xurl}/zh/", timeout=15, proxies=self.proxies)
            r.encoding = "utf-8"
            html = r.text

            # 有些站点会用极短的 JS 跳转页做前置校验
            if 'window.location="' in html and len(html) < 2000:
                url2 = self.extract_between(html, 'window.location="', '"', 0)
                if not url2:
                    return False
                # 兼容相对路径
                if url2.startswith("//"):
                    url2 = "https:" + url2
                elif url2.startswith("/"):
                    url2 = xurl + url2

                r2 = self.sess.get(url2, timeout=15, proxies=self.proxies)
                r2.encoding = "utf-8"
                self.cached_base_url = url2
                return True

            # 如果没有跳转，直接认为 /zh/ 可用
            self.cached_base_url = f"{xurl}/zh/"
            return True
        except Exception:
            return False

    def get_html(self, url: str) -> str:
        if not self.cached_base_url:
            self.refresh_session()
        r = self.sess.get(url, timeout=20, proxies=self.proxies)
        r.encoding = "utf-8"

        # 再次遇到短跳转页则重刷
        if 'window.location="' in r.text and len(r.text) < 2000:
            if self.refresh_session():
                r = self.sess.get(url, timeout=20, proxies=self.proxies)
                r.encoding = "utf-8"
        return r.text

    # -------------------------
    # 站点：分类/搜索（保持你原逻辑）
    # -------------------------

    def homeContent(self, filter):
        result = {"class": []}
        if not self.cached_base_url:
            if not self.refresh_session():
                return result

        res = self.get_html(self.cached_base_url)
        doc = self.soup(res)
        soups = doc.find_all('li', class_="animenu__nav_transparent")
        categories = []
        skip_names = ["18av首頁", "18H漫畫", "寫真圖片", "小說", "91", "Hgame"]
        for soup in soups:
            a = soup.find('a')
            if not a:
                continue
            name = a.get_text().strip()
            if name in skip_names:
                continue
            categories.append({"type_id": a.get('href', ''), "type_name": name})

        result["class"] = categories
        result["class"].append({'type_id': f'{xurl}/zh/dt_random/all/index.html', 'type_name': '国产自拍'})
        return result

    def categoryContent(self, cid, pg, filter, ext):
        """分类/点击跳转列表。

        兼容两类地址：
        1) 原站列表：.../xxx_list/.../index.html 通过拼页码变成 .../2.html
        2) 详情页里的可点击标签/导演/女优：.../xxx_category/.../1.html 通过替换页码变成 .../2.html
        """
        page = int(pg) if pg else 1
        cid = (cid or "").replace('random', 'list')

        # 兼容 cr 点击传入的相对路径（不带域名）
        if cid.startswith("//"):
            cid = "https:" + cid
        elif cid.startswith("/"):
            cid = xurl + cid
        elif not cid.startswith("http://") and not cid.startswith("https://"):
            # 例如："zh/chinese-censored_category/210/高画质/1.html"
            cid = xurl + "/" + cid.lstrip("/")

        # 1) /index.html 形式
        if "index.html" in cid:
            fenge = cid.split("index.html")
            target_url = f'{fenge[0]}{page}.html'
        # 2) /1.html 形式（标签/导演/女优）
        elif re.search(r"/\d+\.html$", cid):
            target_url = re.sub(r"/\d+\.html$", f"/{page}.html", cid)
        else:
            # 兜底：直接拼接页码
            target_url = cid.rstrip('/') + f"/{page}.html"

        res = self.get_html(target_url)
        doc = self.soup(res)
        soups = doc.find_all('div', class_="posts")
        videos = []
        for soup in soups:
            for vod in soup.find_all('div', class_="post"):
                names = vod.find('div', class_="con")
                if not names:
                    continue
                a = names.find('a')
                if not a:
                    continue
                name = names.get_text(" ", strip=True)
                id_url = a.get('href', '')
                pic_tag = vod.find('img')
                pic = pic_tag.get('src', '') if pic_tag else ""
                videos.append({"vod_id": id_url, "vod_name": name, "vod_pic": pic})

        # --------- 修复“无限翻页” ---------
        # 壳通常依据 pagecount 判断是否还有下一页。
        # 这里用“页面是否存在下一页链接”来判断。
        has_next = False
        try:
            p_int = int(pg) if pg else 1
        except Exception:
            p_int = 1

        # 常见分页链接形态：.../2.html、.../3.html（页面内显式出现）
        if re.search(rf"/{p_int + 1}\\.html", res):
            has_next = True

        # 如果页面里看不到下一页链接，则做一次“轻量验证”：请求下一页看是否有内容
        if not has_next and videos:
            try:
                next_url = target_url
                if re.search(r"/\\d+\\.html$", next_url):
                    next_url = re.sub(r"/\\d+\\.html$", f"/{p_int + 1}.html", next_url)
                elif "index.html" in next_url:
                    next_url = next_url.replace("index.html", f"{p_int + 1}.html")
                else:
                    next_url = next_url.rstrip('/') + f"/{p_int + 1}.html"

                next_html = self.get_html(next_url)
                next_doc = self.soup(next_html)
                next_posts = next_doc.find_all('div', class_="post")
                if next_posts:
                    # 再确认一下不是同页重复（取第一个 id 对比）
                    first_a = next_posts[0].find('a')
                    cur_first = videos[0].get('vod_id') if videos else ''
                    nxt_first = first_a.get('href', '') if first_a else ''
                    if nxt_first and nxt_first != cur_first:
                        has_next = True
            except Exception:
                pass

        # 如果本页没有任何视频，也强制认为到头
        if not videos:
            has_next = False

        pagecount = 9999 if has_next else p_int
        total = p_int * 90 if has_next else (p_int - 1) * 90 + len(videos)

        return {
            'list': videos,
            'page': pg,
            'pagecount': pagecount,
            'limit': 90,
            'total': total,
        }

    def searchContentPage(self, key, quick, pg):
        page = int(pg) if pg else 1
        target_url = f'{xurl}/zh/fc_search/all/{key}/{page}.html'
        res = self.get_html(target_url)
        doc = self.soup(res)
        soups = doc.find_all('div', class_="posts")
        videos = []
        for soup in soups:
            for vod in soup.find_all('div', class_="post"):
                names = vod.find('div', class_="con")
                if not names:
                    continue
                a = names.find('a')
                if not a:
                    continue
                name = names.get_text(" ", strip=True)
                id_url = a.get('href', '')
                pic_tag = vod.find('img')
                pic = pic_tag.get('src', '') if pic_tag else ""
                videos.append({"vod_id": id_url, "vod_name": name, "vod_pic": pic})

        return {
            'list': videos,
            'page': pg,
            'pagecount': 9999,
            'limit': 90,
            'total': 999999,
        }

    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, pg)

    # -------------------------
    # 播放：解密 + 取 play.php
    # -------------------------

    @staticmethod
    def _aes_cbc_decrypt(key_str: str, iv_str: str, b64_ciphertext: str) -> str:
        key = key_str.encode('utf-8')
        iv = iv_str.encode('utf-8')
        raw = base64.b64decode(b64_ciphertext)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        plain = cipher.decrypt(raw)
        return unpad(plain, AES.block_size).decode('utf-8', errors='ignore')

    @staticmethod
    def _decode_cipher_to_b64(cipher_raw: str, base_val: int, xor_val: int) -> str:
        """把类似 81k88k38k... 的串，还原为 base64 文本。split char = chr(base+97)。"""
        split_char = chr(int(base_val) + 97)
        out = []
        for part in cipher_raw.split(split_char):
            if not part:
                continue
            try:
                v = int(part, int(base_val))
                v ^= int(xor_val)
                out.append(chr(v))
            except Exception:
                continue
        return "".join(out)

    def jfun_decrypt_v2(self, key_str, iv_str, cipher_raw, base_val, xor_val):
        b64_text = self._decode_cipher_to_b64(cipher_raw, base_val, xor_val)
        return self._aes_cbc_decrypt(key_str, iv_str, b64_text)

    @staticmethod
    def _must_find(pattern: str, text: str, group: int = 1, flags=0, default: str = "") -> str:
        m = re.search(pattern, text, flags)
        if not m:
            return default
        return m.group(group)

    def extract_cipher(self, html_content: str) -> str:
        # 兼容你上传的页面结构：mvarr['10_1']=[[ 'a_iframe_id_...','密文', ...
        # 注意：密文可能很长，启用 DOTALL。
        pattern = r"'a_iframe_id_\d+_\d+_\d+'\s*,\s*'([a-z0-9]+)'\s*,"
        return self._must_find(pattern, html_content, 1, flags=re.I | re.S)

    def extract_key(self, html_content: str) -> str:
        return self._must_find(r"var\s+argdeqweqweqwe\s*=\s*'([a-f0-9]+)'\s*;", html_content, 1, re.I)

    def extract_iv(self, html_content: str) -> str:
        return self._must_find(r"var\s+hdddedg252\s*=\s*'([a-f0-9]+)'\s*;", html_content, 1, re.I)

    def extract_base(self, html_content: str) -> str:
        return self._must_find(r"hadeedd252\s*=\s*(\d+)\s*;", html_content, 1, re.I, default="10")

    def extract_xor(self, html_content: str) -> str:
        # 你上传的 HTML 里有 hadeedg252=30; 这种变量，很像 xor 常量。
        # 如果站点变种不同，找不到就回退到 29（你原先默认值）。
        return self._must_find(r"hadeedg252\s*=\s*(\d+)\s*;", html_content, 1, re.I, default="29")

    def fetch_player_response(self, final_id: str, referer: str = "") -> str:
        """请求 play.php。

        站点经常校验 Referer（必须来自详情页），否则会返回无源的播放器页面。
        """
        params = {'lo': 'on', 'id': final_id}
        headers = dict(DEFAULT_HEADERS)
        if referer:
            headers['Referer'] = referer
        r = self.sess.get(f'{xurl}/js/player/play.php', params=params, headers=headers, timeout=20, proxies=self.proxies)
        r.encoding = 'utf-8'
        return r.text

    @staticmethod
    def extract_video_matches(player_js: str):
        """从 play.php 返回内容中提取清晰度与直链。

        站点格式可能出现：单引号/双引号、size 带不带引号等。
        返回统一为 (src, type, size) 列表。
        """
        patterns = [
            # {src:'...', type:'...', size:'480'}
            r"\{\s*src\s*:\s*'([^']+)'\s*,\s*type\s*:\s*'([^']+)'\s*,\s*size\s*:\s*'?(\d+)'?",
            # {src:"...", type:"...", size:480}
            r"\{\s*src\s*:\s*\"([^\"]+)\"\s*,\s*type\s*:\s*\"([^\"]+)\"\s*,\s*size\s*:\s*'?(\d+)'?",
        ]
        out = []
        for p in patterns:
            out.extend(re.findall(p, player_js, flags=re.I))
        # 去重
        seen = set()
        uniq = []
        for src, typ, size in out:
            k = (src, size)
            if k in seen:
                continue
            seen.add(k)
            uniq.append((src, typ, size))
        return uniq

    @staticmethod
    def build_play_url(matches):
        """转换成 catvod 常见的 vod_play_url: 清晰度$URL#清晰度$URL2。

        按你要求：清晰度（size）从高到低排序。
        """
        if not matches:
            return ""

        def _to_int(x):
            try:
                return int(str(x).strip())
            except Exception:
                return 0

        # matches: (src, type, size)
        matches_sorted = sorted(matches, key=lambda it: _to_int(it[2]), reverse=True)

        items = []
        for src, _typ, size in matches_sorted[:8]:
            items.append(f"{size}${src}")

        return "#".join(items)

    @staticmethod
    def parse_detail_meta(html_content: str):
        """严格按页面结构提取：导演、女优、类型/标签。"""
        doc = BeautifulSoup(html_content, "lxml")

        director = {"name": "", "href": ""}
        categories = []  # list of {name, href}
        actors = []      # list of {name, href}

        # 1) 导演：在 posts-inner-details-text 中按 headline/message 成对取值
        box = doc.find('div', class_='posts-inner-details-text')
        if box:
            lis = box.find_all('li')
            # headline / message 交替出现
            for i in range(len(lis) - 1):
                h = lis[i].get_text(strip=True)
                if h in ("導演:", "导演:"):
                    msg = lis[i + 1]
                    a = msg.find('a')
                    if a:
                        director = {"name": a.get_text(" ", strip=True), "href": a.get('href', '')}
                    else:
                        director = {"name": msg.get_text(" ", strip=True), "href": ""}
                    break

        # 2) 类型/标签：影片類別 下的所有 <a> 文本
        under = doc.find('span', class_='posts-inner-details-text-under')
        if under:
            msg_li = under.find('li', class_='posts-message')
            if msg_li:
                for a in msg_li.find_all('a'):
                    t = a.get_text(strip=True)
                    if t:
                        categories.append({"name": t, "href": a.get('href', '')})

        # 3) 女优：actor-right-details-images 区域内所有 p>a 文本
        actor_box = doc.find('div', class_='actor-right-details-images')
        if actor_box:
            for a in actor_box.select('div.actor-right-images-part p a'):
                t = a.get_text(strip=True)
                if t:
                    actors.append({"name": t, "href": a.get('href', '')})

        # 去重保持顺序
        def dedup_kv(seq):
            seen = set()
            out = []
            for x in seq:
                name = x.get('name', '') if isinstance(x, dict) else str(x)
                if not name or name in seen:
                    continue
                seen.add(name)
                out.append(x)
            return out

        return {
            "director": director,
            "actors": dedup_kv(actors),
            "categories": dedup_kv(categories),
        }

    def detailContent(self, ids):
        did = ids[0]
        html_content = self.get_html(did)

        cipher_raw = self.extract_cipher(html_content)
        key = self.extract_key(html_content)
        iv = self.extract_iv(html_content)
        base_val = self.extract_base(html_content)
        xor_val = self.extract_xor(html_content)

        # 任一关键字段缺失就直接返回空，避免抛异常导致前端无显示
        if not (cipher_raw and key and iv and base_val):
            return {'list': [{"vod_id": did, "vod_play_from": "18AV专线", "vod_play_url": ""}]}

        try:
            final_id = self.jfun_decrypt_v2(key, iv, cipher_raw, base_val=int(base_val), xor_val=int(xor_val))
        except Exception:
            # 解密失败（通常是 base/xor/key/iv 不匹配），返回空播放
            final_id = ""

        play_url = ""
        if final_id:
            player_js = self.fetch_player_response(final_id, referer=did)
            matches = self.extract_video_matches(player_js)
            play_url = self.build_play_url(matches)

        meta = self.parse_detail_meta(html_content)

        def _cr(name: str, href: str) -> str:
            """生成可点击格式：[a=cr:{json}/]name[/a]"""
            if not name:
                return ""

            _id = ""
            if href:
                try:
                    href2 = href.split('?', 1)[0]
                    if '://' in href2:
                        _id = href2.split('/', 3)[-1]
                    else:
                        _id = href2.lstrip('/')
                except Exception:
                    _id = ""

            payload = {"id": _id, "name": name}
            return '[a=cr:' + json.dumps(payload, ensure_ascii=False) + '/]' + name + '[/a]'

        director_obj = meta.get("director", {}) or {}
        director_name = director_obj.get("name", "")
        director_href = director_obj.get("href", "")
        director_click = _cr(director_name, director_href)

        actor_objs = meta.get("actors", []) or []
        actor_click = " ".join([_cr(a.get('name', ''), a.get('href', '')) for a in actor_objs if a.get('name')])

        cat_objs = meta.get("categories", []) or []
        cat_names = [c.get('name', '') for c in cat_objs if c.get('name')]
        cat_click = " ".join([_cr(c.get('name', ''), c.get('href', '')) for c in cat_objs if c.get('name')])

        # 简介只保留标签（按你要求）
        vod_content = f"标签：{cat_click}" if cat_click else ""

        vod = {
            "vod_id": did,
            "vod_name": self.extract_between(html_content, '<h1><b>', '</b></h1>', 0) or "",
            "vod_director": director_click,
            "vod_actor": actor_click,
            "vod_type": ",".join(cat_names),
            "vod_tag": ",".join(cat_names),
            "vod_content": vod_content,
            "vod_play_from": "18AV专线",
            "vod_play_url": play_url,
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        """修复播放地址：

        原代码把真实地址强行拼到 127.0.0.1 的本地代理上（很多环境没有该服务，导致无法播放）。
        这里改为：
        - 如果壳传入的 id 本身就是直链（m3u8/mp4/等）或 http(s)// 开头，直接返回该链接播放
        - 否则才走本地代理兜底（兼容你本地有嗅探/代理的情况）
        """
        url = (id or "").strip()
        if url.startswith("//"):
            url = "https:" + url

        if url.startswith("http://") or url.startswith("https://") or self.isVideoFormat(url):
            return {
                "parse": 0,
                "playUrl": "",
                "url": f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{url}',
                "header": DEFAULT_HEADERS,
            }

        # 兜底：保持原先本地代理逻辑（如果你确实在用该服务）
        return {
            "parse": 0,
            "playUrl": "",
            "url": f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{url}',
            "header": DEFAULT_HEADERS,
        }
