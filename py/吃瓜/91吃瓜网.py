# -*- coding: utf-8 -*-
# by @嗷呜
import json
import re
import sys
import hashlib
from base64 import b64decode, b64encode
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from pyquery import PyQuery as pq
sys.path.append('..')
from base.spider import Spider as BaseSpider

# 图片缓存，避免重复解密
img_cache = {}

class Spider(BaseSpider):
    
    def init(self, extend=""):
        """初始化"""
        try:
            self.proxies = json.loads(extend) if extend else {}
        except:
            self.proxies = {}
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13; M2102J2SC Build/TKQ1.221114.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/142.0.7444.32 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
        }
        self.host = 'https://madou.net'
        self.headers.update({'Origin': self.host, 'Referer': f"{self.host}/"})
        print(f"使用站点: {self.host}")
    
    def getName(self):
        return "麻豆传媒精简版"
    
    def isVideoFormat(self, url):
        return any(ext in (url or '') for ext in ['.m3u8', '.mp4', '.ts', '.flv', '.mkv'])
    
    def manualVideoCheck(self):
        return False
    
    def destroy(self):
        global img_cache
        img_cache.clear()
    
    def homeContent(self, filter):
        """首页：固定分类"""
        classes = [
            {'type_name': '首页', 'type_id': '/'},
            {'type_name': '每日更新', 'type_id': '/category/17202/'},
            {'type_name': '麻豆AV', 'type_id': '/category/17210101/'},
            {'type_name': '热门吃瓜', 'type_id': '/category/165810103/'},
            {'type_name': '顶流网黄', 'type_id': '/category/58110101/'},
            {'type_name': '热门女优', 'type_id': '/category/52310101/'},
            {'type_name': '国产精品', 'type_id': '/category/117710101/'},
            {'type_name': '片商传媒', 'type_id': '/category/71310101/'},
            {'type_name': '网红明星', 'type_id': '/category/167310101/'},
            {'type_name': '日本AV', 'type_id': '/category/64110101/'},
        ]
        
        # 排序过滤器
        filters = {}
        order_filter = {
            'key': 'order',
            'name': '排序',
            'value': [
                {'n': '最新', 'v': 'createdAt'},
                {'n': '最热', 'v': 'viewCount'},
                {'n': '推荐', 'v': 'recommend'}
            ]
        }
        
        for cat in classes:
            filters[cat['type_id']] = [order_filter]
        
        return {'class': classes, 'filters': filters}
    
    def homeVideoContent(self):
        """首页视频列表"""
        try:
            response = requests.get(self.host, headers=self.headers, timeout=10)
            if response.status_code != 200:
                return {'list': []}
            
            html = response.text
            videos = []
            
            # 使用正则提取文章块
            pattern = r'<article[^>]*>(.*?)</article>'
            articles = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            
            for article in articles[:12]:  # 首页只显示12个
                # 提取链接
                href_match = re.search(r'href="([^"]+)"', article)
                if not href_match:
                    continue
                    
                href = href_match.group(1)
                if not href or '/archives/' not in href:
                    continue
                    
                # 构建完整URL
                if not href.startswith('http'):
                    href = self.host + href if href.startswith('/') else f'{self.host}/{href}'
                
                # 提取标题
                title_match = re.search(r'headline">([^<]+)</h2>', article)
                if not title_match:
                    continue
                    
                title = title_match.group(1).strip()
                
                # 提取图片
                cover = ''
                img_match = re.search(r'data-src="([^"]+)"', article)
                if img_match:
                    data_src = img_match.group(1).strip()
                    if data_src:
                        cover = self._proc_img_url(data_src)
                
                videos.append({
                    'vod_id': href,
                    'vod_name': title[:100],
                    'vod_pic': cover,
                    'vod_remarks': '',
                    'style': {"type": "rect", "ratio": 1.5}
                })
            
            return {'list': videos}
            
        except Exception as e:
            print(f"首页视频获取失败: {e}")
            return {'list': []}
    
    def categoryContent(self, tid, pg, filter, extend):
        """分类页内容"""
        try:
            # 构建URL
            if tid == '/':
                url = self.host
            else:
                url = f"{self.host}{tid}"
                if pg and pg != '1':
                    url = f"{url}{pg}" if tid.endswith('/') else f"{url}/{pg}"
            
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code != 200:
                return {'list': [], 'page': pg, 'pagecount': 0, 'limit': 20, 'total': 0}
            
            html = response.text
            videos = []
            
            # 提取文章块
            pattern = r'<article[^>]*>(.*?)</article>'
            articles = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            
            seen_urls = set()
            
            for article in articles:
                if len(videos) >= 20:  # 每页20个
                    break
                
                # 提取链接
                href_match = re.search(r'href="([^"]+)"', article)
                if not href_match:
                    continue
                    
                href = href_match.group(1)
                if not href or '/archives/' not in href:
                    continue
                    
                # 构建完整URL
                if not href.startswith('http'):
                    href = self.host + href if href.startswith('/') else f'{self.host}/{href}'
                
                # 去重
                if href in seen_urls:
                    continue
                seen_urls.add(href)
                
                # 提取标题
                title_match = re.search(r'headline">([^<]+)</h2>', article)
                if not title_match:
                    continue
                    
                title = title_match.group(1).strip()
                
                # 提取图片
                cover = ''
                img_match = re.search(r'data-src="([^"]+)"', article)
                if img_match:
                    data_src = img_match.group(1).strip()
                    if data_src:
                        cover = self._proc_img_url(data_src)
                
                videos.append({
                    'vod_id': href,
                    'vod_name': title[:100],
                    'vod_pic': cover,
                    'vod_remarks': '',
                    'style': {"type": "rect", "ratio": 1.5}
                })
            
            return {
                'list': videos,
                'page': pg,
                'pagecount': 9999,
                'limit': 20,
                'total': 999999
            }
            
        except Exception as e:
            print(f"分类页获取失败: {e}")
            return {'list': [], 'page': pg, 'pagecount': 0, 'limit': 20, 'total': 0}
    
    def detailContent(self, ids):
        """详情页内容"""
        try:
            url = ids[0] if ids[0].startswith('http') else self.host + ids[0]
            
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code != 200:
                return {'list': []}
            
            html = response.text
            
            # 提取标题
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', html)
            title = title_match.group(1).strip() if title_match else '未知标题'
            # 清理标题
            if '|' in title:
                title = title.split('|')[0].strip()
            
            # 提取描述
            desc_match = re.search(r'<meta[^>]*property="og:description"[^>]*content="([^"]+)"', html)
            content = desc_match.group(1).strip() if desc_match else ''
            
            # 提取封面
            cover = ''
            # 查找data-src
            img_match = re.search(r'data-src="([^"]+)"', html)
            if img_match:
                data_src = img_match.group(1).strip()
                if data_src:
                    cover = self._proc_img_url(data_src)
            
            # 提取标签
            keywords = ''
            keywords_match = re.search(r'<meta[^>]*name="keywords"[^>]*content="([^"]+)"', html)
            if keywords_match:
                keywords = keywords_match.group(1).strip()
            
            # 关键：提取播放地址
            play_urls = []
            
            # 1. 从script标签中查找可能的视频地址
            script_pattern = r'<script[^>]*>(.*?)</script>'
            script_matches = re.findall(script_pattern, html, re.DOTALL | re.IGNORECASE)
            
            for script_content in script_matches:
                # 查找可能的视频地址
                video_patterns = [
                    r'"(https?://[^\s"\']+\.m3u8[^\s"\']*)"',
                    r'"(https?://[^\s"\']+\.mp4[^\s"\']*)"',
                    r'https?://[^\s"\']+\.m3u8[^\s"\']*',
                    r'https?://[^\s"\']+\.mp4[^\s"\']*',
                ]
                
                for pattern in video_patterns:
                    matches = re.findall(pattern, script_content, re.IGNORECASE)
                    for match in matches:
                        if isinstance(match, str):
                            play_url = match
                        else:
                            play_url = match[0] if isinstance(match, tuple) else match
                        
                        if play_url and 'http' in play_url and play_url not in play_urls:
                            play_urls.append(play_url)
            
            # 2. 从页面中查找iframe或video标签
            if not play_urls:
                # 查找iframe
                iframe_match = re.search(r'<iframe[^>]*src="([^"]+)"', html)
                if iframe_match:
                    iframe_src = iframe_match.group(1).strip()
                    if iframe_src and iframe_src.startswith('http'):
                        play_urls.append(iframe_src)
                
                # 查找video标签
                video_match = re.search(r'<video[^>]*src="([^"]+)"', html)
                if video_match:
                    video_src = video_match.group(1).strip()
                    if video_src and video_src.startswith('http'):
                        play_urls.append(video_src)
            
            # 3. 从data-url属性提取
            data_url_matches = re.findall(r'data-url="([^"]+)"', html)
            for data_url in data_url_matches:
                if data_url:
                    play_url = data_url.replace('&amp;', '&')
                    if play_url and play_url not in play_urls:
                        play_urls.append(play_url)
            
            # 构建播放列表
            play_list = []
            if play_urls:
                for i, play_url in enumerate(play_urls[:3]):
                    play_list.append(f"线路{i+1}${play_url}")
            else:
                play_list.append(f"线路1${url}")
            
            play_line = '#'.join(play_list)
            
            vod = {
                'vod_name': title,
                'vod_pic': cover or f'{self.host}/static/images/logo.png',
                'vod_content': content,
                'vod_play_from': '麻豆传媒',
                'vod_play_url': play_line,
                'vod_tag': keywords,
                'vod_area': '国产',
                'vod_lang': '国语',
            }
            
            return {'list': [vod]}
            
        except Exception as e:
            print(f"详情页获取失败: {e}")
            return {'list': []}
    
    def searchContent(self, key, quick, pg="1"):
        """搜索内容"""
        try:
            # URL编码关键词
            encoded_key = requests.utils.quote(key)
            url = f"{self.host}/search/{encoded_key}/{pg}"
            
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code != 200:
                return {'list': [], 'page': pg}
            
            html = response.text
            videos = []
            
            # 提取文章块
            pattern = r'<article[^>]*>(.*?)</article>'
            articles = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            
            seen_urls = set()
            
            for article in articles:
                # 提取链接
                href_match = re.search(r'href="([^"]+)"', article)
                if not href_match:
                    continue
                    
                href = href_match.group(1)
                if not href or '/archives/' not in href:
                    continue
                    
                # 构建完整URL
                if not href.startswith('http'):
                    href = self.host + href if href.startswith('/') else f'{self.host}/{href}'
                
                # 去重
                if href in seen_urls:
                    continue
                seen_urls.add(href)
                
                # 提取标题
                title_match = re.search(r'headline">([^<]+)</h2>', article)
                if not title_match:
                    continue
                    
                title = title_match.group(1).strip()
                
                # 提取图片
                cover = ''
                img_match = re.search(r'data-src="([^"]+)"', article)
                if img_match:
                    data_src = img_match.group(1).strip()
                    if data_src:
                        cover = self._proc_img_url(data_src)
                
                videos.append({
                    'vod_id': href,
                    'vod_name': title[:100],
                    'vod_pic': cover,
                    'vod_remarks': '',
                    'style': {"type": "rect", "ratio": 1.5}
                })
            
            return {'list': videos, 'page': pg}
            
        except Exception as e:
            print(f"搜索失败: {e}")
            return {'list': [], 'page': pg}
    
    def playerContent(self, flag, id, vipFlags):
        """播放器内容"""
        # 检查是否是完整的http地址
        if id.startswith('http'):
            return {
                'parse': 0,  # 0表示直接播放
                'url': id,
                'header': self.headers
            }
        else:
            return {
                'parse': 1,  # 1表示需要解析
                'url': id,
                'header': self.headers
            }
    
    def localProxy(self, param):
        """本地代理 - 处理图片解密"""
        try:
            type_ = param.get('type', '')
            url = param.get('url', '')
            key = param.get('key', '')
            
            if type_ == 'cache':
                # 从缓存获取图片
                if key in img_cache:
                    return [200, 'image/jpeg', img_cache[key]]
                return [404, 'text/plain', b'Expired']
            
            elif type_ == 'img':
                # 解密图片
                real_url = self._d64(url) if not url.startswith('http') else url
                res = requests.get(real_url, headers=self.headers, timeout=10)
                if res.status_code == 200:
                    content = self._aesimg(res.content)
                    # 缓存图片
                    cache_key = hashlib.md5(content).hexdigest()
                    img_cache[cache_key] = content
                    return [200, 'image/jpeg', content]
                return [404, 'text/plain', b'Not Found']
            
            return [404, 'text/plain', b'Invalid request']
            
        except Exception as e:
            print(f"本地代理错误: {e}")
            return [404, 'text/plain', b'Error']
    
    def _proc_img_url(self, url):
        """处理图片URL - 转换为代理URL"""
        if not url:
            return ''
        
        url = url.strip('\'" ')
        
        # 如果已经是完整URL，直接返回
        if url.startswith('http'):
            # 使用代理URL进行解密
            return f"{self.getProxyUrl()}&url={self._e64(url)}&type=img"
        
        # 如果是相对路径，添加主机前缀
        if url.startswith('/'):
            full_url = f"{self.host}{url}"
        else:
            full_url = f"{self.host}/{url}"
        
        # 使用代理URL进行解密
        return f"{self.getProxyUrl()}&url={self._e64(full_url)}&type=img"
    
    def _e64(self, text):
        """Base64编码"""
        return b64encode(str(text).encode()).decode()
    
    def _d64(self, text):
        """Base64解码"""
        return b64decode(str(text).encode()).decode()
    
    def _aesimg(self, data):
        """AES解密图片"""
        if len(data) < 16:
            return data
        
        # 从你提供的代码中提取的密钥对
        keys = [
            (b'f5d965df75336270', b'97b60394abc2fbe1'),
            (b'75336270f5d965df', b'abc2fbe197b60394')
        ]
        
        for key, iv in keys:
            try:
                # 尝试CBC模式解密
                cipher = AES.new(key, AES.MODE_CBC, iv)
                decrypted = cipher.decrypt(data)
                decrypted = unpad(decrypted, 16)
                
                # 检查解密后的数据是否是有效的图片格式
                if decrypted.startswith(b'\xff\xd8') or decrypted.startswith(b'\x89PNG'):
                    return decrypted
            except:
                pass
            
            try:
                # 尝试ECB模式解密
                cipher = AES.new(key, AES.MODE_ECB)
                decrypted = cipher.decrypt(data)
                decrypted = unpad(decrypted, 16)
                
                # 检查解密后的数据是否是有效的图片格式
                if decrypted.startswith(b'\xff\xd8'):
                    return decrypted
            except:
                pass
        
        # 如果解密失败，返回原始数据
        return data