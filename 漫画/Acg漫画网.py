# -*- coding: utf-8 -*-
# 无聊自制 · ACG漫画网 (完整版)
# 支持: 漫画 / 图集 / 动画 / 全彩 / 写真
# 站点: https://www.acgxmh.com/

import sys
import re
import json
import requests
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    def getName(self):
        return "ACG漫画网"

    def init(self, extend=""):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        self.host = config.get("site", "https://www.acgxmh.com")
        self.plp = config.get("plp", "")
        self.proxy = config.get("proxy", {})
        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.host + "/",
        })
        self.classes = [
            {"type_id": "h", "type_name": "📚 漫画"},
            {"type_id": "hentai", "type_name": "🖼️ 图集"},
            {"type_id": "animation", "type_name": "🎬 动画"},
            {"type_id": "full-color", "type_name": "🎨 全彩"},
            {"type_id": "cos", "type_name": "📸 写真"},
        ]

    def isVideoFormat(self, url):
        return bool(url and re.search(r"\.(m3u8|mp4|ts)(\?|$)", str(url), re.I))

    def manualVideoCheck(self):
        return False

    def _fetch(self, url):
        try:
            r = self.session.get(url, timeout=15, proxies=self.proxy)
            r.encoding = "utf-8"
            return r.text
        except Exception as e:
            print(f"[ACG漫画] 请求失败: {url} -> {e}")
            return ""

    def _fix_url(self, url):
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return self.host + url
        return url

    def _clean(self, text):
        if not text:
            return ""
        return re.sub(r"\s+", " ", text.strip())

    # ---------- 分类 ----------
    def homeContent(self, filter=False):
        return {"class": self.classes}

    def homeVideoContent(self):
        return self.categoryContent("h", "1", False, {})

    # ---------- 分类列表 ----------
    def categoryContent(self, tid, pg, filter=False, extend=None):
        pg = int(pg) if pg else 1
        cat = str(tid)

        if cat == "full-color":
            if pg == 1:
                url = self.host + "/tags/full-color.html"
            else:
                url = self.host + f"/tags/full-color.html?page={pg}"
        else:
            if pg == 1:
                url = self.host + "/" + cat + "/index.html"
            else:
                url = self.host + "/" + cat + f"/index-{pg}.html"

        html = self._fetch(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": 0}

        items = self._parse_list(html)
        pagecount = self._extract_pagecount(html, pg)

        return {
            "list": items,
            "page": pg,
            "pagecount": max(pagecount, pg),
            "limit": len(items) or 20,
            "total": max(pagecount, pg) * (len(items) or 20),
        }

    # ---------- 列表解析：兼容所有分类 ----------
    def _parse_list(self, html):
        videos = []
        seen = set()
        soup = BeautifulSoup(html, "html.parser")

        # 1. 动画分类 (li.grid-item)
        grid_items = soup.select('li.grid-item')
        if grid_items:
            for li in grid_items:
                a_tag = li.find('a', href=True)
                if not a_tag:
                    continue
                href = a_tag.get('href')
                if not href or href in seen:
                    continue
                seen.add(href)

                img = li.find('img', class_='thumb')
                pic = img.get('src') if img else ''
                pic = self._fix_url(pic)

                title_span = li.find('span', class_='title')
                title = ''
                if title_span:
                    a_title = title_span.find('a')
                    if a_title:
                        title = self._clean(a_title.get_text(strip=True))
                if not title:
                    title = a_tag.get('title', '')
                if not title and img:
                    title = img.get('alt', '')
                if not title:
                    title = '未知'

                time_span = li.find('span', class_='time')
                time_text = time_span.get_text(strip=True) if time_span else ''
                media_span = li.find('span', class_='media')
                media_text = media_span.get_text(strip=True) if media_span else ''
                remark = f"{time_text} | {media_text}" if time_text and media_text else time_text or media_text

                videos.append({
                    "vod_id": href,
                    "vod_name": title,
                    "vod_pic": (self.plp + pic) if pic else "",
                    "vod_remarks": remark,
                })
            return videos

        # 2. 漫画/图集/写真/全彩
        items = soup.select('li:has(a.thumb)')
        if not items:
            list_container = soup.find('ul', class_='list') or soup.find('div', class_='list')
            if list_container:
                items = list_container.find_all('li')
            else:
                items = []
                for a in soup.find_all('a', class_='thumb'):
                    parent_li = a.find_parent('li')
                    if parent_li:
                        items.append(parent_li)
                    else:
                        items.append(a)

        for item in items:
            if item.name == 'a' and 'thumb' in item.get('class', []):
                a_thumb = item
            else:
                a_thumb = item.find('a', class_='thumb')
                if not a_thumb:
                    continue

            href = a_thumb.get('href')
            if not href or href in seen:
                continue
            seen.add(href)

            img = a_thumb.find('img')
            pic = img.get('src') if img else ''
            pic = self._fix_url(pic)

            title = ''
            title_span = item.find('span', class_='title') if item.name != 'a' else None
            if title_span:
                a_title = title_span.find('a')
                if a_title:
                    title = self._clean(a_title.get_text(strip=True))
            if not title:
                title = a_thumb.get('title', '')
            if not title and img:
                title = img.get('alt', '')
            if not title:
                title = '未知'

            time_text = ''
            lang_text = ''
            if item.name != 'a':
                time_span = item.find('span', class_='time')
                if time_span:
                    time_text = time_span.get_text(strip=True)
                lang_span = item.find('span', class_='lang')
                if lang_span:
                    lang_text = lang_span.get_text(strip=True)

            remark = f"{time_text} | {lang_text}" if time_text and lang_text else time_text or lang_text

            videos.append({
                "vod_id": href,
                "vod_name": title,
                "vod_pic": (self.plp + pic) if pic else "",
                "vod_remarks": remark,
            })

        return videos

    def _extract_pagecount(self, html, current):
        nums = re.findall(r'<a[^>]+href="[^"]*index-(\d+)\.html"', html)
        if nums:
            return max(int(x) for x in nums)
        nums2 = re.findall(r'[?&]page=(\d+)', html)
        if nums2:
            return max(int(x) for x in nums2)
        if "下一页" in html:
            return current + 1
        return current

    # ---------- 详情：自动识别漫画/视频 ----------
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = ids[0]

        if not vid.startswith("http"):
            base_url = self._fix_url(vid)
        else:
            base_url = vid

        base_url = re.sub(r'-\d+\.html$', '.html', base_url)

        html = self._fetch(base_url)
        if not html:
            return {"list": []}

        soup = BeautifulSoup(html, "html.parser")

        title = ""
        h1 = soup.find("h1", class_="title")
        if h1:
            title = self._clean(h1.get_text(strip=True))
        if not title:
            og_title = soup.find("meta", property="og:title")
            if og_title:
                title = self._clean(og_title.get("content", ""))

        # --- 检测视频 (m3u8) ---
        video_url = None
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    content_url = data.get("contentUrl")
                    if content_url and ".m3u8" in content_url:
                        video_url = content_url
                        break
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            content_url = item.get("contentUrl")
                            if content_url and ".m3u8" in content_url:
                                video_url = content_url
                                break
                    if video_url:
                        break
            except:
                pass

        if not video_url:
            video_tag = soup.find("video")
            if video_tag:
                src = video_tag.get("src")
                if src and ".m3u8" in src:
                    video_url = self._fix_url(src)

        # 如果找到视频地址 → 按视频处理
        if video_url:
            # 获取封面图
            pic = ""
            img = soup.find("img", class_="thumb")
            if img:
                pic = self._fix_url(img.get("src", ""))

            vod = {
                "vod_id": vid,
                "vod_name": title or "未知视频",
                "vod_pic": (self.plp + pic) if pic else "",
                "vod_content": "",
                "vod_play_from": "ACG动画",
                "vod_play_url": "第1集$" + self.plp + video_url,
            }
            return {"list": [vod]}

        # --- 否则按漫画/图集处理（按需加载：图片 URL 连续编号，直接推导，不逐页抓取） ---
        total_pages = 1
        page_div = soup.find("div", class_="page", id="pages")
        if page_div:
            for a in page_div.find_all("a"):
                href = a.get("href", "")
                m = re.search(r'-(\d+)\.html$', href)
                if m:
                    p = int(m.group(1))
                    if p > total_pages:
                        total_pages = p
            for span in page_div.find_all("span"):
                if span.get_text(strip=True).isdigit():
                    p = int(span.get_text(strip=True))
                    if p > total_pages:
                        total_pages = p

        # 只提取第一页图片，拿到首图地址用于推导
        all_images = []
        seen = set()
        self._extract_page_images(html, all_images, seen)

        # 按需加载：图片地址形如 {前缀}_{页码}.{扩展名}，由首图推导出全部地址，避免逐页抓取 HTML
        derived = self._derive_images(all_images[0] if all_images else "", total_pages)
        if derived:
            all_images = derived
        else:
            # 推导失败（非常规编号）时回退为逐页抓取
            for p in range(2, total_pages + 1):
                page_url = re.sub(r'\.html$', f'-{p}.html', base_url)
                page_html = self._fetch(page_url)
                if page_html:
                    self._extract_page_images(page_html, all_images, seen)
                else:
                    break

        pic = all_images[0] if all_images else ""

        if all_images:
            play_url = "manga://" + "&&".join(
                (self.plp + (img if img.startswith(("http://", "https://")) else self._fix_url(img)))
                for img in all_images
            )
        else:
            play_url = base_url

        desc = ""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            desc = self._clean(meta_desc.get("content", ""))

        vod = {
            "vod_id": vid,
            "vod_name": title or "未知漫画",
            "vod_pic": (self.plp + pic) if pic else "",
            "vod_content": desc,
            "vod_play_from": "ACG漫画",
            "vod_play_url": f"全集${play_url}",
        }
        return {"list": [vod]}

    def _extract_page_images(self, html, img_list, seen):
        soup = BeautifulSoup(html, "html.parser")
        for p in soup.find_all("p", class_="manga-picture"):
            img = p.find("img")
            if img:
                src = img.get("src")
                if src:
                    src = self._fix_url(src)
                    if src not in seen:
                        seen.add(src)
                        img_list.append(src)

        if not img_list:
            for img in soup.find_all("img"):
                src = img.get("src")
                if not src:
                    continue
                if "logo" in src or "icon" in src or "button" in src:
                    continue
                src = self._fix_url(src)
                if src not in seen:
                    seen.add(src)
                    img_list.append(src)

    def _derive_images(self, first_img, total_pages):
        """按需加载核心：图片地址为 {前缀}_{页码}.{扩展名} 连续编号，
        由首图地址 + 总页数推导出全部图片地址，无需逐页抓取 HTML。
        推导失败返回 None。"""
        if not first_img or not total_pages or total_pages <= 0:
            return None
        m = re.match(r'^(.*?)_(\d+)\.(\w+)$', first_img)
        if not m:
            return None
        prefix, start, ext = m.group(1), int(m.group(2)), m.group(3)
        if start != 1:
            return None
        return [f"{prefix}_{i}.{ext}" for i in range(1, total_pages + 1)]

    # ---------- 播放：带完整防盗链头 ----------
    def playerContent(self, flag, id, vipFlags=None):
        # 漫画/图片协议
        if id and (id.startswith("manga://") or id.startswith("pics://")):
            return {"parse": 0, "playUrl": "", "url": id, "header": ""}

        # m3u8 视频
        if id and ".m3u8" in id:
            url = id if id.startswith("http") else (self.plp + id)
            return {"parse": 0, "playUrl": "", "url": url, "header": self.headers}

        # 默认 WebView（章节/网页 URL，加 plp 代理转发）
        if id and id.startswith("http"):
            if self.plp and not id.startswith(self.plp):
                id = self.plp + id
        return {"parse": 1, "url": id, "header": self.headers}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=False, pg="1"):
        pg = int(pg) if pg else 1
        enc_key = quote(key)
        url = f"{self.host}/?q={enc_key}"
        if pg > 1:
            url += f"&page={pg}"

        html = self._fetch(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": 0}

        items = self._parse_list(html)
        pagecount = self._extract_pagecount(html, pg)
        return {
            "list": items,
            "page": pg,
            "pagecount": max(pagecount, pg),
            "limit": len(items) or 20,
            "total": max(pagecount, pg) * (len(items) or 20),
        }

    def localProxy(self, param):
        return None