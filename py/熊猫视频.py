# -*- coding: utf-8 -*-
import json
import sys
import threading
import time
import requests
import re
from urllib.parse import urlparse, unquote
from pyquery import PyQuery as pq
sys.path.append('..')
from base.spider import Spider

class Spider(Spider):

    def init(self, extend="{}"):
        self.entry_url = "https://88xm.tv"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9'
        }
        self.host = self.detect_active_host_from_88xmtv()
        self.api_url = "https://spiderscloudcn2.51111666.com"
        self.headers.update({
            'Origin': self.host,
            'Referer': f"{self.host}/"
        })
        print(f"[+] 88xm.tv 活跃站点: {self.host}")
        print(f"[+] API地址: {self.api_url}")

    def getName(self):
        return "熊猫视频"

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    # ==================== 核心：从 88xm.tv 提取并探测可用 host ====================
    def detect_active_host_from_88xmtv(self):
        """从 https://88xm.tv 提取所有候选地址，并探测可用性"""
        try:
            resp = requests.get(self.entry_url, headers=self.headers, timeout=10)
            resp.encoding = 'utf-8'
            doc = pq(resp.text)
        except Exception as e:
            print(f"[-] 无法访问 {self.entry_url}: {e}")
            return "https://www.yyqqyy.com"  # 回退

        candidates = set()

        # 1. 提取所有链接
        for a in doc('a').items():
            href = a.attr('href')
            if href and href.startswith('http'):
                root = self._extract_root_url(href)
                if root:
                    candidates.add(root)

        # 2. 提取文本中的域名（防止有些域名在注释中）
        text_domains = re.findall(r'[\u718A\u732B\u770B\u7247]+\.[a-zA-Z]+', resp.text)
        for domain in text_domains:
            candidates.add(f"https://{domain}")

        # 3. 手动补充已知候选（防遗漏）
        fallbacks = [
            "https://www.cc44dd.com",
            "https://www.yyqqyy.com",
            "https://njlsw1566.com",
            "https://cmkis944.com"
        ]
        for url in fallbacks:
            root = self._extract_root_url(url)
            if root:
                candidates.add(root)

        candidates = list(candidates)
        if not candidates:
            return "https://www.yyqqyy.com"

        print(f"[+] 候选站点: {candidates}")

        # 多线程探测
        results = {}
        threads = []

        def check(url):
            try:
                start = time.time()
                r = requests.head(url, headers=self.headers, timeout=5, allow_redirects=True)
                if r.status_code == 200:
                    delay = (time.time() - start) * 1000
                    results[url] = delay
                else:
                    results[url] = float('inf')
            except:
                results[url] = float('inf')

        for url in candidates:
            t = threading.Thread(target=check, args=(url,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=6)

        # 选最快可用的
        valid = {k: v for k, v in results.items() if v != float('inf')}
        if valid:
            best = min(valid, key=valid.get)
            return best
        else:
            return "https://www.yyqqyy.com"  # 全挂了就回退

    def _extract_root_url(self, url):
        """提取 scheme + netloc，忽略路径"""
        try:
            parsed = urlparse(url)
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                # 处理中文域名
                if re.search(r'[\u4e00-\u9fff]', parsed.netloc):
                    return None  # 中文域名无法直接请求
                return f"{parsed.scheme}://{parsed.netloc}"
        except:
            pass
        return None

    # ==================== 以下为原业务逻辑（适配新 host） ====================

    def homeContent(self, filter):
        return self._fetch_category_and_videos()

    def _fetch_category_and_videos(self):
        headers = self.headers.copy()
        headers['Referer'] = self.host + '/'

        try:
            # 获取分类数据
            data = {"name": "John", "age": 31, "city": "New York"}
            res = requests.post(f'{self.api_url}/getDataInit', headers=headers, json=data, timeout=10)
            res.encoding = "utf-8"
            json_dict = res.json()
            menu0ListMap = json_dict["data"]["menu0ListMap"]
            result = {'class': []}
            for item in menu0ListMap[:3]:
                if item['typeName'] in ["传媒", "视频", "电影"]:
                    for item1 in item['menu2List']:
                        type_id = str(item1['typeId2']).replace(".0", "")
                        result['class'].append({'type_id': type_id, 'type_name': item1['typeName2']})
            
            # 首页视频
            videos = self._fetch_videos(pg=1, cid="24")
            result['list'] = videos
            return result
        except Exception as e:
            print(f"homeContent 异常: {e}")
            return {'class': [], 'list': []}

    def _fetch_videos(self, pg, cid="", key=""):
        headers = self.headers.copy()
        headers['Referer'] = self.host + '/'
        videos = []
        try:
            # 根据Java源码构建请求参数
            data = {
                "command": "WEB_GET_INFO",
                "pageNumber": int(pg),
                "RecordsPage": 20,
                "typeId": cid,
                "typeMid": "1",
                "languageType": "CN",
                "content": key
            }
            
            res = requests.post(f'{self.api_url}/forward', headers=headers, json=data, timeout=10)
            res.encoding = "utf-8"
            json_dict = res.json()
            resultList = json_dict["data"]["resultList"]
            
            for item in resultList:
                name = item['vod_name'].replace("yy8ycom", "").strip()
                pic = item['vod_pic']
                
                # 确保图片URL完整
                if not pic.startswith('http'):
                    pic = self._ensure_absolute_url(pic)
                
                video = {
                    "vod_id": f"{name}${pic}",  # 使用$分隔，避免与#冲突
                    "vod_name": name,
                    "vod_pic": pic,
                    "vod_remarks": ''
                }
                videos.append(video)
        except Exception as e:
            print(f"获取视频异常: {e}")
        return videos

    def _ensure_absolute_url(self, url):
        """确保URL是绝对路径"""
        if url.startswith('http'):
            return url
        if url.startswith('/'):
            return f"{self.host}{url}"
        return f"{self.host}/{url}"

    def homeVideoContent(self):
        videos = self._fetch_videos(pg=1, cid="24")
        return {'list': videos}

    def categoryContent(self, tid, pg, filter, extend):
        videos = self._fetch_videos(pg=pg, cid=tid)
        return {
            'list': videos,
            'page': int(pg),
            'pagecount': 9999,
            'limit': 20,
            'total': 999999
        }

    def detailContent(self, ids):
        did = ids[0]
        # 使用$分隔名称和图片URL
        parts = did.split("$", 1)
        if len(parts) < 2:
            return {'list': []}
        name, pic_url = parts
        
        # 确保图片URL完整
        pic_url = self._ensure_absolute_url(pic_url)
        
        # 生成播放地址（根据Java源码逻辑）
        play_url = pic_url.replace("1.jpg", "playlist.m3u8")
        
        video = {
            "vod_id": did,
            "vod_name": name,
            "vod_pic": pic_url,
            "vod_play_from": "熊猫视频",
            "vod_play_url": f"播放${play_url}"
        }
        return {'list': [video]}

    def playerContent(self, flag, id, vipFlags):
        url = id.split('$')[-1]
        # 确保播放地址完整
        if not url.startswith('http'):
            url = self._ensure_absolute_url(url)
            
        return {
            "parse": 0,
            "playUrl": '',
            "url": f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{url}',
            "header": self.headers
        }

    def searchContent(self, key, quick):
        # 严格按Java源码实现搜索功能
        try:
            headers = self.headers.copy()
            headers['Referer'] = self.host + '/'
            
            # 构建搜索请求数据 - 与Java源码完全一致
            data = {
                "command": "WEB_GET_INFO",
                "pageNumber": 1,
                "RecordsPage": 20,
                "typeId": "",  # 搜索时typeId为空字符串（与分类不同）
                "typeMid": "1",
                "languageType": "CN",
                "content": key  # 搜索关键词
            }
            
            res = requests.post(f'{self.api_url}/forward', headers=headers, json=data, timeout=10)
            res.encoding = "utf-8"
            json_dict = res.json()
            resultList = json_dict["data"]["resultList"]
            
            videos = []
            for item in resultList:
                name = item['vod_name'].replace("yy8ycom", "").strip()
                pic = item['vod_pic']
                
                # 确保图片URL完整
                if not pic.startswith('http'):
                    pic = self._ensure_absolute_url(pic)
                
                video = {
                    "vod_id": f"{name}${pic}",
                    "vod_name": name,
                    "vod_pic": pic,
                    "vod_remarks": ''
                }
                videos.append(video)
                
            return {'list': videos}
        except Exception as e:
            print(f"搜索异常: {e}")
            return {'list': []}

    def searchContentPage(self, key, quick, page):
        # 严格按Java源码实现分页搜索
        try:
            headers = self.headers.copy()
            headers['Referer'] = self.host + '/'
            
            # 构建搜索请求数据 - 与Java源码完全一致
            data = {
                "command": "WEB_GET_INFO",
                "pageNumber": int(page),
                "RecordsPage": 20,
                "typeId": "",  # 搜索时typeId为空字符串
                "typeMid": "1",
                "languageType": "CN",
                "content": key  # 搜索关键词
            }
            
            res = requests.post(f'{self.api_url}/forward', headers=headers, json=data, timeout=10)
            res.encoding = "utf-8"
            json_dict = res.json()
            resultList = json_dict["data"]["resultList"]
            
            videos = []
            for item in resultList:
                name = item['vod_name'].replace("yy8ycom", "").strip()
                pic = item['vod_pic']
                
                # 确保图片URL完整
                if not pic.startswith('http'):
                    pic = self._ensure_absolute_url(pic)
                
                video = {
                    "vod_id": f"{name}${pic}",
                    "vod_name": name,
                    "vod_pic": pic,
                    "vod_remarks": ''
                }
                videos.append(video)
                
            return {
                'list': videos,
                'page': int(page),
                'pagecount': 9999,
                'limit': 20,
                'total': 999999
            }
        except Exception as e:
            print(f"搜索分页异常: {e}")
            return {'list': []}

    def localProxy(self, params):
        return None