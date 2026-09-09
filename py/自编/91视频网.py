import json,re,sys,time
from base64 import b64decode,b64encode
from concurrent.futures import ThreadPoolExecutor,as_completed
from html import unescape
from urllib.parse import quote,urljoin,urlparse

import requests
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    host='' 
    domain_html_url='https://91sp001.com/'
    play_body='data=gLP27%2BwQby%2F9ENFBpi%2FEnm%2BqmJj7Rchmv6IP6puzut7b2jhMyeQ7e9YPPbxaO3MSBYS6DH35oZXF%2BgiPdvLYgEz0lbFmtlQ0YexEk393u%2FxtaryWcJb2bCEaVTfYN0d6lD0DASux1ccAepD9K0AGE6f0wk%2FNTZVHWtEW3%2FVMv2oRoPCkkhLiZ9k72sGNxT8x6nY2I%2Fpfmuo%2B1sb2JZygWrWJZde%2FU5TeTnW0Ifb866Uzx58aZYwanP%2F7DRqkMZkROWGPO4PS7mgntzWd2J2A6kxujXMv96W8a9saG16vGWX36mZNksgY16ZVI3jYo1yMpXNInV0SFzEri8lD2Q99%2FDXzaJHwnahwLAR0FEgXRZYUkAFKl8pQM8Lp%2FzaP4ifRs8k8kKSNSKVmq9R6bOF7wIzMf6LLABJZPtPgE2FiLYSDdamXIQq5E0NA9wEEgKH2IiXmY%2FgJc%2BwPS%2FEN7sQEoWRMyenbtqg4f6M2MSgRxA3SQKbV4ku%2BQ2DwPeJd0R1T0FpNXigQZJP1p0Ieqtgh6P272RZI4E3j5p7RxJ3B7%2FDS592FJlfMLoFfOc%2BNH0XyeQunlR4GVQMX8Eo%2B6cfVqc68A1btek5bb28hFsSWHk9I4mgRNBsG5b4bExx4lLUERZdZNeDutW7jx%2F%2BZ5uuJLpW%2F3MzXqBNO3qStpbJYX3REFOqsbol5RNFVK4fqpwerdrD%2FH8MlaiPxugkc5Jh%2FSGNukCtUR0Ux0WLqrXnBzLmUtHUnGzDmiSfiV%2FZPCA2RqHIOt1vs0fDOA0XNqmpmH7gru4SD7MuisZ4BYPCCEsXS%2FpY%2FgYvPdKRTtkLMqFMuD89y3uAwX0U6L2dQ5GGJR6ejQBVR4jzq3B6S157cp2NIxVeabfRg7FrsY5vh%2BMZHw9069mp7ItrQu3LL1GHw2TMjWBMITQf%2B45IM302IjfD8vaCM4vVzBrVxc4xwujRMqpvFxaP%2BaRO9hXotFWXnszzGkrV9bVas7ibJNtjDoaK91RvGbCYZo2FO11RZrzJjzkH%2BaP69fK0dT13Hvk900TRokgCy9VIpFfYfWbdAMquMhiahqA4lxsyrtlnyStRVWp9f6TuWxxii80q9inaclsuaKG%2Fw%2Bvf7YaoWD1vMplxWo9eabchi%2Fyi73yimV%2FUZnw87T0ToeKzlKjQKfYRev7N54XDCUi22616QdKtnRz%2FEJ7G5PnlDs0ipnood8MnMrvUV6B7vkL3Dcyi63Tz1TCcWFtHWV%2Fqc59cyEzcAz3pdcTzjmzBNnZQnM47NgZ2VYq1cMcArRqsxBfGrI%2BomKMYHP4E2aq4gfFwsZPklhWm5e3KmF2%2FpaYtX3XlTvghd7zud3dOqCnvOO08mY6Se5MFg83wgUAnhTrK94d5pg7vs0vH0WyJwyxfRqDRprXmWCWGELK31e2EU7Kgg19sDFpfzAqyiQGwaNr2jAZ1adOT6%2BnJOzG%2BP%2FqobhCxVuSW6p4kG3jECxIjAkjcG6q2FQJOOcEey4Dm3xnEyzFbfpruX7F3%2B3Jwe1ZALZgs3tmFs%2B6xtStN75nACi3lI7zZYx9ctZ2c6h36FUozyKBs86QwZeHfE7vuBo%2B8R7wadObx8FhjQ6RCNeEdPeptPRIJohmYeLGinhk0Um1erGspBnYzI2GWP%2BqevbQCqT7V2ew4rc4WXejtQ9CQpJgzQxupbyg%3D%3D&timestamp=1778598518575&_ver=v0&sign=101b7d093f93476d8d5a8d052fb005ea'
    headers={
        'User-Agent':'Mozilla/5.0',
        'Referer':'/',
        'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Encoding':'gzip, deflate, br'
    }

    def init(self,extend=''):
        self.proxies={}
        if extend:
            try:
                c=json.loads(extend)
                self.domain_html_url=c.get('domain_html_url',self.domain_html_url)
                self.play_body=c.get('play_body',self.play_body)
                self.proxies=c.get('proxies',{}) or {}
            except Exception:
                pass
        self.s=requests.Session()
        self.host=self._select_host().rstrip('/')
        self.headers['Referer']=self.host+'/'

    def getName(self):
        return '91视频'

    def isVideoFormat(self,url):
        return url and ('.m3u8' in url or '.mp4' in url)

    def manualVideoCheck(self):
        return False

    def _get(self,url,**kw):
        r=self.s.get(url,headers=kw.pop('headers',self.headers),proxies=self.proxies,timeout=kw.pop('timeout',12),**kw)
        r.encoding='utf-8'
        return r

    def fetch(self,url):
        return self._get(urljoin(self.host,url)).text

    def _aff(self,n):
        s='abcdefghjkmnpqrstuvwxy23456789'
        if n<0:
            return ''
        o=''
        while n>29:
            n,k=divmod(n,30)
            n-=1
            o=s[k]+o
        return s[n]+o

    def _domain_candidates(self,html):
        m=re.search(r"Base64\.decode\('(.+?)'\)\);",html,re.S)
        if m:
            html=b64decode(re.sub(r'[^A-Za-z0-9+/=]','',m.group(1))).decode('utf-8','ignore')
        m=re.search(r'domains\s*=\s*\[(.*?)\]',html,re.S)
        ds=re.findall(r"['\"]([^'\"]+)['\"]",m.group(1)) if m else []
        p=self._aff(int(time.time()*1000)//7200000)+'z1.'
        out=[]
        for d in ds:
            d=d.strip().rstrip('/')
            out.append(d if d.startswith('http') else 'https://'+p+d)
        return out

    def _select_host(self):
        r=requests.get(self.domain_html_url,headers={'User-Agent':'Mozilla/5.0'},proxies=self.proxies or None,timeout=10)
        r.encoding='utf-8'
        hs=self._domain_candidates(r.text)[:12]
        def ok(h):
            r=self._get(h+'/',headers={'User-Agent':'Mozilla/5.0','Referer':h+'/'},timeout=4)
            return h if r.status_code==200 and '/archives/' in r.text and 'post-card-title' in r.text else ''
        with ThreadPoolExecutor(max_workers=min(8,len(hs) or 1)) as ex:
            fs=[ex.submit(ok,h) for h in hs]
            for f in as_completed(fs):
                h=f.result()
                if h:
                    for x in fs:
                        x.cancel()
                    return h
        raise Exception('no available domain')

    def _img(self,img):
        u=''
        if img:
            u=img.attr('z-image-loader-url') or img.attr('x-image-loader-url') or img.attr('src') or ''
        return f'{self.getProxyUrl()}&type=img&url={b64encode(u.encode()).decode()}' if u and self._need_img_dec(u) else u

    img=_img

    def _need_img_dec(self,u):
        return any(x in u for x in ('/new/','/xiao/','/upload/upload/','/upload_01/','/uploads/'))

    need_img_dec=_need_img_dec

    def _items(self,html):
        d=pq(html)
        out,seen=[],set()
        for it in d('article').items():
            a=it('a[href*="/archives/"]').eq(0)
            href=a.attr('href') or ''
            if not href or href in seen:
                continue
            seen.add(href)
            name=it('.post-card-title').text().strip()
            if not name or any(x in name for x in ('回家的路','APP','官方','福利','广告','商务合作')):
                continue
            m=re.search(r'\d{4}-\d{2}-\d{2}',it('.post-card-info').text())
            out.append({'vod_id':urljoin(self.host,href),'vod_name':name,'vod_pic':self._img(it('img').eq(0)),'vod_remarks':m.group(0) if m else ''})
        return out

    def homeContent(self,filter):
        html=self.fetch('/')
        d=pq(html)
        cs=[]
        for a in d('#navbar a.nav-link[href^="/category/"]').items():
            href=(a.attr('href') or '').strip()
            slug=href.strip('/').split('/')[-1]
            name=a.text().strip()
            if slug and name and not any(x['type_id']==slug for x in cs):
                cs.append({'type_id':slug,'type_name':name})
        return {'class':cs,'filters':{},'list':self._items(html)}

    def homeVideoContent(self):
        return {'list':self.homeContent(False).get('list',[])}

    def _list_path(self,tid,pg):
        tid=(tid or '').strip()
        path=urlparse(tid).path if tid.startswith('http') else tid if tid.startswith('/') else f"/category/{tid.strip('/').split('/')[-1]}/"
        if not path.endswith('/'):
            path+='/'
        if pg>1:
            path+=f'{pg}/'
        return path

    def categoryContent(self,tid,pg,filter,extend):
        pg=int(pg or 1)
        html=self.fetch(self._list_path(tid,pg))
        return {'list':self._items(html),'page':pg,'pagecount':9999,'limit':20,'total':999999}

    def searchContent(self,key,quick,pg='1'):
        pg=int(pg or 1)
        html=self.fetch(f"/search/{quote(key)}/"+(f'{pg}/' if pg>1 else ''))
        return {'list':self._items(html),'page':pg,'pagecount':9999,'limit':20,'total':999999}

    def detailContent(self,ids):
        url=ids[0]
        if not url.startswith('http'):
            url=urljoin(self.host+'/',url.lstrip('/'))
        doc=BeautifulSoup(self.fetch(url),'lxml')
        t=doc.select_one('h1.post-title, h1.entry-title, meta[property="og:title"]')
        title=t.get('content') if getattr(t,'name',None)=='meta' else t.get_text(strip=True) if t else ''
        desc=(doc.select_one('meta[name="description"]') or {}).get('content','')

        tags=[]
        for a in doc.select('div.keywords a'):
            n=a.get_text(strip=True)
            h=a.get('href')
            if n and h:
                tags.append(f"[a=cr:{json.dumps({'id':h,'name':n},ensure_ascii=False)}/]{n}[/a]")
        vod_content=('标签: '+' '.join(tags)+('\n' if desc else '')+desc) if tags else desc

        pic=''
        img=doc.select_one('.post-card img, article img, .art-poster img')
        if img:
            pic=img.get('z-image-loader-url') or img.get('x-image-loader-url') or img.get('src') or ''
            if pic and self._need_img_dec(pic):
                pic=f'{self.getProxyUrl()}&type=img&url={b64encode(pic.encode()).decode()}'

        plays,seen=[],set()
        m=re.search(r'/archives/(\d+)/',url)
        cid=m.group(1) if m else ''
        for i,p in enumerate(doc.select('.dplayer[data-config]'),1):
            cfg=json.loads(unescape(p.get('data-config')))
            m=re.search(r'cid=(\d+).*?idx=(\d+)',cfg.get('url',''))
            pid=f"{m.group(1)}_{m.group(2)}" if m else f"{cid}_{i-1}"
            if pid in seen:
                continue
            seen.add(pid)
            plays.append(f'第{i}集${pid}')

        if not plays:
            for i,a in enumerate(doc.select('.post-content a[href*="/archives/"]'),1):
                if '点击观看' not in a.get_text(' ',strip=True):
                    continue
                u=urljoin(self.host+'/',(a.get('href') or '').lstrip('/'))
                if u!=url and u not in seen:
                    seen.add(u)
                    plays.append(f'TOP{i}${u}')

        for u in re.findall(r'https?://[^\'"<>]+?\.(?:m3u8|mp4)[^\'"<>]*',str(doc)):
            if u not in seen:
                seen.add(u)
                plays.append(f'直链${u}')

        return {'list':[{'vod_id':url,'vod_name':title,'vod_pic':pic,'vod_content':vod_content,'vod_play_from':'线路','vod_play_url':'#'.join(plays)}]}

    def playerContent(self,flag,id,vipFlags):
        url=id
        if self.isVideoFormat(url):
            return {'parse':0,'url':url,'header':self.headers}

        if '/archives/' in url:
            doc=BeautifulSoup(self.fetch(url),'lxml')
            p=doc.select_one('.dplayer[data-config]')
            if p:
                m=re.search(r'cid=(\d+).*?idx=(\d+)',json.loads(unescape(p.get('data-config'))).get('url',''))
                if m:
                    url=f"{m.group(1)}_{m.group(2)}"

        if re.fullmatch(r'\d+_\d+',url):
            cid,idx=url.split('_')
            api=f'{self.host}/action/player/get_play_url?cid={cid}&idx={idx}'
            h={**self.headers,**{
                'Referer':f'{self.host}/archives/{cid}/',
                'Origin':self.host,
                'Accept':'application/json, text/javascript, */*; q=0.01',
                'X-Requested-With':'XMLHttpRequest',
                'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'
            }}
            d=self.s.post(api,data=self.play_body,headers=h,proxies=self.proxies,timeout=8).json().get('data')
            if isinstance(d,str):
                url=self._dec_play(d) or d
            elif isinstance(d,dict):
                url=d.get('url') or d.get('play_url') or d.get('src') or self._dec_play(d.get('data','')) or api
            elif isinstance(d,list) and d:
                v=d[0].get('url') if isinstance(d[0],dict) else d[0]
                url=self._dec_play(v) or v
            else:
                url=api

        return {'parse':0 if self.isVideoFormat(url) else 1,'url':f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{url}','header':self.headers}

    def _dec_play(self,text):
        if not text or text.startswith('http'):
            return text
        try:
            return unpad(AES.new(b'2acf7e91e9864673',AES.MODE_CBC,b'1c29882d3ddfcfd6').decrypt(b64decode(text)),16).decode()
        except Exception:
            return ''

    dec_play=_dec_play

    def localProxy(self,param):
        if param.get('type')!='img':
            return [404,'text/plain',b'']
        try:
            u=b64decode(param.get('url','')).decode()
            raw=self.s.get(u,headers=self.headers,proxies=self.proxies,timeout=12).content
            img=self.aesimg(raw)
            ct='image/png' if img.startswith(b'\x89PNG') else 'image/jpeg' if img.startswith(b'\xff\xd8') else 'image/gif' if img.startswith(b'GIF') else 'application/octet-stream'
            return [200,ct,img]
        except Exception:
            return [404,'text/plain',b'']

    def _aesimg(self,data):
        try:
            return unpad(AES.new(b'f5d965df75336270',AES.MODE_CBC,b'97b60394abc2fbe1').decrypt(data),16)
        except Exception:
            return data

    aesimg=_aesimg
