import json
import re
import urllib.parse

import requests
from bs4 import BeautifulSoup

from base.spider import Spider

BASE_URL = "https://www.fullhd.xxx/zh/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}
TIMEOUT = 10

CATEGORIES = [
    ("latest-updates", "最新视频🌠"),
    ("top-rated", "最佳视频🌠"),
    ("most-popular", "热门影片🌠"),
    ("networks/brazzers-com", "Brazzers🌠"),
    ("networks/tushy-com", "Tushy🌠"),
    ("networks/naughtyamerica-com", "Naughtyamerica🌠"),
    ("sites/sexmex", "Sexmex🌠"),
    ("sites/passion-hd", "Passion-HD🌠"),
    ("categories/animation", "Animation🌠"),
    ("categories/18-years-old", "Teen🌠"),
    ("categories/pawg", "Pawg🌠"),
    ("categories/thong", "Thong🌠"),
    ("categories/stockings", "Stockings🌠"),
    ("categories/jav-uncensored", "JAV🌠"),
    ("categories/pantyhose", "Pantyhose🌠"),
]


class Spider(Spider):
    def getName(self):
        return "首页"

    def init(self, extend):
        cfg = (
            json.loads(extend)
            if isinstance(extend, str) and extend.strip()
            else (extend if isinstance(extend, dict) else {})
        )
        self.plp = cfg.get('plp', '')
        self.proxy = cfg.get("proxy", {})

        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        # 设置全局代理，所有通过此会话的请求都会自动使用代理
        self.session.proxies = self.proxy

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _url(self, value):
        value = (value or "").strip()
        return urllib.parse.urljoin(BASE_URL, value.lstrip("/")) if value and not value.startswith("http") else value

    def _cid(self, value):
        path = urllib.parse.urlparse(value or "").path or value or ""
        path = path.split("?", 1)[0].split("#", 1)[0].strip("/")
        return path[3:] if path.startswith("zh/") else path

    def _get(self, url):
        # 移除显式 proxies 参数，使用会话默认代理
        r = self.session.get(self._url(url), timeout=TIMEOUT)
        r.encoding = "utf-8"
        return r.text

    def _videos(self, html):
        soup = BeautifulSoup(html, "lxml")
        data = []
        for item in soup.select("div.list-videos div.item"):
            a = item.select_one("a[title][href]")
            img = item.select_one("img[data-src], img[src]")
            if not a:
                continue
            data.append(
                {
                    "vod_id": a["href"],
                    "vod_name": a.get("title", "").strip(),
                    "vod_pic": self.plp + self._url(img.get("data-src") or img.get("src")) if img else "",
                    "vod_remarks": item.select_one("span.duration").get_text(strip=True)
                    if item.select_one("span.duration")
                    else "",
                }
            )
        return data

    def _page_url(self, cid, page):
        cid = self._cid(cid).strip("/")
        return urllib.parse.urljoin(BASE_URL, f"{cid}/{page}/" if int(page) > 1 else f"{cid}/")

    def _page_result(self, url, page):
        return {"list": self._videos(self._get(url)), "page": str(page), "pagecount": 9999, "limit": 90, "total": 999999}

    def homeContent(self, filter):
        return {"class": [{"type_id": i, "type_name": n} for i, n in CATEGORIES]}

    def homeVideoContent(self):
        return {"list": self._videos(self._get(BASE_URL))}

    def categoryContent(self, cid, pg, filter, ext):
        page = int(pg or 1)
        return self._page_result(self._page_url(cid, page), page)

    def detailContent(self, ids):
        did = self._url(ids[0])
        soup = BeautifulSoup(self._get(did), "lxml")
        title = soup.select_one("h1")
        info = {"vod_actor": [], "vod_director": [], "tags": []}
        rules = (("vod_actor", "a.btn_model"), ("vod_director", "a.btn_sponsor, a.btn_sponsor_group"), ("tags", "a.btn_tag"))
        for key, selector in rules:
            for a in soup.select(selector):
                name, cid = a.get_text(strip=True), self._cid(a.get("href"))
                if name and cid:
                    info[key].append(f"[a=cr:{json.dumps({'id': cid, 'name': name}, ensure_ascii=False)}/]{name}[/a]")
        tags = " ".join(info["tags"])
        content = ("标签: " + tags + " " if tags else "") + "👉" + (title.get_text(strip=True) if title else "")
        return {
            "list": [
                {
                    "vod_id": did,
                    "vod_actor": " ".join(info["vod_actor"]),
                    "vod_director": " ".join(info["vod_director"]),
                    "vod_content": content.strip(),
                    "vod_play_from": "老僧酿酒",
                    "vod_play_url": did,
                }
            ]
        }

    def playerContent(self, flag, id, vipFlags):
        page_url = self._url(id)
        soup = BeautifulSoup(self._get(page_url), "lxml")

        sources = [
            (int(re.search(r"\d+", s.get("label", "0")).group()), s.get("src"))
            for s in soup.select("video source[src]")
            if re.search(r"\d+", s.get("label", "0"))
        ]
        media_url = self._url(max(sources)[1])
        # 移除显式 proxies={}，使用会话默认代理
        r = self.session.head(media_url, timeout=TIMEOUT, allow_redirects=True)
        final_url = r.url or media_url

        return {"parse": 0, "playUrl": "", "url": f'{self.plp}{final_url}', "header": HEADERS}

    def searchContentPage(self, key, quick, page):
        page = int(page or 1)
        q = urllib.parse.quote((key or "").strip())
        return self._page_result(urllib.parse.urljoin(BASE_URL, f"search/{q}/{page}/" if page > 1 else f"search/{q}/"), page)

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, 1)

    def localProxy(self, params):
        t = params.get("type")
        return self.proxyM3u8(params) if t == "m3u8" else self.proxyMedia(params) if t == "media" else self.proxyTs(params) if t == "ts" else None
