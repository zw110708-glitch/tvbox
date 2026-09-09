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
from urllib.parse import quote, urljoin, unquote
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
        self.pan_115_cookie = ""
        self.confirm_115 = True
        self.confirm_cache = set()
        # 169BBS 对齐：115离线/API缓存配置
        self.cache_115_file = "/storage/emulated/0/Download/115api_cache/115_cache.json"
        self.offline_115_timeout = 180
        self.offline_115_poll_interval = 5
        self.min_115_video_size = 100 * 1024 * 1024
        self.pan_115_save_cid = ""

        self.last_vod_pic = ""
        self.ack_mp4 = (
            "https://vd2.bdstatic.com/mda-nj5kxa8kr7wgq6ie/"
            "sc/cae_h264_nowatermark/1653272065989267185/"
            "mda-nj5kxa8kr7wgq6ie.mp4"
        )

        # OpenList / 115播放 配置
        self.openlist_url = ""
        self.openlist_token = ""
        self.openlist_parent = "/云下载"
        self.openlist_force_dav = False
        self.openlist_test_stream = False
        self.test_m3u8 = "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"
        self.openlist_search_cache_ttl = 300
        self._openlist_search_cache = {}
        self._openlist_recent_files = []
        self.openlist_refresh_latest_n = 3
        if extend:
            try:
                ext_data = json.loads(extend)
                if "host" in ext_data:
                    self.host = ext_data["host"].rstrip('/')
                if "pan_115_cookie" in ext_data:
                    self.pan_115_cookie = ext_data.get("pan_115_cookie", "")
                if ext_data.get("cache_115_file"):
                    self.cache_115_file = str(ext_data.get("cache_115_file")).strip()
                if ext_data.get("pan_115_save_cid"):
                    self.pan_115_save_cid = str(ext_data.get("pan_115_save_cid")).strip()
                try:
                    self.offline_115_timeout = max(30, int(ext_data.get("offline_115_timeout", 180)))
                except Exception:
                    pass
                try:
                    self.offline_115_poll_interval = max(3, int(ext_data.get("offline_115_poll_interval", 5)))
                except Exception:
                    pass
                if str(ext_data.get("confirm_115", "1")) in ["0", "false", "False"]:
                    self.confirm_115 = False
                if "ack_mp4" in ext_data:
                    self.ack_mp4 = ext_data.get("ack_mp4") or self.ack_mp4
                if "openlist_url" in ext_data:
                    self.openlist_url = self.normalizeOpenlistBaseUrl(str(ext_data.get("openlist_url", "")).strip())
                if "openlist_token" in ext_data:
                    self.openlist_token = str(ext_data.get("openlist_token", "")).strip()
                if ext_data.get("openlist_parent"):
                    p = str(ext_data.get("openlist_parent")).strip()
                    self.openlist_parent = "/" + p.lstrip("/") if p else "/"
                if str(ext_data.get("openlist_force_dav", "0")) in ["1", "true", "True", "yes", "Yes"]:
                    self.openlist_force_dav = True
                if str(ext_data.get("openlist_test_stream", "0")) in ["1", "true", "True", "yes", "Yes"]:
                    self.openlist_test_stream = True
                if ext_data.get("test_m3u8"):
                    self.test_m3u8 = str(ext_data.get("test_m3u8")).strip()
                try:
                    self.openlist_search_cache_ttl = max(0, int(ext_data.get("openlist_search_cache_ttl", 300)))
                except Exception:
                    pass
                try:
                    self.openlist_refresh_latest_n = max(1, int(ext_data.get("openlist_refresh_latest_n", 3)))
                except Exception:
                    pass
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

        # 169BBS 对齐：OpenList/AList 使用独立 Session，避免携带 javmenu Cookie / Referer
        self.openlist_session = Session()
        self.openlist_session.verify = False
        self.openlist_session.headers.clear()


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
            "河": "/zh/actor/EvkJ?order=publish",
            "泽": "/zh/actor/NPD3?order=publish",
            "森": "/zh/actor/bkxd?order=publish",
            "白": "/zh/actor/bAv5g?order=publish",
            "枫": "/zh/actor/kzx6?order=publish",
            "星": "/zh/actor/vd2n?order=publish",
            "佳": "/zh/actor/8Nqa?order=publish",
            "叶": "/zh/actor/1B0AA?order=publish",
            "f": "/zh/actor/x9mE?order=publish",
            "明": "/zh/actor/658kM?order=publish",
            "彩": "/zh/actor/RdEb4?order=publish",
            "西": "/zh/actor/B8VB1?order=publish",
            "里": "/zh/actor/M4Q7?order=publish",
            "橘": "/zh/actor/yzZW?order=publish",
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

            # 解析列表页打包进来的封面图
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
            magnet_115_url = self.convertMagnetsFor115(magnet_url)

            # 优先使用列表页封面图
            cover = list_pic or self.getCover(data)
            self.last_vod_pic = cover or ""

            play_from = []
            play_url = []

            if online_url:
                play_from.append('在线播放')
                play_url.append(online_url)

            if magnet_115_url:
                play_from.append('115云下载')
                play_url.append(magnet_115_url)

            play_from.append('0')
            play_url.append('不会自动下载，请手动切换到115云下载$__ACK__')

            # 115播放（OpenList）
            if self.openlist_url and self.openlist_token:
                play_from.append('115播放')
                play_url.append(self.buildOpenlistPlayItems(self.getVodName(data)))
            if magnet_url:
                play_from.append('磁力推送')
                play_url.append(magnet_url)

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

            # 115播放 / OpenList
            if flag == "115播放" or id.startswith("__OPENLIST_"):
                if self.openlist_test_stream:
                    return {
                        'parse': 0,
                        'playUrl': '',
                        "url": self.test_m3u8,
                        "header": {"User-Agent": self.headers.get("User-Agent", "")},
                        "pic": self.last_vod_pic,
                        "poster": self.last_vod_pic
                    }
                ret = self.openlistPlayerContent(id)
                if isinstance(ret, dict):
                    ret["pic"] = ret.get("pic") or self.last_vod_pic
                    ret["poster"] = ret.get("poster") or self.last_vod_pic
                return ret
            if flag == "115云下载":
                magnet = ""
                try:
                    decoded = b64decode(id.encode('utf-8')).decode('utf-8')
                    decoded = self.normalizeMagnet(decoded)
                    if decoded.startswith('magnet:'):
                        magnet = decoded
                except Exception as e:
                    print(f"115 decode error: {e}")

                if not self.pan_115_cookie:
                    print("115: 未配置 pan_115_cookie")
                    return self.returnAckVideo(self.last_vod_pic)

                if not magnet:
                    print("115: 磁力为空或格式错误")
                    return self.returnAckVideo(self.last_vod_pic)

                if self.confirm_115:
                    if magnet not in self.confirm_cache:
                        self.confirm_cache.add(magnet)
                        print("115二次确认：第一次点击仅确认，请再次点击同一条提交")
                        return self.returnAckVideo(self.last_vod_pic)

                try:
                    threading.Thread(
                        target=self.add_to_115_v2,
                        args=(magnet,),
                        daemon=True
                    ).start()
                except Exception as e:
                    print(f"115 thread error: {e}")

                return self.returnAckVideo(self.last_vod_pic)

            # 保留原磁力推送逻辑
            if id.startswith('ma2gnet:'):
                real_mag = id.replace('ma2gnet:', 'magnet:', 1)
                return {
                    'parse': 0,
                    'url': 'push://' + real_mag + '#0agent',
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

    # ==================== 115相关 ====================
    def convertMagnetsFor115(self, magnets_str):
        if not magnets_str:
            return ''
        result = []
        try:
            for item in magnets_str.split('#'):
                if '$' not in item:
                    continue
                name, fake_link = item.split('$', 1)
                real_link = fake_link.replace('ma2gnet:', 'magnet:', 1)
                real_link = self.normalizeMagnet(real_link)
                if not real_link.startswith('magnet:'):
                    continue
                encoded = b64encode(real_link.encode('utf-8')).decode('utf-8')
                result.append(f"{self.cleanPlayName(name)}${encoded}")
        except Exception as e:
            print(f"convertMagnetsFor115 error: {e}")
        return '#'.join(result)

    def normalizeMagnet(self, href):
        try:
            if not href:
                return ""
            href = str(href).strip()
            href = href.replace("&amp;", "&")
            if href.startswith("push://"):
                href = href.replace("push://", "", 1).replace("#0agent", "")
            if href.startswith("ma2gnet:"):
                href = href.replace("ma2gnet:", "magnet:", 1)
            if "%3A" in href or "%3F" in href or "%26" in href:
                try:
                    href = unquote(href)
                except:
                    pass
            href = re.sub(r"\s+", "", href)
            if not href.startswith("magnet:"):
                return ""
            if "urn:btih:" not in href:
                return ""
            return href
        except:
            return ""


    # ==================== 115播放 / OpenList ====================
    def buildOpenlistPlayItems(self, title):
        """
        115播放线路：
        刷新缓存 -> 番号 -> 搜2~搜13
        """
        try:
            title = self.cleanText(title or "")
            title_b64 = base64.b64encode(title.encode("utf-8")).decode("utf-8")
            items = []

            items.append(f"刷新缓存$__OPENLIST_REFRESH__|{title_b64}")

            code = self.extractVideoCode(title)
            if code:
                code_name = code.get("dash", code.get("raw", "番号"))
                code_b64 = base64.b64encode(code_name.encode("utf-8")).decode("utf-8")
                items.append(f"{code_name}$__OPENLIST_CODE__|{code_b64}")

            for n in range(2, 14):
                items.append(f"搜{n}$__OPENLIST_SEARCH__|{n}|{title_b64}")

            return "#".join(items)

        except Exception as e:
            print(f"[OpenList] build play items error: {e}")
            return "刷新缓存$__OPENLIST_REFRESH__"


    def normalizeOpenlistBaseUrl(self, url):
        url = str(url or "").strip()

        if not url:
            return ""

        if url.startswith("http://") or url.startswith("https://"):
            return url.rstrip("/")

        if url.startswith("http:") and not url.startswith("http://"):
            url = url.replace("http:", "", 1).lstrip("/")
            return ("http://" + url).rstrip("/")

        if url.startswith("https:") and not url.startswith("https://"):
            url = url.replace("https:", "", 1).lstrip("/")
            return ("https://" + url).rstrip("/")

        return ("http://" + url.lstrip("/")).rstrip("/")


    def openlistHeaders(self):
        return {
            "Authorization": (self.openlist_token or "").strip(),
            "Content-Type": "application/json",
            "User-Agent": self.headers.get("User-Agent", ""),
        }


    def openlistApiPost(self, api_path, payload, timeout=15):
        if not self.openlist_url:
            return {}

        url = f"{self.openlist_url}{api_path}"

        try:
            r = self.session.post(
                url,
                headers=self.openlistHeaders(),
                json=payload,
                timeout=timeout,
                verify=False
            )

            try:
                return r.json()
            except Exception:
                return {}

        except Exception as e:
            print(f"[OpenList API] post error {api_path}: {e}")
            return {}


    def openlistNormalizePath(self, path):
        path = str(path or "/").strip()
        path = "/" + path.lstrip("/")

        if path != "/":
            path = path.rstrip("/")

        return path


    def openlistJoinPath(self, parent, name):
        parent = self.openlistNormalizePath(parent)
        name = str(name or "").strip("/")

        if parent == "/":
            return "/" + name

        return parent + "/" + name


    def isPathUnderOpenlistParent(self, path):
        try:
            parent = self.openlistNormalizePath(self.openlist_parent)
            path = self.openlistNormalizePath(path)

            if parent == "/":
                return True

            return path == parent or path.startswith(parent.rstrip("/") + "/")

        except Exception:
            return False


    def parseOpenlistTime(self, item):
        t = item.get("modified") or item.get("created") or item.get("updated_at") or item.get("time") or ""

        if not t:
            return 0

        try:
            t = str(t).replace("Z", "+00:00")
            return int(datetime.fromisoformat(t).timestamp())
        except Exception:
            return 0


    def openlistIsDir(self, item):
        if not item:
            return False

        if "is_dir" in item:
            return bool(item.get("is_dir"))

        if "isDir" in item:
            return bool(item.get("isDir"))

        if item.get("type") == 1:
            return True

        mime = str(item.get("mime_type") or item.get("mime") or "").lower()

        return ("directory" in mime) or ("folder" in mime)


    def isOpenlistVideoFile(self, name):
        name = str(name or "").lower()

        return name.endswith((
            ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".ts", ".m2ts",
            ".webm", ".m3u8", ".rmvb", ".mpg", ".mpeg", ".3gp", ".m4v",
            ".vob", ".f4v"
        ))


    def normalizeSearchText(self, text):
        text = str(text or "").lower()
        text = unquote(text)
        text = re.sub(r"[\s\-_.,，。:：;；!！?？'\"“”‘’\[\]【】()（）{}《》<>「」『』/\\|&@]+", "", text)

        return text


    def extractVideoCode(self, text):
        """
        番号提取规则。
        支持普通番号、FC2、HEYZO、1PONDO、CARIB。
        """
        s = self.cleanText(text or "")

        special_patterns = [
            r"\b(FC2)[-_ ]?(?:PPV)?[-_ ]?(\d{5,8})\b",
            r"\b(HEYZO)[-_ ]?(\d{3,6})\b",
            r"\b(1PONDO)[-_ ]?(\d{6}[_-]\d{3})\b",
            r"\b(CARIB)[-_ ]?(\d{6}[-_]\d{3})\b",
        ]

        for p in special_patterns:
            m = re.search(p, s, re.I)

            if not m:
                continue

            prefix = (m.group(1) or "").upper()
            num = (m.group(2) or "")

            return {
                "raw": f"{prefix}-{num}",
                "prefix": prefix,
                "num": num,
                "dash": f"{prefix}-{num}",
                "nodash": f"{prefix}{re.sub(r'[^0-9A-Za-z]', '', num)}",
            }

        patterns = [
            r"\b([A-Za-z]{2,10}|\d{2,5}[A-Za-z]{2,10})[-_](\d{2,7})(?:[-_ ]?(?:cd\d+|part\d+|[a-z]{1,3}|\d{1,2}))?\b",
            r"\b([A-Za-z]{2,10}|\d{2,5}[A-Za-z]{2,10})\s+(\d{2,7})(?:[-_ ]?(?:cd\d+|part\d+|[a-z]{1,3}|\d{1,2}))?\b",
            r"\b([A-Za-z]{2,10}|\d{2,5}[A-Za-z]{2,10})(\d{2,7})(?:[-_ ]?(?:cd\d+|part\d+|[a-z]{1,3}|\d{1,2}))?\b",
        ]

        bad_prefix = {"CM", "MM", "GB", "MB", "TB", "FPS", "K"}

        for p in patterns:
            m = re.search(p, s, re.I)

            if not m:
                continue

            prefix = (m.group(1) or "").upper()
            num = (m.group(2) or "")

            if prefix in bad_prefix:
                continue

            if not num.isdigit():
                continue

            return {
                "raw": f"{prefix}-{num}",
                "prefix": prefix,
                "num": num,
                "dash": f"{prefix}-{num}",
                "nodash": f"{prefix}{num}",
            }

        return None


    def candidateMatchExactCode(self, candidate, code_info):
        if not candidate or not code_info:
            return False

        pfx = str(code_info.get("prefix", "")).lower()
        num = str(code_info.get("num", ""))

        if not pfx or not num:
            return False

        raw = (str(candidate.get("name", "")) + " " + str(candidate.get("path", ""))).lower()
        norm = re.sub(r"[\s\-_\.@]+", "", raw)

        target = pfx + re.sub(r"[^0-9A-Za-z]", "", num).lower()

        return target in norm


    def candidateMatchCodeSuffixAllowed(self, candidate, code_info, allow_suffix=None):
        if not candidate or not code_info:
            return False

        if allow_suffix is None:
            allow_suffix = {"", "c", "ch", "uc"}

        pfx = str(code_info.get("prefix", "")).lower()
        num = str(code_info.get("num", ""))

        if not pfx or not num:
            return False

        num_clean = re.sub(r"[^0-9A-Za-z]", "", num).lower()

        raw = (str(candidate.get("name", "")) + " " + str(candidate.get("path", ""))).lower()
        norm = re.sub(r"[\s\-_\.@]+", "", raw)

        hits = re.findall(rf"{re.escape(pfx)}{re.escape(num_clean)}([a-z]{{0,8}})", norm, re.I)

        if not hits:
            return False

        for suf in hits:
            suf = (suf or "").lower()

            if suf == "":
                return True

            if suf in allow_suffix:
                return True

            if suf.startswith("c") or suf.startswith("ch") or suf.startswith("uc"):
                return True

        return False


    def buildOpenlistSearchKeywords(self, title, n=5):
        title = self.cleanText(title or "")

        try:
            n = int(n)
        except Exception:
            n = 5

        n = max(1, min(30, n))

        keywords = []

        code = self.extractVideoCode(title)

        if code:
            keywords += [
                code.get("dash", ""),
                code.get("nodash", ""),
                code.get("prefix", ""),
            ]
        else:
            m = re.search(r"\b([A-Za-z0-9]{2,12})[-_\s]?(\d{2,7})\b", title)

            if m:
                code1 = m.group(1).upper()
                code2 = m.group(2)
                keywords += [
                    f"{code1}-{code2}",
                    f"{code1}{code2}",
                    code1,
                ]

        raw = re.sub(r"\s+", "", title)

        if raw:
            keywords.append(raw[:n])

        compact = re.sub(r"[\[\]【】()（）{}《》<>「」『』]", "", title)
        compact = re.sub(r"[\/\\\|\-_.,，。:：;；!！?？'\"“”‘’&@]+", "", compact)
        compact = re.sub(r"\s+", "", compact)

        if compact:
            keywords.append(compact[:n])

        out, seen = [], set()

        for k in keywords:
            k = self.cleanText(k)

            if k and k not in seen:
                seen.add(k)
                out.append(k)

        return out


    def openlistListDirOnce(self, path, per_page=200, refresh=False):
        """
        只读取指定目录一层。
        不递归，不全盘扫描。
        """
        result = []

        if not self.openlist_url:
            return result

        path = self.openlistNormalizePath(path)

        if not self.isPathUnderOpenlistParent(path):
            return result

        try:
            per_page = max(20, min(500, int(per_page)))
        except Exception:
            per_page = 200

        data = self.openlistApiPost(
            "/api/fs/list",
            {
                "path": path,
                "password": "",
                "page": 1,
                "per_page": per_page,
                "refresh": bool(refresh)
            },
            25
        )

        if data.get("code") != 200:
            return result

        d = data.get("data", {}) or {}
        content = d.get("content") or []

        for item in content:
            try:
                name = str(item.get("name") or "").strip()

                if not name:
                    continue

                full_path = self.openlistJoinPath(path, name)

                if not self.isPathUnderOpenlistParent(full_path):
                    continue

                try:
                    size = int(item.get("size") or 0)
                except Exception:
                    size = 0

                result.append({
                    "name": name,
                    "path": full_path,
                    "size": size,
                    "time": self.parseOpenlistTime(item),
                    "sign": item.get("sign", ""),
                    "is_dir": self.openlistIsDir(item),
                    "parent": path,
                })

            except Exception as e:
                print(f"[OpenList list once item] error: {e}")

        return result


    def openlistApiSearchFiles(self, keyword, page=1, per_page=100):
        """
        OpenList /api/fs/search 搜索。
        如果命中目录，则只展开命中目录一层找视频。
        """
        results = []

        if not self.openlist_url:
            return results

        keyword = self.cleanText(keyword or "")

        if not keyword:
            return results

        try:
            page = max(1, int(page))
        except Exception:
            page = 1

        try:
            per_page = max(20, min(200, int(per_page)))
        except Exception:
            per_page = 100

        payload = {
            "parent": self.openlistNormalizePath(self.openlist_parent),
            "keywords": keyword,
            "scope": 0,
            "page": page,
            "per_page": per_page,
            "password": ""
        }

        data = self.openlistApiPost("/api/fs/search", payload, 20)

        if data.get("code") != 200:
            return results

        d = data.get("data", {}) or {}
        content = d.get("content") or []

        for item in content:
            try:
                name = str(item.get("name") or "").strip()

                if not name:
                    continue

                parent = str(item.get("parent") or "").strip()
                path = str(item.get("path") or "").strip()

                if path:
                    full_path = self.openlistNormalizePath(path)
                else:
                    full_path = self.openlistJoinPath(parent, name)

                if not self.isPathUnderOpenlistParent(full_path):
                    continue

                if self.openlistIsDir(item):
                    children = self.openlistListDirOnce(full_path, per_page=300, refresh=False)

                    for child in children:
                        if child.get("is_dir"):
                            continue

                        child_name = str(child.get("name") or "")

                        if not self.isOpenlistVideoFile(child_name):
                            continue

                        results.append(child)

                    continue

                if not self.isOpenlistVideoFile(name):
                    continue

                try:
                    size = int(item.get("size") or 0)
                except Exception:
                    size = 0

                results.append({
                    "name": name,
                    "path": full_path,
                    "size": size,
                    "time": self.parseOpenlistTime(item),
                    "sign": item.get("sign", ""),
                    "parent": parent,
                    "is_dir": False,
                })

            except Exception as e:
                print(f"[OpenList API search item] error: {e}")

        return results


    def searchOpenlistByApi(self, keywords, max_pages=2, per_page=100):
        result = []
        seen = set()

        if not keywords:
            return result

        if isinstance(keywords, str):
            keywords = [keywords]

        keywords = [self.cleanText(x) for x in keywords if self.cleanText(x)]

        if not keywords:
            return result

        try:
            max_pages = max(1, min(5, int(max_pages)))
        except Exception:
            max_pages = 2

        for kw in keywords:
            for page in range(1, max_pages + 1):
                files = self.openlistApiSearchFiles(kw, page=page, per_page=per_page)

                if not files:
                    break

                for f in files:
                    p = self.openlistNormalizePath(f.get("path", ""))

                    if not p:
                        continue

                    if p in seen:
                        continue

                    seen.add(p)
                    result.append(f)

        return result


    def filterOpenlistApiCandidates(self, candidates, keywords):
        if not candidates:
            return []

        if isinstance(keywords, str):
            keywords = [keywords]

        keywords = [self.cleanText(x) for x in keywords if self.cleanText(x)]
        norm_keys = [self.normalizeSearchText(x) for x in keywords if x]
        norm_keys = [x for x in norm_keys if x]

        code_info = self.extractVideoCode(" ".join(keywords))

        filtered = []

        for c in candidates:
            name = str(c.get("name") or "")
            path = str(c.get("path") or "")

            if not name or not path:
                continue

            if not self.isOpenlistVideoFile(name):
                continue

            if code_info:
                if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"}):
                    filtered.append(c)
                continue

            text_n = self.normalizeSearchText(name + " " + path)

            if norm_keys and any(k in text_n for k in norm_keys):
                filtered.append(c)

        return filtered


    def refreshOpenlistLatest3ToMemory(self, title=""):
        """
        点击刷新缓存：
        只刷新 openlist_parent 最新3个文件/目录。
        如果是目录，只展开一层。
        """
        try:
            n = max(1, int(getattr(self, "openlist_refresh_latest_n", 3) or 3))
        except Exception:
            n = 3

        parent = self.openlistNormalizePath(self.openlist_parent)

        print(f"[OpenList REFRESH] refresh parent={parent}, latest_n={n}, title={title}")

        try:
            self._openlist_search_cache.clear()
        except Exception:
            pass

        items = self.openlistListDirOnce(parent, per_page=100, refresh=True)

        if not items:
            print("[OpenList REFRESH] parent list empty")
            self._openlist_recent_files = []
            return 0

        items.sort(
            key=lambda x: (
                int(x.get("time") or 0),
                int(x.get("size") or 0)
            ),
            reverse=True
        )

        latest_items = items[:n]

        videos = []
        seen = set()

        for it in latest_items:
            try:
                name = str(it.get("name") or "")
                path = self.openlistNormalizePath(it.get("path") or "")

                if not name or not path:
                    continue

                if not it.get("is_dir") and self.isOpenlistVideoFile(name):
                    if path not in seen:
                        seen.add(path)
                        videos.append(it)
                    continue

                if it.get("is_dir"):
                    children = self.openlistListDirOnce(path, per_page=300, refresh=True)

                    for child in children:
                        child_name = str(child.get("name") or "")
                        child_path = self.openlistNormalizePath(child.get("path") or "")

                        if not child_name or not child_path:
                            continue

                        if child.get("is_dir"):
                            continue

                        if not self.isOpenlistVideoFile(child_name):
                            continue

                        if child_path in seen:
                            continue

                        seen.add(child_path)
                        videos.append(child)

            except Exception as e:
                print(f"[OpenList REFRESH] latest item error: {e}")

        self._openlist_recent_files = videos

        print(f"[OpenList REFRESH] recent video count={len(videos)}")

        for v in videos[:10]:
            print(f"[OpenList REFRESH] video={v.get('name')} path={v.get('path')}")

        return len(videos)


    def _cache_get(self, key):
        item = self._openlist_search_cache.get(key)

        if not item:
            return None

        ts, val = item

        if self.openlist_search_cache_ttl > 0 and (time.time() - ts > self.openlist_search_cache_ttl):
            self._openlist_search_cache.pop(key, None)
            return None

        return val


    def _cache_set(self, key, val):
        if self.openlist_search_cache_ttl == 0:
            return

        self._openlist_search_cache[key] = (time.time(), val)


    def scoreOpenlistCandidate(self, c, keywords):
        name = self.normalizeSearchText(c.get("name", ""))
        path = self.normalizeSearchText(c.get("path", ""))

        score = 0

        for k in keywords:
            nk = self.normalizeSearchText(k)

            if not nk:
                continue

            if nk in name:
                score += 100
            elif nk in path:
                score += 30

        code_info = self.extractVideoCode(" ".join(keywords))

        if code_info and self.candidateMatchExactCode(c, code_info):
            score += 10000

        try:
            size = int(c.get("size", 0) or 0)

            if size < 50 * 1024 * 1024:
                score -= 100
            elif size < 200 * 1024 * 1024:
                score -= 20
            else:
                score += min(size // (500 * 1024 * 1024), 20)

        except Exception:
            pass

        try:
            score += min(int(c.get("time", 0)) // 3600, 10)
        except Exception:
            pass

        return score


    def searchOpenlistBestVideoByCode(self, code_text):
        try:
            code_info = self.extractVideoCode(code_text or "")

            if not code_info:
                return None

            keywords = [
                code_info.get("dash", ""),
                code_info.get("nodash", ""),
            ]

            keywords = [x for x in keywords if x]

            if not keywords:
                return None

            cache_key = "api_code|" + "|".join([
                self.openlistNormalizePath(self.openlist_parent)
            ] + [self.normalizeSearchText(x) for x in keywords])

            cached = self._cache_get(cache_key)

            if cached:
                return cached

            norm_keys = [self.normalizeSearchText(x) for x in keywords if x]

            recent = getattr(self, "_openlist_recent_files", []) or []

            if recent:
                strict_pool = [
                    c for c in recent
                    if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"})
                ]

                if strict_pool:
                    strict_pool.sort(
                        key=lambda x: (
                            self.scoreOpenlistCandidate(x, norm_keys),
                            int(x.get("size") or 0)
                        ),
                        reverse=True
                    )

                    best = strict_pool[0]
                    self._cache_set(cache_key, best)

                    print(f"[OpenList RECENT CODE] hit={best.get('name')} path={best.get('path')}")

                    return best

            candidates = self.searchOpenlistByApi(keywords, max_pages=2, per_page=100)

            if not candidates:
                print(f"[OpenList API CODE] no candidates, keywords={keywords}")
                return None

            strict_pool = [
                c for c in candidates
                if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"})
            ]

            if not strict_pool:
                print(f"[OpenList API CODE] no strict match, keywords={keywords}")
                return None

            strict_pool.sort(
                key=lambda x: (
                    self.scoreOpenlistCandidate(x, norm_keys),
                    int(x.get("size") or 0)
                ),
                reverse=True
            )

            best = strict_pool[0]
            self._cache_set(cache_key, best)

            print(f"[OpenList API CODE] hit={best.get('name')} path={best.get('path')}")

            return best

        except Exception as e:
            print(f"[OpenList API CODE] error: {e}")
            return None


    def searchOpenlistBestVideo(self, keywords):
        try:
            if not keywords:
                return None

            if isinstance(keywords, str):
                keywords = [keywords]

            keywords = [self.cleanText(x) for x in keywords if self.cleanText(x)]

            if not keywords:
                return None

            cache_key = "api_search|" + "|".join([
                self.openlistNormalizePath(self.openlist_parent)
            ] + [self.normalizeSearchText(x) for x in keywords])

            cached = self._cache_get(cache_key)

            if cached:
                return cached

            norm_keys = [self.normalizeSearchText(x) for x in keywords if x]
            code_info = self.extractVideoCode(" ".join(keywords))

            recent = getattr(self, "_openlist_recent_files", []) or []

            if recent:
                recent_candidates = self.filterOpenlistApiCandidates(recent, keywords)

                if recent_candidates:
                    if code_info:
                        strict_pool = [
                            c for c in recent_candidates
                            if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"})
                        ]

                        if strict_pool:
                            strict_pool.sort(
                                key=lambda x: (
                                    self.scoreOpenlistCandidate(x, norm_keys),
                                    int(x.get("size") or 0)
                                ),
                                reverse=True
                            )

                            best = strict_pool[0]
                            self._cache_set(cache_key, best)

                            print(f"[OpenList RECENT CODE] hit={best.get('name')} path={best.get('path')}")

                            return best

                    recent_candidates.sort(
                        key=lambda x: (
                            self.scoreOpenlistCandidate(x, norm_keys),
                            int(x.get("size") or 0)
                        ),
                        reverse=True
                    )

                    best = recent_candidates[0]
                    self._cache_set(cache_key, best)

                    print(f"[OpenList RECENT] hit={best.get('name')} path={best.get('path')}")

                    return best

            candidates = self.searchOpenlistByApi(keywords, max_pages=2, per_page=100)

            if not candidates:
                print(f"[OpenList API SEARCH] no candidates, keywords={keywords}")
                return None

            candidates = self.filterOpenlistApiCandidates(candidates, keywords)

            if not candidates:
                print(f"[OpenList API SEARCH] no filtered candidates, keywords={keywords}")
                return None

            if code_info:
                strict_pool = [
                    c for c in candidates
                    if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"})
                ]

                if strict_pool:
                    strict_pool.sort(
                        key=lambda x: (
                            self.scoreOpenlistCandidate(x, norm_keys),
                            int(x.get("size") or 0)
                        ),
                        reverse=True
                    )

                    best = strict_pool[0]
                    self._cache_set(cache_key, best)

                    print(f"[OpenList API SEARCH CODE] hit={best.get('name')} path={best.get('path')}")

                    return best

                return None

            candidates.sort(
                key=lambda x: (
                    self.scoreOpenlistCandidate(x, norm_keys),
                    int(x.get("size") or 0)
                ),
                reverse=True
            )

            best = candidates[0]
            self._cache_set(cache_key, best)

            print(f"[OpenList API SEARCH] hit={best.get('name')} path={best.get('path')}")

            return best

        except Exception as e:
            print(f"[OpenList API SEARCH] search best error: {e}")
            return None


    def normalizeOpenlistUrl(self, url):
        if not url:
            return ""

        url = str(url).strip()

        if url.startswith("//"):
            return "https:" + url

        if url.startswith("http://") or url.startswith("https://"):
            return url

        if url.startswith("/"):
            return self.openlist_url.rstrip("/") + url

        return self.openlist_url.rstrip("/") + "/" + url.lstrip("/")


    def buildOpenlistDownloadUrl(self, full_path, sign=""):
        p = "/" + str(full_path or "").lstrip("/")
        url = f"{self.openlist_url.rstrip('/')}/d{quote(p, safe='/')}"

        if sign:
            url += ("&" if "?" in url else "?") + "sign=" + quote(str(sign))

        return url


    def buildOpenlistDavUrl(self, full_path):
        p = "/" + str(full_path or "").lstrip("/")
        return f"{self.openlist_url.rstrip('/')}/dav{quote(p, safe='/')}"


    def getPlayableUrlFromOpenlist(self, file_path):
        file_path = self.openlistNormalizePath(file_path)

        if not self.isPathUnderOpenlistParent(file_path):
            return "", {}

        data = self.openlistApiPost(
            "/api/fs/get",
            {
                "path": file_path,
                "password": ""
            },
            15
        )

        headers = {
            "User-Agent": self.headers.get("User-Agent", "")
        }

        if data.get("code") == 200:
            d = data.get("data", {}) or {}

            extra_header = d.get("header") or d.get("headers") or {}

            if isinstance(extra_header, dict):
                for k, v in extra_header.items():
                    if k and v:
                        headers[str(k)] = str(v)

            raw = d.get("raw_url") or d.get("rawUrl") or d.get("url") or ""

            if raw:
                return self.normalizeOpenlistUrl(raw), headers

            sign = d.get("sign") or ""

            return self.buildOpenlistDownloadUrl(file_path, sign), headers

        if self.openlist_force_dav:
            dav = self.buildOpenlistDavUrl(file_path)
            headers["Referer"] = self.openlist_url.rstrip("/") + "/"
            return dav, headers

        return self.buildOpenlistDownloadUrl(file_path), headers


    def openlistDecodeTitleFromId(self, _id):
        try:
            parts = str(_id or "").split("|")

            if len(parts) >= 2:
                if parts[0] == "__OPENLIST_SEARCH__" and len(parts) >= 3:
                    title_b64 = parts[2]
                else:
                    title_b64 = parts[1]

                return base64.b64decode(title_b64.encode("utf-8")).decode("utf-8")

        except Exception:
            pass

        return ""


    def openlistPlayerContent(self, _id):
        try:
            _id = str(_id or "")

            if not self.openlist_url or not self.openlist_token:
                return self.returnAckVideo()

            if _id.startswith("__OPENLIST_REFRESH__"):
                title = self.openlistDecodeTitleFromId(_id)
                cnt = self.refreshOpenlistLatest3ToMemory(title)
                print(f"[OpenList REFRESH] clicked, latest videos cached={cnt}")
                return self.returnAckVideo()

            if _id.startswith("__OPENLIST_CODE__"):
                parts = _id.split("|")

                if len(parts) < 2:
                    return self.returnAckVideo()

                try:
                    code_text = base64.b64decode(parts[1].encode("utf-8")).decode("utf-8")
                except Exception:
                    code_text = ""

                if not code_text:
                    return self.returnAckVideo()

                info = self.searchOpenlistBestVideoByCode(code_text)

                if not info or not info.get("path"):
                    return self.returnAckVideo()

                play_url, headers = self.getPlayableUrlFromOpenlist(info.get("path"))

                if not play_url:
                    return self.returnAckVideo()

                return {
                    "parse": 0,
                    "playUrl": "",
                    "url": play_url,
                    "header": headers
                }

            if _id.startswith("__OPENLIST_SEARCH__"):
                parts = _id.split("|")

                try:
                    n = int(parts[1])
                except Exception:
                    n = 5

                title = self.openlistDecodeTitleFromId(_id)
                keywords = self.buildOpenlistSearchKeywords(title, n)

                if not keywords:
                    return self.returnAckVideo()

                info = self.searchOpenlistBestVideo(keywords)

                if not info or not info.get("path"):
                    return self.returnAckVideo()

                play_url, headers = self.getPlayableUrlFromOpenlist(info.get("path"))

                if not play_url:
                    return self.returnAckVideo()

                return {
                    "parse": 0,
                    "playUrl": "",
                    "url": play_url,
                    "header": headers
                }

            return self.returnAckVideo()

        except Exception as e:
            print(f"[OpenList] player error: {e}")
            return self.returnAckVideo()
    def add_to_115_v2(self, magnet):
        if not self.pan_115_cookie:
            print("115添加失败: 未配置 Cookie")
            return

        magnet = self.normalizeMagnet(magnet)
        if not magnet or not magnet.startswith('magnet:'):
            print("115添加失败: 非法磁力链接")
            return

        headers = {
            "User-Agent": self.headers.get('User-Agent', ''),
            "Cookie": self.pan_115_cookie,
            "Origin": "https://115.com",
            "Referer": "https://115.com/web/lixian/",
            "Accept": "application/json, text/javascript, _/_; q=0.01",
            "X-Requested-With": "XMLHttpRequest"
        }

        try:
            pan_session = Session()
            pan_session.verify = False
            pan_session.mount('http://', HTTPAdapter(max_retries=2))
            pan_session.mount('https://', SSLAdapter(max_retries=2))

            space_url = "https://115.com/?ct=offline&ac=space"
            space_resp = pan_session.get(space_url, headers=headers, timeout=10)
            try:
                space_json = space_resp.json()
            except Exception:
                print(f"115获取签名失败(非JSON): {space_resp.text[:200]}")
                return

            if not space_json.get("state"):
                print(f"115获取签名失败(可能Cookie过期): {space_json}")
                return

            sign = space_json.get("sign", "")
            req_time = space_json.get("time", "")
            if not sign or not req_time:
                print(f"115签名数据异常: {space_json}")
                return

            uid_match = re.search(r'UID=(\d+)', self.pan_115_cookie)
            uid = uid_match.group(1) if uid_match else ""

            add_url = "https://115.com/web/lixian/?ct=lixian&ac=add_task_url"
            post_data = {
                "url": magnet,
                "uid": uid,
                "sign": sign,
                "time": req_time
            }

            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
            add_resp = pan_session.post(add_url, data=post_data, headers=headers, timeout=10)

            try:
                add_json = add_resp.json()
            except Exception:
                print(f"115添加失败(非JSON): {add_resp.text[:200]}")
                return

            if add_json.get("state") or add_json.get("errcode") == 0:
                print(f"115离线添加成功: {magnet[:100]}...")
            else:
                error_msg = (
                    add_json.get("error_msg")
                    or add_json.get("msg")
                    or add_json.get("error")
                    or str(add_json)
                )
                print(f"115添加失败: {error_msg}")

        except Exception as e:
            print(f"115离线网络异常: {e}")

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

    # ==================== 在线播放地址解析（保留原逻辑） ====================
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

    # ==================== 预览地址解析（函数保留，不挂线路） ====================
    def getPreviewPlaylist(self, data, url):
        try:
            preview_urls = []
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

            def is_video_link(link):
                if not link:
                    return False
                low = link.lower()
                if self.isAdUrl(link) or low.startswith('magnet:') or low.startswith('ma2gnet:') or low.startswith('javascript:') or low == '#':
                    return False
                return any(x in low for x in ['.m3u8', '.mp4', '.flv', '.mpd'])

            def is_preview_link(link):
                low = (link or '').lower()
                return 'freepv' in low or 'cc3001.dmm.co.jp' in low or 'litevideo' in low or 'preview' in low

            def add_preview(name, link):
                link = normalize_link(link)
                if not link or not is_video_link(link) or link in seen:
                    return
                seen.add(link)
                name = self.cleanPlayName(name or f'预览 {len(preview_urls)+1}')
                if not name or len(name) > 30:
                    name = f'预览 {len(preview_urls)+1}'
                preview_urls.append(f"{name}${self.e64(link)}")

            for source in data('#pills-preview video[src], #pills-preview source[src]').items():
                add_preview(f'预览 {len(preview_urls)+1}', source.attr('src') or '')

            for a in data('#player-tab a').items():
                ds = (a.attr('data-source') or '').strip().lower()
                dk = (a.attr('data-key') or '').strip().lower()
                dt = (a.attr('data-target') or '').strip().lower()
                if ds == 'preview' or dk == 'preview' or 'preview' in dt:
                    m3u8 = a.attr('data-m3u8') or ''
                    if m3u8:
                        add_preview(a.text().strip() or '预览', m3u8)

            html = str(data)
            for p in [
                r'https?://[^\'"\s<>]+?freepv[^\'"\s<>]+?\.(?:mp4|m3u8|flv|mpd)[^\'"\s<>]*',
                r'https?://cc3001\.dmm\.co\.jp/[^\'"\s<>]+?\.(?:mp4|m3u8|flv|mpd)[^\'"\s<>]*',
                r'https?://[^\'"\s<>]+?litevideo[^\'"\s<>]+?\.(?:mp4|m3u8|flv|mpd)[^\'"\s<>]*',
                r'https?://[^\'"\s<>]+?preview[^\'"\s<>]+?\.(?:mp4|m3u8|flv|mpd)[^\'"\s<>]*'
            ]:
                for m in re.finditer(p, html, re.I):
                    link = m.group(0)
                    if is_preview_link(link):
                        add_preview(f'预览 {len(preview_urls)+1}', link)

            return '#'.join(preview_urls[:5]) if preview_urls else ''
        except Exception as e:
            print(f"getPreviewPlaylist error: {e}")
            return ''

    # ==================== 磁力链接提取（保留原逻辑） ====================
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



# ===== JAVMENU_169BBS_115_OPENLIST_PATCH_BEGIN =====
# 说明：
# 只覆盖 115云下载 / 播放列表 / 查询(OpenList) 相关逻辑。
# 首页、分类、列表、封面、在线播放解析尽量不动。
# 115缓存路径、缓存结构、搜索播放规则与 169BBS 对齐。

def _jm_extract_magnet_list_from_playstr(self, magnets_str):
    out, seen = [], set()
    for item in str(magnets_str or "").split("#"):
        if "$" in item:
            _, v = item.split("$", 1)
        else:
            v = item
        v = str(v or "").strip()
        if v.startswith("ma2gnet:"):
            v = v.replace("ma2gnet:", "magnet:", 1)
        try:
            v = self.normalizeMagnet(v)
        except Exception:
            pass
        if v and v.startswith("magnet:") and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _jm_detailContent(self, ids):
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

        url = vod_id if str(vod_id).startswith("http") else f"{self.host}{vod_id}"
        data = self.getpq(url)

        if "/actor/" in url:
            return self.getActressVideos(url, data)

        actors = self.getActors(data)
        actor_links = self.getActorLinks(data)
        vod_actor = actor_links if actor_links else actors

        online_url = self.getPlaylist(data, url)
        magnet_url = self.getMagnetPlaylist(data)
        magnets = self._extract_magnet_list_from_playstr(magnet_url)
        magnet_name_map = self._common_115_magnet_name_map_from_playstr(magnet_url)

        cover = list_pic or self.getCover(data)
        self.last_vod_pic = cover or ""

        title = self.getVodName(data)

        play_from = []
        play_url = []

        if online_url:
            play_from.append("在线播放")
            play_url.append(online_url)

        if magnets:
            # 115云下载：下载状态排最前，磁力项只提交任务，不等待，不播放
            m115 = []
            try:
                mg_json = json.dumps(magnets, ensure_ascii=False)
                mg_b64 = base64.b64encode(mg_json.encode("utf-8")).decode("utf-8")
                status_id = f"__115_STATUS_ALL__|{mg_b64}"
                m115.append(f"下载状态${status_id}")
            except Exception as e:
                print(f"[115 cloud] build status item error: {e}")

            for mg in magnets:
                name = self._common_115_format_magnet_display_name(
                    mg,
                    locals().get("magnet_name_map", {})
                )
                b64 = base64.b64encode(mg.encode("utf-8")).decode("utf-8")
                m115.append(f"{self._common_115_clean_play_name(name, 120)}${b64}")

            play_from.append("115云下载")
            play_url.append("#".join(m115))

            # 播放列表：读取 115 cache
            cached_list = self.build115CachedFilePlayItems(magnets)
            if not cached_list:
                cached_list = "暂无115缓存，请先点115云下载-下载状态$__ACK__"
            play_from.append("播放列表")
            play_url.append(cached_list)

        play_from.append("0")
        play_url.append("不会自动下载，请手动切换到115云下载$__ACK__")

        # 查询：优先 115 cache，再 OpenList
        if self.openlist_url and self.openlist_token:
            play_from.append("查询")
            play_url.append(self.buildOpenlistPlayItems(title))

        # 原磁力推送保留
        if magnet_url:
            play_from.append("磁力推送")
            play_url.append(magnet_url)

        vod = {
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": cover,
            "vod_content": self.getVodContent(data),
            "vod_director": "",
            "vod_actor": vod_actor,
            "vod_area": "日本",
            "vod_year": self.getYear(data),
            "vod_remarks": self.getRemarks(data),
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }
        return {"list": [vod]}
    except Exception as e:
        print(f"detailContent patch error: {e}")
        return {"list": []}


# ===================== 115 cache / 离线 / 播放 =====================

def _jm_115_cache_paths(self):
    paths = []
    main = getattr(self, "cache_115_file", "") or ""
    candidates = [
        main,
        "/storage/emulated/0/Download/115api_cache/115_cache.json",
        "/sdcard/Download/115api_cache/115_cache.json",
        "/storage/emulated/0/Download/115_cache.json",
        "/sdcard/Download/115_cache.json",
        "/sdcard/115_cache.json",
        "/tmp/okys_115_offline_cache.json",
    ]
    for x in candidates:
        x = str(x or "").strip()
        if x and x not in paths:
            paths.append(x)
    return paths


def _jm_115_cache_load(self):
    last_error = ""
    for p in self._115_cache_paths():
        try:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict):
                    if "magnets" not in d or not isinstance(d.get("magnets"), dict):
                        d["magnets"] = {}
                    if "files" not in d or not isinstance(d.get("files"), dict):
                        d["files"] = {}
                    self.cache_115_file = p
                    print(f"[115 cache] load ok: {p}")
                    return d
        except Exception as e:
            last_error = f"{p} => {repr(e)}"
            print(f"[115 cache] load error: {last_error}")

    if last_error:
        print(f"[115 cache] load all failed, last: {last_error}")
    return {"magnets": {}, "files": {}}


def _jm_115_cache_save(self, data):
    errors = []
    for p in self._115_cache_paths():
        try:
            dname = os.path.dirname(p)
            if dname:
                os.makedirs(dname, exist_ok=True)

            tmp = p + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, p)
            except Exception as e1:
                try:
                    with open(p, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except Exception as e2:
                    raise Exception(f"tmp_write_or_replace={repr(e1)}, direct_write={repr(e2)}")

            self.cache_115_file = p
            print(f"[115 cache] write ok: {p}")
            return True
        except Exception as e:
            err = f"{p} => {repr(e)}"
            errors.append(err)
            print(f"[115 cache] save error: {err}")

    print("[115 cache] save all failed: " + " | ".join(errors))
    return False


def _jm_115_extract_btih(self, text):
    s = str(text or "")
    m = re.search(r"btih:([a-fA-F0-9]{40})", s, re.I)
    if m:
        return m.group(1).lower()
    m = re.search(r"btih:([A-Z2-7]{32})", s, re.I)
    if m:
        return m.group(1).lower()
    m = re.search(r"\b([a-fA-F0-9]{40})\b", s)
    if m:
        return m.group(1).lower()
    return ""


def _jm_115_magnet_key(self, magnet):
    h = self._115_extract_btih(magnet)
    if h:
        return h.lower()
    return hashlib.md5(str(magnet or "").encode("utf-8")).hexdigest()


def _jm_115_headers(self):
    return {
        "User-Agent": self.headers.get("User-Agent", "Mozilla/5.0"),
        "Cookie": self.pan_115_cookie,
        "Origin": "https://115.com",
        "Referer": "https://115.com/web/lixian/",
        "Accept": "application/json, text/javascript, _/_; q=0.01",
    }


def _jm_parse115FileItem(self, item, parent_cid=""):
    try:
        name = item.get("n") or item.get("name") or item.get("file_name") or item.get("fname") or ""
        fid = item.get("fid") or item.get("file_id") or item.get("id") or ""
        cid = item.get("cid") or item.get("parent_id") or parent_cid or ""
        pickcode = item.get("pc") or item.get("pick_code") or item.get("pickcode") or item.get("pickCode") or ""
        size = int(item.get("s") or item.get("size") or item.get("file_size") or 0)
        sha1 = item.get("sha") or item.get("sha1") or item.get("file_sha1") or ""
        return {
            "fid": str(fid),
            "cid": str(cid),
            "name": str(name),
            "size": size,
            "pickcode": str(pickcode),
            "sha1": str(sha1),
        }
    except Exception:
        return {
            "fid": "",
            "cid": str(parent_cid or ""),
            "name": "",
            "size": 0,
            "pickcode": "",
            "sha1": "",
        }


def _jm_is115VideoFile(self, name):
    name = str(name or "").lower()
    return name.endswith((
        ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv",
        ".ts", ".m2ts", ".webm", ".m3u8", ".rmvb",
        ".mpg", ".mpeg", ".3gp", ".m4v", ".vob", ".f4v"
    ))


def _jm_choose115VideoFiles(self, files, min_size=None, parent_cid=""):
    if min_size is None:
        min_size = getattr(self, "min_115_video_size", 100 * 1024 * 1024)

    bad_words = ["sample", "trailer", "preview", "预告", "样片", "花絮", "广告"]
    out, seen = [], set()

    for item in files or []:
        info = self.parse115FileItem(item, parent_cid)
        name = info.get("name") or ""
        size = int(info.get("size") or 0)
        low = name.lower()

        if not name:
            continue
        if not self.is115VideoFile(name):
            continue
        if size < min_size:
            continue
        if any(w in low for w in bad_words):
            continue

        k = info.get("fid") or info.get("pickcode") or name
        if k in seen:
            continue
        seen.add(k)
        out.append(info)

    out.sort(key=lambda x: int(x.get("size") or 0), reverse=True)
    return out


def _jm_115_list_files(self, cid="0", limit=500):
    if not self.pan_115_cookie:
        return []

    headers = self._115_headers()
    url = "https://webapi.115.com/files"

    try:
        limit = max(20, min(500, int(limit)))
    except Exception:
        limit = 500

    params = {
        "cid": str(cid or "0"),
        "offset": 0,
        "limit": limit,
        "show_dir": 1,
        "format": "json"
    }

    try:
        s = Session()
        s.verify = False
        try:
            s.mount("http://", HTTPAdapter(max_retries=2))
            s.mount("https://", SSLAdapter(max_retries=2))
        except Exception:
            pass

        r = s.get(url, headers=headers, params=params, timeout=15)
        data = r.json()
        files = data.get("data") or data.get("files") or []
        if not isinstance(files, list):
            files = []
        print(f"[115 files] cid={cid}, count={len(files)}")
        return files
    except Exception as e:
        print(f"[115 files] error: {e}")
        return []


def _jm_115_task_list(self, page=1):
    if not self.pan_115_cookie:
        return []

    headers = self._115_headers()
    urls = [
        "https://115.com/web/lixian/?ct=lixian&ac=task_lists",
        "https://115.com/web/lixian/?ct=lixian&ac=task_list",
    ]
    params = {"page": int(page or 1), "limit": 100}

    for url in urls:
        try:
            s = Session()
            s.verify = False
            try:
                s.mount("http://", HTTPAdapter(max_retries=2))
                s.mount("https://", SSLAdapter(max_retries=2))
            except Exception:
                pass

            r = s.get(url, headers=headers, params=params, timeout=15)
            data = r.json()
            tasks = data.get("tasks") or data.get("data") or data.get("list") or []
            if isinstance(tasks, dict):
                tasks = tasks.get("tasks") or tasks.get("list") or []
            if isinstance(tasks, list):
                print(f"[115 task list] count={len(tasks)}")
                return tasks
        except Exception as e:
            print(f"[115 task list] url={url} error: {e}")

    return []


def _jm_115_find_task_by_hash(self, btih):
    btih = str(btih or "").lower()
    if not btih:
        return None

    tasks = self._115_task_list(1)
    for t in tasks:
        try:
            raw = json.dumps(t, ensure_ascii=False).lower()
            if btih in raw:
                return t

            h = t.get("info_hash") or t.get("hash") or t.get("bt_hash") or t.get("sha1") or ""
            if str(h).lower() == btih:
                return t
        except Exception:
            pass

    return None


def _jm_115_task_done(self, task):
    if not task:
        return False

    raw = json.dumps(task, ensure_ascii=False).lower()
    if any(w in raw for w in ["完成", "已完成", "success", "finished", "done"]):
        return True

    status = task.get("status") or task.get("state") or task.get("percentDone") or task.get("percent") or task.get("progress")
    try:
        if str(status).lower() in ["2", "100", "done", "success", "finished"]:
            return True
        if float(status) >= 100:
            return True
    except Exception:
        pass

    return False


def _jm_115_task_failed(self, task):
    if not task:
        return False

    raw = json.dumps(task, ensure_ascii=False).lower()
    if any(w in raw for w in ["失败", "error", "failed", "fail"]):
        return True

    status = task.get("status") or task.get("state")
    if str(status).lower() in ["-1", "failed", "error"]:
        return True

    return False


def _jm_115_task_save_cid(self, task):
    if not task:
        return str(getattr(self, "pan_115_save_cid", "") or "")

    keys = ["cid", "save_cid", "wp_path_id", "file_id", "to_cid", "target_cid", "parent_id"]

    for k in keys:
        v = task.get(k)
        if v:
            return str(v)

    for k in ["file", "folder", "data", "info"]:
        sub = task.get(k)
        if isinstance(sub, dict):
            for kk in keys:
                v = sub.get(kk)
                if v:
                    return str(v)

    return str(getattr(self, "pan_115_save_cid", "") or "")


def _jm_115_add_task(self, magnet):
    if not self.pan_115_cookie:
        return {"state": False, "msg": "missing 115 cookie"}

    try:
        magnet = self.normalizeMagnet(magnet)
    except Exception:
        pass

    headers = self._115_headers()

    try:
        s = Session()
        s.verify = False
        try:
            s.mount("http://", HTTPAdapter(max_retries=2))
            s.mount("https://", SSLAdapter(max_retries=2))
        except Exception:
            pass

        sign_rsp = s.get(
            "https://115.com/?ct=offline&ac=space",
            headers=headers,
            timeout=10
        ).json()

        if not sign_rsp.get("state"):
            print(f"[115] sign fail: {sign_rsp}")
            return {"state": False, "msg": "sign fail", "raw": sign_rsp}

        sign = sign_rsp.get("sign", "")
        req_time = sign_rsp.get("time", "")

        uid = ""
        m = re.search(r"UID=(\d+)", self.pan_115_cookie)
        if m:
            uid = m.group(1)

        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"

        data = {
            "url": magnet,
            "uid": uid,
            "sign": sign,
            "time": req_time
        }

        if getattr(self, "pan_115_save_cid", ""):
            data["wp_path_id"] = self.pan_115_save_cid

        add_rsp = s.post(
            "https://115.com/web/lixian/?ct=lixian&ac=add_task_url",
            data=data,
            headers=headers,
            timeout=15,
        ).json()

        btih = self._115_extract_btih(magnet)
        ok = bool(add_rsp.get("state") or add_rsp.get("errcode") == 0)

        if ok:
            print(f"[115] add task success, btih={btih}")
        else:
            print(f"[115] add task fail: {add_rsp}")

        return {"state": ok, "btih": btih, "task": add_rsp, "raw": add_rsp}
    except Exception as e:
        print(f"[115] add task error: {e}")
        return {"state": False, "msg": str(e)}


def _jm_115_submit_only(self, magnet):
    try:
        magnet = self.normalizeMagnet(magnet)
    except Exception:
        pass

    key = self._115_magnet_key(magnet)
    btih = self._115_extract_btih(magnet)

    cache = self._115_cache_load()
    rec = cache.get("magnets", {}).get(key)

    if rec:
        print(f"[115 submit] cache exists, status={rec.get('status')}")
        return rec

    task = None
    if btih:
        task = self._115_find_task_by_hash(btih)

    if task:
        status = "done" if self._115_task_done(task) else "downloading"
        rec = {
            "magnet": magnet,
            "key": key,
            "btih": btih,
            "status": status,
            "task": task,
            "cid": self._115_task_save_cid(task),
            "files": [],
            "best": None,
            "update_time": int(time.time())
        }
        cache["magnets"][key] = rec
        self._115_cache_save(cache)
        return rec

    add = self._115_add_task(magnet)

    rec = {
        "magnet": magnet,
        "key": key,
        "btih": btih,
        "status": "submitted" if add.get("state") else "add_failed",
        "task": add.get("task") or add.get("raw") or {},
        "cid": "",
        "files": [],
        "best": None,
        "update_time": int(time.time())
    }

    cache["magnets"][key] = rec
    self._115_cache_save(cache)
    return rec


def _jm_115_list_files_depth1_safe(self, cid="0", limit=500, max_dirs=6, sleep_sec=0.2):
    all_items = []
    visited = set()
    queue = [(str(cid or "").strip(), 0)]
    scanned_dirs = 0
    max_depth = 1

    def get_pickcode(item):
        if not isinstance(item, dict):
            return ""
        return item.get("pick_code") or item.get("pickcode") or item.get("pc") or ""

    def get_name(item):
        if not isinstance(item, dict):
            return ""
        return str(item.get("n") or item.get("name") or item.get("file_name") or "")

    def get_child_cid(item, current_cid):
        try:
            if not isinstance(item, dict):
                return ""
            if get_pickcode(item):
                return ""
            name = get_name(item)
            if name and self.is115VideoFile(name):
                return ""
            child = item.get("cid") or item.get("file_id") or item.get("fid") or item.get("id") or ""
            child = str(child or "").strip()
            current_cid = str(current_cid or "").strip()
            if not child or child == current_cid:
                return ""
            return child
        except Exception:
            return ""

    while queue and scanned_dirs < max_dirs:
        cur_cid, level = queue.pop(0)
        cur_cid = str(cur_cid or "").strip()

        if not cur_cid or cur_cid in visited:
            continue

        visited.add(cur_cid)
        scanned_dirs += 1

        try:
            if sleep_sec and scanned_dirs > 1:
                time.sleep(float(sleep_sec))
        except Exception:
            pass

        try:
            items = self._115_list_files(cur_cid, limit=limit)
        except Exception as e:
            print(f"[115 depth1] list error cid={cur_cid}: {e}")
            items = []

        if not isinstance(items, list):
            items = []

        print(f"[115 depth1] cid={cur_cid}, level={level}, count={len(items)}, scanned={scanned_dirs}/{max_dirs}")

        fixed_items = []
        for it in items:
            if not isinstance(it, dict):
                continue
            x = dict(it)
            if not x.get("_parent_cid"):
                x["_parent_cid"] = cur_cid
            if not x.get("cid"):
                x["cid"] = cur_cid
            fixed_items.append(x)

        all_items.extend(fixed_items)

        if level >= max_depth:
            continue

        for it in fixed_items:
            child_cid = get_child_cid(it, cur_cid)
            if child_cid and child_cid not in visited:
                queue.append((child_cid, level + 1))

    out, seen = [], set()
    for it in all_items:
        if not isinstance(it, dict):
            continue
        k = str(
            it.get("fid")
            or it.get("file_id")
            or it.get("pick_code")
            or it.get("pickcode")
            or it.get("pc")
            or it.get("sha1")
            or it.get("cid")
            or it.get("id")
            or it.get("name")
            or it.get("n")
            or ""
        ).strip()
        if not k:
            k = str(it)
        if k in seen:
            continue
        seen.add(k)
        out.append(it)

    print(f"[115 depth1] total_items={len(out)}, root={cid}, scanned_dirs={scanned_dirs}")
    return out


def _jm_115_resolve_magnet_files(self, magnet, wait=False):
    try:
        magnet = self.normalizeMagnet(magnet)
    except Exception:
        pass

    key = self._115_magnet_key(magnet)
    btih = self._115_extract_btih(magnet)
    cache = self._115_cache_load()
    rec = cache.get("magnets", {}).get(key)

    try:
        if isinstance(rec, dict) and rec.get("status") == "done" and (rec.get("files") or rec.get("best")):
            print(f"[115 resolve] cache hit key={key}, files={len(rec.get('files') or [])}")
            return rec
    except Exception:
        pass

    task = None
    if btih:
        task = self._115_find_task_by_hash(btih)

    if not task:
        if rec and rec.get("task"):
            task = rec.get("task")
        else:
            rec = rec or {
                "magnet": magnet,
                "key": key,
                "btih": btih,
                "status": "not_found",
                "cid": "",
                "task": {},
                "files": [],
                "best": None,
                "update_time": int(time.time())
            }
            cache["magnets"][key] = rec
            self._115_cache_save(cache)
            return rec

    done = self._115_task_done(task)
    failed = self._115_task_failed(task)
    cid = self._115_task_save_cid(task)

    video_files = []

    if done and cid:
        files_raw = self._115_list_files(cid, limit=500)
        video_files = self.choose115VideoFiles(files_raw, self.min_115_video_size, parent_cid=cid)

        if not video_files:
            files_raw_depth1 = self._115_list_files_depth1_safe(
                cid,
                limit=500,
                max_dirs=6,
                sleep_sec=0.2
            )
            video_files = self.choose115VideoFiles(
                files_raw_depth1,
                self.min_115_video_size,
                parent_cid=cid
            )

    if done and not video_files:
        inner_files = task.get("files") or task.get("file_list") or task.get("filelist") or []
        if isinstance(inner_files, list):
            video_files = self.choose115VideoFiles(
                inner_files,
                self.min_115_video_size,
                parent_cid=cid
            )

    best = video_files[0] if video_files else None
    status = "done" if done else ("failed" if failed else "downloading")

    rec = {
        "magnet": magnet,
        "key": key,
        "btih": btih,
        "status": status,
        "cid": cid,
        "task": task or {},
        "files": video_files,
        "best": best,
        "update_time": int(time.time())
    }

    cache["magnets"][key] = rec

    for f in video_files:
        fid = f.get("fid") or ""
        pc = f.get("pickcode") or ""
        fk = fid or pc
        if fk:
            cache["files"][fk] = {
                "fid": fid,
                "pickcode": pc,
                "cid": f.get("cid") or cid,
                "name": f.get("name"),
                "size": f.get("size"),
                "sha1": f.get("sha1"),
                "magnet_key": key,
                "btih": btih,
                "update_time": int(time.time())
            }

    self._115_cache_save(cache)

    print(
        f"[115 resolve] status={status}, cid={cid}, "
        f"videos={len(video_files)}, best={(best or {}).get('name')}"
    )

    return rec


def _jm_build115CachedFilePlayItems(self, magnets):
    try:
        if not magnets:
            return ""

        cache = self._115_cache_load()
        items, seen = [], set()

        for mg in magnets:
            key = self._115_magnet_key(mg)
            rec = cache.get("magnets", {}).get(key)
            if not rec:
                continue

            files = rec.get("files") or []

            for f in files:
                name = f.get("name") or ""
                size = int(f.get("size") or 0)
                fid = f.get("fid") or ""
                pc = f.get("pickcode") or ""
                fk = fid or pc

                if not name or not fk:
                    continue
                if not self.is115VideoFile(name):
                    continue
                if size < self.min_115_video_size:
                    continue
                if fk in seen:
                    continue

                seen.add(fk)
                size_gb = size / 1024 / 1024 / 1024
                show = self.cleanPlayName(f"{name[:50]} [{size_gb:.2f}G]")
                play_id = f"__115_FILE__|{fk}"
                items.append(f"{show}${play_id}")

        return "#".join(items)
    except Exception as e:
        print(f"[115 cached list] error: {e}")
        return ""


def _jm_115StatusAllPlayerContent(self, _id):
    try:
        parts = str(_id or "").split("|", 1)
        if len(parts) < 2:
            return self.returnAckVideo(self.last_vod_pic)

        try:
            magnets_json = base64.b64decode(parts[1].encode("utf-8")).decode("utf-8")
            magnets = json.loads(magnets_json)
        except Exception:
            magnets = []

        if not isinstance(magnets, list) or not magnets:
            return self.returnAckVideo(self.last_vod_pic)

        best_file = None
        updated = 0

        for mg in magnets:
            mg = str(mg or "").strip()
            if not mg:
                continue

            rec = self._115_resolve_magnet_files(mg, wait=False)
            if rec:
                updated += 1

            best = rec.get("best") if isinstance(rec, dict) else None

            if best:
                if not best_file:
                    best_file = best
                else:
                    try:
                        if int(best.get("size") or 0) > int(best_file.get("size") or 0):
                            best_file = best
                    except Exception:
                        pass

        print(f"[115 status all] updated={updated}, best={(best_file or {}).get('name')}")

        if best_file:
            return self._115_play_file_info(best_file)

        return self.returnAckVideo(self.last_vod_pic)
    except Exception as e:
        print(f"[115 status all] error: {e}")
        return self.returnAckVideo(self.last_vod_pic)


def _jm_115CachedFilePlayerContent(self, _id):
    try:
        _id = str(_id or "")
        if not _id.startswith("__115_FILE__|"):
            return self.returnAckVideo(self.last_vod_pic)

        fk = _id.split("|", 1)[1].strip()
        if not fk:
            return self.returnAckVideo(self.last_vod_pic)

        cache = self._115_cache_load()
        f = cache.get("files", {}).get(fk)

        if not f:
            print(f"[115 file] cache miss: {fk}")
            return self.returnAckVideo(self.last_vod_pic)

        return self._115_play_file_info(f)
    except Exception as e:
        print(f"[115 cached file player] error: {e}")
        return self.returnAckVideo(self.last_vod_pic)


def _jm_score115CacheCandidate(self, f, norm_keys):
    try:
        name_n = self.normalizeSearchText(f.get("name") or "")
        score = 0

        for k in norm_keys or []:
            if k and k in name_n:
                score += 100

        size = int(f.get("size") or 0)

        if size >= 100 * 1024 * 1024:
            score += 10
        if size >= 500 * 1024 * 1024:
            score += 20
        if size >= 1024 * 1024 * 1024:
            score += 30

        n = str(f.get("name") or "").lower()
        if n.endswith(".mp4"):
            score += 8
        elif n.endswith(".mkv"):
            score += 6
        elif n.endswith((".ts", ".m2ts")):
            score += 3

        return score
    except Exception:
        return 0


def _jm_search115CacheBestVideo(self, keywords):
    try:
        if not keywords:
            return None

        if isinstance(keywords, str):
            keywords = [keywords]

        keywords = [self.cleanText(x) for x in keywords if self.cleanText(x)]
        if not keywords:
            return None

        cache = self._115_cache_load()
        files_map = cache.get("files", {}) or {}

        if not files_map:
            return None

        norm_keys = [self.normalizeSearchText(k) for k in keywords if k]
        norm_keys = [x for x in norm_keys if x]
        code_info = self.extractVideoCode(" ".join(keywords))

        candidates = []

        for fk, f in files_map.items():
            name = f.get("name") or ""
            size = int(f.get("size") or 0)

            if not name:
                continue
            if not self.is115VideoFile(name):
                continue
            if size < self.min_115_video_size:
                continue

            text_n = self.normalizeSearchText(
                name + " " + str(f.get("cid") or "") + " " + str(f.get("sha1") or "")
            )

            matched = False

            if code_info:
                temp = {"name": name, "path": name}
                if self.candidateMatchCodeSuffixAllowed(temp, code_info, {"", "c", "ch", "uc"}):
                    matched = True
            else:
                if any(k and k in text_n for k in norm_keys):
                    matched = True

            if not matched:
                continue

            item = dict(f)
            item["source"] = "115cache"
            item["path"] = "__115CACHE__|" + str(fk)
            item["_cache_key"] = str(fk)
            candidates.append(item)

        if not candidates:
            return None

        candidates.sort(
            key=lambda x: (
                self.score115CacheCandidate(x, norm_keys),
                int(x.get("size") or 0)
            ),
            reverse=True
        )

        best = candidates[0]
        print(f"[115 cache query] hit={best.get('name')} size={best.get('size')}")
        return best
    except Exception as e:
        print(f"[115 cache query] error: {e}")
        return None


def _jm_json_find_video_urls(self, obj):
    urls = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if isinstance(v, str):
                    sv = v.strip()
                    low = sv.lower()
                    if sv.startswith("http://") or sv.startswith("https://"):
                        if any(t in low for t in [".m3u8", ".mp4", ".ts", "download", "video"]):
                            urls.append(sv)
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)
        elif isinstance(x, str):
            sv = x.strip()
            low = sv.lower()
            if sv.startswith("http://") or sv.startswith("https://"):
                if any(t in low for t in [".m3u8", ".mp4", ".ts", "download", "video"]):
                    urls.append(sv)

    walk(obj)

    out, seen = [], set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _jm_select_best_video_url(self, urls):
    if not urls:
        return ""
    for u in urls:
        if ".m3u8" in u.lower():
            return u
    for u in urls:
        if ".mp4" in u.lower():
            return u
    for u in urls:
        if ".ts" in u.lower():
            return u
    return urls[0]


def _jm_115_get_play_url_by_pickcode(self, pickcode):
    if not pickcode or not self.pan_115_cookie:
        return "", {}

    headers = {
        "User-Agent": self.headers.get("User-Agent", "Mozilla/5.0"),
        "Cookie": self.pan_115_cookie,
        "Referer": "https://115.com/",
        "Origin": "https://115.com",
        "Accept": "application/json, text/plain, _/_",
    }

    candidate_requests = [
        {"url": "https://webapi.115.com/files/video", "params": {"pickcode": pickcode}},
        {"url": "https://webapi.115.com/files/video_info", "params": {"pickcode": pickcode}},
        {"url": "https://webapi.115.com/files/download", "params": {"pickcode": pickcode}},
        {"url": "https://proapi.115.com/android/2.0/ufile/download", "params": {"pickcode": pickcode}},
    ]

    try:
        s = Session()
        s.verify = False
        try:
            s.mount("http://", HTTPAdapter(max_retries=2))
            s.mount("https://", SSLAdapter(max_retries=2))
        except Exception:
            pass

        for req in candidate_requests:
            try:
                url = req.get("url")
                params = req.get("params") or {}
                r = s.get(url, headers=headers, params=params, timeout=15)
                text = r.text or ""

                if r.status_code != 200:
                    print(f"[115 play] {url} HTTP {r.status_code}, text={text[:120]}")
                    continue

                try:
                    data = r.json()
                except Exception:
                    if text.startswith("http://") or text.startswith("https://"):
                        return text.strip(), headers
                    continue

                urls = self._json_find_video_urls(data)
                play_url = self._select_best_video_url(urls)

                if play_url:
                    print(f"[115 play] hit api={url}")
                    return play_url, headers

                print(f"[115 play] no url api={url}")
            except Exception as e:
                print(f"[115 play] candidate error: {req.get('url')} {e}")

    except Exception as e:
        print(f"[115 play] error: {e}")

    return "", headers


def _jm_115_play_file_info(self, file_info):
    if not file_info:
        return self.returnAckVideo(self.last_vod_pic)

    pickcode = file_info.get("pickcode") or ""
    name = file_info.get("name") or ""

    if pickcode:
        play_url, headers = self._115_get_play_url_by_pickcode(pickcode)
        if play_url:
            ret = {
                "parse": 0,
                "playUrl": "",
                "url": play_url,
                "header": headers,
            }
            if self.last_vod_pic:
                ret["pic"] = self.last_vod_pic
                ret["poster"] = self.last_vod_pic
            return ret

    print(f"[115 play] failed name={name}, pickcode={pickcode}")
    return self.returnAckVideo(self.last_vod_pic)


# ===================== OpenList：169BBS 搜索规则 =====================

def _jm_buildOpenlistPlayItems(self, title):
    try:
        title = self.cleanText(title or "")
        title_b64 = base64.b64encode(title.encode("utf-8")).decode("utf-8")
        items = []

        items.append(f"刷新OpenList$__OPENLIST_REFRESH__|{title_b64}")

        code = self.extractVideoCode(title)
        if code:
            code_name = code.get("dash", code.get("raw", "番号"))
            code_b64 = base64.b64encode(code_name.encode("utf-8")).decode("utf-8")
            items.append(f"{code_name}$__OPENLIST_CODE__|{code_b64}")

        for n in range(2, 14):
            items.append(f"搜{n}$__OPENLIST_SEARCH__|{n}|{title_b64}")

        return "#".join(items)
    except Exception as e:
        print(f"[OpenList] build play items error: {e}")
        return "刷新OpenList$__OPENLIST_REFRESH__"


def _jm_openlistApiPost(self, api_path, payload, timeout=15):
    if not self.openlist_url:
        return {}

    url = f"{self.openlist_url}{api_path}"

    try:
        headers = self.openlistHeaders()
        headers.pop("Cookie", None)
        headers.pop("Referer", None)
        headers.pop("Origin", None)
        headers.pop("Host", None)

        sess = getattr(self, "openlist_session", None)
        if sess is None:
            sess = Session()
            sess.verify = False
            self.openlist_session = sess

        r = sess.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout,
            verify=False
        )

        if r.status_code != 200:
            print(f"[OpenList API] {api_path} HTTP {r.status_code}, text={r.text[:300]}")
            return {}

        try:
            data = r.json()
        except Exception:
            print(f"[OpenList API] {api_path} json parse fail: {r.text[:300]}")
            return {}

        if data.get("code") != 200:
            print(f"[OpenList API] {api_path} code={data.get('code')}, message={data.get('message')}")

        return data
    except Exception as e:
        print(f"[OpenList API] {api_path} error: {e}")
        return {}


