import json
import re
from html import unescape
from urllib.parse import urljoin, urlparse, urlsplit

import requests
from base.spider import Spider


class Spider(Spider):
    name = "Bad.news"
    host = "https://bad.news"
    ua = (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
    )
    headers = {
        "User-Agent": ua,
        "Referer": host + "/",
        "Origin": host,
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    bl = ("热点", "招聘", "20k", "工作制", "双休", "远程", "月薪")

    def __init__(self):
        self.proxies = {}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self._cache = {}

    def getName(self):
        return self.name

    def init(self, extend=""):
        self.proxies = (json.loads(extend) if extend else {}).get("proxies", {          "http": "http://127.0.0.1:10172",
          "https": "http://127.0.0.1:10172"})

    def fetch(self, url, headers=None, params=None):
        try:
            r = self.session.get(
                url,
                headers=headers,
                params=params,
                proxies=self.proxies,
                timeout=10,
                allow_redirects=True,
            )
            if r.status_code == 200:
                r.encoding = "utf-8"
                return r.text
        except Exception:
            pass
        return ""

    def homeContent(self, _filter):
        return {
            "class": [
                {"type_id": "/", "type_name": "首页"},
                {"type_id": "/tag/porn", "type_name": "短视频"},
                {"type_id": "/tag/long-porn", "type_name": "长视频"},
            ]
        }

    def homeVideoContent(self):
        return self.categoryContent("", "1", False, {})

    @staticmethod
    def _s(x: str) -> str:
        return unescape((x or "").strip())

    def _p(self, x):
        x = self._s(x).split()[0]
        if not x:
            return ""
        if x.startswith("http"):
            x = urlsplit(x).path
        x = x.split("?", 1)[0].split("#", 1)[0].strip()
        if x.startswith("/av/play/"):
            x = "/av/" + x[9:]
        if x and not x.startswith("/"):
            x = "/" + x
        return x.rstrip("/") if len(x) > 1 else x

    def _t(self, x):
        x = re.sub(r"\s+", " ", self._s(x))
        if not x:
            return ""
        for k in ("｜", "|", " - ", " – ", " — ", "·", "•"):
            if k in x:
                x = x.split(k, 1)[0].strip()
                break
        x = re.sub(r"\s*(?:\d+[KkMm]?\s*)?(?:views?|观看|次观看|播放)\b.*$", "", x, flags=re.I)
        x = re.sub(r"\s*\b\d{1,2}:\d{2}(?::\d{2})?\b.*$", "", x)
        return re.sub(r"\s*[（(]\s*\d+\s*[）)]\s*$", "", x).strip()

    def parse_list(self, html):
        rx, out, seen = re.search, [], set()

        def tm(b):
            m = rx(r'pic-time"[^>]*>([^<]+)<', b, re.S) or rx(r'ct-time">\s*<span[^>]*>([^<]+)<', b, re.S)
            return m.group(1).strip() if m else ""

        def add(i, n, p, t):
            i = self._p(i)
            if (not i) or i in seen:
                return
            n = self._t(n)
            if (not n) or any(x in n for x in self.bl):
                return
            seen.add(i)
            out.append(
                {
                    "vod_id": i,
                    "vod_name": n,
                    "vod_pic": 'http://127.0.0.1:10079/p/0/127.0.0.1:10172/' + (p.split("?", 1)[0] if p else ""),
                    "vod_remarks": t,
                    "vod_tag": "",
                    "style": {"type": "rect", "ratio": 1.33},
                }
            )

        if "twi hasMedia" in html:
            for b in re.findall(
                r'(<div\s+class="twi\s+hasMedia[^\"]*"[^>]*>.*?)(?=<div\s+class="twi\s+hasMedia|\Z)',
                html,
                re.S,
            ):
                m = rx(
                    r'<a\s+href="([^"]+)"[^>]*class="(?:nm\s+auth\s+jump|[^"]*vid[^"]*)"[^>]*>(.*?)</a>',
                    b,
                    re.S,
                )
                if m:
                    p = rx(r'poster="([^"]+)"', b) or rx(r'data-echo-background="([^"]+)"', b)
                    add(m.group(1), re.sub(r"<[^>]+>", "", m.group(2)), p.group(1) if p else "", tm(b))
            return out

        for b in re.findall(r'<div[^>]*class="[^"]*video-list-content-item[^"]*"[^>]*>.*?</div>', html, re.S):
            m = rx(r'href="([^"]+)"', b)
            if m and m.group(1).startswith("/"):
                t = rx(r'(?:title|alt)="([^"]+)"', b)
                p = rx(r'(?:data-echo-background|poster|src)="([^"]+)"', b)
                add(m.group(1), t.group(1) if t else "", p.group(1) if p else "", tm(b))
        if out:
            return out

        for b in re.findall(r"<table.*?>(.*?)</table>", html, re.S):
            m = rx(r'href="([^"]+)"', b)
            if m and m.group(1).startswith("/"):
                t = rx(r"<h3[^>]*>(.*?)</h3>", b, re.S)
                p = rx(r'poster="([^"]+)"', b)
                add(m.group(1), re.sub(r"<[^>]+>", "", t.group(1)).strip() if t else "", p.group(1) if p else "", tm(b))
        return out

    def categoryContent(self, tid, pg, _filter, _extend):
        pg = int(pg)
        if tid:
            url = f"{self.host}{tid}/page-{pg}"
        else:
            url = self.host if pg == 1 else f"{self.host}/page-{pg}"
        return {"list": self.parse_list(self.fetch(url)), "page": pg, "pagecount": 999}

    def _play(self, html):
        if not html:
            return ""
        for p in (
            r'<video[^>]+data-source="([^"]+)"',
            r'<video[^>]+src="([^"]+)"',
            r'<source[^>]+src="([^"]+)"',
            r'"contentUrl"\s*:\s*"([^"]+)"',
            r'<meta\s+property="og:video"\s+content="([^"]+)"',
        ):
            m = re.search(p, html, re.S)
            if m:
                u = self._s(m.group(1)).split()[0]
                if re.search(r"\.(?:m3u8|mp4)(?:\b|\?)", u, re.I):
                    return u
        m = re.search(r"(https?://[^\s\"']+\.(?:m3u8|mp4)[^\s\"']*)", html, re.I)
        return self._s(m.group(1)).split()[0] if m else ""

    def _resolve_download(self, path: str, html: str) -> str:
        m = re.search(r"/ajax/topic/(\d+)/download", html or "") or re.search(r"/t/(\d+)", path or "")
        if not m:
            return ""
        api = f"{self.host}/ajax/topic/{m.group(1)}/download"
        try:
            r = self.session.get(
                api,
                headers={"User-Agent": self.ua, "Referer": self.host + "/"},
                proxies=self.proxies,
                timeout=10,
                allow_redirects=False,
            )
            loc = r.headers.get("Location")
            if 300 <= r.status_code < 400 and loc:
                return self._s(loc).split()[0]
            ct = r.headers.get("content-type", "")
            if ct.startswith("application/json"):
                j = r.json() if r.text else {}
                for k in ("url", "data", "location"):
                    u = j.get(k)
                    if isinstance(u, str) and u.startswith("http"):
                        return u
        except Exception:
            pass
        return ""

    def _tw_child_m3u8(self, u):
        u = self._s(u).split()[0]
        if (not u) or ("video.twimg.com" not in u) or (".m3u8" not in u) or ("/pl/" not in u):
            return u
        v = self._cache.get(u)
        if v:
            return v
        try:
            txt = self.session.get(
                u,
                headers={"User-Agent": self.ua, "Referer": "https://twitter.com/"},
                proxies=self.proxies,
                timeout=10,
            ).text
        except Exception:
            self._cache[u] = u
            return u
        if "#EXT-X-STREAM-INF" not in txt:
            self._cache[u] = u
            return u

        best_bw, best_uri = -1, ""
        lines = [x.strip() for x in txt.splitlines()]
        for i, line in enumerate(lines):
            if not line.startswith("#EXT-X-STREAM-INF"):
                continue
            m = re.search(r"BANDWIDTH=(\d+)", line)
            bw = int(m.group(1)) if m else 0
            j = i + 1
            while j < len(lines) and (not lines[j] or lines[j].startswith("#")):
                j += 1
            uri = lines[j] if j < len(lines) else ""
            if uri and bw >= best_bw:
                best_bw, best_uri = bw, uri
        v = urljoin(u.split("?", 1)[0], best_uri) if best_uri else u
        self._cache[u] = v
        return v

    def _title(self, html):
        for p in (
            r'<p\s+class="[^"]*av-video-func-title[^"]*"[^>]*>(.*?)</p>',
            r'<h3[^>]*>.*?<a\s+[^>]*class="[^"]*nm\s+auth\s+jump[^"]*"[^>]*>(.*?)</a>',
            r"<h3[^>]*>(.*?)</h3>",
        ):
            m = re.search(p, html, re.S)
            if m:
                t = re.sub(r"<[^>]+>", "", m.group(1))
                t = re.sub(r"\s+", " ", self._s(t))
                t = re.sub(r"\s*\([^)]*\)\s*$", "", t).strip()
                if t:
                    return t
        m = re.search(r'<meta\s+property="og:title"\s+content="([^"]*)"', html, re.S)
        if m and m.group(1).strip():
            return self._s(m.group(1))
        m = re.search(r"<title>(.*?)</title>", html, re.S)
        return re.sub(r"\s+", " ", self._s(re.sub(r"<[^>]+>", "", m.group(1)))) if m else self.name

    def detailContent(self, ids):
        path = (ids[0].strip() if ids and ids[0] else "")
        url = path if path.startswith("http") else self.host + (path if path.startswith("/") else "/" + path)
        html = self.fetch(url)
        rx = re.search

        def mk(href, name):
            href = (href or "").strip().split()[0]
            if href and not href.startswith("/"):
                href = "/" + href
            return (
                "[a=cr:" + json.dumps({"id": href, "name": name}, ensure_ascii=False) + "/]" + name + "[/a]"
                if href and name
                else ""
            )

        actor = ""
        m = rx(r"演员\s*:\s*(.*?)</p>", html, re.S)
        if m:
            S, a = set(), []
            for href, name in re.findall(r'<a\s+href="([^"]+)"[^>]*>\s*([^<]+?)\s*</a>', m.group(1), re.S):
                name = re.sub(r"\s+", " ", name).strip()
                if name and (href, name) not in S:
                    S.add((href, name))
                    a.append(mk(href, name))
            actor = " ".join(x for x in a if x)

        director = ""
        m = rx(
            r'<a\s+href="(/search/t-all/q-user:[^"\s]+)"[^>]*>.*?<span\s+class="time"[^>]*>\s*([^<]+?)\s*</span>\s*</a>',
            html,
            re.S,
        )
        if m:
            director = mk(m.group(1), m.group(2).strip())

        tags = []
        m = rx(r"标签\s*:\s*(.*?)</p>", html, re.S)
        if m:
            S = set()
            for href, name in re.findall(r'<a\s+href="([^"]+)"[^>]*>\s*([^<]+?)\s*</a>', m.group(1), re.S):
                name = re.sub(r"\s+", " ", name).strip().lstrip("#").strip()
                if name and (href, name) not in S:
                    S.add((href, name))
                    tags.append(mk(href, name))

        desc = ""
        m = rx(r"影片描述\s*:\s*(.*?)</p>", html, re.S)
        if m:
            desc = re.sub(r"<[^>]+>", "", m.group(1)).strip()

        cover = ""
        m = rx(r'<meta\s+property="og:image"\s+content="([^"]+)"', html, re.S) or rx(r'<video[^>]+poster="([^"]+)"', html, re.S)
        if m:
            cover = m.group(1).split("?", 1)[0]

        return {
            "list": [
                {
                    "vod_id": path,
                    "vod_name": self._title(html),
                    "vod_actor": actor,
                    "vod_director": director,
                    "vod_content": ("%s\n%s" % (" ".join(tags), desc)).strip(),
                    "vod_play_from": "HTML",
                    "vod_play_url": ("播放$" + path) if path else "播放$null",
                    "vod_pic": 'http://127.0.0.1:10079/p/0/127.0.0.1:10172/' + cover,
                }
            ]
        }

    def playerContent(self, flag, id, vipFlags):
        raw = (id or "").split(";", 1)[0].strip()
        if not raw:
            return {"parse": 1, "url": self.host, "header": {"User-Agent": self.ua}}

        u = raw
        if raw.startswith("/"):
            html = self.fetch(self.host + raw)
            u = self._play(html) or self._resolve_download(raw, html)

        if u.startswith("http") and u.endswith(".m3u8") and "video.twimg.com" in u and "/pl/" in u:
            u = self._tw_child_m3u8(u)

        if not u:
            return {"parse": 1, "url": self.host + raw if raw.startswith("/") else raw, "header": {"User-Agent": self.ua}}

        n = (urlparse(u).netloc or "").lower()
        ref = "https://twitter.com/" if ("twimg.com" in n or "twitter.com" in n) else self.host + "/"
        return {"parse": 0, "url": u, "header": {"User-Agent": self.ua, "Referer": ref}}

    def searchContent(self, key, quick, pg="1"):
        return {"list": self.parse_list(self.fetch(f"{self.host}/search/q-{key}"))}

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass
