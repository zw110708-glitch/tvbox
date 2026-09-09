# -*- coding: utf-8 -*-
import sys
import re
import json
import requests
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    """龙禁漫漫画爬虫 - 默影视标准格式"""

    def getName(self):
        return "龙禁漫"

    def init(self, extend=""):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        self.host = config.get("site", "https://long92.org")
        self.plp = config.get("plp", "")
        self.proxy = config.get("proxy", {})
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
            "Referer": self.host + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def _fetch(self, url):
        try:
            r = self.session.get(url, timeout=15, proxies=self.proxy)
            r.encoding = "utf-8"
            return r.text
        except Exception:
            return None

    def _fix_url(self, url):
        if not url:
            return ""
        if url.startswith("http"):
            return url
        if url.startswith("//"):
            return "https:" + url
        return self.host + url

    def _clean(self, text):
        if not text:
            return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&quot;', '"').replace('&#39;', "'")
        return text.strip()

    def homeContent(self, filter):
        return {
            "class": [
                {"type_id": "newbook", "type_name": "最近更新"},
                {"type_id": "bookcata/韩漫/ob/time/st/all", "type_name": "韩漫"},
                {"type_id": "bookcata/日漫/ob/time/st/all", "type_name": "日漫"},
                {"type_id": "bookcata/3D漫画/ob/time/st/all", "type_name": "3D漫画"},
                {"type_id": "bookcata/美女/ob/time/st/all", "type_name": "美女"},
                {"type_id": "bookcata/单本/ob/time/st/all", "type_name": "单本"},
                {"type_id": "bookrank", "type_name": "排行榜"},
            ]
        }

    def homeVideoContent(self):
        return self.categoryContent("newbook", "1", False, None)

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg) if pg else 1
            if tid == "newbook":
                url = self.host + "/newbook"
                if pg > 1:
                    url += "/page/%d" % pg
            elif tid == "bookrank":
                url = self.host + "/bookrank"
                if pg > 1:
                    url += "/page/%d" % pg
            else:
                url = self.host + "/" + tid
                if pg > 1:
                    url += "/page/%d" % pg

            html = self._fetch(url)
            if not html:
                return {"list": []}
            vlist = self._parse_list(html)
            return {"list": vlist, "page": pg, "pagecount": 9999, "limit": 20, "total": 999999}
        except Exception:
            return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        try:
            from urllib.parse import quote
            pg = int(pg) if pg else 1
            url = self.host + "/cata.php?key=" + quote(key)
            if pg > 1:
                url += "&page=%d" % pg
            html = self._fetch(url)
            if not html:
                return {"list": []}
            vlist = self._parse_list(html)
            return {"list": vlist, "page": pg, "pagecount": 9999, "limit": 20, "total": 999999}
        except Exception:
            return {"list": []}

    def detailContent(self, ids):
        try:
            vid = ids[0]
            if not vid.startswith("http"):
                vid = self._fix_url(vid)
            html = self._fetch(vid)
            if not html:
                return {"list": []}

            name = "未知漫画"
            m = re.search(r'<h1[^>]*class=["\'][^"\']*module-info-title[^"\']*["\'][^>]*>(.*?)</h1>', html, re.S)
            if m:
                name = self._clean(m.group(1))
            if name == "未知漫画":
                m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
                if m:
                    name = self._clean(m.group(1))

            author = ""
            m = re.search(r'<div[^>]*class=["\'][^"\']*module-info-item-content[^"\']*["\'][^>]*>(.*?)</div>', html, re.S)
            if m:
                author = self._clean(m.group(1))

            desc = ""
            m = re.search(r'<div[^>]*class=["\'][^"\']*module-info-introduction-content[^"\']*show-desc[^"\']*["\'][^>]*>(.*?)</div>', html, re.S)
            if not m:
                m = re.search(r'<div[^>]*class=["\'][^"\']*module-info-introduction-content[^"\']*["\'][^>]*>(.*?)</div>', html, re.S)
            if m:
                desc = self._clean(m.group(1))

            pic = ""
            m = re.search(r'<div[^>]*class=["\'][^"\']*module-item-cover[^"\']*["\'][^>]*data-original=["\']([^"\']+)["\']', html)
            if not m:
                m = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html)
            if m:
                pic = self._fix_url(m.group(1))
            pic = (self.plp + pic) if pic else ""

            chapters = []
            items = re.findall(r'<a[^>]*class=["\'][^"\']*module-play-list-link[^"\']*["\'][^>]*href=["\']([^"\']+)["\'][^>]*title=["\']([^"\']+)["\']', html, re.S)
            if not items:
                items = re.findall(r'<a[^>]*href=["\'](/manhua/\d+/[^"\']+\.html)["\'][^>]*>(.*?)</a>', html, re.S)
                filtered = []
                for ch_url, ch_title_html in items:
                    ch_title = self._clean(ch_title_html)
                    if ch_title and any(k in ch_title for k in ["章", "话", "第", "卷"]):
                        filtered.append((ch_url, ch_title))
                items = filtered
            if not items:
                items = re.findall(r'<a[^>]*href=["\'](/manhua/\d+/[^"\']+\.html)["\'][^>]*title=["\']([^"\']+)["\']', html, re.S)
            for item in items:
                if len(item) == 2:
                    ch_url, ch_name = item
                    ch_url = self._fix_url(ch_url)
                    ch_name = self._clean(ch_name)
                    if ch_name and ch_url:
                        chapters.append("%s$%s" % (ch_name, self.plp + ch_url))
            chapters.reverse()
            play_url = "#".join(chapters) if chapters else ""

            return {"list": [{
                "vod_id": vid, "vod_name": name, "vod_pic": pic,
                "vod_actor": author, "vod_content": desc,
                "vod_play_from": "龙禁漫", "vod_play_url": play_url,
            }]}
        except Exception:
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        try:
            # 剥掉 self.plp 前缀还原真实 URL
            real_url = id
            if self.plp and id.startswith(self.plp):
                real_url = id[len(self.plp):]
            url = real_url if real_url.startswith("http") else self._fix_url(real_url)

            html = self._fetch(url)
            if not html:
                return {"parse": 1, "url": id, "header": self.headers}

            img_list = []
            imgs = re.findall(r'<img[^>]*data-src=["\']([^"\']+)["\']', html)
            if imgs:
                for src in imgs:
                    if any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                        img_list.append(self._fix_url(src))
            if not img_list:
                imgs = re.findall(r'<img[^>]*data-original=["\']([^"\']+)["\']', html)
                for src in imgs:
                    if any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                        img_list.append(self._fix_url(src))
            if not img_list:
                imgs = re.findall(r'<img[^>]*src=["\']([^"\']+)["\']', html)
                for src in imgs:
                    if any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                        if 'error.png' not in src and 'logo' not in src and '/imgs/' not in src:
                            img_list.append(self._fix_url(src))

            seen = set()
            unique = []
            for img in img_list:
                if img not in seen:
                    seen.add(img)
                    unique.append(img)

            if not unique:
                return {"parse": 1, "url": id, "header": self.headers}

            # 每张图加 self.plp 前缀，返回 manga:// 协议
            proxied = [self.plp + img for img in unique]
            return {
                "parse": 0, "playUrl": "",
                "url": "manga://" + "&&".join(proxied),
                "header": "",
            }
        except Exception:
            return {"parse": 1, "url": id, "header": self.headers}

    def localProxy(self, param):
        return None

    def _parse_list(self, html):
        vlist = []
        if not html or len(html) < 100:
            return vlist
        pattern = r'<a[^>]*class=["\'][^"\']*module-poster-item[^"\']*["\'][^>]*href=["\']([^"\']+)["\'][^>]*title=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
        items = re.findall(pattern, html, re.S | re.I)
        if not items:
            pattern = r'<a[^>]*href=["\'](/manhua/\d+\.html)["\'][^>]*title=["\']([^"\']+)["\'][^>]*class=["\'][^"\']*module-item[^"\']*["\'][^>]*>(.*?)</a>'
            items = re.findall(pattern, html, re.S | re.I)
        for item in items:
            if len(item) != 3:
                continue
            href, title, content = item
            link = self._fix_url(href)
            pic = ""
            m = re.search(r'data-original=["\']([^"\']+)["\']', content)
            if m:
                pic = self._fix_url(m.group(1))
            if not pic:
                m = re.search(r'src=["\']([^"\']+)["\']', content)
                if m:
                    src = m.group(1)
                    if 'error.png' not in src:
                        pic = self._fix_url(src)
            note = ""
            m = re.search(r'<div[^>]*class=["\'][^"\']*module-item-note[^"\']*["\'][^>]*>(.*?)</div>', content, re.S)
            if m:
                note = self._clean(m.group(1))
            vlist.append({
                "vod_id": link, "vod_name": title.strip(),
                "vod_pic": (self.plp + pic) if pic else "",
                "vod_remarks": note,
            })
        return vlist
