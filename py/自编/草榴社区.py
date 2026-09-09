import json,re,hashlib,time
from base64 import b64decode,b64encode
from urllib.parse import urljoin,quote,urlparse,unquote
import requests
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad,unpad

from base.spider import Spider as BaseSpider

_img_cache={}

class Spider(BaseSpider):
    def init(self,extend=""):
        try:cfg=json.loads(extend) if isinstance(extend,str) else (extend or {})
        except:cfg={}
        self.plp = cfg.get('plp', '')
        self.proxy=cfg.get('proxy') or {}
        self.host=(cfg.get('host') or 'https://caoliu4.com').strip().rstrip('/')
        ua='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        self.headers={'User-Agent':ua,'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8','Accept-Language':'zh-CN,zh;q=0.9','Connection':'keep-alive','Cache-Control':'no-cache','Origin':self.host,'Referer':self.host+'/'}
        self.session=requests.Session()
        api_domain=cfg.get('api_domain') or 'rpeudskb.xyz'
        self.api_bases=[f"https://apiv{i}.{api_domain}/api.php" for i in (1,2,3)]
        k="50_97_99_102_55_101_57_49_101_57_56_54_52_54_55_51";v="49_99_50_57_56_56_50_100_51_100_100_102_99_102_100_54";s="53_53_56_57_100_52_49_102_57_50_97_53_57_55_100_48_49_54_98_48_51_55_97_99_51_55_100_98_50_52_51_100"
        self._api_key=self._cc(k).encode();self._api_iv=self._cc(v).encode();self._api_sign_key=self._cc(s)

    def destroy(self):
        _img_cache.clear()
        try:self.session.close()
        except:pass

    def getName(self):
        return "草流社区"

    def manualVideoCheck(self):
        return False

    def _enc(self,r):
        try:r.encoding=r.apparent_encoding or r.encoding or 'utf-8'
        except:r.encoding='utf-8'
        return r

    def _soup(self,html):
        return BeautifulSoup(html,'lxml')

    def homeContent(self,filter):
        try:
            r=self.session.get(self.host+'/',headers=self.headers,proxies=self.proxy,timeout=12)
            if r.status_code!=200:return {'class':[],'filters':{},'list':[]}
            soup=self._soup(self._enc(r).text)
            seen=set();classes=[]
            for a in soup.select('#collapseTag1Stop .tags a'):
                n=(a.get_text(strip=True) or '').strip();h=(a.get('href') or '').strip()
                if not n or not h or h=='#' or 'javascript' in h:continue
                tid=h if h.startswith('/') else urljoin(self.host+'/',h).replace(self.host,'')
                if tid in seen:continue
                seen.add(tid);classes.append({'type_name':n,'type_id':tid})
                if len(classes)>=30:break
            return {'class':classes,'filters':{},'list':self.getlist(soup)}
        except:
            return {'class':[],'filters':{},'list':[]}

    def homeVideoContent(self):
        return {'list':self.homeContent(None).get('list',[])}

    def categoryContent(self,tid,pg,filter,extend):
        try:pg=int(pg or 1)
        except:pg=1
        try:
            if (tid or '').startswith('http'):
                p=urlparse(tid);tid=p.path+(('?' + p.query) if p.query else '')
            tid=tid or '/'
            if tid.startswith('/author/'):
                m=re.search(r'^/author/(\d+)/',tid);uid=int(m.group(1)) if m else 0
                if not uid:return {'list':[],'page':pg,'pagecount':1,'limit':20,'total':0}
                data=self._api_post('/api/tcontent/author_contents',{'sort':'new','uid':uid,'page':pg,'limit':20})
                return self._api_list_to_result(data,pg)
            if tid.startswith('/tag/'):tid=self._norm_tag_path(tid)
            base=(self.host if tid=='/' else f"{self.host}{tid.rstrip('/')}/")
            if tid=='/':urls=[f"{self.host}/page/{pg}/" if pg>1 else f"{self.host}/"]
            elif tid.startswith('/tag/'):urls=[f"{base}{pg}/" if pg>1 else base]
            else:urls=[base] if pg<=1 else [f"{base}page/{pg}/",f"{base}{pg}/"]
            r=None
            for u in urls:
                r=self.session.get(u,headers=self.headers,proxies=self.proxy,timeout=12)
                if r.status_code==200 and (r.text or '').strip():break
            if not r or r.status_code!=200:return {'list':[],'page':pg,'pagecount':9999,'limit':90,'total':0}
            return {'list':self.getlist(self._soup(self._enc(r).text)),'page':pg,'pagecount':9999,'limit':90,'total':999999}
        except:
            return {'list':[],'page':pg,'pagecount':9999,'limit':90,'total':0}

    def detailContent(self,ids):
        try:
            url=ids[0] if ids[0].startswith('http') else f"{self.host}{ids[0]}"
            r=self.session.get(url,headers=self.headers,proxies=self.proxy,timeout=15,allow_redirects=True)
            soup=self._soup(self._enc(r).text)
            seen=set();plist=[]
            def add(n,u):
                if not u:return
                u=u.replace('&amp;','&').strip()
                if not u.startswith('http'):u=urljoin(self.host,u)
                if u in seen:return
                seen.add(u);plist.append(f"{n}${u}")
            for i,dp in enumerate(soup.select('.dplayer'),1):
                cfg=dp.get('data-config') or ''
                if not cfg:continue
                try:j=json.loads(cfg)
                except:
                    try:j=json.loads(cfg.replace('&quot;','"'))
                    except:continue
                u=(j.get('url') or '') or ((j.get('video') or {}).get('url') if isinstance(j.get('video'),dict) else '')
                if not u:continue
                h2=None
                for sib in dp.find_all_previous('h2',limit=1):h2=sib
                name=(h2.get_text(strip=True) if h2 else '') or f"播放{i}"
                add(name,u)
            if not plist:
                v=(soup.select_one('video.dplayer-video') or {}).get('src') if soup.select_one('video.dplayer-video') else ''
                if v:add('播放1',v)
            h1=soup.select_one('h1');title=(h1.get_text(strip=True) if h1 else '')
            if not title:
                t=soup.title.get_text(strip=True) if soup.title else ''
                title=(t.split('|')[0].strip() if t else '')
            author_a=soup.select_one('a[href^="/author/"]')
            author_n=(author_a.get_text(strip=True) if author_a else '')
            author_h=(author_a.get('href') if author_a else '')
            director=''
            if author_n and author_h:
                au=urljoin(self.host+'/',author_h.lstrip('/'))
                director=f"[a=cr:{json.dumps({'id':au,'name':author_n},ensure_ascii=False,separators=(',',':'))}/]{author_n}[/a]"
            tags=[]
            for a in soup.select('.tags-group2 a[href^="/tag/"]'):
                h=(a.get('href') or '').strip();n=(a.get_text(strip=True) or '').strip()
                if not h or not n:continue
                tu=urljoin(self.host+'/',self._norm_tag_path(h).lstrip('/'))
                tags.append(f"[a=cr:{json.dumps({'id':tu,'name':n},ensure_ascii=False,separators=(',',':'))}/]{n}[/a]")
            meta=soup.select_one('meta[name="description"]');intro=(meta.get('content','').strip() if meta else '')
            if not intro:
                p=soup.select_one('article p');intro=(p.get_text(strip=True) if p else '')
            content=('标签: '+' '.join(tags)+'\n'+intro).strip() if tags else (intro or title)
            play_url='#'.join(plist) if plist else '未找到视频源$null'
            return {'list':[{'vod_play_from':'直链','vod_play_url':play_url,'vod_content':content,'vod_director':director,'vod_name':title}]}
        except:
            return {'list':[{'vod_play_from':'直链','vod_play_url':'获取失败$null'}]}

    def searchContent(self,key,quick,pg="1"):
        try:pg=int(pg or 1)
        except:pg=1
        word=(key or '').strip()
        if not word:return {'list':[],'page':pg,'pagecount':1,'limit':20,'total':0}
        return self._api_list_to_result(self._api_post('/api/tcontent/searchContents',{'word':word,'page':pg,'limit':20}),pg)

    def _api_list_to_result(self,data,pg):
        lst=(data.get('list') or []) if isinstance(data,dict) else []
        total=int(data.get('total') or 0) if isinstance(data,dict) else 0
        out=[]
        for it in lst:
            slug=str(it.get('slug') or it.get('cid') or '').strip();title=(it.get('title') or '').strip()
            if not slug or not title:continue
            imgs=it.get('images') or []
            pic=(imgs[0] if isinstance(imgs,list) and imgs else '')
            if pic and not str(pic).startswith('http'):pic=urljoin(self.host+'/',str(pic).lstrip('/'))
            out.append({'vod_id':urljoin(self.host+'/',f"archives/{slug}/"),'vod_name':title,'vod_pic':self._proc_url(str(pic)) if pic else '','vod_remarks':'','style':{'type':'rect','ratio':1.33}})
        pc=max(1,(total+19)//20) if total else 9999
        return {'list':out,'page':pg,'pagecount':pc,'limit':20,'total':total or 999999}

    def playerContent(self,flag,id,vipFlags):
        u=(id or '').strip()
        return {'parse':0,'url': self.plp + u if u and u.lower() not in ('null','none','获取失败') else '','header':self.headers}

    def localProxy(self,param):
        try:
            t=param.get('type');u=param.get('url')
            if t=='cache':
                k=param.get('key');c=_img_cache.get(k)
                return [200,'image/jpeg',c] if c else [404,'text/plain',b'']
            if t=='img':
                real=self.d64(u) if (u and not u.startswith('http')) else u
                res=self.session.get(real,headers=self.headers,proxies=self.proxy,timeout=12)
                c=self.aesimg(res.content)
                ct='image/png' if c.startswith(b'\x89PNG') else ('image/gif' if c.startswith(b'GIF8') else 'image/jpeg')
                return [200,ct,c]
            return self.m3Proxy(u) if t=='m3u8' else self.tsProxy(u)
        except:
            return [404,'text/plain',b'']

    def proxy(self,data,type='m3u8'):
        return f"{self.getProxyUrl()}&url={self.e64(data)}&type={type}" if data and self.proxy is not None else data

    def m3Proxy(self,url):
        res=self.session.get(self.d64(url),headers=self.headers,proxies=self.proxy)
        data=self._enc(res).text;base=res.url.rsplit('/',1)[0]
        out=[]
        for line in data.split('\n'):
            if '#EXT' in line or not line.strip():out.append(line);continue
            if not line.startswith('http'):line=f"{base}/{line}"
            out.append(self.proxy(line,'ts'))
        return [200,'application/vnd.apple.mpegurl','\n'.join(out)]

    def tsProxy(self,url):
        return [200,'video/mp2t',self.session.get(self.d64(url),headers=self.headers,proxies=self.proxy).content]

    def e64(self,x):
        return b64encode(str(x).encode()).decode()

    def d64(self,x):
        return b64decode(str(x).encode()).decode()

    @staticmethod
    def _cc(s):
        return ''.join(chr(int(x)) for x in (s or '').split('_') if x.isdigit())

    def _api_encrypt(self,obj):
        cipher=AES.new(self._api_key,AES.MODE_CBC,self._api_iv)
        return b64encode(cipher.encrypt(pad(json.dumps(obj,ensure_ascii=False,separators=(',',':')).encode(),16))).decode()

    def _api_decrypt(self,b64):
        cipher=AES.new(self._api_key,AES.MODE_CBC,self._api_iv)
        return json.loads(unpad(cipher.decrypt(b64decode(b64)),16).decode())

    def _api_sign(self,client,data_b64,ts):
        return hashlib.md5(hashlib.sha256((f"client={client}&data={data_b64}&timestamp={ts}"+self._api_sign_key).encode()).hexdigest().encode()).hexdigest()

    def _api_post(self,path,params):
        payload={'bundleId':'com.pwa.Chaguaner','version':'3.3.1','oauth_id':'','oauth_type':'web','language':'zh','via':'pch','token':''}
        payload.update(params or {})
        client='ios';ts=int(time.time());enc=self._api_encrypt(payload);sign=self._api_sign(client,enc,ts)
        form=f"client={client}&data={quote(enc,safe='')}&sign={sign}&timestamp={ts}"
        for base in self.api_bases:
            try:
                r=self.session.post(base.rstrip('/')+(path if path.startswith('/') else '/'+path),data=form,headers={'User-Agent':self.headers['User-Agent'],'Content-Type':'application/x-www-form-urlencoded'},proxies=self.proxy,timeout=20)
                r.raise_for_status()
                dec=self._api_decrypt(r.json().get('data') or '')
                if dec.get('status')==1:return dec.get('data') or {}
            except:pass
        return {}

    def getlist(self,soup):
        out=[];seen=set()
        for row in soup.select('.xqbj-list .xqbj-list-rows'):
            a=row.select_one('a[href^="/archives/"]')
            href=(a.get('href') if a else '') or ''
            title=(a.get('title') if a else '') or ''
            href=href.strip();title=title.strip()
            if not href or not title:continue
            pic=self.getimg(row)
            if not pic:continue
            vid=urljoin(self.host+'/',href)
            if vid in seen:continue
            seen.add(vid)
            t=row.find('time');remark=(t.get_text(strip=True) if t else '')
            out.append({'vod_id':vid,'vod_name':title,'vod_pic':pic,'vod_remarks':remark,'style':{'type':'rect','ratio':1.33}})
        return out

    def getimg(self,row):
        img=row.select_one('img[z-image-loader-url]')
        u=(img.get('z-image-loader-url') if img else '') or ''
        u=u.strip()
        if u.startswith('`') and u.endswith('`'):u=u[1:-1].strip()
        return self._proc_url(u)

    def _proc_url(self,url):
        if not url:return ''
        url=url.strip(' \t\r\n\"\'')
        if url.startswith('data:'):
            try:
                raw=b64decode(url.split(',',1)[1]);raw=self.aesimg(raw)
                k=hashlib.md5(raw).hexdigest();_img_cache[k]=raw
                return f"{self.getProxyUrl()}&type=cache&key={k}"
            except:
                return ''
        if not url.startswith('http'):url=urljoin(self.host+'/',url)
        return f"{self.getProxyUrl()}&url={self.e64(url)}&type=img"

    def _norm_tag_path(self,s):
        s=(s or '').strip()
        if s.startswith('http'):
            try:s=urlparse(s).path
            except:pass
        if not s.startswith('/tag/'):return s
        slug=s[len('/tag/'):].strip('/')
        try:slug=unquote(slug)
        except:pass
        if not re.search(r'%[0-9A-Fa-f]{2}',slug):slug=quote(slug,safe='')
        return f"/tag/{slug}/"

    def aesimg(self,data):
        if not data or len(data)<16 or data.startswith((b'\xff\xd8',b'\x89PNG',b'GIF8')):return data
        for k,v in ((b'f5d965df75336270',b'97b60394abc2fbe1'),(b'75336270f5d965df',b'abc2fbe197b60394')):
            for mode in (AES.MODE_CBC,AES.MODE_ECB):
                try:
                    dec=unpad(AES.new(k,mode,v).decrypt(data),16) if mode==AES.MODE_CBC else unpad(AES.new(k,mode).decrypt(data),16)
                    if dec.startswith((b'\xff\xd8',b'\x89PNG',b'GIF8')):return dec
                except:pass
        return data
