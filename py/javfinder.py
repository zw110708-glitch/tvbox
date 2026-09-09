import json
import re
from urllib.parse import urljoin, quote

import requests
from bs4 import BeautifulSoup

# 兼容：沙箱里可能没有 drpy/base.spider
try:
    from base.spider import Spider as BaseSpider  # type: ignore
except Exception:  # pragma: no cover
    class BaseSpider:  # 最小桩，仅用于沙箱自测
        def init(self, extend=""):
            pass


class Spider(BaseSpider):
    """JavFinder 专用爬虫（按站点 HTML 结构精简版）"""

    def init(self, extend=""):
        # 支持 extend='{"host":"https://javfinder.ai"}'
        host = "https://javfinder.ai"
        if extend:
            try:
                cfg = json.loads(extend) if isinstance(extend, str) else (extend or {})
                if isinstance(cfg, dict) and cfg.get("host"):
                    host = str(cfg["host"]).strip()
            except Exception:
                pass

        self.host = host.rstrip("/")
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{self.host}/home",
        }

    def getName(self):
        return "JavFinder"

    def isVideoFormat(self, url):
        url = (url or "").lower()
        return any(url.endswith(x) for x in (".m3u8", ".mp4", ".flv", ".mkv", ".webm"))

    def manualVideoCheck(self):
        return False

    # ------------------------- 核心页面抓取 -------------------------

    def _get(self, url: str):
        r = requests.get(url, headers=self.headers, timeout=20)
        r.encoding = r.apparent_encoding
        return r

    def _soup(self, html: str):
        return BeautifulSoup(html, "lxml")

    def _abs(self, href: str):
        if not href:
            return ""
        return href if href.startswith("http") else urljoin(self.host, href)

    def _text(self, el):
        return (el.get_text(" ", strip=True) if el else "").strip()

    def _parse_list(self, soup):
        videos = []
        seen = set()

        for art in soup.select("article.thumb-block"):
            a = art.find("a")
            if not a:
                continue

            href = self._abs((a.get("href") or "").strip())
            if not href or href in seen:
                continue

            title = self._text(art.select_one("h4.entry-name")) or (a.get("title") or "").strip()
            if not title:
                continue

            img_tag = art.find("img")
            img = ""
            if img_tag:
                img = (img_tag.get("data-src") or img_tag.get("data-lazy-src") or img_tag.get("src") or "").strip()
                if "via.placeholder.com" in img_tag.get("src", "") and img_tag.get("data-src"):
                    img = img_tag.get("data-src").strip()
            img = self._abs(img)

            remark = self._text(art.select_one("span.duration")) or self._text(art.select_one("span.views"))

            videos.append(
                {
                    "vod_id": href,
                    "vod_name": title,
                    "vod_pic": img,
                    "vod_remarks": remark,
                    "style": {"type": "rect", "ratio": 1.78},
                }
            )
            seen.add(href)

        return videos

    def homeContent(self, filter):
        r = self._get(f"{self.host}/home")
        soup = self._soup(r.text)

        classes = []
        bad = {"Home", "Tag Filter", "JAV Sites", "JAV Cams"}
        for a in soup.select("#menu-main-menu a"):
            name = (a.get_text(strip=True) or "").strip()
            href = (a.get("href") or "").strip()
            if not name or name in bad or href in ("#", "/"):
                continue
            classes.append({"type_name": name, "type_id": self._abs(href)})

        videos = self._parse_list(soup)
        return {"class": classes, "filters": {}, "list": videos}

    def homeVideoContent(self):
        return {"list": self.homeContent(None).get("list", [])}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if pg else 1
        base = tid if tid.startswith("http") else self._abs(tid)
        url = base.rstrip("/") if pg == 1 else f"{base.rstrip('/')}/page-{pg}"

        r = self._get(url)
        soup = self._soup(r.text)
        videos = self._parse_list(soup)

        return {"list": videos, "page": pg, "pagecount": 9999, "limit": 90, "total": 999999}

    def detailContent(self, ids):
        url = ids[0] if ids[0].startswith("http") else self._abs(ids[0])
        r = self._get(url)
        html = r.text
        soup = self._soup(html)

        h1 = soup.find("h1")
        title = self._text(h1) or (soup.title.get_text(strip=True) if soup.title else "").strip()

        poster = ""
        og = soup.select_one('meta[property="og:image"]')
        tw = soup.select_one('meta[name="twitter:image"]')
        if og and og.get("content"):
            poster = og.get("content")
        elif tw and tw.get("content"):
            poster = tw.get("content")
        poster = self._abs((poster or "").strip())

        token = ""
        m = re.search(r"/player#([0-9a-zA-Z=]+)", html)
        if m:
            token = m.group(1)

        play_list = []
        if token:
            api = f"{self.host}/stream/{token}"
            j = requests.get(api, headers={**self.headers, "Accept": "application/json"}, timeout=20).json()
            if not poster and j.get("poster"):
                poster = str(j.get("poster"))
            for item in (j.get("list") or []):
                u = str(item.get("url") or "").strip()
                s = str(item.get("server") or "Server").strip()
                if u:
                    play_list.append(f"{s}${u}")

        vod = {
            "vod_id": url,
            "vod_name": title,
            "vod_pic": poster,
            "vod_content": title,
            "vod_play_from": "JavFinder",
            "vod_play_url": "#".join(play_list) if play_list else "",
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if pg else 1
        base = f"{self.host}/search/movie/{quote(key)}"
        url = base if pg == 1 else f"{base}/page-{pg}"

        r = self._get(url)
        soup = self._soup(r.text)
        videos = self._parse_list(soup)
        return {"list": videos, "page": pg, "pagecount": 9999}

    def playerContent(self, flag, id, vipFlags):
        # JavFinder 的 /stream 返回的是外部 embed 页面，交给壳解析
        return {"parse": 1, "url": id, "header": self.headers}
