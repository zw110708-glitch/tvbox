# -*- coding: utf-8 -*-
# 123AV.FUN 短视频源 —— OK影视(pg.jar/Chaquopy Py3.8)
# 站点: https://123av.fun (被墙, 需走 self.proxy)
# 视频/封面 CDN: vs.imgcaches.cc (m3u8 反代 twitter)
import json
import re
import requests
from urllib.parse import quote
from base.spider import Spider


class Spider(Spider):
    def init(self, extend="{}"):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        self.host = config.get('site', 'https://123av.fun')
        # ---- 代理三行（由 extend 传，没传就直连）----
        self.plp = config.get('plp', '')
        self.proxy = config.get('proxy', {})
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }

    def getName(self):
        return '123AV'

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

    # ---- 可点击标签 ----
    def _cr(self, href, name):
        return '[a=cr:%s/]%s[/a]' % (json.dumps({'id': href, 'name': name}, ensure_ascii=False), name)

    # ---- 秒数 -> mm:ss / h:mm:ss ----
    def _dur(self, sec):
        try:
            sec = int(sec)
        except Exception:
            return ''
        if sec >= 3600:
            return '%d:%02d:%02d' % (sec // 3600, (sec % 3600) // 60, sec % 60)
        return '%02d:%02d' % (sec // 60, sec % 60)

    # ---- 通用视频卡片提取（首页/排序/探索/搜索 同构，按 data-id 去重）----
    def _cards(self, html):
        vids = []
        seen = set()
        for m in re.finditer(r'<a\s[^>]*?data-src="([^"]+\.m3u8[^"]*)"[^>]*?>(.*?)</a>', html, re.S):
            block = m.group(0)
            mid = re.search(r'data-id="(\d+)"', block)
            if not mid:
                continue
            vid = mid.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            pic = ''
            pm = re.search(r'data-poster="([^"]+)"', block)
            if pm:
                pic = pm.group(1)
            alt = re.search(r'alt="([^"]*)"', block)
            name = alt.group(1).strip() if alt else ''
            if not name:
                name = '视频' + vid
            dur = ''
            dm = re.search(r'data-duration="(\d+)"', block)
            if dm:
                dur = self._dur(dm.group(1))
            else:
                vd = re.search(r'video-date[^>]*>\s*([\d:]+)\s*</div>', block)
                if vd:
                    dur = vd.group(1).strip()
            vids.append({
                'vod_id': vid,
                'vod_name': name,
                'vod_pic': self.plp + pic if pic else '',
                'vod_remarks': dur,
            })
        return vids

    def homeContent(self, filter):
        return {
            'class': [
                {'type_id': 'index', 'type_name': '首页推荐'},
                {'type_id': 'publish-time/sort-desc', 'type_name': '最新发布'},
                {'type_id': 'view-count/sort-desc', 'type_name': '最多播放'},
                {'type_id': 'comment-count/sort-desc', 'type_name': '最多评论'},
                {'type_id': 'favorite-count/sort-desc', 'type_name': '最多收藏'},
                {'type_id': 'explore', 'type_name': '探索发现'},
            ],
            'filters': {}
        }

    def homeVideoContent(self):
        return self.categoryContent('index', 1, {}, {})

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg or 1)
        if tid.startswith('author_'):
            # 作者页（可点击标签跳转兜底）
            url = self.host + '/author-info/' + tid[7:]
            if page > 1:
                url += '/page-%d' % page
        elif tid == 'index':
            url = self.host if page <= 1 else self.host + '/page-%d' % page
        else:
            url = self.host + '/' + tid
            if page > 1:
                url += '/page-%d' % page
        result = {'list': [], 'page': page, 'pagecount': 9999, 'limit': 100, 'total': 999999}
        try:
            r = self._get(url)
            result['list'] = self._cards(self._text(r))
        except Exception:
            pass
        return result

    def searchContent(self, key, quick, pg="1"):
        page = int(pg or 1)
        result = {'list': [], 'page': page}
        try:
            if key.startswith('author_'):
                # 作者可点击标签：跳作者页
                url = '%s/author-info/%s' % (self.host, key[7:])
                if page > 1:
                    url += '/page-%d' % page
            else:
                # 正确搜索接口：/search/q-{关键词}
                url = '%s/search/q-%s' % (self.host, quote(key))
                if page > 1:
                    url += '/page-%d' % page
            r = self._get(url)
            result['list'] = self._cards(self._text(r))
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, (list, tuple)) else ids
        vod = {'vod_id': vid}
        try:
            r = self._get(self.host + '/detail/' + str(vid))  # 301 跟随到带 slug 的完整页
            html = self._text(r)
            title = re.search(r'property="og:title"\s+content="([^"]*)"', html)
            if title:
                vod['vod_name'] = title.group(1).strip()
            pic = re.search(r'property="og:image"\s+content="([^"]*)"', html)
            if not pic:
                pic = re.search(r'data-poster="([^"]+)"', html)
            if pic:
                vod['vod_pic'] = self.plp + pic.group(1)
            desc = re.search(r'property="og:description"\s+content="([^"]*)"', html)
            content = desc.group(1) if desc else ''
            # 标签（可点击，点击搜索标签）
            tags = re.findall(r'class="rounded-lg[^"]*text-active[^"]*">\s*([^<]+?)\s*</div>', html)
            cr_tags = [self._cr(t.strip(), t.strip()) for t in tags if t.strip()]
            # 作者（可点击，点击跳作者页 /author-info/{userid}）
            author = re.search(r'data-username="([^"]*)"', html)
            uid = re.search(r'data-userid="(\d+)"', html)
            actor = ''
            if author and author.group(1).strip():
                name = author.group(1).strip()
                if uid:
                    actor = self._cr('author_' + uid.group(1), name)
                else:
                    actor = name
            # 时长 / 发布时间
            dur = re.search(r'property="video:duration"\s+content="(\d+)"', html)
            remarks = self._dur(dur.group(1)) if dur else ''
            rel = re.search(r'property="video:release_date"\s+content="([^"]*)T', html)
            if rel:
                remarks = remarks + ('  ' if remarks else '') + rel.group(1)
            # 播放源：主源(vs.imgcaches.cc) + 备用源(twitter)
            m3u8 = re.search(r'data-src="(https?://[^"]+\.m3u8[^"]*)"', html)
            tw = re.search(r'data-twitter="(https?://[^"]+)"', html)
            play_from = []
            play_url = []
            if m3u8:
                play_from.append('高清源')
                play_url.append('正片$' + m3u8.group(1))
            if tw and tw.group(1).strip():
                play_from.append('备用源')
                play_url.append('正片$' + tw.group(1))
            if play_url:
                vod['vod_play_from'] = '$$$'.join(play_from)
                vod['vod_play_url'] = '$$$'.join(play_url)
            vod['vod_remarks'] = remarks
            vod['vod_content'] = content
            if cr_tags:
                vod['vod_content'] = content + ('\n' if content else '') + ' '.join(cr_tags)
            vod['vod_actor'] = actor
            vod['type_name'] = '短视频'
        except Exception:
            pass
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        hdr = dict(self.headers)
        hdr['Referer'] = self.host + '/'
        if re.search(r'\.(m3u8|mp4|ts)(\?|$)', str(id), re.I):
            return {'parse': 0, 'url': self.plp + id, 'header': hdr}
        return {'parse': 1, 'url': id, 'header': hdr}

    def localProxy(self, param):
        return [404, 'text/plain', b'']
