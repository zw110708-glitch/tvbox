# -*- coding: utf-8 -*-
import re
import os
import sys
import json
import ssl
import base64
import urllib3
import threading
import hashlib
import time
from datetime import datetime
from urllib.parse import quote, urljoin, unquote, urlparse, parse_qs
from pyquery import PyQuery as pq
from base64 import b64decode, b64encode
from requests import Session
from requests.adapters import HTTPAdapter

sys.path.append('..')
from base.spider import Spider

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        pool_kwargs['ssl_context'] = ctx
        return super().init_poolmanager(
            connections,
            maxsize,
            block=block,
            **pool_kwargs
        )

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        proxy_kwargs['ssl_context'] = ctx
        return super().proxy_manager_for(proxy, **proxy_kwargs)


class Spider(Spider):
    host = "https://javmenu.com"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/98.0.4758.101 Mobile Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    # ==================== 初始化 ====================
    def init(self, extend=""):
        self.last_vod_pic = ""
        self.ack_mp4 = (
            "https://vd2.bdstatic.com/mda-nj5kxa8kr7wgq6ie/"
            "sc/cae_h264_nowatermark/1653272065989267185/"
            "mda-nj5kxa8kr7wgq6ie.mp4"
        )

        if extend:
            try:
                ext_data = json.loads(extend)
                if "host" in ext_data:
                    self.host = ext_data["host"].rstrip('/')
                if "ack_mp4" in ext_data:
                    self.ack_mp4 = ext_data.get("ack_mp4") or self.ack_mp4
            except Exception as e:
                print(f"init extend error: {e}")

        self.headers['referer'] = f'{self.host}/'
        self.session = Session()
        self.session.headers.update(self.headers)
        self.session.verify = False
        http_adapter = HTTPAdapter(max_retries=3)
        ssl_adapter = SSLAdapter(max_retries=3)
        self.session.mount('http://', http_adapter)
        self.session.mount('https://', ssl_adapter)

    def getName(self):
        return "JAV目录大全"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        pass

    def destroy(self):
        try:
            if self.session:
                self.session.close()
        except:
            pass

    # ==================== 首页 ====================
    def homeContent(self, filter):
        cateManual = {
            "有码在线": "/zh/censored/online?order=publish",
            "无码在线": "/zh/uncensored/online",
            "FC2在线": "/zh/fc2/online",
            "国产在线": "/zh/chinese/online",
            "日榜": "/zh/rank/censored/day",
            "周榜": "/zh/rank/censored/week",
            "月榜": "/zh/rank/censored/month",
            "有码磁力": "/zh/censored?order=publish",
            "无码磁力": "/zh/uncensored?order=publish",
            "成人动画": "/zh/hanime/online",
            "欧美在线": "/zh/western/online",
            "女优榜": "/zh/rank/censored/actress"
        }
        return {
            'class': [
                {'type_name': k, 'type_id': v}
                for k, v in cateManual.items()
            ]
        }

    def homeVideoContent(self):
        try:
            data = self.getpq("/zh")
            return {'list': self.getlist(data(".video-list-item"))}
        except Exception as e:
            print(f"homeVideoContent error: {e}")
            return {'list': []}

    # ==================== 分类 ====================
    def categoryContent(self, tid, pg, filter, extend):
        try:
            base = f"{self.host}{tid}" if not tid.startswith('http') else tid
            if '?' in base:
                url = base if str(pg) == '1' else f"{base}&page={pg}"
            else:
                url = base if str(pg) == '1' else f"{base}?page={pg}"
            data = self.getpq(url)
            if 'actress' in tid:
                vlist = self.getActressList(data)
                pagecount = 9999
            else:
                vlist = self.getlist(data(".video-list-item"))
                pagecount = self.parsePageCount(data)
            return {
                'list': vlist,
                'page': str(pg),
                'pagecount': pagecount,
                'limit': 90,
                'total': 999999
            }
        except Exception as e:
            print(f"categoryContent error: {e}")
            return {
                'list': [],
                'page': str(pg),
                'pagecount': 0,
                'limit': 90,
                'total': 0
            }

    def getActressList(self, data):
        vlist = []
        try:
            items = data('.actor-item, .actress-item, .actor-card, .col-6.col-md-3, .col-4.col-md-2')
            if not items:
                items = data('a[href*="/actor/"]').parent()
            for item in items.items():
                a = item('a[href*="/actor/"]').eq(0)
                if not a:
                    a = item('a').eq(0)
                if not a:
                    continue
                link = a.attr('href')
                if not link:
                    continue
                if not link.startswith('http'):
                    link = self.host.rstrip('/') + '/' + link.lstrip('/')
                name = (item('.actor-name, .card-title, h5').text() or a.text() or a.attr('alt') or '未知')
                img = item('img').attr('data-src') or item('img').attr('src')
                if img:
                    if img.startswith('//'):
                        img = 'https:' + img
                    elif img.startswith('/'):
                        img = self.host + img
                vlist.append({
                    'vod_id': link,
                    'vod_name': name.strip(),
                    'vod_pic': img or '',
                    'vod_remarks': '',
                    'vod_year': '',
                    'vod_area': '',
                    'vod_actor': '',
                    'vod_director': '',
                    'vod_content': ''
                })
        except Exception as e:
            print(f"getActressList error: {e}")
        return vlist

    # ==================== 详情 ====================
    def detailContent(self, ids):
        try:
            raw_id = ids[0]
            vod_id = raw_id
            list_pic = ""

            if isinstance(raw_id, str) and "@@" in raw_id:
                try:
                    _id, _pic_b64 = raw_id.rsplit("@@", 1)
                    _pic = self.d64(_pic_b64)
                    if _id:
                        vod_id = _id
                    if _pic and _pic.startswith("http"):
                        list_pic = _pic
                except Exception as e:
                    print(f"detail id unpack error: {e}")

            url = vod_id if str(vod_id).startswith('http') else f"{self.host}{vod_id}"
            data = self.getpq(url)

            if '/actor/' in url:
                return self.getActressVideos(url, data)

            actors = self.getActors(data)
            actor_links = self.getActorLinks(data)
            vod_actor = actor_links if actor_links else actors

            online_url = self.getPlaylist(data, url)
            magnet_url = self.getMagnetPlaylist(data)

            cover = list_pic or self.getCover(data)
            self.last_vod_pic = cover or ""

            play_from = []
            play_url = []

            if online_url:
                play_from.append('在线播放')
                play_url.append(online_url)

            if magnet_url:
                play_from.append('磁力推送')
                play_url.append(magnet_url)

            play_from.append('0')
            play_url.append('不会自动下载，请使用磁力推送$__ACK__')

            vod = {
                'vod_id': vod_id,
                'vod_name': self.getVodName(data),
                'vod_pic': cover,
                'vod_content': self.getVodContent(data),
                'vod_director': '',
                'vod_actor': vod_actor,
                'vod_area': '日本',
                'vod_year': self.getYear(data),
                'vod_remarks': self.getRemarks(data),
                'vod_play_from': '$$$'.join(play_from),
                'vod_play_url': '$$$'.join(play_url)
            }
            return {'list': [vod]}
        except Exception as e:
            print(f"detailContent error: {e}")
            return {'list': []}

    def getActressVideos(self, url, data):
        try:
            videos = self.getlist(data(".video-list-item"))
            actress_name = data('h1').text() or url.split('/')[-1] or '女优'
            if not videos:
                return {'list': []}
            lines = []
            for v in videos:
                vid = v.get('vod_id', '')
                name = v.get('vod_name', '未知')
                encoded_id = self.e64(vid)
                lines.append(f"{self.cleanPlayName(name)}${encoded_id}")
            vod_play_url = '#'.join(lines)
            return {
                'list': [{
                    'vod_id': url,
                    'vod_name': f'{actress_name} 作品列表',
                    'vod_pic': self.getCover(data),
                    'vod_content': '',
                    'vod_director': '',
                    'vod_actor': actress_name,
                    'vod_area': '日本',
                    'vod_year': '',
                    'vod_remarks': f'共{len(videos)}部作品',
                    'vod_play_from': '作品列表',
                    'vod_play_url': vod_play_url
                }]
            }
        except Exception as e:
            print(f"getActressVideos error: {e}")
            return {'list': []}

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg="1"):
        try:
            url = f"{self.host}/zh/search?wd={quote(key)}&page={pg}"
            data = self.getpq(url)
            return {'list': self.getlist(data(".video-list-item"))}
        except Exception as e:
            print(f"searchContent error: {e}")
            return {'list': []}

    # ==================== 播放 ====================
    def playerContent(self, flag, id, vipFlags):
        try:
            flag = str(flag or '')
            id = str(id or '')

            if flag == "0" or id == "__ACK__":
                return self.returnAckVideo(self.last_vod_pic)

            if id.startswith('ma2gnet:'):
                real_mag = id.replace('ma2gnet:', 'magnet:', 1)
                return {
                    'parse': 0,
                    'url': 'push://' + real_mag,
                    'pic': self.last_vod_pic,
                    'poster': self.last_vod_pic
                }

            real_url = self.d64(id) or id
            low = real_url.lower()

            if self.isAdUrl(real_url):
                return {
                    'parse': 0,
                    'url': '',
                    'pic': self.last_vod_pic,
                    'poster': self.last_vod_pic
                }

            is_direct = any(x in low for x in ['.m3u8', '.mp4', '.flv', '.mpd'])
            return {
                'parse': 0 if is_direct else 1,
                'url': real_url,
                'header': self.headers,
                'pic': self.last_vod_pic,
                'poster': self.last_vod_pic
            }
        except Exception as e:
            print(f"playerContent error: {e}")
            return {
                'parse': 1,
                'url': id,
                'pic': self.last_vod_pic,
                'poster': self.last_vod_pic
            }

    def returnAckVideo(self, pic=""):
        ret = {
            'parse': 0,
            'playUrl': '',
            'url': self.ack_mp4,
            'header': {
                'User-Agent': self.headers.get('User-Agent', ''),
                'Referer': self.host + '/'
            }
        }
        if pic:
            ret['pic'] = pic
            ret['poster'] = pic
        return ret

    # ==================== 列表通用解析 ====================
    def getlist(self, data):
        vlist = []
        try:
            for item in data.items():
                link = item('a').attr('href')
                if not link:
                    continue
                if '/zh/' not in link and not link.startswith('http'):
                    continue
                if not link.startswith('http'):
                    link = self.host.rstrip('/') + '/' + link.lstrip('/')

                name = self.getVideoName(item)
                if not name:
                    continue

                remarks = self.getListRemarks(item)
                if item('a[href^="magnet:"]').attr('href'):
                    remarks = (remarks + ' 🧲').strip()

                pic = self.getListPicture(item)
                packed_id = f"{link}@@{self.e64(pic)}" if pic else link

                vlist.append({
                    'vod_id': packed_id,
                    'vod_name': name,
                    'vod_pic': pic,
                    'vod_remarks': remarks,
                    'vod_year': '',
                    'vod_area': '',
                    'vod_actor': '',
                    'vod_director': '',
                    'vod_content': ''
                })
        except Exception as e:
            print(f"getlist error: {e}")
        return vlist

    def getVideoName(self, item):
        name = item('.card-title').text()
        if not name:
            name = item('img').attr('alt')
        if not name:
            name = item('a').attr('title')
        if name:
            name = name.split(' - ')[0].strip()
        return name or ''

    def getListRemarks(self, item):
        remarks = item('.label').text()
        if not remarks:
            remarks = item('.text-muted').text()
        if not remarks:
            remarks = item('.badge').text()
        return (remarks or '').strip()

    def getListPicture(self, item):
        try:
            for img in item('img').items():
                pic = img.attr('data-src') or img.attr('src')
                if pic and not any(k in pic for k in [
                    'button_logo', 'no_preview', 'loading.gif', 'loading.png'
                ]):
                    if pic.startswith('//'):
                        pic = 'https:' + pic
                    elif pic.startswith('/'):
                        pic = self.host + pic
                    return pic
        except:
            pass
        return ''

    # ==================== 详情字段解析 ====================
    def getCover(self, data):
        try:
            for img in data('img').items():
                pic = img.attr('data-src') or img.attr('src')
                if pic and not any(k in pic for k in [
                    'button_logo', 'no_preview', 'loading.gif', 'loading.png'
                ]):
                    if pic.startswith('//'):
                        pic = 'https:' + pic
                    elif pic.startswith('/'):
                        pic = self.host + pic
                    return pic
        except:
            pass
        return ''

    def getVodName(self, data):
        name = data('h1').text()
        if not name:
            title = data('title').text()
            if title:
                name = title.split(' - ')[0]
        return name or '未知'

    def getVodContent(self, data):
        content = (
            data('.card-text').text()
            or data('meta[name="description"]').attr('content')
            or ''
        )
        return content

    def getActors(self, data):
        try:
            actors = []
            for a in data('a[href*="/actor/"]').items():
                t = a.text().strip()
                if t and t not in actors:
                    actors.append(t)
            return ','.join(actors) if actors else '未知'
        except:
            return '未知'

    def getActorLinks(self, data):
        try:
            links = []
            for a in data('a[href*="/actor/"]').items():
                name = a.text().strip()
                href = a.attr('href')
                if name and href:
                    if not href.startswith('http'):
                        href = self.host + href
                    links.append(f"{name}${href}")
            return '#'.join(links) if links else ''
        except:
            return ''

    def getYear(self, data):
        try:
            m = re.search(r'(\d{4})', data('.text-muted').text())
            return m.group(1) if m else ''
        except:
            return ''

    def getRemarks(self, data):
        try:
            tags = []
            for t in data('.badge').items():
                txt = t.text().strip()
                if txt and txt not in tags:
                    tags.append(txt)
            return ' '.join(tags) if tags else ''
        except:
            return ''

    def parsePageCount(self, data):
        try:
            pages = data('.pagination .page-item a.page-link')
            if not pages:
                pages = data('.pagination a')
            max_page = 1
            for a in pages.items():
                text = a.text().strip()
                if text.isdigit():
                    max_page = max(max_page, int(text))
            return max_page if max_page > 1 else 1000
        except:
            return 1000

    # ==================== 在线播放地址解析 ====================
    def getPlaylist(self, data, url):
        try:
            play_urls = []
            seen = set()

            def normalize_link(link):
                if not link:
                    return ''
                link = link.strip().replace('&amp;', '&')
                if link.startswith('//'):
                    link = 'https:' + link
                elif link.startswith('/'):
                    link = urljoin(self.host, link)
                elif not link.startswith('http'):
                    link = urljoin(url, link)
                return link

            def is_direct_video(link):
                if not link:
                    return False
                low = link.lower()
                return any(x in low for x in ['.m3u8', '.mp4', '.flv', '.mpd'])

            def is_bad_play_url(link):
                if not link:
                    return True
                low = link.lower()
                if self.isAdUrl(link):
                    return True
                if low.startswith('magnet:') or low.startswith('ma2gnet:'):
                    return True
                if low.startswith('javascript:') or low == '#':
                    return True
                nav_keys = [
                    '/zh/censored', '/zh/uncensored', '/zh/fc2', '/zh/chinese',
                    '/zh/hanime', '/zh/western', '/zh/rank', '/zh/actor',
                    '/zh/search', '/zh/genre', '/zh/series', '/zh/studio',
                    '/zh/director', '/zh/maker', '/zh/label', '/zh/tag', '/zh/code'
                ]
                for k in nav_keys:
                    if k in low and not is_direct_video(low):
                        return True
                return False

            def clean_line_name(name, default_name):
                name = (name or default_name).strip()
                name = re.sub(r'\s+', ' ', name).replace('#', '＃').replace('$', '＄')
                bad_names = [
                    '有码', '无码', '欧美', 'FC2', 'fc2', '国产', '成人动画', '成人大全',
                    '在线看', '在线看 New', 'New', '可下载', '含预览', '中文字幕', '分享',
                    '回报未能播放', 'Twitter / X', 'Facebook', 'Telegram', 'WhatsApp', '预览'
                ]
                if name in bad_names or len(name) > 30:
                    return default_name
                return name or default_name

            def add_play(name, link):
                link = normalize_link(link)
                if not link or is_bad_play_url(link) or not is_direct_video(link):
                    return
                low = link.lower()
                if 'freepv' in low or 'cc3001.dmm.co.jp' in low or 'litevideo' in low:
                    return
                if link in seen:
                    return
                seen.add(link)
                no = len(play_urls) + 1
                play_urls.append(f"{clean_line_name(name, f'线路 {no}')}${self.e64(link)}")

            for a in data('#player-tab a[data-m3u8]').items():
                m3u8 = a.attr('data-m3u8') or ''
                text = a.text().strip() or ''
                data_source = (a.attr('data-source') or '').strip().lower()
                data_key = (a.attr('data-key') or '').strip().lower()
                data_target = (a.attr('data-target') or '').strip().lower()
                if data_source == 'preview' or data_key == 'preview' or 'preview' in data_target:
                    continue
                add_play(text or f'线路 {len(play_urls)+1}', m3u8)

            player_area = data('#player-tab, #tab-content, #pills-tabContent, .single-video, .video-player, .player, [id*="player"], [class*="player"]')
            for el in player_area.find('[data-m3u8]').items():
                m3u8 = el.attr('data-m3u8') or ''
                text = el.text().strip() or el.attr('title') or ''
                data_source = (el.attr('data-source') or '').strip().lower()
                data_key = (el.attr('data-key') or '').strip().lower()
                data_target = (el.attr('data-target') or '').strip().lower()
                if data_source == 'preview' or data_key == 'preview' or 'preview' in data_target:
                    continue
                add_play(text or f'线路 {len(play_urls)+1}', m3u8)

            for script in data('script[type="application/ld+json"]').items():
                txt = script.text().strip()
                if not txt:
                    continue
                for m in re.finditer(r'"contentUrl"\s*:\s*"([^"]+)"', txt, re.I):
                    add_play(f'线路 {len(play_urls)+1}', m.group(1))

            for source in data('video[src], source[src]').items():
                src = source.attr('src') or ''
                parent_html = str(source.parents('.tab-pane').eq(0))
                if 'pills-preview' in parent_html or 'player-preview' in parent_html:
                    continue
                add_play(f'线路 {len(play_urls)+1}', src)

            html = str(data)
            for p in [
                r'https?://[^\'"\s<>]+?\.m3u8[^\'"\s<>]*',
                r'https?://[^\'"\s<>]+?\.mp4[^\'"\s<>]*',
                r'https?://[^\'"\s<>]+?\.flv[^\'"\s<>]*',
                r'https?://[^\'"\s<>]+?\.mpd[^\'"\s<>]*'
            ]:
                for m in re.finditer(p, html, re.I):
                    add_play(f'线路 {len(play_urls)+1}', m.group(0))

            return '#'.join(play_urls[:10]) if play_urls else ''
        except Exception as e:
            print(f"getPlaylist error: {e}")
            return ''

    # ==================== 磁力链接提取 ====================
    def getMagnetPlaylist(self, data):
        try:
            magnets = []
            seen = set()

            def normalize_magnet(href):
                if not href:
                    return ''
                href = href.strip().replace('&amp;', '&')
                href = re.sub(r'\s+', '', href)
                if not href.startswith('magnet:'):
                    return ''
                return href

            def get_hash(href):
                m = re.search(r'btih:([a-zA-Z0-9]+)', href)
                return m.group(1) if m else ''

            def add_magnet(name, href):
                href = normalize_magnet(href)
                if not href or href in seen:
                    return
                seen.add(href)
                h = get_hash(href)
                short_hash = h[:8].upper() if h else ''
                name = self.cleanPlayName(name) or '磁力链接'
                if short_hash and short_hash not in name.upper():
                    name = f"{name} {short_hash}"
                magnets.append(f"{name}${href.replace('magnet:', 'ma2gnet:', 1)}")

            for tr in data('table.magnet-table tbody tr').items():
                href = tr('a[href^="magnet:"]').attr('href') or tr('[data-clipboard-text^="magnet:"]').attr('data-clipboard-text') or ''
                href = normalize_magnet(href)
                if not href:
                    continue

                title = tr('td').eq(0).find('a span').eq(0).text().strip() or tr('td').eq(0).find('a').eq(0).text().strip()
                badges = []
                for b in tr('td').eq(0).find('.badge').items():
                    t = b.text().strip()
                    if t and t not in badges:
                        badges.append(t)
                date = tr('td.date span').eq(0).text().strip() or tr('td').eq(1).text().strip()
                short_hash = get_hash(href)[:8].upper() if get_hash(href) else ''
                parts = ([title] if title else []) + badges + ([date] if date else []) + ([short_hash] if short_hash else [])
                add_magnet(' '.join(parts), href)

            for a in data('a[href^="magnet:"]').items():
                href = normalize_magnet(a.attr('href') or '')
                if not href:
                    continue
                title = a.find('span').eq(0).text().strip() or a.text().strip()
                tr = a.parents('tr').eq(0)
                badges, date = [], ''
                if tr:
                    for b in tr.find('.badge').items():
                        t = b.text().strip()
                        if t and t not in badges:
                            badges.append(t)
                    date = tr.find('td.date span').eq(0).text().strip() or tr.find('td').eq(1).text().strip()
                short_hash = get_hash(href)[:8].upper() if get_hash(href) else ''
                parts = ([title] if title else []) + badges + ([date] if date else []) + ([short_hash] if short_hash else [])
                add_magnet(' '.join(parts), href)

            for el in data('[data-clipboard-text^="magnet:"]').items():
                href = normalize_magnet(el.attr('data-clipboard-text') or '')
                if not href:
                    continue
                tr = el.parents('tr').eq(0)
                title, badges, date = '', [], ''
                if tr:
                    title = tr.find('td').eq(0).find('a span').eq(0).text().strip() or tr.find('td').eq(0).find('a').eq(0).text().strip()
                    for b in tr.find('td').eq(0).find('.badge').items():
                        t = b.text().strip()
                        if t and t not in badges:
                            badges.append(t)
                    date = tr.find('td.date span').eq(0).text().strip() or tr.find('td').eq(1).text().strip()
                if not title:
                    title = el.text().strip() or el.parent().text().strip()
                short_hash = get_hash(href)[:8].upper() if get_hash(href) else ''
                parts = ([title] if title else []) + badges + ([date] if date else []) + ([short_hash] if short_hash else [])
                add_magnet(' '.join(parts), href)

            for attr in ['data-magnet', 'data-url', 'data-href', 'data-link', 'data-value']:
                for el in data(f'[{attr}]').items():
                    href = normalize_magnet(el.attr(attr) or '')
                    if not href:
                        continue
                    name = el.text().strip()
                    if not name:
                        tr = el.parents('tr').eq(0)
                        name = tr.text().strip() if tr else ''
                    add_magnet(name, href)

            for el in data('[onclick]').items():
                onclick = el.attr('onclick') or ''
                for m in re.finditer(r'magnet:\?xt=urn:btih:[^\'"\s<>]+', onclick):
                    href = normalize_magnet(m.group(0))
                    if not href:
                        continue
                    name = el.text().strip()
                    if not name:
                        tr = el.parents('tr').eq(0)
                        name = tr.text().strip() if tr else ''
                    add_magnet(name, href)

            html = str(data)
            for m in re.finditer(r'magnet:\?xt=urn:btih:[^\'"\s<>]+', html):
                href = normalize_magnet(m.group(0))
                if not href:
                    continue
                h = get_hash(href)
                add_magnet(f"磁力链接 {h[:8].upper()}" if h else "磁力链接", href)

            return '#'.join(magnets)
        except Exception as e:
            print(f"getMagnetPlaylist error: {e}")
            return ''

    # ==================== 请求 ====================
    def getpq(self, path=''):
        try:
            url = path if path.startswith('http') else f'{self.host}{path}'
            urls = [url]
            if 'javmenu.com' in url:
                urls.append(url.replace('javmenu.com', 'javmenu.org'))
            elif 'javmenu.org' in url:
                urls.append(url.replace('javmenu.org', 'javmenu.com'))

            for u in urls:
                try:
                    rsp = self.session.get(u, timeout=30, allow_redirects=True)
                    rsp.encoding = 'utf-8'
                    if rsp.status_code == 200:
                        return pq(rsp.text)
                except Exception as e:
                    print(f"request error: {u} -> {e}")
        except Exception as e:
            print(f"getpq error: {e}")
        return pq('')

    # ==================== 工具函数 ====================
    def e64(self, text):
        try:
            return b64encode(text.encode('utf-8')).decode('utf-8')
        except:
            return ''

    def d64(self, encoded_text):
        try:
            return b64decode(encoded_text.encode('utf-8')).decode('utf-8')
        except:
            return ''

    def cleanPlayName(self, name):
        try:
            name = name or ''
            name = re.sub(r'\s+', ' ', name).strip()
            name = name.replace('#', '＃')
            name = name.replace('$', '＄')
            if len(name) > 80:
                name = name[:80]
            return name
        except:
            return name or ''

    def cleanText(self, text):
        try:
            text = text or ""
            text = str(text).replace("\xa0", " ").replace("&nbsp;", " ").replace("\u3000", " ")
            text = re.sub(r"\s+", " ", text)
            return text.strip()
        except Exception:
            return text or ""

    def isAdUrl(self, url):
        try:
            if not url:
                return True
            low = url.lower()
            ad_keywords = [
                'ads', 'adserver', 'doubleclick', 'googleads', 'googlesyndication',
                'analytics', 'stat', 'hm.baidu', 'cnzz', 'pop', 'banner', 'promo',
                'track', 'tracker', 'click', 'spider', 'counter', 'loading', 'logo',
                'button', 'vast', 'ima', 'preroll', 'advert', '/ad/', '_ad_', '-ad-', 'ad.'
            ]
            bad_exts = [
                '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.css', '.js',
                '.ico', '.woff', '.woff2', '.ttf', '.apk', '.zip', '.rar'
            ]
            if any(k in low for k in ad_keywords):
                return True
            if any(ext in low for ext in bad_exts):
                return True
            if low.startswith('javascript:'):
                return True
            if low == '#':
                return True
            return False
        except:
            return True


