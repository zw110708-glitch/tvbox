# -*- coding: utf-8 -*-
# 海角网 爬虫源（OK影视 / catvod，Chaquopy Python 3.8）
# 站点：https://www.hjw01.com/（域名可能更换，源配置 extend 传 site 覆盖）
import json
import re
import requests
from base64 import b64encode, b64decode
from urllib.parse import quote
from pyquery import PyQuery as pq
from base.spider import Spider as BaseSpider

try:
    from Crypto.Cipher import AES
except Exception:
    AES = None


class Spider(BaseSpider):

    def init(self, extend="{}"):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}

        # 站点域名固定（永久地址，不随 extend 变动）
        self.host = 'https://www.hjw01.com'
        # ---- 代理三行（照抄，由 extend 传，没传就直连）----
        self.plp = config.get('plp', '')       # 播放器 URL 前缀
        self.proxy = config.get('proxy', {})   # 内部请求代理

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Origin': self.host,
            'Referer': self.host + '/',
        }
        self.session = requests.Session()
        self._img_cache = {}

    def getName(self):
        return '海角网'

    def isVideoFormat(self, url):
        return bool(url and re.search(r'\.(m3u8|mp4|ts)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self._img_cache.clear()

    # ---------------- 请求 ----------------
    def _get(self, url, timeout=15):
        return self.session.get(url, headers=self.headers, proxies=self.proxy, timeout=timeout)

    def _text(self, r):
        try:
            ctype = (r.headers or {}).get('Content-Type', '')
            m = re.search(r'charset\s*=\s*([\w\-]+)', ctype, re.I)
            if m:
                return r.content.decode(m.group(1), errors='ignore')
        except Exception:
            pass
        for enc in ('utf-8', 'gb18030'):
            try:
                return r.content.decode(enc)
            except Exception:
                pass
        return r.content.decode('utf-8', 'ignore')

    def _doc(self, url, timeout=15):
        return pq(self._text(self._get(url, timeout)))

    # ---------------- 工具 ----------------
    def _cr(self, href, name):
        return '[a=cr:%s/]%s[/a]' % (json.dumps({'id': href, 'name': name}, ensure_ascii=False), name)

    def _abs(self, u):
        u = (u or '').strip()
        if not u:
            return ''
        if u.startswith('http'):
            return u
        if u.startswith('//'):
            return 'https:' + u
        return self.host + (u if u.startswith('/') else '/' + u)

    # ---------------- 图片（AES 加密图床，走 localProxy 解密） ----------------
    def _pic_proxy(self, url):
        if not url:
            return ''
        return self.getProxyUrl() + '&url=' + b64encode(url.encode('utf-8')).decode() + '&type=img'

    def _pic(self, it):
        img = it('img').eq(0)
        z = (img.attr('z-image-loader-url') or '').strip('`').strip()
        if z and z.startswith('http'):
            return self._pic_proxy(z)
        src = (img.attr('src') or img.attr('data-src') or '').strip()
        if src.startswith('http'):
            return self._pic_proxy(src)
        return ''

    def _aes_img(self, data):
        if not data or len(data) < 16:
            return data
        head = data[:6]
        if data[:2] == b'\xff\xd8' or data[:4] == b'\x89PNG' or head in (b'GIF87a', b'GIF89a', b'RIFF'):
            return data
        if AES is None:
            return data
        try:
            dec = AES.new(b'f5d965df75336270', AES.MODE_CBC, b'97b60394abc2fbe1').decrypt(data)
            pad = dec[-1]
            if 1 <= pad <= 16:
                dec = dec[:-pad]
            if dec[:2] == b'\xff\xd8' or dec[:4] == b'\x89PNG' or dec[:6] in (b'GIF87a', b'GIF89a'):
                return dec
        except Exception:
            pass
        return data

    def localProxy(self, param):
        try:
            if param.get('type') == 'img':
                url = param.get('url', '')
                if not url.startswith('http'):
                    url = b64decode(url.encode('utf-8')).decode('utf-8')
                if url in self._img_cache:
                    return [200, 'image/jpeg', self._img_cache[url]]
                h = dict(self.headers)
                h['Referer'] = self.host + '/'
                data = self._aes_img(requests.get(url, headers=h, proxies=self.proxy, timeout=10, verify=False).content)
                self._img_cache[url] = data
                return [200, 'image/jpeg', data]
        except Exception:
            pass
        return [404, 'text/plain', b'']

    # ---------------- 分类 ----------------
    def _classes(self, doc):
        skip = ('全部分类', '我的订阅', '原创招募', '海角社区', 'QQ群', '商务', 'TG群', '推特', 'TG')
        classes = []
        seen = set()
        for a in doc('.xqbj-main-menu a').items():
            name = (a.text() or '').strip()
            href = (a.attr('href') or '').strip()
            if not name or not href or name in skip:
                continue
            if any(x in href for x in ('/follow/', '/qun.html', '/tgq.html', '/twitter.html', '/swhz.html', '/category/yczm/')):
                continue
            if href.startswith('http') and self.host not in href:
                continue
            key = name + '::' + href
            if key in seen:
                continue
            seen.add(key)
            classes.append({'type_name': name, 'type_id': href})
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
        result = {'class': [], 'list': []}
        try:
            doc = self._doc(self.host + '/')
            result['class'] = self._classes(doc)
            result['list'] = self._videos('video', doc('.xqbj-list-rows'))
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        result = {'list': []}
        try:
            doc = self._doc(self.host + '/')
            result['list'] = self._videos('video', doc('.xqbj-list-rows'))
        except Exception:
            pass
        return result

    # ---------------- 翻页 URL ----------------
    def _page_url(self, tid, pg):
        if tid.startswith('http'):
            from urllib.parse import urlparse
            path = urlparse(tid).path or '/'
        else:
            path = tid if tid.startswith('/') else '/' + tid
        path = path.rstrip('/') or '/'
        if pg <= 1:
            return self.host + path + '/'
        if path == '/':
            return self.host + '/page/%d/' % pg
        # 带 /page/ 的路径
        if ('/author/' in path or path.startswith('/order/') or path.startswith('/authors_hot')
                or path.startswith('/date') or path.startswith('/authors_blogger') or path == '/tags'):
            return self.host + path + '/page/%d/' % pg
        return self.host + path + '/%d/' % pg

    # ---------------- 列表解析（5 个特殊「榜」页统一走 _pick/_videos） ----------------
    def _pick(self, doc, tid):
        """返回 (kind, items)。kind: author/tag/hotword 为 folder，video 为普通视频。"""
        p = tid if tid.startswith('/') else '/' + tid
        if p.startswith('/authors_blogger') or p.startswith('/authors_up'):
            return 'author', doc('a.rank-card-link[href*="/author/"]')
        if p == '/tags' or p.startswith('/tags/'):
            return 'tag', doc('.tags-group a[href*="/tag/"]')
        if p.startswith('/authors_hot'):
            return 'hotword', doc('a.rank-card[href*="/search/"]')
        if p.startswith('/date'):
            return 'video', doc('a.history-text[href*="/archives/"]')
        return 'video', doc('.xqbj-list-rows')

    def _videos(self, kind, items, tid=''):
        p = tid if tid.startswith('/') else '/' + tid
        if kind == 'author':
            return self._folder_list(items, 'author')
        if kind == 'tag':
            return self._folder_list(items, 'tag')
        if kind == 'hotword':
            return self._folder_list(items, 'hotword')
        return self._video_list(items, p)

    def _folder_list(self, items, kind):
        """作者/标签/热搜词 三种 folder 卡片统一解析。"""
        out = []
        seen = set()
        for it in items.items():
            if kind == 'tag':
                href = (it.attr('href') or '').strip()
                name = re.sub(r'\(\d+\)$', '', (it('h3').eq(0).text() or it.text() or '').strip()).strip()
            elif kind == 'hotword':
                href = (it.attr('href') or '').strip()
                name = (it('.rank-card-title').eq(0).text() or it.text() or '').strip()
            else:  # author
                href = (it.attr('href') or '').strip()
                name = (it('h2').eq(0).text() or it('.rank-card-content-avatar img').attr('alt') or it.text() or '').strip()
            if not href or not name or href in seen:
                continue
            seen.add(href)
            remarks = it('.flex span').eq(0).text() if kind == 'hotword' else ''
            out.append({
                'vod_id': href,
                'vod_name': name,
                'vod_pic': self._pic(it) if kind == 'author' else '',
                'vod_remarks': (remarks or '').strip(),
                'vod_tag': 'folder',
            })
        return out

    def _video_list(self, items, p=''):
        videos = []
        seen = set()
        for it in items.items():
            a = it('a[href*="/archives/"]').eq(0)
            if not a.attr('href') and it.is_('a') and '/archives/' in (it.attr('href') or ''):
                a = it
            href = (a.attr('href') or '').strip()
            if not href or href in seen:
                continue
            seen.add(href)

            title = (a.attr('title') or '').strip()
            if not title:
                title = it('h2').eq(0).text() or it('h3').eq(0).text() or it('.xqbj-list-rows-image-title').text() or a.text()
            title = re.sub(r'\s+', ' ', title).strip()
            if not title:
                continue

            pic = self._pic(it)

            if p.startswith('/date'):
                remarks = it.parents('li').find('.date').eq(0).text().strip()
            else:
                des = it('.xqbj-list-rows-bottom-tags-text.is-desktop').text().strip()
                mob = it('.xqbj-list-rows-bottom-tags-text.is-mobile').text().strip()
                if re.match(r'^\d{1,2}:\d{2}$', des):
                    # 今天：des 是时分，mob 是日期时拼成「时分 日期」，否则只留时分
                    remarks = (des + ' ' + mob).strip() if re.match(r'^\d{1,2}月\d{1,2}日', mob) else des
                else:
                    # 非今天：des 是日期（月-日），只取日期，避免和 mob 的日期重复
                    remarks = des

            videos.append({
                'vod_id': href,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': remarks,
            })
        return videos

    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'page': int(pg or 1), 'pagecount': 9999, 'limit': 90, 'total': 999999}
        try:
            pg = int(pg or 1)
            tid = (tid or '/').strip()
            # 热搜词 folder：直接执行搜索
            if tid.startswith('/search/'):
                return self.searchContent(tid[len('/search/'):].strip('/'), False, pg)

            doc = self._doc(self._page_url(tid, pg))
            kind, items = self._pick(doc, tid)
            videos = self._videos(kind, items, tid)
            # 往期页是整月时间线（上千条），按页切片，避免一次加载卡死
            if tid.startswith('/date'):
                videos = videos[(pg - 1) * 60: pg * 60]
            result['list'] = videos
        except Exception:
            pass
        return result

    # ---------------- 详情 ----------------
    def _actors(self, doc):
        out = []
        seen = set()
        for a in doc('.novel-info a[href*="/author/"]').items():
            href = (a.attr('href') or '').strip()
            name = (a.find('h2').eq(0).text() or a.find('img').attr('alt') or a.text() or '').strip()
            if not href or not name or href in seen:
                continue
            seen.add(href)
            out.append(self._cr(href, name))
        return ' '.join(out)

    def _tag_cr(self, doc):
        out = []
        seen = set()
        for a in doc('.detail-info-desc a[href*="/category/"]').items():
            href = (a.attr('href') or '').strip()
            name = (a.text() or '').strip()
            if not href or not name or href in seen:
                continue
            seen.add(href)
            out.append(self._cr(href, name))
        for a in doc('.tags-group2 a[href*="/tag/"]').items():
            href = (a.attr('href') or '').strip()
            name = (a.text() or '').strip()
            if not href or not name or href in seen:
                continue
            seen.add(href)
            out.append(self._cr(href, name))
        return out

    def detailContent(self, ids):
        try:
            href = (ids[0] if ids and ids[0] else '').strip()
            if not href:
                return {'list': []}
            url = href if href.startswith('http') else self._abs(href)
            doc = self._doc(url)

            title = (doc('h1').eq(0).text() or '').strip()

            # 1. 视频：详情页可能嵌多个 dplayer（多段视频），全部提取
            urls = []
            for d in doc('.dplayer[data-config]').items():
                try:
                    cfg = json.loads(d.attr('data-config'))
                    vu = ((cfg.get('video') or {}).get('url') or '').replace('\\/', '/')
                    if vu:
                        urls.append(vu)
                except Exception:
                    continue

            play = ''
            if urls:
                if len(urls) == 1:
                    play = re.sub(r'[$#]', ' ', title) + '$' + urls[0]
                else:
                    play = '#'.join('第%d段$%s' % (i, u) for i, u in enumerate(urls, 1))

            return {'list': [{
                'vod_name': title or '海角网',
                'vod_play_from': '海角网',
                'vod_play_url': play,
                'vod_actor': self._actors(doc),
                'vod_content': ' '.join(self._tag_cr(doc)),
            }]}
        except Exception:
            return {'list': []}

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick, pg="1"):
        result = {'list': [], 'page': int(pg or 1), 'pagecount': 9999}
        try:
            pg = int(pg or 1)
            kq = quote(str(key), safe='')
            # 文章 Tab 结果更全（综合 Tab 只返回少量文章+博主/标签/用户卡片）
            url = self.host + '/search_contents/' + kq + '/' if pg <= 1 else self.host + '/search_contents/' + kq + '/%d/' % pg
            doc = self._doc(url)
            result['list'] = self._video_list(doc('.xqbj-list-rows'))
        except Exception:
            pass
        return result

    # ---------------- 播放 ----------------
    def playerContent(self, flag, id, vipFlags):
        url = (id or '').strip().replace('\\/', '/')
        headers = dict(self.headers)
        headers['Referer'] = self.host + '/'
        return {'parse': 0, 'url': self.plp + url, 'header': headers}
