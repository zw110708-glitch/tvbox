# -*- coding: utf-8 -*-
# 推特18+（xzhan18）OK影视 爬虫源
# 站点：https://h5.xzhan18.com  数据后端：https://api-user.xzhan18.com
import json, re
import requests
from urllib.parse import quote, urlencode
from base.spider import Spider


class Spider(Spider):

    def init(self, extend="{}"):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}

        self.site = config.get('site', 'https://h5.xzhan18.com').rstrip('/')
        self.api = config.get('api', 'https://api-user.xzhan18.com').rstrip('/')
        # ---- 代理三行（照抄，由 extend 传，没传就直连）----
        self.plp = config.get('plp', '')
        self.proxy = config.get('proxy', {})

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Origin': self.site,
            'Referer': self.site + '/',
        }

        # 推荐话题（站点导航硬编码的 5 个，无动态接口，固定）
        self.REC_TOPICS = [
            {'id': '4000000017', 'name': '福利姬', 'cover': 'https://twitter-prod.ingqicww.work/hr-ai/images/twitter/2026-08-19/f22346bac8b74ad2b9543f526a475f01.jpg'},
            {'id': '4000000007', 'name': '制服诱惑', 'cover': 'https://twitter-prod.ingqicww.work/hr-ai/images/twitter/2026-08-19/e852c1079caf4d138d65fe4cf2af353f.jpg'},
            {'id': '4000000021', 'name': '黑料吃瓜', 'cover': 'https://twitter-prod.ingqicww.work/hr-ai/images/twitter/2026-08-19/ac01534a5f3846ec8e89a7d627642cf7.jpg'},
            {'id': '4000000043', 'name': '动漫天堂', 'cover': 'https://twitter-prod.ingqicww.work/hr-ai/images/twitter/2026-08-19/c3d84e1ae6b6461b83c85c7bb91cec8e.jpg'},
            {'id': '4000000023', 'name': '少女萝莉', 'cover': 'https://twitter-prod.ingqicww.work/hr-ai/images/twitter/2026-08-19/49200988702b479a9c8f13554327e035.png'},
        ]
        # 推荐关注（站点导航硬编码的 4 个作者，固定）
        self.REC_AUTHORS = [
            {'id': '3000000009', 'name': '萝莉学院', 'handle': 'luolixueyuan', 'avatar': 'https://twitter-prod.ingqicww.work/hr-ai/images/twitter/2026-08-19/13128e2caf6246adb0553907fa779f14.jpeg'},
            {'id': '3000000028', 'name': '足控爱好者', 'handle': 'zukong', 'avatar': 'https://twitter-prod.ingqicww.work/hr-ai/images/twitter/2026-08-19/cef78ef159054b4cb8fce0351c6ecd71.jpg'},
            {'id': '3000000015', 'name': '女神社', 'handle': 'nvshenshe', 'avatar': 'https://twitter-prod.ingqicww.work/hr-ai/images/twitter/2026-08-19/6a114df771ea474fa48045af793c296b.jpg'},
            {'id': '3000000008', 'name': '鉴黄师', 'handle': 'jianhuangshi', 'avatar': 'https://twitter-prod.ingqicww.work/hr-ai/images/twitter/2026-08-19/f8bfb44a6a004698aa5de21091c45b22.jpg'},
        ]

    def getName(self):
        return '推特18+'

    def isVideoFormat(self, url):
        return bool(url and re.search(r'\.(m3u8|mp4|ts)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ---- 内部请求：一律走 self.proxy ----
    def _get(self, url, timeout=15):
        return requests.get(url, headers=self.headers, proxies=self.proxy, timeout=timeout, verify=False)

    def _get_json(self, url, timeout=15):
        r = self._get(url, timeout)
        return json.loads(r.text)

    # ---- 封面：CDN 图是 AES 加密的，走前端 media-proxy 解密，再加 plp ----
    def _pic(self, u):
        if not u:
            return ''
        u = str(u)
        if not u.startswith('http'):
            return ''
        return self.plp + self.site + '/media-proxy?url=' + quote(u, safe='')

    # ---- 可点击标签 ----
    def _cr(self, href, name):
        return '[a=cr:%s/]%s[/a]' % (json.dumps({'id': href, 'name': name}, ensure_ascii=False), name)

    # ---- 秒 -> 时长文本（MM:SS 或 H:MM:SS）----
    def _fmt_duration(self, sec):
        try:
            sec = int(float(sec))
        except Exception:
            return ''
        if sec <= 0:
            return ''
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        if h > 0:
            return '%d:%02d:%02d' % (h, m, s)
        return '%d:%02d' % (m, s)

    # ---- 后端 post 结构（feed/hot/topic/author/detail 通用）转列表项 ----
    def _to_vod(self, p):
        if not p:
            return None
        pid = str(p.get('id') or '')
        if not pid:
            return None
        title = p.get('title') or p.get('content') or p.get('text') or ''
        title = title.strip() or ('帖子 ' + pid)
        media = p.get('media') or []
        cover = ''
        duration = ''
        for m in media:
            if m.get('type') == 'video':
                cover = m.get('cover') or m.get('coverUrl') or cover
                duration = m.get('duration') or m.get('durationSeconds') or duration
                break
        if not cover:
            for m in media:
                if m.get('type') == 'image':
                    cover = m.get('url') or cover
                    break
        return {
            'vod_id': pid,
            'vod_name': title,
            'vod_pic': self._pic(cover),
            'vod_remarks': self._fmt_duration(duration),
        }

    # ---- 前端 list-page 结构（搜索用）转列表项 ----
    def _to_vod_lp(self, it):
        if not it:
            return None
        pid = str(it.get('id') or '')
        if not pid:
            return None
        title = it.get('text') or it.get('title') or ('帖子 ' + pid)
        media = it.get('media') or []
        cover = ''
        duration = ''
        for m in media:
            if m.get('type') == 'video':
                cover = m.get('coverUrl') or m.get('url') or cover
                duration = m.get('durationSeconds') or m.get('duration') or duration
                break
        if not cover:
            for m in media:
                if m.get('type') == 'image':
                    cover = m.get('url') or cover
                    break
        return {
            'vod_id': pid,
            'vod_name': title.strip(),
            'vod_pic': self._pic(cover),
            'vod_remarks': self._fmt_duration(duration),
        }

    # ---- 从后端 post 里取视频 m3u8 播放地址 ----
    def _video_url(self, p):
        for m in (p.get('media') or []):
            if m.get('type') == 'video':
                u = m.get('url') or m.get('playbackUrl') or ''
                if u:
                    return u
        return ''

    # ---- 话题名 -> 话题ID 映射（详情页可点击标签用，带缓存）----
    def _topic_map(self):
        if getattr(self, '_tmap', None) is not None:
            return self._tmap
        self._tmap = {}
        try:
            d = self._get_json(self.api + '/api/topic/list')
            for t in (d.get('data') or []):
                self._tmap[str(t.get('name') or '').strip()] = str(t.get('id') or '')
        except Exception:
            pass
        return self._tmap

    def homeContent(self, filter):
        result = {
            'class': [
                {'type_id': 'latest', 'type_name': '最新'},
                {'type_id': 'hot', 'type_name': '热榜推荐'},
                {'type_id': 'topics', 'type_name': '更多话题'},
                {'type_id': 'rectopics', 'type_name': '推荐话题'},
                {'type_id': 'recfollows', 'type_name': '推荐关注'},
            ],
            'filters': {
                'hot': [{'key': 'range', 'name': '榜单', 'value': [
                    {'n': '日榜精选', 'v': 'day'},
                    {'n': '周榜精选', 'v': 'week'},
                    {'n': '月榜精选', 'v': 'month'},
                    {'n': '总榜精选', 'v': 'all'},
                ]}],
            },
            'list': [],
        }
        # 首页推荐直接拉最新
        try:
            d = self._get_json(self.api + '/api/content/feed?tab=latest&pageNum=1&pageSize=20')
            for p in (d.get('data') or {}).get('list') or []:
                v = self._to_vod(p)
                if v:
                    result['list'].append(v)
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'page': int(pg or 1), 'pagecount': 1, 'limit': 50, 'total': 0}
        try:
            pg = int(pg or 1)
            tid = str(tid or '')

            # ---- 最新 / 推荐：后端 feed，标准分页 ----
            if tid in ('latest', 'recommended'):
                tab = 'latest' if tid == 'latest' else 'recommended'
                d = self._get_json(self.api + '/api/content/feed?tab=%s&pageNum=%d&pageSize=20' % (tab, pg))
                data = d.get('data') or {}
                for p in data.get('list') or []:
                    v = self._to_vod(p)
                    if v:
                        result['list'].append(v)
                result['pagecount'] = data.get('totalPages') or 1
                result['total'] = data.get('total') or 0

            # ---- 热榜：日/周/月/总榜（后端固定榜，range 仅作标记）----
            elif tid == 'hot':
                rng = 'day'
                if isinstance(extend, dict) and extend.get('range'):
                    rng = str(extend.get('range'))
                d = self._get_json(self.api + '/api/content/hot?range=%s&limit=50' % rng)
                for p in (d.get('data') or []):
                    v = self._to_vod(p)
                    if v:
                        result['list'].append(v)
                result['total'] = len(result['list'])

            # ---- 更多话题：话题卡片列表（vod_tag folder -> 点击进二级视频列表）----
            elif tid == 'topics':
                d = self._get_json(self.api + '/api/topic/list')
                for t in (d.get('data') or []):
                    tid0 = str(t.get('id') or '')
                    if not tid0:
                        continue
                    result['list'].append({
                        'vod_id': 'topic_' + tid0,
                        'vod_name': '#' + str(t.get('name') or ''),
                        'vod_pic': self._pic(t.get('coverUrl') or ''),
                        'vod_remarks': str(t.get('contentCount') or '0') + '个视频',
                        'vod_tag': 'folder',
                    })
                result['total'] = len(result['list'])

            # ---- 推荐话题：固定 5 个话题卡片 ----
            elif tid == 'rectopics':
                for t in self.REC_TOPICS:
                    result['list'].append({
                        'vod_id': 'topic_' + str(t['id']),
                        'vod_name': '#' + t['name'],
                        'vod_pic': self._pic(t.get('cover') or ''),
                        'vod_remarks': '推荐',
                        'vod_tag': 'folder',
                    })
                result['total'] = len(result['list'])

            # ---- 推荐关注：固定 4 个作者卡片 ----
            elif tid == 'recfollows':
                for a in self.REC_AUTHORS:
                    result['list'].append({
                        'vod_id': 'author_' + str(a['id']),
                        'vod_name': a['name'],
                        'vod_pic': self._pic(a.get('avatar') or ''),
                        'vod_remarks': '@' + a['handle'],
                        'vod_tag': 'folder',
                    })
                result['total'] = len(result['list'])

            # ---- 二级：话题视频 ----
            elif tid.startswith('topic_'):
                topic_id = tid[6:]
                d = self._get_json(self.api + '/api/content/topic/%s?limit=50' % topic_id)
                for p in (d.get('data') or []):
                    v = self._to_vod(p)
                    if v:
                        result['list'].append(v)
                result['total'] = len(result['list'])

            # ---- 二级：作者视频 ----
            elif tid.startswith('author_'):
                author_id = tid[7:]
                d = self._get_json(self.api + '/api/content/author/%s?limit=50' % author_id)
                for p in (d.get('data') or []):
                    v = self._to_vod(p)
                    if v:
                        result['list'].append(v)
                result['total'] = len(result['list'])

        except Exception:
            pass
        return result

    def detailContent(self, ids):
        try:
            vid = str(ids[0]) if isinstance(ids, list) and ids else str(ids)
        except Exception:
            vid = ''
        if not vid:
            return {'list': []}

        # 卡片/标签的 topic_、author_ 前缀走 categoryContent（二级视频列表），
        # 不会进 detailContent；这里兜底防呆返回空
        if vid.startswith('topic_') or vid.startswith('author_'):
            return {'list': []}

        # ---- 单个视频详情 ----
        vod = {}
        try:
            d = self._get_json(self.api + '/api/content/' + vid)
            p = d.get('data') or {}
            if not p:
                return {'list': []}
            title = (p.get('title') or p.get('content') or p.get('text') or '').strip()
            content = (p.get('content') or '').strip()
            media = p.get('media') or []
            author = p.get('author') or {}
            topics = p.get('topics') or []

            # 封面
            cover = ''
            for m in media:
                if m.get('type') == 'video':
                    cover = m.get('cover') or m.get('coverUrl') or cover
                    break
            if not cover:
                for m in media:
                    if m.get('type') == 'image':
                        cover = m.get('url') or cover
                        break

            aname = author.get('name') or author.get('displayName') or '未知作者'
            aid = author.get('id') or ''

            # 简介文本 + 末尾可点击 #话题标签
            text = content if content else title
            tags = []
            tmap = self._topic_map()
            # topics 可能是 [str] 或 [{id,name}]
            for t in topics:
                if isinstance(t, dict):
                    tname = str(t.get('name') or '').strip()
                    t_id = str(t.get('id') or '')
                else:
                    tname = str(t).strip()
                    t_id = tmap.get(tname, '')
                if not tname:
                    continue
                tag = tname if tname.startswith('#') else '#' + tname
                if t_id:
                    tags.append(self._cr('topic_' + t_id, tag))
                else:
                    tags.append(tag)
            if tags:
                text = (text + '\n' if text else '') + ' '.join(tags)

            # 导演位 = 作者（可点击 -> 作者视频）
            director = self._cr('author_' + str(aid), aname) if aid else aname

            # 播放地址
            vurl = self._video_url(p)

            views = p.get('views')
            remarks = (str(views) + '次播放') if views else ''

            vod = {
                'vod_id': vid,
                'vod_name': title or ('帖子 ' + vid),
                'vod_pic': self._pic(cover),
                'vod_director': director,
                'vod_content': text,
                'vod_remarks': remarks,
                'type_name': '视频',
            }
            if vurl:
                vod['vod_play_from'] = '播放'
                vod['vod_play_url'] = '正片$' + vurl
            else:
                vod['vod_play_from'] = ''
                vod['vod_play_url'] = ''
        except Exception:
            pass
        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        result = {'list': [], 'page': int(pg or 1)}
        try:
            pg = int(pg or 1)
            safe_key = quote(str(key), safe='')
            url = self.site + '/api/list-page?' + urlencode({'kind': 'search', 'query': str(key), 'pageNum': str(pg)})
            d = self._get_json(url)
            for it in (d.get('items') or []):
                v = self._to_vod_lp(it)
                if v:
                    result['list'].append(v)
        except Exception:
            pass
        return result

    def playerContent(self, flag, id, vipFlags):
        if '.m3u8' in id or '.mp4' in id:
            return {'parse': 0, 'url': self.plp + id, 'header': self.headers}
        return {'parse': 1, 'url': id, 'header': self.headers}

    def localProxy(self, param):
        return [404, 'text/plain', b'']
