# coding: utf-8
import base64
import json
import re
from urllib.parse import quote, unquote, urljoin

import requests
from bs4 import BeautifulSoup

from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def init(self, extend=""):
        try:
            cfg = json.loads(extend) if isinstance(extend, str) and extend.strip() else (extend or {})
        except Exception:
            cfg = {}

        self.base = (cfg.get("host") or "https://321xav.icu").rstrip("/")
        self.entry = self.base + "/enter"
        self.proxies = cfg.get("proxies") or {}
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": f"{self.base}/",
        }

    def getName(self):
        return "321AV"

    def isVideoFormat(self, url):
        u = (url or "").lower()
        return any(x in u for x in (".m3u8", ".mp4", ".ts"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ---------------- helpers ----------------
    def _get_text(self, url, timeout=10):
        r = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=timeout)
        r.encoding = r.apparent_encoding
        return r.text

    def _abs(self, u):
        return u if u.startswith("http") else urljoin(self.base + "/", u)

    def _soup(self, html):
        return BeautifulSoup(html, "html.parser")

    def _cat_url(self, tid, pg):
        # 分页 URL 适配（兼容 vodtype /vod/search 的多种路由）
        pg = int(pg or 1)
        tid = self._abs(tid)
        if pg <= 1:
            return tid

        # 1) /vodtype/20.html -> /vodtype/20-2.html
        m = re.search(r"(/vodtype/\d+)\.html$", tid)
        if m:
            return tid.replace(m.group(0), f"{m.group(1)}-{pg}.html")

        # 2) /vod/search/... 路由（演员/标签/关键词/排序）
        if "/vod/search/" in tid:
            # 2.1) 关键词搜索：/vod/search/page/2/wd/XXX.html
            if re.search(r"/vod/search/page/\d+/wd/", tid):
                return re.sub(r"/vod/search/page/\d+/wd/", f"/vod/search/page/{pg}/wd/", tid)
            if re.search(r"/vod/search/wd/", tid):
                return re.sub(r"/vod/search/wd/", f"/vod/search/page/{pg}/wd/", tid)

            # 2.2) 标签搜索：/vod/search/id/21/page/2/tag/XXX.html
            if "/tag/" in tid:
                if re.search(r"/page/\d+/tag/", tid):
                    return re.sub(r"/page/\d+/tag/", f"/page/{pg}/tag/", tid)
                return tid.replace("/tag/", f"/page/{pg}/tag/", 1)

            # 2.3) 演员搜索：/vod/search/actor/XXX/id/21/page/2.html
            if "/actor/" in tid:
                if re.search(r"/page/\d+\.html$", tid):
                    return re.sub(r"/page/\d+\.html$", f"/page/{pg}.html", tid)
                if re.search(r"/id/\d+\.html$", tid):
                    return re.sub(r"\.html$", f"/page/{pg}.html", tid)

            # 2.4) 兜底：优先替换 /page/N.html 结尾
            if re.search(r"/page/\d+\.html$", tid):
                return re.sub(r"/page/\d+\.html$", f"/page/{pg}.html", tid)

        # 3) .../page/1.html -> .../page/2.html
        if re.search(r"/page/\d+\.html$", tid):
            return re.sub(r"/page/\d+\.html$", f"/page/{pg}.html", tid)

        # 4) 兜底：.../xxx.html -> .../xxx/page/2.html
        if tid.endswith(".html"):
            return tid[:-5] + f"/page/{pg}.html"

        return tid.rstrip("/") + f"/page/{pg}.html"
    def _replace_res_url(self, url):
        # xplayer 内的替换逻辑：host/path -> rjmp1.datalicdn.top/host//path
        return re.sub(r"(https?://)([\w\.-]+)(/)", r"\1rjmp1.datalicdn.top\3\2\3", url, count=1)

    def _unpack_packer(self, js):
        # Dean Edwards Packer（本站返回的 videoUrl 是这种混淆）
        m = re.search(
            r"decop\(function\(p,a,c,k,e,d\)\{.*?\}\('(.+?)',(\d+),(\d+),'([^']*)'\.split\('\|'\)",
            js,
            re.S,
        )
        if not m:
            return ""
        payload, a, c, k = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4).split("|")

        def base_n(num, base):
            chars = "0123456789abcdefghijklmnopqrstuvwxyz"
            if num == 0:
                return "0"
            s = ""
            while num:
                num, r = divmod(num, base)
                s = chars[r] + s
            return s

        out = payload
        for i in range(c - 1, -1, -1):
            if i < len(k) and k[i]:
                out = re.sub(r"\b" + re.escape(base_n(i, a)) + r"\b", k[i], out)
        return out.replace("\\'", "'")

    # ---------------- tvbox api ----------------
    def homeContent(self, filter):
        soup = self._soup(self._get_text(self.entry))

        cats, seen = [], set()
        for a in soup.select('a[href^="/vodtype/"]'):
            href = a.get("href") or ""
            if not re.search(r"/vodtype/\d+\.html$", href):
                continue
            name = a.get_text(strip=True)
            if not name:
                continue
            cid = self._abs(href)
            if cid in seen:
                continue
            seen.add(cid)
            cats.append({"type_name": name, "type_id": cid})
            if len(cats) >= 20:
                break

        return {"class": cats, "filters": {}, "list": self._list_from_soup(soup)}

    def homeVideoContent(self):
        return {"list": self.homeContent(False).get("list", [])}

    def _parse_pagecount(self, soup, current_page):
        # 从分页区域解析总页数；解析不到则回退为 current_page
        # 站点移动端分页会显示："/ 7759" 这种总页数
        t = soup.get_text(" ", strip=True)
        m = re.search(r"/\s*(\d+)\b", t)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass

        nums = []
        for a in soup.select('a[href]'):
            href = a.get('href') or ''
            # ...-3.html
            m = re.search(r"-(\d+)\.html$", href)
            if m:
                nums.append(int(m.group(1)))
                continue
            # .../page/3.html
            m = re.search(r"/page/(\d+)\.html$", href)
            if m:
                nums.append(int(m.group(1)))
                continue
            # /vod/search/page/3/wd/xxx.html
            m = re.search(r"/vod/search/page/(\d+)/", href)
            if m:
                nums.append(int(m.group(1)))
                continue
        return max(nums) if nums else int(current_page or 1)

    def categoryContent(self, tid, pg, filter, extend):
        p = int(pg or 1)
        url = self._cat_url(tid, p)
        soup = self._soup(self._get_text(url))
        items = self._list_from_soup(soup)
        pagecount = self._parse_pagecount(soup, p)
        # 如果已经没有内容，直接锁死页数，避免客户端无限翻页
        if not items and p > 1:
            pagecount = p - 1
        return {"list": items, "page": p, "pagecount": pagecount, "limit": 90, "total": pagecount * 90}

    def detailContent(self, ids):
        # 本站列表直接是 /vodplay/xxx-1-1.html，按单集处理
        play = self._abs(ids[0])
        soup = self._soup(self._get_text(play))

        title_el = (soup.select_one("h1") or soup.select_one("title"))
        title = title_el.get_text(strip=True) if title_el else ""

        pic = ""
        og = soup.select_one('meta[property="og:image"]')
        if og and og.get("content"):
            pic = og.get("content").strip()

        # 主演（可点击）
        actors = []
        for div in soup.select("div.text-secondary"):
            sp = div.find("span")
            if not sp:
                continue
            if "主演" not in sp.get_text(strip=True):
                continue
            for a in div.select("a[href]"):
                name = a.get_text(strip=True)
                href = a.get("href")
                if name and href:
                    actors.append((name, self._abs(href)))
            break

        actor_html = ""
        if actors:
            links = " ".join(
                [
                    f"[a=cr:{json.dumps({'id': href, 'name': name}, ensure_ascii=False)}/]{name}[/a]"
                    for name, href in actors
                ]
            )
            actor_html = links

        # 标签（可点击）+ 影片简介
        tags = []
        for div in soup.select("div.text-secondary"):
            sp = div.find("span")
            if not sp:
                continue
            if "标签" not in sp.get_text(strip=True):
                continue
            for a in div.select("a[href]"):
                name = a.get_text(strip=True)
                href = a.get("href")
                if name and href:
                    tags.append((name, self._abs(href)))
            break

        tag_html = ""
        if tags:
            links = " ".join(
                [
                    f"[a=cr:{json.dumps({'id': href, 'name': name}, ensure_ascii=False)}/]{name}[/a]"
                    for name, href in tags
                ]
            )
            tag_html = f"标签:{links}"

        intro = ""
        intro_div = soup.find(lambda t: t.name == "div" and (t.get_text(strip=True) or "").startswith("简介："))
        if intro_div:
            intro = intro_div.get_text(" ", strip=True)

        intro_html = ""
        if intro:
            intro_html = (
                '<div class="mb-4">'
                f'<div class="mb-1 text-secondary break-all line-clamp-2">{intro}</div>'
                "</div>"
            )

        vod_content = tag_html + intro_html

        return {
            "list": [
                {
                    "vod_id": play,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_actor": actor_html,
                    "vod_content": vod_content,
                    "vod_play_from": "321AV",
                    "vod_play_url": f"播放${play}",
                }
            ]
        }

    def searchContent(self, key, quick, pg="1"):
        # 站点搜索结果路由：/vod/search/page/2/wd/XXX.html
        p = int(pg or 1)
        url = f"{self.base}/vod/search/page/{p}/wd/{quote(key)}.html"
        soup = self._soup(self._get_text(url))
        items = self._list_from_soup(soup)
        pagecount = self._parse_pagecount(soup, p)
        if not items and p > 1:
            pagecount = p - 1
        return {"list": items, "page": p, "pagecount": pagecount}

    def playerContent(self, flag, id, vipFlags):
        play_page = self._abs(id)
        try:
            html = self._get_text(play_page)
            m = re.search(r"player_aaaa\s*=\s*(\{.*?\})\s*</script>", html, re.S)
            if not m:
                raise ValueError
            p = json.loads(m.group(1))

            raw = p.get("url") or ""
            enc = str(p.get("encrypt", "0"))
            if enc == "1":
                raw = unquote(raw)
            elif enc == "2":
                raw = unquote(base64.b64decode(raw).decode("utf-8", "ignore"))

            src_obj = json.loads(base64.b64decode(raw).decode("utf-8", "ignore"))
            for typ, path, *_ in (src_obj.get("ss") or []):
                if typ == 1 and path:
                    return {"parse": 0, "url": path, "header": self.headers}
                if typ != 0 or not path:
                    continue

                api = "https://rmissav.datalicdn.top" + ("" if path.startswith("/") else "/") + path
                js = self._get_text(api)
                plain = self._unpack_packer(js) or js
                urls = re.findall(r"https?://[^\"\s']+", plain)
                urls = [u for u in urls if any(x in u for x in (".m3u8", ".mp4"))]
                if urls:
                    return {"parse": 0, "url": self._replace_res_url(urls[0]), "header": self.headers}
        except Exception:
            pass

        return {"parse": 1, "url": play_page, "header": self.headers}

    # ---------------- list parser ----------------
    def _list_from_soup(self, soup):
        """解析列表页/搜索页缩略图。

        站点结构：
        - 封面链接 a[href^=/vodplay/] 包着 img/video，通常没有文字
        - 片名在同卡片下方 div.my-2 ... a.text-secondary 内
        """
        out, seen = [], set()

        # 优先按卡片容器解析，保证能拿到片名
        cards = soup.select("div.thumbnail.group") or []
        if cards:
            for card in cards:
                a_cover = card.select_one('a[href^="/vodplay/"]')
                if not a_cover:
                    continue
                href = a_cover.get("href") or ""
                if not re.search(r"/vodplay/\d+-\d+-\d+\.html$", href):
                    continue
                vid = self._abs(href)
                if vid in seen:
                    continue
                seen.add(vid)

                # 片名：优先取卡片下方文字链接，其次 img alt / a title
                title = ""
                a_title = card.select_one("div.my-2 a")
                if a_title:
                    title = a_title.get_text(strip=True)
                if not title:
                    img = card.find("img")
                    if img and img.get("alt"):
                        title = img.get("alt").strip()
                if not title:
                    title = (a_cover.get("title") or "").strip()

                # 封面
                img = card.find("img")
                pic = (img.get("data-src") or img.get("src")) if img else ""

                out.append(
                    {
                        "vod_id": vid,
                        "vod_name": title,
                        "vod_pic": self._abs(pic) if pic else "",
                        "vod_remarks": "",
                        "style": {"type": "rect", "ratio": 1.33},
                    }
                )
                if len(out) >= 90:
                    break
            return out

        # 兜底：老结构直接扫 /vodplay/ 链接
        for a in soup.select('a[href^="/vodplay/"]'):
            href = a.get("href") or ""
            if not re.search(r"/vodplay/\d+-\d+-\d+\.html$", href):
                continue
            vid = self._abs(href)
            if vid in seen:
                continue
            seen.add(vid)

            title = (a.get("title") or a.get_text(strip=True) or "").strip()
            img = a.find("img")
            if not title and img and img.get("alt"):
                title = img.get("alt").strip()
            pic = (img.get("data-src") or img.get("src")) if img else ""

            out.append(
                {
                    "vod_id": vid,
                    "vod_name": title,
                    "vod_pic": self._abs(pic) if pic else "",
                    "vod_remarks": "",
                    "style": {"type": "rect", "ratio": 1.33},
                }
            )
            if len(out) >= 90:
                break
        return out
