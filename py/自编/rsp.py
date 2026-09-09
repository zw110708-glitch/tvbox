# -*- coding: utf-8 -*-
# by @嗷呜
import json
import sys
import re
import base64
import requests
from pyquery import PyQuery as pq
from urllib.parse import urljoin

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def init(self, extend='{}'):
        config = json.loads(extend)
        self.proxy = config.get('proxy', {})
        self.plp = config.get('plp', '')
        self.session = requests.session()
        self.session.proxies = self.proxy
        self.headers = {
            'referer': f'{self.host}/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
        }

    def getName(self):
        return "肉视频修复版"

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    host = 'https://rou.video'

    def homeContent(self, filter):
        cdata = self.getpq(self.session.get(f'{self.host}/cat', headers=self.headers))
        result = {}
        classes = []
        filters = {}

        # 解析主分类
        for section in cdata('div.space-y-2 > div.mb-8').items():
            # 获取主分类名称和ID
            main_cat = section('div > a:first-child')
            type_name = main_cat('h2').text().strip()
            type_id = main_cat.attr('href')

            # 添加到分类列表
            classes.append({
                'type_name': type_name,
                'type_id': type_id
            })

            # 构建过滤器
            type_filter = {
                'key': 'type',
                'name': '类型',
                'value': []
            }

            # 解析子分类标签
            for tag in section('.flex.flex-wrap.gap-2 > a').items():
                tag_name = tag('span').text().strip()
                tag_url = tag.attr('href')
                type_filter['value'].append({
                    'n': tag_name,
                    'v': tag_url
                })

            # 添加排序选项
            order_filter = {
                'key': 'order',
                'name': '排序',
                'value': [
                    {'n': '最新', 'v': 'createdAt'},
                    {'n': '最热', 'v': 'viewCount'},
                    {'n': '最多', 'v': 'likeCount'}
                ]
            }

            # 将过滤器添加到该分类
            filters[type_id] = [order_filter, type_filter]

        result['class'] = classes
        result['filters'] = filters
        return result

    def homeVideoContent(self):
        res = self.getpq(self.session.get(f'{self.host}/home', headers=self.headers))
        videos = self.getlist(res('.grid.grid-cols-2.lg\\:grid-cols-4 div.aspect-video.relative'))
        return {'list': videos}

    def categoryContent(self, tid, pg, filter, extend):
        # 处理扩展参数
        params = {'page': pg}
        if extend:
            if 'type' in extend:
                tid = extend['type']  # 使用子分类URL
            if 'order' in extend:
                params['order'] = extend['order']

        data = self.getpq(self.session.get(f'{self.host}{tid}', params=params, headers=self.headers))
        result = {}
        result['list'] = self.getlist(data('.grid.grid-cols-2 div.aspect-video.relative'))
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def _extract_next_data(self, html: str) -> dict:
        """从页面HTML中提取Next.js __NEXT_DATA__ JSON"""
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
        if not m:
            return {}
        try:
            return json.loads(m.group(1))
        except Exception:
            return {}

    def _decode_ev(self, ev: dict) -> dict:
        """解密 pageProps.ev，得到 videoUrl / thumbVTTUrl 等直链信息"""
        if not isinstance(ev, dict):
            return {}
        d = ev.get('d')
        k = ev.get('k')
        if not d or k is None:
            return {}
        try:
            raw = base64.b64decode(d)
            dec = ''.join(chr(b - int(k)) for b in raw)
            return json.loads(dec)
        except Exception:
            return {}

    def detailContent(self, ids):
        resp = self.session.get(f'{self.host}{ids[0]}', headers=self.headers)
        html = resp.text
        data = self.getpq(html)

        # 关键修复：不要再依赖 /api/v/{id}（目前会返回 {}）
        # 直接从 __NEXT_DATA__ 的 pageProps.ev 解密拿到 videoUrl（直链）
        next_data = self._extract_next_data(html)
        page_props = (next_data.get('props') or {}).get('pageProps') or {}
        video_info = page_props.get('video') or {}
        ev_info = self._decode_ev(page_props.get('ev') or {})

        url = ev_info.get('videoUrl', '')
        if url and not url.startswith('http'):
            url = urljoin(self.host, url)

        # 提取视频标题
        vod_name = (video_info.get('nameZh') or video_info.get('name') or '').strip()
        if not vod_name:
            title_elem = data('h1.text-2xl, h1.text-3xl')
            if not title_elem:
                title_elem = data('h1').eq(0)
            vod_name = title_elem.text().strip() if title_elem else '未知标题'

        # 提取封面图
        vod_pic = video_info.get('coverImageUrl') or (data('img.object-cover').attr('src') or '')

        # ============== 修改后的标签提取逻辑 ==============
        # 优先使用Next数据中的 tagsZh / tags
        vod_content = ''
        try:
            tags = []

            tags_zh = video_info.get("tagsZh") or []
            if tags_zh:
                for tag_name in tags_zh:
                    tag_url = f"/search?q={tag_name}"
                    target = json.dumps({'id': tag_url, 'name': tag_name})
                    tags.append(f'[a=cr:{target}/]{tag_name}[/a]')

            # 如果Next数据没有标签，则尝试从HTML中提取
            if not tags:
                seen_names = set()
                seen_ids = set()
                tag_links = data('div.flex.flex-wrap.gap-1 a')

                candidates = []
                for k in tag_links.items():
                    tag_name = k.find('span[data-slot="badge"]').text() or k.text()
                    tag_name = tag_name.strip()
                    tag_href = k.attr('href')
                    if tag_name and tag_href:
                        candidates.append({'name': tag_name, 'id': tag_href})

                candidates.sort(key=lambda x: len(x['name']), reverse=True)

                for item in candidates:
                    name = item['name']
                    id_ = item['id']
                    if id_ in seen_ids:
                        continue
                    is_duplicate = False
                    for seen in seen_names:
                        if name in seen or seen in name:
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        target = json.dumps({'id': id_, 'name': name})
                        tags.append(f'[a=cr:{target}/]{name}[/a]')
                        seen_names.add(name)
                        seen_ids.add(id_)

            vod_content = ' '.join(tags) if tags else (vod_name if vod_name else "本视频暂无标签")
        except Exception as e:
            print(f"标签提取错误: {str(e)}")
            vod_content = vod_name if vod_name else "获取标签失败"
        # ============== 标签提取结束 ==============

        # 提取播放列表名称
        n = data('.md\\:col-span-2 .px-2 .hidden').eq(0).text() or '正片'

        vod = {
            'vod_name': vod_name,
            'vod_pic': vod_pic,
            'vod_content': vod_content,
            'vod_play_from': '书生玩剣',
            'vod_play_url': f"{n}${url}"
        }
        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        params = {'q': key, 'page': pg}
        data = self.getpq(self.session.get(f'{self.host}/search', params=params, headers=self.headers))
        return {'list': self.getlist(data('.grid.grid-cols-2 div.aspect-video.relative')), 'page': pg}

    def playerContent(self, flag, id, vipFlags):
        return {'parse': 0, 'url': f"{self.plp}{id}", 'header': self.headers}

    def localProxy(self, param):
        pass

    def liveContent(self, url):
        pass

    def getlist(self, data):
        videos = []
        for item in data.items():
            # 获取视频链接元素
            link_elem = item('a')
            if not link_elem:
                continue

            link = link_elem.attr('href')
            if not link:
                continue

            # 关键修改：使用修改前代码的选择器提取标题
            # 这是根据您提供的修改前代码中的选择器
            cover_img = item('img.relative.w-full')
            if not cover_img:
                # 备用选择器
                cover_img = item('img')

            # 从封面图元素获取标题和封面URL
            name = cover_img.attr('alt') or '未知标题'
            pic = cover_img.attr('src') or ''

            # 提取年份和备注
            year = item('.absolute.top-1').text().strip() or ''
            remarks = item('.absolute.bottom-1').text().strip() or ''

            videos.append({
                'vod_id': link,
                'vod_name': name,
                'vod_pic': pic,
                'vod_year': year,
                'vod_remarks': remarks,
                'style': {"type": "rect", "ratio": 1.33}
            })
        return videos

    def _urljoin(self, base, url):
        """安全的URL拼接函数"""
        if url.startswith('http'):
            return url
        if not base.endswith('/'):
            base += '/'
        if url.startswith('/'):
            url = url[1:]
        return base + url

    def getpq(self, response):
        try:
            if isinstance(response, str):
                return pq(response)
            return pq(response.text)
        except Exception as e:
            print(f"解析错误: {str(e)}")
            return pq('')
