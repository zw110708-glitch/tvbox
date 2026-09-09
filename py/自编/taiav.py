import json
import re
from urllib.parse import parse_qs, quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def init(self, extend=""):
        try:
            cfg = json.loads(extend) if isinstance(extend, str) and extend else (extend or {})
        except Exception:
            cfg = {}
        self.host = (cfg.get("host") or "https://taiav.com").rstrip("/")
        self.plp = cfg.get('plp', '')
        self.proxy = cfg.get("proxy", {})
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Referer": f"{self.host}/",
        }
        self.fixed_categories = [
            ("最新更新", "news", "/cn/news"),
            ("随机", "random", "/random"),
            ("热门视频", "hots", "/hots"),           
            ("无码", "cat_uncensored", "/cn/category/%E6%97%A0%E7%A0%81"),
            ("有码", "cat_censored", "/cn/category/%E6%9C%89%E7%A0%81"),
            ("国产AV", "cat_china", "/cn/category/%E5%9B%BD%E4%BA%A7AV"),
            ("网红主播", "cat_webstar", "/cn/category/%E7%BD%91%E7%BA%A2%E4%B8%BB%E6%92%AD"),
            ("大分类", "discover_category", "/discover?tab=category"),
            ("热门标签", "discover_tags", "/discover?tab=tags"),
        ]
        self.category_map = {i: p for _, i, p in self.fixed_categories}
        self.blocked_hosts = ("enter.javhd.com", "mavrtracktor", "adxadserv", "jads.co")
        self.blocked_titles = ("AI脱衣换脸", "脫衣秀聊天室", "Porn Dude", "廣告", "广告")

    def getName(self):
        return "🌈 通用视频解析器|Taiav精简版"

    def isVideoFormat(self, url):
        url = (url or "").lower()
        return any(url.endswith(ext) or (ext in url and "?" in url) for ext in (".m3u8", ".mp4", ".ts", ".flv", ".mkv", ".avi", ".webm"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass

    def homeContent(self, filter):
        soup = self._get_soup(self.host)
        return {
            "class": [{"type_name": n, "type_id": i} for n, i, _ in self.fixed_categories],
            "filters": {},
            "list": self._parse_cards(soup) if soup else [],
        }

    def categoryContent(self, tid, pg, filter, extend):
        page = max(int(pg or 1), 1)
        tid = self.category_map.get(tid, tid)
        if "@folder" in tid:
            return self._list_result(tid.replace("@folder", ""), page)
        if "/discover" in tid:
            soup = self._get_soup(f"{self.host}/discover")
            if not soup:
                return self._result([])
            tab = (parse_qs(urlparse(self._full_url(tid)).query).get("tab", [""])[0] or "").lower()
            cards = self._parse_discover_category_cards(soup) if tab == "category" else self._parse_discover_tag_cards(soup)
            return self._result(cards, 1, 1, len(cards))
        url = self._full_url(tid)
        if isinstance(extend, dict):
            params = "&".join(f"{k}={quote(str(v))}" for k in ("class", "area", "year", "lang", "letter", "by") if (v := extend.get(k)))
            if params:
                url = f"{url}{'&' if '?' in url else '?'}{params}"
        return self._list_result(url, page)

    def detailContent(self, ids):
        url = self._full_url((ids[0] if isinstance(ids, list) and ids else ids) or self.host)
        html = self._get_html(url)
        vid = self._extract_movie_id(url, html)
        play = self._try_get_m3u8_by_api(url, vid) if vid else ""
        content = ""
        if html:
            soup = BeautifulSoup(html, "html.parser")
            tags = []
            for a in soup.select('a.uk-button[href*="/cn/tag/"]'):
                name = a.get_text(strip=True)
                href = (a.get("href") or "").strip()
                if not name or not href or href.endswith("/cn/tag/"):
                    continue
                tags.append(f'[a=cr:{json.dumps({"id": self._full_url(href) + "@folder", "name": name}, ensure_ascii=False)}/]{name}[/a]')
            intro = ""
            p = soup.select_one("p.uk-margin-small-top")
            if p:
                for span in p.select("span"):
                    span.decompose()
                intro = p.get_text(" ", strip=True)
            parts = []
            if tags:
                parts.append("标签: " + " ".join(dict.fromkeys(tags)))
            if intro:
                parts.append(intro)
            content = "\n".join(parts)
        return {"list": [{"vod_play_from": "Taiav", "vod_play_url": f"正片${play}", "vod_content": content}]}

    def searchContent(self, key, quick, pg="1"):
        page = max(int(pg or 1), 1)
        url = f"{self.host}/cn/search?q={quote(key)}"
        videos, pagecount = self._fetch_list(url, page)
        return self._result(videos, page, pagecount, pagecount * 90)

    def playerContent(self, flag, id, vipFlags):
        return {"parse": 0, "url": f"{self.plp}{id}", "header": self.headers}

    def _result(self, videos, page=1, pagecount=1, total=999999):
        return {"list": videos, "page": page, "pagecount": pagecount, "limit": 90, "total": total}

    def _list_result(self, url, page):
        videos, pagecount = self._fetch_list(url, page)
        return self._result(videos, page, pagecount)

    def _full_url(self, url):
        url = (url or "").strip()
        if not url:
            return self.host
        if url.startswith("http"):
            return url
        return urljoin(self.host + "/", url.lstrip("/"))

    def _get_html(self, url):
        try:
            r = self.session.get(url, headers=self.headers, proxies=self.proxy, timeout=8)
            if r.status_code != 200:
                return ""
            r.encoding = r.apparent_encoding
            return r.text or ""
        except Exception:
            return ""

    def _get_soup(self, url):
        html = self._get_html(url)
        return BeautifulSoup(html, "html.parser") if html else None

    def _paged_url(self, url, page):
        return f"{self._full_url(url)}{'&' if '?' in url else '?'}page={page}" if page > 1 else self._full_url(url)

    def _fetch_list(self, url, page):
        soup = self._get_soup(self._paged_url(url, page))
        return ([], 1) if not soup else (self._parse_cards(soup), self._parse_pagecount(soup))

    def _extract_movie_id(self, url, html):
        m = re.search(r"/movie/([0-9a-fA-F]{8,})", url or "")
        if m:
            return m.group(1)
        if html:
            for p in (
                r'\bvar\s+id\s*=\s*"([0-9a-fA-F]{8,})"',
                r"/api/getmovie\?type=[^\s'\"]+\\u0026id=([0-9a-fA-F]{8,})",
            ):
                m = re.search(p, html)
                if m:
                    return m.group(1)
        return ""

    def _try_get_m3u8_by_api(self, detail_url, vid):
        try:
            r = self.session.get(
                f"{self.host}/api/getmovie?type=1280&id={vid}",
                headers={**self.headers, "Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest", "Referer": detail_url},
                proxies=self.proxy,
                timeout=8,
            )
            if r.status_code != 200:
                return ""
            data = r.json() if "json" in (r.headers.get("Content-Type") or "") else json.loads(r.text or "{}")
            return self._full_url((data or {}).get("m3u8") or "")
        except Exception:
            return ""

    def _folder_card(self, href, name):
        return {"vod_id": self._full_url(href) + "@folder", "vod_name": name, "vod_pic": "", "vod_remarks": "", "style": {"type": "rect", "ratio": 1.33}, "vod_tag": "folder"}

    def _parse_discover_category_cards(self, soup):
        sec = next((h for h in soup.select("h3") if h.get_text(strip=True) == "大分类"), None)
        grid = sec.find_next("div", attrs={"uk-grid": True}) if sec else None
        if not grid:
            return []
        return [self._folder_card(a.get("href"), a.get_text(strip=True)) for a in grid.select("a[href]") if "/cn/category/" in (a.get("href") or "") and a.get_text(strip=True)]

    def _parse_discover_tag_cards(self, soup):
        cards = {}
        for h in soup.select("h3"):
            if h.get_text(strip=True) == "大分类":
                continue
            grid = h.find_next("div", attrs={"uk-grid": True})
            if not grid:
                continue
            for a in grid.select("a[href]"):
                href = (a.get("href") or "").strip()
                name = a.get_text(strip=True)
                if name and "/cn/tag/" in href and not href.endswith("/cn/tag/"):
                    card = self._folder_card(href, name)
                    cards[card["vod_id"]] = card
        return list(cards.values())

    def _parse_cards(self, soup):
        videos = []
        seen = set()
        for card in soup.select(".movie-card"):
            a = card.select_one("a[href]")
            if not a:
                continue
            href = self._full_url(a.get("href"))
            if href in seen or any(x in href for x in self.blocked_hosts):
                continue
            img_tag = card.select_one("img")
            title = ""
            h5 = card.select_one(".uk-card-body h5")
            if h5:
                title = h5.get_text(strip=True)
            if not title:
                title = ((a.get("title") or "") if a else "") or ((img_tag.get("alt") or "") if img_tag else "") or a.get_text(strip=True)
            if not title or any(x in title for x in self.blocked_titles):
                continue
            seen.add(href)
            img = ((img_tag.get("src") or "") if img_tag else "") or ((img_tag.get("data-src") or "") if img_tag else "")
            img = "" if img.lower().endswith(".gif") else self._full_url(img)
            remark_tag = card.select_one(".video-box-info .uk-tag")
            videos.append({
                "vod_id": href,
                "vod_name": title,
                "vod_pic": img,
                "vod_remarks": remark_tag.get_text(strip=True) if remark_tag else "",
                "style": {"type": "rect", "ratio": 1.33},
            })
        return videos

    def _parse_pagecount(self, soup):
        pager = soup.select("ul.pagination a, .pagination a, .uk-pagination a")
        if not pager:
            return 1
        nums = [1]
        for a in pager:
            href = (a.get("href") or "").strip()
            txt = a.get_text(strip=True)
            m = re.search(r"(?:[?&]|^)page=(\d+)", href)
            if m:
                nums.append(int(m.group(1)))
            elif txt.isdigit():
                nums.append(int(txt))
        return max(nums)
