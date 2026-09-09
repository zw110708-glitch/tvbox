# -*- coding: utf-8 -*-
# 溏心次元 OK影视源（苹果CMS v10）
import json, re
import requests
from urllib.parse import quote, urljoin
from pyquery import PyQuery as pq
from base.spider import Spider


class Spider(Spider):
    def init(self, extend="{}"):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}

        # ---- 代理三行（照抄，由 extend 传，没传就直连）----
        self.plp = config.get('plp', '')       # 播放器/封面/播放地址 URL 前缀
        self.proxy = config.get('proxy', {})   # 内部请求代理

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }

        # 上游导航地址（入口页，下发真实站点） + 历史镜像，运行时探活自选可用域名
        self.nav = config.get('nav', 'https://mpxx.txcy-lame.buzz/')
        self.mirrors = config.get('mirrors', [
            'https://txcy-7oo1.txcy-pu.buzz/',
            'https://txcybz3p.buzz/',
        ])
        self.host = (config.get('site', '') or '').rstrip('/')
        if not self.host:
            self.host = self._pick()

        # 一级分类（网站顶部导航）+ 二级分类（分类频道/女优广场）
        self._cls = [
            ('麻豆原创', '1'), ('代理节目', '2'), ('节目企划', '3'), ('国产片商', '32'), ('国产精品', '39'),
            ('分类频道', 'sort'), ('女优广场', 'actor'),
        ]

    def _pick(self):
        # 依次探活：上游导航 -> 历史镜像，返回首个可用域名（不含尾斜杠）
        for c in [self.nav] + list(self.mirrors):
            base = c.rstrip('/')
            try:
                r = requests.get(base + '/banshu/', headers=self.headers, proxies=self.proxy, timeout=8, verify=False)
                if r.status_code == 200 and '/voddetail/' in r.text:
                    return base
            except Exception:
                pass
        return self.nav.rstrip('/')

    def getName(self):
        return '溏心次元'

    def isVideoFormat(self, url):
        return bool(url and re.search(r'\.(m3u8|mp4|ts)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ---- 内部请求：一律走 self.proxy ----
    def _get(self, url, timeout=15):
        return requests.get(url, headers=self.headers, proxies=self.proxy, timeout=timeout, verify=False)

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

    def _cr(self, href, name):
        return '[a=cr:%s/]%s[/a]' % (json.dumps({'id': href, 'name': name}, ensure_ascii=False), name)

    def _abs(self, u):
        if not u:
            return ''
        if u.startswith('http'):
            return u
        if u.startswith('//'):
            return 'https:' + u
        return urljoin(self.host + '/', u)

    # ---- 视频列表解析：只取 /voddetail/ 卡片（过滤广告），按 href 去重 ----
    def _getlist(self, items):
        videos = []
        seen = []
        for it in items.items():
            href = it('a.img-box').attr('href') or ''
            if '/voddetail/' not in href or href in seen:
                continue
            seen.append(href)
            img = it('img').eq(0)
            pic = self._abs(img.attr('src') or '')
            name = (img.attr('alt') or it('h2 a').text() or '').strip()
            m = re.search(r'(\d{2}-\d{2}-\d{2})', it.text())
            videos.append({
                'vod_id': href,
                'vod_name': name,
                'vod_pic': self.plp + pic if pic else '',
                'vod_remarks': m.group(1) if m else '',
            })
        return videos

    # ---- 二级分类卡片列表（folder 卡片，点击进入下一级视频列表） ----
    # 一级分类（顶部导航）id，分类频道里要过滤掉（它们已作为一级分类展示）
    _TOP = ('1', '2', '3', '32', '39')

    def _folders(self, actor, pg):
        out = []
        page = int(pg or 1)
        label = 'tags' if actor else 'sort'
        # 专用列表页：分类频道 /label/sort.html、女优广场 /label/tags.html（翻页 -{pg}.html）
        url = self.host + ('/label/%s.html' % label if page == 1 else '/label/%s-%s.html' % (label, page))
        try:
            d = pq(self._text(self._get(url)))
            out = self._actors(d) if actor else self._sorts(d)
            # 第 1 页专用页抓不到（520 等）时，回退首页内嵌卡片
            if not out and page == 1:
                d = pq(self._text(self._get(self.host + '/banshu/')))
                out = self._actors(d) if actor else self._sorts(d)
        except Exception:
            pass
        return out

    def _sorts(self, d):
        # 分类频道：li.col-26.col-m-26.mb20 -> /vodtype/{id}/ + p.classfont；过滤一级分类 + 去重
        out, seen = [], []
        for it in d('li.col-26.col-m-26.mb20').items():
            href = it('a').eq(0).attr('href') or ''
            m = re.search(r'/vodtype/(\d+)/', href)
            if not m:
                continue
            cid = m.group(1)
            if cid in self._TOP or cid in seen:
                continue
            seen.append(cid)
            out.append({
                'vod_id': cid,
                'vod_name': it('p.classfont').text().strip(),
                'vod_pic': self.plp + self._abs(it('img').eq(0).attr('src') or ''),
                'vod_remarks': '',
                'vod_tag': 'folder',
                'style': {'type': 'rect', 'ratio': 1.0},
            })
        return out

    def _actors(self, d):
        # 女优广场：抓所有 /actordetail/{id}/ 链接（不依赖具体 li class，兼容不同卡片结构）+ 去重
        out, seen = [], []
        for a in d('a[href*="/actordetail/"]').items():
            href = a.attr('href') or ''
            m = re.search(r'/actordetail/(\d+)/', href)
            if not m:
                continue
            aid = m.group(1)
            if aid in seen:
                continue
            img = a('img').eq(0)
            name = (img.attr('alt') or '').strip()
            if not name:
                li = a.closest('li')
                name = (li('p').text() if li.length else '').strip()
            if not name:
                name = a.text().strip()
            if not name:
                continue
            seen.append(aid)
            out.append({
                'vod_id': 'actor_%s_%s' % (aid, name),
                'vod_name': name,
                'vod_pic': self.plp + self._abs(img.attr('src') or ''),
                'vod_remarks': '',
                'vod_tag': 'folder',
                'style': {'type': 'oval'},
            })
        return out

    def homeContent(self, filter):
        result = {'class': [{'type_id': i, 'type_name': n} for n, i in self._cls], 'list': []}
        try:
            doc = self._text(self._get(self.host + '/banshu/'))
            result['list'] = self._getlist(pq(doc)('li.col-25.col-m-12.mb20'))
        except Exception:
            pass
        return result

    def categoryContent(self, tid, pg, filter, extend):
        # pagecount 动态：folder 固定 1 页；视频列表当前页有内容则 pg+1，空则 pg（到底即停，不无限翻页）
        result = {'list': [], 'page': int(pg or 1), 'pagecount': 1, 'limit': 90, 'total': 0}
        try:
            tid = str(tid)
            p = int(pg or 1)
            if tid == 'sort':
                lst = self._folders(False, p)
                result['list'] = lst
                result['total'] = len(lst)
                result['pagecount'] = p + 1 if lst else p
                return result
            if tid == 'actor':
                lst = self._folders(True, p)
                result['list'] = lst
                result['total'] = len(lst)
                result['pagecount'] = p + 1 if lst else p
                return result
            if tid.startswith('actor_'):
                parts = tid.split('_', 2)
                aid = parts[1] if len(parts) > 1 else ''
                name = parts[2] if len(parts) > 2 else ''
                if aid:
                    doc = self._text(self._get(self.host + '/actordetail/%s/' % aid))
                    lst = self._getlist(pq(doc)('li.col-25.col-m-12.mb20'))
                    if lst:
                        result['list'] = lst
                        result['total'] = len(lst)
                        return result
                if name:
                    lst = self._search_list(name, p)
                    result['list'] = lst
                    result['total'] = len(lst)
                    result['pagecount'] = p + 1 if lst else p
                return result
            url = self.host + '/vodtype/%s.html' % tid if p == 1 else self.host + '/vodtype/%s-%s/' % (tid, p)
            doc = self._text(self._get(url))
            lst = self._getlist(pq(doc)('li.col-25.col-m-12.mb20'))
            result['list'] = lst
            result['total'] = len(lst)
            result['pagecount'] = p + 1 if lst else p
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        try:
            vid = ids[0] if isinstance(ids, list) else ids
            m = re.search(r'(\d+)', str(vid))
            if not m:
                return {'list': []}
            vid = m.group(1)
            doc = self._text(self._get(self.host + '/voddetail/%s/' % vid))
            d = pq(doc)
            name = re.sub(r'\s+', ' ', d('h1.f-20.f-bold').text() or '').strip()
            y = re.search(r'(\d{4}-\d{2}-\d{2})', d('h6').text() or '')
            type_name = d('.detail-info-type h2 a').text().strip()
            # 可点击标签（点击=搜索该关键词），放简介前面
            tags = []
            for a in d('.tags-box a').items():
                t = a.text().strip()
                if t:
                    tags.append(self._cr(t, t))
            intro = re.sub(r'\s+', ' ', d('.tx-text p').text() or '').strip() or name
            content = (' '.join(tags) + '\n' + intro) if tags else intro
            pm = re.search(r'src="(https:[^"]+\.(?:jpg|jpeg|png|webp))"', doc)
            pic = pm.group(1) if pm else ''
            play = self._play(vid, d('a.tx-btn').attr('href'))
            vod = {
                'vod_id': '/voddetail/%s/' % vid,
                'vod_name': name,
                'vod_pic': self.plp + pic if pic else '',
                'vod_year': y.group(1) if y else '',
                'type_name': type_name,
                'vod_actor': '',
                'vod_director': '',
                'vod_remarks': '',
                'vod_content': content,
                'vod_play_from': '在线播放',
                'vod_play_url': '正片$' + play if play else '',
            }
            return {'list': [vod]}
        except Exception:
            return {'list': []}

    def _play(self, vid, plink):
        # 抓播放页 player_data 里的直链 m3u8/mp4
        try:
            url = plink or ('/vodplay/%s-1-1/' % vid)
            doc = self._text(self._get(self._abs(url)))
            m = re.search(r'"url":"(https:[^"]+?\.(?:m3u8|mp4)[^"]*)"', doc)
            return m.group(1).replace('\\/', '/') if m else ''
        except Exception:
            return ''

    def _search_list(self, name, p):
        kw = quote(str(name), safe='')
        doc = self._text(self._get(self.host + '/vodsearch/%s----------%s---/' % (kw, p)))
        return self._getlist(pq(doc)('li.col-25.col-m-12.mb20'))

    def searchContent(self, key, quick, pg="1"):
        result = {'list': [], 'page': int(pg or 1)}
        try:
            result['list'] = self._search_list(key, int(pg or 1))
        except Exception:
            pass
        return result

    def playerContent(self, flag, id, vipFlags):
        if '.m3u8' in id or '.mp4' in id:
            return {'parse': 0, 'url': self.plp + id, 'header': self.headers}
        return {'parse': 1, 'url': id, 'header': self.headers}

    def localProxy(self, param):
        return [404, 'text/plain', b'']
