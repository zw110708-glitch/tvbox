import json,re,sys,requests
from base64 import b64decode,b64encode
from html import unescape
from urllib.parse import quote,urljoin
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
sys.path.append('..')
from base.spider import Spider as BaseSpider

class Spider(BaseSpider):
    def init(self,extend=''):
        cfg=json.loads(extend) if isinstance(extend,str) and extend.strip().startswith('{') else (extend if isinstance(extend,dict) else {})
        self.host=(cfg.get('host') or 'https://heiliao.com').rstrip('/')
        self.proxies = cfg.get('proxies', {})
        self.h={'User-Agent':'Mozilla/5.0','Referer':self.host+'/','Origin':self.host,'X-Requested-With':'XMLHttpRequest'}
    def getName(self): return '黑料网终极瘦身版'
    def manualVideoCheck(self): return False
    def isVideoFormat(self,u): return any((u or '').lower().split('?')[0].endswith(x) for x in('.m3u8','.mp4','.flv','.m4v'))
    def e64(self,s): return b64encode(str(s).encode()).decode()
    def d64(self,s): return b64decode(str(s).encode()).decode()

    def homeContent(self,filter):
        r=requests.get(self.host+'/',headers=self.h,proxies=self.proxies,timeout=15);r.raise_for_status();r.encoding=r.apparent_encoding
        s=BeautifulSoup(r.text,'lxml');a=[];seen=set()
        for x in s.select('a[href]'):
            h=(x.get('href') or '').strip();n=re.sub(r'\s+',' ',x.get_text()).strip()
            if h.startswith('/') and h not in('/','#','/index/search','/aitech/') and re.match(r'^/(?:[a-z0-9_-]+/){1,2}$',h,re.I) and 2<=len(n)<=12 and '登录' not in n and '搜索' not in n and '注册' not in n and n not in ('热门TOP10','收藏TOP10') and h not in seen:
                seen.add(h);a.append({'type_name':n,'type_id':h})
        v=[];seen=set()
        for x in s.select('.video-list .video-item'):
            y=x.select_one('a[href*="/archives/"]');t=x.select_one('.title');h=(y.get('href') if y else '').strip();n=re.sub(r'\s+',' ',t.get_text() if t else '').strip()
            m=re.search(r"loadImg\(this,'([^']+)'\)",str(x)) or re.search(r'data-src=["\']([^"\']+)',str(x)) or re.search(r'src=["\']([^"\']+\.(?:jpg|jpeg|png|webp))',str(x),re.I)
            if h and n and m:
                h=h if h.startswith('http') else urljoin(self.host+'/',h)
                if h in seen: continue
                seen.add(h)
                v.append({'vod_id':h,'vod_name':n,'vod_pic':f"{self.getProxyUrl()}&type=img&url={self.e64((m.group(1) if m.group(1).startswith('http') else urljoin(self.host+'/',unescape(m.group(1)))))}",'vod_remarks':re.sub(r'\s+',' ',' '.join(i.get_text(' ',strip=True) for i in x.select('.date-xxx,.isnewx,.ishot'))).strip(),'style':{'type':'rect','ratio':1.33}})
        return {'class':a[:30],'filters':{},'list':v}

    def homeVideoContent(self): return {'list':self.homeContent(False).get('list',[])}

    def categoryContent(self,tid,pg,filter,extend):
        p=int(pg or 1);u=((tid if str(tid).startswith('http') else urljoin(self.host+'/',tid or '/hlcg/')).rstrip('/')+'/')
        if p>1:u=urljoin(u,f'page/{p}/')
        r=requests.get(u,headers=self.h,proxies=self.proxies,timeout=15);r.raise_for_status();r.encoding=r.apparent_encoding
        s=BeautifulSoup(r.text,'lxml');v=[];seen=set()
        for x in s.select('.video-list .video-item'):
            y=x.select_one('a[href*="/archives/"]');t=x.select_one('.title');h=(y.get('href') if y else '').strip();n=re.sub(r'\s+',' ',t.get_text() if t else '').strip()
            m=re.search(r"loadImg\(this,'([^']+)'\)",str(x)) or re.search(r'data-src=["\']([^"\']+)',str(x)) or re.search(r'src=["\']([^"\']+\.(?:jpg|jpeg|png|webp))',str(x),re.I)
            if h and n and m:
                h=h if h.startswith('http') else urljoin(self.host+'/',h)
                if h in seen: continue
                seen.add(h)
                v.append({'vod_id':h,'vod_name':n,'vod_pic':f"{self.getProxyUrl()}&type=img&url={self.e64((m.group(1) if m.group(1).startswith('http') else urljoin(self.host+'/',unescape(m.group(1)))))}",'vod_remarks':re.sub(r'\s+',' ',' '.join(i.get_text(' ',strip=True) for i in x.select('.date-xxx,.isnewx,.ishot'))).strip(),'style':{'type':'rect','ratio':1.33}})
        return {'list':v,'page':p,'pagecount':p+1 if v else p,'limit':len(v) or 30,'total':p*(len(v) or 30)}

    def detailContent(self,ids):
        u=ids[0] if str(ids[0]).startswith('http') else urljoin(self.host+'/',ids[0])
        r=requests.get(u,headers=self.h,proxies=self.proxies,timeout=15);r.raise_for_status();r.encoding=r.apparent_encoding
        h=r.text;s=BeautifulSoup(h,'lxml');t=re.sub(r'\s+',' ',((s.select_one('h1') or s.title).get_text())).strip().replace('-黑料网','').strip();d=s.select_one('meta[name="description"]');c=re.sub(r'\s+',' ',(d.get('content') if d else '')).strip();tags=[];p=[]
        for x in s.select('.tags a[href]'):
            n=re.sub(r'\s+',' ',x.get_text()).strip();v=(x.get('href') or '').strip()
            if n and v: tags.append(f'[a=cr:{json.dumps({"id":v,"name":n},ensure_ascii=False)}/]{n}[/a]')
        for i,x in enumerate(s.select('.dplayer[config]'),1):
            try:v=json.loads(unescape(x.get('config') or ''))['video'].get('url') or ''
            except:v=''
            if v:
                if not v.startswith('http'): v=urljoin(self.host+'/',v)
                p.append(f'播放 {i}${v}')
        if not p:
            a=s.find_all('a',href=re.compile(r'^/archives/\d+/',re.I),string=re.compile(r'完整爆料'))
            for i,x in enumerate(a,1): p.append(f'播放 {i}$arch:{urljoin(self.host+"/",x.get("href"))}')
            if not p:
                m=re.search(r'https?://[^\s"\']+\.(?:m3u8|mp4)[^\s"\']*',h,re.I)
                if m: p.append(f'播放 1${m.group(0)}')
        c=(('标签: '+' '.join(tags)) if tags else '') + (("\n" if tags and c else '') + c if c else '')
        return {'list':[{'vod_id':u,'vod_name':t,'vod_content':c,'vod_play_from':'黑料网','vod_play_url':'#'.join(p),'vod_video_title':' '.join([x.split('$',1)[0] for x in p])}]}

    def searchContent(self,key,quick,pg='1'):
        p=int(pg or 1)
        r=requests.post(self.host+'/index/search_article',headers=self.h,proxies=self.proxies,timeout=15,data={'word':key,'page':p})
        r.raise_for_status()
        j=r.json().get('data') or {}
        v=[]
        for x in j.get('list') or []:
            h=urljoin(self.host+'/',f"/archives/{x.get('id')}/")
            n=re.sub(r'\s+',' ',x.get('title') or '').strip()
            m=x.get('thumb') or ''
            if h and n:
                v.append({'vod_id':h,'vod_name':n,'vod_pic':f"{self.getProxyUrl()}&type=img&url={self.e64(m if str(m).startswith('http') else urljoin(self.host+'/',str(m)))}" if m else self.host+'/static/pc/img/logo2.png','vod_remarks':'搜索','style':{'type':'rect','ratio':1.33}})
        limit=int(j.get('limit') or len(v) or 10)
        total=int(j.get('count') or len(v))
        pc=int(j.get('total_page') or p)
        calc=(total+limit-1)//limit if limit>0 else p
        if calc>0: pc=calc if pc<=0 else min(pc,calc) if total>0 else pc
        return {'list':v,'page':p,'pagecount':pc,'limit':limit,'total':total}

    def playerContent(self,flag,id,vipFlags):
        if str(id).startswith('arch:'):
            u=str(id)[5:]
            r=requests.get(u,headers=self.h,proxies=self.proxies,timeout=15);r.raise_for_status();r.encoding=r.apparent_encoding
            h=r.text;s=BeautifulSoup(h,'lxml');v=''
            for x in s.select('.dplayer[config]'):
                try:v=json.loads(unescape(x.get('config') or ''))['video'].get('url') or ''
                except:v=''
                if v: break
            if not v:
                m=re.search(r'https?://[^\s"\']+\.(?:m3u8|mp4)[^\s"\']*',h,re.I);v=m.group(0) if m else u
            if v and not v.startswith('http'): v=urljoin(self.host+'/',v)
            id=v
        return {'parse':0 if self.isVideoFormat(id) else 1,'url':f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{id}','header':self.h}

    def localProxy(self,param):
        t=param.get('type');u=self.d64(param.get('url','')) if param.get('url') else ''
        if t=='img':
            d=requests.get(u,headers=self.h,proxies=self.proxies,timeout=15).content
            try:d=unpad(AES.new(b'f5d965df75336270',AES.MODE_CBC,b'97b60394abc2fbe1').decrypt(d),16)
            except:pass
            return [200,'image/jpeg',d]
        if t=='m3u8':
            r=requests.get(u,headers=self.h,proxies=self.proxies,timeout=15);r.raise_for_status();b=r.url.rsplit('/',1)[0]+'/';o=[]
            for x in r.text.splitlines():
                y=x.strip()
                if not y or y.startswith('#'):o.append(x)
                else:o.append(f"{self.getProxyUrl()}&type=ts&url={self.e64(y if y.startswith('http') else ('/'.join(r.url.split('/')[:3])+y if y.startswith('/') else urljoin(b,y)))}")
            return [200,'application/vnd.apple.mpegurl','\n'.join(o)]
        if t=='ts': return [200,'video/mp2t',requests.get(u,headers=self.h,proxies=self.proxies,timeout=15).content]
        return [404,'text/plain',b'']
