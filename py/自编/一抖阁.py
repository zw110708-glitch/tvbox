# -*- coding: utf-8 -*-
# 一抖阁 yidouge.com —— WordPress 视频站（PMV / 短剧混剪）
# 结构：分类 /v1/ /v2/ 自定义分类法（父+子两级）；列表 <article class="video-card">（普通 /video/ + 合集 /creator/）；
#       详情 <h1> 标题、<div class="video-meta"> 时长+分类、data-video-url 直链 mp4（R2 CDN）、data-video-poster 封面。
import json, re, html
import requests
from urllib.parse import quote, urljoin
from base.spider import Spider


class Spider(Spider):
    # 分类树：(父分类 slug, 显示名, [(子分类显示名, 子分类 slug)])
    _TREE = [
        ('v2/ai短剧', 'AI短剧', [('伦理绿帽NTR', 'v2/绿帽ntr'), ('动漫短剧', 'v2/动漫短剧'), ('古装', 'v2/古装'),
            ('奇幻 科幻', 'v2/奇幻'), ('小说 影视剧同人', 'v2/小说同人'), ('微恐', 'v2/微恐'), ('短篇', 'v2/短篇'),
            ('都市', 'v2/都市'), ('擦边短剧魔改', 'v2/擦边短剧魔改'), ('末世', 'v2/末世'), ('校园', 'v2/校园'),
            ('热点事件改编', 'v2/热点事件改编'), ('穿越', 'v2/穿越'), ('职场', 'v2/职场'), ('重生', 'v2/重生')]),
        ('v2/pmv', 'PMV', [('AI风格PMV', 'v2/ai风格pmv'), ('AV剧情剪辑', 'v2/avjuqing'), ('B站舞蹈', 'v2/b站舞蹈'),
            ('KPOP深度换脸', 'v2/dfpmv'), ('MMD动画', 'v2/mmd动画'), ('寸止挑战', 'v2/cunzhi'), ('抖音混剪', 'v2/dyhunjian'),
            ('拼接跳转', 'v2/拼接跳转'), ('欧美PMV', 'v2/oumeipmv'), ('舞蹈', 'v2/wudaopmv')]),
        ('v2/魔改影视剧', '魔改影视剧', [('魔改电影电视剧', 'v2/魔改电影电视剧'), ('魔改综艺', 'v2/魔改综艺')]),
        ('v2/名人二创', '名人二创', [('明星换脸', 'v2/明星换脸'), ('明星短剧 去衣', 'v2/明星去衣'), ('网红去衣', 'v2/网红去衣')]),
        ('v2/vam动画-漫画', 'VAM动画', []),
        ('v1/国产', '国产', [('91大神', 'v1/91大神'), ('国产订阅博主', 'v1/国产订阅博主'), ('泄露门事件', 'v1/泄露门事件'),
            ('绿帽NTR', 'v1/绿帽ntr'), ('萝莉福利姬', 'v1/萝莉福利姬-国产'), ('调教SM', 'v1/调教sm')]),
        ('v1/欧美', '欧美', [('欧美订阅博主', 'v1/欧美订阅博主')]),
        ('v1/里番', '里番', []),
    ]

    def init(self, extend="{}"):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        self.host = config.get('site', 'https://yidouge.com')
        self.plp = config.get('plp', '')       # 播放器/封面 URL 前缀
        self.proxy = config.get('proxy', {})   # 内部请求代理
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Referer': self.host + '/',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    def getName(self):
        return '一抖阁'

    def isVideoFormat(self, url):
        return bool(url and re.search(r'\.(?:mp4|m3u8|flv|m4v)(?:\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ---------- 基础工具 ----------
    def _get(self, url, timeout=15):
        r = requests.get(url, headers=self.headers, proxies=self.proxy, timeout=timeout, verify=False)
        try:
            m = re.search(r'charset=([\w-]+)', (r.headers or {}).get('Content-Type', ''), re.I)
            if m:
                return r.content.decode(m.group(1), 'ignore')
        except Exception:
            pass
        return r.content.decode('utf-8', 'ignore')

    def _clean(self, s):
        return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', s or ''))).strip()

    def _abs(self, u):
        if not u:
            return ''
        u = html.unescape(str(u)).replace('\\/', '/')
        if u.startswith('http'):
            return u
        if u.startswith('//'):
            return 'https:' + u
        return urljoin(self.host, u)

    def _cr(self, href, name):
        return '[a=cr:%s/]%s[/a]' % (json.dumps({'id': href, 'name': name}, ensure_ascii=False), name)

    def _pic(self, pic):
        # 封面是 webp，OK影视 不支持 webp 显示 → 走 images.weserv.nl 图片服务转 jpg（顺带代理/防盗链）
        if pic:
            return 'https://images.weserv.nl/?url=' + pic + '&output=jpg'
        return ''

    def _cat(self, slug):
        return self.host + '/' + quote(slug) + '/'

    # ---------- 列表解析（兼容普通视频卡 + 作者合集卡） ----------
    def _items(self, text):
        out, seen = [], set()
        for b in re.findall(r'<article[^>]*class="video-card[^"]*".*?</article>', text, re.S | re.I):
            a = re.search(r'<a[^>]*href="([^"]*(?:/video/|/creator/)[^"]*)"', b, re.I)
            if not a:
                continue
            href = self._abs(a.group(1))
            if href in seen:
                continue
            seen.add(href)
            # 标题：h2 title -> 合集 strong -> aria-label -> img alt
            m = re.search(r'<h2[^>]*class="video-card__title"[^>]*>(.*?)</h2>', b, re.I | re.S)
            if not m:
                m = re.search(r'class="ydg-author-collection-title"[^>]*>(.*?)</', b, re.I | re.S)
            if not m:
                m = re.search(r'aria-label="([^"]+)"', b, re.I)
            if not m:
                m = re.search(r'<img[^>]*alt="([^"]+)"', b, re.I)
            title = self._clean(m.group(1)) if m else ''
            # 封面：懒加载站优先 data-src/data-original，避免取到占位图
            m = re.search(r'<img[^>]*\bdata-src="([^"]+)"', b, re.I) \
                or re.search(r'<img[^>]*\bdata-original="([^"]+)"', b, re.I) \
                or re.search(r'<img[^>]*\bsrc="([^"]+)"', b, re.I)
            pic = self._abs(m.group(1)) if m else ''
            # 备注：时长 -> 合集连载状态
            m = re.search(r'video-card__duration[^>]*>(.*?)<', b, re.I | re.S)
            if not m:
                m = re.search(r'collection-update-badge[^>]*>(.*?)<', b, re.I | re.S)
            remark = self._clean(m.group(1)) if m else ''
            out.append({'vod_id': href, 'vod_name': title, 'vod_pic': self._pic(pic), 'vod_remarks': remark})
        return out

    # ---------- 首页 ----------
    def homeContent(self, filter):
        cats, filters = [], {}
        for slug, name, subs in self._TREE:
            tid = self._cat(slug)
            cats.append({'type_id': tid, 'type_name': name})
            if subs:
                filters[tid] = [{'key': 'type', 'name': '分类', 'value': [{'n': sn, 'v': self._cat(ss)} for sn, ss in subs]}]
        return {'class': cats, 'filters': filters}

    def homeVideoContent(self):
        try:
            return {'list': self._items(self._get(self.host))}
        except Exception:
            return {'list': []}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        if extend and isinstance(extend, dict) and extend.get('type'):
            tid = extend['type']
        u = tid if str(tid).startswith('http') else self._abs(str(tid))
        if str(pg) != '1':
            u = u.rstrip('/') + '/page/' + str(pg) + '/'
        t = self._get(u)
        items = self._items(t)
        # 真实总页数（分页区 data-total），避免 pagecount=9999 导致无限翻页
        total = 1
        m = re.search(r'data-total="(\d+)"', t)
        if m:
            total = int(m.group(1))
        return {'page': int(pg or 1), 'pagecount': total, 'limit': len(items), 'total': total * 20, 'list': items}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=False, pg='1'):
        u = self.host + '/?s=' + quote(str(key))
        if str(pg) != '1':
            u += '&paged=' + str(pg)
        items = self._items(self._get(u))
        return {'page': int(pg or 1), 'pagecount': 9999, 'limit': len(items), 'total': 999999, 'list': items}

    # ---------- 详情 ----------
    def detailContent(self, ids):
        u = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        u = self._abs(u)
        t = self._get(u)

        # 作者合集页 /creator/：展开成视频分集
        if '/creator/' in u:
            m = re.search(r'<h1[^>]*>(.*?)</h1>', t, re.S)
            title = self._clean(m.group(1)) if m else ''
            items = self._items(t)
            eps = []
            for i, x in enumerate(items, 1):
                if '/video/' not in x['vod_id']:
                    continue
                eps.append((x['vod_name'] or ('第%d集' % i)) + '$' + x['vod_id'])
            pic = items[0].get('vod_pic', '') if items else ''
            return {'list': [{'vod_id': u, 'vod_name': title, 'vod_pic': pic,
                              'vod_play_from': '一抖阁', 'vod_play_url': '#'.join(eps)}]}

        # 单视频详情页
        m = re.search(r'<h1[^>]*>(.*?)</h1>', t, re.S)
        title = self._clean(m.group(1)) if m else ''
        if not title:
            m = re.search(r'<title>(.*?)</title>', t, re.S)
            title = self._clean(m.group(1)).split(' - ')[0] if m else ''

        # 封面
        m = re.search(r'data-video-poster="([^"]+)"', t, re.I)
        if not m:
            m = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', t, re.I)
        pic = self._abs(m.group(1)) if m else ''

        # 时长 + 分类（可点击标签）
        meta = re.search(r'<div class="video-meta">(.*?)</div>', t, re.S)
        remark, types = '', []
        if meta:
            rm = re.search(r'<span>([^<]+)</span>', meta.group(1))
            if rm:
                remark = self._clean(rm.group(1))
            for cm in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', meta.group(1), re.S):
                types.append(self._cr(self._abs(cm.group(1)), self._clean(cm.group(2))))

        # 播放地址：优先直链 mp4，兜底详情页 URL
        pm = re.search(r'data-video-url="([^"]+)"', t, re.I)
        play = self._abs(pm.group(1)) if pm else u

        return {'list': [{'vod_id': u, 'vod_name': title, 'vod_pic': self._pic(pic),
                          'vod_content': ' '.join(types), 'vod_remarks': remark,
                          'vod_play_from': '一抖阁', 'vod_play_url': '正片$' + play}]}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags=None):
        url = str(id)
        # 已是直链 mp4/m3u8 → 加前缀直接返回
        if re.search(r'\.(?:mp4|m3u8|flv|m4v)(?:\?|$)', url, re.I):
            return {'parse': 0, 'url': self.plp + url, 'header': self.headers}
        # 否则是详情页 URL → 二次请求提取 data-video-url
        try:
            t = self._get(url)
            m = re.search(r'data-video-url="([^"]+)"', t, re.I)
            if m:
                url = self._abs(m.group(1))
        except Exception:
            pass
        return {'parse': 0, 'url': self.plp + url, 'header': self.headers}

    def localProxy(self, param):
        return [404, 'text/plain', b'']
