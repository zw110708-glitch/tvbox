# coding: utf-8
import re
import json
import requests
from urllib.parse import urljoin, quote, unquote
from bs4 import BeautifulSoup
from base.spider import Spider

class Spider(Spider):

    def getName(self):
        return "xgroovy"

    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        elif isinstance(extend, dict):
            cfg = extend
        self.proxies = cfg.get("proxies") or {}
        self.host = cfg.get("host") or "https://cn.xgroovy.com"
        self.image_proxy_prefix = cfg.get("image_proxy_prefix") or "http://127.0.0.1:10079/p/0/127.0.0.1:10172/"  # 可选图片代理前缀

        self.session = requests.Session()
        if self.proxies:
            self.session.proxies.update(self.proxies)
        self.session.headers.update(self.getHeaders())

    def getHeaders(self):
        return {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
            'Referer': 'https://cn.xgroovy.com/'
        }

    def _fetch_text(self, url):
        resp = self.session.get(url, timeout=10)
        resp.encoding = resp.apparent_encoding or 'utf-8'
        return resp.text

    # =========================================================
    # 1. 顶级分类
    # =========================================================
    def homeContent(self, filter):
        classes = [
            {"type_id": "new", "type_name": "🔥 最新"},
            {"type_id": "best", "type_name": "🏆 最佳影片"},
            {"type_id": "folder::pornstars", "type_name": "💃 模特列表"},
            {"type_id": "folder::categories", "type_name": "📂 视频分类"},
            {"type_id": "folder::tags", "type_name": "🏷️ 标签"}
        ]
        return {'class': classes}

    # 2. 首页推荐
    def homeVideoContent(self):
        html = self._fetch_text("https://cn.xgroovy.com")
        return {'list': self._parse_list(html)}

    # =========================================================
    # 3. 分类/穿透路由
    # =========================================================
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        if tid.startswith("folder::"):
            folder_type = tid.split("::")[1]
            if folder_type == "pornstars":
                url = f"https://cn.xgroovy.com/pornstars/" if pg == 1 else f"https://cn.xgroovy.com/pornstars/{pg}/"
                html = self._fetch_text(url)
                return {
                    'page': pg,
                    'pagecount': 999,
                    'limit': 24,
                    'total': 9999,
                    'list': self._parse_models_folder(html)
                }
            elif folder_type == "categories":
                url = f"https://cn.xgroovy.com/categories/" if pg == 1 else f"https://cn.xgroovy.com/categories/{pg}/"
                html = self._fetch_text(url)
                return {
                    'page': pg,
                    'pagecount': 999,
                    'limit': 100,
                    'total': 9999,
                    'list': self._parse_categories_folder(html)
                }
            elif folder_type == "tags":
                url = f"https://cn.xgroovy.com/tags/" if pg == 1 else f"https://cn.xgroovy.com/tags/{pg}/"
                html = self._fetch_text(url)
                return {
                    'page': pg,
                    'pagecount': 999,
                    'limit': 100,
                    'total': 9999,
                    'list': self._parse_tags_folder(html)
                }

        # 第3层：进入具体视频列表
        cateId = extend.get('cateId', tid)
        clean_cate = cateId.strip('/')
        base_url = clean_cate if clean_cate.startswith('http') else f"https://cn.xgroovy.com/{clean_cate}"
        url = f"{base_url}/" if pg == 1 else f"{base_url}/{pg}/"
        html = self._fetch_text(url)
        video_list = self._parse_list(html)

        # 标签专区兜底搜索
        if not video_list and ("tags" in clean_cate or "tag" in clean_cate):
            tag_keyword = unquote(clean_cate.split('/')[-1])
            search_url = f"https://cn.xgroovy.com/search/{quote(tag_keyword)}/"
            if pg > 1:
                search_url = f"{search_url}{pg}/"
            html = self._fetch_text(search_url)
            video_list = self._parse_list(html)

        return {
            'page': pg,
            'pagecount': 999,
            'limit': 24,
            'total': 9999,
            'list': video_list
        }

    # =========================================================
    # 4. 详情页（含简介和可点击标签）
    # =========================================================
    def detailContent(self, ids):
        vod_id = ids[0]
        url = vod_id if vod_id.startswith('http') else urljoin("https://cn.xgroovy.com", vod_id)
        html = self._fetch_text(url)
        soup = BeautifulSoup(html, 'html.parser')

        # 标题
        title = ""
        title_node = soup.select_one("h1, .title, meta[property='og:title']")
        if title_node:
            title = title_node.get('content', '') or title_node.text.strip()

        # 图片（可选拼接代理前缀）
        pic = ""
        img_node = soup.select_one("video[poster], meta[property='og:image']")
        if img_node:
            pic = img_node.get('poster') or img_node.get('content', '')
            if pic and self.image_proxy_prefix:
                pic = self.image_proxy_prefix + pic

        # 简介和可点击标签
        ogd = soup.select_one('meta[property="og:description"]')
        desc = ogd.get("content", "").strip() if ogd else ""

        tags = []
        ul = soup.select_one("ul.default-list")
        if ul:
            seen = set()
            for a in ul.select("li a[href]"):
                href = a.get("href", "").strip()
                if not href or href in seen:
                    continue
                abs_href = urljoin("https://cn.xgroovy.com", href)
                parts = list(a.stripped_strings)
                if parts and parts[-1].isdigit():
                    parts = parts[:-1]
                name = " ".join([p for p in parts if p]).strip()
                if not name:
                    continue
                tags.append(f'[a=cr:{json.dumps({"id": abs_href, "name": name})}/]{name}[/a]')
                seen.add(href)
                if len(tags) >= 60:
                    break

        content = desc
        if tags:
            content = "标签: " + " ".join(tags) + "\n\n" + content

        vod = {
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": pic,
            "type_name": "视频",
            "vod_year": "",
            "vod_area": "",
            "vod_remarks": "",
            "vod_actor": "",
            "vod_director": "",
            "vod_content": content,
            "vod_play_from": "Xgroovy",
            "vod_play_url": f"在线播放${vod_id}"
        }
        return {"list": [vod]}

    # =========================================================
    # 5. 搜索（修正：增加 pg 参数，支持分页）
    # =========================================================
    def searchContent(self, key, quick, pg="1"):
        pg = int(pg or 1)
        q = quote(str(key).strip())
        if pg == 1:
            url = f"https://cn.xgroovy.com/search/{q}/"
        else:
            url = f"https://cn.xgroovy.com/search/{q}/{pg}/"
        html = self._fetch_text(url)
        video_list = self._parse_list(html)
        return {
            'list': video_list,
            'page': pg,
            'pagecount': 9999
        }

    # =========================================================
    # 6. 播放直链提取
    # =========================================================
    def playerContent(self, flag, id, vipFlags):
        url = id if id.startswith('http') else urljoin("https://cn.xgroovy.com", id)
        html = self._fetch_text(url)
        video_url = ""
        match = re.search(r'(https?://[^\s"\']+\.(?:m3u8|mp4)[^\s"\']*)', html)
        if match:
            video_url = match.group(1)
        if video_url:
            return {
                "parse": 0,
                "url": f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{video_url}',
                "header": self.getHeaders()
            }
        else:
            return {
                "parse": 1,
                "url": url,
                "header": self.getHeaders()
            }

    # =========================================================
    # 以下解析函数保持不变（但图片处已加入代理前缀支持）
    # =========================================================
    def _parse_models_folder(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        folders = []
        items = soup.select(".list-models .item, .list-performers .item, .list-pornstars .item, .item-model")
        if not items:
            items = soup.select("a[href*='/models/'], a[href*='/pornstars/']")
        for item in items:
            a_tag = item if item.name == 'a' else item.select_one("a")
            if not a_tag: continue
            href = a_tag.get('href', '')
            if not href or href.strip('/') in ['models', 'pornstars', 'categories', 'tags', '']:
                continue
            title_tag = item.select_one(".title, .name")
            title = title_tag.text.strip() if title_tag else (a_tag.get('title', '') or a_tag.text.strip())
            img_tag = item.select_one("img")
            pic = ""
            if img_tag:
                pic = img_tag.get('data-src') or img_tag.get('src', '')
                if pic and self.image_proxy_prefix:
                    pic = self.image_proxy_prefix + pic
            count_tag = item.select_one(".videos, .count, .rating")
            remarks = count_tag.text.strip() if count_tag else "模特"
            folders.append({
                "vod_id": href.lstrip('/'),
                "vod_name": title,
                "vod_pic": pic,
                "vod_tag": "folder",
                "vod_remarks": remarks
            })
        return folders

    def _parse_categories_folder(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        folders = []
        items = soup.select(".list-categories .item, a[href*='/categories/']")
        for item in items:
            a_tag = item if item.name == 'a' else item.select_one("a")
            if not a_tag: continue
            href = a_tag.get('href', '')
            if not href or href.strip('/') in ['categories', '']: continue
            title = a_tag.get('title', '') or a_tag.text.strip()
            img_tag = item.select_one("img")
            pic = ""
            if img_tag:
                pic = img_tag.get('data-src') or img_tag.get('src', '')
                if pic and self.image_proxy_prefix:
                    pic = self.image_proxy_prefix + pic
            folders.append({
                "vod_id": href.lstrip('/'),
                "vod_name": title,
                "vod_pic": pic,
                "vod_tag": "folder",
                "vod_remarks": "分类"
            })
        return folders

    def _parse_tags_folder(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        folders = []
        items = soup.select(".list-tags-simple li")
        for item in items:
            a_tag = item.select_one("a")
            if not a_tag: continue
            href = a_tag.get('href', '').strip()
            clean_href = href.strip('/')
            if not clean_href: continue
            span_tag = a_tag.select_one("span")
            remarks = span_tag.text.strip() if span_tag else "标签"
            tag_name = ""
            if a_tag.contents:
                tag_name = str(a_tag.contents[0]).strip()
            if not tag_name:
                tag_name = re.sub(r'\(.*?\)', '', a_tag.text).strip()
            folders.append({
                "vod_id": clean_href,
                "vod_name": tag_name,
                "vod_pic": "",
                "vod_tag": "folder",
                "vod_remarks": remarks
            })
        return folders

    def _parse_list(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        videos = []
        items = soup.select("#list_videos_custom_all_videos_items .item")
        if not items:
            items = soup.select(".list-videos .item, .list-videos:has(img) .item, .item-video")
        for item in items:
            a_tag = item.select_one("a.popito") or item.select_one("a")
            if not a_tag: continue
            href = a_tag.get('href', '')
            if not href or href == '/': continue
            title_tag = item.select_one("strong.title") or item.select_one(".title")
            img_tag = item.select_one("img.thumb") or item.select_one("img")
            title = ""
            if title_tag:
                title = title_tag.text.strip()
            elif img_tag and img_tag.get('alt'):
                title = img_tag.get('alt').strip()
            else:
                title = a_tag.get('title', '').strip() or a_tag.text.strip()
            pic = ""
            if img_tag:
                pic = img_tag.get('data-jpg') or img_tag.get('src') or img_tag.get('data-src') or ""
                if pic.startswith('//'):
                    pic = 'https:' + pic
                if pic and self.image_proxy_prefix:
                    pic = self.image_proxy_prefix + pic
            duration_tag = item.select_one(".duration")
            views_tag = item.select_one(".views")
            duration = duration_tag.text.strip() if duration_tag else ""
            views = views_tag.text.strip() if views_tag else ""
            remarks = f"{duration} {views}".strip()
            videos.append({
                "vod_id": href,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks
            })
        return videos