import base64
import json
import re
import sys
from urllib.parse import quote, quote_plus, unquote, unquote_plus, urljoin

import requests
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):

    # ── 分类：ASCII type_id -> (显示名, vc_class) ──
    # vc_class 里逗号表示「主分类,子分类」组合，站点 query 格式支持任意段逗号
    CLASSES = [
        ("japan_hd", "日本HD", "日本HD"),
        ("western_hd", "欧美HD", "欧美HD"),
        ("japan_cen", "日本有碼", "日本,有码"),
        ("japan_uncen", "日本无码", "日本"),
        ("china", "國產原創", "中国"),
        ("western", "歐美风情", "欧美"),
        ("anime", "動畫", "动漫"),
        ("gay", "同性影集", "男同,女同"),
    ]

    # ── 每大类可选的子分类（站点真实 data-classes）──
    FILTER_SUBS = {
        "japan_hd": ["Attackers", "Das", "IdeaPocket", "Madonna", "Moodys", "Premium", "Prestige", "S1", "SOD",
                     "巨乳", "人妻", "美女", "情侣", "少女", "苗條", "美乳", "OL", "癡女", "3P", "群交", "NTR",
                     "BDSM", "出轨", "凌辱", "强奸", "淫乱", "玩具", "调教", "口交", "口爆", "颜射", "中出",
                     "露出", "视角", "自拍", "剧情"],
        "western_hd": ["Blacked", "BlackedRaw", "Brazzers", "Deeper", "Milfy", "Tushy", "Vixen"],
        "japan_cen": ["OL", "美乳", "自拍", "美腿", "口爆", "颜射", "淫乱", "女學生", "素人", "出轨", "情侣", "女佣"],
        "japan_uncen": ["10musume", "CARIBBEANCOM", "HEYZO", "Pacopacomama", "PONDO"],
        "china": ["麻豆傳媒", "大象傳媒", "天美傳媒", "星空無限傳媒", "果凍傳媒", "愛豆傳媒", "91製片廠"],
        "western": ["BlackedRaw", "Vixen", "Tushy", "Brazzers", "Blacked", "Deeper", "Milfy", "MarcDorcel"],
        "anime": ["淫乱", "群交", "巨乳", "OL", "女佣"],
        "gay": ["男同", "女同"],
    }

    SORT_BY = [{"n": "按最新", "v": "time"}, {"n": "按最热", "v": "hits"}, {"n": "按评分", "v": "score"}]

    def init(self, extend=""):
        self.host = "https://motv.app"
        self.lang = "/cn"
        self.cookies = "user_lang=cn; adult_notice_ok=1; user_id=6045; user_name=pd62430; group_id=2; group_name=%E9%BB%98%E8%AE%A4%E4%BC%9A%E5%91%98; user_check=0401f832e5a407f7457ce05eb0c7efa9; user_portrait=%2Fstatic_new%2Fimages%2Ftouxiang.png; PHPSESSID=2a592e7494c476fe3d5a83020415dc41"
        cfg = {}
        if extend:
            try:
                cfg = json.loads(extend) if isinstance(extend, str) else (extend or {})
            except Exception:
                cfg = {}
        self.plp = cfg.get('plp', '')
        self.proxy = cfg.get("proxy", {}) if isinstance(cfg, dict) else {}

        self.ua = "Dalvik/2.1.0 (Linux; U; Android 10; SM-G975F Build/QP1A.190711.020) okhttp/5.0.0"
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": self.ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cookie": self.cookies,
        })
        if self.proxy:
            self.s.proxies.update(self.proxy)

        self.CLASS_VC = {c[0]: c[2] for c in self.CLASSES}

    def getName(self):
        return "MOTV"

    def isVideoFormat(self, url):
        u = url or ""
        return ".m3u8" in u or ".mp4" in u

    def manualVideoCheck(self):
        return True

    def _b64e(self, s: str) -> str:
        return base64.b64encode(s.encode("utf-8")).decode("utf-8")

    def _b64d_url(self, s: str) -> str:
        try:
            u = base64.b64decode(s.encode("utf-8")).decode("utf-8", "ignore")
            return u if u.startswith("http") else ""
        except Exception:
            return ""

    def _abs(self, u: str) -> str:
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        return u if u.startswith("http") else urljoin(self.host + "/", u)

    def _get(self, url: str, *, params=None, headers=None, timeout=10) -> str:
        r = self.s.get(url, params=params, headers=headers, timeout=timeout)
        r.encoding = "utf-8"
        return r.text

    def _soup(self, html: str):
        return BeautifulSoup(html or "", "lxml")

    def _pick_pic(self, node) -> str:
        el = node.select_one("[data-original]")
        if el and el.get("data-original"):
            return el.get("data-original")
        el = node.select_one("img[src]")
        if el and el.get("src"):
            return el.get("src")
        return ""

    # ── 视频列表提取 ──
    def _extract_list(self, soup: BeautifulSoup):
        out = []
        seen = set()
        for it in soup.select(".hl-list-item"):
            if it.find_parent(class_="sidebar"):
                continue
            a = it.select_one("a[href*='/vod/play/']")
            if not a:
                continue
            vod_url = (a.get("href") or "").strip()
            t = it.select_one(".hl-item-title")
            vod_name = (t.get_text(strip=True) if t else (a.get("title") or "")).strip()
            vod_pic = (self._pick_pic(it) or "").strip()
            if not (vod_url and vod_name and vod_pic):
                continue
            vod_url_abs = self._abs(vod_url)
            if vod_url_abs in seen:
                continue
            seen.add(vod_url_abs)
            out.append({
                "vod_id": self._b64e(vod_url_abs),
                "vod_name": vod_name,
                "vod_pic": self.plp + self._abs(vod_pic),
                "vod_remarks": "",
                "style": {"ratio": 1.78, "type": "rect"},
            })
        return out

    # ── 分页总数提取 ──
    def _extract_pagecount(self, soup: BeautifulSoup) -> int:
        try:
            links = soup.select("ul.hl-page-wrap a[href]")
            max_pg = 0
            for a in links:
                m = re.search(r"/page/(\d+)", (a.get("href") or ""))
                if m:
                    max_pg = max(max_pg, int(m.group(1)))
            if max_pg > 0:
                return max_pg
            tips = soup.select_one(".hl-page-tips a, .hl-page-tips")
            if tips:
                m2 = re.search(r"/\s*(\d+)", tips.get_text(strip=True))
                if m2:
                    return int(m2.group(1))
        except Exception:
            pass
        return 9999

    # ── 分类页 tid 解析（支持 query 格式与 vc_class 路径格式） ──
    def _parse_vodclass_tid(self, tid: str) -> str:
        t = (tid or "").strip()
        if "?vc_class=" in t:
            return unquote(t.split("?vc_class=", 1)[1].strip())
        m = re.search(r"/vc_class/([^/]+?)(?:\.html)?$", t)
        if m:
            return unquote(m.group(1))
        return ""

    # ── 统一把 tid 解析成 vc_class（ASCII 短名 或 完整 URL） ──
    def _vc_class_of(self, tid: str) -> str:
        t = str(tid or "").strip().strip("/")
        if t in self.CLASS_VC:
            return self.CLASS_VC[t]
        if "vodclass" in t:
            return self._parse_vodclass_tid(t)
        return ""

    # ── 分类页 URL 构建（query 格式，支持逗号子分类 + 排序 + 分页） ──
    def _build_vodclass_url(self, tid: str, pg: int, extend: dict) -> str:
        ext = extend if isinstance(extend, dict) else {}
        by = ext.get("by") or "time"
        sub = ext.get("class") or ""
        vc = self._vc_class_of(tid)
        full = (vc + "," + sub) if (vc and sub) else (sub or vc)
        q = []
        if full:
            q.append("vc_class=" + quote(full, safe=""))
        q.append("by=" + by)
        q.append("order=desc")
        q.append("page=" + str(int(pg) if pg else 1))
        return self.host + self.lang + "/label/vodclass.html?" + "&".join(q)

    # ── 关键词搜索 URL 构建 ──
    def _build_vodsearch_url(self, href: str, pg: int, name: str = "") -> str:
        kw = ""
        if name:
            kw = quote_plus(str(name))
        else:
            m = re.search(r"/vod/search/(?:page/\d+/)?wd/([^/.]+)", href or "")
            if m:
                kw = m.group(1)
        if not kw:
            return f"{self.host}{self.lang}/vod/search.html"
        if pg <= 1:
            return f"{self.host}{self.lang}/vod/search/wd/{kw}.html"
        return f"{self.host}{self.lang}/vod/search/page/{pg}/wd/{kw}.html"

    # ── 演员搜索 URL 构建 ──
    def _build_actor_search_url(self, tid: str, pg: int) -> str:
        m = re.search(r"/search/actor/([^/]+)", tid or "")
        if not m:
            return ""
        actor = unquote_plus(m.group(1).split(".html")[0])
        actor_enc = quote_plus(actor)
        if pg <= 1:
            return f"{self.host}{self.lang}/vod/search/actor/{actor_enc}.html"
        return f"{self.host}{self.lang}/vod/search/actor/{actor_enc}/page/{pg}.html"

    def buildCategoryUrlTest(self, tid, pg, extend=None):
        pg = int(pg) if pg else 1
        stid = str(tid)
        ext = extend or {}
        if "search/actor" in stid:
            return self._build_actor_search_url(stid, pg)
        if "vodclass" in stid or stid in self.CLASS_VC:
            return self._build_vodclass_url(stid, pg, ext)
        if "search/wd" in stid:
            return self._build_vodsearch_url(stid, pg, (ext.get("name") if isinstance(ext, dict) else ""))
        return ""

    # ── 首页（分类列表 + 最新视频） ──
    def homeContent(self, filter):
        classes = [{"type_name": n, "type_id": i} for i, n, _ in self.CLASSES]
        soup = self._soup(self._get(self.host + self.lang + "/"))
        return {"class": classes, "filters": self.getFilters(), "list": self._extract_list(soup)}

    def homeVideoContent(self):
        return {"list": self.homeContent(None).get("list", [])}

    # ── 筛选器（子分类 + 排序，key 用 ASCII type_id） ──
    def getFilters(self):
        filters = {}
        for tid, _, _ in self.CLASSES:
            subs = self.FILTER_SUBS.get(tid, [])
            val = [{"n": "全部", "v": ""}]
            for s in subs:
                val.append({"n": s, "v": s})
            filters[tid] = [
                {"key": "class", "name": "分类", "value": val},
                {"key": "by", "name": "排序", "value": self.SORT_BY},
            ]
        return filters

    def _category_page(self, url: str, page: int):
        soup = self._soup(self._get(url))
        pc = self._extract_pagecount(soup)
        return {"page": page, "pagecount": pc, "limit": 90, "total": 999999, "list": self._extract_list(soup)}

    # ── 分类页内容（含标签 / 演员 / 关键词搜索） ──
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if pg else 1
        stid = str(tid).strip("/")
        ext = extend or {}

        if "search/actor" in stid:
            return self._category_page(self._build_actor_search_url(stid, pg), pg)
        if "search/wd" in stid:
            name = (ext.get("name") if isinstance(ext, dict) else "")
            return self._category_page(self._build_vodsearch_url(stid, pg, name), pg)
        if "vodclass" in stid or stid in self.CLASS_VC:
            return self._category_page(self._build_vodclass_url(stid, pg, ext), pg)
        return self._category_page(self._abs(stid), pg)

    # ── 搜索 ──
    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if pg else 1
        kw = quote_plus(str(key))
        if pg <= 1:
            url = f"{self.host}{self.lang}/vod/search/wd/{kw}.html"
        else:
            url = f"{self.host}{self.lang}/vod/search/page/{pg}/wd/{kw}.html"
        soup = self._soup(self._get(url))
        pc = self._extract_pagecount(soup)
        return {"list": self._extract_list(soup), "page": pg, "pagecount": pc}

    # ── 详情页 ──
    def detailContent(self, ids):
        detail_url = self._b64d_url(ids[0]) or self._abs(ids[0])
        soup = self._soup(self._get(detail_url))

        title_el = soup.select_one(".hl-infos-title") or soup.select_one("h2") or soup.select_one("h1")
        title = (title_el.get_text(strip=True) if title_el else "").strip()

        # 演员（主演，可点击）
        actors = []
        for a in soup.select("ul.hl-play-meta a[href*='/vod/search/actor/']"):
            name = a.get_text(strip=True)
            href = (a.get("href") or "").strip()
            if name and href:
                actors.append(f"[a=cr:{json.dumps({'id': href, 'name': name}, ensure_ascii=False)}/]{name}[/a]")

        # 标签（可点击）
        tags = []
        tag_container = soup.select_one(".hl-tag-item") or soup
        for a in tag_container.select("a[href*='/vodclass/']"):
            name = a.get_text(strip=True)
            href = (a.get("href") or "").strip()
            if name and href:
                tags.append(f"[a=cr:{json.dumps({'id': href, 'name': name}, ensure_ascii=False)}/]{name}[/a]")

        # 简介
        intro = ""
        blurb = soup.select_one("ul.hl-play-meta li.blurb")
        if blurb:
            intro = blurb.get_text(strip=True).replace("简介：", "", 1).replace("簡介：", "", 1).strip()

        # 单集播放：播放链接即详情页地址
        eps = [f"第1集${self._b64e(detail_url)}"]

        vod = {
            "vod_name": title,
            "vod_actor": " ".join(actors),
            "vod_content": " ".join(tags) + (("\n" + intro) if intro else ""),
            "vod_play_from": "MOTV",
            "vod_play_url": "#".join(eps),
        }
        return {"list": [vod]}

    # ── 播放地址提取（括号计数法处理嵌套 JSON） ──
    def _extract_json_block(self, text: str, start: int) -> str:
        depth = 0
        in_string = False
        escape = False
        i = start
        while i < len(text):
            c = text[i]
            if escape:
                escape = False
            elif c == '\\':
                escape = True
            elif c == '"':
                in_string = not in_string
            elif not in_string:
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        return text[start:i + 1]
            i += 1
        return ""

    def _extract_direct_url(self, html: str) -> str:
        m = re.search(r'var\s+player_[a-zA-Z0-9_]*\s*=\s*', html)
        if m:
            rest = html[m.end():]
            brace_start = rest.find('{')
            if brace_start >= 0:
                block = self._extract_json_block(rest, brace_start)
                if block:
                    try:
                        url = json.loads(block).get("url") or ""
                    except Exception:
                        mu = re.search(r'"url"\s*:\s*"([^"]+)"', block)
                        url = mu.group(1) if mu else ""
                    if url:
                        return self._abs(url.replace("\\/", "/"))
        m2 = re.search(r'https?://[^"\'\s]+\.(?:m3u8|mp4)[^"\'\s]*', html)
        return m2.group(0) if m2 else ""

    def _pick_best_m3u8(self, watch_html: str):
        m3u8s = re.findall(r"['\"]((?:/|\./)?[^'\"]+\.m3u8(?:\?[^'\"]*)?)['\"]", watch_html, re.I)
        if not m3u8s:
            return ""
        for u in m3u8s:
            if "master.m3u8" in u:
                return u
        return m3u8s[0]

    def playerContent(self, flag, id, vipFlags):
        detail_url = self._b64d_url(id) or self._abs(id)
        try:
            html = self._get(detail_url)
        except Exception:
            html = ""

        direct = self._extract_direct_url(html) or detail_url

        if direct and not self.isVideoFormat(direct):
            try:
                watch_html = self._get(direct, headers={"User-Agent": self.ua, "Referer": detail_url})
                rel = self._pick_best_m3u8(watch_html)
                if rel:
                    direct = urljoin(direct, rel)
            except Exception:
                pass

        headers = {"User-Agent": self.ua, "Referer": detail_url, "Origin": self.host}
        return {"parse": 0, "playUrl": "", "url": f'{self.plp}{direct}', "header": headers}
