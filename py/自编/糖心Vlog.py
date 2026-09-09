# -*- coding: utf-8 -*-
import re
import json
import time
import requests
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    BaseSpider = object


class Spider(BaseSpider):
    """糖心Vlog 爬虫实现"""

    def getName(self):
        return "糖心vlog"

    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, str) and extend.strip().startswith("{"):
            try:
                cfg = json.loads(extend)
            except Exception:
                pass
        elif isinstance(extend, dict):
            cfg = extend

        self.host = "https://tangxinvlog.app"
        self.lang = "/zh-tw"
        self.cdn = "https://t.5gcdn.xyz/videos"
        self.ua = (
            "Mozilla/5.0 (Linux; Android 10; K) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/139.0 Mobile Safari/537.36"
        )

        self.plp = cfg.get('plp', '')
        self.proxy = cfg.get("proxy") or {}

        self.headers = {
            "User-Agent": self.ua,
            "Referer": self.host + self.lang + "/",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
        }
        self.img_headers = {
            "User-Agent": self.ua,
            "Referer": self.host + self.lang + "/",
            "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
        }

        self.session = requests.Session()
        self.img_session = requests.Session()

        self.page_cache = {}
        self.img_cache = {}
        self.bad_img = set()
        self._proxy_prefix = None

        # 搜索池缓存
        self._search_pool = []
        self._search_pool_ts = 0

    def destroy(self):
        pass

    def homeContent(self, filter):
        return {
            "class": [
                            {"type_id": "featured", "type_name": "精选推荐"},
                {"type_id": "tag/黑料正能量", "type_name": "黑料正能量"},
                {"type_id": "tag", "type_name": "标签"},
                {"type_id": "actor", "type_name": "演员"},
            ],
            "list": [],
        }

    def homeVideoContent(self):
        return self.categoryContent("latest", 1, None, {})

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        tid = unquote(str(tid or "tag")).strip()

        if tid == "latest":
            url = self.host + self.lang + "/"
            data = self._video_list(url)
            return {
                "page": pg,
                "pagecount": 1,
                "limit": len(data),
                "total": len(data),
                "list": data,
            }

        if tid == "tag":
            return self._people_list(self.host + self.lang + "/tag/", "tag", pg)
        if tid == "actor":
            return self._people_list(self.host + self.lang + "/a/", "actor", pg)

        if tid == "featured":
            url = self.host + self.lang + "/featured/" + ("" if pg <= 1 else str(pg))
            data = self._video_list(url)
            return {
                "page": pg,
                "pagecount": 999,
                "limit": len(data),
                "total": 999999,
                "list": data,
            }

        if tid.startswith("tag/") or tid.startswith("actor/"):
            prefix, slug = tid.split("/", 1)
            path = "tag" if prefix == "tag" else "a"
            url = (
                self.host
                + self.lang
                + "/"
                + path
                + "/"
                + quote(slug, safe="")
                + ("/" if pg <= 1 else "/" + str(pg))
            )
            data = self._video_list(url)
            return {
                "page": pg,
                "pagecount": 999,
                "limit": len(data),
                "total": 999999,
                "list": data,
            }

        return {"page": pg, "pagecount": pg, "limit": 0, "total": 0, "list": []}

    def _people_list(self, url, ptype, pg):
        h = self._get(url)
        arr = []
        pattern = r'<a href="[^"]+/([^/"]+)/?[^"]*"[^>]*>\s*<span class="name"[^>]*>(.*?)</span>\s*<span class="num"[^>]*>(.*?)</span>'
        for slug, name, num in re.findall(pattern, h, re.S):
            slug = unquote(slug).strip("/")
            name = self._clean(name)
            num = self._clean(num)
            if slug and name:
                arr.append({
                    "vod_id": ptype + "/" + slug,
                    "vod_name": name,
                    "vod_pic": "",
                    "vod_remarks": num,
                    "vod_tag": "folder",
                })
        return {
            "page": pg,
            "pagecount": 1,
            "limit": len(arr),
            "total": len(arr),
            "list": self._dedup(arr),
        }

    def _video_list(self, url):
        """解析视频卡片，返回所有卡片（无数量限制）"""
        h = self._get(url)
        arr = []
        for card in re.findall(r'<article class="card".*?</article>', h, re.S):
            href = re.search(r'href="([^"]*/v/\d+/[^"]*)"', card, re.I)
            if not href:
                continue
            vid = re.search(r"/v/(\d+)/", href.group(1)).group(1)

            name_match = (
                re.search(r'aria-label="([^"]+)"', card, re.I)
                or re.search(r'<img[^>]+alt="([^"]+)"', card, re.I)
                or re.search(r'<h3[^>]*>.*?<a[^>]*>(.*?)</a>', card, re.S)
            )
            name = self._clean(name_match.group(1)) if name_match else vid

            pic_match = re.search(r'<img[^>]+src="([^"]+)"', card, re.I)
            pic = pic_match.group(1) if pic_match else self.cdn + "/" + vid + "/cover.jpg"

            dur_match = re.search(r'<span class="duration"[^>]*>(.*?)</span>', card, re.I)
            mark = self._clean(dur_match.group(1)) if dur_match else ""

            arr.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": self._pic(pic, vid),
                "vod_remarks": mark,
            })
        return self._dedup(arr)

    def detailContent(self, ids):
        vid_match = re.search(r"(\d+)", str(ids[0]).strip())
        if not vid_match:
            return {"list": []}
        vid = vid_match.group(1)

        h = self._get(self.host + self.lang + "/v/" + vid + "/")

        title_match = re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S)
        name = self._clean(title_match.group(1)) if title_match else vid

        pic_match = re.search(r'<video[^>]+poster="([^"]+)"', h, re.I)
        pic = pic_match.group(1) if pic_match else self.cdn + "/" + vid + "/cover.jpg"

        dur_match = re.search(r'data-pagefind-meta="duration"[^>]*>(.*?)</span>', h, re.I)
        duration = self._clean(dur_match.group(1)) if dur_match else ""

        date_match = re.search(r'<time[^>]+datetime="([^"]+)"', h, re.I)
        date = self._clean(date_match.group(1)) if date_match else ""

        actor_link = ""
        actor_raw = ""
        am = re.search(r'<a class="nickname"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', h, re.S)
        if am:
            raw_href = am.group(1).strip()
            actor_raw = self._clean(am.group(2))
            slug_match = re.search(r"/a/([^/]+)/?$", raw_href)
            if slug_match:
                slug = slug_match.group(1)
                actor_link = (
                    f'[a=cr:{json.dumps({"id": "actor/" + slug, "name": actor_raw})}/]'
                    f"{actor_raw}[/a]"
                )

        tag_links = []
        for tag_href, tag_name in re.findall(
            r'<a class="tag"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', h, re.S
        ):
            tag_name = self._clean(tag_name)
            slug_match = re.search(r"/tag/([^/]+)/?$", tag_href)
            if slug_match:
                slug = slug_match.group(1)
                tag_links.append(
                    f'[a=cr:{json.dumps({"id": "tag/" + slug, "name": tag_name})}/]'
                    f"{tag_name}[/a]"
                )
        tag_content = " ".join(tag_links)

        vod = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": self._pic(pic, vid),
            "type_name": "",
            "vod_year": date,
            "vod_actor": actor_link,
            "vod_remarks": duration or "m3u8",
            "vod_content": " ".join([tag_content, actor_raw, duration, date]).strip(),
            "vod_play_from": "直连",
            "vod_play_url": "播放$" + vid,
        }
        return {"list": [vod]}

    # ================= 搜索修复开始 =================
    def searchContent(self, key, quick=False, pg="1"):
        k = str(key or "").strip().lower()
        if not k:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}

        pg = int(pg or 1)
        pool = self._get_search_pool()

        results = []
        for v in pool:
            score = 0
            vod_name = v.get("vod_name", "").lower()
            type_name = v.get("type_name", "").lower()
            vod_remarks = v.get("vod_remarks", "").lower()
            vod_id = str(v.get("vod_id", "")).lower()

            if k in vod_name:
                score += 10
            if k in type_name:
                score += 5
            if k in vod_remarks:
                score += 2
            if k in vod_id:
                score += 1

            if score > 0:
                results.append((score, v))

        # 按相关度降序排列
        results.sort(key=lambda x: x[0], reverse=True)

        page_size = 20
        total = len(results)
        pagecount = max(1, (total + page_size - 1) // page_size)
        if pg < 1:
            pg = 1
        if pg > pagecount:
            pg = pagecount

        start = (pg - 1) * page_size
        end = start + page_size
        out = [v for _, v in results[start:end]]

        return {
            "list": out,
            "page": pg,
            "pagecount": pagecount,
            "limit": len(out),
            "total": total,
        }

    def _get_search_pool(self):
        """构建搜索池：RSS + 首页 + Featured多页，5分钟缓存"""
        now = time.time()
        if self._search_pool and (now - self._search_pool_ts) < 300:
            return self._search_pool

        pool = []

        # 1. RSS 全量（去掉120条限制）
        pool.extend(self._rss_all())

        # 2. 首页视频列表
        pool.extend(self._video_list(self.host + self.lang + "/"))

        # 3. Featured 多页（增加搜索覆盖率）
        for p in range(1, 4):
            url = self.host + self.lang + "/featured/" + (str(p) if p > 1 else "")
            pool.extend(self._video_list(url))

        self._search_pool = self._dedup(pool)
        self._search_pool_ts = now
        return self._search_pool

    def _rss_all(self):
        """RSS 全量抓取，不限制条数，封面走原始 _pic() 通道"""
        urls = [
            self.host + self.lang + "/rss.xml",
            self.host + "/rss.xml",
        ]
        for url in urls:
            h = self._get(url)
            if not h:
                continue
            arr = []
            for item in re.findall(r"<item>(.*?)</item>", h, re.S):
                title_m = re.search(r"<title>(.*?)</title>", item, re.S)
                link_m = re.search(r"<link>(.*?)</link>", item, re.S)
                desc_m = re.search(r"<description>(.*?)</description>", item, re.S)
                date_m = re.search(r"<pubDate>(.*?)</pubDate>", item, re.S)

                title = self._clean(title_m.group(1)) if title_m else ""
                link = self._clean(link_m.group(1)) if link_m else ""
                desc = self._clean(desc_m.group(1)) if desc_m else ""
                date = self._clean(date_m.group(1)) if date_m else ""

                vid_m = re.search(r"/v/(\d+)/", link)
                if vid_m:
                    vid = vid_m.group(1)
                    cover = self.cdn + "/" + vid + "/cover.jpg"
                    arr.append({
                        "vod_id": vid,
                        "vod_name": title or vid,
                        "vod_pic": self._pic(cover, vid),
                        "vod_remarks": date[:16] if date else "m3u8",
                        "type_name": desc,
                    })
            if arr:
                return arr
        return []

    def _rss(self):
        """保留原方法名兼容，内部调用 _rss_all"""
        return self._rss_all()
    # ================= 搜索修复结束 =================

    def playerContent(self, flag, id, vipFlags):
        vid_match = re.search(r"(\d+)", str(id).strip())
        if not vid_match:
            return {"parse": 0, "playUrl": "", "url": ""}
        vid = vid_match.group(1)
        return {
            "parse": 0,
            "playUrl": "",
            "url": self.plp + self.cdn + "/" + vid + "/index.m3u8",
            "header": {
                "User-Agent": self.ua,
                "Referer": self.host + self.lang + "/v/" + vid + "/",
            },
        }

    def localProxy(self, param):
        try:
            u = unquote(param.get("url", ""))
            if not u or u in self.bad_img:
                return [404, "text/plain", ""]
            if u in self.img_cache:
                return self.img_cache[u]

            r = self.img_session.get(
                u,
                headers=self.img_headers,
                timeout=3,
                proxies=self.proxy,
            )
            if r.status_code != 200 or not r.content:
                self.bad_img.add(u)
                return [404, "text/plain", ""]

            res = [200, r.headers.get("content-type", "image/jpeg"), r.content]
            if len(self.img_cache) > 80:
                self.img_cache.clear()
            self.img_cache[u] = res
            return res
        except Exception:
            self.bad_img.add(unquote(param.get("url", "")))
            return [404, "text/plain", ""]

    def _get(self, url):
        if url in self.page_cache:
            return self.page_cache[url]

        try:
            r = self.session.get(
                url,
                headers=self.headers,
                timeout=8,
                verify=False,
                proxies=self.proxy,
            )
            r.encoding = "utf-8"
            h = r.text if r.status_code == 200 else ""
            if h:
                if len(self.page_cache) > 40:
                    self.page_cache.clear()
                self.page_cache[url] = h
            return h
        except Exception:
            return ""

    @staticmethod
    def _clean(s):
        s = re.sub(r"<!\[CDATA\[|\]\]>", "", s or "")
        s = re.sub(r"<.*?>", "", s)
        s = re.sub(r"\s+", " ", s)
        return s.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'").strip()

    def _pic(self, u, vid=""):
        u = u or self.cdn + "/" + str(vid) + "/cover.jpg"
        if self._proxy_prefix is None:
            self._proxy_prefix = self.getProxyUrl()
        return self._proxy_prefix + (
            "&" if "?" in self._proxy_prefix else "?"
        ) + "url=" + quote(u, safe="")

    @staticmethod
    def _dedup(arr):
        seen = set()
        out = []
        for x in arr:
            k = x.get("vod_id")
            if k and k not in seen:
                seen.add(k)
                out.append(x)
        return out

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False