# ===== FINAL_JAVMENU_SITE_IMAGE_ONLINE_PROXY_BEGIN =====
# -*- coding: utf-8 -*-
# ============================================================
# 原始代理穿透补丁（恢复）
# ============================================================

import json as _jmpx_json
import re as _jmpx_re
from urllib.parse import quote as _jmpx_quote
from urllib.parse import unquote as _jmpx_unquote
from urllib.parse import urljoin as _jmpx_urljoin
from urllib.parse import urlparse as _jmpx_urlparse
from urllib.parse import parse_qs as _jmpx_parse_qs

try:
    from requests import Session as _jmpx_Session
except Exception:
    _jmpx_Session = None

try:
    from pyquery import PyQuery as _jmpx_pq
except Exception:
    _jmpx_pq = None


# 保存原始方法
Spider._jmpx_old_init = Spider.init
Spider._jmpx_old_getpq = Spider.getpq
Spider._jmpx_old_getListPicture = Spider.getListPicture
Spider._jmpx_old_getCover = Spider.getCover
Spider._jmpx_old_categoryContent = Spider.categoryContent
Spider._jmpx_old_searchContent = Spider.searchContent
Spider._jmpx_old_detailContent = Spider.detailContent
Spider._jmpx_old_playerContent = Spider.playerContent
Spider._jmpx_old_localProxy = getattr(Spider, "localProxy", None)


