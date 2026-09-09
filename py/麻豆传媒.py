import json
import re
import sys
from urllib.parse import urlparse

import requests
from pyquery import PyQuery as pq
sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def init(self, extend=""):
        try:
            self.proxies = json.loads(extend)
        except:
            self.proxies = {}
        # 代理前缀（用户反馈的可用形式）
        self.proxy_prefix = 'http://127.0.0.1:10079/p/0/127.0.0.1:10172/'
        # 可通过传入 extend JSON 开启前缀代理模式：{"use_prefix": true}
        self.use_proxy_prefix = bool(self.proxies.get('use_prefix')) if isinstance(self.proxies, dict) else False
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
        }
        self.host = self.get_working_host()
        self.headers.update({'Origin': self.host, 'Referer': f"{self.host}/"})
        print(f"使用站点: {self.host}")

    def getName(self):
        return "传媒"

    def isVideoFormat(self, url):
        return any(ext in (url or '') for ext in ['.m3u8', '.mp4', '.ts'])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def get_working_host(self):
        dynamic_urls = [
            'https://madou.net'
        ]
        for url in dynamic_urls:
            try:
                response = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=10)
                if response.status_code == 200:
                    return url
            except Exception:
                continue
        return dynamic_urls[0]

    def homeContent(self, filter):
        try:
            response = requests.get(self.host, headers=self.headers, proxies=self.proxies, timeout=15)
            if response.status_code != 200:
                return {'class': [], 'list': []}
            data = self.getpq(response.text)

            classes = []
            seen = set()
            # PC导航主分类
            for item in data('#pcNav .pcNavList > a.pcNavItem').items():
                name = (item.find('.pcNavName').text() or item.text() or '').strip()
                href = (item.attr('href') or '').strip()
                if not name or not href or href.startswith('http'):
                    continue
                if href == '/':
                    href = '/home'
                tid = href if href.startswith('/') else f'/{href}'
                key = f'{name}|{tid}'
                if key not in seen:
                    classes.append({'type_name': name, 'type_id': tid.rstrip('/') + ('/' if tid.startswith('/category/') else '')})
                    seen.add(key)

            # 子分类
            for sub in data('#pcNav .pcNavList .subNavBox a').items():
                name = (sub.text() or '').strip()
                href = (sub.attr('href') or '').strip()
                if not name or not href or href.startswith('http'):
                    continue
                tid = href if href.startswith('/') else f'/{href}'
                key = f'{name}|{tid}'
                if key not in seen:
                    classes.append({'type_name': name, 'type_id': tid.rstrip('/') + ('/' if tid.startswith('/category/') else '')})
                    seen.add(key)

            # 移动端导航补充
            for m_item in data('#navigation .navigationList a.nav-link').items():
                name = (m_item.text() or '').strip()
                href = (m_item.attr('href') or '').strip()
                if not name or not href or href.startswith('http'):
                    continue
                if href == '/':
                    href = '/home'
                tid = href if href.startswith('/') else f'/{href}'
                key = f'{name}|{tid}'
                if key not in seen:
                    classes.append({'type_name': name, 'type_id': tid.rstrip('/') + ('/' if tid.startswith('/category/') else '')})
                    seen.add(key)

            if not classes:
                classes = [
                    {'type_name': '首页', 'type_id': '/home'},
                    {'type_name': '每日更新', 'type_id': '/category/17202/'},
                ]

            return {'class': classes, 'list': self.getlist(data('#index article, article'))}
        except Exception:
            return {'class': [], 'list': []}

    def homeVideoContent(self):
        try:
            response = requests.get(self.host, headers=self.headers, proxies=self.proxies, timeout=15)
            if response.status_code != 200: return {'list': []}
            data = self.getpq(response.text)
            return {'list': self.getlist(data('#index article, article'))}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            if '@folder' in tid:
                v = self.getfod(tid.replace('@folder', ''))
                return {'list': v, 'page': 1, 'pagecount': 1, 'limit': 90, 'total': len(v)}

            pg = int(pg) if pg else 1

            if tid.startswith('http'):
                full = tid.rstrip('/')
                parsed = urlparse(full)
                base_path = parsed.path or '/'
            else:
                base_path = tid if tid.startswith('/') else f'/{tid}'

            if base_path.startswith('/home'):
                url = f"{self.host}/home" if pg == 1 else f"{self.host}/home/{pg}"
            elif base_path.startswith('/category/'):
                cat_base = base_path.rstrip('/')
                url = f"{self.host}{cat_base}/" if pg == 1 else f"{self.host}{cat_base}/{pg}"
            else:
                base_url = f"{self.host}{base_path}".rstrip('/')
                url = f"{base_url}/" if pg == 1 else f"{base_url}/{pg}/"

            response = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=15)
            if response.status_code != 200:
                return {'list': [], 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 0}

            data = self.getpq(response.text)
            videos = self.getlist(data('#archive article, #index article, article'), tid)
            return {'list': videos, 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}
        except Exception:
            return {'list': [], 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 0}

    def detailContent(self, ids):
        """
        - 兼容单视频详情页的 dplayer/data-url 解析
        - 若为“合集”页面（内含 TOP 列表），生成剧集播放列表（名称来自 .postTitle TOP N），链接指向各篇章详情页
        """
        try:
            url = ids[0] if ids[0].startswith('http') else f"{self.host}{ids[0]}"
            response = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=15)
            data = self.getpq(response.text)

            # 判断是否合集页：标题或页面主标题含“合集”，或存在多个 TOP 项
            page_title = (data('h1.title').text() or data('.post-title').text() or data('title').text() or '').strip()
            top_items = list(data('.postContent .postTitle').items())
            is_collection = ('合集' in page_title) or any(re.search(r'\btop\b', (t.text() or '').lower()) for t in top_items)

            plist = []
            used_names = set()

            if is_collection:
                # 从合集页面生成剧集列表：每个 .postContent 所在的 a[href] 即为章节链接
                episodes = []
                for a in data('a[href]').items():
                    href = (a.attr('href') or '').strip()
                    # 章节链接通常以 /archives/ 开头且内部包含 .postContent/.postTitle
                    if not href or not href.startswith('/') or '/archives/' not in href:
                        continue
                    box = a.find('.postContent .postBox')
                    title = (box.find('.postTitle').text() or '').strip()
                    if not title:
                        # 回退：从 a 内文本尝试抓取 TOP N
                        txt = (a.text() or '').strip()
                        title = txt
                    if not title:
                        continue
                    # 仅收录包含 TOP/top 的条目
                    if not re.search(r'\btop\b', title, re.I):
                        continue
                    # 提取封面
                    img = ''
                    img_el = box.find('img.postimage').eq(0)
                    if img_el:
                        img = (img_el.attr('data-src') or img_el.attr('src') or '').strip()
                    episodes.append({'href': href, 'name': title, 'img': img})

                # 去重并构造播放列表
                for idx, ep in enumerate(episodes, start=1):
                    ep_name = ep['name'] or f'TOP {idx}'
                    base_name = ep_name
                    name = base_name
                    cnt = 2
                    while name in used_names:
                        name = f"{base_name} {cnt}"
                        cnt += 1
                    used_names.add(name)
                    # 集数链接（非直接视频），交给 playerContent 统一加代理/解析
                    ep_url = ep['href'] if ep['href'].startswith('http') else f"{self.host}{ep['href']}"
                    plist.append(f"{name}${ep_url}")

            # 若非合集页，走单视频解析
            if not plist:
                # 1) 旧版 .dplayer data-config（JSON）
                for c, k in enumerate(data('.dplayer').items(), start=1):
                    try:
                        config_attr = k.attr('data-config')
                        if config_attr:
                            config = json.loads(config_attr)
                            video_url = config.get('video', {}).get('url', '')
                            if video_url:
                                ep_name = ''
                                parent = k.parents().eq(0)
                                for _ in range(4):
                                    if not parent: break
                                    heading = parent.find('h2, h3, h4').eq(0).text().strip()
                                    if heading:
                                        ep_name = heading
                                        break
                                    parent = parent.parents().eq(0)
                                base_name = ep_name if ep_name else f"视频{c}"
                                name = base_name
                                count = 2
                                while name in used_names:
                                    name = f"{base_name} {count}"
                                    count += 1
                                used_names.add(name)
                                plist.append(f"{name}${video_url}")
                    except:
                        continue

                # 2) 新版 #dplayer 使用 data-url（可能为相对路径，需补全 /h5/m3u8/ 前缀）
                for c, k in enumerate(data('#dplayer').items(), start=len(plist)+1):
                    try:
                        data_url = (k.attr('data-url') or '').strip()
                        if not data_url:
                            continue
                        if data_url.startswith('http'):
                            video_url = data_url
                        else:
                            video_url = f"{self.host}/h5/m3u8/{data_url}"
                        ep_name = ''
                        parent = k.parents().eq(0)
                        for _ in range(4):
                            if not parent: break
                            heading = parent.find('h1, h2, h3').eq(0).text().strip()
                            if heading:
                                ep_name = heading
                                break
                            parent = parent.parents().eq(0)
                        base_name = ep_name if ep_name else f"在线播放{c}"
                        name = base_name
                        count = 2
                        while name in used_names:
                            name = f"{base_name} {count}"
                            count += 1
                        used_names.add(name)
                        plist.append(f"{name}${video_url}")
                    except:
                        continue

                # 3) 兜底：内容区内“点击观看”类链接
                if not plist:
                    content_area = data('.post-content, article')
                    for i, link in enumerate(content_area('a').items(), start=1):
                        link_text = (link.text() or '').strip()
                        link_href = link.attr('href')
                        if link_href and any(kw in link_text for kw in ['点击观看', '观看', '播放', '视频']):
                            ep_name = link_text.replace('点击观看：', '').replace('点击观看', '').strip() or f"视频{i}"
                            if not link_href.startswith('http'):
                                link_href = f"{self.host}{link_href}" if link_href.startswith('/') else f"{self.host}/{link_href}"
                            plist.append(f"{ep_name}${link_href}")

            play_url = '#'.join(plist) if plist else f"未找到视频源${url}"

            # 内容（标签）
            vod_content = ''
            try:
                tags = []
                seen_names = set()
                seen_ids = set()
                tag_links = data('.tags a, .keywords a, .post-tags a, .tagBox a, .tagBox a.tagItem')
                candidates = []
                for k in tag_links.items():
                    title = (k.text() or '').strip()
                    href = (k.attr('href') or '').strip()
                    if title and href:
                        candidates.append({'name': title, 'id': href})
                candidates.sort(key=lambda x: len(x['name']), reverse=True)
                for item in candidates:
                    name = item['name']
                    id_ = item['id']
                    if id_ in seen_ids: continue
                    is_duplicate = False
                    for seen in seen_names:
                        if name in seen:
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        target = json.dumps({'id': id_, 'name': name})
                        tags.append(f'[a=cr:{target}/]{name}[/a]')
                        seen_names.add(name)
                        seen_ids.add(id_)
                if tags:
                    vod_content = ' '.join(tags)
                else:
                    vod_content = data('.post-title').text()
            except Exception:
                vod_content = '获取标签失败'

            if not vod_content:
                vod_content = data('h1').text() or '麻豆传媒'

            return {'list': [{'vod_play_from': '麻豆传媒', 'vod_play_url': play_url, 'vod_content': vod_content}]}
        except Exception:
            return {'list': [{'vod_play_from': '麻豆传媒', 'vod_play_url': '获取失败'}]}

    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg) if pg else 1
            url = f"{self.host}/search/{key}/" if pg == 1 else f"{self.host}/search/{key}/{pg}/"
            response = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=15)
            doc = self.getpq(response.text)
            videos = []
            for k in doc('article').items():
                # 尽量直接取首个链接和标题
                a = k if hasattr(k, 'is_') and k.is_('a') else k('a').eq(0)
                href = (a.attr('href') or '').strip()
                title = (k('h2').text() or k('.entry-title').text() or k('.post-title').text() or '').strip()
                if not title and hasattr(k, 'is_') and k.is_('a'):
                    title = (k.text() or '').strip()
                if href and title:
                    # 简单取封面，避免复杂判断
                    card_html = k.outer_html() if hasattr(k, 'outer_html') else str(k)
                    img = self.getimg(k('script').text(), k, card_html) or ''
                    videos.append({
                        'vod_id': href,            # 不加 @folder，保持为直接详情链接
                        'vod_name': title,
                        'vod_pic': img,
                        'vod_remarks': k('time').text() or '',
                        'vod_tag': '',              # 搜索结果不标记为 folder
                        'style': {"type": "rect", "ratio": 1.33}
                    })
            return {'list': videos, 'page': pg, 'pagecount': 9999}
        except Exception:
            return {'list': [], 'page': pg, 'pagecount': 9999}


    def playerContent(self, flag, id, vipFlags):
        parse = 0 if self.isVideoFormat(id) else 1
        full = id
        if not str(id).startswith('http'):
            full = f"{self.host}{id}" if str(id).startswith('/') else f"{self.host}/{id}"
        url = f"{self.proxy_prefix}{full}"
        return {'parse': parse, 'url': url, 'header': self.headers}

    def getlist(self, data, tid=''):
        videos = []
        is_folder_hint = '/mrdg' in (tid or '')
        # 页面主标题也可作为合集信号
        root = data.parents('html') if hasattr(data, 'parents') else None
        page_title = ''
        try:
            doc = data
            page_title = (doc('h1.title').text() or doc('.post-title').text() or doc('title').text() or '').strip()
        except:
            pass
        for k in data.items():
            a = k if k.is_('a') else k('a').eq(0)
            href = (a.attr('href') or '').strip()
            title = (k('h2').text() or k('.entry-title').text() or k('.post-title').text() or '').strip()
            if not title and k.is_('a'):
                title = (k.text() or '').strip()
            if href and title:
                card_html = k.outer_html() if hasattr(k, 'outer_html') else str(k)
                img = self.getimg(k('script').text(), k, card_html)
                vod_pic = img if img else ''
                is_collection = any(kw in title or kw in page_title for kw in ('合集', '榜单'))
                videos.append({
                    'vod_id': f"{href}{'@folder' if (is_collection or is_folder_hint) else ''}",
                    'vod_name': title,
                    'vod_pic': vod_pic,
                    'vod_remarks': k('time').text() or '',
                    'vod_tag': 'folder' if (is_collection or is_folder_hint) else '',
                    'style': {"type": "rect", "ratio": 1.33}
                })
        return videos

    def getfod(self, id):
        url = f"{self.host}{id}" if not id.startswith('http') else id
        html = ''
        try:
            html = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=15).text
        except:
            html = ''
        doc = self.getpq(html)
        videos = []
        # 遍历所有 a[href]，寻找包含 .postContent 的块
        for a in doc('a[href]').items():
            href = (a.attr('href') or '').strip()
            if not href or '/archives/' not in href:
                continue
            box = a.find('.postContent .postBox')
            title = (box.find('.postTitle').text() or '').strip()
            if not title:
                continue
            if not re.search(r'\btop\b', title, re.I):
                continue
            # 图片
            img = ''
            img_el = box.find('img.postimage').eq(0)
            if img_el:
                img = (img_el.attr('data-src') or img_el.attr('src') or '').strip()
            # 规范化 href
            full = href if href.startswith('http') else f"{self.host}{href}"
            videos.append({
                'vod_id': full,
                'vod_name': title,
                'vod_pic': self._proc_url(img) if img else '',
                'vod_remarks': title
            })
        return videos

    def getimg(self, text, elem=None, html_content=None):
        if m := re.search(r"loadBannerDirect\('([^']+)'", text or ''):
            return self._proc_url(m.group(1))

        def pick_img_from_elem(el):
            try:
                if hasattr(el, 'is_') and el.is_('img'):
                    for attr in ['data-src', 'data-original', 'src']:
                        v = (el.attr(attr) or '').strip()
                        if v and not v.startswith('blob:'):
                            return v
                for img in el('img').items():
                    for attr in ['data-src', 'data-original', 'src']:
                        v = (img.attr(attr) or '').strip()
                        if v and not v.startswith('blob:'):
                            return v
            except:
                pass
            return ''

        if elem is not None:
            picked = pick_img_from_elem(elem)
            if picked:
                return self._proc_url(picked)

        if html_content is None and elem is not None:
            html_content = elem.outer_html() if hasattr(elem, 'outer_html') else str(elem)
        if not html_content:
            return ''

        html_content = html_content.replace('&quot;', '"').replace('&apos;', "'").replace('&amp;', '&')

        if 'data:image' in html_content:
            m = re.search(r'(data:image/[a-zA-Z0-9+/=;,]+)', html_content)
            if m: return self._proc_url(m.group(1))

        m = re.search(r'(https?://[^"\'\s)]+\.(?:jpg|png|jpeg|webp))', html_content, re.I)
        if m: return self._proc_url(m.group(1))

        if 'url(' in html_content:
            m = re.search(r'url\s*\(\s*[\'\"]?([^\"\'\)]+)[\'\"]?\s*\)', html_content, re.I)
            if m: return self._proc_url(m.group(1))

        return ''

    def _proc_url(self, url):
        if not url:
            return ''
        url = url.strip('\'\" ')
        if not url.startswith('http'):
            url = f"{self.host}{url}" if url.startswith('/') else f"{self.host}/{url}"
        if re.search(r"\.(?:jpg|jpeg|png|webp|gif)(?:\?.*)?$", url, re.I) or ('imgwebsa.shzvsh.cn' in url):
            return f"{self.getProxyUrl()}&type=img&url={url}"
        return f"{self.proxy_prefix}{url}"

    def getpq(self, data):
        try: return pq(data)
        except: return pq(data.encode('utf-8'))

    # —— 最小版图片解密代理 ——
    def aesimg(self, data: bytes) -> bytes:
        try:
            key = b'2019ysapp7527'
            arr = bytearray(data)
            n = 100 if len(arr) >= 100 else len(arr)
            klen = len(key)
            for i in range(n):
                arr[i] ^= key[i % klen]
            return bytes(arr)
        except:
            return data

    def localProxy(self, param):
        try:
            type_ = param.get('type')
            url = param.get('url')
            if type_ == 'img' and url:
                res = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=10)
                content = self.aesimg(res.content)
                ctype = 'image/jpeg'
                if content.startswith(b'\x89PNG'):
                    ctype = 'image/png'
                elif content.startswith(b'GIF8'):
                    ctype = 'image/gif'
                elif content.startswith(b'RIFF') and b'WEBP' in content[8:16]:
                    ctype = 'image/webp'
                elif content.startswith(b'\xff\xd8'):
                    ctype = 'image/jpeg'
                return [200, ctype, content]
            return [404, 'text/plain', b'']
        except:
            return [404, 'text/plain', b'']
