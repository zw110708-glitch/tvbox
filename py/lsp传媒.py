import re
import sys
import urllib.parse
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    def __init__(self):
        self.proxy_host = "http://127.0.0.1:10079/p/0/127.0.0.1:10172/"
        self.base_url = "https://xn--oq2a.lspcm48.lat"
        self.proxy_enabled = True
        
    def getName(self):
        return "lsp传媒（优）"
    
    def init(self, extend):
        pass
        
    def get_proxy_url(self, url):
        """生成代理URL"""
        if not self.proxy_enabled or not url or not url.startswith('http'):
            return url
            
        try:
            # 确保URL编码正确
            encoded_url = urllib.parse.quote(url, safe='')
            proxy_url = f"{self.proxy_host}{encoded_url}"
            return proxy_url
        except:
            return url
        
    def fetch_proxied(self, url, headers=None):
        """使用代理获取内容"""
        if self.proxy_enabled:
            proxy_url = self.get_proxy_url(url)
            print(f"代理请求: {url} -> {proxy_url}")
            return self.fetch(proxy_url, headers=headers)
        else:
            return self.fetch(url, headers=headers)
        
    def homeContent(self, filter):
        result = {}
        classes = []
        try:
            rsp = self.fetch_proxied(f"{self.base_url}/index.php")
            if rsp and rsp.text:
                doc = pq(rsp.text)
                items = doc('.tabs li a')
                for item in items.items():
                    name = item.text()
                    href = item.attr('href')
                    if name and href:
                        match = re.search(r'/(\d+).html', href)
                        if match:
                            classes.append({
                                'type_name': name,
                                'type_id': match.group(1)
                            })
        except Exception as e:
            print(f"homeContent error: {e}")
            
        result['class'] = classes
        return result

    def homeVideoContent(self):
        result = {}
        return result

    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        videos = []
        try:
            url = f"{self.base_url}/index.php/vod/type/id/{tid}/page/{pg}.html"
            rsp = self.fetch_proxied(url)
            if rsp and rsp.text:
                doc = pq(rsp.text)
                items = doc('.grid .grid__item')
                for item in items.items():
                    a = item.find('a')
                    href = a.attr('href')
                    name = item.find('h3').text()
                    if not name or not href:
                        continue
                        
                    img = item.find('img').attr('data-original') or item.find('img').attr('src')
                    desc = item.find('.duration-video').text() or ''
                    
                    # 处理相对路径的图片URL
                    if img and not img.startswith('http'):
                        if img.startswith('//'):
                            img = f"https:{img}"
                        else:
                            img = f"{self.base_url}{img}" if img.startswith('/') else f"{self.base_url}/{img}"
                    
                    # 图片也通过代理
                    img_proxy = self.get_proxy_url(img) if img else ''
                    
                    videos.append({
                        'vod_id': href,
                        'vod_name': name,
                        'vod_pic': img_proxy,
                        'vod_remarks': desc
                    })
        except Exception as e:
            print(f"categoryContent error: {e}")
            
        result['list'] = videos
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def detailContent(self, array):
        result = {}
        if not array or not array[0]:
            return result
            
        try:
            aid = array[0]
            # 处理详情页URL
            if aid.startswith('http'):
                url = aid
            elif aid.startswith('/'):
                url = f"{self.base_url}{aid}"
            else:
                url = f"{self.base_url}/{aid}"
                
            print(f"详情页请求: {url}")
            rsp = self.fetch_proxied(url)
            if not rsp or not rsp.text:
                print("详情页请求失败")
                return result
                
            html = rsp.text
            doc = pq(html)
            
            # 提取视频信息
            title = doc('.section-header__title--video').text() or doc('title').text() or ''
            vod_pic = doc('.xgplayer-poster').attr('style') or doc('meta[property="og:image"]').attr('content') or ''
            description = doc('.video-footer__description').text() or doc('meta[name="description"]').attr('content') or ''
            
            vod = {
                'vod_id': aid,
                'vod_name': title,
                'vod_pic': vod_pic,
                'vod_remarks': description,
                'vod_content': description,
                'vod_play_from': '默认线路',
                'vod_play_url': ''
            }
            
            # 清理封面图片URL
            if 'background-image:' in vod['vod_pic']:
                match = re.search(r'url$$["\']?(.*?)["\']?$$', vod['vod_pic'])
                if match:
                    vod['vod_pic'] = match.group(1)
            
            # 处理图片URL
            if vod['vod_pic'] and not vod['vod_pic'].startswith('http'):
                if vod['vod_pic'].startswith('//'):
                    vod['vod_pic'] = f"https:{vod['vod_pic']}"
                else:
                    vod['vod_pic'] = f"{self.base_url}{vod['vod_pic']}" if vod['vod_pic'].startswith('/') else f"{self.base_url}/{vod['vod_pic']}"
            
            # 图片代理
            vod['vod_pic'] = self.get_proxy_url(vod['vod_pic']) if vod['vod_pic'] else ''
            
            # 提取播放URL - 多种方法尝试
            play_urls = []
            
            # 方法1: 从JavaScript配置中提取
            script_patterns = [
                r'let player = new HlsJsPlayer\s*$$\s*({.*?})\s*$$',
                r'var player = new HlsJsPlayer\s*$$\s*({.*?})\s*$$',
                r'player\s*=\s*new HlsJsPlayer\s*$$\s*({.*?})\s*$$',
                r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"',
                r'file\s*:\s*"([^"]+\.m3u8[^"]*)"',
                r'src\s*:\s*"([^"]+\.m3u8[^"]*)"'
            ]
            
            for pattern in script_patterns:
                matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]
                    if '.m3u8' in match and match not in play_urls:
                        play_urls.append(match)
            
            # 方法2: 直接搜索m3u8链接
            m3u8_matches = re.findall(r'https?://[^\s"\']+\.m3u8[^\s"\']*', html, re.IGNORECASE)
            for match in m3u8_matches:
                if match not in play_urls:
                    play_urls.append(match)
            
            # 方法3: 从iframe中提取
            iframe_src = doc('iframe').attr('src') or doc('embed').attr('src') or doc('video source').attr('src')
            if iframe_src and iframe_src not in play_urls:
                play_urls.append(iframe_src)
            
            # 选择第一个有效的播放URL
            play_url = play_urls[0] if play_urls else ""
            
            if play_url:
                # 处理相对路径的播放URL
                if play_url.startswith('//'):
                    play_url = f"https:{play_url}"
                elif play_url.startswith('/'):
                    play_url = f"{self.base_url}{play_url}"
                elif not play_url.startswith('http'):
                    play_url = f"{self.base_url}/{play_url}"
                
                vod['vod_play_url'] = f'正片${play_url}'
                print(f"找到播放URL: {play_url}")
            else:
                print("未找到播放URL")
                # 如果没有找到播放URL，尝试使用详情页URL作为播放地址
                vod['vod_play_url'] = f'正片${url}'
            
            result['list'] = [vod]
            
        except Exception as e:
            print(f"detailContent error: {e}")
            import traceback
            traceback.print_exc()
            
        return result

    def searchContent(self, key, quick, page='1'):
        result = {}
        videos = []
        try:
            if not key:
                return result
                
            url = f"{self.base_url}/index.php/vod/search/wd/{urllib.parse.quote(key)}/page/{page}.html"
            rsp = self.fetch_proxied(url)
            if rsp and rsp.text:
                doc = pq(rsp.text)
                items = doc('.grid .grid__item')
                for item in items.items():
                    a = item.find('a')
                    href = a.attr('href')
                    name = item.find('h3').text()
                    if not name or not href:
                        continue
                        
                    img = item.find('img').attr('data-original') or item.find('img').attr('src')
                    desc = item.find('.duration-video').text() or ''
                    
                    # 处理相对路径
                    if img and not img.startswith('http'):
                        if img.startswith('//'):
                            img = f"https:{img}"
                        else:
                            img = f"{self.base_url}{img}" if img.startswith('/') else f"{self.base_url}/{img}"
                    
                    videos.append({
                        'vod_id': href,
                        'vod_name': name,
                        'vod_pic': self.get_proxy_url(img) if img else '',
                        'vod_remarks': desc
                    })
        except Exception as e:
            print(f"searchContent error: {e}")
            
        result['list'] = videos
        return result

    def playerContent(self, flag, id, vipFlags):
        result = {}
        try:
            if not id:
                return result
                
            print(f"播放器请求: {id}")
            
            # 如果id已经是视频链接，直接代理
            if id.startswith('http') and ('.m3u8' in id or '.mp4' in id or '.flv' in id):
                result["parse"] = 0
                result["playUrl"] = ''
                result["url"] = self.get_proxy_url(id)
                result["header"] = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': f'{self.base_url}/'
                }
                print(f"直接播放: {result['url']}")
                return result
            
            # 否则重新获取详情页提取播放地址
            detail_result = self.detailContent([id])
            if detail_result and 'list' in detail_result and detail_result['list']:
                vod = detail_result['list'][0]
                play_url = vod.get('vod_play_url', '')
                
                if play_url and '$' in play_url:
                    # 提取实际的播放URL
                    actual_url = play_url.split('$')[-1]
                    if actual_url:
                        result["parse"] = 0
                        result["playUrl"] = ''
                        result["url"] = self.get_proxy_url(actual_url)
                        result["header"] = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                            'Referer': f'{self.base_url}/'
                        }
                        print(f"提取播放: {result['url']}")
                        return result
            
            # 如果以上方法都失败，尝试直接使用ID作为URL
            result["parse"] = 0
            result["playUrl"] = ''
            result["url"] = self.get_proxy_url(id)
            result["header"] = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': f'{self.base_url}/'
            }
            print(f"备用播放: {result['url']}")
            
        except Exception as e:
            print(f"playerContent error: {e}")
            import traceback
            traceback.print_exc()
            
        return result

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return {}