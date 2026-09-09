# -*- coding: utf-8 -*-
# Hanime1 Spider (refactor 2026-04-26)
# - proxies: self.proxy = cfg.get("proxy") or {}
# - removed all danmaku related code
# - auto-select best Hanime1 domain (like jable.py)

import json
import re
import time
import html as html_parser
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urljoin, urlparse, unquote

import base64
import requests

import sys
sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    _BEST = None
    _POOL = None

    # 导航站（与 jable 同款）
    NAV = ("https://x99dh.cc", "https://x99dh.one","https://x97.icu", "https://x97.one")

    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def getName(self):
        return "Hanime"

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # -------------------- init / config --------------------
    def init(self, extend=""):
        # TVBox 常见情况：源只 init 一次。
        # 代理未启动时如果这里直接 raise，TVBox 可能把源判死。
        # 因此改为：init 不强依赖拿到 site；后续每次请求前按需刷新。
        try:
            cfg = json.loads(extend) if isinstance(extend, str) else (extend or {})
        except Exception:
            cfg = {}

        # 1) 代理转发：严格按 jable 的格式
        self.plp = cfg.get('plp', '')
        self.proxy = cfg.get("proxy") or {}

        # 2) 站点延迟初始化
        self.site = ""
        self.enter = ""

        # 3) headers 先给最小集，等 site 可用后再补 Referer/Origin
        self.headers = {
            "User-Agent": self.UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
        }

        # 站点内置分类（用于判断 tid 属于分类还是标签）
        self.genres = {
            '裏番', '泡麵番', 'Motion Anime', '3DCG', '2.5D', '2D動畫', 'AI生成', 'MMD', 'Cosplay'
        }
        self.rank_tids = {'latest', 'daily_rank', 'weekly_rank', 'monthly_rank'}

        # 统一 requests 会话（便于 cookie/连接复用）
        self.session = requests.Session()

        # 尝试刷新一次（不保证成功，失败也不抛异常）
        self._ensure_site()

    def _apply_site(self, site: str) -> bool:
        site = (site or '').rstrip('/')
        if not site:
            return False
        self.site = site
        self.enter = f"{self.site}/enter"

        # headers 必须与自动选择域名匹配（Referer/Origin 跟随自动域名）
        self.headers["Referer"] = f"{self.enter}/"
        self.headers["Origin"] = self.site

        # 预热：访问 /enter 让 cookie/年龄确认生效
        try:
            self.session.get(
                self.enter,
                headers={"User-Agent": self.UA, "Referer": f"{self.site}/", "Origin": self.site},
                proxies=self.proxy,
                timeout=10,
                allow_redirects=True,
            )
        except Exception:
            pass

        return True

    def _ensure_site(self) -> bool:
        """确保 site 可用：每次需要时都尝试重新获取（不缓存）。"""
        h = (self._best_host() or "").rstrip('/')
        if not h:
            return False
        if h != getattr(self, 'site', ''):
            print(f"[Spider] 使用站点: {h}")
        return self._apply_site(h)

    def _site(self) -> str:
        """获取当前 site（必要时自动刷新）。"""
        if not getattr(self, 'site', ''):
            self._ensure_site()
        return self.site

    def getheaders(self, param=None):
        return self.headers

    # -------------------- http helpers --------------------
    def _abs(self, u: str) -> str:
        u = (u or '').strip()
        if u.startswith('http'):
            return u
        # 相对链接需要 site；每次用到时都允许刷新（不缓存）
        base = self._site()
        return urljoin((base or '').rstrip('/') + '/', u) if base else u

    def _origin_from(self, u: str) -> str:
        """取链接的 scheme://netloc，用于播放请求的 Origin/Referer 跟随直链域名。"""
        try:
            p = urlparse((u or '').strip())
            if p.scheme and p.netloc:
                return f"{p.scheme}://{p.netloc}"
        except Exception:
            pass
        return (self.site or '').rstrip('/')

    def _get(self, url: str, timeout: float = 12.0, headers=None, **kwargs) -> requests.Response:
        # 确保 site 已就绪（用于 Referer/Origin/cookie）
        if not getattr(self, 'site', ''):
            self._ensure_site()
        h = headers or self.headers
        return self.session.get(
            url,
            headers=h,
            proxies=self.proxy,
            timeout=timeout,
            allow_redirects=True,
            **kwargs,
        )

    # -------------------- best host (Hanime1) --------------------
    def _norm_host(self, u: str) -> str:
        u = (u or '').strip().rstrip('/')
        if not u:
            return ""
        if not u.startswith('http'):
            u = 'https://' + u.lstrip('/')
        p = urlparse(u)
        path = (p.path or '').rstrip('/')
        if path.endswith('/enter'):
            path = path[:-6]
        return (p.scheme + '://' + p.netloc + path).rstrip('/')

    def _parse_pool(self, html: str):
        # 导航页里以 const encodedData = 'base64...' 方式携带站点列表
        m = re.search(r"const\s+encodedData\s*=\s*'([^']+)'", html or "")
        if not m:
            return []
        try:
            data = json.loads(unquote(base64.b64decode(m.group(1)).decode('utf-8', 'ignore')))
        except Exception:
            return []

        for it in data if isinstance(data, list) else []:
            if (it.get('name') or '').strip() != 'Hanime1':
                continue
            out = []
            for u in it.get('urls') or []:
                host = self._norm_host(u.get('url'))
                test = (u.get('testUrl') or '').strip()
                if host and test:
                    out.append({'host': host, 'test': test})
            return out
        return []

    def _fetch_pool(self):
        # 不缓存：每次都重新从 NAV 拉取解析
        headers = {"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache", "Pragma": "no-cache"}
        pool = []
        for nav in self.NAV:
            try:
                r = requests.get(nav, headers=headers, proxies=self.proxy, timeout=10, allow_redirects=True)
                pool = self._parse_pool(r.text or "")
                if pool:
                    break
            except Exception:
                pass

        seen, out = set(), []
        for it in pool:
            h = it.get('host')
            if h and h not in seen:
                seen.add(h)
                out.append(it)
        return out

    def _probe(self, url: str, timeout: float):
        t0 = time.time()
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, proxies=self.proxy, timeout=timeout)
        if r.status_code != 200 or (r.text or '').strip().lower() != 'ok':
            return None
        return time.time() - t0

    def _best_host(self):
        # 不缓存：每次都重新探测选择
        pool = self._fetch_pool()
        if not pool:
            return None
        threshold, timeout = 2.5, 3.0
        best_h, best_t = None, 1e9
        workers = min(12, max(4, len(pool)))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(self._probe, it['test'], timeout): it['host'] for it in pool}
            for fut in as_completed(futs):
                try:
                    t = fut.result()
                except Exception:
                    continue
                if t is None:
                    continue
                h = futs[fut]
                if t < best_t:
                    best_h, best_t = h, t
                if t <= threshold:
                    best_h = h
                    break
        return best_h

    # -------------------- business logic --------------------
    def isVideoFormat(self, url):
        return any(ext in (url or '') for ext in ['.m3u8', '.mp4', '.ts'])

    def homeContent(self, filter):
        classes = [
            {'type_name': '最新上市', 'type_id': 'latest'},
            {'type_name': '裏番', 'type_id': '裏番'},
            {'type_name': '泡麵番', 'type_id': '泡麵番'},
            {'type_name': 'Motion Anime', 'type_id': 'Motion Anime'},
            {'type_name': '3DCG', 'type_id': '3DCG'},
            {'type_name': '2.5D', 'type_id': '2.5D'},
            {'type_name': '2D動畫', 'type_id': '2D動畫'},
            {'type_name': 'AI生成', 'type_id': 'AI生成'},
            {'type_name': 'MMD', 'type_id': 'MMD'},
            {'type_name': 'Cosplay', 'type_id': 'Cosplay'},
            {'type_name': '本日排行', 'type_id': 'daily_rank'},
            {'type_name': '本週排行', 'type_id': 'weekly_rank'},
            {'type_name': '本月排行', 'type_id': 'monthly_rank'},
        ]

        sort_filters = [
            {"n": "最新上市", "v": "最新上市"},
            {"n": "本日排行", "v": "本日排行"},
            {"n": "本週排行", "v": "本週排行"},
            {"n": "本月排行", "v": "本月排行"},
            {"n": "人氣爆棚", "v": "人氣爆棚"},
        ]
        date_filters = [
            {"n": "全部時間", "v": ""},
            {"n": "24小時", "v": "24"},
            {"n": "2天", "v": "2"},
            {"n": "1週", "v": "7"},
            {"n": "1月", "v": "30"},
            {"n": "3月", "v": "90"},
        ]
        duration_filters = [
            {"n": "全部時長", "v": ""},
            {"n": "1分鐘", "v": "1"},
            {"n": "5分鐘", "v": "5"},
            {"n": "10分鐘", "v": "10"},
            {"n": "20分鐘", "v": "20"},
            {"n": "30分鐘", "v": "30"},
            {"n": "60+分鐘", "v": "60"},
            {"n": "0-10分鐘", "v": "0-10"},
            {"n": "0-20分鐘", "v": "0-20"},
        ]

        filters = {}
        for item in classes:
            filters[item['type_id']] = [
                {"key": "sort", "name": "排序", "value": sort_filters},
                {"key": "date", "name": "時間", "value": date_filters},
                {"key": "duration", "name": "時長", "value": duration_filters},
            ]
        return {'class': classes, 'filters': filters}

    def homeVideoContent(self):
        try:
            url = f"{self._site()}/search?sort=最新上市"
            html = self._get(url, headers=self.getheaders()).text
            vods = self.parse_vod_list(html)
            return {'list': vods}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg)
        sort = (extend or {}).get('sort', '')
        date = (extend or {}).get('date', '')
        duration = (extend or {}).get('duration', '')

        valid_dates = {"": "", "24": "24", "2": "2", "7": "7", "30": "30", "90": "90"}
        valid_durations = {"": "", "1": "1", "5": "5", "10": "10", "20": "20", "30": "30", "60": "60", "0-10": "0-10", "0-20": "0-20"}
        date = valid_dates.get(date, "")
        duration = valid_durations.get(duration, "")

        if tid == 'latest':
            url = f"{self._site()}/search?sort=最新上市&page={page}"
        elif tid == 'daily_rank':
            url = f"{self._site()}/search?sort=本日排行&page={page}"
        elif tid == 'weekly_rank':
            url = f"{self._site()}/search?sort=本週排行&page={page}"
        elif tid == 'monthly_rank':
            url = f"{self._site()}/search?sort=本月排行&page={page}"
        elif tid in self.genres:
            param_list = [f"genre={quote(tid)}", f"page={page}"]
            if sort:
                param_list.append(f"sort={quote(sort)}")
            url = f"{self._site()}/search?" + "&".join(param_list)
        else:
            param_list = [f"page={page}", f"tags[]={quote(tid)}"]
            if sort:
                param_list.append(f"sort={quote(sort)}")
            if date:
                param_list.append(f"date={date}")
            if duration:
                param_list.append(f"duration={duration}")
            url = f"{self._site()}/search?" + "&".join(param_list)

        try:
            html = self._get(url, headers=self.getheaders()).text
            vods = self.parse_vod_list(html)
            return {
                'list': vods,
                'page': page,
                'pagecount': page + 1 if len(vods) > 0 else page,
                'limit': 30,
                'total': 9999,
            }
        except Exception:
            return {'list': []}

    def detailContent(self, ids):
        vid = ids[0]
        url = f"{self._site()}/watch?v={vid}"

        try:
            html = self._get(url, headers=self.getheaders()).text

            title_match = re.search(r'<meta property="og:title" content="(.*?)"', html)
            title = title_match.group(1) if title_match else vid

            pic_match = re.search(r'<meta property="og:image" content="(.*?)"', html)
            pic = pic_match.group(1) if pic_match else ""

            desc_match = re.search(r'<meta property="og:description" content="(.*?)"', html)
            desc = desc_match.group(1) if desc_match else ""

            vod_tag_list = []
            rich_tags = []

            description_match = re.search(
                r'<div class="video-caption-text caption-ellipsis"[^>]*>(.*?)</div>',
                html,
                re.DOTALL,
            )
            if description_match:
                description_text = description_match.group(1).strip()
                description_text = re.sub(r'<[^>]+>', '', description_text)
                desc = description_text

            tags_section_match = re.search(
                r'<div[^>]*class="video-details-wrapper video-tags-wrapper"[^>]*>(.*?)</div>\s*<div',
                html,
                re.DOTALL,
            )
            if not tags_section_match:
                tags_section_match = re.search(r'<div[^>]*video-tags-wrapper[^>]*>(.*?)</div>\s*<div', html, re.DOTALL)
            if tags_section_match:
                tags_section = tags_section_match.group(1)
                tag_matches = re.findall(
                    r'<div[^>]*class="single-video-tag"[^>]*>.*?<a[^>]*>(.*?)</a>.*?</div>',
                    tags_section,
                    re.DOTALL,
                )
                for tag_html in tag_matches:
                    if not tag_html:
                        continue
                    clean_tag = html_parser.unescape(str(tag_html))
                    clean_tag = re.sub(r'<[^>]+>', '', clean_tag)
                    clean_tag = re.sub(r'\s*\(\d+\)\s*$', '', clean_tag)
                    if clean_tag.startswith('#') or clean_tag.startswith('#&nbsp;'):
                        clean_tag = clean_tag.replace('#', '').replace('#&nbsp;', '')
                    clean_tag = clean_tag.replace('&nbsp;', ' ').strip()
                    clean_tag = re.sub(r'\s+', ' ', clean_tag).strip()
                    if clean_tag and clean_tag not in vod_tag_list:
                        vod_tag_list.append(clean_tag)

            if not vod_tag_list:
                keywords_match = re.search(r'<meta name="keywords" content="(.*?)"', html)
                if keywords_match:
                    keywords = html_parser.unescape(keywords_match.group(1))
                    tags = re.split(r'[,、，]', keywords)
                    for tag in tags:
                        tag = tag.strip()
                        if tag and tag not in vod_tag_list and tag != 'Hanime1':
                            vod_tag_list.append(tag)

            if not vod_tag_list:
                all_tags = re.findall(r'href="/search\?tags%5B%5D=([^&\"]+)', html)
                for tag in all_tags:
                    tag = html_parser.unescape(tag)
                    if tag and tag not in vod_tag_list:
                        vod_tag_list.append(tag)

            if len(vod_tag_list) < 5 and desc:
                words = re.findall(r'[a-zA-Z0-9\u4e00-\u9fff]{2,}', desc)
                for word in words[:10]:
                    if len(word) > 1 and word not in vod_tag_list:
                        vod_tag_list.append(word)

            seen_tags = set()
            for tag in vod_tag_list:
                if tag and tag not in seen_tags:
                    seen_tags.add(tag)
                    target = json.dumps({'id': tag, 'name': tag}, ensure_ascii=False)
                    rich_tags.append(f'[a=cr:{target}/]{tag}[/a]')

            vod_tag_str = ",".join(vod_tag_list)
            vod_content = f"🏷️ 标签: {' '.join(rich_tags)}\n\n{desc}" if rich_tags else desc

            # 提取视频源（只保留最高画质单线路）
            sources = re.findall(r'<source[^>]+src="([^"]+)"', html) or re.findall(r'src="([^"]+\.mp4[^"]*)"', html)
            sources = [html_parser.unescape(s).replace('&amp;', '&') for s in sources]

            best_url = ""
            # 优先级：4K > 2K > 1080p > 720p > 480p > 其它
            for key in ('4k', '2160'):
                best_url = next((u for u in sources if key in u.lower() or key in u), "")
                if best_url:
                    break
            if not best_url:
                for key in ('2k', '1440'):
                    best_url = next((u for u in sources if key in u.lower() or key in u), "")
                    if best_url:
                        break
            if not best_url:
                best_url = next((u for u in sources if '1080' in u), "")
            if not best_url:
                best_url = next((u for u in sources if '720' in u), "")
            if not best_url:
                best_url = next((u for u in sources if '480' in u), "")
            if not best_url and sources:
                best_url = sources[0]

            if not best_url:
                m3u8_match = re.search(r"source\s*=\s*['\"](https?://[^'\"]+\.m3u8[^'\"]*)['\"]", html)
                if m3u8_match:
                    best_url = m3u8_match.group(1).replace('&amp;', '&')

            if not best_url:
                best_url = url

            # 仅保留单线路：让 playerContent 拿到的 id 就是直链 URL
            # 注意：框架通常要求 "剧集名$链接" 格式，这里剧集名固定为“播放”，不会污染真实 URL
            vod_play_url = f"播放${best_url}"

            vod = {
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": self._abs(pic),
                "type_name": "",
                "vod_year": "",
                "vod_area": "",
                "vod_remarks": "",
                "vod_actor": "",
                "vod_director": "",
                "vod_content": vod_content,
                "vod_tag": vod_tag_str,
                "vod_play_from": "直链",
                "vod_play_url": vod_play_url,
            }
            return {'list': [vod]}
        except Exception as e:
            print(f"Error in detailContent: {e}")
            return {'list': []}

    def searchContent(self, key, quick, pg="1", extend=None):
        page = int(pg)
        base_url = f"{self._site()}/search?"
        param_list = [f"page={page}"]
        if key:
            param_list.append(f"query={quote(key)}")

        extend = extend or {}
        tags = extend.get("tags", [])
        if isinstance(tags, list) and tags:
            for t in tags:
                param_list.append(f"tags[]={quote(t)}")

        sort = extend.get("sort", "")
        if sort:
            param_list.append(f"sort={quote(sort)}")

        date = extend.get("date", "")
        date_map = {"": "", "24": "24", "2": "2", "7": "7", "30": "30", "90": "90"}
        if date in date_map and date_map[date] != "":
            param_list.append(f"date={date_map[date]}")

        duration = extend.get("duration", "")
        duration_map = {"": "", "1": "1", "5": "5", "10": "10", "20": "20", "30": "30", "60": "60"}
        if duration in duration_map and duration_map[duration] != "":
            param_list.append(f"duration={duration_map[duration]}")

        genre = extend.get("genre", "")
        if genre:
            param_list.append(f"genre={quote(genre)}")

        url = base_url + "&".join(param_list)
        try:
            html = self._get(url, headers=self.getheaders()).text
            vods = self.parse_vod_list(html)
            return {'list': vods, 'page': page}
        except Exception:
            return {'list': [], 'page': page}

    def playerContent(self, flag, id, vipFlags):
        url = (id or '').strip()
        if not url:
            return {'parse': 1, 'url': '', 'header': {}}

        # 兼容：壳把清晰度/剧集名等前缀一起传进来（如 "播放$https://..." / "1080p$https://..."）
        if '$' in url and not url.startswith('http'):
            url = url.split('$')[-1].strip()

        # 关键修复：播放直链的域名可能与 self.site 不同（例如直链在 hanime365.top）
        # 这里让 Origin/Referer 跟随直链域名，否则服务器可能 403/无法播放
        origin = self._origin_from(url)
        header = {
            'User-Agent': self.UA,
            'Origin': origin,
            'Referer': origin + '/',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
        }

        if self.isVideoFormat(url):
            return {'parse': 0, 'url': f'{self.plp}{url}', 'header': header}
        return {'parse': 1, 'url': f'{self.plp}{url}', 'header': header}

    def parse_vod_list(self, html):
        vods = []
        seen = set()

        for m in re.finditer(r'href="[^"]*watch\?v=(\d+)"', html or ''):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)

            start = max(0, m.start() - 600)
            end = min(len(html), m.end() + 1200)
            block = (html or '')[start:end]

            title = vid
            t_attr = re.search(r'title="([^"]+)"', block)
            if t_attr:
                title = t_attr.group(1)
            else:
                t_match = re.search(r'class="[^\"]*(card-mobile-title|video-card-title|title)[^\"]*"[^>]*>(.*?)</div>', block, re.S)
                if t_match:
                    title = re.sub(r'<[^>]+>', '', t_match.group(2)).strip() or title

            pic = ""
            img_match = re.search(r'<img[^>]+class="[^"]*(main-thumb|thumbnail)[^"]*"[^>]+src="([^"]+)"', block)
            if img_match:
                pic = img_match.group(2)
            else:
                any_img = re.search(r'<img[^>]+src="([^"]+)"', block)
                if any_img:
                    pic = any_img.group(1)

            remarks = ""
            dur_match = re.search(r'class="[^\"]*duration[^\"]*"[^>]*>\s*([^<]+)\s*<', block)
            if dur_match:
                remarks = dur_match.group(1).strip()

            vods.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": self._abs(pic),
                "vod_remarks": remarks,
            })

        return vods
