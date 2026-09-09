// 定义网站主域名
let host = 'https://pwxxx.pwxxx33.fun/pwxxx/';
// 请求头配置，模拟安卓移动端浏览器请求
let headers = {
  "User-Agent": "Mozilla/5.0 (Linux; Android 13; M2102J2SC Build/TKQ1.221114.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/143.0.7499.3 Mobile Safari/537.36"
};
//永久地址:pwxxx.com
/**
 * 初始化函数（预留）
 * @param {Object} cfg - 配置参数（暂未使用）
 */
async function init(cfg) {}

/**
 * 解析HTML内容，提取视频列表数据
 * @param {string} html - 页面HTML字符串
 * @returns {Array} 视频列表数组，包含每个视频的id、名称、封面、备注等信息
 */
function getList(html) {
  let videos = []; // 存储解析后的视频数据
  // 根据是否包含搜索结果标识，选择不同的DOM选择器获取视频项列表
  let items = pdfa(html, ".stui-vodlist__box");

  // 遍历每个视频项，解析关键信息
  items.forEach(it => {
    // 匹配视频详情页链接（id）
    let idMatch = it.match(/href="(.*?)"/);
    // 匹配视频名称（优先title属性，其次alt属性）
    let nameMatch = it.match(/title="(.*?)"/) || it.match(/alt="(.*?)"/);
    // 匹配视频封面图（优先data-src，其次data-original，最后src）
    let picMatch = it.match(/data-src="(.*?)"/) || it.match(/data-original="(.*?)"/) || it.match(/src="(.*?)"/);
    // 匹配视频备注/状态信息
    let remarksMatch = it.match(/<span class="pic-text text-right">(.*?)<\/span>/) || it.match(/state">[\s\S]*?<span>([\s\S]*?)<\/span>/);

    // 确保id和名称匹配成功才添加到列表
    if (idMatch && nameMatch) {
      let pic = picMatch ? (picMatch[1] || picMatch[2]) : "";
      videos.push({
        vod_id: idMatch[1], // 视频唯一标识（详情页链接）
        vod_name: nameMatch?.[1]?.trim() || "未知片名", // 视频名称
        vod_pic: pic.startsWith('/') ? host + pic : pic, // 封面图完整URL（补全域名）
        vod_remarks: remarksMatch?.[1]?.trim() || "未知备注" // 视频备注/状态
      });
    }
  });
  return videos;
}

/**
 * 获取首页分类列表
 * @param {Object} filter - 筛选参数（暂未使用）
 * @returns {string} 分类列表的JSON字符串，包含电影、剧集、综艺、动漫、短剧五类
 */
async function home(filter) {
  return JSON.stringify({
    "class": [{
      "type_id": "1",
      "type_name": "国产大区"
    }, {
      "type_id": "2",
      "type_name": "日韩大区"
    }, {
      "type_id": "3",
      "type_name": "欧美大区"
    }, {
      "type_id": "4",
      "type_name": "其它视频"
    }, {
      "type_id": "13",
      "type_name": "国产精品"
    }, {
      "type_id": "6",
      "type_name": "网曝吃瓜"
    }, {
      "type_id": "7",
      "type_name": "自拍偷拍"
    }, {
      "type_id": "8",
      "type_name": "传媒出品"
    }, {
      "type_id": "9",
      "type_name": "网红主播"
    }, {
      "type_id": "10",
      "type_name": "大神探花"
    }, {
      "type_id": "11",
      "type_name": "抖阴视频"
    }, {
      "type_id": "12",
      "type_name": "国产其它"
    }, {
      "type_id": "14",
      "type_name": "日韩精品"
    }, {
      "type_id": "15",
      "type_name": "日韩无码"
    }, {
      "type_id": "16",
      "type_name": "日韩有码"
    }, {
      "type_id": "20",
      "type_name": "中文字幕"
    }, {
      "type_id": "21",
      "type_name": "萝莉少女"
    }, {
      "type_id": "22",
      "type_name": "人妻熟妇"
    }, {
      "type_id": "23",
      "type_name": "韩国主播"
    }, {
      "type_id": "24",
      "type_name": "日韩其它"
    }, {
      "type_id": "5",
      "type_name": "欧美精品"
    }, {
      "type_id": "25",
      "type_name": "欧美无码"
    }, {
      "type_id": "26",
      "type_name": "欧美另类"
    }, {
      "type_id": "27",
      "type_name": "欧美其它"
    }, {
      "type_id": "28",
      "type_name": "AI换脸"
    }, {
      "type_id": "29",
      "type_name": "AV解说"
    }, {
      "type_id": "30",
      "type_name": "三级伦理"
    }, {
      "type_id": "31",
      "type_name": "成人动漫"
    }]
  });
}

/**
 * 获取首页推荐视频列表
 * @returns {string} 首页视频列表的JSON字符串
 */
async function homeVod() {
  // 请求首页数据
  let resp = await req(host, {
    headers
  });
  // 解析并返回视频列表
  return JSON.stringify({
    list: getList(resp.content)
  });
}

/**
 * 获取分类下的视频列表（支持分页）
 * @param {string} tid - 分类ID
 * @param {number} pg - 页码
 * @param {Object} filter - 筛选参数（暂未使用）
 * @param {Object} extend - 扩展参数（优先使用extend.class作为分类ID）
 * @returns {string} 分类视频列表+当前页码的JSON字符串
 */
async function category(tid, pg, filter, extend) {
  let p = pg || 1; // 默认第一页
  // 优先使用扩展参数中的分类ID，否则使用tid
  let targetId = (extend && extend.class) ? extend.class : tid;
  // 拼接分类列表页URL（带分页）
  let url = `${host}/vod/type/id/${tid}/page/${p}.html`;
  // 请求分类页面数据
  let resp = await req(url, {
    headers
  });
  // 解析并返回视频列表+当前页码
  return JSON.stringify({
    list: getList(resp.content),
    page: parseInt(p)
  });
}
/**
 * 获取视频详情信息（含播放源）
 * @param {string} id - 视频详情页链接（相对路径）
 * @returns {string} 视频详情的JSON字符串，包含名称、封面、年份、地区、演员、播放地址等
 */
async function detail(id) {
  //二级链接拼接
  let url = host + '/vod/play/id' + id + '/sid/1/nid/1.html';
  let resp = await req(url, {
    headers
  });
  const html = resp.content;
  const v = html.match(/"url":"([^"]+\.m3u8)",/)?.[1] || '';
  const playPairs = [{
    name: '菜佬湿最爱',
    url: `立即播放$${v}`
  }];
  const playFrom = playPairs.map(p => p.name).join('$$$');
  const playUrl = playPairs.map(p => p.url).join('$$$');
  return JSON.stringify({
    list: [{
      vod_id: id,
      'vod_content': (html.match(/<h1 class="title">(.*?)<\/h1>/) || ["", ""])[1].replace(/<.*?>/g, "").replace("特别提醒如果您对影片有自己的看法请留言弹幕评论。", ""),
      vod_play_from: playFrom,
      vod_play_url: playUrl
    }]
  });
}

