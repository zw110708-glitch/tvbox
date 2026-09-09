// 定义网站主域名（根据源码修正）
let host = 'https://madou.com/';
// 请求头配置，模拟安卓移动端浏览器请求
let headers = {
  "User-Agent": "Mozilla/5.0 (Linux; Android 13; M2102J2SC Build/TKQ1.221114.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/143.0.7499.3 Mobile Safari/537.36"
};

/**
 * 初始化函数（预留）
 */
async function init(cfg) {}

/**
 * 获取首页分类列表（根据实际网站结构修正）
 */
async function home(filter) {
  return JSON.stringify({
    "class": [
      // 麻豆AV主分类及子分类
      { "type_id": "/topic/0/13678/", "type_name": "精选好片专区" },
      { "type_id": "/topic/0/13679/", "type_name": "麻豆出品-MSD系列" },
      { "type_id": "/topic/0/13681/", "type_name": "情趣诱惑-黑丝美腿" },
      { "type_id": "/topic/0/13680/", "type_name": "群交盛宴-多人系列" },
      { "type_id": "/topic/0/13682/", "type_name": "淫欲中国风-后宫淫乱史" },
      { "type_id": "/topic/0/13683/", "type_name": "SM调教-性癖患者" },
      
      // 传媒片商主分类及子分类
      { "type_id": "/topic/0/13687/", "type_name": "爱豆传媒" },
      { "type_id": "/topic/0/13685/", "type_name": "皇家华人" },
      { "type_id": "/topic/0/13686/", "type_name": "星空传媒" },
      { "type_id": "/topic/0/13688/", "type_name": "精东影业" },
      { "type_id": "/topic/0/13689/", "type_name": "色控" },
      { "type_id": "/topic/0/13931/", "type_name": "天美传媒" },
      { "type_id": "/topic/0/13711/", "type_name": "蜜桃传媒" },
      { "type_id": "/topic/0/13690/", "type_name": "兔子先生" },
      { "type_id": "/topic/0/13712/", "type_name": "果冻传媒" },
      
      // 网黄大神主分类及子分类
      { "type_id": "/topic/0/13713/", "type_name": "极品福利姬&网黄合集" },
      { "type_id": "/topic/0/13714/", "type_name": "真实乱伦大神合集" },
      { "type_id": "/topic/0/13715/", "type_name": "探花大神-大神约炮实录" },
      { "type_id": "/topic/0/13717/", "type_name": "极品双马尾-反差萝莉" },
      
      // 日本AV主分类及子分类
      { "type_id": "/topic/0/13719/", "type_name": "禁忌乱伦" },
      { "type_id": "/topic/0/13721/", "type_name": "淫妻绿帽NTR" },
      { "type_id": "/topic/0/13722/", "type_name": "制服OL专区" },
      { "type_id": "/topic/0/13724/", "type_name": "极品巨乳女郎" },
      { "type_id": "/topic/0/13720/", "type_name": "FC2极品素人" },
      
      // 欧美AV主分类及子分类
      { "type_id": "/topic/0/13726/", "type_name": "中文字幕" },
      { "type_id": "/topic/0/13728/", "type_name": "捷克搭讪" },
      { "type_id": "/topic/0/13729/", "type_name": "欧美黑白配" },
      { "type_id": "/topic/0/13730/", "type_name": "欧美网黄" }
    ]
  });
}

/**
 * 获取分类下的视频列表（根据源码修正URL格式）
 */
async function category(tid, pg, filter, extend) {
  let p = pg || 1;
  // 根据源码修正URL格式
  let url;
  
  if (tid.startsWith('/topic/')) {
    // topic类型的分类页格式：/topic/0/13678/0/页码/
    if (p === 1) {
      url = host + tid.replace(/\/$/, '');
    } else {
      url = host + tid.replace(/\/$/, '') + '/0/' + p;
    }
  } else if (tid.startsWith('/category/')) {
    // category类型的分类页格式：/category/30521/页码.html
    url = host + tid.replace(/\/$/, '') + '/' + p + '.html';
  } else if (tid.startsWith('/tag/')) {
    // tag类型的分类页格式：/tag/34190/页码/
    url = host + tid.replace(/\/$/, '') + '/' + p + '/';
  } else {
    // 其他类型保持原样
    url = `${host}${tid}/page/${p}.html`;
  }
  
  console.log('分类页URL:', url); // 调试用
  let resp = await req(url, { headers });
  
  if (!resp || !resp.content) {
    return JSON.stringify({
      list: [],
      page: parseInt(p)
    });
  }
  
  return JSON.stringify({
    list: getList(resp.content),
    page: parseInt(p)
  });
}

