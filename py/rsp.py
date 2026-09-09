# -*- coding: utf-8 -*-
# by @嗷呜
import json
import sys
import requests
from pyquery import PyQuery as pq
from urllib.parse import urljoin

sys.path.append('..')
from base.spider import Spider

class Spider(Spider):

    def init(self, extend='{}'):
        config = json.loads(extend)
        self.proxies = config.get('proxies', {
            "http": "http://127.0.0.1:10172",
            "https": "http://127.0.0.1:10172"
        })
        self.plp = config.get('plp', '')
        self.session = requests.session()
        self.session.proxies = self.proxies
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

    def detailContent(self, ids):
        data = self.getpq(self.session.get(f'{self.host}{ids[0]}', headers=self.headers))
        api_url = f"{self.host}/api{ids[0]}"
        api_data = self.session.get(api_url, headers=self.headers).json()

        # 获取视频URL
        url = api_data.get('video', {}).get('videoUrl', '')
        if not url:
            player = data('video#main-player')
            if player:
                url = player.attr('src')

        # 提取视频标题
        title_elem = data('h1.text-2xl, h1.text-3xl')
        if not title_elem:
            title_elem = data('h1').eq(0)
        vod_name = title_elem.text().strip() if title_elem else '未知标题'

        # 提取封面图
        vod_pic = data('img.object-cover').attr('src') or ''

        # ============== 修改后的标签提取逻辑 ==============
        # 按照二次点击逻辑提取标签
        vod_content = ''
        try:
            tags = []
            seen_names = set()
            seen_ids = set()
            
            # 根据HTML源码结构，标签位于div.flex.flex-wrap.gap-1容器中的a标签
            tag_links = data('div.flex.flex-wrap.gap-1 a')
            
            # 如果没有找到，尝试其他可能的选择器
            if not tag_links:
                # 尝试从所有包含data-slot="badge"的span元素的父元素a中提取
                badges = data('span[data-slot="badge"]')
                if badges:
                    for badge in badges.items():
                        parent_a = badge.parent('a')
                        if parent_a:
                            # 临时存储，模拟tag_links
                            tag_links = tag_links.add(parent_a)
            
            # 如果还没找到，尝试使用API数据中的tagsZh
            if not tag_links:
                tags_zh = api_data.get("tagsZh", [])
                if tags_zh:
                    for tag_name in tags_zh:
                        tag_url = f"/search?q={tag_name}"
                        target = json.dumps({'id': tag_url, 'name': tag_name})
                        tags.append(f'[a=cr:{target}/]{tag_name}[/a]')
            
            # 从HTML中提取标签
            candidates = []
            for k in tag_links.items():
                # 提取标签名：从span元素中获取，如果不存在则使用a标签的文本
                tag_name = k.find('span[data-slot="badge"]').text() or k.text()
                tag_name = tag_name.strip()
                tag_href = k.attr('href')
                if tag_name and tag_href:
                    candidates.append({'name': tag_name, 'id': tag_href})
            
            # 按标签名长度排序，优先选择更长的标签名（避免包含关系导致的重复）
            candidates.sort(key=lambda x: len(x['name']), reverse=True)
            
            # 构建标签列表，避免重复
            for item in candidates:
                name = item['name']
                id_ = item['id']
                
                # 检查id是否已存在
                if id_ in seen_ids:
                    continue
                
                # 检查标签名是否包含在其他已选标签中
                is_duplicate = False
                for seen in seen_names:
                    if name in seen or seen in name:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    # 构建JSON字符串，注意格式要正确
                    target = json.dumps({'id': id_, 'name': name})
                    # 按照参考代码的格式构建标签字符串，添加斜杠
                    tags.append(f'[a=cr:{target}/]{name}[/a]')
                    seen_names.add(name)
                    seen_ids.add(id_)
            
            # 如果有标签，则构建vod_content
            if tags:
                vod_content = ' '.join(tags)
            else:
                # 如果没有标签，使用标题作为备选
                vod_content = vod_name if vod_name else "本视频暂无标签"
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