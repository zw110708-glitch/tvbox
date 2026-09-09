import base64
import html
import json
import re
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

import sys

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    HOST_DEFAULT = "https://cgw666.com"

    IMG_AES_KEY = b"97b60394abc2fbe1"
    IMG_AES_IV = b"f5d965df75336270"

    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend) or {}
            except Exception:
                cfg = {}
        elif isinstance(extend, dict):
            cfg = extend or {}

        self.proxies = cfg.get("proxies") or {          "http": "http://127.0.0.1:10172",

          "https": "http://127.0.0.1:10172"}
        host = (cfg.get("host") or "").strip()
        self.host = (host or self.HOST_DEFAULT).rstrip("/")

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.host + "/",
        }

        self.sess = requests.Session()
        self.sess.headers.update(self.headers)
        self._play_cache = {}

    def getName(self):
        return "吃瓜网(cgw666)直链修复版"

    def isVideoFormat(self, url):
        u = (url or "").lower()
        return ".m3u8" in u or ".mp4" in u

    def manualVideoCheck(self):
        return False

    def homeContent(self, filter):
        soup = self._soup(self._get(self.host + "/"))
        classes = []
        for a in soup.select(".category-list a[href]"):
            name = a.get_text(strip=True)
            href = (a.get("href") or "").strip()
            if name and href:
                classes.append({"type_name": name, "type_id": self._abs(href)})
        return {"class": classes, "filters": {}, "list": self._parse_cards(soup)}

    def homeVideoContent(self):
        return {"list": self.homeContent(None).get("list", [])}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        base = tid if str(tid).startswith("http") else self._abs(str(tid))
        base = base.rstrip("/") + "/"
        url = base if pg == 1 else base + f"{pg}/"
        soup = self._soup(self._get(url))
        return {"list": self._parse_cards(soup), "page": pg, "pagecount": 9999, "limit": 90, "total": 999999}

    def detailContent(self, ids):
        url = ids[0] if str(ids[0]).startswith("http") else self._abs(str(ids[0]))
        html_txt = self._get(url)
        soup = self._soup(html_txt)

        h1 = soup.select_one("h1.post-title") or soup.select_one("h1")
        title = h1.get_text(" ", strip=True) if h1 else ""
        if not title and soup.title:
            title = (soup.title.get_text(strip=True) or "").split("|")[0].strip()

        cover = self._pick_cover(soup) or self._pick_site_logo(soup)
        vod_pic = self._proxy_img(cover) if cover else ""

        tags = []
        kw_div = soup.select_one('div.keywords[itemprop="keywords"], div[itemprop="keywords"].keywords')
        if kw_div:
            for a in kw_div.select('a[href]'):
                name = a.get_text(strip=True)
                href = (a.get('href') or '').strip()
                if name and href:
                    tags.append(
                        f"[a=cr:{json.dumps({'id': self._abs(href), 'name': name}, ensure_ascii=False)}/]{name}[/a]"
                    )

        post_content = soup.select_one(".post-content")
        vod_content = ""
        if post_content:
            vod_content = re.sub(r"\s+", " ", post_content.get_text(" ", strip=True)).strip()
            if len(vod_content) > 500:
                vod_content = vod_content[:500]

        final_content = "\n".join([x for x in ["标签: " + " ".join(tags) if tags else "", "影片介绍: " + vod_content if vod_content else ""] if x]).strip() or title

        play_items = []
        idx = 1

        for dp in soup.select(".dplayer[data-config]"):
            real = self._extract_real_from_dplayer(dp)
            if real and self.isVideoFormat(real):
                play_items.append(f"播放{idx}${real}")
                idx += 1

        if not play_items and post_content:
            seen = set()
            for a in post_content.select('a.btn.btn-primary'):
                href = (a.get('href') or a.get('data-href') or a.get('data-url') or '').strip()
                if not href:
                    continue
                hl = href.lower()
                if href in ("#", "/", "1") or hl.startswith("javascript:"):
                    continue
                abs_url = href if href.startswith("http") else self._abs(href)
                if "/archives/" not in abs_url:
                    continue
                if abs_url in seen:
                    continue
                seen.add(abs_url)
                play_items.append(f"播放{idx}${abs_url}")
                idx += 1

        vod_play_url = "#".join(play_items) if play_items else ("网页$" + url)

        vod = {
            "vod_id": url,
            "vod_name": title or "详情",
            "vod_pic": vod_pic,
            "vod_content": final_content,
            "vod_play_from": "直链",
            "vod_play_url": vod_play_url,
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg or 1)
        key_q = quote(key)
        base = f"{self.host}/search/{key_q}/"
        url = base if pg == 1 else base + f"{pg}/"
        soup = self._soup(self._get(url))
        return {"list": self._parse_cards(soup), "page": pg, "pagecount": 9999}

    def playerContent(self, flag, id, vipFlags):
        pid = (id or "").strip()
        if not pid:
            return {"parse": 1, "url": "", "header": self.headers}

        if self.isVideoFormat(pid):
            h = dict(self.headers)
            h.update({"Accept": "*/*", "Origin": self.host})
            return {"parse": 0, "url": f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pid}', "header": h}

        if "/archives/" in pid:
            detail_url = pid if pid.startswith("http") else self._abs(pid)
            real = self._play_cache.get(detail_url)
            if not real:
                real = self._extract_real_video_from_detail(detail_url)
                if real:
                    self._play_cache[detail_url] = real
            if real and self.isVideoFormat(real):
                h = dict(self.headers)
                h.update({"Accept": "*/*", "Origin": self.host, "Referer": detail_url})
                return {"parse": 0, "url": f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{real}', "header": h}

        return {"parse": 1, "url": pid, "header": self.headers}

    def localProxy(self, param):
        try:
            if (param.get("type") or "").strip() != "img":
                return [404, "text/plain", b""]

            real = self._d64(param.get("url") or "")
            if not real:
                return [404, "text/plain", b""]

            r = self.sess.get(
                real,
                headers={"User-Agent": self.headers["User-Agent"], "Referer": self.host + "/"},
                timeout=8,
                proxies=self.proxies,
            )
            data = r.content or b""
            dec = self._decrypt_image_if_needed(data)

            ctype = "image/jpeg"
            if dec.startswith(b"\x89PNG"):
                ctype = "image/png"
            elif dec.startswith(b"GIF8"):
                ctype = "image/gif"
            return [200, ctype, dec]
        except Exception:
            return [404, "text/plain", b""]

    def _proxy_img(self, real_url: str) -> str:
        if not real_url:
            return ""
        if not real_url.startswith("http"):
            real_url = self._abs(real_url)
        return f"{self.getProxyUrl()}&type=img&url={self._e64(real_url)}"

    def _decrypt_image_if_needed(self, data: bytes) -> bytes:
        if not data or len(data) < 16:
            return data
        if data.startswith(b"\xff\xd8") or data.startswith(b"\x89PNG") or data.startswith(b"GIF8"):
            return data
        if len(data) % 16 != 0:
            return data

        try:
            dec = unpad(AES.new(self.IMG_AES_KEY, AES.MODE_CBC, self.IMG_AES_IV).decrypt(data), 16)
            if dec.startswith(b"\xff\xd8") or dec.startswith(b"\x89PNG") or dec.startswith(b"GIF8"):
                return dec
        except Exception:
            pass

        try:
            dec = unpad(AES.new(self.IMG_AES_IV, AES.MODE_CBC, self.IMG_AES_KEY).decrypt(data), 16)
            if dec.startswith(b"\xff\xd8") or dec.startswith(b"\x89PNG") or dec.startswith(b"GIF8"):
                return dec
        except Exception:
            pass

        return data

    def _get(self, url: str) -> str:
        r = self.sess.get(url, timeout=8, proxies=self.proxies)
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text

    def _get_json(self, url: str):
        r = self.sess.get(url, timeout=8, proxies=self.proxies)
        r.encoding = r.apparent_encoding or "utf-8"
        try:
            return r.json()
        except Exception:
            try:
                return json.loads(r.text)
            except Exception:
                return {}

    def _soup(self, html_text: str):
        return BeautifulSoup(html_text or "", "lxml")

    def _abs(self, href: str) -> str:
        return urljoin(self.host + "/", (href or "").strip())

    def _e64(self, text: str) -> str:
        return base64.b64encode(str(text).encode("utf-8")).decode("utf-8")

    def _d64(self, text: str) -> str:
        try:
            return base64.b64decode(str(text).encode("utf-8")).decode("utf-8")
        except Exception:
            return ""

    def _pick_site_logo(self, soup: BeautifulSoup) -> str:
        og = soup.select_one("meta[property='og:image']")
        if og and og.get("content"):
            return self._abs(og.get("content").strip())
        return ""

    def _pick_cover(self, soup: BeautifulSoup) -> str:
        img = soup.select_one(".post-content img")
        if img:
            src = (img.get("data-src") or img.get("src") or "").strip()
            if src:
                return self._abs(src)
        return ""

    def _extract_real_from_dplayer(self, dp) -> str:
        cfg_raw = dp.get("data-config") or ""
        try:
            cfg = json.loads(cfg_raw)
        except Exception:
            return ""

        vurl = (((cfg or {}).get("video") or {}).get("url") or "").strip()
        vurl = html.unescape(vurl)
        if not vurl:
            return ""

        vlow = vurl.lower()
        if vlow.endswith(".m3u8") or vlow.endswith(".mp4"):
            return vurl

        api = (cfg.get("data-api") or "").strip()
        if not api:
            return ""

        api_url = self._abs(api)
        j = self._get_json(api_url)
        if isinstance(j, dict) and str(j.get("code")) in ("1", "200"):
            return (j.get("data") or "").strip()
        return ""

    def _extract_real_video_from_detail(self, detail_url: str) -> str:
        html_txt = self._get(detail_url)
        if not html_txt:
            return ""
        soup = self._soup(html_txt)
        for dp in soup.select(".dplayer[data-config]"):
            real = self._extract_real_from_dplayer(dp)
            if real and self.isVideoFormat(real):
                return real
        return ""

    def _parse_cards(self, soup: BeautifulSoup):
        videos = []
        seen = set()
        default_pic = self._pick_site_logo(soup)

        for a in soup.select("a.archive-link-data[href*='/archives/']"):
            href = self._abs(a.get("href"))
            if not href or href in seen:
                continue

            title_tag = a.select_one("h2.post-card-title")
            title = title_tag.get_text(" ", strip=True) if title_tag else ""
            title = re.sub(r"\s+", " ", title).strip()
            if not title:
                continue

            pic = ""
            for sc in a.select("script"):
                txt = sc.get_text("", strip=True)
                m = re.search(r"loadBannerDirect\(\s*'([^']+)'", txt)
                if m:
                    pic = m.group(1).strip()
                    break
            if not pic:
                pic = default_pic

            videos.append(
                {
                    "vod_id": href,
                    "vod_name": title,
                    "vod_pic": self._proxy_img(pic) if pic else "",
                    "style": {"type": "rect", "ratio": 1.33},
                }
            )
            seen.add(href)

        return videos
