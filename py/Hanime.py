# -*- coding: utf-8 -*-
# by @嗷呜 & Perplexity (Updated 2026-01-15 分类页&解析修复 v2)
import json
import sys
import threading
import requests
import os
import re
import time
import random
import html as html_parser
from urllib.parse import quote, unquote

sys.path.append('..')
from base.spider import Spider

class Spider(Spider):

    def init(self, extend=""):
        # 使用主域，避免Referer/Origin与站点期望不一致触发反爬
        self.host = "https://hanime1.me"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': f'{self.host}/',
            'Origin': self.host,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cache-Control': 'no-cache'
        }
        # 站点内置分类（用于判断 tid 属于分类还是标签）
        self.genres = {
            '裏番','泡麵番','Motion Anime','3DCG','2.5D','2D動畫','AI生成','MMD','Cosplay'
        }
        self.rank_tids = {'latest','daily_rank','weekly_rank','monthly_rank'}
        # 全局代理设置
        self.proxies = {
            "http": "http://127.0.0.1:10172",
            "https": "http://127.0.0.1:10172"
        }
        os.environ['HTTP_PROXY'] = self.proxies['http']
        os.environ['HTTPS_PROXY'] = self.proxies['https']
        os.environ['http_proxy'] = self.proxies['http']
        os.environ['https_proxy'] = self.proxies['https']
        # 统一 requests 会话
        self.session = requests.Session()
        self.session.proxies.update(self.proxies)
        self.session.trust_env = True

    def getName(self):
        return "Hanime"

    def isVideoFormat(self, url):
        return any(ext in (url or '') for ext in ['.m3u8', '.mp4', '.ts'])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

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
            {'type_name': '本月排行', 'type_id': 'monthly_rank'}
        ]
        sort_filters = [
            {"n": "最新上市", "v": "最新上市"},
            {"n": "本日排行", "v": "本日排行"},
            {"n": "本週排行", "v": "本週排行"},
            {"n": "本月排行", "v": "本月排行"},
            {"n": "人氣爆棚", "v": "人氣爆棚"}
        ]
        date_filters = [
            {"n": "全部時間", "v": ""},
            {"n": "24小時", "v": "24"},
            {"n": "2天", "v": "2"},
            {"n": "1週", "v": "7"},
            {"n": "1月", "v": "30"},
            {"n": "3月", "v": "90"}
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
            {"n": "0-20分鐘", "v": "0-20"}
        ]
        filters = {}
        for item in classes:
            filters[item['type_id']] = [
                {"key": "sort", "name": "排序", "value": sort_filters},
                {"key": "date", "name": "時間", "value": date_filters},
                {"key": "duration", "name": "時長", "value": duration_filters}
            ]
        return {'class': classes, 'filters': filters}

    def homeVideoContent(self):
        try:
            url = f"{self.host}/search?sort=最新上市"
            content = self.fetch(url, headers=self.getheaders()).text
            vods = self.parse_vod_list(content)
            return {'list': vods}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg)
        sort = extend.get('sort', '')
        date = extend.get('date', '')
        duration = extend.get('duration', '')

        # 参数映射，严格对应网页支持值
        valid_dates = {"": "", "24": "24", "2": "2", "7": "7", "30": "30", "90": "90"}
        valid_durations = {"": "", "1": "1", "5": "5", "10": "10", "20": "20", "30": "30", "60": "60", "0-10": "0-10", "0-20": "0-20"}

        date = valid_dates.get(date, "")
        duration = valid_durations.get(duration, "")

        if tid == 'latest':
            url = f"{self.host}/search?sort=最新上市&page={page}"
        elif tid == 'daily_rank':
            url = f"{self.host}/search?sort=本日排行&page={page}"
        elif tid == 'weekly_rank':
            url = f"{self.host}/search?sort=本週排行&page={page}"
        elif tid == 'monthly_rank':
            url = f"{self.host}/search?sort=本月排行&page={page}"
        elif tid in self.genres:
            # 分类：使用 genre=
            param_list = [f"genre={quote(tid)}", f"page={page}"]
            if sort:
                param_list.append(f"sort={quote(sort)}")
            # 分类不拼 date/duration，保持站点行为一致
            url = f"{self.host}/search?" + "&".join(param_list)
        else:
            # 标签：使用 tags[]= 并支持 date/duration/sort
            param_list = [f"page={page}"]
            param_list.append(f"tags[]={quote(tid)}")
            if sort:
                param_list.append(f"sort={quote(sort)}")
            if date:
                param_list.append(f"date={date}")
            if duration:
                # 对标签检索也允许时长过滤
                # 站点支持的 duration 值已在上方映射
                param_list.append(f"duration={duration}")
            url = f"{self.host}/search?" + "&".join(param_list)

        try:
            content = self.fetch(url, headers=self.getheaders()).text
            vods = self.parse_vod_list(content)
            return {
                'list': vods,
                'page': page,
                'pagecount': page + 1 if len(vods) > 0 else page,
                'limit': 30,
                'total': 9999
            }
        except Exception:
            return {'list': []}

    def detailContent(self, ids):
        vid = ids[0]
        url = f"{self.host}/watch?v={vid}"

        try:
            html = self.fetch(url, headers=self.getheaders()).text

            title_match = re.search(r'<meta property="og:title" content="(.*?)"', html)
            title = title_match.group(1) if title_match else vid

            pic_match = re.search(r'<meta property="og:image" content="(.*?)"', html)
            pic = pic_match.group(1) if pic_match else ""

            desc_match = re.search(r'<meta property="og:description" content="(.*?)"', html)
            desc = desc_match.group(1) if desc_match else ""

            vod_tag_list = []
            rich_tags = []

            # 简介（如果存在）
            description_match = re.search(r'<div class="video-caption-text caption-ellipsis"[^>]*>(.*?)</div>', html, re.DOTALL)
            if description_match:
                description_text = description_match.group(1).strip()
                description_text = re.sub(r'<[^>]+>', '', description_text)
                desc = description_text

            # 标签区域
            tags_section_match = re.search(r'<div[^>]*class="video-details-wrapper video-tags-wrapper"[^>]*>(.*?)</div>\s*<div', html, re.DOTALL)
            if not tags_section_match:
                tags_section_match = re.search(r'<div[^>]*video-tags-wrapper[^>]*>(.*?)</div>\s*<div', html, re.DOTALL)
            if tags_section_match:
                tags_section = tags_section_match.group(1)
                tag_matches = re.findall(r'<div[^>]*class="single-video-tag"[^>]*>.*?<a[^>]*>(.*?)</a>.*?</div>', tags_section, re.DOTALL)
                for tag_html in tag_matches:
                    if tag_html:
                        clean_tag = str(tag_html)
                        clean_tag = html_parser.unescape(clean_tag)
                        clean_tag = re.sub(r'<[^>]+>', '', clean_tag)
                        clean_tag = re.sub(r'\s*\(\d+\)\s*$', '', clean_tag)
                        if clean_tag.startswith('#') or clean_tag.startswith('#&nbsp;'):
                            clean_tag = clean_tag.replace('#', '').replace('#&nbsp;', '')
                        clean_tag = clean_tag.replace('&nbsp;', ' ').strip()
                        clean_tag = re.sub(r'\s+', ' ', clean_tag).strip()
                        if clean_tag and re.search(r'[^\s]', clean_tag) and clean_tag not in vod_tag_list:
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
                all_tags = re.findall(r'href="/search\?tags%5B%5D=([^&"]+)', html)
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

            # 提取视频源
            sources = re.findall(r'<source[^>]+src="([^"]+)"', html)
            if not sources:
                sources = re.findall(r'src="([^"]+\.mp4[^"]*)"', html)
            decoded_sources = [html_parser.unescape(s).replace('&amp;', '&') for s in sources]

            quality_map = {}
            for s in decoded_sources:
                if '4k' in s.lower() or '2160' in s:
                    quality_map.setdefault('4K', []).append(s)
                elif '2k' in s.lower() or '1440' in s:
                    quality_map.setdefault('2K', []).append(s)
                elif '1080' in s:
                    quality_map.setdefault('1080p', []).append(s)
                elif '720' in s:
                    quality_map.setdefault('720p', []).append(s)
                elif '480' in s:
                    quality_map.setdefault('480p', []).append(s)
                else:
                    quality_map.setdefault('标清', []).append(s)

            quality_order = ['4K', '2K', '1080p', '720p', '480p', '标清']
            play_parts = []
            for q in quality_order:
                if q in quality_map and quality_map[q]:
                    best_url = quality_map[q][0]
                    play_url_with_dm = f"{vid}_dm_{best_url}"
                    play_parts.append(f"{q}${play_url_with_dm}")

            if not play_parts:
                m3u8_match = re.search(r'source\s*=\s*[\'\"](https?://[^\'\"]+\.m3u8[^\'\"]*)[\'\"]', html)
                if m3u8_match:
                    best_url = m3u8_match.group(1).replace('&amp;', '&')
                    play_url_with_dm = f"{vid}_dm_{best_url}"
                    play_parts.append(f"自动${play_url_with_dm}")

            if not play_parts:
                play_parts.append(f"网页播放${url}")

            line_name = "书生玩剣"
            vod_play_url = f"{line_name}$" + "#".join(play_parts)

            vod = {
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pic}',
                "type_name": "",
                "vod_year": "",
                "vod_area": "",
                "vod_remarks": "",
                "vod_actor": "",
                "vod_director": "",
                "vod_content": vod_content,
                "vod_tag": vod_tag_str,
                "vod_play_from": line_name,
                "vod_play_url": vod_play_url
            }
            return {'list': [vod]}
        except Exception as e:
            print(f"Error in detailContent: {e}")
            return {'list': []}

    def searchContent(self, key, quick, pg="1", extend=None):
        page = int(pg)
        base_url = f"{self.host}/search?"
        param_list = [f"page={page}"]
        if key:
            param_list.append(f"query={quote(key)}")
        if extend:
            tags = extend.get("tags", [])
            if isinstance(tags, list) and tags:
                for t in tags:
                    param_list.append(f"tags[]={quote(t)}")
            sort = extend.get("sort", "")
            if sort:
                param_list.append(f"sort={quote(sort)}")
            date = extend.get("date", "")
            date_map = {"": "", "24": "24", "2": "2", "7": "7", "30": "30", "90": "90"}
            if date and date in date_map:
                param_list.append(f"date={date_map[date]}")
            duration = extend.get("duration", "")
            duration_map = {"": "", "1": "1", "5": "5", "10": "10", "20": "20", "30": "30", "60": "60"}
            if duration and duration in duration_map:
                param_list.append(f"duration={duration_map[duration]}")
            genre = extend.get("genre", "")
            if genre:
                # 支持按分类检索
                param_list.append(f"genre={quote(genre)}")

        url = base_url + "&".join(param_list)
        try:
            html = self.fetch(url, headers=self.getheaders()).text
            vods = self.parse_vod_list(html)
            return {'list': vods, 'page': page}
        except Exception:
            return {'list': [], 'page': page}

    def playerContent(self, flag, id, vipFlags):
        header = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': f'{self.host}/',
            'Origin': self.host
        }
        if '_dm_' in id:
            vid, url = id.split('_dm_', 1)
            threading.Thread(target=self._preload_danmaku, args=(vid, url)).start()
        else:
            url = id

        if '.mp4' in url or '.m3u8' in url:
            return {'parse': 0, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{url}', 'header': header}
        return {'parse': 1, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{url}', 'header': header}

    def parse_vod_list(self, html):
        vods = []
        seen = set()

        # 新策略：以 watch?v=ID 为核心，向前后窗口提取标题/缩略图/时长
        for m in re.finditer(r'href="[^"]*watch\?v=(\d+)"', html):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)

            start = max(0, m.start() - 600)
            end = min(len(html), m.end() + 1200)
            block = html[start:end]

            # 标题：优先 title 属性；其次常见标题容器
            title = vid
            t_attr = re.search(r'title="([^"]+)"', block)
            if t_attr:
                title = t_attr.group(1)
            else:
                t_match = re.search(r'class="[^\"]*(card-mobile-title|video-card-title|title)[^\"]*"[^>]*>(.*?)</div>', block, re.S)
                if t_match:
                    title = re.sub(r'<[^>]+>', '', t_match.group(2)).strip() or title

            # 缩略图：优先 main-thumb/thumbnail
            pic = ""
            img_match = re.search(r'<img[^>]+class="[^"]*(main-thumb|thumbnail)[^"]*"[^>]+src="([^"]+)"', block)
            if img_match:
                pic = img_match.group(2)
            else:
                any_img = re.search(r'<img[^>]+src="([^"]+)"', block)
                if any_img:
                    pic = any_img.group(1)

            # 时长（备注）
            remarks = ""
            dur_match = re.search(r'class="[^\"]*duration[^\"]*"[^>]*>\s*([^<]+)\s*<', block)
            if dur_match:
                remarks = dur_match.group(1).strip()

            vods.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks
            })

        return vods

    # 弹幕处理保持不变
    def localProxy(self, param):
        try:
            xtype = param.get('type', '')
            if xtype == 'hlxdm':
                vid = param.get('path', '')
                times = int(param.get('times', 0))
                comments = self._fetch_comments(vid)
                return self._generate_danmaku_xml(comments, times)
            return [404, 'text/plain', b'']
        except Exception:
            return [500, 'text/plain', b'']

    def _fetch_comments(self, vid):
        comments = []
        try:
            url = f"{self.host}/loadComment?id={vid}&type=video&content=comment-tablink"
            res = self.session.get(url, headers=self.getheaders(), timeout=5)
            data = res.json()
            comments_html = data.get('comments', '')
            if not comments_html:
                return ["欢迎观看", "Hanime1"]

            comment_blocks = re.findall(
                r'<div[^>]*class="comment-index-text"[^>]*>(?:[^<]|<[^>]*>)*?</div>\s*<div[^>]*class="comment-index-text"[^>]*>(.*?)</div>',
                comments_html, re.S
            )
            for block in comment_blocks:
                text = re.sub(r'<[^>]+>', '', block).strip()
                if len(text) > 2 and len(text) < 100 and not any(x in text for x in ['加载中', '查看', '回复', '登录', '发表']):
                    comments.append(text)
            seen = set()
            clean_comments = []
            for c in comments:
                if c not in seen and len(clean_comments) < 60:
                    seen.add(c)
                    clean_comments.append(c)
            return clean_comments if clean_comments else ["欢迎观看", "精彩内容"]
        except Exception:
            return ["欢迎观看", "Hanime1"]

    def _generate_danmaku_xml(self, comments, duration):
        if duration <= 0:
            duration = 600
        xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<i>']
        xml.append('<d p="0,5,25,16711680,0">弹幕加载成功</d>')
        if not comments:
            xml.extend([
                '<d p="5,1,25,16777215,0">暂无评论，欢迎补充~</d>',
                '<d p="15,1,25,16777215,0">Hanime1 高清无码</d>'
            ])
        else:
            for i, c in enumerate(comments):
                progress = i / len(comments)
                base_time = progress * duration
                t = round(max(1, min(base_time + random.uniform(-5, 5), duration - 1)), 1)
                color = 16777215
                if random.random() < 0.15:
                    color = random.randint(0x666666, 0xFFFFFF)
                safe_text = html_parser.escape(c)
                xml.append(f'<d p="{t},1,25,{color},0">{safe_text}</d>')
        xml.append('</i>')
        return [200, 'text/xml', '\n'.join(xml)]

    def _preload_danmaku(self, vid, url):
        try:
            time.sleep(1)
            dm_url = f"{self.getProxyUrl()}&path={vid}&times=600&type=hlxdm"
            self.session.get(f"http://127.0.0.1:9978/action?do=refresh&type=danmaku&path={quote(dm_url)}", timeout=2)
        except:
            pass

    def getheaders(self, param=None):
        return self.headers