def _jm_buildOpenlistSearchKeywords(self, title, n=5):
    title = self.cleanText(title or "")
    try:
        n = int(n)
    except Exception:
        n = 5

    n = max(1, min(30, n))
    keywords = []

    code = self.extractVideoCode(title)

    if code:
        keywords += [code.get("dash", ""), code.get("nodash", "")]
    else:
        m = re.search(r"\b([A-Za-z0-9]{2,12})[-_\s]?(\d{2,7})\b", title, re.I)
        if m:
            code1 = m.group(1).upper()
            code2 = m.group(2)
            keywords += [f"{code1}-{code2}", f"{code1}{code2}"]

    raw = re.sub(r"\s+", "", title)
    if raw:
        keywords.append(raw[:n])

    compact = re.sub(r"[\[\]【】()（）{}《》<>「」『』]", "", title)
    compact = re.sub(r"[\/\\\|\-_.,，。:：;；!！?？'\"“”‘’&@]+", "", compact)
    compact = re.sub(r"\s+", "", compact)
    if compact:
        keywords.append(compact[:n])

    tokens = re.split(r"[\s\-_.,，。:：;；!！?？\[\]【】()（）{}<>/\\|]+", title)
    tokens = [x for x in tokens if len(x) >= 3]
    keywords.extend(tokens[:5])

    out, seen = [], set()
    for k in keywords:
        k = self.cleanText(k)
        if k and k not in seen:
            seen.add(k)
            out.append(k)

    return out


