# -*- coding: utf-8 -*-
# by @嗷呜
import json
import sys
from base64 import b64decode, b64encode
from pyquery import PyQuery as pq
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def init(self, extend="{}"):
        """初始化并加载代理配置
        示例：{"proxy":{"http":"http://127.0.0.1:10172","https":"https://127.0.0.1:10172"}}
        """
        # 解析代理配置
        self.proxy = {}
        if extend:
            try:
                config = json.loads(extend)
                self.plp = config.get('plp', '')
                self.proxy = config.get('proxy', {})
            except Exception as e:
                print(f"代理配置解析错误: {str(e)}")
        
        # 初始化会话（保持原始代码的会话模式）
        self.host = self.gethost()
        self.headers['referer'] = f'{self.host}/'
        self.session = self._create_session()
        self.session.headers.update(self.headers)
        self.session.proxies = self.proxy  # 仅在此处添加代理配置

    def _create_session(self):
        """创建带重试机制的会话，优化连接稳定性"""
        session = Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.3,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def getName(self):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        if hasattr(self, 'session'):
            self.session.close()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'sec-ch-ua': '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        'sec-ch-ua-full-version-list': '"Not(A:Brand";v="99.0.0.0", "Google Chrome";v="133.0.6943.98", "Chromium";v="133.0.6943.98"',
        'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }

    def homeContent(self, filter):
        result = {}
        cateManual = {
            "4K": "/4k",
            "国产": "two_click_/categories/chinese",
            "最新": "/newest",
            "最佳": "/best",
            "频道": "/channels",
            "类别": "/categories",
            "明星": "/pornstars"
        }
        classes = []
        filters = {}
        for k in cateManual:
            classes.append({
                'type_name': k,
                'type_id': cateManual[k]
            })
            if k !='4K':filters[cateManual[k]]=[{'key':'type','name':'类型','value':[{'n':'4K','v':'/4k'}]}]
        result['class'] = classes
        result['filters'] = filters
        return result

    def homeVideoContent(self):
        data = self.getpq()
        return {'list': self.getlist_from_page(data, ".thumb-list--sidebar .thumb-list__item")}

    def categoryContent(self, tid, pg, filter, extend):
        vdata = []
        result = {}
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        if tid in ['/4k', '/newest', '/best'] or 'two_click_' in tid:
            if 'two_click_' in tid: tid = tid.split('click_')[-1]
            data = self.getpq(f'{tid}{extend.get("type","")}/{pg}')
            vdata = self.getlist_from_page(data, ".thumb-list--sidebar .thumb-list__item")
        elif tid == '/channels':
            data = self.getpq(f'{tid}/{pg}')
            jsdata = self.getjsdata(data)
            for i in jsdata['channels']:
                vdata.append({
                    'vod_id': f"two_click_" + i.get('channelURL'),
                    'vod_name': i.get('channelName'),
                    'vod_pic': i.get('siteLogoURL'),
                    'vod_year': f'videos:{i.get("videoCount")}',
                    'vod_tag': 'folder',
                    'vod_remarks': f'subscribers:{i["subscriptionModel"].get("subscribers")}',
                    'style': {'ratio': 1.33, 'type': 'rect'}
                })
        elif tid == '/categories':
            result['pagecount'] = pg
            data = self.getpq(tid)
            self.cdata = self.getjsdata(data)
            for i in self.cdata['layoutPage']['store']['popular']['assignable']:
                vdata.append({
                    'vod_id': "one_click_" + i.get('id'),
                    'vod_name': i.get('name'),
                    'vod_pic': '',
                    'vod_tag': 'folder',
                    'style': {'ratio': 1.33, 'type': 'rect'}
                })
        elif tid == '/pornstars':
            data = self.getpq(f'{tid}/{pg}')
            pdata = self.getjsdata(data)
            for i in pdata['layoutPage']['pornstarListProps']['pornstars']:
                vdata.append({
                    'vod_id': f"two_click_" + i.get('pageURL'),
                    'vod_name': i.get('name'),
                    'vod_pic': i.get('imageThumbUrl'),
                    'vod_remarks': i.get('translatedCountryName'),
                    'vod_tag': 'folder',
                    'style': {'ratio': 1.33, 'type': 'rect'}
                })
        elif 'one_click' in tid:
            result['pagecount'] = pg
            tid = tid.split('click_')[-1]
            for i in self.cdata['layoutPage']['store']['popular']['assignable']:
                if i.get('id') == tid:
                    for j in i['items']:
                        vdata.append({
                            'vod_id': f"two_click_" + j.get('url'),
                            'vod_name': j.get('name'),
                            'vod_pic': j.get('thumb'),
                            'vod_tag': 'folder',
                            'style': {'ratio': 1.33, 'type': 'rect'}
                        })
        result['list'] = vdata
        return result

    def detailContent(self, ids):
        data = self.getpq(ids[0])
        link = data('link[rel="preload"][as="fetch"][crossorigin="true"]').attr('href')
        if  link:
            ggggx = f"多音画$666_{link}"
        else:
            ggggx = f"嗅探${ids[0]}"
        vn = data('meta[property="og:title"]').attr('content')
        dtext = data('#video-tags-list-container')
        href = dtext('a').attr('href')
        title = dtext('span[class*="body-bold-"]').eq(0).text()
        pdtitle = ''
        if href:
            pdtitle = '[a=cr:' + json.dumps({'id': 'two_click_' + href, 'name': title}) + '/]' + title + '[/a]'
        vod = {
            'vod_name': vn,
            'vod_director': pdtitle,
            'vod_remarks': data('.rb-new__info').text(),
            'vod_play_from': 'Xhamster',
            'vod_play_url': ggggx
        }
        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        data = self.getpq(f'/search/{key}?page={pg}')
        return {'list': self.getlist_from_page(data, ".thumb-list--sidebar .thumb-list__item"), 'page': pg}

    def playerContent(self, flag, id, vipFlags):
        # 完全保留原始代码的播放逻辑，不做本地代理转发
        p, url = 1, id
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.5410.0 Safari/537.36',
            'origin': self.host,
            'referer': f'{self.host}/',
        }
        if id.startswith("666_"):
            p, url = 0, id[4:]
        
        # 关键优化：将代理配置传递给播放器
        return {
            'parse': p, 
            'url': url, 
            'header': headers,
            'proxy': self.proxy  # 新增：将代理配置传递给播放器
        }

    # 禁用本地代理转发，保持和原始代码一致
    def localProxy(self, param):
        pass

    def gethost(self):
        try:
            # 使用带代理的会话获取主机
            response = self.session.get(
                'https://xhamster.com',
                headers=self.headers,
                proxies=self.proxy,
                allow_redirects=False,
                timeout=10
            )
            return response.headers.get('Location', 'https://xhamster.com')
        except Exception as e:
            print(f"获取主页失败: {str(e)}")
            return "https://xhamster.com"

    def e64(self, text):
        try:
            text_bytes = text.encode('utf-8')
            encoded_bytes = b64encode(text_bytes)
            return encoded_bytes.decode('utf-8')
        except Exception as e:
            print(f"Base64编码错误: {str(e)}")
            return ""

    def d64(self, encoded_text):
        try:
            encoded_bytes = encoded_text.encode('utf-8')
            decoded_bytes = b64decode(encoded_bytes)
            return decoded_bytes.decode('utf-8')
        except Exception as e:
            print(f"Base64解码错误: {str(e)}")
            return ""

    def getlist_from_page(self, page_doc, selector):
        """从整页文档解析列表（解决懒加载/骨架屏导致后续无<img>的问题）。"""
        thumb_map_by_id = {}
        meta_map_by_url = {}

        # 从 initials-script 递归抽取 (pageURL + thumbURL) 的条目。
        # 这样比硬编码 layoutPage.videoListProps.videoThumbProps 更稳，
        # 兼容频道/明星等二级列表页面结构变化。
        try:
            js = self.getjsdata(page_doc) or {}

            entries = []
            def walk(o):
                if isinstance(o, dict):
                    page_url = o.get('pageURL') or o.get('pageUrl')
                    thumb_url = o.get('thumbURL') or o.get('thumbUrl') or o.get('previewThumbURL')
                    if page_url and thumb_url:
                        entries.append(o)
                    for v in o.values():
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)

            walk(js)

            for v in entries:
                vid = str(v.get('id') or v.get('videoId') or '')
                purl = (v.get('pageURL') or v.get('pageUrl') or '').strip()
                turl = (v.get('thumbURL') or v.get('thumbUrl') or v.get('previewThumbURL') or '').strip()
                title = (v.get('title') or v.get('videoTitle') or '').strip()
                if vid and turl:
                    thumb_map_by_id[vid] = turl
                if purl:
                    meta_map_by_url[purl] = {'thumb': turl, 'title': title}
        except Exception:
            pass

        items = page_doc(selector)
        vlist = []
        for i in items.items():
            href = (i('.role-pop').attr('href') or '').strip()
            # 有些列表中会混入广告/占位条目，没有 href，直接跳过
            if not href:
                continue

            # 先走 DOM 解析；若拿不到(骨架屏)，再从 initials-script 的映射补齐
            pic = self._pick_img_url_from_item(i)
            if not pic:
                vid = (i.attr('data-video-id') or '').strip()
                pic = thumb_map_by_id.get(vid) or (meta_map_by_url.get(href) or {}).get('thumb') or ''

            name = (i('.video-thumb-info a').text() or '').strip()
            if not name:
                name = (meta_map_by_url.get(href) or {}).get('title') or ''

            vlist.append({
                'vod_id': href,
                'vod_name': name,
                'vod_pic': pic,
                'vod_year': i('.video-thumb-info .video-thumb-views').text().split(' ')[0],
                'vod_remarks': i('.role-pop div[data-role="video-duration"]').text(),
                'style': {'ratio': 1.33, 'type': 'rect'}
            })
        return vlist

    def _pick_img_url_from_item(self, item):
        img = item('.role-pop img')
        if not img:
            return ''
        # 1) 直接 src
        src = (img.attr('src') or '').strip()
        if src and not src.startswith('data:'):
            return src
        # 2) 常见懒加载属性
        for k in ('data-src', 'data-original', 'data-thumb'):
            v = (img.attr(k) or '').strip()
            if v and not v.startswith('data:'):
                return v
        # 3) srcset / data-srcset: 取第一条 URL
        for k in ('data-srcset', 'srcset'):
            v = (img.attr(k) or '').strip()
            if v:
                first = v.split(',')[0].strip().split(' ')[0]
                if first and not first.startswith('data:'):
                    return first
        return ''

    def getlist(self, data):
        """兼容旧调用：仅从条目 DOM 解析。

        说明：某些列表页后续条目会渲染为骨架屏（没有 <img>），这时仅靠 DOM
        无法拿到缩略图 URL，会得到空 vod_pic。此时应使用 getlist_from_page。
        """
        vlist = []
        for i in data.items():
            href = (i('.role-pop').attr('href') or '').strip()
            if not href:
                continue

            pic = self._pick_img_url_from_item(i)
            if not pic:
                # 兜底: 有些布局把图放在 background-image 上
                bg = (i('.role-pop').attr('style') or '').strip()
                if 'url(' in bg:
                    try:
                        pic = bg.split('url(')[-1].split(')')[0].strip('"\'')
                    except Exception:
                        pic = ''
            vlist.append({
                'vod_id': href,
                'vod_name': i('.video-thumb-info a').text(),
                'vod_pic': pic,
                'vod_year': i('.video-thumb-info .video-thumb-views').text().split(' ')[0],
                'vod_remarks': i('.role-pop div[data-role="video-duration"]').text(),
                'style': {'ratio': 1.33, 'type': 'rect'}
            })
        return vlist

    def getpq(self, path=''):
        h = '' if path.startswith('http') else self.host
        try:
            response = self.session.get(f'{h}{path}', timeout=10,proxies=self.proxy)
            response.raise_for_status()
            return pq(response.content)
        except Exception as e:
            print(f"页面请求错误({h}{path}): {str(e)}")
            # 返回一个最小 HTML，避免 pq('') 在部分环境下抛 Document is empty
            return pq('<html></html>')

    def getjsdata(self, data):
        vhtml = data("script[id='initials-script']").text()
        try:
            jst = json.loads(vhtml.split('initials=')[-1][:-1])
            return jst
        except Exception as e:
            print(f"解析js数据错误: {str(e)}")
            return {}
