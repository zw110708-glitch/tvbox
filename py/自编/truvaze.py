import json
import time
from datetime import datetime
from urllib .parse import unquote ,urljoin ,urlparse ,parse_qs
import requests
from bs4 import BeautifulSoup
from base .spider import Spider
class Spider (Spider ):
    def getName (self ):
        return "Truvaze"
    def init (self ,extend =""):
        self .host ="https://truvaze.com"
        cfg =json .loads (extend )if extend else {}
        self .plp =cfg .get ("plp")or ""
        self .proxy =cfg .get ("proxy")or {}
        self .api =self .host +"/api/media"
        self .headers ={
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.7444.235 Safari/537.36",
        "Referer":self .host +"/",
        "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language":"zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Accept-Encoding":"gzip, deflate, br",
        "Connection":"keep-alive",
        "Upgrade-Insecure-Requests":"1",
        "Sec-Fetch-Dest":"document",
        "Sec-Fetch-Mode":"navigate",
        "Sec-Fetch-Site":"none",
        "Sec-Fetch-User":"?1",
        "Cache-Control":"max-age=0",
        "TE":"trailers",
        "Sec-Ch-Ua":'"Not A(Brand";v="99", "Google Chrome";v="142", "Chromium";v="142"',
        "Sec-Ch-Ua-Mobile":"?0",
        "Sec-Ch-Ua-Platform":'"Windows"',
        }
        self .categories =[
        {"type_id":"","type_name":"首页"},
        {"type_id":"weekly","type_name":"每周"},
        {"type_id":"monthly","type_name":"每月"},
        {"type_id":"all","type_name":"所有时间"},
        ]
    def _pic_url (self ,path :str )->str :
        if not path :
            return ""
        s =str (path ).strip ()
        s =s .replace ("&amp;","&")
        if s .startswith ("/"):
            s =urljoin (self .host ,s )
        if s .startswith ("http")and "/_next/image"not in s :
            return s
        if "/_next/image"in s :
            u =urlparse (s )
            qs =parse_qs (u .query )
            raw =(qs .get ("url")or [""])[0 ]
            raw =unquote (raw ).strip ()
            if raw .startswith ("http"):
                return raw
            if raw .startswith ("/"):
                return urljoin (self .host ,raw )
            if raw :
                return urljoin (self .host +"/",raw )
        return urljoin (self .host ,s )if not s .startswith ("http")else s
    def _get_api (self ,params ):
        r =requests .get (
        self .api ,
        params =params ,
        headers =self .headers ,
        timeout =30 ,
        verify =False ,
        proxies =self .proxy if self .proxy else None ,
        )
        return r .json ()
    def _format_time (self ,seconds ):
        if not seconds :
            return "0:00"
        seconds =int (seconds )
        h ,m =divmod (seconds ,3600 )
        m ,s =divmod (m ,60 )
        return f"{h }:{m :02d}:{s :02d}"if h else f"{m }:{s :02d}"
    def _format_count (self ,count ):
        if not count :
            return "0"
        count =int (count )
        if count >=10000 :
            return f"{count /10000 :.1f}w"
        if count >=1000 :
            return f"{count /1000 :.1f}k"
        return str (count )
    def _relative_time (self ,timestamp ):
        if not timestamp :
            return ""
        ts_str =str (timestamp ).strip ()
        if ts_str .endswith ("Z"):
            ts_str =ts_str [:-1 ]+"+00:00"
        dt =datetime .fromisoformat (ts_str )
        ts =int (dt .timestamp ())
        now =int (time .time ())
        diff =now -ts
        if diff <3600 :
            return "刚刚"if diff <60 else f"{diff //60 }分钟前"
        if diff <86400 :
            return f"{diff //3600 }小时前"
        if diff <2592000 :
            return f"{diff //86400 }天前"
        if diff <31536000 :
            return f"{diff //2592000 }个月前"
        return f"{diff //31536000 }年前"
    def _get_extra_info (self ,item ):
        time_str =self ._format_time (item .get ("time",0 ))
        views =item .get ("views")or item .get ("play_count")or item .get ("view_count")
        view_str =f"👁 {self ._format_count (views )}"if views else ""
        upload =item .get ("posted_at")
        upload_str =self ._relative_time (upload )if upload else ""
        parts =[f"⏱ {time_str }"]
        if view_str :
            parts .append (view_str )
        if upload_str :
            parts .append (upload_str )
        return " · ".join (parts )
    def _get_detail_tags (self ,item ):
        url =urljoin (self .host ,f"/zh-CN/movie/{item ['url_cd']}")
        r =requests .get (
        url ,
        headers =self .headers ,
        timeout =30 ,
        verify =False ,
        proxies =self .proxy if self .proxy else None ,
        )
        soup =BeautifulSoup (r .text ,"lxml")
        return [
        f"[a=cr:{json .dumps ({'id':a ['href']},ensure_ascii =False )}/]{a .get_text (strip =True ).lstrip ('#')}[/a]"
        for a in soup .select ("ul.tag-list a")
        ]
    def homeContent (self ,filter ):
        params ={
        "range":"",
        "page":1 ,
        "per_page":50 ,
        "category":"",
        "ids":"",
        "isAnimeOnly":0 ,
        "sort":"favorite",
        }
        data =self ._get_api (params )
        items =[]
        for item in data .get ("items",[]):
            account =item .get ("tweet_account")or "未知用户"
            thumbnail =item .get ("thumbnail")or ""
            items .append (
            {
            "vod_id":str (item .get ("id")),
            "vod_name":f"{account } - {self ._format_time (item .get ('time',0 ))}",
            "vod_pic":self.plp+self ._pic_url (thumbnail ),
            "vod_remarks":self ._get_extra_info (item ),
            }
            )
        return {"class":self .categories ,"list":items ,"filters":{}}
    def categoryContent (self ,tid ,pg ,filter ,extend ):
        range_map ={"daily":"daily","weekly":"weekly","monthly":"monthly","all":"all"}
        tid =(tid or "").strip ()
        if tid =="":
            category =""
        elif tid in range_map :
            category =""
        else :
            category =tid .split ("/category/",1 )[1 ]
        params ={
        "range":range_map .get (tid ,""),
        "page":pg ,
        "per_page":50 ,
        "category":category ,
        "ids":"",
        "isAnimeOnly":0 ,
        "sort":"favorite",
        }
        data =self ._get_api (params )
        items =[]
        for item in data .get ("items",[]):
            account =item .get ("tweet_account")or "未知用户"
            thumbnail =item .get ("thumbnail")or ""
            items .append (
            {
            "vod_id":str (item .get ("id")),
            "vod_name":f"{account } - {self ._format_time (item .get ('time',0 ))}",
            "vod_pic":self.plp+self ._pic_url (thumbnail ),
            "vod_remarks":self ._get_extra_info (item ),
            }
            )
        return {
        "page":int (pg ),
        "pagecount":data .get ("lastPage",1 ),
        "limit":data .get ("perPage",50 ),
        "total":data .get ("total",0 ),
        "list":items ,
        }
    def detailContent (self ,ids ):
        result ={"list":[]}
        for vid in ids :
            params ={"ids":vid }
            data =self ._get_api (params )
            if not data .get ("items"):
                continue
            item =data ["items"][0 ]
            account =item .get ("tweet_account")or "未知用户"
            name =f"{account } - {self ._format_time (item .get ('time',0 ))}"
            thumbnail =item .get ("thumbnail")or ""
            video_url =item .get ("url","")
            vod ={
            "vod_id":vid ,
            "vod_name":name ,
            "vod_pic":self.plp+self ._pic_url (thumbnail ),
            "vod_play_from":"默认",
            "vod_play_url":f"播放${video_url }",
            "vod_remarks":self ._get_extra_info (item ),
            }
            tags =self ._get_detail_tags (item )
            if tags :
                vod ["vod_content"]="标签："+" ".join (tags )
            result ["list"].append (vod )
        return result
    def searchContent (self ,key ,quick ,pg ="1"):
        return {"list":[],"page":int (pg )}
    def playerContent (self ,flag ,id ,vipFlags ):
        return {"parse":0 ,"url":self.plp+str (id )if id else ""}
