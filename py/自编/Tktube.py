import json
import re
import sys
import time
from urllib.parse import quote, urlencode, urljoin

import requests
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    """tktube.art/zh 直链精简版

    优化点：
    - 翻页：优先使用分页区提供的 **直链 href**；只有拿不到直链时才走 KVS 的 get_block（仍是直连请求）
    - 性能：requests.Session + 简单页面缓存（缓存第1页解析出的 block_id / pagecount / 分页直链）
    - 详情：稳定提取 HD/SD 两种清晰度 mp4 直链
    """

    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        elif isinstance(extend, dict):
            cfg = extend

        base = (cfg.get("host") or "https://tktube.art").rstrip("/")
        lang = (cfg.get("lang") or "zh").strip("/")
        self.host = f"{base}/{lang}"  # https://tktube.art/zh
        self.proxies = cfg.get("proxies") or {          "http": "http://127.0.0.1:10172",
          "https": "http://127.0.0.1:10172"}

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": f"{self.host}/",
        }

        self.s = requests.Session()
        self._cache = {}  # url -> {ts, html, block_id, pagecount, page_href_map}

    def getName(self):
        return "J163(tktube) 直链精简版"

    def manualVideoCheck(self):
        return False

    # ------------------------
    # Helpers
    # ------------------------
    def _get(self, url: str, timeout: int = 12) -> str:
        r = self.s.get(url, headers=self.headers, proxies=self.proxies, timeout=timeout)
        r.encoding = r.apparent_encoding
        return r.text

    def _abs(self, href: str) -> str:
        if not href:
            return ""
        return href if href.startswith("http") else urljoin(self.host + "/", href)

    def _cr(self, href: str, name: str) -> str:
        payload = {"id": href, "name": name}
        return f'[a=cr:{json.dumps(payload, ensure_ascii=False)}/]{name}[/a]'

    def _parse_video_cards(self, html: str):
        doc = pq(html)
        videos = []
        seen = set()
        for a in doc('a[href*="/videos/"]:has(img)').items():
            href = (a.attr("href") or "").strip()
            if not href:
                continue
            vid = self._abs(href)
            if vid in seen:
                continue

            img_tag = a.find("img")
            img = (img_tag.attr("data-webp") or img_tag.attr("src") or "").strip()
            title = (img_tag.attr("alt") or a.attr("title") or a.text() or "").strip()
            if not title or not img:
                continue

            videos.append(
                {
                    "vod_id": vid,
                    "vod_name": title,
                    "vod_pic": img,
                    "vod_remarks": "",
                    "style": {"type": "rect", "ratio": 1.33},
                }
            )
            seen.add(vid)
            if len(videos) >= 90:
                break
        return videos

    def _get_block_html(self, page_url: str, block_id: str, params: dict) -> str:
        sep = "&" if "?" in page_url else "?"
        q = {"mode": "async", "function": "get_block", "block_id": block_id}
        q.update(params or {})
        return self._get(page_url + sep + urlencode(q))

    def _extract_total_pages(self, doc: pq, block_id: str) -> int:
        # input id = {block_id}_myPageNum  title="Total:13454"
        inp = doc(f"#{block_id}_myPageNum")
        if inp:
            title = inp.attr("title") or ""
            m = re.search(r"Total\s*:\s*(\d+)", title)
            if m:
                return int(m.group(1))

        last = doc(f"#{block_id}_pagination li.last a, #{block_id}_pagination a.last")
        if last:
            dp = last.attr("data-parameters") or ""
            m = re.search(r"from:(\d+)", dp)
            if m:
                return int(m.group(1))

        return 9999

    def _build_page_href_map(self, doc: pq) -> dict:
        """从分页区收集 “页码 -> href(直链)”

        注意：很多分类页的分页链接是 `href="#videos"`（仅用于前端 JS-AJAX），
        这类锚点并不是真正的翻页直链，若误用会造成“翻页不精准/卡顿”。
        因此这里 **只收集真正的 http/相对路径直链**，忽略 `#...`。
        """
        page_map = {}
        for a in doc('a[data-action="ajax"][href]').items():
            txt = (a.text() or "").strip()
            href = (a.attr("href") or "").strip()
            if not href:
                continue
            if href.startswith('#'):
                continue
            if txt.isdigit():
                page_map[int(txt)] = href
        return page_map

    def _get_list_page_meta(self, url: str):
        # 简单缓存，避免每次翻页都重复抓第 1 页
        now = time.time()
        cache = self._cache.get(url)
        if cache and now - cache.get("ts", 0) < 180:
            return cache

        html = self._get(url)
        doc = pq(html)

        # block_id：直接从分页元素的 data-block-id 拿（最可靠）
        block_id = (doc('a[data-action="ajax"][data-block-id]').eq(0).attr("data-block-id") or "").strip()
        if not block_id:
            # 极少数页面没有分页 a（例如只有 1 页），按 URL 兜底
            block_id = "list_videos_most_recent_videos" if "/latest-updates" in url else "list_videos_common_videos_list"

        pagecount = self._extract_total_pages(doc, block_id)
        page_href_map = self._build_page_href_map(doc)

        cache = {"ts": now, "html": html, "block_id": block_id, "pagecount": pagecount, "page_href_map": page_href_map}
        self._cache[url] = cache
        return cache

    def _pick_quality_urls(self, html: str):
        """稳定提取详情页 HD/SD mp4 直链（只做直链，不做解析）。"""

        def _m(pat: str):
            m = re.search(pat, html, flags=re.I)
            return (m.group(1).strip() if m else "")

        # 1) Flowplayer 配置字段（最稳定）
        hd = _m(r"\bvideo_alt_url\s*:\s*['\"]([^'\"]+?\.mp4/?)['\"]")
        sd = _m(r"\bvideo_url\s*:\s*['\"]([^'\"]+?\.mp4/?)['\"]")

        # 2) 字段缺失时：从所有 mp4 直链中挑选（仍然是直链）
        if not (hd and sd):
            mp4s = re.findall(r"https?://[^'\"\s]+?\.mp4/?", html, flags=re.I)
            mp4s = list(dict.fromkeys([u.strip() for u in mp4s]))

            def q(u: str):
                m = re.search(r"_(\d{3,4})p\.mp4", u)
                return int(m.group(1)) if m else -1

            if mp4s:
                if not hd:
                    for u in mp4s:
                        if "_720p.mp4" in u:
                            hd = u
                            break
                if not sd:
                    for u in mp4s:
                        if "_360p.mp4" in u:
                            sd = u
                            break

                scored = [(q(u), u) for u in mp4s]
                scored = [x for x in scored if x[0] > 0] or scored
                scored.sort(key=lambda x: x[0])
                if scored:
                    sd = sd or scored[0][1]
                    hd = hd or scored[-1][1]

        return hd, sd

    # ------------------------
    # Home
    # ------------------------
    def homeContent(self, filter):
        classes = [
            {"type_name": "最新影片", "type_id": f"{self.host}/latest-updates/"},
            {"type_name": "好评影片", "type_id": f"{self.host}/top-rated/"},
            {"type_name": "热门影片", "type_id": f"{self.host}/most-popular/"},
        ]

        # 分类目录：仅以 /categories/ 页面为准（最稳定直链来源）
        try:
            cat_html = self._get(f"{self.host}/categories/")
            cat_doc = pq(cat_html)
            for a in cat_doc('a[href*="/categories/"]').items():
                href = self._abs((a.attr("href") or "").strip())
                if not href.startswith(f"{self.host}/categories/"):
                    continue
                if href.rstrip("/") == f"{self.host}/categories":
                    continue

                name = (a.attr("title") or a.text() or "").strip()
                name = name.replace("无头像", "").strip()
                name = re.sub(r"\s+\d+\s*影片.*$", "", name).strip()
                if not name:
                    continue

                classes.append({"type_name": name, "type_id": href})
                if len(classes) >= 20:
                    break
        except Exception:
            pass

        try:
            html = self._get(f"{self.host}/")
            videos = self._parse_video_cards(html)
        except Exception:
            videos = []

        return {"class": classes, "filters": {}, "list": videos}

    def homeVideoContent(self):
        return {"list": self.homeContent(None).get("list", [])}

    # ------------------------
    # Category / List（高效直链翻页）
    # ------------------------
    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg) if pg else 1
            url = tid if (tid or "").startswith("http") else self._abs(tid)

            meta = self._get_list_page_meta(url)
            block_id = meta["block_id"]
            pagecount = meta["pagecount"]

            if pg <= 1:
                html = meta["html"]
            else:
                # 1) 优先：分页区直接给的 href 直链
                href = meta["page_href_map"].get(pg)
                if href:
                    html = self._get(self._abs(href))
                else:
                    # 2) 拿不到 href：再用 get_block（仍然是直链请求）
                    from_val = str(pg).zfill(2) if pg < 100 else str(pg)
                    html = self._get_block_html(url, block_id, {"sort_by": "post_date", "from": from_val})

            videos = self._parse_video_cards(html)
            return {"list": videos, "page": pg, "pagecount": pagecount, "limit": 90, "total": pagecount * 90}
        except Exception:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 90, "total": 0}

    # ------------------------
    # Detail（HD/SD直链 + 演员/标签可点击）
    # ------------------------
    def detailContent(self, ids):
        try:
            url = ids[0] if (ids and ids[0].startswith("http")) else self._abs(ids[0])
            html = self._get(url)
            doc = pq(html)

            title = (doc("h1").text() or doc("title").text() or "").strip()
            hd, sd = self._pick_quality_urls(html)

            pic = None
            m = re.search(r"\bpreview_url1\s*:\s*['\"]([^'\"]+)['\"]", html)
            if m:
                pic = m.group(1).strip()
            pic = pic or doc('meta[property="og:image"]').attr("content") or doc("img").eq(0).attr("src") or ""

            play_items = []
            if hd:
                play_items.append(f"HD${hd}")
            if sd:
                play_items.append(f"SD${sd}")

            desc = (doc('meta[name="description"]').attr("content") or "").strip()

            # 女优
            actors = []
            for item in doc("div.item").items():
                if "女优" not in (item.text() or ""):
                    continue
                for a in item('a[href]').items():
                    name = (a.text() or "").strip()
                    href = (a.attr("href") or "").strip()
                    if name and href:
                        actors.append(self._cr(href, name))
                if actors:
                    break

            # 标签
            tags = []
            for item in doc("div.item").items():
                if "标签" not in (item.text() or ""):
                    continue
                for a in item('a[href]').items():
                    name = (a.text() or "").strip()
                    href = (a.attr("href") or "").strip()
                    if name and href:
                        tags.append(self._cr(href, name))
                if tags:
                    break

            desc2 = (doc('div.item[style*="display"]').text() or "").strip()

            vod_content_parts = []
            if tags:
                vod_content_parts.append("标签：" + " ".join(tags))
            vod_content_parts.append(desc2 or desc)

            vod = {
                "vod_id": url,
                "vod_name": title,
                "vod_pic": pic,
                "vod_play_from": "直链",
                "vod_play_url": "#".join([x for x in play_items if x]),
                "vod_content": "\n".join([x for x in vod_content_parts if x]),
            }
            if actors:
                vod["vod_actor"] = " ".join(actors)

            return {"list": [vod]}
        except Exception:
            return {"list": []}

    # ------------------------
    # Search
    # ------------------------
    def searchContent(self, key, quick, pg="1"):
        try:
            q = quote(key)
            url = f"{self.host}/search/{q}/"
            html = self._get(url)
            videos = self._parse_video_cards(html)
            return {"list": videos, "page": 1, "pagecount": 1}
        except Exception:
            return {"list": [], "page": 1, "pagecount": 1}

    # ------------------------
    # Player
    # ------------------------
    def playerContent(self, flag, id, vipFlags):
        return {"parse": 0, "url": f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{id}', "header": self.headers}
