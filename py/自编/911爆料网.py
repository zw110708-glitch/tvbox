# -*- coding: utf-8 -*-
import json,re,sys
from base64 import b64decode,b64encode
from html import unescape
from urllib.parse import quote,urljoin
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
sys.path.append('..')
from base.spider import Spider as BaseSpider

class Spider(BaseSpider):
    _K=b"f5d965df75336270"
    _IV=b"97b60394abc2fbe1"

    def init(self,extend=""):
        cfg={}
        if isinstance(extend,(str,dict)) and extend:
            try: cfg=json.loads(extend) if isinstance(extend,str) else extend
            except Exception: cfg={}
        self.host="https://911bl.com"
        self.proxies=cfg.get('proxies',{          "http": "http://127.0.0.1:10172",
          "https": "http://127.0.0.1:10172"}) or {}
        self.s=requests.Session()
        self.headers={"User-Agent":"Mozilla/5.0","Referer":self.host+"/"}

    def getName(self):
        return "911爆料(极简)"

    def isVideoFormat(self,url):
        u=(url or "").lower()
        return any(x in u for x in (".m3u8",".mp4",".m4v",".flv",".ts"))

    def manualVideoCheck(self):
        return False

    def homeContent(self,filter):
        h=self._get(self.host+"/")
        return {"class":self._cats(h),"filters":{},"list":self._list(h)}

    def homeVideoContent(self):
        return {"list":self.homeContent(None).get("list",[])}

    def categoryContent(self,tid,pg,filter,extend):
        pg=int(pg or 1)
        h=self._get(self._cat_url(tid,pg))
        return {"list":self._list(h),"page":pg,"pagecount":9999,"limit":30,"total":999999}

    def searchContent(self,key,quick,pg="1"):
        h=self._get(f"{self.host}/?s={quote(key)}")
        return {"list":self._list(h),"page":int(pg or 1),"pagecount":9999}

    def detailContent(self,ids):
        url=ids[0]
        if not url.startswith("http"): url=urljoin(self.host+"/",url.lstrip("/"))
        h=self._get(url)
        plays=self._plays(h)
        if not plays:
            for ep in self._eps(h):
                eh=self._get(ep)
                u=self._plays(eh)
                if u: plays.append(u[0])
        t=self._title(h)
        pic=self._cover(h)
        tags=self._tags(h)
        intro=self._intro(h)
        content=("标签: "+" ".join(tags)) if tags else ""
        if intro: content=(content+"\n" if content else "")+intro
        vod={"vod_id":ids[0],"vod_name":t,"vod_pic":self._img(pic) if pic else "","vod_play_from":"DPlayer","vod_play_url":self._pl(plays) if plays else ("网页$"+url),"vod_content":content}
        return {"list":[vod]}

    def playerContent(self,flag,id,vipFlags):
        # 极简兼容：当真实播放地址包含 ? 或 & 时，直接拼代理 path 会被截断，需先编码
        pid = quote(id, safe='') if (id and ('?' in id or '&' in id)) else id
        return {"parse":0 if self.isVideoFormat(id) else 1,
                "url":f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pid}',
                "header":self.headers}

    def localProxy(self,param):
        try:
            if param.get("type")!="img": return [404,"text/plain",b""]
            url=self._d64(param.get("url") or "")
            if not url.startswith("http"): url=urljoin(self.host+"/",url.lstrip("/"))
            r=self.s.get(url,headers=self.headers,timeout=15,proxies=self.proxies)
            data=self._aes(r.content)
            ctype="image/jpeg"
            if data.startswith(b"\x89PNG"): ctype="image/png"
            elif data[:6] in (b"GIF87a",b"GIF89a"): ctype="image/gif"
            elif data.startswith(b"RIFF") and b"WEBP" in data[8:16]: ctype="image/webp"
            return [200,ctype,data]
        except Exception:
            return [404,"text/plain",b""]

    def _get(self,url):
        r=self.s.get(url,headers=self.headers,timeout=15,proxies=self.proxies)
        r.encoding=r.apparent_encoding
        return r.text or ""

    def _cats(self,h):
        out=[];seen=set()
        for href,name in re.findall(r'href="(https?://[^\"]+?/category/[^\"]+?/|/category/[^\"]+?/)"[^>]*>([^<]{1,30})<',h):
            name=re.sub(r"\s+"," ",name).strip()
            if not name: continue
            if href.startswith("/"): href=urljoin(self.host+"/",href.lstrip("/"))
            m=re.search(r"https?://[^/]+(/category/[^\s\"']+/)",href)
            if not m: continue
            u=urljoin(self.host+"/",m.group(1).lstrip("/"))
            if u in seen: continue
            seen.add(u);out.append({"type_name":name,"type_id":u})
        return out

    def _cat_url(self,tid,pg):
        tid=(tid or "").strip()
        if not tid: return self.host+"/"
        base=tid if tid.startswith("http") else urljoin(self.host+"/",tid.lstrip("/"))
        base=base.rstrip("/")+"/"
        return base if pg==1 else f"{base}{pg}/"

    def _list(self,h):
        out=[];seen=set()
        # 1) 常规列表：article 卡片
        for blk in re.findall(r"<article[\s\S]*?</article>",h,re.I):
            m=re.search(r'href="([^"]*?/archives/\d+/)"',blk)
            if not m: continue
            href=m.group(1)
            if href.startswith("/"): href=urljoin(self.host+"/",href.lstrip("/"))
            if href in seen: continue
            mt=re.search(r'class="post-card-title"[^>]*>([\s\S]*?)</',blk)
            title=re.sub(r"\s+"," ",re.sub(r"<[^>]+>","",mt.group(1))).strip() if mt else ""
            if not title: continue
            mp=re.search(r"loadBannerDirect\('([^']+\.(?:jpg|jpeg|png|webp|gif)[^']*)'",blk,re.I)
            if not mp: continue
            mr=re.search(r'itemprop="datePublished"[^>]*>([^<]+)<',blk)
            seen.add(href)
            out.append({"vod_id":href,"vod_name":title,"vod_pic":self._img(mp.group(1).strip()),"vod_remarks":(mr.group(1).strip() if mr else ""),"style":{"type":"rect","ratio":1.33}})
        if out: return out
        # 2) 网黄专辑 / 爆料排行：详情页内用 btn-primary 链接直指 /archives/xxxx/
        for p in re.findall(r"<p[^>]*>[\s\S]*?</p>",h,re.I):
            ma=re.search(r'<a[^>]*href="([^"]*?/archives/\d+/)"[^>]*class="[^"]*btn\s+btn-primary[^"]*"[^>]*>([\s\S]*?)</a>',p,re.I)
            if not ma: continue
            href=ma.group(1)
            if href.startswith("/"): href=urljoin(self.host+"/",href.lstrip("/"))
            if href in seen: continue
            title=re.sub(r"\s+"," ",re.sub(r"<[^>]+>","",ma.group(2))).strip()
            if not title: continue
            # 同段落里优先取加密图真实地址 data-xkrkllgl，其次退回普通图片
            mp=re.search(r'data-xkrkllgl="([^"]+\.(?:jpg|jpeg|png|webp|gif)[^"]*)"',p,re.I) or re.search(r'src="([^"]+\.(?:jpg|jpeg|png|webp|gif)[^"]*)"',p,re.I)
            pic=self._img(mp.group(1).strip()) if mp else ""
            seen.add(href)
            out.append({"vod_id":href,"vod_name":title,"vod_pic":pic,"vod_remarks":"","style":{"type":"rect","ratio":1.33}})
        return out

    def _title(self,h):
        m=re.search(r"<h1[^>]*>([\s\S]*?)</h1>",h,re.I)
        if m: return re.sub(r"\s+"," ",re.sub(r"<[^>]+>","",m.group(1))).strip()
        m=re.search(r"<title>([\s\S]*?)</title>",h,re.I)
        if not m: return ""
        t=re.sub(r"\s+"," ",m.group(1)).strip()
        return t.split("-")[0].strip() if "-" in t else t

    def _cover(self,h):
        m=re.search(r"loadBannerDirect\('([^']+\.(?:jpg|jpeg|png|webp|gif)[^']*)'",h,re.I)
        return m.group(1).strip() if m else ""

    def _plays(self,h):
        urls=[]
        for a,b in re.findall(r"data-config=(?:\"([^\"]+)\"|'([^']+)')",h):
            cfg=a or b
            try:
                obj=json.loads(unescape(cfg))
                u=((obj or {}).get("video") or {}).get("url")
                if isinstance(u,list):
                    for x in u:
                        x=(x or "").strip()
                        if x and x not in urls: urls.append(x)
                else:
                    u=(u or "").strip()
                    if u and u not in urls: urls.append(u)
            except Exception:
                pass
        return urls

    def _eps(self,h):
        out=[]
        for href in re.findall(r'href="([^"]*?/archives/\d+/)"[^>]*class="btn btn-primary"',h,re.I):
            if href.startswith('/'):
                href=urljoin(self.host+'/',href.lstrip('/'))
            if href not in out: out.append(href)
        return out

    def _pl(self,urls):
        urls=[u for u in (urls or []) if u]
        if not urls: return ""
        if len(urls)==1: return "播放$"+urls[0]
        return "#".join([f"播放{i}${u}" for i,u in enumerate(urls,1)])

    def _tags(self,h):
        m=re.search(r'<div[^>]*itemprop="keywords"[^>]*class="keywords[^\"]*"[^>]*>([\s\S]*?)</div>',h,re.I)
        if not m: return []
        out=[]
        for href,name in re.findall(r'<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>',m.group(1),re.I):
            name=re.sub(r"\s+"," ",re.sub(r"<[^>]+>","",name)).strip()
            href=(href or "").strip()
            if not name or not href: continue
            if href.startswith('/'):
                href=urljoin(self.host+'/',href.lstrip('/'))
            out.append(f'[a=cr:{json.dumps({"id":href,"name":name},ensure_ascii=False)}/]{name}[/a]')
        return out

    def _intro(self,h):
        i=h.lower().find('class="post-content"')
        s=h[i:] if i>=0 else h
        for p in re.findall(r"<p[^>]*>([\s\S]*?)</p>",s,re.I):
            t=re.sub(r"\s+"," ",re.sub(r"<[^>]+>","",p)).strip()
            if len(t)<20: continue
            if "版权声明" in t or "源于网络采集" in t: continue
            if t.startswith("关键词：") or t.startswith("关键词:"): continue
            return t
        return ""

    def _img(self,url):
        if not url: return ""
        if not url.startswith("http"): url=urljoin(self.host+"/",url.lstrip("/"))
        return f"{self.getProxyUrl()}&type=img&url={self._e64(url)}"

    def _aes(self,data):
        if data.startswith(b"\xff\xd8") or data.startswith(b"\x89PNG") or data[:6] in (b"GIF87a",b"GIF89a") or (data.startswith(b"RIFF") and b"WEBP" in data[8:16]):
            return data
        if len(data)<16: return data
        try: return unpad(AES.new(self._K,AES.MODE_CBC,self._IV).decrypt(data),16)
        except Exception: return data

    def _e64(self,s):
        return b64encode(s.encode()).decode()

    def _d64(self,s):
        return b64decode(s.encode()).decode()
