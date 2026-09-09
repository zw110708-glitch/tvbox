var rule = {
    title: '[密] 爱看伦理',
    host: 'https://www.yklunli.top',
    url: 'https://www.yklunli.top/fyclass/pfypage.html',
    homeUrl: '/',
    searchUrl: 'https://www.yklunli.top/vod-search-wd-**-p-fypage.html',
    searchable: 2,
    quickSearch: 1,
    filterable: 1,
    limit: 30,
    编码: 'utf-8',
    timeout: 5000,
    headers: {
      'User-Agent': 'Mozilla/5.0 (Linux; Android 15; RMX3770 Build/AP3A.240617.008) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/130.0.6723.58 Mobile Safari/537.36'
    
    },
    
        class_name: '韩国伦理&日本伦理&欧美伦理&香港伦理',
    //静态分类值
    class_url: 'hanguolunli&ribenlunli&oumeilunli&xiangganglunli',
    
 //   图片来源: '@Referer=https://author.xotwzad.org/cn@User-Agent=Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36',
    
    //是否启用辅助嗅探: 1,0
    sniffer: 0,
    // 辅助嗅探规则
    isVideo: 'http((?!http).){26,}\\.(m3u8|mp4|flv|avi|mkv|wmv|mpg|mpeg|mov|ts|3gp|rm|rmvb|asf|m4a|mp3|wma)',
    play_parse: true,
    lazy: $js.toString(() => {
        input = {
            parse: 1,
            url: input,
            js: 'document.querySelector("#playleft iframe").contentWindow.document.querySelector("#start").click();'
        };
    }),
    
    //播放地址通用解析
    lazy: $js.toString(() => {
let kcode = JSON.parse(fetch(input).split('aaaa=')[1].split('<')[0]);
let kurl = decodeURIComponent(kcode.url);
if (/\.(m3u8|mp4)/.test(kurl)) {
    input = { jx: 0, parse: 0, url: kurl, header: {'User-Agent': MOBILE_UA, 'Referer': getHome(kurl)} }
} else {
    input = { jx: 0, parse: 1, url: input }
}
}),

    double: false,
    
    推荐: '*', 

   一级: '.col-xs-4;img&&alt;img&&data-original;.continu&&Text;a&&href',
   
   
   二级: {
        title: 'h2&&Text',
        img: 'img&&data-original',
        //desc: '.data:contains(类型)&&Text;.data:contains(年份)&&Text;.data:contains(地区)&&Text;.data:contains(导演)&&Text;.data:contains(主演)&&Text',
        content: '.vod-nav-content&&Text',
        tabs: '.nav-tabs-play li',
        tab_text: 'Text',
        lists: '.ff-playurl-line',
        list_text: 'a&&Text',
        list_url: 'a&&href'
    
    },
   
   
   
  /*二级: $js.toString(() => {
    let html = request(input);
    VOD = {vod_id: input};
    
    // 基本信息
    VOD.vod_name = pdfh(html, 'img&&alt');
    VOD.vod_pic = pd(html, 'img&&data-original', input);
    vod_content: pdfh(html, '.vod-nav-content&&Text');
    
    // 播放来源 - 从导航标签中提取
    VOD.vod_play_from = pdfa(html, '.nav-tabs-play li').map(it => 
        pdfh(it, 'a&&Text')
    ).join('$$$');
    
    // 播放列表 - 从播放链接中提取
    VOD.vod_play_url = pdfa(html, '.ff-playurl-line').map(rp => 
        pdfa(rp, 'a').map(it => 
            pdfh(it, 'a&&Text') + '$' + pd(it, 'a&&href', input)
        ).join('#')
    ).join('$$$');
}),*/

   
    //二级: '*',
    搜索: '*',
}

