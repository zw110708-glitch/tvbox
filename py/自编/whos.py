import json
import re
import sys
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def init(self, extend=""):
        if isinstance(extend, str) and extend:
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        else:
            cfg = extend or {}
        self.proxies = cfg.get("proxies", {})
        self.host = (cfg.get("host") or "").strip() or "https://whos.tv"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Referer": self.host + "/",
        }
        self.s = requests.Session()
        self.s.headers.update(self.headers)

    def getName(self):
        return "whos.tv 直链解析(极简+代理+详情信息)"

    def homeContent(self, filter):
        return {
            "class": [
                {"type_name": "影片库", "type_id": "/videos"},
                {"type_name": "女优库", "type_id": "/actresses"},
                {"type_name": "专题", "type_id": "/topics"},
                {"type_name": "排行榜", "type_id": "/ranking/video"},
            ],
            "filters": {},
            "list": self._video_list("/videos", 1),
        }

    def homeVideoContent(self):
        return {"list": self._video_list("/videos", 1)}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        path = tid if str(tid).startswith("/") else "/" + str(tid)

        # 女优库一级列表（女优列表）
        if path == "/actresses":
            return {"list": self._actress_list(pg), "page": pg, "pagecount": 9999, "limit": 90, "total": 999999}
        # 专题一级列表
        elif path == "/topics":
            return {"list": self._topic_list(pg), "page": pg, "pagecount": 9999, "limit": 90, "total": 999999}

        # 女优详情页（作品列表）—— 常规分页
        if path.startswith("/actresses/") and path != "/actresses":
            lst = self._video_list(path, pg)
            return {"list": lst, "page": pg, "pagecount": 9999, "limit": 90, "total": 999999}

        # 专题详情页（收录内容）—— AJAX 加载更多
        if path.startswith("/topics/details/"):
            lst, total_pages = self._video_list_from_ajax(path, pg)
            return {"list": lst, "page": pg, "pagecount": total_pages, "limit": 90, "total": 999999}

        # 其他（影片库、搜索结果等）常规分页
        lst = self._video_list(path, pg)
        return {"list": lst, "page": pg, "pagecount": 9999, "limit": 90, "total": 999999}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg or 1)
        # 修正参数名 serach -> search
        return {"list": self._video_list(f"/result?search={quote(key)}", pg), "page": pg, "pagecount": 9999}

    def detailContent(self, ids):
        url = ids[0]
        if not str(url).startswith("http"):
            url = urljoin(self.host, str(url))

        html = self._get(url)
        soup = BeautifulSoup(html, "lxml")

        # 处理帧页面
        if "/frames/" in url:
            video_link = soup.select_one('a[href^="/videos/"]')
            if video_link:
                video_url = urljoin(self.host, video_link.get("href"))
                video_html = self._get(video_url)
                video_soup = BeautifulSoup(video_html, "lxml")
                return self._parse_video_detail(video_soup, video_url)
            m3u8 = self._extract_m3u8_from_soup(soup)
            if m3u8:
                title = soup.select_one("h1")
                vod_name = title.get_text(strip=True) if title else "帧"
                return {
                    "list": [{
                        "vod_name": vod_name,
                        "vod_play_from": "直链",
                        "vod_play_url": m3u8,
                        "vod_content": "",
                    }]
                }
            title = soup.select_one("h1")
            vod_name = title.get_text(strip=True) if title else "帧"
            return {
                "list": [{
                    "vod_name": vod_name,
                    "vod_play_from": "直链",
                    "vod_play_url": f"网页播放${url}",
                    "vod_content": "",
                }]
            }

        # 普通影片页面
        return self._parse_video_detail(soup, url)

    def _parse_video_detail(self, soup, url):
        title = self._first_text_html(soup, ["h1", "title"]) or "whos.tv"
        m3u8 = self._extract_m3u8_from_soup(soup)
        if m3u8:
            play = [f"线路1${m3u8}"]
        else:
            play = []
        vod = {
            "vod_name": title.split("|")[0].strip() or "whos.tv",
            "vod_play_from": "直链",
            "vod_play_url": "#".join(play) if play else f"网页播放${url}",
            "vod_content": "",
        }
        vod["vod_actor"] = self._clickable_list(soup, '/actresses/', True)
        vod["vod_director"] = self._clickable_list(soup, '/makers/', False)
        tags = self._clickable_list(soup, '/tags/', True)
        if tags:
            vod["vod_content"] = "标签: " + tags
        return {"list": [vod]}

    def _extract_m3u8_from_soup(self, soup):
        player = soup.select_one("video-player")
        if player:
            src = player.get("data-preview-source")
            if src and src.startswith("http"):
                return src
        source = soup.select_one("video source[src]")
        if source:
            src = source.get("src")
            if src and src.startswith("http"):
                return src
        html = str(soup)
        matches = re.findall(r"https?://[^\"'\s]+\.m3u8[^\"'\s]*", html)
        if matches:
            return matches[0]
        return None

    def playerContent(self, flag, id, vipFlags):
        return {"parse": 0, "url": f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{id}', "header": self.headers}

    def _get(self, url_or_path):
        url = url_or_path if str(url_or_path).startswith("http") else urljoin(self.host, str(url_or_path))
        r = self.s.get(url, proxies=self.proxies, timeout=12)
        r.encoding = r.apparent_encoding
        return r.text

    @staticmethod
    def _paged_url(path, pg):
        pg = int(pg or 1)
        if pg <= 1:
            return path
        if "?" in path:
            base, qs = path.split("?", 1)
            return f"{base.rstrip('/')}/page-{pg}?{qs}"
        return f"{path.rstrip('/')}/page-{pg}"

    def _video_list(self, path, pg):
        html = self._get(self._paged_url(path, pg))
        soup = BeautifulSoup(html, "lxml")
        return self._parse_video_cards(soup)

    def _parse_video_cards(self, soup):
        out, seen = [], set()
        for a in soup.select('a[href^="/videos/"]'):
            cover = a.select_one('[data-cover-src]')
            if not cover:
                continue
            href = a.get("href")
            if not href or href in seen:
                continue
            seen.add(href)
            title = (cover.get("alt") or "").strip() or " ".join(a.get_text(" ", strip=True).split())
            if not title:
                continue
            pic_enc = cover.get("data-cover-src")
            out.append(
                {
                    "vod_id": urljoin(self.host, href),
                    "vod_name": title,
                    "vod_pic": "http://127.0.0.1:10079/p/0/127.0.0.1:10172/" + self._decode_cover(pic_enc) if pic_enc else "",
                    "vod_remarks": (a.select_one("span.badge").get_text(strip=True) if a.select_one("span.badge") else ""),
                    "style": {"type": "rect", "ratio": 1.6},
                }
            )
        return out

    def _parse_frame_cards(self, soup):
        out, seen = [], set()
        for a in soup.select('a[href^="/frames/"]'):
            href = a.get("href")
            if not href or href in seen:
                continue
            seen.add(href)
            img = a.find("img")
            pic = img.get("src") if img else ""
            title_el = a.find("h3")
            title = title_el.get_text(" ", strip=True) if title_el else ""
            if not title:
                continue
            out.append({
                "vod_id": urljoin(self.host, href),
                "vod_name": title,
                "vod_pic": f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pic}',
                "vod_remarks": "",
                "style": {"type": "rect", "ratio": 1.6},
            })
        return out

    def _video_list_from_ajax(self, path, pg):
        html = self._get(path)
        soup = BeautifulSoup(html, "lxml")

        # 影片列表
        btn = soup.select_one('[data-key="load-more"][data-load-url*="/video"]')
        if btn:
            load_url = btn.get("data-load-url")
            if load_url:
                if not load_url.startswith("http"):
                    load_url = urljoin(self.host, load_url)
                page_size = int(btn.get("data-page-size", 20))
                separator = "&" if "?" in load_url else "?"
                ajax_url = f"{load_url}{separator}page={pg}&page_size={page_size}"
                try:
                    resp_html = self._get(ajax_url)
                    frag_soup = BeautifulSoup(resp_html, "lxml")
                    cards = self._parse_video_cards(frag_soup)
                    if cards:
                        is_last = len(cards) < page_size
                        total_pages = pg if is_last else pg + 1
                        return cards, total_pages
                except Exception:
                    pass

        # 帧列表
        btn = soup.select_one('[data-key="load-more"][data-load-url*="/frame"]')
        if btn:
            load_url = btn.get("data-load-url")
            if load_url:
                if not load_url.startswith("http"):
                    load_url = urljoin(self.host, load_url)
                page_size = int(btn.get("data-page-size", 20))
                separator = "&" if "?" in load_url else "?"
                ajax_url = f"{load_url}{separator}page={pg}&page_size={page_size}"
                try:
                    resp_html = self._get(ajax_url)
                    frag_soup = BeautifulSoup(resp_html, "lxml")
                    cards = self._parse_frame_cards(frag_soup)
                    if cards:
                        is_last = len(cards) < page_size
                        total_pages = pg if is_last else pg + 1
                        return cards, total_pages
                except Exception:
                    pass

        # 回退
        cards = self._parse_video_cards(soup)
        if cards:
            return cards, 1
        cards = self._parse_frame_cards(soup)
        return cards, 1 if cards else 1

    def _actress_list(self, pg):
        html = self._get(self._paged_url("/actresses", pg))
        soup = BeautifulSoup(html, "lxml")
        out, seen = [], set()
        for a in soup.select('a[href^="/actresses/"]'):
            href = a.get("href")
            if not href or href in seen or href == "/actresses" or "page-" in href:
                continue
            img = a.find("img")
            if not img:
                continue
            name = (img.get("alt") or "").strip()
            if not name:
                continue
            icon_span = a.find("span", class_=re.compile(r"icon-\[lucide--film\]"))
            count_text = ""
            if icon_span:
                parent_flex = icon_span.find_parent("span", class_="flex")
                if parent_flex:
                    count_text = parent_flex.get_text(strip=True) + "部作品"
            out.append(
                {
                    "vod_id": href,
                    "vod_name": name,
                    "vod_pic": "http://127.0.0.1:10079/p/0/127.0.0.1:10172/" + (img.get("src") or "").strip(),
                    "vod_remarks": count_text or "作品集",
                    "vod_tag": "folder",
                    "style": {"type": "rect", "ratio": 1.6},
                }
            )
            seen.add(href)
        return out

    def _topic_list(self, pg):
        html = self._get(self._paged_url("/topics", pg))
        soup = BeautifulSoup(html, "lxml")
        out, seen = [], set()
        for a in soup.select('a[href^="/topics/details/"]'):
            href = a.get("href")
            if not href or href in seen or "page-" in href:
                continue
            seen.add(href)
            img = a.find("img")
            pic = (img.get("src") or "").strip() if img else ""
            title_el = a.find("h3")
            title = title_el.get_text(strip=True) if title_el else ""
            stats_el = a.find("div", class_="flex items-center gap-3 mt-2 text-[11px] text-white/50")
            remarks = ""
            if stats_el:
                parts = stats_el.get_text(" ", strip=True).split()
                for part in parts:
                    if part.isdigit() and len(part) < 5:
                        idx = parts.index(part) + 1
                        if idx < len(parts):
                            unit = parts[idx]
                            if unit in ("影片", "帧"):
                                remarks = f"{part}{unit}"
                                break
                if not remarks:
                    remarks = stats_el.get_text(strip=True)
            out.append(
                {
                    "vod_id": href,
                    "vod_name": title,
                    "vod_pic": f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pic}',
                    "vod_remarks": remarks or "专题",
                    "vod_tag": "folder",
                    "style": {"type": "rect", "ratio": 1.6},
                }
            )
        return out

    def _clickable_list(self, soup, prefix, last_token):
        items, seen = [], set()
        sel = f'a[href^="{prefix}"]'
        for a in soup.select(sel):
            href = a.get("href")
            if not href or href in seen:
                continue
            if prefix == "/actresses/" and href == "/actresses":
                continue
            name = " ".join(a.get_text(" ", strip=True).split())
            if last_token and name:
                name = name.split()[-1]
            if not name:
                continue
            seen.add(href)
            items.append(f'[a=cr:{json.dumps({"id": href, "name": name}, ensure_ascii=False)}/]{name}[/a]')
        return " ".join(items)

    @staticmethod
    def _decode_cover(s):
        if not s or len(s) < 4:
            return ""
        key = int(s[-2:], 16)
        hex_part = s[:-2]
        return "".join(chr(int(hex_part[i : i + 2], 16) ^ key) for i in range(0, len(hex_part), 2))

    @staticmethod
    def _first_text_html(soup, selectors):
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                t = el.get_text(" ", strip=True)
                if t:
                    return t
        return ""