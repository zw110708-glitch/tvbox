import json
import re
import sys
from base64 import b64decode, b64encode
from html import unescape
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def init(self, extend=""):
        cfg = extend
        if isinstance(extend, str):
            cfg = json.loads(extend) if extend.strip() else {}
        if not isinstance(cfg, dict):
            cfg = {}

        self.host = (cfg.get("host") or "https://missavt.com").rstrip("/")
        self.proxies = cfg.get("proxies") or {          "http": "http://127.0.0.1:10172",
          "https": "http://127.0.0.1:10172"}

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Referer": f"{self.host}/",
            "Origin": self.host,
        }

        self._session = requests.Session()
        self._session.headers.update(self.headers)

    def getName(self):
        return "MissAVt 直链极简"

    def manualVideoCheck(self):
        return False

    def _abs(self, u: str) -> str:
        if not u:
            return ""
        u = unescape(u.strip())
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        return urljoin(self.host + "/", u.lstrip("/"))

    def _get_text(self, url: str) -> str:
        r = self._session.get(url, proxies=self.proxies, timeout=(6, 12))
        r.encoding = r.apparent_encoding
        return r.text

    def _soup_from_url(self, url: str) -> BeautifulSoup:
        return BeautifulSoup(self._get_text(url), "lxml")

    def e64(self, text: str) -> str:
        return b64encode(str(text).encode()).decode()

    def d64(self, text: str) -> str:
        return b64decode(str(text).encode()).decode()

    def aesimg(self, data: bytes) -> bytes:
        if not data or len(data) < 16:
            return data

        keys = [
            (b"f5d965df75336270", b"97b60394abc2fbe1"),
            (b"75336270f5d965df", b"abc2fbe197b60394"),
        ]

        def ok(b: bytes) -> bool:
            return b.startswith(b"\xff\xd8") or b.startswith(b"\x89PNG") or b.startswith(b"GIF8")

        for k, iv in keys:
            try:
                dec = unpad(AES.new(k, AES.MODE_CBC, iv).decrypt(data), 16)
                if ok(dec):
                    return dec
            except Exception:
                pass
            try:
                dec = unpad(AES.new(k, AES.MODE_ECB).decrypt(data), 16)
                if ok(dec):
                    return dec
            except Exception:
                pass

        return data

    def _img_proxy(self, img_url: str) -> str:
        return f"{self.getProxyUrl()}&type=img&url={self.e64(img_url)}" if img_url else ""

    def localProxy(self, param):
        if param.get("type") != "img":
            return [404, "text/plain", b""]

        url = self.d64(param.get("url") or "")
        if not url:
            return [404, "text/plain", b""]

        r = self._session.get(url, proxies=self.proxies, timeout=(6, 12))
        dec = self.aesimg(r.content or b"")

        if dec.startswith(b"\xff\xd8"):
            ct = "image/jpeg"
        elif dec.startswith(b"\x89PNG"):
            ct = "image/png"
        elif dec.startswith(b"GIF8"):
            ct = "image/gif"
        else:
            ct = "application/octet-stream"

        return [200, ct, dec]

    def homeContent(self, filter):
        soup = self._soup_from_url(self.host + "/")

        fixed = [
            ("最近更新", "/sort/renew/"),
            ("热门影片", "/sort/month_hot/"),
            ("有码", "/category/censored/"),
            ("素人", "/category/amateur/"),
            ("中文字幕", "/category/chinese-subtitle/"),
            ("无码破解", "/category/reducing-mosaic/"),
            ("麻豆传媒", "/category/madou/"),
            ("swag", "/category/swag/"),
            ("糖心vlog", "/category/sweet-heart-vlog/"),
            ("ed mosaic", "/category/ed-mosaic/"),
            ("抖阴", "/category/douyin/"),
            ("91制片厂", "/category/91-studio/"),
            ("兔子先生", "/category/mr-rabbit/"),
            ("国产传媒", "/category/domestic-media/"),
            ("无码流出", "/category/uncensored-leak/"),
            ("FC2", "/category/fc2/"),
            ("东京热", "/category/tokyohot/"),
            ("人妻斩", "/category/marriedslash/"),
            ("HEYZO", "/category/heyzo/"),
            ("一本道", "/category/1pondo/"),
        ]
        classes = [{"type_name": n, "type_id": self._abs(h)} for n, h in fixed]
        return {"class": classes, "filters": {}, "list": self._parse_video_items(soup)}

    def homeVideoContent(self):
        return {"list": self.homeContent(None).get("list", [])}

    def _with_page(self, url: str, pg: int) -> str:
        if pg <= 1:
            return url
        base = (url or "").split("?", 1)[0]
        if not base.endswith("/"):
            base += "/"
        return f"{base}{pg}/"

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if pg else 1
        url = tid if tid.startswith("http") else self._abs(tid)
        soup = self._soup_from_url(self._with_page(url, pg))
        return {"list": self._parse_video_items(soup), "page": pg, "pagecount": 9999, "limit": 90, "total": 999999}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if pg else 1
        url = self._abs(f"/search/{quote(key)}/")
        soup = self._soup_from_url(self._with_page(url, pg))
        return {"list": self._parse_video_items(soup), "page": pg, "pagecount": 9999}

    def _parse_video_items(self, soup: BeautifulSoup):
        videos, seen = [], set()
        for li in soup.select("ul.video-items > li"):
            a = li.select_one("div.video-item a[href]") or li.select_one("a[href]")
            if not a:
                continue

            href = self._abs(a.get("href") or "")
            if not href or href in seen:
                continue

            title = ""
            t = li.select_one("a.line-clamp-2")
            if t:
                title = t.get_text(" ", strip=True)
            if not title:
                img_alt = li.select_one("img[alt]")
                title = (img_alt.get("alt") or "").strip() if img_alt else ""

            img = ""
            img_tag = li.select_one("img")
            if img_tag:
                img = img_tag.get("data-src") or img_tag.get("src") or ""
            vod_pic = self._img_proxy(self._abs(img)) if img else ""
            if not vod_pic:
                continue

            dur = li.select_one(".text-sm.opacity-50")
            remark = dur.get_text(" ", strip=True) if dur else ""

            seen.add(href)
            videos.append(
                {
                    "vod_id": href,
                    "vod_name": title,
                    "vod_pic": vod_pic,
                    "vod_remarks": remark,
                    "style": {"type": "rect", "ratio": 1.77},
                }
            )
            if len(videos) >= 90:
                break

        return videos

    def _unpack_packer(self, packed_js: str) -> str:
        def read_sq(s: str, start: int):
            i = start + 1
            out = []
            while i < len(s):
                ch = s[i]
                if ch == "\\" and i + 1 < len(s):
                    out.append(s[i + 1])
                    i += 2
                    continue
                if ch == "'":
                    return "".join(out), i + 1
                out.append(ch)
                i += 1
            return "", -1

        pos = packed_js.find("}('")
        if pos == -1:
            return ""

        payload, p_end = read_sq(packed_js, pos + 2)
        if p_end == -1:
            return ""

        rest = packed_js[p_end:]
        m = re.search(r"\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*'", rest)
        if not m:
            return ""
        a = int(m.group(1))
        c = int(m.group(2))

        k_start = p_end + m.end(0) - 1
        k_str, k_end = read_sq(packed_js, k_start)
        if k_end == -1:
            return ""
        k = k_str.split("|")

        chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

        def baseN(num: int, b: int) -> str:
            if num == 0:
                return "0"
            s2 = ""
            while num:
                s2 = chars[num % b] + s2
                num //= b
            return s2

        out = payload
        for i in range(c - 1, -1, -1):
            token = baseN(i, a)
            if i < len(k) and k[i]:
                out = re.sub(rf"\b{re.escape(token)}\b", k[i], out)
        return out

    def _extract_main_play_url(self, soup: BeautifulSoup) -> str:
        for sc in soup.find_all("script"):
            txt = sc.string or sc.get_text() or ""
            if "eval(function(p,a,c,k,e,d)" not in txt:
                continue
            unpacked = self._unpack_packer(txt)
            if not unpacked:
                continue
            m = re.search(
                r"create_player\s*\(\s*\{.*?(?:['\"]url['\"]|\burl\b)\s*:\s*['\"](?P<url>[^'\"]+)['\"]",
                unpacked,
                re.S,
            )
            if m:
                return self._abs(m.group("url"))

        player = soup.select_one(".player-container")
        if player:
            m = re.search(r"https?://[^\s\"']+\.(?:m3u8|mp4|webm)(?:\?[^\s\"']*)?", str(player), re.I)
            if m:
                return unescape(m.group(0))

        return ""

    def detailContent(self, ids):
        url = ids[0]
        url = url if url.startswith("http") else self._abs(url)

        html = self._get_text(url)
        soup = BeautifulSoup(html, "lxml")

        h1 = soup.select_one("h1")
        title = h1.get_text(" ", strip=True).strip() if h1 else ""
        if not title and soup.title:
            title = soup.title.get_text(strip=True).replace("- MissAVt", "").strip()

        og = soup.select_one('meta[property="og:image"], meta[name="twitter:image"]')
        cover = self._abs(og.get("content")) if og and og.get("content") else ""

        play = self._extract_main_play_url(soup)

        vod_content_parts = []
        tags = []
        tags_ul = soup.select_one("ul.flex.flex-wrap.text-default")
        if tags_ul:
            for a in tags_ul.select("a[href]"):
                name = a.get_text(" ", strip=True)
                href = a.get("href") or ""
                if name and href and "javascript" not in href:
                    href = self._abs(href)
                    tags.append(f'[a=cr:{json.dumps({"id": href, "name": name}, ensure_ascii=False)}/]{name}[/a]')

        if tags:
            vod_content_parts.append("标签: " + " ".join(tags))

        intro = ""
        intro_el = soup.select_one("h2.bg-base1.dx-text") or soup.select_one("h2.dx-text")
        if intro_el:
            intro = intro_el.get_text(" ", strip=True)
        if intro:
            vod_content_parts.append("视频介绍: " + intro)

        vod_content = "\n".join(vod_content_parts).strip() or title

        return {
            "list": [
                {
                    "vod_id": url,
                    "vod_name": title,
                    "vod_pic": self._img_proxy(cover) if cover else "",
                    "vod_play_from": "直链",
                    "vod_play_url": f"直链${play}" if play else "",
                    "vod_content": vod_content,
                }
            ]
        }

    def playerContent(self, flag, id, vipFlags):
        return {"parse": 0, "url": f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{id}', "header": self.headers}
