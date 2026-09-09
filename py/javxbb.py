# -*- coding: utf-8 -*-
#author 🍑
import json
import re
import os
import sys
import requests
import urllib.parse
from requests.exceptions import RequestException
try:
    from pyquery import PyQuery as pq
except Exception:
    pq = None
from base.spider import Spider

class Spider(Spider):
    name = 'Javbobo'
    host = 'https://javbobo.com'
    proxy_prefix = "http://127.0.0.1:10079/p/0/127.0.0.1:10172/"  # 代理地址前缀
    
    def init(self, extend=""):
        # 修改为与hohoj相同的代理配置方式
        self.proxies = json.loads(extend).get('proxy', {}) if extend else {}
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': f'{self.host}/',
            'Origin': self.host,
            'Connection': 'keep-alive',
        }
    
    def getName(self):
        return self.name
    
    def fetch(self, url, params=None):
        """添加与hohoj相同的fetch方法"""
        try:
            return requests.get(url, headers=self.headers, params=params, 
                              proxies=self.proxies, timeout=10).text
        except:
            return ''
    
    def add_proxy(self, url):
        """添加代理前缀到URL"""
        if not url or url.startswith('http://127.0.0.1') or url.startswith('https://127.0.0.1'):
            return url
        return self.proxy_prefix + urllib.parse.quote(url, safe='')
    
    def isVideoFormat(self, url):
        return any(ext in (url or '') for ext in ['.m3u8', '.mp4', '.ts'])
    
    def manualVideoCheck(self):
        return False
    
    def destroy(self):
        pass
    
    def homeContent(self, filter):
        result = {}
        try:
            cateManual = [
                {'type_name': '日本有碼', 'type_id': '47'},
                {'type_name': '日本無碼', 'type_id': '48'},
                {'type_name': '國產AV', 'type_id': '49'},
                {'type_name': '網紅主播', 'type_id': '50'},
            ]
            result['class'] = cateManual
            result['filters'] = {}
        except Exception:
            pass
        return result
    
    def homeVideoContent(self):
        return self.categoryContent('', '1', False, {})
    
    def categoryContent(self, tid, pg, filter, extend):
        pg = str(pg)
        result = {'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999, 'list': []}
        try:
            url = self.host
            if tid:
                if str(tid).startswith('http'):
                    url = str(tid)
                    if pg != '1': url = f"{url}{'&' if '?' in url else '?'}page={pg}"
                elif str(tid).startswith('/'):
                    url = f"{self.host}{tid}"
                    if pg != '1': url = f"{url}{'&' if '?' in url else '?'}page={pg}"
                else:
                    url = f"{self.host}/vod/index.html?type_id={tid}"
                    if pg != '1': url = f"{self.host}/vod/index.html?page={pg}&type_id={tid}"
            
            # 使用fetch方法替代直接调用session.get
            html = self.fetch(url)
            if not html: 
                result['list'] = []
                return result
                
            if pq is None: raise RuntimeError('PyQuery 未安装，无法解析列表页面')
            doc = pq(html)
            
            def _parse_list(doc):
                vlist = []
                seen = set()
                for a in doc('a[href*="/vod/player.html"]').items():
                    href = a.attr('href') or ''
                    if not href: continue
                    full = href if href.startswith('http') else f"{self.host}{href}"
                    m = re.search(r'[?&]id=(\d+)', full)
                    if not m: continue
                    vid = m.group(1)
                    if vid in seen: continue
                    seen.add(vid)
                    img_el = a('img')
                    title = img_el.attr('alt') or a.attr('title') or (a.text() or '').strip()
                    if not title:
                        li = a.parents('li').eq(0)
                        title = li.find('h1,h2,h3').text().strip() if li else ''
                        if not title: title = f"视频{vid}"
                    img = img_el.attr('src') or img_el.attr('data-src') or ''
                    if img and not img.startswith('http'): img = f"{self.host}{img}"
                    
                    # 添加代理前缀到图片地址
                    img = self.add_proxy(img)
                    
                    vlist.append({
                        'vod_id': full, 'vod_name': title, 'vod_pic': img, 'vod_remarks': '',
                        'style': {'ratio': 1.33, 'type': 'rect'}
                    })
                    if len(vlist) >= 90: break
                return vlist
            
            result['list'] = _parse_list(doc)
            page_numbers = []
            for a in doc('a[href*="/vod/index.html?page="]').items():
                t = (a.text() or '').strip()
                if t.isdigit(): page_numbers.append(int(t))
            if page_numbers: result['pagecount'] = max(page_numbers)
        except Exception:
            result['list'] = []
        return result
    
    def detailContent(self, ids):
        try:
            url = ids[0] if isinstance(ids, list) else str(ids)
            if not url: return {'list': []}
            if not url.startswith('http'): url = f"{self.host}/vod/player.html?id={url}"
            
            # 使用fetch方法替代直接调用session.get
            html = self.fetch(url)
            if not html: 
                return {'list': []}
                
            if pq is None: raise RuntimeError('PyQuery 未安装，无法解析详情页面')
            doc = pq(html)
            title = doc('meta[property="og:title"]').attr('content') or doc('h1').text().strip() or 'Javbobo 视频'
            vod_pic = doc('meta[property="og:image"]').attr('content') or ''
            if not vod_pic:
                img_el = doc('img').eq(0)
                vod_pic = img_el.attr('src') or img_el.attr('data-src') or ''
                if vod_pic and not vod_pic.startswith('http'): vod_pic = f"{self.host}{vod_pic}"
            
            # 添加代理前缀到图片地址
            vod_pic = self.add_proxy(vod_pic)
            
            line_id = None
            m = re.search(r"lineId\s*=\s*Number\('?(\d+)'?\)", html)
            if m: line_id = m.group(1)
            if not line_id:
                m = re.search(r"var\s+Iyplayer\s*=\s*\{[^}]*id:(\d+)", html)
                if m: line_id = m.group(1)
            play_id = line_id or url
            vod = {
                'vod_name': title, 'vod_pic': vod_pic, 'vod_content': '',
                'vod_play_from': 'Javbobo', 'vod_play_url': f'正片${play_id}'
            }
            return {'list': [vod]}
        except Exception:
            return {'list': []}
    
    def searchContent(self, key, quick, pg="1"):
        try:
            params = {'wd': key}
            url = f"{self.host}/index.html"
            
            # 使用fetch方法替代直接调用session.get
            html = self.fetch(url, params=params)
            if not html: 
                return {'list': []}
                
            if pq is None: raise RuntimeError('PyQuery 未安装，无法解析搜索页面')
            doc = pq(html)
            vlist = []
            seen = set()
            for a in doc('a[href*="/vod/player.html"]').items():
                href = a.attr('href') or ''
                if not href: continue
                full = href if href.startswith('http') else f"{self.host}{href}"
                m = re.search(r'[?&]id=(\d+)', full)
                if not m: continue
                vid = m.group(1)
                if vid in seen: continue
                seen.add(vid)
                img_el = a('img')
                title = img_el.attr('alt') or a.attr('title') or (a.text() or '').strip()
                img = img_el.attr('src') or img_el.attr('data-src') or ''
                if img and not img.startswith('http'): img = f"{self.host}{img}"
                
                # 添加代理前缀到图片地址
                img = self.add_proxy(img)
                
                vlist.append({
                    'vod_id': full, 'vod_name': title or f'视频{vid}', 'vod_pic': img,
                    'vod_remarks': '', 'style': {'ratio': 1.33, 'type': 'rect'}
                })
                if len(vlist) >= 60: break
            return {'list': vlist, 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}
        except Exception:
            return {'list': []}
    
    def playerContent(self, flag, id, vipFlags):
        try:
            line_id = None
            sid = str(id or '')
            if re.fullmatch(r'\d+', sid):
                line_id = sid
            elif sid.startswith('http'):
                if self.isVideoFormat(sid):
                    # 添加代理前缀到视频地址
                    proxied_url = self.add_proxy(sid)
                    headers = {'User-Agent': self.headers['User-Agent'], 'Referer': f'{self.host}/'}
                    return {'parse': 0, 'url': proxied_url, 'header': headers}
                
                # 使用fetch方法替代直接调用session.get
                html = self.fetch(sid)
                if not html: 
                    return {'parse': 0, 'url': '', 'header': {}}
                    
                m = re.search(r"lineId\s*=\s*Number\('?(\d+)'?\)", html)
                if m: line_id = m.group(1)
                if not line_id:
                    m = re.search(r"var\s+Iyplayer\s*=\s*\{[^}]*id:(\d+)", html)
                    if m: line_id = m.group(1)
            else:
                if sid.startswith('/'): page_url = f"{self.host}{sid}"
                else: page_url = f"{self.host}/vod/player.html?id={sid}"
                
                # 使用fetch方法替代直接调用session.get
                html = self.fetch(page_url)
                if not html: 
                    return {'parse': 0, 'url': '', 'header': {}}
                    
                m = re.search(r"lineId\s*=\s*Number\('?(\d+)'?\)", html)
                if m: line_id = m.group(1)
                if not line_id:
                    m = re.search(r"var\s+Iyplayer\s*=\s*\{[^}]*id:(\d+)", html)
                    if m: line_id = m.group(1)
            if not line_id: raise ValueError('未能获取到播放线路ID(lineId)')
            api = f"{self.host}/openapi/playline/{line_id}"
            
            # 使用fetch方法替代直接调用session.get
            txt = self.fetch(api)
            if not txt: 
                return {'parse': 0, 'url': '', 'header': {}}
                
            j = None
            try: j = json.loads(txt)
            except Exception: j = {}
            m3u8_url = ''
            if isinstance(j, dict): m3u8_url = j.get('info', {}).get('file') or j.get('file') or ''
            
            # 添加代理前缀到视频地址
            m3u8_url = self.add_proxy(m3u8_url)
            
            headers = {'User-Agent': self.headers['User-Agent'], 'Referer': f'{self.host}/'}
            return {'parse': 0, 'url': m3u8_url, 'header': headers}
        except Exception:
            return {'parse': 0, 'url': '', 'header': {}}
