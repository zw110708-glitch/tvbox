# -*- coding: utf-8 -*-
# Taiav 直链版 Spider：基于页面/接口提取 m3u8/mp4，避免嗅探（修正版）
import json
import re
from urllib.parse import urljoin, urlparse

import requests
from pyquery import PyQuery as pq

# 保留原有基类引入（按你的工程结构）
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def init(self, extend=""):
        try:
            cfg = json.loads(extend) if isinstance(extend, str) else extend or {}
            self.proxies = cfg.get('proxies', {
                "http": "http://127.0.0.1:10172",
                "https": "http://127.0.0.1:10172"})
            self.host = (cfg.get('host', '') or '').strip() or 'https://taiav.com'
        except Exception:
            self.proxies = {
                "http": "http://127.0.0.1:10172",
                "https": "http://127.0.0.1:10172"}
            self.host = 'https://taiav.com'

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Upgrade-Insecure-Requests': '1',
            'Origin': self.host,
            'Referer': f"{self.host}/",
        }
        print(f"[Spider] 使用站点: {self.host}")

    def getName(self):
        return "Taiav"

    def isVideoFormat(self, url):
        return any(ext in (url or '').lower() for ext in ['.m3u8', '.mp4', '.ts', '.flv', '.mkv', '.avi', '.webm'])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # -------------------- 简易 fetch 封装 --------------------
    def fetch(self, url, timeout=10):
        resp = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=timeout)
        resp.encoding = resp.apparent_encoding
        return resp.text

    # -------------------- 首页 --------------------
    def homeContent(self, filter):
        try:
            classes = [
                {'type_name': '热门视频', 'type_id': '/hots'},
                {'type_name': '随机', 'type_id': '/random'},
                {'type_name': '大分类', 'type_id': '/discover?tab=category'},
                {'type_name': '热门标签', 'type_id': '/discover?tab=tags'},
                {'type_name': '网红主播', 'type_id': '/cn/category/网红主播'},
                {'type_name': '有码', 'type_id': '/cn/category/有码'},
                {'type_name': '无码', 'type_id': '/cn/category/无码'},
            ]

            resp = requests.get(self.host, headers=self.headers, proxies=self.proxies, timeout=10)
            if resp.status_code != 200:
                return {'class': classes, 'filters': {}, 'list': []}

            resp.encoding = resp.apparent_encoding
            doc = self.getpq(resp.text)

            videos = self._parse_cards(doc)
            return {'class': classes, 'filters': {}, 'list': videos}
        except Exception as e:
            print(f"[homeContent] Error: {e}")
            return {'class': [], 'filters': {}, 'list': []}

    # -------------------- 分类列表 --------------------
    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg) if pg else 1

            if '@folder' in tid:
                base_url = tid.replace('@folder', '')
                page = int(pg) if pg else 1
                v, pagecount = self.getfod(base_url, page)
                return {'list': v, 'page': page, 'pagecount': pagecount, 'limit': 90, 'total': 999999}

            if tid.startswith('/discover') or tid.startswith(f'{self.host}/discover'):
                discover_url = f"{self.host}/discover"
                resp = requests.get(discover_url, headers=self.headers, proxies=self.proxies, timeout=10)
                if resp.status_code != 200:
                    return {'list': [], 'page': 1, 'pagecount': 1, 'limit': 90, 'total': 0}
                resp.encoding = resp.apparent_encoding
                doc = self.getpq(resp.text)

                parsed = urlparse(tid if tid.startswith('http') else f"{self.host}{tid}")
                q = dict([kv if len(kv)==2 else (kv[0], '') for kv in [s.split('=') for s in (parsed.query or '').split('&') if s]])
                tab = (q.get('tab', '') or '').lower()
                print(f"[categoryContent] discover tab={tab}")

                if tab == 'category':
                    cards = self._parse_discover_category_cards(doc)
                else:
                    cards = self._parse_discover_tag_cards(doc)

                return {'list': cards, 'page': 1, 'pagecount': 1, 'limit': 90, 'total': len(cards)}

            url = tid if tid.startswith('http') else f"{self.host}{tid if tid.startswith('/') else '/' + tid}"
            url = url.rstrip('/')
            real_url = url
            if pg > 1:
                sep = '?' if '?' not in real_url else '&'
                real_url = f"{real_url}{sep}page={pg}"

            if isinstance(extend, dict) and extend:
                params = []
                for key in ['class', 'area', 'year', 'lang', 'letter', 'by']:
                    if extend.get(key):
                        params.append(f"{key}={extend[key]}")
                if params:
                    sep = '&' if '?' in real_url else '?'
                    real_url = real_url + sep + '&'.join(params)

            print(f"[categoryContent] 请求URL: {real_url}")
            resp = requests.get(real_url, headers=self.headers, proxies=self.proxies, timeout=10)
            if resp.status_code != 200:
                return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 90, 'total': 0}

            resp.encoding = resp.apparent_encoding
            doc = self.getpq(resp.text)

            videos = self._parse_cards(doc)
            videos = self._filter_ads(videos)

            pagecount = self._parse_pagecount(doc)
            return {'list': videos, 'page': pg, 'pagecount': pagecount, 'limit': 90, 'total': 999999}
        except Exception as e:
            print(f"[categoryContent] Error: {e}")
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 90, 'total': 0}

    # -------------------- 详情页（直链提取 + 标签写入） --------------------
    def detailContent(self, ids):
        try:
            page_url = ids[0] if str(ids[0]).startswith('http') else f"{self.host}{ids[0]}"
            resp = requests.get(page_url, headers=self.headers, proxies=self.proxies, timeout=10)
            resp.encoding = resp.apparent_encoding
            html = resp.text
            doc = self.getpq(html)

            # 标题获取（保留原有思路）
            vod_title = (doc('h1').text() or
                         doc('.post-title, .module-info-heading, .video-title').text() or
                         (doc('title').text() or '').split('|')[0].strip())
            # JSON-LD 补充标题（保留）
            try:
                ld_json = doc('script[type="application/ld+json"]').text()
                if ld_json:
                    obj = json.loads(ld_json)
                    if isinstance(obj, dict) and obj.get('@type') == 'VideoObject':
                        vod_title = obj.get('name') or vod_title
            except Exception:
                pass

            # 直链提取（保留）
            video_url = self._extract_direct_video_url(page_url, html, doc)
            if video_url:
                play_url = f"直链${video_url}"
            else:
                # 回退：仍用页面 URL 播放（不解析）（保留）
                play_url = f"正片${page_url}"

            # —— 标签提取与写入（修正版） ——
            vod = {
                'vod_play_from': 'Taiav',
                'vod_play_url': play_url,
                # 'vod_name': vod_title,  # 如上层需要可启用
            }

            tags = []
            # 锚定“视频简介”标题（多语言可选：Description/Synopsis）
            sec = doc('h3:contains("视频简介"), h3:contains("Description"), h3:contains("Synopsis")').eq(0)
            panel = sec.next('.primary-background') if sec else doc('.primary-background').eq(0)

            for a in panel('a[href^="/cn/tag/"]').items():
                name = (a.text() or '').strip()
                href = a.attr('href') or ''
                if not name or not href:
                    continue
                full = href if href.startswith('http') else urljoin(self.host, href)
                tag_payload = {'id': full + '@folder', 'name': name}
                tags.append(f"[a=cr:{json.dumps(tag_payload, ensure_ascii=False)}/]{name}[/a]")

            vod['vod_content'] = ' '.join(tags) if tags else ''

            return {'list': [vod]}
        except Exception as e:
            print(f"[detailContent] Error: {e}")
            return {'list': [{'vod_play_from': 'Taiav', 'vod_play_url': '获取失败', 'vod_content': ''}]}

    # -------------------- 搜索 --------------------
    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg) if pg else 1
            url = f"{self.host}/cn/search?q={key}"
            resp = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=10)
            resp.encoding = resp.apparent_encoding
            doc = self.getpq(resp.text)
            videos = self._parse_cards(doc)
            videos = self._filter_ads(videos)
            return {'list': videos, 'page': pg, 'pagecount': self._parse_pagecount(doc)}
        except Exception as e:
            print(f"[searchContent] Error: {e}")
            return {'list': [], 'page': pg, 'pagecount': 1}

    # -------------------- 播放器 --------------------
    def playerContent(self, flag, id, vipFlags):
        # id 即为直链 URL（来自 detailContent 的 vod_play_url），无需解析
        parse = 0
        # 补充必要头部，避免直链跨域限制
        headers = dict(self.headers)
        headers['Referer'] = self.host
        headers['Origin'] = self.host
        return {'parse': parse, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{id}', 'header': headers}

    # -------------------- 直链提取核心 --------------------
    def _extract_direct_video_url(self, page_url, html, doc):
        vid = None
        # a) 从 URL 提取：/movie/<id>
        try:
            m = re.search(r"/movie/([A-Za-z0-9]+)", page_url)
            if m:
                vid = m.group(1)
        except Exception:
            pass
        # b) 从 HTML 中变量提取：var id = "..."
        if not vid:
            try:
                m = re.search(r'var\s+id\s*=\s*"([^"]+)"', html)
                if m:
                    vid = m.group(1)
            except Exception:
                pass
        # 2) 首选接口 /api/getmovie?type=1280&id=<id>
        if vid:
            api = urljoin(self.host, f"/api/getmovie?type=1280&id={vid}")
            try:
                r = requests.get(api, headers=self.headers, proxies=self.proxies, timeout=10)
                if r.status_code == 200:
                    j = r.json()
                    m3u8 = (j.get('m3u8') or '').strip()
                    if m3u8:
                        # 某些环境下返回相对路径，做补全
                        if not m3u8.startswith('http'):
                            m3u8 = urljoin(self.host, m3u8)
                        return m3u8
            except Exception as e:
                print(f"[_extract_direct_video_url] api error: {e}")
        # 3) 从 script 正则提取（回退）
        try:
            # 常见模式：m3u8 = "..." 或 clappr source: "source": "...m3u8"
            patterns = [
                r"m3u8\s*[:=]\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]",
                r"source" + r"\s*:\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]",
                r"url" + r"\s*:\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]",
                r"src" + r"\s*[:=]\s*['\"]([^'\"]+\.mp4[^'\"]*)['\"]",
            ]
            for pat in patterns:
                m = re.search(pat, html, flags=re.IGNORECASE)
                if m:
                    u = m.group(1)
                    if not u.startswith('http'):
                        u = urljoin(self.host, u)
                    return u
        except Exception:
            pass
        # 4) video/source 直链
        try:
            src = (doc('video').attr('src') or '')
            if not src:
                src = (doc('video source').attr('src') or '')
            if src:
                if not src.startswith('http'):
                    src = urljoin(self.host, src)
                return src
        except Exception:
            pass
        return None

    # -------------------- 工具方法：解析 discover 卡片 --------------------
    def _parse_discover_category_cards(self, doc):
        cards = []
        sec = doc('h3:contains("大分类")').eq(0)
        grid = sec.next('div[uk-grid]') if sec else None
        if not grid:
            grid = doc('div[uk-grid]').eq(0)
        for a in grid('a[href]').items():
            href = a.attr('href') or ''
            name = a.text().strip()
            if not href or not name:
                continue
            if '/cn/category/' not in href:
                continue
            if not href.startswith('http'):
                href = urljoin(self.host, href)
            cards.append({
                'vod_id': href + '@folder',
                'vod_name': name,
                'vod_pic': '',
                'vod_remarks': '',
                'style': {"type": "rect", "ratio": 1.33},
                'vod_tag': 'folder'
            })
        print(f"[_parse_discover_category_cards] 提取到 {len(cards)} 个分类卡片")
        return cards

    def _parse_discover_tag_cards(self, doc):
        cards = []
        sections = []
        for h in doc('h3').items():
            title = h.text().strip()
            if not title or title == '大分类':
                continue
            sections.append(h)
        for h in sections:
            grid = h.next('div[uk-grid]')
            for a in grid('a[href]').items():
                href = a.attr('href') or ''
                name = a.text().strip()
                if not href or not name:
                    continue
                if '/cn/tag/' not in href:
                    continue
                if href.endswith('/cn/tag/'):
                    continue
                if not href.startswith('http'):
                    href = urljoin(self.host, href)
                cards.append({
                    'vod_id': href + '@folder',
                    'vod_name': name,
                    'vod_pic': '',
                    'vod_remarks': '',
                    'style': {"type": "rect", "ratio": 1.33},
                    'vod_tag': 'folder'
                })
        uniq = {}
        for v in cards:
            uniq[v['vod_id']] = v
        cards = list(uniq.values())
        print(f"[_parse_discover_tag_cards] 提取到 {len(cards)} 个标签卡片")
        return cards

    # -------------------- 工具方法：解析卡片 --------------------
    def _parse_cards(self, doc):
        videos = []
        cards = doc('.movie-card')
        print(f"[_parse_cards] 找到 {len(cards)} 个 .movie-card")
        seen = set()

        for card in cards.items():
            a = card('.uk-card-media-top a').eq(0)
            href = a.attr('href') or ''
            if not href or href in ['#', '/']:
                continue
            if not href.startswith('http'):
                href = urljoin(self.host, href)

            if href in seen:
                continue
            seen.add(href)

            title = card('.uk-card-body h5').text().strip()
            if not title:
                title = a.attr('title') or a.find('img').attr('alt') or a.text().strip()
            if not title or len(title) < 2:
                continue

            img = card('.uk-card-media-top img').attr('src') or ''
            if img and not img.startswith('http'):
                img = urljoin(self.host, img)
            if img.lower().endswith('.gif'):
                img = ''

            remark = card('.video-box-info .uk-tag').text().strip()
            videos.append({
                'vod_id': href,
                'vod_name': title,
                'vod_pic': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{img}',
                'vod_remarks': remark,
                'style': {"type": "rect", "ratio": 1.33}
            })
        return videos

    # -------------------- 工具方法：过滤广告 --------------------
    def _filter_ads(self, videos):
        blocked_hosts = [
            'enter.javhd.com', 'javhd.com', 'javhd', 'mavrtracktor', 'adxadserv', 'jads.co',
            'porn', 'adservice', 'ads.', '/ad/', '#ad'
        ]
        blocked_titles = [
            'AI脱衣换脸', '脫衣秀聊天室', 'Porn Dude', '廣告', '[廣告]', '广告', '[广告]',
            'JAV HD', 'JAVHD', 'jav hd', 'javhd'
        ]
        res = []
        for v in videos:
            href = (v.get('vod_id', '') or '').lower()
            name = (v.get('vod_name', '') or '').lower()
            remark = (v.get('vod_remarks', '') or '').lower()
            if any(b.lower() in href for b in blocked_hosts):
                continue
            if any(bt.lower() in name for bt in blocked_titles):
                continue
            if any(bt.lower() in remark for bt in blocked_titles):
                continue
            res.append(v)
        print(f"[_filter_ads] 过滤后剩余 {len(res)} / {len(videos)}")
        return res

    # -------------------- 工具方法：分页 --------------------
    def _parse_pagecount(self, doc):
        pagecount = 1
        try:
            pager = doc('.uk-pagination, .pagination')
            if not pager:
                return pagecount
            last_a = None
            for a in pager('a').items():
                last_a = a
            if last_a is not None:
                href = last_a.attr('href') or ''
                m = re.search(r'page=(\d+)', href)
                if m:
                    pagecount = int(m.group(1))
                else:
                    txt = last_a.text().strip()
                    if txt.isdigit():
                        pagecount = int(txt)
        except Exception:
            pass
        return pagecount

    # -------------------- 文件夹列表解析 --------------------
    def getfod(self, url, pg=1):
        try:
            if not url.startswith('http'):
                url = urljoin(self.host, url)
            real_url = url.rstrip('/')
            if pg and int(pg) > 1:
                sep = '?' if '?' not in real_url else '&'
                real_url = f"{real_url}{sep}page={int(pg)}"
            resp = requests.get(real_url, headers=self.headers, proxies=self.proxies, timeout=10)
            if resp.status_code != 200:
                return [], 1
            resp.encoding = resp.apparent_encoding
            doc = self.getpq(resp.text)
            videos = self._parse_cards(doc)
            videos = self._filter_ads(videos)
            pagecount = self._parse_pagecount(doc)
            return videos, pagecount
        except Exception as e:
            print(f"[getfod] Error: {e}")
            return [], 1

    # -------------------- pq 包装 --------------------
    def getpq(self, data):
        try:
            return pq(data)
        except Exception:
            return pq(data.encode('utf-8'))
