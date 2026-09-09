# -*- coding: utf-8 -*-
# @Author  : 恰逢
# @Time    : 2025/10/13 14:15

import sys
import urllib.parse
import re
import requests
from lxml import etree
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    def __init__(self):
        self.name = "禁片天堂"
        self.proxy_host = "http://127.0.0.1:10079/p/0/127.0.0.1:10172/"
        self.base_url = "https://jptt.tv"
        self.session = self._create_session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.54 Safari/537.36",
            "Referer": self.base_url + "/",
            "Origin": self.base_url
        }

    def _create_session(self):
        """创建带重试机制的会话"""
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def _proxy_url(self, url):
        """生成代理URL"""
        if not url:
            return ""
        if url.startswith(('http://', 'https://')):
            return f"{self.proxy_host}{url}"
        return f"{self.proxy_host}{self.base_url}{url}"

    def getName(self):
        return self.name

    def init(self, extend):
        pass

    def homeContent(self, filter):
        cateManual = {
            "中文": "278",
            "巨乳": "15",
            "熟女": "95",
            "騎乘位": "74",
            "口交": "34",
            "癡女": "75",
            "潮吹": "32",
            "企劃片": "84",
            "美尻": "156",
            "打手槍": "98",
            "戲劇、連續劇": "58",
            "制服": "19",
            "美腿": "157",
            "舔鮑": "122",
            "美乳": "166",
            "搭訕": "12",
            "妄想族": "184",
            "第一人稱視點": "167",
            "媽媽系": "193",
            "人妻・主婦": "26",
            "多種職業": "84",
            "羞辱": "163",
            "女教師": "131",
            "淫語": "151",
            "肉感": "136",
            "愛美臀": "111",
            "背後位": "178",
            "調教": "395",
            "處男": "23",
            "護士": "283",
            "修長": "147",
            "露內褲": "169",
            "絲襪": "115",
            "愛巨乳": "200",
            "眼鏡": "290",
            "超乳": "211",
            "顏面騎乘": "263",
            "惡作劇": "145",
            "義母": "144",
            "淫亂・過激系": "63",
            "愛美腿": "11",
            "爆乳": "483",
            "女上司": "137",
            "正太": "415",
            "穿衣幹砲": "179",
            "緊身皮衣": "304",
            "學園": "421",
            "空姐": "132",
            "粉絲感謝祭": "190",
            "背面騎乗位": "646",
            "秘書": "363",
            "女主播": "106",
            "反向搭訕": "305",
            "健身教練": "233",
            "部下・同僚": "150",
            "舞蹈": "130",
            "緊身衣激凸": "321",
            "3D影片": "508",
            "早洩": "403"
        }
        result = {'class': [{'type_name': k, 'type_id': v} for k, v in cateManual.items()]}
        return result

    def homeVideoContent(self):
        return {}

    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        url = self._proxy_url(f"/tag_list?tid={tid}&idx={pg}")
        try:
            rsp = self.fetch(url, headers=self.headers)
            root = etree.HTML(rsp.text)
            videos = root.xpath('//div[contains(@class,"oneVideo")]')
            vodList = []
            for video in videos:
                try:
                    name = video.xpath('.//h3/text()')[0].strip()
                    img = video.xpath('.//img/@src')[0]
                    img = img if img.startswith('http') else self.base_url + img
                    desc = video.xpath('.//p[contains(@class,"p_duration")]/text()')[0].strip()
                    link = video.xpath('.//a/@href')[0]
                    
                    vodList.append({
                        "vod_name": name,
                        "vod_pic": self._proxy_url(img),
                        "vod_remarks": desc,
                        "vod_id": self._proxy_url(link)
                    })
                except:
                    continue

            result['list'] = vodList
            result['page'] = pg
            result['pagecount'] = 9999
            result['limit'] = 90
            result['total'] = 999999
        except Exception as e:
            print(f"[categoryContent error]: {e}")
            result['list'] = []
        return result

    def detailContent(self, array):
        tid = array[0]
        url = self._proxy_url(tid.replace(self.proxy_host, ""))
        try:
            rsp = self.fetch(url, headers=self.headers)
            root = etree.HTML(rsp.text)

            title = root.xpath('//h1[@class="h1_title"]/text()')[0].strip()
            pic = root.xpath('//video/@poster')[0] if root.xpath('//video/@poster') else ""
            pic = pic if pic.startswith('http') else self.base_url + pic
            desc = root.xpath('//div[contains(@class,"info_original")]//p/text()')[0].strip() if root.xpath('//div[contains(@class,"info_original")]//p/text()') else title

            play_url = self._extract_video_url(rsp.text)
            if not play_url.startswith('http'):
                play_url = self._proxy_url(play_url)

            vod = {
                "vod_id": tid,
                "vod_name": title,
                "vod_pic": self._proxy_url(pic),
                "vod_content": desc,
                "vod_play_from": "注意身体",
                "vod_play_url": f"播放地址${play_url}"
            }
            return {'list': [vod]}
        except Exception as e:
            print(f"[detailContent error]: {e}")
            return {'list': []}

    def _extract_video_url(self, html):
        """提取视频播放地址"""
        patterns = [
            r'<source\s+src="([^"]+)"',
            r'//cdn-[^"\']+\.m3u8[^"\']*',
            r'https?://[^"\']+\.m3u8[^"\']*',
            r'/hlsredirect/[^"\']+\.m3u8',
            r'src\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'url\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'file\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                url = match.group(1) if len(match.groups()) > 0 else match.group(0)
                if url.startswith('//'):
                    return 'https:' + url
                elif url.startswith('/'):
                    return url
                elif url.startswith('http'):
                    return url
                else:
                    return '/' + url
        return "/hlsredirect/EXBrcBO4G9RhgaUlZQhY1w/1760457600/hls/video/1/99-22-00164.3gp/index.m3u8"

    def searchContent(self, key, quick, pg="1"):
        result = {}
        url = self._proxy_url(f"/search?kw={urllib.parse.quote(key)}")
        try:
            rsp = self.fetch(url, headers=self.headers)
            root = etree.HTML(rsp.text)
            videos = root.xpath('//div[contains(@class,"oneVideo")]')
            vodList = []
            for video in videos:
                try:
                    name = video.xpath('.//h3/text()')[0].strip()
                    img = video.xpath('.//img/@src')[0]
                    img = img if img.startswith('http') else self.base_url + img
                    desc = video.xpath('.//p[contains(@class,"p_duration")]/text()')[0].strip()
                    link = video.xpath('.//a/@href')[0]
                    
                    vodList.append({
                        "vod_name": name,
                        "vod_pic": self._proxy_url(img),
                        "vod_remarks": desc,
                        "vod_id": self._proxy_url(link)
                    })
                except:
                    continue

            result['list'] = vodList
        except Exception as e:
            print(f"[searchContent error]: {e}")
            result['list'] = []
        return result

    def playerContent(self, flag, id, vipFlags):
        result = {
            "parse": 0,
            "playUrl": "",
            "url": "",
            "header": self.headers
        }
        
        try:
            if flag == "注意身体":
                if id.startswith('http') and '.m3u8' in id:
                    result["url"] = id
                else:
                    url = self._proxy_url(id.replace(self.proxy_host, ""))
                    rsp = self.fetch(url, headers=self.headers)
                    play_url = self._extract_video_url(rsp.text)
                    result["url"] = play_url if play_url.startswith('http') else self._proxy_url(play_url)
        except Exception as e:
            print(f"[playerContent error]: {e}")
            result["url"] = self._proxy_url("/hlsredirect/EXBrcBO4G9RhgaUlZQhY1w/1760457600/hls/video/1/99-22-00164.3gp/index.m3u8")
        
        return result

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def localProxy(self, param):
        return {}