/**
 * 解析HTML内容，提取视频列表数据（根据实际源码修正）
 */
function getList(html) {
  let videos = [];
  
  // 根据提供的源码，尝试多种可能的视频容器选择器
  let items = [];
  
  // 尝试多种选择器，根据实际网站结构
  if (html.includes('stui-vodlist__box')) {
    items = pdfa(html, ".stui-vodlist__box");
  } else if (html.includes('video-item')) {
    items = pdfa(html, ".video-item");
  } else if (html.includes('col-lg-3')) {
    items = pdfa(html, ".col-lg-3");
  } else {
    // 如果没有找到特定选择器，尝试通用匹配
    const itemRegex = /<a[^>]*href="([^"]+)"[^>]*title="([^"]+)"[^>]*>/g;
    let match;
    while ((match = itemRegex.exec(html)) !== null) {
      items.push(match[0]);
    }
  }
  
  console.log('找到的项目数量:', items.length); // 调试用
  
  items.forEach(it => {
    try {
      let idMatch = it.match(/href="([^"]+)"/);
      let nameMatch = it.match(/title="([^"]+)"/) || it.match(/alt="([^"]+)"/);
      let picMatch = it.match(/data-src="([^"]+)"/) || 
                    it.match(/data-original="([^"]+)"/) || 
                    it.match(/src="([^"]+)"/);
      let remarksMatch = it.match(/<span[^>]*class="[^"]*pic-text[^"]*"[^>]*>([^<]+)<\/span>/) ||
                        it.match(/<span[^>]*class="[^"]*state[^"]*"[^>]*>([^<]+)<\/span>/);

      if (idMatch && nameMatch) {
        let id = idMatch[1];
        let name = nameMatch[1]?.trim() || "未知片名";
        let pic = picMatch ? (picMatch[1] || picMatch[2]) : "";
        
        // 处理图片URL
        if (pic) {
          if (pic.startsWith('//')) {
            pic = 'https:' + pic;
          } else if (pic.startsWith('/')) {
            pic = host + pic.substring(1);
          }
        }
        
        // 处理ID
        if (!id.startsWith('http') && id.startsWith('/')) {
          id = id.substring(1);
        }
        
        videos.push({
          vod_id: id,
          vod_name: name,
          vod_pic: pic,
          vod_remarks: remarksMatch?.[1]?.trim() || "最新"
        });
      }
    } catch (e) {
      console.error('解析视频项时出错:', e);
    }
  });
  
  return videos;
}

/**
 * 获取首页推荐视频列表
 */
async function homeVod() {
  let resp = await req(host, { headers });
  if (!resp || !resp.content) {
    return JSON.stringify({
      list: []
    });
  }
  return JSON.stringify({
    list: getList(resp.content)
  });
}

/**
 * 获取视频详情信息
 */
