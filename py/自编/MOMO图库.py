# -*- coding: utf-8 -*-
"""
MOMO图库 默影视图片集源（pics:// 协议）
站点：https://www.momo777.cc/888/ （WordPress，.cc 被墙，源配置需传 proxy/plp）
"""
import re
import json
import requests
from urllib.parse import quote
from base.spider import Spider

try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass


class Spider(Spider):
    def getName(self):
        return 'MOMO图库'

    def init(self, extend='{}'):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}

        self.site = 'https://www.momo777.cc'          # 域名根
        self.host = self.site + '/888'                # 站点根（WP 子目录）
        # ---- 代理三行（由 extend 传，没传就直连）----
        self.plp = config.get('plp', '')              # 封面/播放图片 URL 前缀
        self.proxy = config.get('proxy', {})          # 内部请求代理

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.host + '/',
        }

    # ---- 内部请求：一律走 self.proxy ----
    def _get(self, url):
        try:
            return requests.get(url, headers=self.headers, proxies=self.proxy, timeout=15, verify=False)
        except Exception:
            return None

    def _text(self, r):
        try:
            ctype = (r.headers or {}).get('Content-Type', '')
            m = re.search(r'charset\s*=\s*([\w\-]+)', ctype, re.I)
            if m:
                return r.content.decode(m.group(1), errors='ignore')
        except Exception:
            pass
        return r.content.decode('utf-8', 'ignore')

    # ---- 补全相对 URL ----
    def _abs(self, u):
        if not u:
            return ''
        if u.startswith('http'):
            return u
        if u.startswith('//'):
            return 'https:' + u
        if u.startswith('/'):
            return self.site + u
        return self.host + '/' + u

    # ---- 去掉 WP 缩略图后缀 -WxH / -WxH-1，还原原图 ----
    def _full(self, u):
        return re.sub(r'-\d+x\d+(?:-\d+)?\.', '.', u)

    # ---- 统一清洗图片 URL：还原 Photon CDN 直链 + 去 query + 可选去缩略图后缀 ----
    def _clean_img(self, u, full=False):
        if not u:
            return ''
        u = self._abs(u)
        # Photon CDN（i0-3.wp.com/xxx）还原成外站直链
        m = re.match(r'https?://i[0-3]\.wp\.com/(.+)', u)
        if m:
            u = 'https://' + m.group(1)
        # 去掉 query 参数（?w=768&resize=...&ssl=1）
        u = u.split('?')[0]
        if full:
            u = self._full(u)
        return u

    # ---- 从 <img> 标签取可用图：优先 srcset 最大尺寸（src 可能指向失效外站域名），fallback src ----
    def _pick_img(self, tag, full=False):
        srcset = re.search(r'srcset="([^"]+)"', tag)
        if srcset:
            best = ''
            best_w = -1
            for m in re.finditer(r'(\S+)\s+(\d+)w', srcset.group(1)):
                try:
                    w = int(m.group(2))
                    if w > best_w:
                        best_w = w
                        best = m.group(1)
                except Exception:
                    pass
            if best:
                return self._clean_img(best, full=full)
        srcm = re.search(r'src="([^"]+)"', tag)
        if srcm:
            return self._clean_img(srcm.group(1), full=full)
        return ''

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    # ============ 首页 ============
    def homeContent(self, filter):
        result = {'class': [], 'list': []}
        classes = [
            {'type_id': 'cat=2', 'type_name': '写真集'},
            {'type_id': 'cat=3', 'type_name': '白丝'},
            {'type_id': 'cat=4', 'type_name': '黑丝'},
        ]
        tags = ['蠢沫沫', '奈汐酱', '奶桃桃', '白银', '兔娘', 'AT鲨', '日奈娇', '水淼',
                '雨波', '布丁大法', '桜井宁宁', '森萝', '小仓千代', '鹿八岁', '迷之呆梨',
                '七月喵子', '轩萧学姐', '星之迟迟', '一只毛毛', '抖娘利世', '疯猫ss', '雪晴',
                '是一只废喵了', '九言', '脸红', '阿朱', '小瑶幺幺', '仙仙桃', '猫九酱',
                '樱岛麻衣', '年年', '小樱', '邦尼', '梨霜儿']
        for t in tags:
            classes.append({'type_id': 'tag=' + quote(t), 'type_name': t})
        result['class'] = classes
        # 首页最新图集
        try:
            r = self._get(self.host + '/')
            if r and r.status_code == 200:
                result['list'] = self._parse_list(self._text(r))
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return {'list': []}

    # ============ 分类 ============
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        url = self.host + '/?' + tid
        if pg > 1:
            url += '&paged=' + str(pg)
        r = self._get(url)
        if not r or r.status_code != 200:
            return {'list': [], 'page': pg, 'pagecount': pg, 'limit': 20, 'total': 0}
        html = self._text(r)
        vlist = self._parse_list(html)
        pagecount = self._pagecount(html, pg)
        return {'list': vlist, 'page': pg, 'pagecount': pagecount, 'limit': len(vlist), 'total': 9999}

    # ============ 列表解析（首页/分类/搜索通用）============
    def _parse_list(self, html):
        vlist = []
        seen = set()
        cards = re.findall(r'<article[^>]*class="[^"]*satin-card[^"]*"[^>]*>(.*?)</article>', html, re.S)
        for c in cards:
            m = re.search(r'<a[^>]+class="[^"]*satin-card__media[^"]*"[^>]+href="([^"]+)"', c)
            if not m:
                m = re.search(r'<h2[^>]*class="[^"]*satin-card__title[^"]*"[^>]*>\s*<a[^>]+href="([^"]+)"', c)
            if not m:
                continue
            href = self._abs(m.group(1))
            if href in seen:
                continue
            seen.add(href)

            pic = ''
            pm = re.search(r'<img[^>]*class="[^"]*satin-card__image[^"]*"[^>]*>', c)
            if pm:
                pic = self._pick_img(pm.group(0), full=False)

            tm = re.search(r'<h2[^>]*class="[^"]*satin-card__title[^"]*"[^>]*>\s*<a[^>]*>(.*?)</a>', c, re.S)
            name = tm.group(1).strip() if tm else ''
            name = re.sub(r'<[^>]+>', '', name)
            if not name:
                continue

            dm = re.search(r'<a[^>]+class="[^"]*satin-date[^"]*"[^>]*>(.*?)</a>', c)
            remarks = dm.group(1).strip() if dm else ''

            vlist.append({
                'vod_id': href,
                'vod_name': name,
                'vod_pic': (self.plp + pic) if pic else '',
                'vod_remarks': remarks,
            })
        return vlist

    def _pagecount(self, html, pg):
        m = re.search(r'<ul class="page-numbers">(.*?)</ul>', html, re.S)
        if m:
            nums = re.findall(r'<a[^>]*page-numbers[^>]*>(\d+)</a>', m.group(1))
            nums += re.findall(r'<span[^>]*current[^>]*>(\d+)</span>', m.group(1))
            if nums:
                try:
                    return max(int(n) for n in nums)
                except Exception:
                    pass
        return pg

    # ============ 搜索 ============
    def searchContent(self, key, quick, pg='1'):
        pg = int(pg or 1)
        url = self.host + '/?s=' + quote(key)
        if pg > 1:
            url += '&paged=' + str(pg)
        r = self._get(url)
        if not r or r.status_code != 200:
            return {'list': [], 'page': pg, 'pagecount': pg, 'limit': 20, 'total': 0}
        html = self._text(r)
        vlist = self._parse_list(html)
        pagecount = self._pagecount(html, pg)
        return {'list': vlist, 'page': pg, 'pagecount': pagecount, 'limit': len(vlist), 'total': 9999}

    # ============ 详情 ============
    def detailContent(self, ids):
        url = ids[0] if ids else ''
        if not url:
            return {'list': []}
        r = self._get(url)
        if not r or r.status_code != 200:
            return {'list': []}
        html = self._text(r)

        vod = {
            'vod_id': url,
            'vod_name': '',
            'vod_pic': '',
            'type_name': '写真',
            'vod_content': '',
            'vod_play_from': 'MOMO图库',
            'vod_play_url': '',
        }

        h1 = re.search(r'<h1[^>]*class="[^"]*satin-single-title[^"]*"[^>]*>(.*?)</h1>', html, re.S)
        if not h1:
            h1 = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        if h1:
            vod['vod_name'] = re.sub(r'<[^>]+>', '', h1.group(1)).strip()

        imgs = self._extract_imgs(html)
        if imgs:
            vod['vod_pic'] = self.plp + imgs[0]

        # 播放地址：单集图集，playerContent 按详情页 URL 二次抓正文图
        vod['vod_play_url'] = '打开图集$' + url
        return {'list': [vod]}

    # ============ 正文图片提取（返回去后缀的原图绝对地址，不含 plp）============
    def _extract_imgs(self, html):
        result = []
        seen = set()
        # 正文图：<figure class="wp-block-image"> 里的 img（域名可能多样，src 可能指向失效域名，优先 srcset）
        figs = re.findall(r'<figure[^>]*wp-block-image[^>]*>.*?</figure>', html, re.S)
        for f in figs:
            im = re.search(r'<img[^>]*>', f)
            if not im:
                continue
            tag = im.group(0)
            srcm = re.search(r'src="([^"]+)"', tag)
            src = srcm.group(1) if srcm else ''
            low = src.lower()
            # 排除广告 gif / 表情 / 头像
            if '.gif' in low or 'mmtk5' in low or 'emoji' in low or 'smiley' in low or 'avatar' in low:
                continue
            u = self._pick_img(tag, full=True)
            if u and u not in seen:
                seen.add(u)
                result.append(u)
        return result

    # ============ 播放 ============
    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {'parse': 0, 'playUrl': '', 'url': '', 'header': ''}
        if id.startswith('pics://') or id.startswith('manga://'):
            return {'parse': 0, 'playUrl': '', 'url': id, 'header': ''}
        # id 为详情页 URL，二次请求提取正文图片
        r = self._get(id)
        if r and r.status_code == 200:
            imgs = self._extract_imgs(self._text(r))
            if imgs:
                pics = 'pics://' + '&&'.join(self.plp + u for u in imgs)
                return {'parse': 0, 'playUrl': '', 'url': pics, 'header': ''}
        return {'parse': 0, 'playUrl': '', 'url': id, 'header': ''}
