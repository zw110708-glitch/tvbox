# -*- coding: utf-8 -*-
import json
import re
import sys
import hashlib
from base64 import b64decode, b64encode
from urllib.parse import urljoin, quote

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 图片解密依赖（原版使用 pycryptodome）
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

sys.path.append('..')
from base.spider import Spider as BaseSpider


# 图片缓存：避免重复下载/解密（仅内存，进程重启失效）
_img_cache = {}


class Spider(BaseSpider):
    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        elif isinstance(extend, dict):
            cfg = extend

        self.host = (cfg.get("host") or "https://51avhd.com").rstrip("/")
        self.proxies = cfg.get("proxies") or {          "http": "http://127.0.0.1:10172",
          "https": "http://127.0.0.1:10172"}

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Referer": f"{self.host}/",
        }

        self.s = requests.Session()
        retry = Retry(
            total=2,
            backoff_factor=0.4,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "HEAD"),
            raise_on_status=False,
        )
        ad = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        self.s.mount("http://", ad)
        self.s.mount("https://", ad)

    def getName(self):
        return "直链解析器（固定分类·图片解密版）"

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        u = (url or "").lower()
        return ".m3u8" in u or ".mp4" in u

    def _abs(self, u: str) -> str:
        if not u:
            return ""
        return u if u.startswith("http") else urljoin(self.host + "/", u)

    def _get(self, url, timeout=10):
        r = self.s.get(url, headers=self.headers, proxies=self.proxies, timeout=timeout)
        r.encoding = r.apparent_encoding
        return r

    def _soup(self, html: str):
        return BeautifulSoup(html, "lxml")

    def e64(self, text: str) -> str:
        return b64encode(str(text).encode()).decode()

    def d64(self, text: str) -> str:
        return b64decode(str(text).encode()).decode()

    # ---------------- 首页/分类/搜索 ----------------

    def homeContent(self, filter):
        classes = [
            {"type_name": "最近更新", "type_id": "/recent/latest/"},
            {"type_name": "新作上市", "type_id": "/new/release/"},
            {"type_name": "今日热门", "type_id": "/popular/today/"},
            {"type_name": "本周热门", "type_id": "/popular/week/"},
            {"type_name": "本月热门", "type_id": "/popular/month/"},
            {"type_name": "中文字幕", "type_id": "/theme/detail/3/update/"},
            {"type_name": "素人", "type_id": "/tags/3131/latest/"},
            {"type_name": "无码影片", "type_id": "/tags/3361/latest/"},
        ]

        try:
            r = self._get(self.host + "/")
            soup = self._soup(r.text) if r.status_code == 200 else BeautifulSoup("", "lxml")
            return {"class": classes, "filters": {}, "list": self._parse_list(soup)}
        except Exception:
            return {"class": classes, "filters": {}, "list": []}

    def homeVideoContent(self):
        return {"list": self.homeContent(None).get("list", [])}

    def categoryContent(self, tid, pg, filter, extend):
        """最简翻页（按站点固定规则拼接）

        - recent：/recent/ -> /recent/all/{pg}/
        - theme：/theme/detail/3/ -> /theme/detail/3/all/{pg}/
        """
        try:
            pg = int(pg) if str(pg).isdigit() else 1
        except Exception:
            pg = 1

        try:
            u = tid if tid.startswith("http") else self._abs(tid)

            # 规范化到“第一页”URL（避免传入 /latest/ /update/ 等）
            u = re.sub(r"/recent/latest/?$", "/recent/", u)
            u = re.sub(r"/theme/detail/(\d+)/update/?$", r"/theme/detail/\1/", u)
            u = re.sub(r"/all/\d+/?$", "/", u)

            if pg > 1:
                if re.search(r"/recent/?$", u):
                    u = re.sub(r"/recent/?$", f"/recent/all/{pg}/", u)
                elif re.search(r"/theme/detail/\d+/?$", u):
                    u = re.sub(r"/theme/detail/(\d+)/?$", rf"/theme/detail/\1/all/{pg}/", u)
                elif re.search(r"/latest/?$", u):
                    u = re.sub(r"/latest/?$", f"/latest/{pg}/", u)
                else:
                    u = u.rstrip("/") + f"/all/{pg}/"

            r = self._get(u)
            if r.status_code != 200:
                return {"list": [], "page": pg, "pagecount": pg, "limit": 90, "total": 0}

            return {"list": self._parse_list(self._soup(r.text)), "page": pg, "pagecount": 999999, "limit": 90, "total": 999999}
        except Exception:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 90, "total": 0}


    def searchContent(self, key, quick, pg="1"):
        """修复搜索翻页：不同站点可能使用不同分页参数，这里做多种 URL 兜底尝试。"""
        try:
            pg = int(pg) if str(pg).isdigit() else 1
        except Exception:
            pg = 1

        try:
            q = quote(key)

            # 常见搜索分页模式，按顺序尝试
            urls = []
            if pg <= 1:
                urls = [f"{self.host}/?s={q}"]
            else:
                urls = [
                    f"{self.host}/?s={q}&page={pg}",
                    f"{self.host}/?s={q}&paged={pg}",
                    f"{self.host}/page/{pg}/?s={q}",
                    f"{self.host}/?s={q}",
                ]

            soup = None
            out_list = []
            for u in urls:
                r = self._get(u)
                if r.status_code != 200:
                    continue
                soup0 = self._soup(r.text)
                lst = self._parse_list(soup0)
                # pg>1 时允许空（可能无结果），但优先用有列表的页面
                if lst or pg <= 1:
                    soup = soup0
                    out_list = lst
                    break
            else:
                return {"list": [], "page": pg, "pagecount": 1}

            # pagecount：优先解析 van-pagination / pagination 的数字页
            pagecount = 1
            try:
                nums = []
                for a in soup.select('ul.van-pagination__items a[href]'):
                    t = (a.get_text(strip=True) or "")
                    if t.isdigit():
                        nums.append(int(t))
                if not nums:
                    for a in soup.select('.pagination a[href]'):
                        t = (a.get_text(strip=True) or "")
                        if t.isdigit():
                            nums.append(int(t))
                if nums:
                    pagecount = max(nums)
            except Exception:
                pagecount = 1

            return {"list": out_list, "page": pg, "pagecount": pagecount}
        except Exception:
            return {"list": [], "page": 1, "pagecount": 1}

    def _parse_list(self, soup: BeautifulSoup):
        out, seen = [], set()
        for a in soup.select('a[href*="/videos/"]'):
            href = (a.get("href") or "").strip()
            if not href or "/videos/" not in href:
                continue
            vid = self._abs(href)
            if vid in seen:
                continue

            img = a.find("img")
            pic = ""
            title = ""
            if img:
                pic = (img.get("z-image-loader-url") or img.get("data-src") or img.get("data-original") or img.get("src") or "").strip()
                title = (img.get("alt") or "").strip()

            if not title:
                title = a.get_text(" ", strip=True)
            if not title or any(x in title for x in ("日本語", "English", "简体中文", "登出", "登录", "注册")):
                continue

            if not pic:
                p = a.parent
                img2 = p.find("img") if p else None
                if img2:
                    pic = (img2.get("z-image-loader-url") or img2.get("data-src") or img2.get("data-original") or img2.get("src") or "").strip()

            if not pic:
                continue

            # 关键：封面走本地代理（解密）
            pic_url = self._abs(pic)
            pic_proxy = f"{self.getProxyUrl()}&type=img&url={self.e64(pic_url)}"

            seen.add(vid)
            out.append({"vod_id": vid, "vod_name": title, "vod_pic": pic_proxy, "vod_remarks": ""})

        return out

    # ---------------- 详情/播放（直链） ----------------

    def detailContent(self, ids):
        try:
            url = ids[0]
            url = url if url.startswith("http") else self._abs(url)
            r = self._get(url)
            if r.status_code != 200:
                return {"list": [{"vod_play_from": "直链", "vod_play_url": ""}]}

            html = r.text
            soup = self._soup(html)
            t = soup.select_one("h1") or soup.select_one("title")
            title = t.get_text(strip=True) if t else ""

            # -------- 详情信息：演员/类型/导演(发行商)/标签（可点击 a=cr） --------
            def mk_click(name: str, href: str) -> str:
                name = (name or "").strip()
                href = (href or "").strip()
                if not name or not href:
                    return ""
                try:
                    return f'[a=cr:{json.dumps({"id": href, "name": name}, ensure_ascii=False)}/]{name}[/a]'
                except Exception:
                    return name

            vod_actor = ""
            try:
                actors = []
                for a in soup.select('div.actors-list a[href]'):
                    nm = a.get_text(" ", strip=True)
                    href = a.get('href')
                    c = mk_click(nm, href)
                    if c:
                        actors.append(c)
                if actors:
                    vod_actor = " ".join(actors)
            except Exception:
                vod_actor = ""

            # 类型（按你给的“演员”代码格式：list + for + if 写法）
            type_txt = ""
            try:
                types = []
                for row in soup.select('div.text-secondary'):
                    lab = row.select_one('span.info-label')
                    if not lab:
                        continue
                    if lab.get_text(strip=True).replace(' ', '') != '类型:':
                        continue

                    box = row.select_one('div.tags-list')
                    if not box:
                        continue

                    for a in box.select('a[href]'):
                        name = a.get_text(" ", strip=True)
                        href = a.get('href')
                        if name and href:
                            types.append(mk_click(name, href))
                    break

                if types:
                    type_txt = '类型: ' + ' / '.join(types)
            except Exception:
                type_txt = ""

            # 导演（按 list + for + if；输出到 vod_director）
            vod_director = ""
            try:
                directors = []
                for row in soup.select('div.text-secondary'):
                    lab = row.select_one('span.info-label')
                    if not lab:
                        continue
                    t0 = lab.get_text(strip=True).replace(' ', '')
                    if t0 not in ('导演:', '发行商:'):
                        continue

                    a = row.select_one('a[href]')
                    if a:
                        name = a.get_text(" ", strip=True)
                        href = a.get('href')
                        if name and href:
                            directors.append(mk_click(name, href))
                    break

                if directors:
                    vod_director = ' '.join(directors)
            except Exception:
                vod_director = ""

            tags_txt = ""
            try:
                tags = []

                # 1) 优先找“标签:”对应的 tags-list
                tag_label = None
                for sp in soup.select('span.info-label'):
                    if '标签' in sp.get_text(strip=True):
                        tag_label = sp
                        break
                if tag_label:
                    box = tag_label.find_next('div', class_='tags-list')
                    if box:
                        for a in box.select('a[href]'):
                            c = mk_click(a.get_text(" ", strip=True), a.get('href'))
                            if c:
                                tags.append(c)

                # 2) 兼容你给的结构：span.ctg a
                if not tags:
                    for sp in soup.select('span.ctg'):
                        a = sp.find('a', href=True)
                        if a:
                            c = mk_click(a.get_text(" ", strip=True), a.get('href'))
                            if c:
                                tags.append(c)

                if tags:
                    tags_txt = '标签: ' + ' '.join(tags)
            except Exception:
                tags_txt = ""

            # 类型放到 vod_remarks；导演独立放 vod_director
            vod_remarks = type_txt or ""

            vod_content = title
            if tags_txt:
                vod_content = tags_txt + "\\n" + vod_content

            links = self._sniff(html, soup)

            if not links:
                iframe = soup.find("iframe")
                src = (iframe.get("src") or iframe.get("data-src") or "").strip() if iframe else ""
                if src:
                    rr = self._get(self._abs(src), timeout=10)
                    if rr.status_code == 200:
                        links = self._sniff(rr.text, self._soup(rr.text))

            play_url = "#".join([f"线路{i+1}${u}" for i, u in enumerate(links)])
            return {"list": [{"vod_name": title, "vod_actor": vod_actor, "vod_director": vod_director, "vod_remarks": vod_remarks, "vod_play_from": "直链", "vod_play_url": play_url, "vod_content": vod_content}]}
        except Exception:
            return {"list": [{"vod_play_from": "直链", "vod_play_url": ""}]}

    def _sniff(self, html: str, soup: BeautifulSoup):
        out, seen = [], set()

        def add(u: str):
            if not u:
                return
            u = u.strip().strip('"\'')
            if not self.isVideoFormat(u):
                return
            u = self._abs(u)
            if u in seen:
                return
            seen.add(u)
            out.append(u)

        for v in soup.find_all("video"):
            add(v.get("src") or "")
            for s in v.find_all("source"):
                add(s.get("src") or "")

        for a in soup.select('a[href*=".m3u8"], a[href*=".mp4"]'):
            add(a.get("href") or "")

        for m in re.finditer(r"(https?://[^\s\"']+\.(?:m3u8|mp4)[^\s\"']*)", html, re.I):
            add(m.group(1))

        return out

    def playerContent(self, flag, id, vipFlags):
        return {"parse": 0, "url": f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{id}', "header": self.headers}

    # ---------------- 本地代理：仅图片解密 ----------------

    def localProxy(self, param):
        try:
            t = param.get("type")
            if t == "cache":
                key = param.get("key")
                b = _img_cache.get(key)
                return [200, "image/jpeg", b] if b else [404, "text/plain", b""]

            if t != "img":
                return [404, "text/plain", b""]

            url = param.get("url") or ""
            real = self.d64(url) if not url.startswith("http") else url

            r = self.s.get(real, headers=self.headers, proxies=self.proxies, timeout=10)
            raw = r.content or b""

            # 若已是正常图片头，直接返回
            if raw.startswith(b"\xff\xd8"):
                mime = "image/jpeg"
                out = raw
            elif raw.startswith(b"\x89PNG"):
                mime = "image/png"
                out = raw
            elif raw.startswith(b"GIF8"):
                mime = "image/gif"
                out = raw
            else:
                out = self.aesimg(raw)
                # 尝试根据头判断 mime
                mime = "image/jpeg"
                if out.startswith(b"\x89PNG"):
                    mime = "image/png"
                elif out.startswith(b"GIF8"):
                    mime = "image/gif"

            # cache
            key = hashlib.md5(out).hexdigest()
            _img_cache[key] = out
            return [200, mime, out]
        except Exception:
            return [404, "text/plain", b""]

    def aesimg(self, data: bytes) -> bytes:
        """AES 解密图片（复用原版逻辑，尽量保持兼容）"""
        if not data or len(data) < 16:
            return data

        keys = [
            (b"f5d965df75336270", b"97b60394abc2fbe1"),
            (b"75336270f5d965df", b"abc2fbe197b60394"),
        ]

        for k, v in keys:
            # CBC
            try:
                dec = unpad(AES.new(k, AES.MODE_CBC, v).decrypt(data), 16)
                if dec.startswith((b"\xff\xd8", b"\x89PNG", b"GIF8")):
                    return dec
            except Exception:
                pass
            # ECB
            try:
                dec = unpad(AES.new(k, AES.MODE_ECB).decrypt(data), 16)
                if dec.startswith((b"\xff\xd8", b"\x89PNG", b"GIF8")):
                    return dec
            except Exception:
                pass

        return data
