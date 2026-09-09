# -*- coding: utf-8 -*-
# 影视交流群
# k55.net 解析（自动提取分类、支持分页、专题/演员两级分类、详情页演员/标签可点击）

import json
import re
import sys
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    host = 'https://k55.net'

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://k55.net/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    def init(self, extend=''):
        try:
            self.proxies = json.loads(extend).get('proxy', {}) if extend else {}
        except Exception:
            self.proxies = {}

    def getName(self):
        return 'k55'

    # -------------------- utils --------------------

    def fetch(self, url, params=None):
        try:
            return requests.get(
                url,
                headers=self.headers,
                params=params,
                proxies=getattr(self, 'proxies', {}) or {},
                timeout=12,
            ).text
        except Exception:
            return ''

    def _soup(self, html: str):
        return BeautifulSoup(html or '<html></html>', 'lxml')

    def _abs_url(self, path: str) -> str:
        if not path:
            return self.host
        path = str(path).strip()
        if path.startswith('http://') or path.startswith('https://'):
            return path
        if path.startswith('/'):
            return f'{self.host}{path}'
        return f'{self.host}/{path}'

    def _normalize_tid(self, tid: str) -> str:
        """tid 统一成以 / 开头的相对路径（不带 host）。"""
        if not tid:
            return ''
        tid = str(tid).strip()
        if tid.startswith('http://') or tid.startswith('https://'):
            tid = re.sub(r'^https?://[^/]+', '', tid)
        if not tid.startswith('/'):
            tid = '/' + tid
        return tid

    def _build_page_tid(self, tid: str, pg: str) -> str:
        r"""把 tid 转成对应分页 tid。

        站点常见分页形式：/label/new/page/2.html
        规则：
        - pg==1：返回原 tid
        - 若 tid 已含 /page/\d+.html：替换页码
        - 否则若 tid 以 .html 结尾：去掉 .html 后拼 /page/{pg}.html
        """
        tid = self._normalize_tid(tid)
        try:
            pg_i = int(pg)
        except Exception:
            pg_i = 1
        if pg_i <= 1:
            return tid

        if re.search(r'/page/\d+\.html$', tid):
            return re.sub(r'/page/\d+\.html$', f'/page/{pg_i}.html', tid)

        if tid.endswith('.html'):
            base = tid[:-5]
            return f'{base}/page/{pg_i}.html'

        # 兜底：/xxx -> /xxx/page/2.html
        return tid.rstrip('/') + f'/page/{pg_i}.html'

    def _extract_pagecount(self, soup: BeautifulSoup) -> int:
        pagecount = 1
        pag = soup.select_one('ul.pagination') or soup.select_one('.pagination')
        if pag:
            nums = [int(x) for x in re.findall(r'\b(\d+)\b', pag.get_text(' ', strip=True) or '')]
            if nums:
                pagecount = max(nums)
        return pagecount

    def _mk_click(self, name: str, tid: str) -> str:
        """框架可点击标记。"""
        name = (name or '').strip()
        tid = self._normalize_tid(tid)
        if not name or not tid:
            return name
        return f'[a=cr:{json.dumps({"id": tid, "name": name}, ensure_ascii=False)}/]{name}[/a]'

    # -------------------- home (auto class) --------------------

    def homeContent(self, filter):
        html = self.fetch(self.host)
        soup = self._soup(html)

        classes = []

        # 顶部4个（专题/演员/最近更新/热门）
        for a in soup.select('a.h5.text-light[href]'):
            name = a.get_text(strip=True)
            href = a.get('href')
            if not href or not name:
                continue
            # 去掉 emoji
            name = re.sub(r'^[^\w\u4e00-\u9fff]+\s*', '', name).strip()
            if not name:
                continue
            classes.append({'type_name': name, 'type_id': self._normalize_tid(href)})

        # 视频分类（/vodtype/xx.html）
        for a in soup.select('a.tag.text-light[href^="/vodtype/"]'):
            name = a.get_text(strip=True)
            href = a.get('href')
            if name and href:
                classes.append({'type_name': name, 'type_id': self._normalize_tid(href)})

        # 去重（按 type_id）
        seen = set()
        uniq = []
        for c in classes:
            if c['type_id'] in seen:
                continue
            seen.add(c['type_id'])
            uniq.append(c)

        # 删除“首页”分类：不再返回 '/'
        uniq = [c for c in uniq if c.get('type_id') not in ['/', '']]

        # 把“专题合集/女优(演员)”放到分类目录最后（如无法识别则保持原顺序）
        tail_ids = {'/topic.html', '/actor.html'}
        head_part = [c for c in uniq if c.get('type_id') not in tail_ids]
        tail_part = [c for c in uniq if c.get('type_id') in tail_ids]
        uniq = head_part + tail_part

        # 首页内容：这里展示“最近更新”第一页（若存在）；失败则展示空列表
        # 这样不会因为首页没列表而让UI空白
        list_html = self.fetch(self._abs_url('/label/new.html'))
        list_soup = self._soup(list_html)

        return {
            'class': uniq,
            'filters': {},
            'list': self.parse_videos(list_soup.select('.video-img-box')),
        }

    # -------------------- category --------------------

    def categoryContent(self, tid, pg, filter, extend):
        tid = self._normalize_tid(tid)

        # 专题合集一级：卡片列表
        if tid in ['/topic.html', '/topic']:
            url = self._abs_url(self._build_page_tid('/topic.html', pg))
            soup = self._soup(self.fetch(url))
            return {
                'list': self.parse_topic_cards(soup.select('.video-img-box')),
                'page': pg,
                'pagecount': self._extract_pagecount(soup),
                'limit': 90,
                'total': 999999,
            }

        # 演员一级：卡片列表（/actordetail-xxxx.html）
        if tid in ['/actor.html', '/actor']:
            url = self._abs_url(self._build_page_tid('/actor.html', pg))
            soup = self._soup(self.fetch(url))
            return {
                'list': self.parse_actor_cards(soup.select('.horizontal-img-box')),
                'page': pg,
                'pagecount': self._extract_pagecount(soup),
                'limit': 90,
                'total': 999999,
            }

        # 其它：视频列表（支持分页）
        page_tid = self._build_page_tid(tid, pg)
        url = self._abs_url(page_tid)
        soup = self._soup(self.fetch(url))

        return {
            'list': self.parse_videos(soup.select('.video-img-box')),
            'page': pg,
            'pagecount': self._extract_pagecount(soup),
            'limit': 90,
            'total': 999999,
        }

    # -------------------- search --------------------

    def searchContent(self, key, quick, pg='1'):
        key = (key or '').strip()
        if not key:
            return {'list': [], 'page': pg}
        # /search?text= 会 System Error；必须用 /vodsearch/xxx-----.html
        tid = f'/vodsearch/{quote(key)}-----.html'
        url = self._abs_url(self._build_page_tid(tid, pg))
        soup = self._soup(self.fetch(url))
        return {
            'list': self.parse_videos(soup.select('.video-img-box')),
            'page': pg,
            'pagecount': self._extract_pagecount(soup),
        }

    # -------------------- detail / player --------------------

    def _extract_id_from_vodplay(self, vodplay_path: str) -> str:
        m = re.search(r'/vodplay/(\d+)-', vodplay_path or '')
        return m.group(1) if m else ''

    def detailContent(self, ids):
        vid = self._normalize_tid(ids[0])
        url = self._abs_url(vid)
        html = self.fetch(url)
        soup = self._soup(html)

        title = ''
        h1 = soup.select_one('h1')
        if h1 and h1.get_text(strip=True):
            title = h1.get_text(strip=True)
        elif soup.title and soup.title.get_text(strip=True):
            title = soup.title.get_text(strip=True)
        title = re.sub(r'\s*\|.*$', '', title).strip()

        video_id = self._extract_id_from_vodplay(vid)

        vod_pic = ''
        m_pic = re.search(r'"vod_pic"\s*:\s*"([^"]+)"', html)
        if m_pic:
            vod_pic = m_pic.group(1).replace('\\/', '/')
        if not vod_pic:
            og = soup.select_one('meta[property="og:image"]')
            if og and og.get('content'):
                vod_pic = og.get('content')

        vod = {
            'vod_name': title,
            'vod_play_from': 'madou',
            'vod_play_url': f'{title}${video_id}' if video_id else f'{title}$',
            'vod_pic': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{vod_pic}',
        }

        # 1) 演员可点击
        # 真实DOM里：全名通常在 span.placeholder 的 data-original-title 上，a 标签文本只有 1 个字
        actors = []
        for a in soup.select('div.models a.model[href]'):
            span = a.select_one('span')
            name = ''
            if span:
                # 有的页面用 data-original-title，有的只用 title
                name = (span.get('data-original-title') or span.get('title') or '').strip()
            if not name:
                # 兜底：a 的 title 或文本
                name = (a.get('title') or a.get_text(strip=True) or '').strip()
            if not name:
                continue
            actor_tid = f'/vodsearch/{quote(name)}-----.html'
            actors.append(self._mk_click(name, actor_tid))
        if actors:
            vod['vod_actor'] = ' '.join(actors)

        # 2) 标签可点击（详情页简介标签）
        # 详情页里可能出现两段 h5.tags.h6-md：
        # - 一段是“女优”标签（cat 文本为 女优 / href 为空或指向演员搜索）
        # - 另一段才是视频分类/关键词标签（cat href 以 /vodtype/ 开头）
        tags = []
        tags_boxes = soup.select('h5.tags.h6-md')
        tags_box = None
        for box in tags_boxes:
            cat = box.select_one('a.cat')
            cat_href = (cat.get('href') or '').strip() if cat else ''
            cat_text = (cat.get_text(strip=True) if cat else '')
            # 优先选择真正“视频分类”那段：cat href 指向 /vodtype/
            if cat_href.startswith('/vodtype/'):
                tags_box = box
                break
        if not tags_box and tags_boxes:
            # 兜底：选第一个 cat 不是“女优”且 href 非空的
            for box in tags_boxes:
                cat = box.select_one('a.cat')
                cat_href = (cat.get('href') or '').strip() if cat else ''
                cat_text = (cat.get_text(strip=True) if cat else '')
                if cat_text not in ['女优', '演員', '演员'] and cat_href:
                    tags_box = box
                    break

        if tags_box:
            for a in tags_box.select('a[href]'):
                name = a.get_text(strip=True)
                href = (a.get('href') or '').strip()
                if not name or not href:
                    continue
                href = self._normalize_tid(href)
                tags.append(self._mk_click(name, href))

        if tags:
            vod['vod_content'] = ' '.join(tags)

        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {'parse': 0, 'url': ''}
        html = self.fetch(f'{self.host}/vodplay/{id}-1-1.html')
        m = re.search(r'"url"\s*:\s*"(https?:\\/\\/[^\"]+)"', html)
        play_url = m.group(1).replace('\\/', '/') if m else ''
        return {
            'parse': 0,
            'url': play_url,
            'header': {
                'user-agent': self.headers['User-Agent'],
                'referer': f'{self.host}/vodplay/{id}-1-1.html',
                'origin': self.host,
            }
        } if play_url else {'parse': 0, 'url': ''}

    # -------------------- parsers --------------------

    def parse_videos(self, nodes):
        videos = []
        for node in nodes or []:
            a = node.select_one('a[href^="/vodplay/"]') or node.select_one('a[href]')
            if not a:
                continue
            link = a.get('href')

            title = ''
            h6 = node.select_one('.detail h6')
            if h6 and h6.get_text(strip=True):
                title = h6.get_text(strip=True)
            else:
                detail = node.select_one('.detail')
                if detail and detail.get_text(strip=True):
                    title = detail.get_text(' ', strip=True)

            if not link or not title:
                continue

            img = node.select_one('img')
            pic = ''
            if img:
                pic = img.get('data-src') or img.get('src') or ''
            if pic.startswith('/'):
                pic = self.host + pic

            remarks = ''
            detail_txt = (node.select_one('.detail').get_text(' ', strip=True) if node.select_one('.detail') else '')
            nums = re.findall(r'\b(\d+)\b', detail_txt)
            if len(nums) >= 2:
                remarks = f'👁 {nums[-2]} ❤ {nums[-1]}'
            elif len(nums) == 1:
                remarks = f'👁 {nums[-1]}'

            videos.append({
                'vod_id': self._normalize_tid(link),
                'vod_name': title,
                'vod_pic': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pic}',
                'vod_remarks': remarks,
                'style': {'type': 'rect', 'ratio': 1.33},
            })
        return videos

    def parse_topic_cards(self, nodes):
        # 专题首页卡片：/topicdetail-2.html
        out = []
        for node in nodes or []:
            a = node.select_one('a[href^="/topicdetail-"]')
            if not a:
                continue
            href = a.get('href')
            title_el = node.select_one('h4')
            name = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
            img = node.select_one('img')
            pic = img.get('src') if img else ''
            if pic.startswith('/'):
                pic = self.host + pic
            if href and name:
                out.append({
                    'vod_id': self._normalize_tid(href),
                    'vod_name': name,
                    'vod_pic': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pic}',
                    'vod_tag': 'folder',
                    'style': {'type': 'rect', 'ratio': 0.75},
                })
        return out

    def parse_actor_cards(self, nodes):
        # 演员首页卡片：/actordetail-12382.html
        out = []
        for node in nodes or []:
            a = node.select_one('a[href^="/actordetail-"]')
            if not a:
                continue
            href = a.get('href')
            name_el = node.select_one('h6.title')
            name = name_el.get_text(strip=True) if name_el else a.get_text(strip=True)
            img = node.select_one('img')
            pic = img.get('src') if img else ''
            if href and name:
                out.append({
                    'vod_id': self._normalize_tid(href),
                    'vod_name': name,
                    'vod_pic': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pic}',
                    'vod_tag': 'folder',
                    'style': {'type': 'rect', 'ratio': 0.75},
                })
        return out

    # -------------------- unused hooks --------------------

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def homeVideoContent(self):
        pass

    def localProxy(self, param):
        pass

    def liveContent(self, url):
        pass
