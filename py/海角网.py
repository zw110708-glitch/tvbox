# coding: utf-8
import json
import re
import sys
import hashlib
import html
from base64 import b64decode, b64encode
from urllib.parse import quote

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider as BaseSpider

img_cache = {}


class Spider(BaseSpider):

    def init(self, extend=""):
        try:
            self.proxies = json.loads(extend)
        except:
            self.proxies = {"http": "http://127.0.0.1:10172",
              "https": "http://127.0.0.1:10172"}

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
        return "海角网"

    def isVideoFormat(self, url):
        return any(ext in (url or '') for ext in ['.m3u8', '.mp4', '.ts'])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        global img_cache
        img_cache.clear()

    def get_working_host(self):
        """优先使用主站，避免初始化探测导致变慢。"""
        candidates = [
            'https://www.hjw01.com',
            'https://bad.vqddyqx.cc'
        ]
        for url in candidates:
            try:
                r = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=6)
                r.encoding = 'utf-8'
                if r.status_code == 200:
                    return url
            except Exception:
                continue
        return candidates[0]

    def _get_html(self, url, timeout=15):
        r = requests.get(url, headers=self.headers, proxies=self.proxies, timeout=timeout)
        r.encoding = 'utf-8'
        return r

    # ------------------------
    # 编码修复（页面文本）
    # ------------------------

    def _fix_text(self, s: str) -> str:
        if not s:
            return ''
        s = (s or '').strip()
        try:
            s = html.unescape(s)
        except:
            pass
        if any(ch in s for ch in ('æ', 'å', 'ä', 'Ã', 'Â','è','£','éª','é','¼é','ç²¾','ç½','çº','¢','©','±ç','¦')):
            try:
                return s.encode('latin1', 'ignore').decode('utf-8', 'ignore').strip()
            except:
                pass
        return s.strip()

    def _sanitize_url(self, u: str) -> str:
        if not u:
            return ''
        u = (u or '').strip().strip('"\'')
        # 关键：把 HTML 实体与转义还原成真实直链
        # 例如：\/= /，&amp;= &
        try:
            u = html.unescape(u)
        except:
            pass
        u = u.replace('\\/', '/')
        return u

    def _make_abs(self, href: str) -> str:
        href = (href or '').strip()
        if not href:
            return ''
        href = self._sanitize_url(href)
        if href.startswith('http'):
            return href
        if href.startswith('/'):
            return f"{self.host}{href}"
        return f"{self.host}/{href}"

    # ------------------------
    # 分类/首页
    # ------------------------

    def _abs_url(self, href: str) -> str:
        href = (href or '').strip()
        if not href or href == '#':
            return ''
        if href.lower().startswith('javascript:'):
            return ''
        if href.startswith('/'):
            return href
        if href.startswith('http'):
            try:
                from urllib.parse import urlparse
                u = urlparse(href)
                host_u = urlparse(self.host)
                if u.netloc and host_u.netloc and u.netloc == host_u.netloc:
                    return u.path if u.path else '/'
            except:
                pass
            return href
        return '/' + href

    def _collect_classes(self, data):
        """从首页 HTML 中提取分类（使用你上面那份代码的分类提取逻辑）。"""
        classes = []
        seen = set()

        selectors = [
            '.xqbj-main-menu a',
            '.tabs_nav_scrolling a',
        ]

        for sel in selectors:
            for a in data(sel).items():
                name = (a.text() or '').strip()
                href = self._abs_url(a.attr('href'))

                if not name or not href:
                    continue

                # 屏蔽不需要展示的入口
                if name in ('全部分类', '我的订阅', '原创招募'):
                    continue

                if any(x in href for x in ['/my/', '/history/', '/login', '/register', '/logout', '/ai/', '/qun.html', '/tgq.html', '/twitter.html', '/swhz.html']):
                    continue
                if href.startswith('http') and self.host not in href:
                    continue

                h0 = href.rstrip('/')
                # 入口指向修正
                if name == '海角博主':
                    href = '/authors_blogger/creator/'
                elif name == '热门榜单':
                    href = '/authors_up/post-all/'
                elif name == '海角社区':
                    href = '/communitys/video/'
                elif h0 in ('/authors_up', '/authors_up/post-1', '/authors_up/post-all'):
                    href = '/authors_up/post-all/'
                elif h0 in ('/authors_blogger/original', '/authors_blogger/creator'):
                    href = '/authors_blogger/creator/'

                key = f"{name}::{href}"
                if key in seen:
                    continue
                seen.add(key)

                classes.append({'type_name': name, 'type_id': href})

            if classes:
                break

        if not classes:
            classes = [
                {'type_name': '海角首页', 'type_id': '/'},
                {'type_name': '海角热门', 'type_id': '/order/hot/'},
                {'type_name': '今日更新', 'type_id': '/order/today/'},
                {'type_name': '海角乱伦', 'type_id': '/category/hjll/'},
                {'type_name': '海角原创', 'type_id': '/category/hjyc/'},
            ]
        return classes

    def homeContent(self, filter):
        try:
            response = self._get_html(self.host, timeout=15)
            if response.status_code != 200:
                return {'class': [], 'list': []}
            data = self.getpq(response.text)
            classes = self._collect_classes(data)
            home_items = data('.xqbj-list-rows')
            if not home_items or len(home_items) == 0:
                home_items = data('#index article, article')
            return {'class': classes, 'list': self.getlist(home_items)}
        except Exception:
            return {'class': [], 'list': []}

    def homeVideoContent(self):
        try:
            response = self._get_html(self.host, timeout=15)
            if response.status_code != 200:
                return {'list': []}
            data = self.getpq(response.text)
            return {'list': self.getlist(data('#index article, article'))}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        """分类列表：增加海角社区视频(/communitys/video/)的分页规则：/2/。"""
        try:
            # 二级列表（folder）需要支持翻页：
            # - 作者页：/author/xxx/new/page/2/
            # - 标签页：/tag/xxx/2/
            if '@folder' in (tid or ''):
                pg = int(pg) if pg else 1
                fid = (tid or '').replace('@folder', '')
                v = self.getfod(fid, pg)
                return {'list': v, 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}

            pg = int(pg) if pg else 1
            tid = (tid or '').strip()
            if not tid:
                tid = '/'

            if tid.startswith('http'):
                base_url = tid.rstrip('/')
            else:
                path = tid if tid.startswith('/') else f"/{tid}"
                base_url = f"{self.host}{path}".rstrip('/')

            if pg == 1:
                url = f"{base_url}/"
            else:
                try:
                    from urllib.parse import urlparse
                    path = urlparse(base_url).path or '/'
                except:
                    path = '/'

                if path.startswith('/communitys/'):
                    url = f"{base_url}/{pg}/"
                elif '/order/' in path:
                    url = f"{base_url}/page/{pg}/"
                elif '/tag/' in path:
                    url = f"{base_url}/{pg}/"
                elif '/author/' in path:
                    url = f"{base_url}/page/{pg}/"
                elif path.startswith('/authors_up/post-all'):
                    url = f"{base_url}/{pg}/"
                elif path.startswith('/authors_up/'):
                    if re.search(r'/post-\d+$', base_url):
                        url = re.sub(r'/post-\d+$', f'/post-{pg}', base_url) + '/'
                    else:
                        url = f"{self.host}/authors_up/post-{pg}/"
                elif path.startswith('/authors_blogger/'):
                    url = f"{base_url}/page/{pg}/"
                elif path.startswith('/authors_') or path.startswith('/tags') or path.startswith('/date'):
                    url = f"{base_url}/page/{pg}/"
                elif '/category/' in path:
                    url = f"{base_url}/{pg}/"
                else:
                    url = f"{self.host}/page/{pg}/"

            response = self._get_html(url, timeout=15)
            if response.status_code != 200:
                return {'list': [], 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 0}

            data = self.getpq(response.text)

            list_root = data('#archive .xqbj-list').eq(0)
            if not list_root or len(list_root) == 0:
                list_root = data('.xqbj-list').eq(0)
            if not list_root or len(list_root) == 0:
                list_root = data('#archive')
            if not list_root or len(list_root) == 0:
                list_root = data('main')

            items = list_root.find('.xqbj-list-rows')
            if not items or len(items) == 0:
                items = list_root.find('article')
            if not items or len(items) == 0:
                items = data('#archive article, #index article, article')

            try:
                from urllib.parse import urlparse
                p0 = urlparse(url).path or ''
            except:
                p0 = ''

            # ------------------------------
            # 仅修复用户提到的 5 个分类
            # ------------------------------
            if p0.startswith('/authors_blogger/creator'):
                # 1) 海角博主：一级作者卡片列表
                items = data('a.rank-card[href^="/author/"]')
            elif p0.startswith('/authors_up/post-all'):
                # 5) 热门榜单：一级作者卡片列表
                items = data('a.rank-card[href^="/author/"]')
            elif p0.startswith('/authors_hot'):
                # 2) 海角热搜：一级视频榜单
                items = data('a.rank-item[href*="/archives/"]')
            elif p0.startswith('/tags'):
                # 3) 海角标签：一级标签卡片（必须含 h3）
                items = data('a[href^="/tag/"] h3').parents('a')
            elif p0.startswith('/date'):
                # 4) 海角往期：一级视频列表（li + a.history-text）
                items = data('a.history-text[href*="/archives/"]')
            else:
                if not items or len(items) == 0:
                    items = data('.refresh-list a.item[href*="/archives/"], #archive article, #index article, article')

            videos = self.getlist(items, tid)
            return {'list': videos, 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}
        except Exception:
            return {'list': [], 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 0}

    # ------------------------
    # 详情（保持原逻辑，只做 _fix_text 修正）
    # ------------------------

    def detailContent(self, ids):
        try:
            url = ids[0] if ids[0].startswith('http') else f"{self.host}{ids[0]}"
            response = self._get_html(url, timeout=15)
            data = self.getpq(response.text)

            plist = []
            used_names = set()
            if data('.dplayer'):
                for c, k in enumerate(data('.dplayer').items(), start=1):
                    try:
                        config_attr = k.attr('data-config')
                        if config_attr:
                            config = json.loads(config_attr)
                            video_url = (config.get('video', {}) or {}).get('url', '')
                            video_url = self._sanitize_url(video_url)
                            if video_url:
                                ep_name = ''
                                parent = k.parents().eq(0)
                                for _ in range(4):
                                    if not parent:
                                        break
                                    heading = self._fix_text(parent.find('h2, h3, h4').eq(0).text())
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

            if not plist:
                content_area = data('.post-content, article')
                for i, link in enumerate(content_area('a').items(), start=1):
                    link_text = self._fix_text(link.text())
                    link_href = self._sanitize_url(link.attr('href') or '')

                    if link_href and any(kw in (link_text or '') for kw in ['点击观看', '观看', '播放', '视频', '第一弹', '第二弹', '第三弹', '第四弹', '第五弹', '第六弹', '第七弹', '第八弹', '第九弹', '第十弹']):
                        ep_name = self._fix_text((link_text or '').replace('点击观看：', '').replace('点击观看', '').strip())
                        if not ep_name:
                            ep_name = f"视频{i}"
                        if not link_href.startswith('http'):
                            link_href = self._make_abs(link_href)
                        plist.append(f"{ep_name}${link_href}")

            play_url = '#'.join(plist) if plist else f"未找到视频源${url}"

            vod_content = ''
            try:
                tags = []
                seen_names = set()
                seen_ids = set()

                vod_actor = ''
                try:
                    actor_tags = []
                    actor_seen = set()
                    for a in data('a[href*="/author/"]').items():
                        name = self._fix_text(a.find('h2').eq(0).text() or a.text())
                        href = self._fix_text(a.attr('href') or '')
                        if not (name and href and '/author/' in href):
                            continue
                        if href in actor_seen:
                            continue
                        actor_seen.add(href)
                        target = json.dumps({'id': href, 'name': name}, ensure_ascii=False)
                        actor_tags.append(f'[a=cr:{target}/]{name}[/a]')
                    vod_actor = ' '.join(actor_tags)
                except:
                    vod_actor = ''

                content_root = data('.post-content, article').eq(0)
                tag_links = data('div.tags-group2 a')
                if not tag_links or len(tag_links) == 0:
                    tag_links = content_root.find('div.tags-group2 a')
                if not tag_links or len(tag_links) == 0:
                    tag_links = content_root.find('.tags a, .keywords a, .post-tags a')

                candidates = []
                for k in tag_links.items():
                    title = self._fix_text(k.text())
                    href = self._fix_text(k.attr('href') or '')
                    if title and href and '/tag/' in href:
                        candidates.append({'name': title, 'id': href})

                candidates.sort(key=lambda x: len(x['name']), reverse=True)

                for item in candidates:
                    name = item['name']
                    id_ = item['id']
                    if id_ in seen_ids:
                        continue
                    is_duplicate = False
                    for seen in seen_names:
                        if name in seen:
                            is_duplicate = True
                            break
                    if is_duplicate:
                        continue
                    target = json.dumps({'id': id_, 'name': name}, ensure_ascii=False)
                    tags.append(f'[a=cr:{target}/]{name}[/a]')
                    seen_names.add(name)
                    seen_ids.add(id_)

                if tags:
                    vod_content = ' '.join(tags)
                else:
                    vod_content = self._fix_text(data('.post-title').text())
            except Exception:
                vod_content = '获取标签失败'
                vod_actor = ''

            if not vod_content:
                vod_content = self._fix_text(data('h1').text()) or '海角网'

            return {'list': [{'vod_play_from': '海角网', 'vod_play_url': play_url, 'vod_content': vod_content, 'vod_actor': vod_actor}]}
        except:
            return {'list': [{'vod_play_from': '海角网', 'vod_play_url': '获取失败'}]}

    # ------------------------
    # 搜索（修复 URL + 列表解析）
    # ------------------------

    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg) if pg else 1
            kq = quote(str(key), safe='')

            if pg == 1:
                url = f"{self.host}/search/{kq}/"
            else:
                url = f"{self.host}/search/{kq}/{pg}/"

            response = self._get_html(url, timeout=15)
            if response.status_code != 200:
                return {'list': [], 'page': pg, 'pagecount': 9999}

            doc = self.getpq(response.text)

            items = doc('.search-result-content .xqbj-list.search .xqbj-list-rows')
            if not items or len(items) == 0:
                items = doc('.xqbj-list.search .xqbj-list-rows')
            if not items or len(items) == 0:
                items = doc('.xqbj-list-rows')

            return {'list': self.getlist(items), 'page': pg, 'pagecount': 9999}
        except:
            return {'list': [], 'page': 1, 'pagecount': 9999}

    def playerContent(self, flag, id, vipFlags):
        # 精简：影视壳子直接吃“真实直链”（不走本地 m3u8/ts 代理，不做兜底拓展）
        url = self._sanitize_url(id or '')
        try:
            from urllib.parse import urlparse
            o = urlparse(url)
            origin = f"{o.scheme}://{o.netloc}" if o.scheme and o.netloc else self.host
        except:
            origin = self.host

        headers = dict(self.headers)
        headers.update({'Origin': origin, 'Referer': f"{self.host}/"})
        return {'parse': 0, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{url}', 'header': headers}

    # ------------------------
    # 代理/解密（原逻辑保持不变）
    # ------------------------

    def localProxy(self, param):
        try:
            type_ = param.get('type')
            url = param.get('url')
            if type_ == 'cache':
                key = param.get('key')
                if content := img_cache.get(key):
                    return [200, 'image/jpeg', content]
                return [404, 'text/plain', b'Expired']
            elif type_ == 'img':
                real_url = self.d64(url) if not url.startswith('http') else url
                res = requests.get(real_url, headers=self.headers, proxies=self.proxies, timeout=10)
                content = self.aesimg(res.content)
                return [200, 'image/jpeg', content]
            elif type_ == 'm3u8':
                return self.m3Proxy(url)
            else:
                return self.tsProxy(url)
        except:
            return [404, 'text/plain', b'']

    def proxy(self, data, type='m3u8'):
        if data and self.proxies:
            return f"{self.getProxyUrl()}&url={self.e64(data)}&type={type}"
        return data

    def m3Proxy(self, url):
        url = self.d64(url)
        res = requests.get(url, headers=self.headers, proxies=self.proxies)
        res.encoding = 'utf-8'
        data = res.text
        base = res.url.rsplit('/', 1)[0]
        lines = []
        for line in data.split('\n'):
            if '#EXT' not in line and line.strip():
                if not line.startswith('http'):
                    line = f"{base}/{line}"
                lines.append(self.proxy(line, 'ts'))
            else:
                lines.append(line)
        return [200, "application/vnd.apple.mpegurl", '\n'.join(lines)]

    def tsProxy(self, url):
        return [200, 'video/mp2t', requests.get(self.d64(url), headers=self.headers, proxies=self.proxies).content]

    def e64(self, text):
        return b64encode(str(text).encode()).decode()

    def d64(self, text):
        return b64decode(str(text).encode()).decode()

    def aesimg(self, data):
        if len(data) < 16:
            return data
        keys = [
            (b'f5d965df75336270', b'97b60394abc2fbe1'),
            (b'75336270f5d965df', b'abc2fbe197b60394')
        ]
        for k, v in keys:
            try:
                dec = unpad(AES.new(k, AES.MODE_CBC, v).decrypt(data), 16)
                if dec.startswith(b'\xff\xd8') or dec.startswith(b'\x89PNG'):
                    return dec
            except:
                pass
            try:
                dec = unpad(AES.new(k, AES.MODE_ECB).decrypt(data), 16)
                if dec.startswith(b'\xff\xd8'):
                    return dec
            except:
                pass
        return data

    # ------------------------
    # 列表/图片
    # ------------------------

    def getlist(self, data, tid=''):
        videos = []
        is_folder = '/mrdg' in (tid or '')

        for k in data.items():
            card_html = k.outer_html() if hasattr(k, 'outer_html') else str(k)

            a = k('a[href*="/archives/"], a[href*="/community/"]').eq(0)
            href = a.attr('href') if a else None

            if not href:
                a = k('a.rank-card[href*="/author/"]').eq(0)
                href = a.attr('href') if a else None

            if not href:
                a = k('a[href^="/tag/"]').eq(0)
                href = a.attr('href') if a else None

            if not href:
                a = k if k.is_('a') else k('a').eq(0)
                href = a.attr('href')

            if not href or href.startswith('#') or href.startswith('javascript:'):
                continue

            href = self._sanitize_url(href)

            is_folder_card = False
            if '/author/' in href:
                is_folder_card = True
            if href.startswith('/tag/'):
                is_folder_card = True

            if '/authors_up/post-all' in (tid or ''):
                if '/author/' not in href:
                    continue
            if (tid or '').startswith('/tags'):
                if not href.startswith('/tag/'):
                    continue

            if (not is_folder_card) and ('/archives/' not in href and '/community/' not in href) and not is_folder:
                continue

            title = (
                a.attr('title')
                or k('.xqbj-list-rows-title a').text()
                or k('.xqbj-list-rows-title').text()
                or k('h2').text()
                or k('h3').text()
                or k('.entry-title').text()
                or k('.post-title').text()
                or a.text()
            )

            title = self._fix_text(title)

            # 修复：作者卡片优先取头像 alt（避免前 3 名取到“第1/第2/第3”）
            if is_folder_card and '/author/' in href:
                avatar_alt = self._fix_text(k('.rank-card-content-avatar img').attr('alt') or '')
                if avatar_alt and (not re.match(r'^第\d+$', avatar_alt)):
                    title = avatar_alt
                else:
                    h2_name = self._fix_text(k('h2').eq(0).text() or '')
                    if h2_name:
                        title = h2_name

            # 海角往期：用日期做备注
            remarks = self._fix_text(k('time').text() or '')
            if (tid or '').startswith('/date'):
                d0 = self._fix_text(k.parents('li').find('.date').eq(0).text() or k.find('.date').eq(0).text() or k.siblings('.date').eq(0).text())
                if d0:
                    remarks = d0

            if href and title:
                img = self.getimg(k('script').text(), k, card_html)

                tag = ''
                vid = href
                if is_folder or is_folder_card:
                    tag = 'folder'
                    vid = f"{href}@folder"

                # 仅作用在这三个分类：海角热搜/海角标签/海角往期 的一级列表使用 list 形式
                style = {"type": "rect", "ratio": 1.01}
                if (tid or '').startswith('/authors_hot') or (tid or '').startswith('/tags') or (tid or '').startswith('/date'):
                    style = {"type": "list", "ratio": 0.75}

                videos.append({
                    'vod_id': vid,
                    'vod_name': title.strip(),
                    'vod_pic': img,
                    'vod_remarks': remarks,
                    'vod_tag': tag,
                    'style': style
                })
        return videos

    def getfod(self, id, pg=1):
        """二级列表：兼容
        - /author/xxx/new/ （作者页 -> 视频列表，翻页：/page/2/）
        - /tag/xxx/ （标签页 -> 视频列表，翻页：/2/）
        - 原 /mrdg... 的图文分集结构

        修复点：作者页优先解析 .xqbj-list-rows（真实作品列表），避免误取顶部 refresh-list 推荐词条。
        """
        pg = int(pg) if pg else 1

        # 二级翻页 URL 规则
        if pg == 1:
            url = f"{self.host}{id}"
        else:
            if '/author/' in (id or ''):
                url = f"{self.host}{id.rstrip('/')}/page/{pg}/"
            elif (id or '').startswith('/tag/'):
                url = f"{self.host}{id.rstrip('/')}/{pg}/"
            else:
                url = f"{self.host}{id}"

        r = self._get_html(url, timeout=15)
        data = self.getpq(r.text)

        if '/author/' in (id or '') or (id or '').startswith('/tag/'):
            items = data('.xqbj-list .xqbj-list-rows')
            if not items or len(items) == 0:
                items = data('.meritvideo-list .xqbj-list-rows')
            if not items or len(items) == 0:
                items = data('.xqbj-list-rows')

            # 某些标签页没有卡片，只有链接列表
            if not items or len(items) == 0:
                items = data('.refresh-list a.item[href*="/archives/"]')
            if not items or len(items) == 0:
                items = data('a.item[href*="/archives/"]')

            # 其它兼容
            if not items or len(items) == 0:
                items = data('a.rank-item[href*="/archives/"]')
            if not items or len(items) == 0:
                items = data('#archive article, #index article, article')

            return self.getlist(items)

        videos = []
        for i, h2 in enumerate(data('.post-content h2').items()):
            p_txt = data('.post-content p').eq(i * 2)
            p_img = data('.post-content p').eq(i * 2 + 1)
            p_html = p_img.outer_html() if hasattr(p_img, 'outer_html') else str(p_img)
            videos.append({
                'vod_id': self._sanitize_url(p_txt('a').attr('href')),
                'vod_name': self._fix_text(p_txt.text()).strip(),
                'vod_pic': self.getimg('', p_img, p_html),
                'vod_remarks': self._fix_text(h2.text()).strip()
            })
        return videos

    def getimg(self, text, elem=None, html_content=None):
        if m := re.search(r"loadBannerDirect\('([^']+)'", text or ''):
            return self._proc_url(m.group(1))

        if html_content is None and elem is not None:
            html_content = elem.outer_html() if hasattr(elem, 'outer_html') else str(elem)
        if not html_content:
            return ''

        html_content = str(html_content)

        if 'data:image' in html_content:
            m = re.search(r'(data:image/[a-zA-Z0-9+/=;,]+)', html_content)
            if m:
                return self._proc_url(m.group(1))

        # 兼容 <img z-image-loader-url="`https://...jpg`"> 以及无反引号形式
        m = re.search(r'z-image-loader-url\s*=\s*"`([^`]+)`"', html_content, re.I)
        if m:
            return self._proc_url(m.group(1))
        m = re.search(r'z-image-loader-url\s*=\s*"(https?://[^"\s]+)"', html_content, re.I)
        if m:
            return self._proc_url(m.group(1))

        m = re.search(r'(https?://[^"\'\s)]+\.(?:jpg|png|jpeg|webp))', html_content, re.I)
        if m:
            return self._proc_url(m.group(1))

        if 'url(' in html_content:
            m = re.search(r'url\s*\(\s*[\"\']?([^\"\')\s]+)[\"\']?\s*\)', html_content, re.I)
            if m:
                return self._proc_url(m.group(1))

        return ''

    def _proc_url(self, url):
        if not url:
            return ''
        url = url.strip('"\'` ')

        if url.startswith('data:'):
            try:
                _, b64_str = url.split(',', 1)
                raw = b64decode(b64_str)
                if not (raw.startswith(b'\xff\xd8') or raw.startswith(b'\x89PNG') or raw.startswith(b'GIF8')):
                    raw = self.aesimg(raw)
                key = hashlib.md5(raw).hexdigest()
                img_cache[key] = raw
                return f"{self.getProxyUrl()}&type=cache&key={key}"
            except:
                return ""

        if not url.startswith('http'):
            url = self._make_abs(url)

        return f"{self.getProxyUrl()}&url={self.e64(url)}&type=img"

    def getpq(self, data):
        try:
            return pq(data)
        except:
            return pq(data.encode('utf-8'))