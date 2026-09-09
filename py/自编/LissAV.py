import base64
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from urllib.parse import quote, unquote, urljoin, urlparse

import requests

sys.path.append("..")
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    NAV = ("https://x99dh.cc","https://x99dh.one","https://x97.icu","https://x97.one")
    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    )

    PREFIX_LISS = "/asian/zh-CN"
    PREFIX_18 = "/domestic/zh-CN"

    CATES_LISS = [
        ("最近更新-日本", "/videos/recent"),
        ("新作上市-日本", "/videos/new-releases"),
        ("今日热门-日本", "/videos/hot/today"),
        ("本周热门-日本", "/videos/hot/week"),
        ("本月热门-日本", "/videos/hot/month"),
        ("中文字幕-日本", "/videos/tag/中文字幕"),
        ("无码流出-日本", "/videos/tag/无码流出"),
    ]

    CATES_18 = [
        ("新作上市", "/videos/new-releases"),
        ("最近更新", "/videos/recent"),
        ("中文字幕", "/videos/tag/中文字幕"),
        ("今日热门", "/videos/hot/today"),
        ("本周热门", "/videos/hot/week"),
        ("本月热门", "/videos/hot/month"),
        ("探花", "/videos/genre/探花"),
        ("自拍流出", "/videos/genre/自拍流出"),
        ("国产AV", "/videos/genre/国产AV"),
        ("日本", "/videos/genre/日本"),
        ("麻豆传媒", "/videos/genre/麻豆传媒"),
        ("OnlyFan", "/videos/genre/OnlyFan"),
        ("糖心Vlog", "/videos/genre/糖心Vlog"),
        ("蜜桃影像传媒", "/videos/genre/蜜桃影像传媒"),
        ("香蕉视频传媒", "/videos/genre/香蕉视频传媒"),
        ("星空无限传媒", "/videos/genre/星空无限传媒"),
        ("杏吧传媒", "/videos/genre/杏吧传媒"),
        ("天美传媒", "/videos/genre/天美传媒"),
        ("爱豆传媒", "/videos/genre/爱豆传媒"),
        ("精东影业", "/videos/genre/精东影业"),
        ("皇家华人", "/videos/genre/皇家华人"),
        ("果冻传媒", "/videos/genre/果冻传媒"),
        ("萝莉社", "/videos/genre/萝莉社"),
        ("起点传媒", "/videos/genre/起点传媒"),
        ("大象传媒", "/videos/genre/大象传媒"),
        ("91制片厂", "/videos/genre/91制片厂"),
    ]

    RX = {
        "pool": re.compile(r"const\s+encodedData\s*=\s*'([^']+)"),
        "card_a": re.compile(
            r'<div class="streamit-video-card__media position-relative">([\s\S]{0,2500}?)<button[^>]+streamit-video-card__watch-later',
            re.I,
        ),
        "card_b": re.compile(
            r'<div class="streamit-video-card rounded-3"[\s\S]{0,2500}?<div class="streamit-video-card__info',
            re.I,
        ),
        "pager": re.compile(
            r'<ul[^>]*class="[^"]*pagination[^"]*"[^>]*aria-label="分页"[\s\S]*?</ul>',
            re.I,
        ),
        "title": re.compile(
            r"<h1[^>]*>([\s\S]*?)</h1>|<meta[^>]+property=\"og:title\"[^>]+content=\"([^\"]+)\"",
            re.I,
        ),
        "api": re.compile(
            r"(?:var\s+streamApi\s*=|data-stream-api=)\s*[\"']([^\"']+)",
            re.I,
        ),
        "uid": re.compile(
            r"(?:var\s+videoUid\s*=|data-video-uid=|data-streamit-page-video-uid=)\s*[\"']([^\"']+)",
            re.I,
        ),
        "poster": re.compile(
            r"(?:data-poster|poster\s*:)\s*[=:]?\s*[\"']([^\"']+)",
            re.I,
        ),
        "iframe": re.compile(r"<iframe[^>]+src=\"([^\"]+)\"", re.I),
        "date": re.compile(r"<dt>\s*发行日期\s*</dt>\s*<dd[^>]*>\s*([^<\s]+)", re.I),
    }

    def getName(self):
        return "LissAV"

    def manualVideoCheck(self):
        return False

    def init(self, extend=""):
        try:
            cfg = json.loads(extend) if isinstance(extend, str) and extend else (extend or {})
        except Exception:
            cfg = {}

        self.plp = cfg.get('plp', '')
        self.proxy = cfg.get("proxy") or {}
        self.prefix_liss = (cfg.get("prefix_liss") or self.PREFIX_LISS).rstrip("/")
        self.prefix_18 = (cfg.get("prefix_18") or self.PREFIX_18).rstrip("/")

        self.s = requests.Session()
        adp = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=50, max_retries=0)
        self.s.mount("http://", adp)
        self.s.mount("https://", adp)

        self._fixed_host = (cfg.get("host") or "").rstrip("/")
        # 惰性探测：代理未启动时 _best_host() 会失败，这里不强求成功
        self.host = ''
        self.base = ''
        self.headers = {
            "User-Agent": self.UA,
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "",
            "Origin": "",
        }
        self._gethost()

    def _gethost(self):
        # 惰性重探测：代理未启动时 _best_host() 失败，host 为空；
        # 刷新时只要 host 还是空，就重试一次。
        if not self.host:
            self.host = (self._fixed_host or self._best_host() or '').rstrip('/')
            if self.host:
                self.base = self.host
                self.headers['Referer'] = self.host + '/'
                self.headers['Origin'] = self.host
        return self.host

    def isVideoFormat(self, u):
        u = u or ""
        return bool(
            re.search(r"\.(m3u8|mp4)(\?|$)", u, re.I)
            or re.search(r"/hls/.*/index\.jpg(?:\?|$)", u, re.I)
        )

    def _abs(self, u, base=""):
        u = (u or "").strip()
        if u.startswith("http"):
            return u
        if u.startswith("//"):
            return "https:" + u
        return urljoin((base or self._gethost()).rstrip("/") + "/", u)

    def _root(self, u):
        p = urlparse(u or "")
        return f"{p.scheme}://{p.netloc}" if p.netloc else ""

    def _b64(self, s):
        return quote(base64.b64encode(str(s).encode()).decode(), safe="")

    def _unb64(self, s):
        try:
            return base64.b64decode(unquote(str(s))).decode("utf-8", "ignore")
        except Exception:
            return ""

    def _get(self, u, h=None, t=10, stream=False):
        return self.s.get(
            u,
            headers=h or self.headers,
            timeout=t,
            stream=stream,
            allow_redirects=True,
            proxies=self.proxy,
        )

    def _text(self, u, h=None, t=10):
        try:
            r = self._get(u, h, t)
            if r.status_code != 200:
                return ""
            if (not r.encoding) or r.encoding.lower() == "iso-8859-1":
                r.encoding = "utf-8"
            return r.text
        except Exception:
            return ""

    def _json(self, u, h=None, t=10):
        try:
            r = self._get(u, h, t)
            return r.json() if r.status_code == 200 else {}
        except Exception:
            return {}

    def _norm(self, u):
        u = (u or "").strip().rstrip("/")
        if not u:
            return ""
        if not u.startswith("http"):
            u = "https://" + u.lstrip("/")
        return self._root(u).rstrip("/")

    def _best_host(self):
        def pool_from(nav):
            try:
                html = requests.get(
                    nav,
                    headers={"User-Agent": self.UA},
                    proxies=self.proxy,
                    timeout=4,
                ).text
                m = self.RX["pool"].search(html)
                data = json.loads(unquote(base64.b64decode(m.group(1)).decode())) if m else []
                return [
                    {"host": self._norm(x.get("url")), "test": x.get("testUrl", "")}
                    for i in data
                    if i.get("name") == "LissAV"
                    for x in (i.get("urls", []) or [])
                    if self._norm(x.get("url")) and x.get("testUrl")
                ]
            except Exception:
                return []

        pool = []
        with ThreadPoolExecutor(max_workers=min(2, len(self.NAV))) as ex:
            for f in as_completed(ex.submit(pool_from, nav) for nav in self.NAV):
                pool = f.result()
                if pool:
                    break
        if not pool:
            return ""

        pool = list({x["host"]: x for x in pool}.values())

        def probe(x):
            t0 = time.time()
            try:
                r = requests.get(
                    x["test"],
                    headers={"User-Agent": self.UA},
                    proxies=self.proxy,
                    timeout=2,
                )
                ok = r.status_code == 200 and r.text.strip().lower() == "ok"
                return (x["host"], time.time() - t0) if ok else (x["host"], 9e9)
            except Exception:
                return x["host"], 9e9

        best = ("", 9e9)
        with ThreadPoolExecutor(max_workers=min(12, len(pool))) as ex:
            for f in as_completed(ex.submit(probe, x) for x in pool):
                host, dt = f.result()
                if dt < best[1]:
                    best = (host, dt)
                if dt <= 1.2:
                    return host
        return best[0]

    def _page(self, tid, pg):
        p = urlparse(tid).path if str(tid).startswith("http") else str(tid or "")
        if not p.startswith("/"):
            p = "/" + p
        p = re.sub(r"/page/\d+/?$", "", p.split("?", 1)[0]).rstrip("/")
        pg = int(pg or 1)
        return self._abs(p + (f"/page/{pg}" if pg > 1 else ""))

    def _cards(self, html):
        out, seen = [], set()

        def add(block):
            a = re.search(
                r'<a[^>]+streamit-video-card__media-link[^>]+href="([^"]+)"',
                block,
                re.I,
            )
            i = re.search(r'<img[^>]+src="([^"]+)"[^>]*alt="([^"]*)"', block, re.I)
            if not (a and i):
                return
            vid = self._abs(a.group(1))
            if vid in seen:
                return
            t = re.search(r'<p class="mb-0">\s*([^<]+)', block, re.I)
            e = re.search(r'<div class="streamit-video-card__edition[^>]*>\s*([^<]*)', block, re.I)
            rem = " ".join(
                x
                for x in (
                    (t.group(1).strip() if t else ""),
                    (unescape(e.group(1)).strip() if e else ""),
                )
                if x
            )
            seen.add(vid)
            out.append(
                {
                    "vod_id": vid,
                    "vod_name": unescape(i.group(2)).strip(),
                    "vod_pic": self._abs(i.group(1)),
                    "vod_remarks": rem,
                    "style": {"type": "rect", "ratio": 1.33},
                }
            )

        for b in self.RX["card_a"].findall(html or ""):
            add(b)
        for b in self.RX["card_b"].findall(html or ""):
            add(b)
        return out

    def _pc(self, html):
        m = self.RX["pager"].search(html or "")
        src = m.group(0) if m else (html or "")
        a = [int(x) for x in re.findall(r"/page/(\d+)", src)]
        return max(a) if a else 1

    def _cr(self, n, h):
        return "[a=cr:%s/]%s[/a]" % (json.dumps({"id": h, "name": n}, ensure_ascii=False), n)

    def _links(self, html, name, key):
        m = re.search(
            r"<dt>\s*%s\s*</dt>[\s\S]*?<dd[^>]*>([\s\S]*?)</dd>" % re.escape(name),
            html or "",
            re.I,
        )
        if not m:
            return ""
        return " ".join(
            self._cr(unescape(t).strip(), self._abs(h.strip()))
            for h, t in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', m.group(1), re.I)
            if t.strip() and h.strip() and (key in h)
        )

    def _stream(self, html, ref):
        a = self.RX["api"].search(html or "")
        u = self.RX["uid"].search(html or "")
        if not (a and u):
            return {}
        api = a.group(1).strip()
        uid = u.group(1).strip()
        url = self._abs(api) + ("&" if "?" in api else "?") + "video_uid=" + quote(uid)
        return self._json(
            url,
            {"User-Agent": self.UA, "Referer": ref, "X-Requested-With": "XMLHttpRequest"},
            15,
        )

    def _q(self, u):
        u = (u or "").lower()
        m = re.search(r"/(\d{3,4})x(\d{3,4}|\d{3,4}p)(?:/|\b)", u) or re.search(
            r"/(2160|1440|1080|720|480|360|240)p(?:/|\b)", u
        )
        if not m:
            return 0
        if len(m.groups()) > 1:
            return int(m.group(1)) * int(re.sub(r"\D", "", m.group(2)))
        return int(m.group(1))

    def _best_m3u8(self, u, ref):
        txt = self._text(u, {"User-Agent": self.UA, "Referer": ref}, 15)
        if "#EXT-X-STREAM-INF" not in (txt or ""):
            return u, self._q(u)

        best = (u, 0)
        ls = [x.strip() for x in txt.splitlines() if x.strip()]
        for i, x in enumerate(ls[:-1]):
            if x.startswith("#EXT-X-STREAM-INF") and (not ls[i + 1].startswith("#")):
                v = ls[i + 1] if ls[i + 1].startswith("http") else urljoin(u, ls[i + 1])
                m = re.search(r"RESOLUTION=(\d+)x(\d+)", x)
                q = int(m.group(1)) * int(m.group(2)) if m else self._q(v)
                if q > best[1]:
                    best = (v, q)
        return best

    def _play(self, data, ref):
        best = ("", -1)
        for x in (data or {}).get("playlist") or (data or {}).get("sources") or []:
            u = (x.get("url") or "").strip()
            if not u.startswith("http"):
                continue
            if not (self.isVideoFormat(u) or x.get("urlType") == "m3u8"):
                continue
            v = (
                self._best_m3u8(u, ref)
                if (x.get("urlType") == "m3u8" or ".m3u8" in u or "/hls/" in u)
                else (u, self._q(u))
            )
            if v[1] > best[1]:
                best = v
        return best[0]

    def _resolve(self, page, html=""):
        html = html or self._text(page)
        if not html:
            return "", "", page

        m = self.RX["poster"].search(html)
        poster = (m.group(1) or "").strip() if m else ""

        data = self._stream(html, page)
        play = self._play(data, page)
        if play:
            return play, (poster or data.get("poster", "")), page

        m = self.RX["iframe"].search(html)
        iframe = self._abs(m.group(1), page) if m else ""
        if not iframe or "herebyad" in iframe:
            return "", poster, page

        html2 = self._text(iframe, t=15)
        data2 = self._stream(html2, iframe)
        return self._play(data2, iframe), (poster or data2.get("poster", "")), iframe

    def _classes(self):
        out, seen = [], set()

        def add(prefix, name, path):
            k = (prefix, path)
            if k in seen:
                return
            seen.add(k)
            out.append({"type_name": name, "type_id": prefix + path})

        for n, p in self.CATES_LISS:
            add(self.prefix_liss, n, p)
        for n, p in self.CATES_18:
            add(self.prefix_18, n, p)
        return out

    def homeContent(self, filter):
        urls = [self._abs(self.prefix_liss), self._abs(self.prefix_18)]

        def fetch(u):
            return self._cards(self._text(u))

        ls = []
        with ThreadPoolExecutor(max_workers=2) as ex:
            for f in as_completed(ex.submit(fetch, u) for u in urls):
                ls.extend(f.result() or [])

        seen = set()
        uniq = []
        for x in ls:
            vid = x.get("vod_id")
            if vid and vid not in seen:
                seen.add(vid)
                uniq.append(x)

        return {"class": self._classes(), "filters": {}, "list": uniq}

    def homeVideoContent(self):
        return {"list": self._cards(self._text(self._abs(self.prefix_liss)))}

    def categoryContent(self, tid, pg, filter, extend):
        html = self._text(self._page(tid, pg))
        pc = self._pc(html)
        ls = self._cards(html)
        return {
            "list": ls,
            "page": int(pg or 1),
            "pagecount": pc,
            "limit": 90,
            "total": pc * 90 if ls else 0,
        }

    def searchContent(self, key, quick, pg="1"):
        html = self._text(self._page(self.prefix_liss + "/videos/search/" + quote(str(key)), pg))
        return {"list": self._cards(html), "page": int(pg or 1), "pagecount": self._pc(html)}

    def detailContent(self, ids):
        page = self._abs(ids[0])
        html = self._text(page)
        m = self.RX["title"].search(html or "")
        title = re.sub(r"<[^>]+>", "", (m.group(1) or m.group(2) or "")).strip() if m else "LissAV"
        if title.lower().startswith("liss") and "|" in title:
            title = title.split("|", 1)[1].strip()

        play, pic, ref = self._resolve(page, html)
        d = self.RX["date"].search(html or "")
        tags = self._links(html, "标签", "/videos/tag/")

        return {
            "list": [
                {
                    "vod_id": page,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_year": (d.group(1).strip() if d else ""),
                    "vod_director": self._links(html, "发行商", "/videos/studio/"),
                    "vod_actor": self._links(html, "女优", "/videos/actor/"),
                    "vod_content": ("标签：" + tags) if tags else "",
                    "vod_play_from": "直链",
                    "vod_play_url": "播放$%s@@%s" % (play, ref or page),
                }
            ]
        }

    def _proxy(self, u, ref="", t="m3u8"):
        p = self.getProxyUrl()
        return u if not p else f"{p}&type={t}&url={self._b64(u)}" + (f"&ref={self._b64(ref)}" if ref else "")

    def _hdr(self, ref=""):
        host = self._gethost()
        h = {"User-Agent": self.UA, "Referer": ref or (host + "/" if host else "")}
        o = self._root(ref)
        if o:
            h["Origin"] = o
        return h

    def _m3u8(self, text, url, ref):
        base = url.rsplit("/", 1)[0]
        host = self._root(url)

        def full(x):
            return x if x.startswith("http") else (host + x if x.startswith("/") else base + "/" + x)

        out = []
        for line in (text or "").splitlines():
            s = line.strip()
            if not s:
                out.append(line)
                continue
            if s.startswith("#EXT-X-KEY"):
                out.append(
                    re.sub(
                        r'URI="([^"]+)"',
                        lambda m: 'URI="%s"' % self._proxy(full(m.group(1)), ref, "key"),
                        line,
                    )
                )
                continue
            if s.startswith("#"):
                out.append(line)
                continue
            u = full(s)
            out.append(self._proxy(u, ref, "m3u8" if ".m3u8" in s.lower() else "ts"))

        return ("\n".join(out)).encode()

    def localProxy(self, param):
        t = (param.get("type") or "").strip()
        u = self._unb64(param.get("url"))
        host = self._gethost()
        ref = self._unb64(param.get("ref")) or (host + "/" if host else "")
        if t == "auto":
            p = urlparse(u).path.lower()
            t = "m3u8" if re.search(r"\.m3u8$|/hls/.*/index\.jpg$", p) else "mp4"

        try:
            r = self._get(
                u,
                {
                    "User-Agent": self.UA,
                    "Accept": "*/*",
                    "Accept-Encoding": "identity",
                    "Referer": ref,
                    "Origin": self._root(ref),
                    "Connection": "keep-alive",
                },
                (30 if t == "mp4" else 25),
                (t in {"ts", "mp4"}),
            )
            if t == "m3u8":
                b = self._m3u8(r.text, r.url, ref)
            elif t in {"ts", "mp4"}:
                b = b"".join(x for x in r.iter_content(262144) if x)
            else:
                b = r.content
            return [
                r.status_code,
                {
                    "m3u8": "application/vnd.apple.mpegurl",
                    "key": "application/octet-stream",
                    "ts": "video/mp2t",
                    "mp4": "video/mp4",
                }.get(t, "application/octet-stream"),
                b,
            ]
        except Exception:
            return [404, "text/plain", b""]

    def playerContent(self, flag, id, vipFlags):
        if isinstance(id, str) and "@@" in id:
            media, ref = (id.split("@@", 1) + [""])[:2]
        else:
            media, ref = id, ""

        media = (media or "").strip() if isinstance(media, str) else ""
        ref = (ref or "").strip()

        if (not (media.startswith("http") and self.isVideoFormat(media))) and ref:
            media, _, ref = self._resolve(ref)

        if not media:
            return {"parse": 0, "url": "", "header": self._hdr(ref)}

        is_m3u8 = bool(re.search(r"\.m3u8(?:\?|$)|/hls/.*/index\.jpg", media or "", re.I))
        return {
            "parse": 0,
            "url": self._proxy(media, ref or self._root(media), "m3u8" if is_m3u8 else "mp4"),
            "header": self._hdr(ref),
        }