def _jm_scoreOpenlistCandidate(self, c, keywords):
    name = self.normalizeSearchText(c.get("name", ""))
    path = self.normalizeSearchText(c.get("path", ""))
    score = 0

    for k in keywords:
        nk = self.normalizeSearchText(k)
        if not nk:
            continue
        if nk in name:
            score += 100
        elif nk in path:
            score += 30

    code_info = self.extractVideoCode(" ".join(keywords))
    if code_info and self.candidateMatchExactCode(c, code_info):
        score += 10000

    try:
        size = int(c.get("size", 0) or 0)
        if size < 50 * 1024 * 1024:
            score -= 100
        elif size < 200 * 1024 * 1024:
            score -= 20
        else:
            score += min(size // (500 * 1024 * 1024), 20)
    except Exception:
        pass

    try:
        t = int(c.get("time", 0) or 0)
        if t > 0:
            age_days = max(0, (time.time() - t) / 86400)
            if age_days <= 1:
                score += 10
            elif age_days <= 3:
                score += 8
            elif age_days <= 7:
                score += 5
            elif age_days <= 30:
                score += 2
    except Exception:
        pass

    n = str(c.get("name", "")).lower()
    if n.endswith(".mp4"):
        score += 8
    elif n.endswith(".mkv"):
        score += 6
    elif n.endswith((".ts", ".m2ts")):
        score += 3
    elif n.endswith((".flv", ".wmv", ".avi")):
        score += 1

    return score


def _jm_searchOpenlistBestVideoByCode(self, code_text):
    try:
        cache_hit = self.search115CacheBestVideo([code_text])
        if cache_hit:
            return cache_hit

        code_info = self.extractVideoCode(code_text or "")
        if not code_info:
            return None

        keywords = [
            code_info.get("dash", ""),
            code_info.get("nodash", ""),
        ]
        keywords = [x for x in keywords if x]
        if not keywords:
            return None

        cache_key = "api_code|" + "|".join(
            [self.openlistNormalizePath(self.openlist_parent)] +
            [self.normalizeSearchText(x) for x in keywords]
        )

        cached = self._cache_get(cache_key)
        if cached:
            return cached

        norm_keys = [self.normalizeSearchText(x) for x in keywords if x]

        recent = getattr(self, "_openlist_recent_files", []) or []
        if recent:
            strict_pool = [
                c for c in recent
                if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"})
            ]
            if strict_pool:
                strict_pool.sort(
                    key=lambda x: (
                        self.scoreOpenlistCandidate(x, norm_keys),
                        int(x.get("size") or 0)
                    ),
                    reverse=True
                )
                best = strict_pool[0]
                self._cache_set(cache_key, best)
                print(f"[OpenList RECENT CODE] hit={best.get('name')} path={best.get('path')}")
                return best

        candidates = self.searchOpenlistByApi(keywords, max_pages=2, per_page=100)
        if not candidates:
            print(f"[OpenList API CODE] no candidates, keywords={keywords}")
            return None

        strict_pool = [
            c for c in candidates
            if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"})
        ]

        if not strict_pool:
            print(f"[OpenList API CODE] no strict match, keywords={keywords}")
            return None

        strict_pool.sort(
            key=lambda x: (
                self.scoreOpenlistCandidate(x, norm_keys),
                int(x.get("size") or 0)
            ),
            reverse=True
        )

        best = strict_pool[0]
        self._cache_set(cache_key, best)
        print(f"[OpenList API CODE] hit={best.get('name')} path={best.get('path')}")
        return best
    except Exception as e:
        print(f"[OpenList API CODE] error: {e}")
        return None


def _jm_searchOpenlistBestVideo(self, keywords):
    try:
        cache_hit = self.search115CacheBestVideo(keywords)
        if cache_hit:
            return cache_hit

        if not keywords:
            return None

        if isinstance(keywords, str):
            keywords = [keywords]

        keywords = [self.cleanText(x) for x in keywords if self.cleanText(x)]
        if not keywords:
            return None

        cache_key = "api_search|" + "|".join(
            [self.openlistNormalizePath(self.openlist_parent)] +
            [self.normalizeSearchText(x) for x in keywords]
        )

        cached = self._cache_get(cache_key)
        if cached:
            return cached

        norm_keys = [self.normalizeSearchText(x) for x in keywords if x]
        code_info = self.extractVideoCode(" ".join(keywords))

        recent = getattr(self, "_openlist_recent_files", []) or []
        if recent:
            recent_candidates = self.filterOpenlistApiCandidates(recent, keywords)
            if recent_candidates:
                if code_info:
                    strict_pool = [
                        c for c in recent_candidates
                        if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"})
                    ]
                    if strict_pool:
                        strict_pool.sort(
                            key=lambda x: (
                                self.scoreOpenlistCandidate(x, norm_keys),
                                int(x.get("size") or 0)
                            ),
                            reverse=True
                        )
                        best = strict_pool[0]
                        self._cache_set(cache_key, best)
                        print(f"[OpenList RECENT CODE] hit={best.get('name')} path={best.get('path')}")
                        return best

                recent_candidates.sort(
                    key=lambda x: (
                        self.scoreOpenlistCandidate(x, norm_keys),
                        int(x.get("size") or 0)
                    ),
                    reverse=True
                )
                best = recent_candidates[0]
                self._cache_set(cache_key, best)
                print(f"[OpenList RECENT] hit={best.get('name')} path={best.get('path')}")
                return best

        candidates = self.searchOpenlistByApi(keywords, max_pages=2, per_page=100)
        if not candidates:
            print(f"[OpenList API SEARCH] no candidates, keywords={keywords}")
            return None

        candidates = self.filterOpenlistApiCandidates(candidates, keywords)
        if not candidates:
            print(f"[OpenList API SEARCH] no filtered candidates, keywords={keywords}")
            return None

        if code_info:
            strict_pool = [
                c for c in candidates
                if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"})
            ]
            if strict_pool:
                strict_pool.sort(
                    key=lambda x: (
                        self.scoreOpenlistCandidate(x, norm_keys),
                        int(x.get("size") or 0)
                    ),
                    reverse=True
                )
                best = strict_pool[0]
                self._cache_set(cache_key, best)
                print(f"[OpenList API SEARCH CODE] hit={best.get('name')} path={best.get('path')}")
                return best
            return None

        candidates.sort(
            key=lambda x: (
                self.scoreOpenlistCandidate(x, norm_keys),
                int(x.get("size") or 0)
            ),
            reverse=True
        )

        best = candidates[0]
        self._cache_set(cache_key, best)
        print(f"[OpenList API SEARCH] hit={best.get('name')} path={best.get('path')}")
        return best
    except Exception as e:
        print(f"[OpenList API SEARCH] search best error: {e}")
        return None


def _jm_getPlayableUrlFromOpenlist(self, file_path):
    try:
        if str(file_path or "").startswith("__115CACHE__|"):
            fk = str(file_path).split("|", 1)[1].strip()
            cache = self._115_cache_load()
            f = cache.get("files", {}).get(fk)

            if f:
                pickcode = f.get("pickcode") or ""
                if pickcode:
                    play_url, headers = self._115_get_play_url_by_pickcode(pickcode)
                    if play_url:
                        return play_url, headers

            return "", {}
    except Exception as e:
        print(f"[115 cache playable] error: {e}")

    file_path = self.openlistNormalizePath(file_path)

    if not self.isPathUnderOpenlistParent(file_path):
        return "", {}

    data = self.openlistApiPost(
        "/api/fs/get",
        {
            "path": file_path,
            "password": ""
        },
        15
    )

    headers = {
        "User-Agent": self.headers.get("User-Agent", "")
    }

    if data.get("code") == 200:
        d = data.get("data", {}) or {}

        extra_header = d.get("header") or d.get("headers") or {}
        if isinstance(extra_header, dict):
            for k, v in extra_header.items():
                if k and v:
                    headers[str(k)] = str(v)

        raw = d.get("raw_url") or d.get("rawUrl") or d.get("url") or ""

        if raw:
            return self.normalizeOpenlistUrl(raw), headers

        sign = d.get("sign") or ""
        return self.buildOpenlistDownloadUrl(file_path, sign), headers

    if self.openlist_force_dav:
        dav = self.buildOpenlistDavUrl(file_path)
        headers["Referer"] = self.openlist_url.rstrip("/") + "/"
        return dav, headers

    return self.buildOpenlistDownloadUrl(file_path), headers


def _jm_openlistPlayerContent(self, _id):
    try:
        _id = str(_id or "")

        if not self.openlist_url or not self.openlist_token:
            return self.returnAckVideo(self.last_vod_pic)

        if _id.startswith("__OPENLIST_REFRESH__"):
            title = self.openlistDecodeTitleFromId(_id)
            cnt = self.refreshOpenlistLatest3ToMemory(title)
            print(f"[OpenList REFRESH] clicked, latest videos cached={cnt}")
            return self.returnAckVideo(self.last_vod_pic)

        if _id.startswith("__OPENLIST_CODE__"):
            parts = _id.split("|")
            if len(parts) < 2:
                return self.returnAckVideo(self.last_vod_pic)

            try:
                code_text = base64.b64decode(parts[1].encode("utf-8")).decode("utf-8")
            except Exception:
                code_text = ""

            if not code_text:
                return self.returnAckVideo(self.last_vod_pic)

            info = self.searchOpenlistBestVideoByCode(code_text)
            if not info or not info.get("path"):
                return self.returnAckVideo(self.last_vod_pic)

            play_url, headers = self.getPlayableUrlFromOpenlist(info.get("path"))
            if not play_url:
                return self.returnAckVideo(self.last_vod_pic)

            ret = {"parse": 0, "playUrl": "", "url": play_url, "header": headers}
            if self.last_vod_pic:
                ret["pic"] = self.last_vod_pic
                ret["poster"] = self.last_vod_pic
            return ret

        if _id.startswith("__OPENLIST_SEARCH__"):
            parts = _id.split("|")
            try:
                n = int(parts[1])
            except Exception:
                n = 5

            title = self.openlistDecodeTitleFromId(_id)
            keywords = self.buildOpenlistSearchKeywords(title, n)
            if not keywords:
                return self.returnAckVideo(self.last_vod_pic)

            info = self.searchOpenlistBestVideo(keywords)
            if not info or not info.get("path"):
                return self.returnAckVideo(self.last_vod_pic)

            play_url, headers = self.getPlayableUrlFromOpenlist(info.get("path"))
            if not play_url:
                return self.returnAckVideo(self.last_vod_pic)

            ret = {"parse": 0, "playUrl": "", "url": play_url, "header": headers}
            if self.last_vod_pic:
                ret["pic"] = self.last_vod_pic
                ret["poster"] = self.last_vod_pic
            return ret

        return self.returnAckVideo(self.last_vod_pic)
    except Exception as e:
        print(f"[OpenList] player error: {e}")
        return self.returnAckVideo(self.last_vod_pic)


def _jm_playerContent(self, flag, id, vipFlags):
    try:
        flag = str(flag or "")
        id = str(id or "")

        if flag == "0" or flag == "提示" or id == "__ACK__":
            return self.returnAckVideo(self.last_vod_pic)

        if flag in ["查询", "115播放"] or id.startswith("__OPENLIST_"):
            if self.openlist_test_stream:
                ret = {
                    "parse": 0,
                    "playUrl": "",
                    "url": self.test_m3u8,
                    "header": {"User-Agent": self.headers.get("User-Agent", "")},
                }
                if self.last_vod_pic:
                    ret["pic"] = self.last_vod_pic
                    ret["poster"] = self.last_vod_pic
                return ret

            return self.openlistPlayerContent(id)

        if flag == "播放列表" or id.startswith("__115_FILE__|"):
            return self._115CachedFilePlayerContent(id)

        if flag == "115云下载":
            if id.startswith("__115_STATUS_ALL__|"):
                return self._115StatusAllPlayerContent(id)

            try:
                real_mag = base64.b64decode(id.encode("utf-8")).decode("utf-8")
                real_mag = self.normalizeMagnet(real_mag)
            except Exception:
                return self.returnAckVideo(self.last_vod_pic)

            if not real_mag:
                return self.returnAckVideo(self.last_vod_pic)

            if self.confirm_115 and real_mag not in self.confirm_cache:
                self.confirm_cache.add(real_mag)
                return self.returnAckVideo(self.last_vod_pic)

            threading.Thread(
                target=self._115_submit_only,
                args=(real_mag,),
                daemon=True
            ).start()

            return self.returnAckVideo(self.last_vod_pic)

        if id.startswith("ma2gnet:") or id.startswith("magnet:"):
            real = id.replace("ma2gnet:", "magnet:", 1)
            ret = {
                "parse": 0,
                "playUrl": "",
                "url": "push://" + real + "#0agent"
            }
            if self.last_vod_pic:
                ret["pic"] = self.last_vod_pic
                ret["poster"] = self.last_vod_pic
            return ret

        if id.startswith("ed2k://"):
            ret = {
                "parse": 0,
                "playUrl": "",
                "url": "push://" + id + "#0agent"
            }
            if self.last_vod_pic:
                ret["pic"] = self.last_vod_pic
                ret["poster"] = self.last_vod_pic
            return ret

        real_url = self.d64(id) or id
        low = real_url.lower()

        if self.isAdUrl(real_url):
            return {
                "parse": 0,
                "url": "",
                "pic": self.last_vod_pic,
                "poster": self.last_vod_pic
            }

        is_direct = any(x in low for x in [".m3u8", ".mp4", ".flv", ".mpd"])

        return {
            "parse": 0 if is_direct else 1,
            "url": real_url,
            "header": self.headers,
            "pic": self.last_vod_pic,
            "poster": self.last_vod_pic
        }
    except Exception as e:
        print(f"[playerContent 169 patch] error: {e}")
        return self.returnAckVideo(self.last_vod_pic)


# ===================== 绑定覆盖 =====================

Spider._extract_magnet_list_from_playstr = _jm_extract_magnet_list_from_playstr
Spider.detailContent = _jm_detailContent

Spider._115_cache_paths = _jm_115_cache_paths
Spider._115_cache_load = _jm_115_cache_load
Spider._115_cache_save = _jm_115_cache_save
Spider._115_extract_btih = _jm_115_extract_btih
Spider._115_magnet_key = _jm_115_magnet_key
Spider._115_headers = _jm_115_headers
Spider.parse115FileItem = _jm_parse115FileItem
Spider.is115VideoFile = _jm_is115VideoFile
Spider.choose115VideoFiles = _jm_choose115VideoFiles
Spider._115_list_files = _jm_115_list_files
Spider._115_task_list = _jm_115_task_list
Spider._115_find_task_by_hash = _jm_115_find_task_by_hash
Spider._115_task_done = _jm_115_task_done
Spider._115_task_failed = _jm_115_task_failed
Spider._115_task_save_cid = _jm_115_task_save_cid
Spider._115_add_task = _jm_115_add_task
Spider.add_to_115_v2 = _jm_115_add_task
Spider._115_submit_only = _jm_115_submit_only
Spider._115_list_files_depth1_safe = _jm_115_list_files_depth1_safe
Spider._115_resolve_magnet_files = _jm_115_resolve_magnet_files
Spider.build115CachedFilePlayItems = _jm_build115CachedFilePlayItems
Spider._115StatusAllPlayerContent = _jm_115StatusAllPlayerContent
Spider._115CachedFilePlayerContent = _jm_115CachedFilePlayerContent
Spider.search115CacheBestVideo = _jm_search115CacheBestVideo
Spider.score115CacheCandidate = _jm_score115CacheCandidate
Spider._json_find_video_urls = _jm_json_find_video_urls
Spider._select_best_video_url = _jm_select_best_video_url
Spider._115_get_play_url_by_pickcode = _jm_115_get_play_url_by_pickcode
Spider._115_play_file_info = _jm_115_play_file_info

Spider.buildOpenlistPlayItems = _jm_buildOpenlistPlayItems
Spider.buildOpenlistSearchKeywords = _jm_buildOpenlistSearchKeywords
Spider.openlistApiPost = _jm_openlistApiPost
Spider.scoreOpenlistCandidate = _jm_scoreOpenlistCandidate
Spider.searchOpenlistBestVideoByCode = _jm_searchOpenlistBestVideoByCode
Spider.searchOpenlistBestVideo = _jm_searchOpenlistBestVideo
Spider.getPlayableUrlFromOpenlist = _jm_getPlayableUrlFromOpenlist
Spider.openlistPlayerContent = _jm_openlistPlayerContent
Spider.playerContent = _jm_playerContent

# ===== JAVMENU_169BBS_115_OPENLIST_PATCH_END =====



# ===== COMMON_115_MAGNET_NAME_ONLY_PATCH_BEGIN =====
# 只修正 115云下载 下磁力项名称：
# 优先使用原磁力线路文件名，并把文件大小移动到名称最前面。
# 下载状态名称保持不变。

def _common_115_decode_possible_b64_text(_s):
    try:
        _s = str(_s or "").strip()
        if not _s:
            return ""
        # urlsafe base64
        try:
            _p = _s + "=" * (-len(_s) % 4)
            _v = base64.urlsafe_b64decode(_p.encode("utf-8")).decode("utf-8")
            if _v:
                return _v
        except Exception:
            pass
        # standard base64
        try:
            _p = _s + "=" * (-len(_s) % 4)
            _v = base64.b64decode(_p.encode("utf-8")).decode("utf-8")
            if _v:
                return _v
        except Exception:
            pass
        return _s
    except Exception:
        return ""


def _common_115_normalize_magnet_for_name(self, _v):
    try:
        _v = str(_v or "").strip()
        if not _v:
            return ""
        if _v.startswith("ma2gnet:"):
            _v = _v.replace("ma2gnet:", "magnet:", 1)
        if hasattr(self, "normalizeMagnet"):
            try:
                return self.normalizeMagnet(_v)
            except Exception:
                pass
        if hasattr(self, "_normalize_magnet"):
            try:
                return self._normalize_magnet(_v)
            except Exception:
                pass
        if _v.startswith("magnet:") and "urn:btih:" in _v:
            return _v
    except Exception:
        pass
    return ""


def _common_115_btih_for_name(self, _magnet):
    try:
        if hasattr(self, "_115_extract_btih"):
            _h = self._115_extract_btih(_magnet)
            if _h:
                return _h.lower()
    except Exception:
        pass
    try:
        _m = re.search(r"btih:([a-fA-F0-9]{40})", str(_magnet or ""), re.I)
        if _m:
            return _m.group(1).lower()
        _m = re.search(r"btih:([A-Z2-7]{32})", str(_magnet or ""), re.I)
        if _m:
            return _m.group(1).lower()
    except Exception:
        pass
    return ""


def _common_115_clean_play_name(self, _name, _limit=100):
    try:
        _name = str(_name or "")
        _name = _name.replace("#", "＃").replace("$", "＄")
        _name = re.sub(r"\s+", " ", _name).strip()
        if hasattr(self, "cleanPlayName"):
            try:
                _name = self.cleanPlayName(_name)
            except Exception:
                pass
        elif hasattr(self, "_clean_name"):
            try:
                _name = self._clean_name(_name, _limit)
            except Exception:
                pass
        return _name[:_limit]
    except Exception:
        return str(_name or "")[:_limit]


def _common_115_is_bad_original_name(_name):
    try:
        _n = re.sub(r"\s+", "", str(_name or "")).strip().lower()
        if not _n:
            return True
        bad = {
            "磁力",
            "磁力链接",
            "磁力资源",
            "链接",
            "ed2k链接",
            "下载",
            "资源",
            "magnet",
            "magnetlink",
        }
        if _n in bad:
            return True
        # 纯短 hash 或类似 hash 的名称，认为没有有效文件名
        if re.fullmatch(r"[a-f0-9]{6,40}", _n, re.I):
            return True
        if re.fullmatch(r"磁力[a-f0-9]{4,16}", _n, re.I):
            return True
        return False
    except Exception:
        return True


def _common_115_move_size_to_front(self, _name):
    """
    把大小移动到最前面：
    例如：
    影片名 1080p 2.36GB -> 2.36GB 影片名 1080p
    [2.36G] 影片名 -> 2.36G 影片名
    850MB-影片名 -> 850MB 影片名
    """
    try:
        _name = str(_name or "").strip()
        if not _name:
            return ""

        # 支持 TB/GB/MB/G/M/GiB/MiB/TiB，避免把 4K 当大小
        size_re = re.compile(
            r"(?i)(?:[\[\(（【]?\s*)"
            r"(\d+(?:\.\d+)?)\s*"
            r"(tb|tib|gb|gib|mb|mib|g|m)"
            r"(?:\s*[\]\)）】]?)"
        )

        _m = size_re.search(_name)
        if not _m:
            return self._common_115_clean_play_name(_name, 120)

        _num = _m.group(1)
        _unit = _m.group(2).upper()

        unit_map = {
            "GIB": "GB",
            "MIB": "MB",
            "TIB": "TB",
            "G": "GB",
            "M": "MB",
        }
        _unit = unit_map.get(_unit, _unit)
        _size = f"{_num}{_unit}"

        # 删除名称里所有大小标记
        _rest = size_re.sub(" ", _name)
        _rest = re.sub(r"[\[\]【】()（）]+", " ", _rest)
        _rest = re.sub(r"[-_｜|:：]+", " ", _rest)
        _rest = re.sub(r"\s+", " ", _rest).strip()

        if _rest:
            return self._common_115_clean_play_name(f"{_size} {_rest}", 120)
        return self._common_115_clean_play_name(_size, 120)
    except Exception:
        return self._common_115_clean_play_name(_name, 120)


def _common_115_magnet_name_map_from_playstr(self, _playstr):
    """
    从原磁力线路里提取：
    原名称 -> magnet

    支持：
    name$magnet:
    name$ma2gnet:
    name$base64(magnet)
    """
    _mp = {}
    try:
        for _item in str(_playstr or "").split("#"):
            if not _item:
                continue

            if "$" in _item:
                _name, _val = _item.split("$", 1)
            else:
                _name, _val = "", _item

            _name = self._common_115_clean_play_name(_name, 160)
            _val = str(_val or "").strip()

            _magnet = self._common_115_normalize_magnet_for_name(_val)

            if not _magnet:
                _decoded = _common_115_decode_possible_b64_text(_val)
                _magnet = self._common_115_normalize_magnet_for_name(_decoded)

            if not _magnet:
                continue

            _key = self._common_115_btih_for_name(_magnet) or _magnet.lower()
            if not _key:
                continue

            if _name and not _common_115_is_bad_original_name(_name):
                _mp[_key] = _name
    except Exception as e:
        print(f"[115 name map] error: {e}")
    return _mp


def _common_115_format_magnet_display_name(self, _magnet, _name_map=None):
    """
    115云下载下单个磁力的显示名：
    1. 优先使用原磁力线路名称
    2. 如果名称里有文件大小，则移动到最前面
    3. 没有有效名称时 fallback：磁力XXXXXXXX
    """
    try:
        _name_map = _name_map or {}
        _key = self._common_115_btih_for_name(_magnet) or str(_magnet or "").lower()
        _raw_name = _name_map.get(_key, "")

        if _raw_name and not _common_115_is_bad_original_name(_raw_name):
            return self._common_115_move_size_to_front(_raw_name)

        _btih = self._common_115_btih_for_name(_magnet)
        if _btih:
            return f"磁力{_btih[:8].upper()}"

        _m = str(_magnet or "")
        return f"磁力{_m[20:28]}" if len(_m) > 28 else "磁力链接"
    except Exception:
        return "磁力链接"


def _common_115_build_cloud_items_named(self, _magnets, _name_map=None):
    """
    通用构建 115云下载列表：
    下载状态 名称保持不变；
    其他磁力项用原文件名。
    """
    _items = []
    try:
        _mg_json = json.dumps(_magnets, ensure_ascii=False)
        _mg_b64 = base64.b64encode(_mg_json.encode("utf-8")).decode("utf-8")
        _items.append(f"下载状态$__115_STATUS_ALL__|{_mg_b64}")
    except Exception as e:
        print(f"[115 cloud] build status item error: {e}")

    for _mg in _magnets or []:
        try:
            _name = self._common_115_format_magnet_display_name(_mg, _name_map or {})
            # 七味/qw 原逻辑使用 urlsafe b64；其他脚本使用普通 b64也能被后续解码兼容
            _encoded = base64.urlsafe_b64encode(str(_mg).encode("utf-8")).decode("utf-8").rstrip("=")
            _items.append(f"{self._common_115_clean_play_name(_name, 120)}${_encoded}")
        except Exception as e:
            print(f"[115 cloud] named item error: {e}")

    return "#".join(_items)


# 绑定到 Spider
Spider._common_115_clean_play_name = _common_115_clean_play_name
Spider._common_115_move_size_to_front = _common_115_move_size_to_front
Spider._common_115_btih_for_name = _common_115_btih_for_name
Spider._common_115_normalize_magnet_for_name = _common_115_normalize_magnet_for_name
Spider._common_115_magnet_name_map_from_playstr = _common_115_magnet_name_map_from_playstr
Spider._common_115_format_magnet_display_name = _common_115_format_magnet_display_name
Spider._common_115_build_cloud_items_named = _common_115_build_cloud_items_named

# 兼容七味/qw 补丁里可能调用的 named builder
Spider._build_115_cloud_items_named = _common_115_build_cloud_items_named

# ===== COMMON_115_MAGNET_NAME_ONLY_PATCH_END =====
# ===== QUERY_ORDER_OPENLIST_DEPTH4_PATCH_BEGIN =====
# 功能：
# 1. 查询线路改为：OpenList 优先，115缓存最后
# 2. OpenList 命中目录后最多展开 4 层索引

def _jm_openlistListDirDepth(self, root_path, max_depth=4, per_page=300, refresh=False, max_dirs=120):
    """
    OpenList 目录递归展开。
    默认最多展开 4 层。
    只收集视频文件。
    """
    results = []
    seen_files = set()
    seen_dirs = set()

    try:
        max_depth = max(0, int(max_depth))
    except Exception:
        max_depth = 4

    try:
        max_dirs = max(1, int(max_dirs))
    except Exception:
        max_dirs = 120

    root_path = self.openlistNormalizePath(root_path)

    if not self.isPathUnderOpenlistParent(root_path):
        return results

    queue = [(root_path, 0)]
    scanned_dirs = 0

    while queue and scanned_dirs < max_dirs:
        cur_path, depth = queue.pop(0)
        cur_path = self.openlistNormalizePath(cur_path)

        if cur_path in seen_dirs:
            continue

        seen_dirs.add(cur_path)
        scanned_dirs += 1

        try:
            items = self.openlistListDirOnce(
                cur_path,
                per_page=per_page,
                refresh=refresh
            )
        except Exception as e:
            print(f"[OpenList DEPTH4] list error path={cur_path}: {e}")
            items = []

        if not items:
            continue

        for it in items:
            try:
                name = str(it.get("name") or "")
                path = self.openlistNormalizePath(it.get("path") or "")

                if not name or not path:
                    continue

                if not self.isPathUnderOpenlistParent(path):
                    continue

                if it.get("is_dir"):
                    if depth < max_depth:
                        queue.append((path, depth + 1))
                    continue

                if not self.isOpenlistVideoFile(name):
                    continue

                if path in seen_files:
                    continue

                seen_files.add(path)
                results.append(it)

            except Exception as e:
                print(f"[OpenList DEPTH4] item error: {e}")

    print(
        f"[OpenList DEPTH4] root={root_path}, "
        f"videos={len(results)}, scanned_dirs={scanned_dirs}, max_depth={max_depth}"
    )

    return results


def _jm_openlistApiSearchFiles_depth4(self, keyword, page=1, per_page=100):
    """
    OpenList /api/fs/search 搜索。
    如果命中目录，则最多展开 4 层找视频。
    """
    results = []

    if not self.openlist_url:
        return results

    keyword = self.cleanText(keyword or "")
    if not keyword:
        return results

    try:
        page = max(1, int(page))
    except Exception:
        page = 1

    try:
        per_page = max(20, min(200, int(per_page)))
    except Exception:
        per_page = 100

    payload = {
        "parent": self.openlistNormalizePath(self.openlist_parent),
        "keywords": keyword,
        "scope": 0,
        "page": page,
        "per_page": per_page,
        "password": ""
    }

    data = self.openlistApiPost("/api/fs/search", payload, 20)

    if data.get("code") != 200:
        return results

    d = data.get("data", {}) or {}
    content = d.get("content") or []

    seen = set()

    for item in content:
        try:
            name = str(item.get("name") or "").strip()
            if not name:
                continue

            parent = str(item.get("parent") or "").strip()
            path = str(item.get("path") or "").strip()

            if path:
                full_path = self.openlistNormalizePath(path)
            else:
                full_path = self.openlistJoinPath(parent, name)

            if not self.isPathUnderOpenlistParent(full_path):
                continue

            # 命中目录：展开 4 层
            if self.openlistIsDir(item):
                children = self.openlistListDirDepth(
                    full_path,
                    max_depth=4,
                    per_page=300,
                    refresh=False,
                    max_dirs=120
                )

                for child in children:
                    child_path = self.openlistNormalizePath(child.get("path") or "")
                    child_name = str(child.get("name") or "")

                    if not child_path or not child_name:
                        continue

                    if child_path in seen:
                        continue

                    if child.get("is_dir"):
                        continue

                    if not self.isOpenlistVideoFile(child_name):
                        continue

                    seen.add(child_path)
                    results.append(child)

                continue

            # 命中文件：必须是视频
            if not self.isOpenlistVideoFile(name):
                continue

            try:
                size = int(item.get("size") or 0)
            except Exception:
                size = 0

            if full_path in seen:
                continue

            seen.add(full_path)

            results.append({
                "name": name,
                "path": full_path,
                "size": size,
                "time": self.parseOpenlistTime(item),
                "sign": item.get("sign", ""),
                "parent": parent,
                "is_dir": False,
            })

        except Exception as e:
            print(f"[OpenList API SEARCH DEPTH4] item error: {e}")

    return results


def _jm_refreshOpenlistLatest3ToMemory_depth4(self, title=""):
    """
    点击 刷新OpenList：
    刷新 openlist_parent 下最新 N 个文件/目录。
    如果是目录，最多展开 4 层。
    """
    try:
        n = max(1, int(getattr(self, "openlist_refresh_latest_n", 3) or 3))
    except Exception:
        n = 3

    parent = self.openlistNormalizePath(self.openlist_parent)

    print(f"[OpenList REFRESH DEPTH4] parent={parent}, latest_n={n}, title={title}")

    try:
        self._openlist_search_cache.clear()
    except Exception:
        pass

    items = self.openlistListDirOnce(parent, per_page=100, refresh=True)

    if not items:
        print("[OpenList REFRESH DEPTH4] parent list empty")
        self._openlist_recent_files = []
        return 0

    items.sort(
        key=lambda x: (
            int(x.get("time") or 0),
            int(x.get("size") or 0)
        ),
        reverse=True
    )

    latest_items = items[:n]

    videos = []
    seen = set()

    for it in latest_items:
        try:
            name = str(it.get("name") or "")
            path = self.openlistNormalizePath(it.get("path") or "")

            if not name or not path:
                continue

            if not it.get("is_dir"):
                if self.isOpenlistVideoFile(name):
                    if path not in seen:
                        seen.add(path)
                        videos.append(it)
                continue

            # 最新项是目录：展开 4 层
            children = self.openlistListDirDepth(
                path,
                max_depth=4,
                per_page=300,
                refresh=True,
                max_dirs=120
            )

            for child in children:
                child_name = str(child.get("name") or "")
                child_path = self.openlistNormalizePath(child.get("path") or "")

                if not child_name or not child_path:
                    continue

                if child.get("is_dir"):
                    continue

                if not self.isOpenlistVideoFile(child_name):
                    continue

                if child_path in seen:
                    continue

                seen.add(child_path)
                videos.append(child)

        except Exception as e:
            print(f"[OpenList REFRESH DEPTH4] latest item error: {e}")

    self._openlist_recent_files = videos

    print(f"[OpenList REFRESH DEPTH4] recent video count={len(videos)}")

    for v in videos[:20]:
        print(f"[OpenList REFRESH DEPTH4] video={v.get('name')} path={v.get('path')}")

    return len(videos)


def _jm_searchOpenlistBestVideoByCode_115_last(self, code_text):
    """
    查询线路番号按钮：
    查询顺序改为：
    1. OpenList 最近刷新缓存
    2. OpenList API
    3. 115 本地缓存
    """
    try:
        code_info = self.extractVideoCode(code_text or "")
        if not code_info:
            # 没有番号时，最后尝试 115 缓存
            return self.search115CacheBestVideo([code_text])

        keywords = [
            code_info.get("dash", ""),
            code_info.get("nodash", ""),
        ]
        keywords = [x for x in keywords if x]

        if not keywords:
            return self.search115CacheBestVideo([code_text])

        cache_key = "api_code|" + "|".join(
            [self.openlistNormalizePath(self.openlist_parent)] +
            [self.normalizeSearchText(x) for x in keywords]
        )

        # 这里的缓存是 OpenList 查询缓存，仍然优先于 115
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        norm_keys = [self.normalizeSearchText(x) for x in keywords if x]

        # 1. OpenList 最近刷新缓存
        recent = getattr(self, "_openlist_recent_files", []) or []
        if recent:
            strict_pool = [
                c for c in recent
                if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"})
            ]

            if strict_pool:
                strict_pool.sort(
                    key=lambda x: (
                        self.scoreOpenlistCandidate(x, norm_keys),
                        int(x.get("size") or 0)
                    ),
                    reverse=True
                )

                best = strict_pool[0]
                self._cache_set(cache_key, best)

                print(f"[OpenList RECENT CODE] hit={best.get('name')} path={best.get('path')}")
                return best

        # 2. OpenList API
        candidates = self.searchOpenlistByApi(keywords, max_pages=2, per_page=100)

        if candidates:
            strict_pool = [
                c for c in candidates
                if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"})
            ]

            if strict_pool:
                strict_pool.sort(
                    key=lambda x: (
                        self.scoreOpenlistCandidate(x, norm_keys),
                        int(x.get("size") or 0)
                    ),
                    reverse=True
                )

                best = strict_pool[0]
                self._cache_set(cache_key, best)

                print(f"[OpenList API CODE] hit={best.get('name')} path={best.get('path')}")
                return best

            print(f"[OpenList API CODE] no strict match, keywords={keywords}")
        else:
            print(f"[OpenList API CODE] no candidates, keywords={keywords}")

        # 3. 115缓存最后查
        cache_hit = self.search115CacheBestVideo([code_text])
        if cache_hit:
            print(f"[115 CACHE LAST CODE] hit={cache_hit.get('name')}")
            return cache_hit

        return None

    except Exception as e:
        print(f"[OpenList API CODE 115 LAST] error: {e}")
        try:
            return self.search115CacheBestVideo([code_text])
        except Exception:
            return None


def _jm_searchOpenlistBestVideo_115_last(self, keywords):
    """
    查询线路 搜2~搜13：
    查询顺序改为：
    1. OpenList 最近刷新缓存
    2. OpenList API
    3. 115 本地缓存
    """
    try:
        if not keywords:
            return None

        if isinstance(keywords, str):
            keywords = [keywords]

        keywords = [self.cleanText(x) for x in keywords if self.cleanText(x)]

        if not keywords:
            return None

        cache_key = "api_search|" + "|".join(
            [self.openlistNormalizePath(self.openlist_parent)] +
            [self.normalizeSearchText(x) for x in keywords]
        )

        # 这里的缓存是 OpenList 查询缓存，仍然优先于 115
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        norm_keys = [self.normalizeSearchText(x) for x in keywords if x]
        code_info = self.extractVideoCode(" ".join(keywords))

        # 1. OpenList 最近刷新缓存
        recent = getattr(self, "_openlist_recent_files", []) or []

        if recent:
            recent_candidates = self.filterOpenlistApiCandidates(recent, keywords)

            if recent_candidates:
                if code_info:
                    strict_pool = [
                        c for c in recent_candidates
                        if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"})
                    ]

                    if strict_pool:
                        strict_pool.sort(
                            key=lambda x: (
                                self.scoreOpenlistCandidate(x, norm_keys),
                                int(x.get("size") or 0)
                            ),
                            reverse=True
                        )

                        best = strict_pool[0]
                        self._cache_set(cache_key, best)

                        print(f"[OpenList RECENT CODE] hit={best.get('name')} path={best.get('path')}")
                        return best

                recent_candidates.sort(
                    key=lambda x: (
                        self.scoreOpenlistCandidate(x, norm_keys),
                        int(x.get("size") or 0)
                    ),
                    reverse=True
                )

                best = recent_candidates[0]
                self._cache_set(cache_key, best)

                print(f"[OpenList RECENT] hit={best.get('name')} path={best.get('path')}")
                return best

        # 2. OpenList API
        candidates = self.searchOpenlistByApi(keywords, max_pages=2, per_page=100)

        if candidates:
            candidates = self.filterOpenlistApiCandidates(candidates, keywords)

            if candidates:
                if code_info:
                    strict_pool = [
                        c for c in candidates
                        if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"})
                    ]

                    if strict_pool:
                        strict_pool.sort(
                            key=lambda x: (
                                self.scoreOpenlistCandidate(x, norm_keys),
                                int(x.get("size") or 0)
                            ),
                            reverse=True
                        )

                        best = strict_pool[0]
                        self._cache_set(cache_key, best)

                        print(f"[OpenList API SEARCH CODE] hit={best.get('name')} path={best.get('path')}")
                        return best

                    print(f"[OpenList API SEARCH] no strict code match, keywords={keywords}")

                else:
                    candidates.sort(
                        key=lambda x: (
                            self.scoreOpenlistCandidate(x, norm_keys),
                            int(x.get("size") or 0)
                        ),
                        reverse=True
                    )

                    best = candidates[0]
                    self._cache_set(cache_key, best)

                    print(f"[OpenList API SEARCH] hit={best.get('name')} path={best.get('path')}")
                    return best

            else:
                print(f"[OpenList API SEARCH] no filtered candidates, keywords={keywords}")
        else:
            print(f"[OpenList API SEARCH] no candidates, keywords={keywords}")

        # 3. 115缓存最后查
        cache_hit = self.search115CacheBestVideo(keywords)
        if cache_hit:
            print(f"[115 CACHE LAST SEARCH] hit={cache_hit.get('name')}")
            return cache_hit

        return None

    except Exception as e:
        print(f"[OpenList API SEARCH 115 LAST] error: {e}")
        try:
            return self.search115CacheBestVideo(keywords)
        except Exception:
            return None


# 绑定覆盖
Spider.openlistListDirDepth = _jm_openlistListDirDepth
Spider.openlistApiSearchFiles = _jm_openlistApiSearchFiles_depth4
Spider.refreshOpenlistLatest3ToMemory = _jm_refreshOpenlistLatest3ToMemory_depth4
Spider.searchOpenlistBestVideoByCode = _jm_searchOpenlistBestVideoByCode_115_last
Spider.searchOpenlistBestVideo = _jm_searchOpenlistBestVideo_115_last

# ===== QUERY_ORDER_OPENLIST_DEPTH4_PATCH_END =====
# ===== FINAL_JAVBUS_OPENLIST_SCORE_PATCH_BEGIN =====
# -*- coding: utf-8 -*-

# ============================================================
# 最终评分规则：
#
# 1. .iso 识别为视频文件
# 2. 同番号命中最高优先，非同番号不能抢同番号
# 3. 同番号且文件 >= 10GB：
#       文件大小最高优先级，谁大选谁
# 4. 同番号且文件 < 10GB：
#       分辨率 > UC/CH/C > 文件大小 > 格式
# 5. UC / CH / C 优先于纯番号
# 6. iso / mp4 / mkv 格式评分相同
# ============================================================

JBF_BIG_FILE_THRESHOLD = 10 * 1024 * 1024 * 1024  # 10GB


# ============================================================
# 让 ISO 也被识别为视频文件
# ============================================================

def _jbf_is_video(self, name):
    try:
        n = str(name or "").lower()
        return n.endswith((
            ".mp4",
            ".mkv",
            ".iso",
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
            ".rmvb",
            ".ts",
            ".m2ts",
        ))
    except Exception:
        return False


# ============================================================
# 分辨率评分
# ============================================================

def _jbf_resolution_score_threshold(all_l):
    """
    分辨率辅助分。
    注意：这里只看文件名 + 路径文字，不读取真实视频分辨率。
    """
    try:
        all_l = str(all_l or "").lower()

        if any(x in all_l for x in [
            "4k",
            "4 k",
            "2160p",
            "2160",
            "uhd",
            "ultra hd",
            "ultrahd",
        ]):
            return 50000

        if any(x in all_l for x in [
            "2k",
            "1440p",
            "1440",
        ]):
            return 20000

        if any(x in all_l for x in [
            "1080p",
            "1080",
            "fhd",
            "fullhd",
        ]):
            return 10000

        if any(x in all_l for x in [
            "720p",
            "720",
        ]):
            return 3000

        return 0

    except Exception:
        return 0


# ============================================================
# UC / CH / C 版本评分
# ============================================================

def _jbf_detect_code_variant_priority_threshold(self, c, keywords):
    """
    同番号变体辅助分：

      UC 版：+3000
      CH 版：+2500
      C 版 ：+2000
      纯番号：+0

    支持识别：

      SONE-168UC
      SONE-168-UC
      SONE_168_UC
      SONE.168.UC

      SONE-168CH
      SONE-168-CH

      SONE-168C
      SONE-168-C
      SONE168C
    """
    try:
        name = str(c.get("name", "") or "")
        path = str(c.get("path", "") or "")
        text = (name + " " + path).lower()

        code_info = _jbf_extract_code(self, " ".join(keywords or []))
        if not code_info:
            return 0

        prefix = str(code_info.get("prefix", "") or "").lower()
        num = str(code_info.get("num", "") or "").lower()

        if not prefix or not num:
            return 0

        # 压缩文本，去掉符号：
        # SONE-168-UC -> sone168uc
        # SONE_168_C  -> sone168c
        compact = _jbf_re.sub(r"[^0-9a-zA-Z]+", "", text).lower()
        base = prefix + num

        if base + "uc" in compact:
            return 3000

        if base + "ch" in compact:
            return 2500

        if base + "c" in compact:
            return 2000

        return 0

    except Exception:
        return 0


# ============================================================
# 视频格式评分
# ============================================================

def _jbf_format_score_threshold(name_l):
    """
    格式辅助分：

      mp4 / mkv / iso = +3
      ts / m2ts       = +2
      其他视频格式     = +1
    """
    try:
        name_l = str(name_l or "").lower()

        if name_l.endswith((".mp4", ".mkv", ".iso")):
            return 3

        if name_l.endswith((".ts", ".m2ts")):
            return 2

        if name_l.endswith((
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".rmvb",
            ".m4v",
        )):
            return 1

        return 0

    except Exception:
        return 0


# ============================================================
# 最终候选评分函数
# ============================================================

def _jbf_score_candidate(self, c, keywords):
    try:
        name = str(c.get("name", "") or "")
        path = str(c.get("path", "") or "")
        size = int(c.get("size") or 0)

        name_l = name.lower()
        path_l = path.lower()
        all_l = name_l + " " + path_l

        score = 0

        # ========================================================
        # 判断是否同番号命中
        # ========================================================
        code_hit = False

        try:
            code_info = _jbf_extract_code(self, " ".join(keywords or []))
            if code_info and _jbf_candidate_match_code(self, c, code_info):
                code_hit = True
        except Exception:
            code_hit = False

        # ========================================================
        # 情况一：同番号命中
        # ========================================================
        if code_hit:
            # 同番号基础超大分，确保非同番号无法抢
            score += 10 ** 30

            # ====================================================
            # A. 同番号 且 >= 10GB
            # 文件大小最高优先级
            # ====================================================
            if size >= JBF_BIG_FILE_THRESHOLD:
                # 大文件区基础分
                # 保证 >=10GB 的同番号文件优先于 <10GB 的同番号文件
                score += 10 ** 25

                # 文件大小绝对优先
                # 乘 1000000，确保哪怕只大 1 byte，
                # 也能压过分辨率、UC/C、格式等辅助分
                score += size * 1000000

                minor = 0

                # 大文件区里这些只是辅助分
                minor += _jbf_resolution_score_threshold(all_l)
                minor += _jbf_detect_code_variant_priority_threshold(self, c, keywords)
                minor += _jbf_format_score_threshold(name_l)

                score += minor

                print("[JavBus Final Score] BIG code_hit=%s score=%s size=%s minor=%s name=%s path=%s" % (
                    code_hit,
                    score,
                    size,
                    minor,
                    name,
                    path,
                ))

                return score

            # ====================================================
            # B. 同番号 但 < 10GB
            # 使用之前评分规则：
            # 分辨率 > UC/CH/C > 文件大小 > 格式
            # ====================================================
            else:
                # 小文件区基础分
                score += 10 ** 20

                # 关键词命中基础分
                try:
                    name_n = _jbf_norm_text(self, name)
                    path_n = _jbf_norm_text(self, path)

                    for k in keywords or []:
                        nk = _jbf_norm_text(self, k)
                        if not nk:
                            continue

                        if nk in name_n:
                            score += 100
                        elif nk in path_n:
                            score += 50
                except Exception:
                    pass

                # 分辨率优先
                resolution_score = _jbf_resolution_score_threshold(all_l)
                score += resolution_score

                # UC / CH / C 优先
                variant_score = _jbf_detect_code_variant_priority_threshold(self, c, keywords)
                score += variant_score

                # 文件大小辅助：
                # 每 100MB +1 分，上限 5000
                size_score = 0
                try:
                    size_score = size // (100 * 1024 * 1024)
                    if size_score > 5000:
                        size_score = 5000
                    score += int(size_score)
                except Exception:
                    size_score = 0

                # 格式辅助分
                format_score = _jbf_format_score_threshold(name_l)
                score += format_score

                print("[JavBus Final Score] SMALL code_hit=%s score=%s size=%s resolution=%s variant=%s size_score=%s format=%s name=%s path=%s" % (
                    code_hit,
                    score,
                    size,
                    resolution_score,
                    variant_score,
                    size_score,
                    format_score,
                    name,
                    path,
                ))

                return score

        # ========================================================
        # 情况二：非同番号
        # 只能普通关键词匹配，不能抢同番号
        # ========================================================
        else:
            try:
                name_n = _jbf_norm_text(self, name)
                path_n = _jbf_norm_text(self, path)

                for k in keywords or []:
                    nk = _jbf_norm_text(self, k)
                    if not nk:
                        continue

                    if nk in name_n:
                        score += 10000
                    elif nk in path_n:
                        score += 5000

            except Exception:
                pass

            # 非同番号也给一点大小分
            # 但这个分数远远低于同番号基础分
            score += size

            print("[JavBus Final Score] NONCODE code_hit=%s score=%s size=%s name=%s path=%s" % (
                code_hit,
                score,
                size,
                name,
                path,
            ))

            return score

    except Exception as e:
        print("[JavBus Final Score] error:", e)
        return 0


print("[FINAL JAVBUS OPENLIST SCORE PATCH] loaded")
# ===== FINAL_JAVBUS_OPENLIST_SCORE_PATCH_END =====


# ===== FINAL_JAVMENU_SITE_IMAGE_ONLINE_PROXY_BEGIN =====
# -*- coding: utf-8 -*-
# ============================================================
# JAVMENU 最终代理规则：
#
# 走代理：
#   javmenu 首页 / 分类 / 列表 / 搜索 / 详情页
#   列表封面 / 详情封面 / 在线播放线路
#
# 不走代理：
#   115云下载 / 115任务查询 / 115文件查询 / 115播放地址
#   OpenList查询 / OpenList播放
#   磁力 push://
#   最终网盘播放链接
#
# 默认代理：
#   http://127.0.0.1:10172
#
# 配置里不要再写：
#   "proxy": "proxy"
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


try:
    Spider._jmpx_old_init = Spider.init
except Exception:
    Spider._jmpx_old_init = None

try:
    Spider._jmpx_old_getpq = Spider.getpq
except Exception:
    Spider._jmpx_old_getpq = None

try:
    Spider._jmpx_old_getListPicture = Spider.getListPicture
except Exception:
    Spider._jmpx_old_getListPicture = None

try:
    Spider._jmpx_old_getCover = Spider.getCover
except Exception:
    Spider._jmpx_old_getCover = None

try:
    Spider._jmpx_old_categoryContent = Spider.categoryContent
except Exception:
    Spider._jmpx_old_categoryContent = None

try:
    Spider._jmpx_old_searchContent = Spider.searchContent
except Exception:
    Spider._jmpx_old_searchContent = None

try:
    Spider._jmpx_old_detailContent = Spider.detailContent
except Exception:
    Spider._jmpx_old_detailContent = None

try:
    Spider._jmpx_old_playerContent = Spider.playerContent
except Exception:
    Spider._jmpx_old_playerContent = None

try:
    Spider._jmpx_old_localProxy = Spider.localProxy
except Exception:
    Spider._jmpx_old_localProxy = None


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
    """
    在线播放线路专用代理 URL。
    仅用于 在线播放，不用于 115/OpenList/磁力push。
    """
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
                # vod_id 里可能打包了封面，保持原样，不强行拆
            except Exception:
                pass
        return ret
    except Exception:
        return ret


def _jmpx_init(self, extend=""):
    """
    最终 init：
    1. 先调用原 init，保留 115/OpenList 配置；
    2. 再给 javmenu 页面、图片、在线播放设置代理；
    3. 115/OpenList/磁力push 保持直连。
    """
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

    # javmenu 站点 session 走代理
    try:
        if hasattr(self, "session") and self.session:
            self.session.trust_env = False
            self.session.verify = False
            self.session.headers.update(_jmpx_site_headers(self, False))
            self.session.proxies.clear()
            self.session.proxies.update(_jmpx_proxies(self) or {})
    except Exception as e:
        print("[JAVMENU FINAL PROXY session setup] error:", e)

    # OpenList session 直连
    try:
        if hasattr(self, "openlist_session") and self.openlist_session:
            self.openlist_session.trust_env = False
            self.openlist_session.proxies.clear()
    except Exception:
        pass

    print("[JAVMENU FINAL PROXY] site/image/online proxy=%s image_proxy=%s online_proxy=%s" % (
        _jmpx_get_site_proxy(self),
        bool(getattr(self, "use_img_proxy", True)),
        bool(getattr(self, "use_online_proxy", True)),
    ))
    print("[JAVMENU FINAL PROXY] 115/OpenList/magnet/push keep direct")


def _jmpx_getpq(self, path=""):
    """
    javmenu 页面请求走代理。
    影响：首页、分类、搜索、详情。
    """
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
                print("[JAVMENU FINAL PROXY GET] %s => %s final=%s len=%s proxy=%s" % (
                    u,
                    rsp.status_code,
                    rsp.url,
                    len(rsp.text or ""),
                    _jmpx_get_site_proxy(self),
                ))
                if rsp.status_code == 200:
                    return _jmpx_pq(rsp.text) if _jmpx_pq else pq(rsp.text)
            except Exception as e:
                print("[JAVMENU FINAL PROXY request error]", u, e)
    except Exception as e:
        print("[JAVMENU FINAL PROXY getpq] error:", e)

    return _jmpx_pq("") if _jmpx_pq else pq("")


def _jmpx_getListPicture(self, item):
    """
    列表封面走图片代理。
    """
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
    """
    详情封面走图片代理。
    """
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
    """
    m3u8 内容重写：
    把分片、子 m3u8 地址继续改成本地 play 代理。
    """
    try:
        out = []
        for line in str(text or "").splitlines():
            raw = line.strip()
            if not raw:
                out.append(line)
                continue

            if raw.startswith("#"):
                # 处理 #EXT-X-KEY:URI="xxx"
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
    """
    接管：
      type=img  图片代理
      type=play 在线播放代理

    其他 localProxy 请求交给旧逻辑。
    """
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

        print("[JAVMENU FINAL PROXY LOCAL] type=%s status=%s ctype=%s len=%s url=%s proxy=%s" % (
            "img" if is_img else "play",
            rsp.status_code,
            ctype,
            len(content),
            fixed,
            _jmpx_get_site_proxy(self),
        ))

        if rsp.status_code != 200 or not content:
            return [404, "text/plain", "Proxy Request Failed"]

        low = fixed.lower()

        # 在线 m3u8：重写分片继续走代理
        if is_play and (".m3u8" in low or "mpegurl" in ctype.lower()):
            try:
                text = rsp.text or content.decode("utf-8", errors="ignore")
                text = _jmpx_rewrite_m3u8(self, text, fixed)
                return [200, "application/vnd.apple.mpegurl", text]
            except Exception as e:
                print("[JAVMENU FINAL PROXY m3u8] error:", e)
                return [200, "application/vnd.apple.mpegurl", content]

        # 图片
        if is_img:
            return [200, _jmpx_guess_ctype(fixed, content, rsp), content]

        # 在线 mp4/flv/mpd/ts：
        # 注意：这里是通过 py 本地代理转发，适合需要代理才能访问的在线播放。
        return [200, _jmpx_guess_ctype(fixed, content, rsp), content]

    except Exception as e:
        print("[JAVMENU FINAL PROXY localProxy] error:", e)
        return [404, "text/plain", "Proxy Error"]


def _jmpx_playerContent(self, flag, id, vipFlags):
    """
    只额外处理 在线播放。
    115 / OpenList / 磁力push 继续走原逻辑，保持不代理。
    """
    try:
        flag = str(flag or "")
        pid = str(id or "")

        # 在线播放线路：走本地 play 代理
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

        # 其他线路：调用原 playerContent，不代理
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