/**
 * 搜索视频（支持分页）
 * @param {string} wd - 搜索关键词
 * @param {boolean} quick - 快速搜索标识（暂未使用）
 * @param {number} pg - 页码
 * @returns {string} 搜索结果列表+当前页码的JSON字符串
 */
async function search(wd, quick, pg) {
  let p = pg || 1; // 默认第一页
  // 拼接搜索结果页URL（带分页）
  let url = `${host}/vod/search/page/${p}/wd/${wd}.html`;
  // 请求搜索页面数据
  let resp = await req(url, {
    headers
  });
  // 解析并返回搜索结果+当前页码
  return JSON.stringify({
    list: getList(resp.content),
    page: parseInt(p)
  });
}
/**
 * 获取播放链接（核心播放逻辑）
 * @param {string} flag - 播放源标识（暂未使用）
 * @param {string} id - 播放页链接（相对/绝对路径）
 * @param {string} flags - 扩展标识（暂未使用）
 * @returns {string} 播放配置的JSON字符串，包含是否解析、播放URL、请求头等
 */
async function play(flag, id, flags) {
  try {
    // 拼接播放页完整URL（如果是相对路径则补全域名）
    const playUrl = /^http/.test(id) ? id : `${host}${id}`;
    // 请求播放页HTML
    const resHtml = (await req(playUrl, {
      headers
    })).content;

    // 匹配并解析播放器配置的JSON数据（提取播放URL）
    const kcode = safeParseJSON(
      resHtml.match(/var player_.*?=([^]*?)</)?.[1] ?? ''
    );
    let kurl = kcode?.url ?? ''; // 提取原始播放URL

    // 判断是否需要二次解析：如果是m3u8/mp4/mkv直接播放，否则标记为需要解析
    const kp = /m3u8|mp4|mkv/i.test(kurl) ? 0 : 1;
    if (kp) kurl = playUrl; // 需要解析则使用播放页URL

    // 返回播放配置
    return JSON.stringify({
      jx: 0, // 无需代理（固定值）
      parse: kp, // 是否需要解析（0=否，1=是）
      url: "http://127.0.0.1:10079/p/0/127.0.0.1:10172/" + kurl, // 播放URL
      header: headers // 播放请求头
    });
  } catch (e) {
    // 异常时返回空配置
    return JSON.stringify({
      jx: 0,
      parse: 0,
      url: '',
      header: {}
    });
  }
}

/**
 * 安全解析JSON字符串（容错处理）
 * @param {string} str - 待解析的JSON字符串
 * @returns {Object|null} 解析后的对象，失败则返回null
 */
function safeParseJSON(str) {
  try {
    // 去除字符串首尾空格和末尾分号后解析
    return JSON.parse(str.trim().replace(/;+$/, ''));
  } catch {
    return null; // 解析失败返回null
  }
}

// 导出核心函数，供外部调用
export default {
  init, // 初始化
  home, // 获取首页分类
  homeVod, // 获取首页视频
  category, // 获取分类视频
  detail, // 获取视频详情
  search, // 搜索视频
  play // 获取播放链接
};