def _jmpx_default_proxy():
    return "http://127.0.0.1:10172"


def _jmpx_get_site_proxy(self):
    try:
        p = (
            getattr(self, "site_proxy", "")
            or getattr(self, "javmenu_proxy", "")
            or getattr(self, "proxy_url", "")
            or ""
        )
        p = str(p or "").strip()
        if p:
            return p
    except Exception:
        pass
    return _jmpx_default_proxy()


def _jmpx_proxies(self):
    p = _jmpx_get_site_proxy(self)
    if not p:
        return None
    return {
        "http": p,
        "https": p,
    }


def _jmpx_clean_url(self, url, base_url=None):
    try:
        url = str(url or "").strip().replace("&amp;", "&")
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if base_url:
            return _jmpx_urljoin(base_url, url)
        host = getattr(self, "host", "https://javmenu.com").rstrip("/")
        return _jmpx_urljoin(host + "/", url.lstrip("/"))
    except Exception:
        return str(url or "")


def _jmpx_is_local_proxy_url(url):
    try:
        u = str(url or "")
        return (
            "/proxy?" in u
            and "url=" in u
            and (
                "127.0.0.1" in u
                or "localhost" in u
                or ":9978" in u
            )
        )
    except Exception:
        return False


def _jmpx_unwrap_proxy_url(url):
    try:
        url = str(url or "").strip()
        if not url:
            return ""
        for _ in range(10):
            url = _jmpx_unquote(url)
            if not _jmpx_is_local_proxy_url(url):
                break
            up = _jmpx_urlparse(url)
            qs = _jmpx_parse_qs(up.query)
            inner = ""
            if "url" in qs and qs["url"]:
                inner = qs["url"][0]
            if not inner:
                break
            inner = _jmpx_unquote(inner)
            if inner == url:
                break
            url = inner
        return url
    except Exception:
        return str(url or "")


