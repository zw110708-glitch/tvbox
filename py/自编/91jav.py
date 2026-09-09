import json
import re
import sys
import hashlib
from base64 import b64encode, b64decode
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    host_default = "https://www.91jav1.com"

    classes = [
        {"type_name": "最近更新", "type_id": "/cn/new/{pg}"},
        {"type_name": "新作上市", "type_id": "/cn/release/{pg}"},
        {"type_name": "热门(本周)", "type_id": "/cn/popular/week/{pg}"},
        {"type_name": "中文字幕(今日更新)", "type_id": "/cn/theme/detail/3/update/{pg}"},
        {"type_name": "无码影片(近期最佳)", "type_id": "/cn/theme/detail/11/hot/{pg}"},
    ]

    sel_list_img = 'a[href*="/videos/"] img.zximg'
    sel_list_a = 'a[href*="/videos/"]'

    re_play = re.compile(r"(https?://[^\s'\"]+\.(?:m3u8|mp4)(?:\?[^'\"\s]*)?)", re.I)

    bad_hints = (
        "banner",
        "swiper",
        "carousel",
        "slider",
        "recommend",
        "ranking",
        "rank",
        "hot",
        "hot-list",
        "hot_video",
        "hotvideo",
        "popular",
        "sticky",
        "fixed",
        "ads",
        "ad-",
    )

    re_noise_title = re.compile(r"^(?:排名\s*\d+|热门\s*\d+|热门)$")

    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        elif isinstance(extend, dict):
            cfg = extend

        self.host = (cfg.get("host") or self.host_default).rstrip("/")
        self.proxies = cfg.get("proxies") or {          "http": "http://127.0.0.1:10172",
          "https": "http://127.0.0.1:10172"}

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": f"{self.host}/",
        }
        self._img_cache = {}

    def getName(self):
        return "91JAV-直链-极简"

    def isVideoFormat(self, url):
        u = (url or "").lower()
        return u.endswith((".m3u8", ".mp4")) or ".m3u8?" in u or ".mp4?" in u

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self._img_cache.clear()

    # -------------------- home / category / search --------------------

    def homeContent(self, _filter):
        return {"class": self.classes, "filters": {}, "list": self._fetch_list_page(f"{self.host}/cn/new")}

    def homeVideoContent(self):
        return {"list": self._fetch_list_page(f"{self.host}/cn/new")}

    def categoryContent(self, tid, pg, _filter, _extend):
        pg = int(pg) if pg else 1
        if tid.startswith("http"):
            url = tid
        else:
            url = urljoin(self.host + "/", self._render_page_path(tid, pg).lstrip("/"))
        return {"list": self._fetch_list_page(url), "page": pg, "pagecount": 9999, "limit": 90, "total": 999999}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if pg else 1
        kw = quote(key)
        tid = f"/cn/search/{kw}/{{pg}}"
        url = urljoin(self.host + "/", self._render_page_path(tid, pg).lstrip("/"))
        return {"list": self._fetch_list_page(url), "page": pg, "pagecount": 9999}

    # -------------------- detail / player --------------------

    def detailContent(self, ids):
        url = ids[0]
        if not url.startswith("http"):
            url = urljoin(self.host + "/", url.lstrip("/"))

        html = self._get(url)
        soup = BeautifulSoup(html, "lxml")

        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else ""
        if not title:
            t = soup.find("title")
            title = t.get_text(strip=True) if t else ""

        des = soup.select_one(".jav-detail-des")

        # 演员（精准区域 + latest/{pg}）
        actors = []
        if des:
            for a in des.select('a[href^="/cn/actress/detail/"]'):
                name = a.get_text(strip=True)
                href = self._norm_latest(a.get("href") or "")
                self._append_unique(actors, (name, href), 20)

        for a in soup.select('.models a[href^="/cn/actress/detail/"]'):
            name = (a.get("title") or a.get_text(strip=True) or "").strip()
            href = self._norm_latest(a.get("href") or "")
            self._append_unique(actors, (name, href), 20)

        # 分类(cat) + 标签（h5.jav-detail-tags）
        cats, tags = [], []
        h5 = soup.select_one("h5.jav-detail-tags")
        if h5:
            for a in h5.select('a.cat[href^="/cn/theme/detail/"]'):
                name = (a.select_one("em").get_text(strip=True) if a.select_one("em") else a.get_text(strip=True)).strip()
                href = self._norm_update(a.get("href") or "")
                self._append_unique(cats, (name, href), 20)

            for a in h5.select('a[href^="/cn/tags/"]'):
                name = (a.select_one("em").get_text(strip=True) if a.select_one("em") else a.get_text(strip=True)).strip()
                href = self._norm_latest(a.get("href") or "")
                self._append_unique(tags, (name, href), 40)

        intro = self._extract_intro(soup)

        content_parts = []
        if cats:
            content_parts.append("分类: " + " ".join(self._mk_click(n, h) for n, h in cats))
        if tags:
            content_parts.append("标签: " + " ".join(self._mk_click(n, h) for n, h in tags))
        if intro:
            content_parts.append(intro)

        play = []
        seen = set()
        for m in self.re_play.finditer(html):
            u = m.group(1)
            if u not in seen:
                seen.add(u)
                play.append(f"直链${u}")

        vod = {
            "vod_name": title or "",
            "vod_play_from": "91JAV",
            "vod_play_url": "#".join(play) if play else f"网页播放${url}",
            "vod_content": "\n".join(content_parts).strip() or title or "",
        }
        if actors:
            vod["vod_actor"] = " ".join(self._mk_click(n, h) for n, h in actors)
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        return {"parse": 0 , "url": f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{id}', "header": self.headers}

    # -------------------- local proxy (img) --------------------

    def localProxy(self, param):
        if param.get("type") != "img":
            return [404, "text/plain", b""]

        try:
            real_url = self._d64(param.get("url") or "")
        except Exception:
            return [404, "text/plain", b""]

        if not real_url.startswith("http"):
            return [404, "text/plain", b""]

        key = hashlib.md5(real_url.encode("utf-8")).hexdigest()
        if key in self._img_cache:
            return [200, "image/jpeg", self._img_cache[key]]

        headers = dict(self.headers)
        headers["Referer"] = self.host + "/"
        r = requests.get(real_url, headers=headers, proxies=self.proxies, timeout=10)
        data = self._aes_img_maybe(r.content or b"")

        mime = "image/jpeg"
        if data.startswith(b"\x89PNG"):
            mime = "image/png"
        elif data.startswith(b"GIF8"):
            mime = "image/gif"

        self._img_cache[key] = data
        return [200, mime, data]

    # -------------------- helpers --------------------

    def _get(self, url: str) -> str:
        r = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=10)
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text

    def _render_page_path(self, tid: str, pg: int) -> str:
        t = (tid or "").strip()
        if not t.startswith("/") and not t.startswith("http"):
            t = "/" + t

        if "{pg}" in t:
            path = t.replace("{pg}", str(pg))
        else:
            path = t if pg == 1 else (t.rstrip("/") + f"/{pg}")

        if pg == 1 and path.endswith("/1"):
            path = path[:-2]
        return path

    def _in_bad_container(self, tag) -> bool:
        cur = tag
        for _ in range(8):
            if not cur or not getattr(cur, "attrs", None):
                cur = getattr(cur, "parent", None)
                continue
            s = ((cur.get("id") or "") + " " + " ".join(cur.get("class") or [])).lower()
            if s and any(h in s for h in self.bad_hints):
                return True
            cur = getattr(cur, "parent", None)
        return False

    def _fetch_list_page(self, url: str):
        doc = BeautifulSoup(self._get(url), "lxml")

        a_nodes = []
        for img in doc.select(self.sel_list_img):
            a = img.find_parent("a")
            if a:
                a_nodes.append(a)
        if not a_nodes:
            a_nodes = doc.select(self.sel_list_a)

        out, seen = [], set()
        for a in a_nodes:
            href = (a.get("href") or "").strip()
            if "/videos/" not in href:
                continue
            if self._in_bad_container(a):
                continue

            full = href if href.startswith("http") else urljoin(self.host + "/", href.lstrip("/"))
            if full in seen:
                continue

            img = a.find("img")
            title = (img.get("alt") if img else "") or (a.get("title") or a.get_text(strip=True) or "")
            title = re.sub(r"\s*\d{1,3}(?:,\d{3})+\s*$", "", title).strip()
            if not title:
                continue

            # 过滤：演员/标签/搜索列表末尾常混入“排名1/热门...”等推荐块
            if self.re_noise_title.match(title) or ("热门" in title and len(title) <= 6):
                continue

            pic = ""
            if img:
                pic = (img.get("z-image-loader-url") or img.get("data-src") or img.get("data-original") or img.get("src") or "").strip()

            card = a
            for _ in range(3):
                if card.parent and getattr(card.parent, "name", None) in ("div", "li", "article"):
                    card = card.parent

            badge = ""
            dur = ""
            b = card.select_one('.absolute-bottom-left span')
            if b:
                badge = b.get_text(strip=True)
            d = card.select_one('.absolute-bottom-right .label') or card.select_one('.absolute-bottom-right span')
            if d:
                dur = d.get_text(strip=True)

            out.append(
                {
                    "vod_id": full,
                    "vod_name": title,
                    "vod_pic": self._img_proxy(pic) if pic else "",
                    "vod_remarks": " ".join(x for x in (badge, dur) if x),
                    "style": {"type": "rect", "ratio": 1.01},
                }
            )
            seen.add(full)

        return out

    def _img_proxy(self, real_url: str) -> str:
        if not real_url:
            return ""
        if not real_url.startswith("http"):
            real_url = urljoin(self.host + "/", real_url.lstrip("/"))
        return f"{self.getProxyUrl()}&type=img&url={self._e64(real_url)}"

    def _aes_img_maybe(self, data: bytes) -> bytes:
        if not data or len(data) < 16:
            return data
        if data.startswith((b"\xff\xd8", b"\x89PNG", b"GIF8")):
            return data

        keys = (
            (b"f5d965df75336270", b"97b60394abc2fbe1"),
            (b"75336270f5d965df", b"abc2fbe197b60394"),
        )

        for k, iv in keys:
            try:
                dec = unpad(AES.new(k, AES.MODE_CBC, iv).decrypt(data), 16)
                if dec.startswith((b"\xff\xd8", b"\x89PNG", b"GIF8")):
                    return dec
            except Exception:
                pass
            try:
                dec = unpad(AES.new(k, AES.MODE_ECB).decrypt(data), 16)
                if dec.startswith((b"\xff\xd8", b"\x89PNG", b"GIF8")):
                    return dec
            except Exception:
                pass
        return data

    def _mk_click(self, name: str, href: str) -> str:
        name = (name or "").strip()
        href = (href or "").strip()
        if not name or not href:
            return ""
        payload = json.dumps({"id": href, "name": name}, ensure_ascii=False, separators=(",", ":"))
        return f"[a=cr:{payload}/]{name}[/a]"

    def _append_unique(self, arr, item, limit: int):
        name, href = item
        name = (name or "").strip()
        href = (href or "").strip()
        if not name or not href:
            return
        if (name, href) in arr:
            return
        if len(arr) >= limit:
            return
        arr.append((name, href))

    def _norm_latest(self, href: str) -> str:
        h = (href or "").strip()
        h = re.sub(r"/latest/\d+/?$", r"/latest/{pg}", h)
        if "/latest/" not in h:
            h = h.rstrip("/") + "/latest/{pg}"
        return h

    def _norm_update(self, href: str) -> str:
        h = (href or "").strip()
        h = re.sub(r"/update/\d+/?$", r"/update/{pg}", h)
        if "/update/" not in h:
            h = h.rstrip("/") + "/update/{pg}"
        return h

    def _extract_intro(self, soup: BeautifulSoup) -> str:
        h = None
        for node in soup.select("h1,h2,h3"):
            if node.get_text(strip=True) == "影片介绍":
                h = node
                break
        if not h:
            h = soup.find("h2", class_=re.compile(r"h3-md"))
            if h and h.get_text(strip=True) != "影片介绍":
                h = None
        if not h:
            return ""

        parts = []
        for sib in h.next_siblings:
            if getattr(sib, "name", None) in ("h1", "h2", "h3"):
                break
            if isinstance(sib, str):
                t = sib.strip()
                if t:
                    parts.append(t)
            else:
                t = sib.get_text(" ", strip=True)
                if t:
                    parts.append(t)
        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    def _e64(self, text: str) -> str:
        return b64encode(text.encode("utf-8")).decode("utf-8")

    def _d64(self, text: str) -> str:
        return b64decode(text.encode("utf-8")).decode("utf-8")