async function detail(id) {
  // 根据源码，详情页URL可能是 /archives/39519/ 格式
  let url;
  if (id.startsWith('http')) {
    url = id;
  } else if (id.startsWith('/')) {
    url = host + id.substring(1);
  } else {
    url = host + id;
  }
  
  let resp = await req(url, { headers });
  if (!resp || !resp.content) {
    return JSON.stringify({
      list: []
    });
  }
  
  const html = resp.content;
  
  // 从源码中提取视频信息
  const titleMatch = html.match(/<title>([^<]+)<\/title>/);
  const contentMatch = html.match(/<div[^>]*class="[^"]*content[^"]*"[^>]*>([\s\S]*?)<\/div>/);
  const videoUrlMatch = html.match(/<source[^>]*src="([^"]+\.(m3u8|mp4|mkv))"/i) ||
                       html.match(/"url":"([^"]+\.(m3u8|mp4|mkv))"/i);
  
  let playUrl = videoUrlMatch ? videoUrlMatch[1] : '';
  
  // 如果视频URL是相对路径，补全域名
  if (playUrl && playUrl.startsWith('/')) {
    playUrl = host + playUrl.substring(1);
  } else if (playUrl && !playUrl.startsWith('http')) {
    playUrl = host + playUrl;
  }
  
  const playPairs = [{
    name: '高清播放',
    url: playUrl ? `立即播放$${playUrl}` : '暂无播放地址'   }];      const playFrom = playPairs.map(p => p.name).join('$$$');
  const playUrlStr = playPairs.map(p => p.url).join('$$$');
  
  return JSON.stringify({
    list: [{
      vod_id: id,
      vod_name: titleMatch ? titleMatch[1].replace('｜麻豆官网｜麻豆传媒官方站 最新华语AV免费看', '').trim() : '未知标题',
      vod_content: contentMatch ? contentMatch[1].replace(/<[^>]+>/g, '').substring(0, 200) + '...' : '暂无描述',
      vod_play_from: playFrom,
      vod_play_url: playUrlStr
    }]
  });
}

/**
 * 搜索视频
 */
async function search(wd, quick, pg) {
  let p = pg || 1;
  
  // 根据源码修正搜索URL格式
  let url;
  if (host.includes('madou.com')) {
    // madou.com的搜索格式
    url = `${host}?s=${encodeURIComponent(wd)}&page=${p}`;
  } else {
    // 其他网站保持原样
    url = `${host}/vod/search/page/${p}/wd/${wd}.html`;
  }
  
  let resp = await req(url, { headers });
  if (!resp || !resp.content) {
    return JSON.stringify({
      list: [],
      page: parseInt(p)
    });
  }
  
  return JSON.stringify({
    list: getList(resp.content),
    page: parseInt(p)
  });
}

/**
 * 获取播放链接
 */
async function play(flag, id, flags) {
  try {
    const playUrl = /^http/.test(id) ? id : `${host}${id}`;
    const resHtml = (await req(playUrl, { headers })).content;

    // 尝试多种方式提取播放地址
    let videoUrl = '';
    
    // 方式1：直接匹配m3u8/mp4/mkv链接
    const directMatch = resHtml.match(/https?:\/\/[^\s"']+\.(m3u8|mp4|mkv)[^\s"']*/i);
    if (directMatch) {
      videoUrl = directMatch[0];
    }
    
    // 方式2：匹配source标签
    if (!videoUrl) {
      const sourceMatch = resHtml.match(/<source[^>]*src="([^"]+\.(m3u8|mp4|mkv))"/i);
      if (sourceMatch) {
        videoUrl = sourceMatch[1];
      }
    }
    
    // 方式3：匹配JSON中的url
    if (!videoUrl) {
      const jsonMatch = resHtml.match(/"url":"([^"]+\.(m3u8|mp4|mkv))"/i);
      if (jsonMatch) {
        videoUrl = jsonMatch[1];
      }
    }
    
    // 判断是否需要解析
    const needParse = /m3u8|mp4|mkv/i.test(videoUrl) ? 0 : 1;
    
    // 如果找不到视频地址，使用播放页URL
    if (!videoUrl || needParse) {
      videoUrl = playUrl;
    }

    return JSON.stringify({
      jx: 0,
      parse: needParse,
      url: videoUrl,
      header: headers
    });
  } catch (e) {
    console.error('播放链接获取失败:', e);
    return JSON.stringify({
      jx: 0,
      parse: 0,
      url: '',
      header: {}
    });
  }
}

/**
 * 安全解析JSON字符串
 */
function safeParseJSON(str) {
  try {
    return JSON.parse(str.trim().replace(/;+$/, ''));
  } catch {
    return null;
  }
}

// 导出核心函数
export default {
  init,
  home,
  homeVod,
  category,
  detail,
  search,
  play
};