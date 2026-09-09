# -*- coding: utf-8 -*-
# A漫 (aman3.org) 修复版 - 适配漫画图片显示

import sys
import re
import json
import requests
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    def getName(self):
        return "A漫"

    def init(self, extend=""):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        self.host = config.get("site", "https://aman3.org")
        self.plp = config.get("plp", "")
        self.proxy = config.get("proxy", {})
        self.session = requests.Session()

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': self.host + '/',
            'Cookie': 'age_verify=1; popup_agreement=1',
        }
        self.session.headers.update(self.headers)

    def _fetch(self, url):
        try:
            resp = self.session.get(url, timeout=15, allow_redirects=True, proxies=self.proxy)
            resp.encoding = 'utf-8'
            if resp.status_code != 200:
                return ""
            if "网页走丢了" in resp.text or len(resp.text) < 500:
                return ""
            return resp.text
        except:
            return ""

    def _fix_url(self, url):
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return self.host + url
        if not url.startswith("http"):
            return self.host + "/" + url
        return url

    def _clean(self, text):
        if not text:
            return ""
        return re.sub(r'\s+', ' ', text).strip()

    def _parse_items(self, soup):
        """解析列表项 - 修复封面图片获取"""
        videos = []
        items = soup.select('li.hl-list-item')
        for li in items:
            try:
                a = li.find('a', class_='hl-item-thumb')
                if not a:
                    a = li.find('a', href=True)
                if not a:
                    continue
                href = a.get('href')
                if not href or not href.startswith('/manhuaview/'):
                    continue

                # 关键修复：封面图片在 a 标签的 data-original 属性上
                pic = a.get('data-original') or ''
                pic = self._fix_url(pic)

                # 标题
                title_div = li.find('div', class_='hl-item-title')
                title = title_div.find('a').text.strip() if title_div and title_div.find('a') else a.get('title', '')
                title = self._clean(title)

                # 备注
                sub_div = li.find('div', class_='hl-item-sub')
                remark = self._clean(sub_div.text) if sub_div else ''

                videos.append({
                    "vod_id": href,
                    "vod_name": title or "未知",
                    "vod_pic": (self.plp + pic) if pic else "",
                    "vod_remarks": remark
                })
            except:
                continue
        return videos

    def homeContent(self, filter):
        classes = [
            {"type_id": "bookcata/all/ob/time/st/completed", "type_name": "已完结"},
            {"type_id": "bookcata/all/ob/time/st/serialized", "type_name": "更新中"},
            {"type_id": "bookcata/all/ob/time/st/all", "type_name": "全部"},
            {"type_id": "nbook", "type_name": "最新"},
            {"type_id": "booktop", "type_name": "排行"},
        ]
        filters = {
            "bookcata/all/ob/time/st/all": [
                {"key": "category", "name": "分类", "value": [
                    {"n": "全部", "v": "all"},
                    {"n": "韩漫", "v": "韩漫"},
                    {"n": "日漫", "v": "日漫"},
                    {"n": "3D漫画", "v": "3D漫画"},
                    {"n": "美女", "v": "美女"},
                    {"n": "单本", "v": "单本"},
                ]},
                {"key": "status", "name": "进度", "value": [
                    {"n": "全部", "v": "all"},
                    {"n": "已完结", "v": "completed"},
                    {"n": "更新中", "v": "serialized"},
                ]},
                {"key": "sort", "name": "排序", "value": [
                    {"n": "按时间", "v": "time"},
                    {"n": "按阅读", "v": "hits"},
                ]},
            ],
        }
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        html = self._fetch(self.host)
        if not html:
            return {"list": []}
        soup = BeautifulSoup(html, 'html.parser')
        hot_block = soup.select_one('.hl-rb-vod')
        if not hot_block:
            return {"list": []}
        videos = self._parse_items(hot_block)
        return {"list": videos}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if pg else 1
        extend = extend or {}

        if tid.startswith("bookcata"):
            parts = tid.split('/')
            if len(parts) >= 6:
                category = extend.get('category', parts[1])
                sort = extend.get('sort', parts[3])
                status = extend.get('status', parts[5])
                base = f"bookcata/{category}/ob/{sort}/st/{status}"
            else:
                base = tid
            url = f"{self.host}/{base}" + (f"/page/{pg}" if pg > 1 else "")
        elif tid == "nbook":
            url = f"{self.host}/nbook" + (f"?page={pg}" if pg > 1 else "")
        elif tid == "booktop":
            url = f"{self.host}/booktop" + (f"?page={pg}" if pg > 1 else "")
        else:
            url = f"{self.host}/{tid}" + (f"?page={pg}" if pg > 1 else "")

        html = self._fetch(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": 0}

        soup = BeautifulSoup(html, 'html.parser')
        videos = self._parse_items(soup)

        pagecount = 1
        pagination = soup.select('.hl-page-wrap a')
        for a in pagination:
            txt = a.text.strip()
            if txt.isdigit():
                pagecount = max(pagecount, int(txt))

        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": len(videos),
            "total": pagecount * len(videos) if videos else 0
        }

    def detailContent(self, ids):
        detail_path = ids[0]
        url = self._fix_url(detail_path)
        html = self._fetch(url)
        if not html:
            return {"list": []}
        soup = BeautifulSoup(html, 'html.parser')

        # 标题
        title = ""
        h1 = soup.find('h1')
        if h1:
            title = self._clean(h1.text)
        if not title:
            title_tag = soup.find('title')
            if title_tag:
                title = self._clean(title_tag.text).replace(' - A漫-韩漫日漫H漫的天堂', '')

        # 封面（详情页封面在 img 的 data-original）
        pic = ""
        img = soup.find('img', attrs={'data-original': True}) or soup.find('img')
        if img:
            pic = img.get('data-original') or img.get('src')
            pic = self._fix_url(pic)
        pic = (self.plp + pic) if pic else ""

        # 简介
        content = ""
        desc = soup.find('div', class_='hl-desc') or soup.find('div', class_='module-info-introduction-content')
        if desc:
            content = self._clean(desc.text)

        # 章节列表
        play_list = []
        for a in soup.find_all('a', href=True):
            if '/mangaread/' in a['href']:
                href = a['href']
                name = self._clean(a.text) or '阅读'
                full_url = self._fix_url(href)
                play_list.append(f"{name}${self.plp + full_url}")
        if not play_list:
            for a in soup.find_all('a', href=True):
                if '阅读' in a.text or '话' in a.text or '章' in a.text:
                    href = a['href']
                    if href and not href.startswith('#') and not href.startswith('javascript'):
                        full_url = self._fix_url(href)
                        play_list.append(f"{self._clean(a.text)}${self.plp + full_url}")
        if not play_list:
            play_list.append(f"全集${self.plp + url}")

        play_url = "#".join(play_list)

        vod = {
            "vod_id": detail_path,
            "vod_name": title or "未知",
            "vod_pic": pic,
            "vod_content": content,
            "vod_play_from": "A漫",
            "vod_play_url": play_url
        }
        return {"list": [vod]}

    # ========== 关键修复：playerContent 返回 manga:// ==========
    def playerContent(self, flag, id, vipFlags):
        """返回 manga:// 协议"""
        try:
            # id 带 self.plp 前缀，剥掉后抓真实页面
            real_url = id
            if self.plp and id.startswith(self.plp):
                real_url = id[len(self.plp):]
            url = real_url if real_url.startswith("http") else self._fix_url(real_url)
            html = self._fetch(url)
            if not html:
                return {"parse": 1, "url": id, "header": self.headers}

            img_list = []

            # 策略1: data-original
            imgs = re.findall(r'<img[^>]+data-original=["\']([^"\']+)["\']', html)
            for src in imgs:
                if any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                    img_list.append(self._fix_url(src))

            # 策略2: src（过滤占位图）
            if not img_list:
                imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html)
                for src in imgs:
                    if any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                        if 'error.png' not in src and 'logo' not in src and 'loading' not in src:
                            img_list.append(self._fix_url(src))

            # 策略3: 暴力正则
            if len(img_list) < 2:
                pattern = r'(https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|webp|gif|bmp))'
                for match in re.findall(pattern, html, re.I):
                    if any(x in match.lower() for x in ['logo', 'icon', 'load', 'error', 'thumb']):
                        continue
                    if match not in img_list:
                        img_list.append(match)

            # 去重
            seen = set()
            unique = []
            for u in img_list:
                if u not in seen:
                    seen.add(u)
                    unique.append(u)

            if not unique:
                return {"parse": 1, "url": id, "header": self.headers}

            # 关键：每张图加 self.plp 前缀，返回 manga:// 协议
            proxied = [self.plp + u for u in unique]
            return {
                "parse": 0,
                "playUrl": "",
                "url": "manga://" + "&&".join(proxied),
                "header": "",
            }
        except Exception as e:
            return {"parse": 1, "url": id, "header": self.headers}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if pg else 1
        url = f"{self.host}/cata.php?key={key}&page={pg}"
        html = self._fetch(url)
        if not html:
            return {"list": []}
        soup = BeautifulSoup(html, 'html.parser')
        videos = self._parse_items(soup)
        return {"list": videos}

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        if self.session:
            self.session.close()

    def localProxy(self, param):
        return None