def _jmpx_is_img(url):
    try:
        u = str(url or "").lower()
        if u.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")):
            return True
        if "image" in u and any(x in u for x in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
            return True
        if "cover" in u and any(x in u for x in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
            return True
        return False
    except Exception:
        return False


def _jmpx_is_video_url(url):
    try:
        u = str(url or "").lower()
        return any(x in u for x in [".m3u8", ".mp4", ".flv", ".mpd", ".ts"])
    except Exception:
        return False


def _jmpx_guess_ctype(url, content=None, rsp=None):
    try:
        if rsp is not None:
            ctype = rsp.headers.get("Content-Type") or ""
            if ctype and "text/html" not in ctype.lower():
                return ctype

        if content:
            if content[:3] == b"\xff\xd8\xff":
                return "image/jpeg"
            if content[:8] == b"\x89PNG\r\n\x1a\n":
                return "image/png"
            if content[:4] == b"RIFF" and b"WEBP" in content[:20]:
                return "image/webp"
            if content[:6] in [b"GIF87a", b"GIF89a"]:
                return "image/gif"

        low = str(url or "").lower()
        if ".m3u8" in low:
            return "application/vnd.apple.mpegurl"
        if ".mpd" in low:
            return "application/dash+xml"
        if ".mp4" in low:
            return "video/mp4"
        if ".flv" in low:
            return "video/x-flv"
        if ".ts" in low:
            return "video/mp2t"
        if low.endswith(".png"):
            return "image/png"
        if low.endswith(".webp"):
            return "image/webp"
        if low.endswith(".gif"):
            return "image/gif"
        if low.endswith(".avif"):
            return "image/avif"
        return "image/jpeg"
    except Exception:
        return "application/octet-stream"


def _jmpx_get_param(params, key):
    try:
        if not isinstance(params, dict):
            return ""
        v = params.get(key, "")
        if isinstance(v, list):
            return v[0] if v else ""
        return v
    except Exception:
        return ""


def _jmpx_site_headers(self, accept_image=False):
    try:
        ua = ""
        try:
            ua = getattr(self, "headers", {}).get("User-Agent", "")
        except Exception:
            ua = ""

        if not ua:
            ua = (
                "Mozilla/5.0 (Linux; Android 11; SM-G991B) "
                "AppleWebKit/537.36 Chrome/98.0.4758.101 Mobile Safari/537.36"
            )

        host = getattr(self, "host", "https://javmenu.com").rstrip("/")

        if accept_image:
            accept = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        else:
            accept = "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"

        headers = {
            "User-Agent": ua,
            "Accept": accept,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": host + "/",
            "Connection": "keep-alive",
        }

        ck = ""
        try:
            ck = getattr(self, "site_cookie", "") or getattr(self, "headers", {}).get("Cookie", "")
        except Exception:
            ck = ""

        if ck:
            headers["Cookie"] = ck

        return headers
    except Exception:
        return {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://javmenu.com/",
        }


def _jmpx_get_proxy_url(self):
    try:
        if hasattr(self, "getProxyUrl"):
            proxy = self.getProxyUrl()
            if proxy:
                return proxy
    except Exception:
        pass
    return ""


def _jmpx_to_local_proxy(self, url, ptype="img"):
    try:
        url = _jmpx_unwrap_proxy_url(url)
        url = _jmpx_clean_url(self, url)
        if not url:
            return ""
        proxy = _jmpx_get_proxy_url(self)
        if proxy:
            sep = "&" if "?" in proxy else "?"
            return proxy + sep + "type=" + ptype + "&url=" + _jmpx_quote(url, safe="")
        return url
    except Exception:
        return str(url or "")


def _jmpx_to_img_proxy(self, url):
    try:
        url = _jmpx_unwrap_proxy_url(url)
        url = _jmpx_clean_url(self, url)
        if not url:
            return ""
        if not _jmpx_is_img(url):
            return url
        if not getattr(self, "use_img_proxy", True):
            return url
        return _jmpx_to_local_proxy(self, url, "img")
    except Exception:
        return str(url or "")


def _jmpx_to_play_proxy(self, url):
    try:
        url = _jmpx_unwrap_proxy_url(url)
        url = _jmpx_clean_url(self, url)
        if not url:
            return ""
        return _jmpx_to_local_proxy(self, url, "play")
    except Exception:
        return str(url or "")


def _jmpx_fix_vod_pics(self, ret):
    try:
        if not isinstance(ret, dict):
            return ret
        lst = ret.get("list", [])
        if not isinstance(lst, list):
            return ret
        for v in lst:
            try:
                if not isinstance(v, dict):
                    continue
                pic = v.get("vod_pic", "")
                if pic:
                    v["vod_pic"] = _jmpx_to_img_proxy(self, pic)
            except Exception:
                pass
        return ret
    except Exception:
        return ret


def _jmpx_init(self, extend=""):
    if getattr(Spider, "_jmpx_old_init", None):
        Spider._jmpx_old_init(self, extend)

    self.proxy_url = getattr(self, "proxy_url", "") or _jmpx_default_proxy()
    self.site_proxy = getattr(self, "site_proxy", "") or self.proxy_url
    self.javmenu_proxy = getattr(self, "javmenu_proxy", "") or self.site_proxy
    self.use_img_proxy = True
    self.use_online_proxy = True

    try:
        if extend:
            ext = _jmpx_json.loads(extend)
            if isinstance(ext, dict):
                p = str(
                    ext.get("site_proxy", "")
                    or ext.get("javmenu_proxy", "")
                    or ext.get("proxy_url", "")
                    or ""
                ).strip()
                if p:
                    self.proxy_url = p
                    self.site_proxy = p
                    self.javmenu_proxy = p

                if str(ext.get("image_proxy", "true")).lower() in ["0", "false", "no"]:
                    self.use_img_proxy = False
                else:
                    self.use_img_proxy = True

                if str(ext.get("online_proxy", "true")).lower() in ["0", "false", "no"]:
                    self.use_online_proxy = False
                else:
                    self.use_online_proxy = True
    except Exception as e:
        print("[JAVMENU FINAL PROXY init ext] error:", e)

    try:
        if hasattr(self, "session") and self.session:
            self.session.trust_env = False
            self.session.verify = False
            self.session.headers.update(_jmpx_site_headers(self, False))
            self.session.proxies.clear()
            self.session.proxies.update(_jmpx_proxies(self) or {})
    except Exception as e:
        print("[JAVMENU FINAL PROXY session setup] error:", e)

    print("[JAVMENU FINAL PROXY] site/image/online proxy=%s image_proxy=%s online_proxy=%s" % (
        _jmpx_get_site_proxy(self),
        bool(getattr(self, "use_img_proxy", True)),
        bool(getattr(self, "use_online_proxy", True)),
    ))
    print("[JAVMENU FINAL PROXY] 115/OpenList/magnet/push keep direct")


def _jmpx_getpq(self, path=""):
    try:
        url = path if str(path).startswith("http") else f"{self.host}{path}"
        url = _jmpx_clean_url(self, url)

        urls = [url]
        if "javmenu.com" in url:
            urls.append(url.replace("javmenu.com", "javmenu.org"))
        elif "javmenu.org" in url:
            urls.append(url.replace("javmenu.org", "javmenu.com"))

        sess = getattr(self, "session", None)

        if sess is None and _jmpx_Session:
            sess = _jmpx_Session()
            sess.verify = False
            sess.trust_env = False
            sess.proxies.update(_jmpx_proxies(self) or {})
            self.session = sess

        if sess is None:
            old = getattr(Spider, "_jmpx_old_getpq", None)
            if old:
                return old(self, path)
            return _jmpx_pq("") if _jmpx_pq else pq("")

        for u in urls:
            try:
                rsp = sess.get(
                    u,
                    headers=_jmpx_site_headers(self, False),
                    timeout=30,
                    allow_redirects=True,
                    verify=False,
                    proxies=_jmpx_proxies(self),
                )
                rsp.encoding = "utf-8"
                if rsp.status_code == 200:
                    return _jmpx_pq(rsp.text) if _jmpx_pq else pq(rsp.text)
            except Exception as e:
                print("[JAVMENU FINAL PROXY request error]", u, e)
    except Exception as e:
        print("[JAVMENU FINAL PROXY getpq] error:", e)

    return _jmpx_pq("") if _jmpx_pq else pq("")


def _jmpx_getListPicture(self, item):
    try:
        old = getattr(Spider, "_jmpx_old_getListPicture", None)
        raw = old(self, item) if old else ""
        raw = _jmpx_unwrap_proxy_url(raw)
        raw = _jmpx_clean_url(self, raw)
        if not raw:
            return ""
        return _jmpx_to_img_proxy(self, raw)
    except Exception as e:
        print("[JAVMENU FINAL PROXY getListPicture] error:", e)
        return ""


def _jmpx_getCover(self, data):
    try:
        old = getattr(Spider, "_jmpx_old_getCover", None)
        raw = old(self, data) if old else ""
        raw = _jmpx_unwrap_proxy_url(raw)
        raw = _jmpx_clean_url(self, raw)
        if not raw:
            return ""
        return _jmpx_to_img_proxy(self, raw)
    except Exception as e:
        print("[JAVMENU FINAL PROXY getCover] error:", e)
        return ""


def _jmpx_categoryContent(self, tid, pg, filter, extend):
    old = getattr(Spider, "_jmpx_old_categoryContent", None)
    if old:
        ret = old(self, tid, pg, filter, extend)
    else:
        ret = {"list": [], "page": str(pg), "pagecount": 0, "limit": 90, "total": 0}
    return _jmpx_fix_vod_pics(self, ret)


def _jmpx_searchContent(self, key, quick, pg="1"):
    old = getattr(Spider, "_jmpx_old_searchContent", None)
    if old:
        ret = old(self, key, quick, pg)
    else:
        ret = {"list": []}
    return _jmpx_fix_vod_pics(self, ret)


def _jmpx_detailContent(self, ids):
    old = getattr(Spider, "_jmpx_old_detailContent", None)
    if old:
        ret = old(self, ids)
    else:
        ret = {"list": []}
    ret = _jmpx_fix_vod_pics(self, ret)
    try:
        if ret and ret.get("list"):
            pic = ret["list"][0].get("vod_pic", "")
            if pic:
                self.last_vod_pic = pic
    except Exception:
        pass
    return ret


def _jmpx_rewrite_m3u8(self, text, base_url):
    try:
        out = []
        for line in str(text or "").splitlines():
            raw = line.strip()
            if not raw:
                out.append(line)
                continue

            if raw.startswith("#"):
                if "URI=" in raw:
                    def repl(m):
                        inner = m.group(1)
                        absu = _jmpx_clean_url(self, inner, base_url)
                        prox = _jmpx_to_play_proxy(self, absu)
                        return 'URI="%s"' % prox

                    raw = _jmpx_re.sub(r'URI="([^"]+)"', repl, raw)
                out.append(raw)
                continue

            abs_url = _jmpx_clean_url(self, raw, base_url)
            out.append(_jmpx_to_play_proxy(self, abs_url))

        return "\n".join(out)
    except Exception as e:
        print("[JAVMENU FINAL PROXY rewrite m3u8] error:", e)
        return text


def _jmpx_localProxy(self, params):
    try:
        ptype = str(_jmpx_get_param(params, "type") or "").strip()
        action = str(_jmpx_get_param(params, "action") or "").strip()
        do_val = str(_jmpx_get_param(params, "do") or "").strip()

        is_img = ptype == "img" or action == "img" or do_val == "img"
        is_play = ptype == "play" or action == "play" or do_val == "play"

        if not is_img and not is_play:
            old = getattr(Spider, "_jmpx_old_localProxy", None)
            if old:
                return old(self, params)
            return [404, "text/plain", "Not Found"]

        raw_url = str(_jmpx_get_param(params, "url") or "").strip()

        if not raw_url:
            return [404, "text/plain", "No Url"]

        raw_url = _jmpx_unquote(raw_url)
        fixed = _jmpx_clean_url(self, _jmpx_unwrap_proxy_url(raw_url))

        if not fixed:
            return [404, "text/plain", "Bad Url"]

        sess = getattr(self, "jmpx_proxy_session", None)

        if sess is None and _jmpx_Session:
            sess = _jmpx_Session()
            sess.verify = False
            sess.trust_env = False
            self.jmpx_proxy_session = sess

        if sess is None:
            return [404, "text/plain", "No Session"]

        headers = _jmpx_site_headers(self, accept_image=is_img)

        rsp = sess.get(
            fixed,
            headers=headers,
            timeout=30,
            allow_redirects=True,
            verify=False,
            proxies=_jmpx_proxies(self),
        )

        content = rsp.content or b""
        ctype = rsp.headers.get("Content-Type") or ""

        if rsp.status_code != 200 or not content:
            return [404, "text/plain", "Proxy Request Failed"]

        low = fixed.lower()

        if is_play and (".m3u8" in low or "mpegurl" in ctype.lower()):
            try:
                text = rsp.text or content.decode("utf-8", errors="ignore")
                text = _jmpx_rewrite_m3u8(self, text, fixed)
                return [200, "application/vnd.apple.mpegurl", text]
            except Exception as e:
                print("[JAVMENU FINAL PROXY m3u8] error:", e)
                return [200, "application/vnd.apple.mpegurl", content]

        if is_img:
            return [200, _jmpx_guess_ctype(fixed, content, rsp), content]

        return [200, _jmpx_guess_ctype(fixed, content, rsp), content]

    except Exception as e:
        print("[JAVMENU FINAL PROXY localProxy] error:", e)
        return [404, "text/plain", "Proxy Error"]


def _jmpx_playerContent(self, flag, id, vipFlags):
    try:
        flag = str(flag or "")
        pid = str(id or "")

        if flag == "在线播放":
            real_url = ""
            try:
                real_url = self.d64(pid) or pid
            except Exception:
                real_url = pid

            real_url = _jmpx_clean_url(self, real_url)

            if not real_url or self.isAdUrl(real_url):
                return {
                    "parse": 0,
                    "playUrl": "",
                    "url": "",
                    "pic": getattr(self, "last_vod_pic", ""),
                    "poster": getattr(self, "last_vod_pic", ""),
                }

            low = real_url.lower()
            is_direct = any(x in low for x in [".m3u8", ".mp4", ".flv", ".mpd"])

            if getattr(self, "use_online_proxy", True) and is_direct:
                proxy_url = _jmpx_to_play_proxy(self, real_url)
                return {
                    "parse": 0,
                    "playUrl": "",
                    "url": proxy_url,
                    "header": _jmpx_site_headers(self, False),
                    "pic": getattr(self, "last_vod_pic", ""),
                    "poster": getattr(self, "last_vod_pic", ""),
                }

            return {
                "parse": 0 if is_direct else 1,
                "playUrl": "",
                "url": real_url,
                "header": _jmpx_site_headers(self, False),
                "pic": getattr(self, "last_vod_pic", ""),
                "poster": getattr(self, "last_vod_pic", ""),
            }

        old = getattr(Spider, "_jmpx_old_playerContent", None)
        if old:
            return old(self, flag, id, vipFlags)

        return {
            "parse": 1,
            "playUrl": "",
            "url": pid,
            "header": getattr(self, "headers", {}),
        }

    except Exception as e:
        print("[JAVMENU FINAL PROXY playerContent] error:", e)
        old = getattr(Spider, "_jmpx_old_playerContent", None)
        if old:
            return old(self, flag, id, vipFlags)
        return {
            "parse": 1,
            "playUrl": "",
            "url": str(id or ""),
        }


# 绑定最终方法
Spider.init = _jmpx_init
Spider.getpq = _jmpx_getpq
Spider.getListPicture = _jmpx_getListPicture
Spider.getCover = _jmpx_getCover
Spider.categoryContent = _jmpx_categoryContent
Spider.searchContent = _jmpx_searchContent
Spider.detailContent = _jmpx_detailContent
Spider.playerContent = _jmpx_playerContent
Spider.localProxy = _jmpx_localProxy

print("[FINAL JAVMENU SITE/IMAGE/ONLINE PROXY] loaded")
# ===== FINAL_JAVMENU_SITE_IMAGE_ONLINE_PROXY_END =====