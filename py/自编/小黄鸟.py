import json
import re
import sys
from urllib.parse import quote, unquote

import requests
from bs4 import BeautifulSoup

sys.path.append('..')
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass


class Spider(BaseSpider):
    def getName(self):
        return "小黄鸟"

    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}

        self.host = (cfg.get("host") or "https://xiaohuangniao.me").rstrip("/")
        self.proxies = cfg.get("proxies") or {          "http": "http://127.0.0.1:10172",

          "https": "http://127.0.0.1:10172"}
        self.limit = int(cfg.get("page_limit") or 30)

        self.s = requests.Session()
        self.h = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.host + "/",
        }

        self._c = {}
        self._cq = []
        self._cmax = int(cfg.get("api_cache_max") or 128)


    def _txt(self, x, n=120):
        s = "" if x is None else str(x)
        s = re.sub(r"[\x00-\x1f\x7f]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s[:n] if n and len(s) > n else s

    def _hms(self, ms):
        s = int(ms or 0) // 1000
        h = s // 3600
        m = (s % 3600) // 60
        ss = s % 60
        return f"{h:02d}:{m:02d}:{ss:02d}"

    def _enc_kw(self, kw):
        return "kw:" + quote(self._txt(kw, 80), safe="")

    def _dec_kw(self, tid):
        tid = self._txt(tid, 200)
        if tid.startswith("kw:"):
            tid = tid[3:]
        try:
            return unquote(tid)
        except Exception:
            return tid

    def _get(self, url, is_json=False, params=None):
        r = self.s.get(url, headers=self.h, proxies=self.proxies, timeout=20, params=params)
        r.raise_for_status()
        if is_json:
            return r.json()
        r.encoding = r.apparent_encoding
        return r.text

    def _api_tweet(self, **params):
        k = ('tweet',) + tuple(sorted((a, str(b)) for a, b in params.items()))
        if k in self._c:
            return self._c[k]

        obj = self._get(self.host + "/api/tweet", is_json=True, params=params)
        data = (obj.get("data") or {}) if (obj and obj.get("success")) else {}

        self._c[k] = data
        self._cq.append(k)
        if len(self._cq) > self._cmax:
            old = self._cq.pop(0)
            self._c.pop(old, None)

        return data

    def _api_requestdb(self, **params):
        obj = self._get(self.host + "/api/requestdb", is_json=True, params=params)
        return (obj.get('data') or {}) if (obj and obj.get('success')) else {}

    def _pick_media(self, tweet):
        mp4_urls = []
        cover = ""
        dur = 0

        ext = tweet.get("extendedEntities") or {}
        media = (ext.get("media") or [])[:1]
        if media:
            m0 = media[0] or {}
            cover = m0.get("media_url_https") or m0.get("media_url") or ""
            vinfo = m0.get("video_info") or {}
            dur = int(vinfo.get("duration_millis") or 0)
            variants = vinfo.get("variants") or []

            mp4s = [v for v in variants if (v.get("content_type") or "").lower() == "video/mp4" and v.get("url")]
            if mp4s:
                mp4s.sort(key=lambda x: x.get("bitrate") or 0, reverse=True)
                mp4_urls = [x["url"].replace("\\u0026", "&") for x in mp4s]

        return mp4_urls, cover, dur

    def _vod(self, t):
        vid = self._txt(t.get("tweetId") or t.get("id"), 80)
        name = self._txt(t.get("text") or "(无标题)", 120)
        mp4_urls, cover, dur = self._pick_media(t)
        if not mp4_urls:
            return None
        return {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": 'http://127.0.0.1:10079/p/0/127.0.0.1:10172/' + cover,
            "vod_remarks": self._hms(dur),
        }

    def _creator_tweets(self, username, pg):
        username = self._txt(username, 60).lstrip('@')
        if not username:
            return [], 1

        data = self._api_requestdb(type='search-users', query=username, limit=1)
        users = data.get('users') or []
        if not users:
            return [], 1
        author_id = users[0].get('id')
        if not author_id:
            return [], 1

        d = self._api_tweet(authorId=author_id, page=pg, limit=self.limit)
        return (d.get('tweets') or []), int(d.get('totalPages') or 1)


    def _categories(self):
        html = self._get(self.host + "/categories")
        soup = BeautifulSoup(html, "lxml")

        best, score = None, 0
        for g in soup.find_all("div", class_=lambda c: c and "grid" in c and "grid-cols" in c):
            btns = g.find_all("button")
            if not btns:
                continue
            s = sum(1 for b in btns if b.find("p"))
            if s > score:
                best, score = g, s

        out, seen = [], set()
        if best:
            for b in best.find_all("button"):
                p = b.find("p")
                kw = self._txt(p.get_text(strip=True) if p else "", 20)
                if kw and kw not in seen:
                    seen.add(kw)
                    out.append(kw)
        return out


    def homeContent(self, filter):
        cls = [{"type_name": "热门", "type_id": "hot"}]
        for kw in self._categories():
            cls.append({"type_name": kw, "type_id": self._enc_kw(kw)})

        data = self._api_tweet(page=1, limit=20, minViewCount=10000, minDuration=180000)
        lst = []
        for t in data.get("tweets") or []:
            v = self._vod(t)
            if v:
                lst.append(v)

        return {"class": cls[:150], "filters": {}, "list": lst}

    def homeVideoContent(self):
        return {"list": self.homeContent(None).get("list") or []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = max(int(pg or 1), 1)

        if tid == "hot":
            data = self._api_tweet(page=pg, limit=self.limit, minViewCount=10000, minDuration=180000)
            tweets = data.get("tweets") or []
            pagecount = int(data.get("totalPages") or 1)

        elif isinstance(tid, str) and (tid.startswith('cr:') or tid.startswith('/creators/')):
            uname = tid[3:] if tid.startswith('cr:') else tid.split('/creators/',1)[1]
            tweets, pagecount = self._creator_tweets(uname, pg)

        else:
            key = self._dec_kw(tid)
            data = self._api_tweet(page=pg, limit=self.limit, keyword=key)
            tweets = data.get("tweets") or []
            pagecount = int(data.get("totalPages") or 9999)

        lst = []
        for t in tweets:
            v = self._vod(t)
            if v:
                lst.append(v)

        return {"list": lst, "page": pg, "pagecount": pagecount, "limit": self.limit, "total": len(lst) + (pg - 1) * self.limit}

    def detailContent(self, ids):
        vid = self._txt(ids[0] if ids else "", 80)
        if not vid:
            return {"list": []}

        data = self._api_tweet(tweetId=vid)
        tweets = data.get("tweets") or []
        if not tweets:
            return {"list": []}

        t = tweets[0]
        a = t.get("author") or {}
        uname = self._txt(a.get("userName"), 60)
        aname = self._txt(a.get("name") or uname, 60)

        mp4_urls, cover, _ = self._pick_media(t)

        vod = {
            "vod_id": self._txt(t.get("tweetId") or vid, 80),
            "vod_name": self._txt(t.get("text") or "(无标题)", 160),
            "vod_pic": 'http://127.0.0.1:10079/p/0/127.0.0.1:10172/' + cover or self._txt(a.get("profilePicture"), 300),
            "vod_content": self._txt(t.get("text") or "", 500),
        }

        if uname:
            payload = json.dumps({"id": "cr:" + uname, "name": aname}, ensure_ascii=False)
            vod["vod_actor"] = f"[a=cr:{payload}/]{aname}[/a]"

        vod["vod_play_from"] = "直链"
        vod["vod_play_url"] = "播放$" + "http://127.0.0.1:10079/p/0/127.0.0.1:10172/" + mp4_urls[0]

        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        return {
            "parse": 0,
            "url": self._txt(id, 2000).replace("\\u0026", "&"),
            "header": {"User-Agent": self.h["User-Agent"], "Referer": "https://twitter.com/"},
        }

    def searchContent(self, key, quick, pg="1"):
        pg = max(int(pg or 1), 1)
        key = self._txt(key, 200)

        data = self._api_tweet(page=pg, limit=self.limit, keyword=key)
        lst = []
        for t in data.get("tweets") or []:
            v = self._vod(t)
            if v:
                lst.append(v)

        return {"list": lst, "page": pg, "pagecount": int(data.get("totalPages") or 9999)}
