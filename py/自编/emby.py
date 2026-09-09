#coding=utf-8
#!/usr/bin/python
import sys
import json
import time
import random
import requests
import threading
from uuid import uuid4
from urllib.parse import quote

sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    def getName(self):
        return "EMBY"

    def init(self, extend):
        try:
            extendDict = json.loads(extend)
            self.baseUrl = extendDict['server'].strip('/')
            self.username = extendDict['username']
            self.password = extendDict['password']
            self.proxy = extendDict['proxy']
            self.thread = extendDict['thread'] if 'thread' in extendDict else 0
            self.device_id = extendDict.get('device_id', str(uuid4()))
            self.client = extendDict.get('client', 'Hills Windows')
            self.device_name = extendDict.get('device_name', 'My Computer')
            self.client_version = extendDict.get('client_version', '0.2.2')
        except:
            self.baseUrl = ''
            self.username = ''
            self.password = ''
            self.proxy = ''
            self.thread = 0
            self.device_id = str(uuid4())
            self.client = 'Hills Windows'
            self.device_name = 'My Computer'
            self.client_version = '0.2.2'
        
        self.header = {
            "User-Agent": f"{self.client}/{self.client_version}".replace(' ', '-'),
            "X-Emby-Client": self.client,
            "X-Emby-Device-Name": self.device_name,
            "X-Emby-Device-Id": self.device_id,
            "X-Emby-Client-Version": self.client_version
        }
        self.play_sessions = {}
        self.api_prefix = None

    def destroy(self):
        for session_id in list(self.play_sessions.keys()):
            self._record_playback_stop(session_id)
        self.play_sessions.clear()

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def _get_proxies(self):
        if self.proxy and isinstance(self.proxy, str) and self.proxy.strip():
            return {"http": self.proxy, "https": self.proxy}
        return None

    def _detect_api_prefix(self):
        if self.api_prefix is not None:
            return self.api_prefix

        candidates = ['', '/emby']
        header = self.header.copy()
        header['Content-Type'] = "application/json; charset=UTF-8"
        auth_data = {"Username": self.username, "Pw": self.password}
        proxies = self._get_proxies()

        for prefix in candidates:
            url = f"{self.baseUrl}{prefix}/Users/AuthenticateByName"
            try:
                r = requests.post(url, json=auth_data, headers=header, timeout=10, proxies=proxies)
                if r.status_code == 200:
                    self.api_prefix = prefix
                    return prefix
            except:
                pass
        self.api_prefix = None
        return None

    def getAccessToken(self, force_refresh=False):
        if not self.baseUrl or not self.username or not self.password:
            return None

        key = f"emby_{self.baseUrl}_{self.username}_{self.password}"
        if not force_refresh:
            embyInfos = self.getCache(key)
            if embyInfos:
                return embyInfos

        prefix = self._detect_api_prefix()
        if prefix is None:
            return None

        header = self.header.copy()
        header['Content-Type'] = "application/json; charset=UTF-8"
        auth_data = {"Username": self.username, "Pw": self.password}
        auth_url = f"{self.baseUrl}{prefix}/Users/AuthenticateByName"
        proxies = self._get_proxies()
        try:
            r = requests.post(auth_url, json=auth_data, headers=header, timeout=120, proxies=proxies)
            if r.status_code != 200:
                return None
            embyInfos = r.json()
            self.setCache(key, embyInfos)
            return embyInfos
        except:
            return None

    def _request_with_auth_retry(self, method, url, params=None, data=None, headers=None, timeout=180, max_retries=2):
        proxies = self._get_proxies()
        for attempt in range(max_retries):
            embyInfos = self.getAccessToken(force_refresh=(attempt > 0))
            if not embyInfos:
                return None
            token = embyInfos['AccessToken']
            if headers is None:
                headers = self.header.copy()
            headers['X-Emby-Token'] = token
            if params is None:
                params = {}
            params['X-Emby-Token'] = token
            for k, v in self.header.items():
                if k not in headers:
                    headers[k] = v
            try:
                if method.upper() == 'GET':
                    r = requests.get(url, params=params, headers=headers, timeout=timeout, proxies=proxies)
                elif method.upper() == 'POST':
                    r = requests.post(url, params=params, data=data, headers=headers, timeout=timeout, proxies=proxies)
                else:
                    return None
                if r.status_code == 401 and attempt < max_retries - 1:
                    key = f"emby_{self.baseUrl}_{self.username}_{self.password}"
                    self.setCache(key, None)
                    continue
                return r
            except:
                if attempt < max_retries - 1:
                    continue
                return None
        return None

    def homeContent(self, filter):
        if not self.baseUrl:
            return {'class': []}
        prefix = self.api_prefix or ''
        embyInfos = self.getAccessToken()
        if not embyInfos:
            return {'class': []}
        user_id = embyInfos['User']['Id']
        url = f"{self.baseUrl}{prefix}/Users/{user_id}/Views"
        params = {
            "X-Emby-Client": self.client,
            "X-Emby-Device-Name": self.device_name,
            "X-Emby-Device-Id": self.device_id,
            "X-Emby-Client-Version": self.client_version,
            "Fields": "People,Overview,Genres,TagItems,Tags"
        }
        r = self._request_with_auth_retry('GET', url, params=params)
        if r is None or r.status_code != 200:
            return {'class': []}
        try:
            data = r.json()
            typeInfos = data.get('Items', [])
        except:
            return {'class': []}
        classList = []
        for typeInfo in typeInfos:
            name = typeInfo.get('Name', '')
            if "播放列表" in name or '相机' in name:
                continue
            classList.append({"type_name": name, "type_id": typeInfo.get('Id', '')})
        return {'class': classList}

    def homeVideoContent(self):
        return {}

    def categoryContent(self, cid, page, filter, ext):
        if not cid or not self.baseUrl:
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': 0, 'total': 0}
        prefix = self.api_prefix or ''
        embyInfos = self.getAccessToken()
        if not embyInfos:
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': 0, 'total': 0}
        user_id = embyInfos['User']['Id']
        page = int(page) if str(page).isdigit() else 1
        url = f"{self.baseUrl}{prefix}/Users/{user_id}/Items"

        tag_id = None
        person_id = None
        tag_name = None
        if isinstance(cid, str) and cid.startswith('list/list.html'):
            from urllib.parse import urlparse, parse_qs
            try:
                qs = parse_qs(urlparse(cid).query)
                tag_id = (qs.get('tagId') or [None])[0]
                person_id = (qs.get('personId') or [None])[0]
            except:
                pass

        params = {
            "X-Emby-Client": self.client,
            "X-Emby-Device-Name": self.device_name,
            "X-Emby-Device-Id": self.device_id,
            "X-Emby-Client-Version": self.client_version,
            "SortBy": "DateCreated",
            "SortOrder": "Descending",
            "IncludeItemTypes": "Movie,Series",
            "Recursive": "true",
            "Limit": "50",
            "ImageTypeLimit": 1,
            "StartIndex": str((page - 1) * 50),
            "EnableImageTypes": "Primary,Backdrop,Thumb",
            "Fields": "PrimaryImageAspectRatio,ProductionYear,CommunityRating",
            "EnableUserData": "true"
        }

        if person_id:
            params['IncludeItemTypes'] = 'Movie'
            params['PersonIds'] = str(person_id)
        elif tag_id:
            params['IncludeItemTypes'] = 'Movie'
            tag_item_url = f"{self.baseUrl}{prefix}/Users/{user_id}/Items/{tag_id}"
            tag_item_params = {
                "X-Emby-Client": self.client,
                "X-Emby-Device-Name": self.device_name,
                "X-Emby-Device-Id": self.device_id,
                "X-Emby-Client-Version": self.client_version,
            }
            r_tag = self._request_with_auth_retry('GET', tag_item_url, params=tag_item_params, timeout=30)
            if r_tag and r_tag.status_code == 200:
                tag_name = self.cleanText((r_tag.json() or {}).get('Name', ''))
            if tag_name:
                params['Tags'] = tag_name
        else:
            params["ParentId"] = cid

        r = self._request_with_auth_retry('GET', url, params=params, timeout=180)
        if r is None or r.status_code != 200:
            return {'list': [], 'page': page, 'pagecount': 1, 'limit': 0, 'total': 0}
        try:
            data = r.json()
        except:
            return {'list': [], 'page': page, 'pagecount': 1, 'limit': 0, 'total': 0}

        videoList = data.get('Items', [])
        videos = []
        for video in videoList:
            name = self.cleanText(video.get('Name', ''))
            pic = ''
            if 'ImageTags' in video and 'Primary' in video['ImageTags']:
                pic = f"http://127.0.0.1:10079/p/0/127.0.0.1:10172/{self.baseUrl}{prefix}/Items/{video['Id']}/Images/Primary?maxWidth=400&tag={video['ImageTags']['Primary']}&quality=90"
            videos.append({
                "vod_id": video.get('Id', ''),
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": video.get('ProductionYear', '')
            })
        total = int(data.get('TotalRecordCount', 0))
        pagecount = (total + 49) // 50 if total > 0 else 1
        return {
            'list': videos,
            'page': page,
            'pagecount': pagecount,
            'limit': len(videos),
            'total': total
        }

    def detailContent(self, did):
        if not did:
            return {'list': []}
        try:
            embyInfos = self.getAccessToken()
            if not embyInfos:
                return {'list': []}
            prefix = self.api_prefix or ''
            user_id = embyInfos['User']['Id']
            item_id = did[0]
            header = self.header.copy()
            header['Content-Type'] = "application/json; charset=UTF-8"
            url = f"{self.baseUrl}{prefix}/Users/{user_id}/Items/{item_id}"
            params = {
                "X-Emby-Client": self.client,
                "X-Emby-Device-Name": self.device_name,
                "X-Emby-Device-Id": self.device_id,
                "X-Emby-Client-Version": self.client_version,
                "Fields": "People,Overview,Genres,TagItems,Tags"
            }
            r = self._request_with_auth_retry('GET', url, params=params)
            if r is None or r.status_code != 200:
                return {'list': []}
            videoInfos = r.json()
        except:
            return {'list': []}

        vod = {
            "vod_id": item_id,
            "vod_name": videoInfos.get('Name', ''),
            "vod_pic": f"http://127.0.0.1:10079/p/0/127.0.0.1:10172/{self.baseUrl}{prefix}/Items/{item_id}/Images/Primary?maxWidth=400&tag={videoInfos.get('ImageTags', {}).get('Primary', '')}&quality=90" if 'Primary' in videoInfos.get('ImageTags', {}) else '',
            "type_name": videoInfos.get('Genres', [''])[0] if videoInfos.get('Genres') else '',
            "vod_year": videoInfos.get('ProductionYear', ''),
            "vod_content": videoInfos.get('Overview', '').replace('\xa0', ' ').replace('\n\n', '\n').strip(),
            "vod_play_from": "EMBY"
        }

        server_id = embyInfos.get('ServerId') or (embyInfos.get('User') or {}).get('ServerId') or ''
        people = videoInfos.get('People', []) or []
        actors = []
        directors = []
        for person in people:
            name = self.cleanText(person.get('Name', ''))
            if not name:
                continue
            pid = str(person.get('Id') or '').strip()
            href = self._make_list_link(link_type='personId', value=pid or name, server_id=server_id)
            if person.get('Type') == 'Actor':
                actors.append(self._make_clickable(href, name))
            elif person.get('Type') == 'Director':
                directors.append(self._make_clickable(href, name))

        vod['vod_actor'] = ' / '.join(actors)
        vod['vod_director'] = ' / '.join(directors)

        tag_links = []
        for tag in (videoInfos.get('TagItems', []) or []):
            tname = self.cleanText(tag.get('Name', ''))
            if not tname:
                continue
            tag_id = str(tag.get('Id') or '').strip()
            href = self._make_list_link(link_type='tagId', value=tag_id or tname, server_id=server_id)
            tag_links.append(self._make_clickable(href, tname))

        if tag_links:
            tag_line = ' '.join(tag_links)
            if vod.get('vod_content'):
                vod['vod_content'] = f"标签：{tag_line}\n\n{vod['vod_content']}"
            else:
                vod['vod_content'] = f"标签：{tag_line}"

        # 获取播放列表
        playUrl = ''
        try:
            if not videoInfos.get('IsFolder', True):
                playUrl += f"{videoInfos.get('Name', '').strip()}${videoInfos.get('Id', '')}#"
            else:
                url_seasons = f"{self.baseUrl}{prefix}/Shows/{item_id}/Seasons"
                params_seasons = {
                    "UserId": user_id,
                    "EnableImages": "true",
                    "Fields": "BasicSyncInfo,CanDelete,Container,PrimaryImageAspectRatio,ProductionYear,CommunityRating",
                    "EnableUserData": "true",
                    "EnableTotalRecordCount": "false"
                }
                r_seasons = self._request_with_auth_retry('GET', url_seasons, params=params_seasons, timeout=60)
                if r_seasons and r_seasons.status_code == 200:
                    playInfos = r_seasons.json().get('Items', [])
                    for playInfo in playInfos:
                        url_ep = f"{self.baseUrl}{prefix}/Shows/{playInfo['Id']}/Episodes"
                        params_ep = {
                            "SeasonId": playInfo['Id'],
                            "Fields": "BasicSyncInfo,CanDelete,CommunityRating,PrimaryImageAspectRatio,ProductionYear,Overview",
                            "UserId": user_id,
                            "EnableImages": "true",
                            "EnableUserData": "true",
                            "EnableTotalRecordCount": "false"
                        }
                        r_ep = self._request_with_auth_retry('GET', url_ep, params=params_ep, timeout=60)
                        if r_ep and r_ep.status_code == 200:
                            videoList = r_ep.json().get('Items', [])
                            for video in videoList:
                                playUrl += f"{playInfo.get('Name', '').replace('#', '-').replace('$', '|').strip()}|{video.get('Name', '').strip()}${video.get('Id', '')}#"
                else:
                    url_items = f"{self.baseUrl}{prefix}/Users/{user_id}/Items"
                    params_items = {
                        "ParentId": item_id,
                        "Fields": "BasicSyncInfo,CanDelete,Container,PrimaryImageAspectRatio,ProductionYear,CommunityRating,CriticRating",
                        "ImageTypeLimit": "1",
                        "StartIndex": "0",
                        "EnableUserData": "true"
                    }
                    r_items = self._request_with_auth_retry('GET', url_items, params=params_items, timeout=60)
                    if r_items and r_items.status_code == 200:
                        videoList = r_items.json().get('Items', [])
                        for video in videoList:
                            playUrl += f"{video.get('Name', '').replace('#', '-').replace('$', '|').strip()}${video.get('Id', '')}#"
        except:
            pass
        vod['vod_play_url'] = playUrl.strip('#')
        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, keywords, quick, page):
        try:
            embyInfos = self.getAccessToken()
            if not embyInfos:
                return {'list': []}
            prefix = self.api_prefix or ''
            user_id = embyInfos['User']['Id']
            page = int(page) if str(page).isdigit() else 1
            url = f"{self.baseUrl}{prefix}/Users/{user_id}/Items"
            params = {
                "X-Emby-Client": self.client,
                "X-Emby-Device-Name": self.device_name,
                "X-Emby-Device-Id": self.device_id,
                "X-Emby-Client-Version": self.client_version,
                "SortBy": "DateCreated",
                "SortOrder": "Descending",
                "Fields": "BasicSyncInfo,CanDelete,Container,PrimaryImageAspectRatio,ProductionYear,Status,EndDate",
                "StartIndex": str((page - 1) * 50),
                "EnableImageTypes": "Primary,Backdrop,Thumb",
                "ImageTypeLimit": "1",
                "Recursive": "true",
                "SearchTerm": keywords,
                "IncludeItemTypes": "Movie,Series,BoxSet",
                "GroupProgramsBySeries": "true",
                "Limit": "50",
                "EnableTotalRecordCount": "true"
            }
            r = self._request_with_auth_retry('GET', url, params=params)
            if r is None or r.status_code != 200:
                return {'list': []}
            data = r.json()
        except:
            return {'list': []}

        videos = []
        vodList = data.get('Items', [])
        for vod in vodList:
            sid = vod.get('Id', '')
            name = self.cleanText(vod.get('Name', ''))
            pic = ''
            if 'ImageTags' in vod and 'Primary' in vod['ImageTags']:
                pic = f"{self.baseUrl}{prefix}/Items/{sid}/Images/Primary?maxWidth=400&tag={vod['ImageTags']['Primary']}&quality=90"
            videos.append({
                "vod_id": sid,
                "vod_name": name,
                "vod_pic": f"http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pic}" if pic else '',
                "vod_remarks": vod.get('ProductionYear', '')
            })
        return {'list': videos}

    def playerContent(self, flag, pid, vipFlags):
        try:
            embyInfos = self.getAccessToken()
            if not embyInfos:
                return {'list': [], 'msg': '获取Emby服务器信息出错'}
            prefix = self.api_prefix or ''
            user_id = embyInfos['User']['Id']
            header = self.header.copy()
            header['Content-Type'] = "application/json; charset=UTF-8"
            url = f"{self.baseUrl}{prefix}/Items/{pid}/PlaybackInfo"
            params = {
                "UserId": user_id,
                "IsPlayback": "false",
                "AutoOpenLiveStream": "false",
                "StartTimeTicks": 0,
                "MaxStreamingBitrate": "2147483647"
            }
            data = "{\"DeviceProfile\":{\"SubtitleProfiles\":[{\"Method\":\"Embed\",\"Format\":\"ass\"},{\"Format\":\"ssa\",\"Method\":\"Embed\"},{\"Format\":\"subrip\",\"Method\":\"Embed\"},{\"Format\":\"sub\",\"Method\":\"Embed\"},{\"Method\":\"Embed\",\"Format\":\"pgssub\"},{\"Format\":\"subrip\",\"Method\":\"External\"},{\"Method\":\"External\",\"Format\":\"sub\"},{\"Method\":\"External\",\"Format\":\"ass\"},{\"Format\":\"ssa\",\"Method\":\"External\"},{\"Method\":\"External\",\"Format\":\"vtt\"},{\"Method\":\"External\",\"Format\":\"ass\"},{\"Format\":\"ssa\",\"Method\":\"External\"}],\"CodecProfiles\":[{\"Codec\":\"h264\",\"Type\":\"Video\",\"ApplyConditions\":[{\"Property\":\"IsAnamorphic\",\"Value\":\"true\",\"Condition\":\"NotEquals\",\"IsRequired\":false},{\"IsRequired\":false,\"Value\":\"high|main|baseline|constrained baseline\",\"Condition\":\"EqualsAny\",\"Property\":\"VideoProfile\"},{\"IsRequired\":false,\"Value\":\"80\",\"Condition\":\"LessThanEqual\",\"Property\":\"VideoLevel\"},{\"IsRequired\":false,\"Value\":\"true\",\"Condition\":\"NotEquals\",\"Property\":\"IsInterlaced\"}]},{\"Codec\":\"hevc\",\"ApplyConditions\":[{\"Property\":\"IsAnamorphic\",\"Value\":\"true\",\"Condition\":\"NotEquals\",\"IsRequired\":false},{\"IsRequired\":false,\"Value\":\"high|main|main 10\",\"Condition\":\"EqualsAny\",\"Property\":\"VideoProfile\"},{\"Property\":\"VideoLevel\",\"Value\":\"175\",\"Condition\":\"LessThanEqual\",\"IsRequired\":false},{\"IsRequired\":false,\"Value\":\"true\",\"Condition\":\"NotEquals\",\"Property\":\"IsInterlaced\"}],\"Type\":\"Video\"}],\"MaxStreamingBitrate\":40000000,\"TranscodingProfiles\":[{\"Container\":\"ts\",\"AudioCodec\":\"aac,mp3,wav,ac3,eac3,flac,opus\",\"VideoCodec\":\"hevc,h264,mpeg4\",\"BreakOnNonKeyFrames\":true,\"Type\":\"Video\",\"MaxAudioChannels\":\"6\",\"Protocol\":\"hls\",\"Context\":\"Streaming\",\"MinSegments\":2}],\"DirectPlayProfiles\":[{\"Container\":\"mov,mp4,mkv,hls,webm\",\"Type\":\"Video\",\"VideoCodec\":\"h264,hevc,dvhe,dvh1,h264,hevc,hev1,mpeg4,vp9\",\"AudioCodec\":\"aac,mp3,wav,ac3,eac3,flac,truehd,dts,dca,opus,pcm,pcm_s24le\"}],\"ResponseProfiles\":[{\"MimeType\":\"video/mp4\",\"Type\":\"Video\",\"Container\":\"m4v\"}],\"ContainerProfiles\":[],\"MusicStreamingTranscodingBitrate\":40000000,\"MaxStaticBitrate\":40000000}}"
            r = self._request_with_auth_retry('POST', url, params=params, data=data)
            if r is None or r.status_code != 200:
                return {'list': [], 'msg': '获取播放信息失败'}
            media_sources = r.json().get('MediaSources', [])
            if not media_sources:
                return {'list': [], 'msg': '没有可用的媒体源'}
            media_source = media_sources[0]
            direct_stream_url = media_source.get('DirectStreamUrl')
            if not direct_stream_url:
                return {'list': [], 'msg': '无法获取播放URL'}
            url_play = self.baseUrl + direct_stream_url

            try:
                session_id = self._record_playback_start(embyInfos, pid, media_source)
                self._start_progress_updater(embyInfos, pid, media_source, session_id)
            except:
                pass

            if int(self.thread) > 0:
                try:
                    self.fetch('http://127.0.0.1:10079/p/0/127.0.0.1:10172/', timeout=120)
                except:
                    self.fetch('http:127.0.0.1:10172/go')
                url_play = f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{quote(url_play)}&thread={self.thread}'
            return {"url": url_play, "header": self.header, "parse": 0}
        except Exception as e:
            return {'list': [], 'msg': f'播放出错: {str(e)}'}

    def _record_playback_start(self, embyInfos, item_id, media_source):
        header = self.header.copy()
        header['Content-Type'] = "application/json; charset=UTF-8"
        header.update({
            "X-Emby-Client": self.client,
            "X-Emby-Device-Name": self.device_name,
            "X-Emby-Device-Id": self.device_id,
            "X-Emby-Client-Version": self.client_version,
            "X-Emby-Token": embyInfos['AccessToken']
        })
        session_id = f"session_{int(time.time())}_{random.randint(1000, 9999)}"
        play_data = {
            "ItemId": item_id,
            "MediaSourceId": media_source.get('Id'),
            "CanSeek": True,
            "IsPaused": False,
            "IsMuted": False,
            "PositionTicks": 0,
            "PlayMethod": "DirectStream",
            "PlaySessionId": session_id,
            "LiveStreamId": None,
            "AudioStreamIndex": 1,
            "SubtitleStreamIndex": -1,
            "VolumeLevel": 100,
            "PlaybackStartTimeTicks": int(time.time() * 10000000)
        }
        play_url = f"{self.baseUrl}/Sessions/Playing"
        try:
            response = requests.post(play_url, json=play_data, headers=header, timeout=5, proxies=self._get_proxies())
            if response.status_code in (200, 204):
                self.play_sessions[session_id] = {
                    'embyInfos': embyInfos,
                    'item_id': item_id,
                    'media_source': media_source,
                    'start_time': time.time(),
                    'last_update': time.time()
                }
                return session_id
        except:
            pass
        return None

    def _record_playback_progress(self, embyInfos, item_id, media_source, session_id, position_seconds):
        header = self.header.copy()
        header['Content-Type'] = "application/json; charset=UTF-8"
        header.update({
            "X-Emby-Client": self.client,
            "X-Emby-Device-Name": self.device_name,
            "X-Emby-Device-Id": self.device_id,
            "X-Emby-Client-Version": self.client_version,
            "X-Emby-Token": embyInfos['AccessToken']
        })
        progress_data = {
            "ItemId": item_id,
            "MediaSourceId": media_source.get('Id'),
            "PositionTicks": int(position_seconds * 10000000),
            "IsPaused": False,
            "PlaySessionId": session_id,
            "EventName": "timeupdate"
        }
        progress_url = f"{self.baseUrl}/Sessions/Playing/Progress"
        try:
            response = requests.post(progress_url, json=progress_data, headers=header, timeout=5, proxies=self._get_proxies())
            return response.status_code in (200, 204)
        except:
            return False

    def _record_playback_stop(self, session_id):
        if session_id not in self.play_sessions:
            return False
        session_info = self.play_sessions[session_id]
        embyInfos = session_info['embyInfos']
        item_id = session_info['item_id']
        media_source = session_info['media_source']
        total_duration = time.time() - session_info['start_time']
        header = self.header.copy()
        header['Content-Type'] = "application/json; charset=UTF-8"
        header.update({
            "X-Emby-Client": self.client,
            "X-Emby-Device-Name": self.device_name,
            "X-Emby-Device-Id": self.device_id,
            "X-Emby-Client-Version": self.client_version,
            "X-Emby-Token": embyInfos['AccessToken']
        })
        stop_data = {
            "ItemId": item_id,
            "MediaSourceId": media_source.get('Id'),
            "PositionTicks": int(total_duration * 10000000),
            "PlaySessionId": session_id
        }
        stop_url = f"{self.baseUrl}/Sessions/Playing/Stopped"
        try:
            response = requests.post(stop_url, json=stop_data, headers=header, timeout=5, proxies=self._get_proxies())
            if response.status_code in (200, 204):
                if session_id in self.play_sessions:
                    del self.play_sessions[session_id]
                return True
        except:
            pass
        return False

    def _start_progress_updater(self, embyInfos, item_id, media_source, session_id):
        if not session_id:
            return
        def progress_updater():
            try:
                start_time = time.time()
                last_update = start_time
                while session_id in self.play_sessions:
                    current_time = time.time()
                    elapsed = current_time - start_time
                    if current_time - last_update >= 30:
                        self._record_playback_progress(embyInfos, item_id, media_source, session_id, elapsed)
                        last_update = current_time
                    if elapsed >= 7200:
                        break
                    time.sleep(5)
                if session_id in self.play_sessions:
                    self._record_playback_stop(session_id)
            except:
                if session_id in self.play_sessions:
                    self._record_playback_stop(session_id)
        threading.Thread(target=progress_updater, daemon=True).start()

    def localProxy(self, params):
        pass

    def _make_clickable(self, href, name):
        try:
            payload = {"id": href, "name": name}
            return f'[a=cr:{json.dumps(payload, ensure_ascii=False)}/]{name}[/a]'
        except:
            return name

    def _make_list_link(self, *, link_type, value, server_id=''):
        base = f"list/list.html?type=Movie&{link_type}={value}"
        if server_id:
            base += f"&serverId={server_id}"
        return base

    def cleanText(self, text):
        if not text:
            return ""
        return text.replace("\n", " ").replace("\r", " ").replace("\t", " ").strip()