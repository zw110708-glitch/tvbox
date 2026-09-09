# -*- coding: utf-8 -*-
import re
import json
import requests
from html import unescape
from urllib.parse import urlsplit
from base.spider import Spider

class Spider(Spider):
    def __init__(self):
        self.name = 'Bad.news'
        self.host = 'https://bad.news'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36',
            'Referer': self.host + '/',
            'Origin': self.host,
            'Accept-Language': 'zh-CN,zh;q=0.9'
        }
        self.proxies = {}  # 代理配置
        self.proxy_prefix = 'http://127.0.0.1:10079/p/0/127.0.0.1:10172/'  # 封面代理前缀

    def getName(self):
        return self.name

    def init(self, extend=""):
        # 代理配置解析（与hohoj相同）
        self.proxies = json.loads(extend).get('proxy', {}) if extend else {}

    def fetch(self, url, headers=None, params=None):
        # 实现与hohoj相同的fetch方法
        try:
            if headers is None:
                headers = self.headers
            return requests.get(
                url, 
                headers=headers, 
                params=params, 
                proxies=self.proxies, 
                timeout=10
            ).text
        except:
            return ''

    # =========================
    # 首页分类
    # =========================
    def homeContent(self, filter):
        return {
            'class': [
                {'type_id': '/', 'type_name': '首页'},
                {'type_id': '/tag/porn', 'type_name': '短视频'},
                {'type_id': '/tag/long-porn', 'type_name': '长视频'},
                {'type_id': '/av/release', 'type_name': '新品上市'},
                {'type_id': '/av/tag/中文字幕', 'type_name': '中字'},
                {'type_id': '/av/uncensored/type-uncensored-leak', 'type_name': '无码流出'},
                {'type_id': '/av/uncensored/type-tokyohot', 'type_name': '东京热'},
                {'type_id': '/av/uncensored/type-1pondo', 'type_name': '一本道'}
            ]
        }

    def homeVideoContent(self):
        return self.categoryContent('', '1', False, {})

    # =========================
    # 列表解析（修改后）
    # =========================
    def parse_list(self, html):
        videos = []
        black_list = ['热点', '招聘', '20k', '工作制', '双休', '远程', '月薪']

        def _norm_path(path: str) -> str:
            """统一 href 形式，避免同一视频因 URL 形式差异而重复"""
            if not path:
                return ''

            # 1) 反转义 + 去空白/多余内容
            path = unescape(path).strip()
            path = path.split()[0]

            # 2) 绝对链接统一转成站内 path
            if path.startswith('http://') or path.startswith('https://'):
                u = urlsplit(path)
                path = u.path

            # 3) 去掉 query / fragment
            path = path.split('?', 1)[0].split('#', 1)[0].strip()

            if not path:
                return ''

            # 3.1) 统一 AV 播放页与详情页（同一视频避免重复）
            # 例如：/av/play/abc 与 /av/abc 实际是同一条
            if path.startswith('/av/play/'):
                path = '/av/' + path[len('/av/play/'):]
                path = path.strip()
            if not path.startswith('/'):
                path = '/' + path

            # 4) 去掉尾部 /
            if len(path) > 1:
                path = path.rstrip('/')

            return path

        def _norm_title(t: str) -> str:
            if not t:
                return ''
            t = unescape(t)
            t = re.sub(r'\s+', ' ', t).strip()

            # 常见分隔符：只取主标题（避免把统计/标签拼进来）
            for sep in ['｜', '|', ' - ', ' – ', ' — ', '·', '•']:
                if sep in t:
                    t = t.split(sep, 1)[0].strip()

            # 去掉常见尾随"数据/时长/日期"等噪音
            t = re.sub(r'\s*(?:\d+[KkMm]?\s*)?(?:views?|观看|次观看|播放)\b.*$', '', t, flags=re.I)
            t = re.sub(r'\s*\b\d{1,2}:\d{2}(?::\d{2})?\b.*$', '', t)  # 01:23 或 01:23:45
            t = re.sub(r'\s*\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b.*$', '', t)  # 2026-01-30
            t = re.sub(r'\s*[（($$]\s*\d+\s*[）)$$]\s*$', '', t)  # (123)

            return t.strip()

        def _extract_time(block: str) -> str:
            """从HTML块中提取时间信息"""
            # 尝试第一种时间格式
            time_match = re.search(
                r'<div class="video-list-content-item-pic">.*?<span class="video-list-content-item-pic-time"[^>]*>([^<]+)</span>',
                block, re.S
            )
            if time_match:
                return time_match.group(1).strip()
            
            # 尝试第二种时间格式
            time_match = re.search(
                r'<div class="ct-time">\s*<span[^>]*>([^<]+)</span>',
                block, re.S
            )
            if time_match:
                return time_match.group(1).strip()
            
            return ''

        def _add(path, title, pic='', time=''):
            if not path or not title:
                return
            title = _norm_title(title)
            if (not title) or any(word in title for word in black_list):
                return
            path = _norm_path(path)
            if not path:
                return
            if any(v['vod_id'] == path for v in videos):
                return
                
            # 添加代理前缀到封面地址
            if pic:
                pic = self.proxy_prefix + pic.split('?')[0]
                
            videos.append({
                'vod_id': path,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': time,  # 使用时间作为副标题
                'vod_tag': '',
                'style': {"type": "rect", "ratio": 1.5}
            })

        # 检查是否是twi结构的页面（中字、无码流出等页面）
        if 'twi hasMedia link' in html:
            # 3) /av/new、/av/tag/中文字幕、/av/uncensored/... 使用 twi 卡片结构
            blocks = re.findall(
                r'(<div\s+class="twi\s+hasMedia\s+link"[^>]*>.*?)(?=<div\s+class="twi\s+hasMedia\s+link"|\Z)',
                html, re.S
            )
            for block in blocks:
                # 提取时间信息
                time_text = _extract_time(block)
                
                # 从twi卡片中提取链接和标题
                link_match = re.search(r'<a\s+href="([^"]+)"[^>]*class="nm\s+auth\s+jump"[^>]*>(.*?)</a>', block, re.S)
                if link_match:
                    path = link_match.group(1)
                    title = re.sub('<[^>]+>', '', link_match.group(2))
                    # 从twi卡片中提取图片
                    pic_match = re.search(r'poster="([^"]+)"', block)
                    pic = pic_match.group(1) if pic_match else ''
                    _add(path, title, pic, time_text)
                else:
                    # 备用提取方式：从视频信息中提取
                    video_match = re.search(r'<a\s+href="([^"]+)"[^>]*class="[^"]*vid[^"]*"[^>]*>(.*?)</a>', block, re.S)
                    if video_match:
                        path = video_match.group(1)
                        title = re.sub('<[^>]+>', '', video_match.group(2))
                        pic_match = re.search(r'data-echo-background="([^"]+)"', block)
                        pic = pic_match.group(1) if pic_match else ''
                        _add(path, title, pic, time_text)
        else:
            # 1) 解析瀑布流 (p1) - 首页和分类页的主要结构
            p1_blocks = re.findall(
                r'<div[^>]*class="[^"]*video-list-content-item[^"]*"[^>]*>.*?</div>',
                html, re.S
            )
            for block in p1_blocks:
                # 提取时间信息
                time_text = _extract_time(block)
                
                # 提取链接
                link_match = re.search(r'href="([^"]+)"', block)
                if not link_match:
                    continue
                path = link_match.group(1)
                if not path.startswith('/'):
                    continue
                    
                # 提取标题
                title_match = re.search(r'title="([^"]*?)"', block)
                title = title_match.group(1) if title_match else ''
                if not title:
                    # 尝试从alt属性提取
                    alt_match = re.search(r'alt="([^"]+)"', block)
                    title = alt_match.group(1) if alt_match else ''
                    
                # 提取图片
                pic_match = re.search(r'(?:data-echo-background|poster|src)="([^"]+)"', block)
                pic = pic_match.group(1) if pic_match else ''
                
                _add(path, title, pic, time_text)

            # 2) 解析 table 信息流 (p2) - 备用解析方式
            if not videos:  # 如果瀑布流没有解析到内容，再尝试table方式
                p2 = re.findall(r'<table.*?>(.*?)</table>', html, re.S)
                for block in p2:
                    # 提取时间信息
                    time_text = _extract_time(block)
                    
                    title_m = re.search(r'<h3.*?>(.*?)</h3>', block, re.S)
                    raw_title = re.sub('<[^>]+>', '', title_m.group(1)).strip() if title_m else ''
                    if not raw_title or any(word in raw_title for word in black_list):
                        continue

                    link = re.search(r'href="([^"]+)"', block)
                    if not link:
                        continue
                    path = link.group(1)
                    if not path.startswith('/'):
                        continue

                    pic_m = re.search(r'poster="([^"]+)"', block)
                    pic = pic_m.group(1) if pic_m else ''
                    
                    _add(path, raw_title, pic, time_text)

        return videos

    # =========================
    # 分类
    # =========================
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg)
        url = f'{self.host}{tid}/page-{pg}' if tid else (self.host if pg == 1 else f'{self.host}/page-{pg}')
        res = self.fetch(url)  # 使用新的fetch方法
        return {'list': self.parse_list(res), 'page': pg, 'pagecount': 999}

    # =========================
    # 详情页（HTML + DM 分流）
    # =========================
    def _extract_play(self, html: str):
        m = re.search(r'<video[^>]+data-source="([^"]+)"', html)
        if m:
            return unescape(m.group(1))

        m = re.search(r'<source[^>]+src="([^"]+)"', html, re.S)
        if m:
            return unescape(m.group(1))

        m = re.search(r'"contentUrl"\s*:\s*"([^"]+)"', html)
        if m:
            return unescape(m.group(1))

        m = re.search(r'<meta\s+property="og:video"\s+content="([^"]+)"', html)
        if m:
            return unescape(m.group(1))

        return ''

    def _extract_detail_title(self, html: str) -> str:
        """修复详情标题提取，支持多种页面结构"""
        # 1) AV播放页主体标题 - /av/xxx 页面
        m = re.search(r'<p\s+class="[^"]*no-margin\s+av-video-func-title[^"]*"[^>]*>(.*?)</p>', html, re.S)
        if m:
            t = re.sub(r'<[^>]+>', '', m.group(1))
            t = unescape(t)
            t = re.sub(r'\s+', ' ', t).strip()
            if t:
                return t

        # 2) 普通视频页标题 - /t/xxx 页面（从h3中的a标签提取）
        m = re.search(r'<h3[^>]*>.*?<a\s+[^>]*class="[^"]*nm\s+auth\s+jump[^"]*"[^>]*>(.*?)</a>', html, re.S)
        if m:
            t = re.sub(r'<[^>]+>', '', m.group(1))
            t = unescape(t)
            t = re.sub(r'\s+', ' ', t).strip()
            if t:
                return t

        # 3) 尝试直接匹配 h3 标签内容
        m = re.search(r'<h3[^>]*>(.*?)</h3>', html, re.S)
        if m:
            t = re.sub(r'<[^>]+>', '', m.group(1))
            t = unescape(t)
            t = re.sub(r'\s+', ' ', t).strip()
            # 清理掉可能的标签和括号内容
            t = re.sub(r'\s*$$[^)]*$$', '', t)
            if t:
                return t

        # 4) og:title
        m = re.search(r'<meta\s+property="og:title"\s+content="([^"]*)"', html, re.S)
        if m:
            t = unescape(m.group(1)).strip()
            if t:
                return t

        # 5) fallback <title>
        m = re.search(r'<title>(.*?)</title>', html, re.S)
        if m:
            t = re.sub(r'<[^>]+>', '', m.group(1))
            t = unescape(t)
            t = re.sub(r'\s+', ' ', t).strip()
            return t

        return 'Bad.news'

    def detailContent(self, ids):
        path = ids[0].strip() if ids and ids[0] else ''

        if path.startswith('http://') or path.startswith('https://'):
            url = path
        else:
            if not path.startswith('/'):
                path = '/' + path
            url = self.host + path

        html = self.fetch(url)  # 使用新的fetch方法

        title = self._extract_detail_title(html)

        # ===== 点击包装 =====
        def _mk_click_full(href: str, name: str):
            _id = (href or '').strip().split()[0]
            if not _id.startswith('/'):
                _id = '/' + _id
            return '[a=cr:' + json.dumps({'id': _id, 'name': name}, ensure_ascii=False) + '/]' + name + '[/a]'

        def _mk_actor_click(href: str, name: str):
            """女优主页 /av/actress/{id} 多数靠 JS 加载列表，APP 端抓不到。
            这里改跳到可解析的 search 页：/av/search/q-actress_id:{id}

            同时兼容 <a href="/av/actress/69" style="">希咲アリス</a> 这类写法。
            """
            _href = (href or '').strip().split()[0]
            if not _href:
                return ''

            m = re.search(r'^/av/actress/(\d+)', _href)
            if m:
                actress_id = m.group(1)
                return _mk_click_full(f'/av/search/q-actress_id:{actress_id}', name)

            return _mk_click_full(_href, name)

        vod_actor = ''
        vod_director = ''
        vod_content = ''

        # A) 演员：先抓"演员:"这一段的 <p> 块，再抽里面所有 <a>
        actress_block = re.search(r'演员\s*:\s*(.*?)</p>', html, re.S)
        if actress_block:
            inner = actress_block.group(1)
            actress_links = re.findall(r'<a\s+href="([^"]+)"[^>]*>\s*([^<]+?)\s*</a>', inner, re.S)
            if actress_links:
                seen = set()
                parts = []
                for href, name in actress_links:
                    name = re.sub(r'\s+', ' ', (name or '')).strip()
                    if not name:
                        continue
                    key = (href, name)
                    if key in seen:
                        continue
                    seen.add(key)
                    parts.append(_mk_actor_click(href, name))
                vod_actor = ' '.join([p for p in parts if p])

        # B) /t/ 页面：沿用原来的作者解析逻辑（给 /t/ 用），写入导演字段
        author_m = re.search(
            r'<a\s+href="(/search/t-all/q-user:[^"\s]+)"[^>]*>.*?<span\s+class="time"[^>]*>\s*([^<]+?)\s*</span>\s*</a>',
            html, re.S
        )
        if author_m:
            href = author_m.group(1)
            name = author_m.group(2).strip()
            if href and name:
                vod_director = _mk_click_full(href, name)

        # 标签：播放页 HTML 中的"标签:"块
        tag_block = re.search(r'标签\s*:\s*(.*?)</p>', html, re.S)
        tag_clicks = []
        if tag_block:
            inner = tag_block.group(1)
            tag_links = re.findall(r'<a\s+href="([^"]+)"[^>]*>\s*([^<]+?)\s*</a>', inner, re.S)
            if tag_links:
                seen_t = set()
                for href, name in tag_links:
                    name = re.sub(r'\s+', ' ', (name or '')).strip()
                    if name.startswith('#'):
                        name = name[1:].strip()
                    if not name:
                        continue
                    key = (href, name)
                    if key in seen_t:
                        continue
                    seen_t.add(key)
                    tag_clicks.append(_mk_click_full(href, name))

        # 影片描述：用于 vod_content 的正文部分
        desc = ''
        desc_m = re.search(r'影片描述\s*:\s*(.*?)</p>', html, re.S)
        if desc_m:
            desc = re.sub('<[^>]+>', '', desc_m.group(1)).strip()

        vod_content = f"{' '.join(tag_clicks)}\n{desc}".strip()

        # ===== DM（H动漫）=========
        if (not (path.startswith('http://') or path.startswith('https://'))) and path.startswith('/dm'):
            iframe = re.search(r'<iframe[^>]+src="([^"]+)"', html)
            play_url = iframe.group(1) if iframe else url
            if play_url.startswith('/'):
                play_url = self.host + play_url

            return {'list': [{
                'vod_id': play_url,
                'vod_name': title,
                'vod_actor': vod_actor,
                'vod_director': vod_director,
                'vod_content': vod_content,
                'vod_play_from': 'DM-Web',
                'vod_play_url': f'播放${play_url}',
                'vod_pic': self.proxy_prefix + play_url if play_url else ''  # 添加代理前缀
            }]}

        play = self._extract_play(html)

        # /av/{slug} 抓不到流时，去 /av/play/{slug}
        if (not play) and (not (path.startswith('http://') or path.startswith('https://'))):
            if path.startswith('/av/') and (not path.startswith('/av/play/')):
                slug = path[len('/av/'):]
                play_html = self.fetch(f'{self.host}/av/play/{slug}')  # 使用新的fetch方法
                play = self._extract_play(play_html)
                # 播放页也取主体标题/og:title
                title2 = self._extract_detail_title(play_html)
                if title2:
                    title = title2
            elif path.startswith('/av/play/'):
                play = self._extract_play(html)

        # 获取封面地址并添加代理前缀
        cover = ''
        if path.startswith('/av/play/') or path.startswith('/av/'):
            # 尝试从播放页获取封面
            cover_match = re.search(r'<video[^>]+poster="([^"]+)"', html)
            if cover_match:
                cover = cover_match.group(1)
            else:
                # 尝试从og:image获取
                og_image = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
                if og_image:
                    cover = og_image.group(1)
        else:
            # 普通页面封面
            cover_match = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
            if cover_match:
                cover = cover_match.group(1)
        
        # 添加代理前缀到封面地址
        if cover:
            cover = self.proxy_prefix + cover.split('?')[0]
        else:
            # 默认封面
            cover = self.proxy_prefix + '/default-cover.jpg'

        if play:
            return {'list': [{
                'vod_id': path,
                'vod_name': title,
                'vod_actor': vod_actor,
                'vod_director': vod_director,
                'vod_content': vod_content,
                'vod_play_from': 'HTML',
                'vod_play_url': f'播放${play}',
                'vod_pic': cover  # 使用带代理前缀的封面
            }]}

        return {'list': []}

    # =========================
    # 播放器
    # =========================
    def playerContent(self, flag, id, vipFlags):
        headers = {
            'User-Agent': self.headers['User-Agent'],
            'Referer': self.host + '/',
            'Origin': self.host,
            'Range': 'bytes=0-'
        }

        if flag == 'DM-Web':
            return {
                'parse': 1,
                'sniff': 1,
                'url': id,
                'header': headers,
                'sniff_include': ['.mp4', '.m3u8'],
                'sniff_exclude': [
                    '.html', '.js', '.css',
                    '.jpg', '.png', '.gif',
                    'google', 'facebook',
                    'doubleclick', 'analytics',
                    'ads', 'tracker'
                ]
            }

        return {'parse': 0, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{id}'}

    # =========================
    # 搜索
    # =========================
    def searchContent(self, key, quick, pg="1"):
        url = f'{self.host}/search/q-{key}'
        res = self.fetch(url)  # 使用新的fetch方法
        return {'list': self.parse_list(res)}

    # 以下方法保持为空或默认实现
    def isVideoFormat(self, url):
        pass
    def manualVideoCheck(self):
        pass
    def destroy(self):
        pass
    def localProxy(self, param):
        pass
    def liveContent(self, url):
        pass
