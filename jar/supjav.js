/**
 * SupJav 爬虫（OK影视/TVBox 适配：真人验证需手动通过后复用 Cookie）
 * 说明：
 * - 不尝试绕过/自动破解真人验证；只是在检测到验证页时弹出 WebView，让你手动点选通过。
 * - 通过后从 WebView 的 CookieManager 里读取 cf_clearance，
 *   后续请求继续复用，避免每次都重复验证。
 */

const baseUrl = 'https://supjav.com/zh';

// 可能的真人验证关键字（不同站点/语言会变化，做了宽松匹配）
const HUMAN_CHALLENGE_MARKERS = [
  'Verifying you are human',
  'verify you are human',
  'turnstile',
  'cf-challenge',
  'cf-turnstile',
  'challenge-platform',
  'captcha',
  '人机验证',
  '真人验证',
  '正在验证您是人类',
  '正在进行安全验证',
  '验证您不是自动程序'
];

// __cf_bm 只表示 Bot Management 已参与请求，不能代表挑战已经通过。
const PASS_COOKIE_NAMES = [
  'cf_clearance'
];

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

function containsAny(text, arr) {
  if (!text) return false;
  const t = String(text);
  return arr.some(k => t.toLowerCase().includes(String(k).toLowerCase()));
}

function hasPassCookie(cookieStr) {
  if (!cookieStr) return false;
  const c = String(cookieStr);
  return PASS_COOKIE_NAMES.some(name => c.includes(name + '='));
}

/**
 * 确保已通过真人验证（需要时弹出 WebView 让用户手动操作）
 * @param {string} url
 */
async function ensureHumanVerified(url) {
  // 1) 如果 Cookie 已经有放行标记，就不再打扰
  try {
    const ck = Java.getCookies(url);
    if (hasPassCookie(ck)) return;
  } catch (e) {}

  // 2) 打开一次目标页面，判断是否落在验证页
  let doc;
  try {
    doc = await Java.wvOpen(url);
  } catch (e) {
    // wvOpen 失败时也只能直接返回，让上层报错
    return;
  }

  const html = (doc && (doc.content || (doc.documentElement && doc.documentElement.outerHTML))) || '';
  const isChallenge = containsAny(html, HUMAN_CHALLENGE_MARKERS);

  if (!isChallenge) return;

  // 3) 需要人工：显示 WebView，让用户勾选/点击验证
  try {
    Java.showWebView();
    if (Java.showToast) Java.showToast('检测到真人验证：请在弹出的页面手动通过一次（可能需要勾选/等待），通过后会自动继续。', 'long');
  } catch (e) {}

  // 4) 轮询 Cookie，等待用户完成验证后 WebView 写入放行 Cookie
  const maxWaitMs = 90 * 1000;
  const stepMs = 1200;
  const start = Date.now();

  while (Date.now() - start < maxWaitMs) {
    await sleep(stepMs);
    let ck = '';
    try { ck = Java.getCookies(url) || ''; } catch (e) {}

    // 有些站点把 cookie 写在顶级域名，取 baseUrl 也试一下
    let ck2 = '';
    try { ck2 = Java.getCookies(baseUrl) || ''; } catch (e) {}

    if (hasPassCookie(ck) || hasPassCookie(ck2)) {
      try {
        if (Java.showToast) Java.showToast('真人验证已通过，继续加载…', 'short');
        Java.hideWebView();
      } catch (e) {}
      return;
    }
  }

  // 超时：不强行隐藏，方便你继续操作
  try {
    if (Java.showToast) Java.showToast('等待真人验证超时：如果一直过不去，可能是系统 WebView/网络环境导致循环验证。', 'long');
  } catch (e) {}
}

/**
 * 初始化配置
 */
async function init(cfg) {
  return {
    webview: {
      debug: true,
      showWebView: false,        // 默认不显示，只有检测到真人验证时才显示
      widthPercent: 90,
      heightPercent: 70,

      // 关键点：不要把 keyword 留空。
      // keyword 的语义通常是“页面不包含该关键字时才显示 WebView”。
      // 这里填一个正常页面常见的关键词（比如站点标题/导航），这样正常抓取不弹窗。
      keyword: 'supjav',

      returnType: 'dom',
      timeout: 40,
      blockImages: false,
      enableJavaScript: true,
      header: {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 12; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
        'Referer': baseUrl + '/',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
      },

      // 详情页含自动播放广告，嗅探时必须排除这些已确认的广告媒体域。
      blockList: [
        'growcdnssedge.com',
        'doppiocdn.com',
        'mayzaent.com',
        'eix304.com',
        'mnaspm.com',
        'djsalcbhew47.lol',
        'tapioni.com',
        'googletagmanager.com',
        'google-analytics.com'
      ]
    }
  };
}

async function homeContent(filter) {
  return {
    class: [
      { type_id: "popular", type_name: "热门" },
      { type_id: "category/censored-jav", type_name: "有码" },
      { type_id: "category/uncensored-jav", type_name: "无码" },
      { type_id: "category/amateur", type_name: "素人" },
      { type_id: "category/chinese-subtitles", type_name: "中文字幕" },
      { type_id: "category/english-subtitles", type_name: "英文字幕" },
      { type_id: "category/reducing-mosaic", type_name: "无码破解" }
    ]
  };
}

async function homeVideoContent() {
  await ensureHumanVerified(baseUrl + '/');
  const document = await Java.wvOpen(baseUrl + '/');
  const videos = parseVideoList(document);
  return { list: videos };
}

async function categoryContent(tid, pg, filter, extend) {
  const page = Math.max(1, parseInt(pg, 10) || 1);
  const pgSuffix = (page === 1 ? '' : `/page/${page}`);
  const url = `${baseUrl}/${tid}${pgSuffix}`;
  await ensureHumanVerified(url);
  const document = await Java.wvOpen(url);
  const videos = parseVideoList(document);
  return { code: 1, msg: "数据列表", list: videos, page, pagecount: 10000, limit: 24, total: 240000 };
}

async function detailContent(ids) {
  // 列表统一返回 "452805.html" 这类 ID，保持模板简单以便 WvSpider 预加载器识别。
  const id = ids && ids.length ? String(ids[0] || '').trim() : '';
  if (!id) return emptyResult('无效的详情 ID');

  // SupJav 的真实详情地址必须保留 .html，例如 /zh/452805.html。
  const url = baseUrl + `/${id}`;
  await ensureHumanVerified(url);
  const document = await Java.wvOpen(baseUrl + `/${id}`);

  if (isChallengeDocument(document)) {
    return emptyResult('真人验证尚未完成，请验证后重试');
  }

  const postImage = document.querySelector('.post-meta img.img, .post-meta .img');
  const title = textOf(document.querySelector('.archive-title h1, .post-meta h2')) ||
    (postImage ? postImage.getAttribute('alt') || '' : '');
  const pic = fixUrl(document, postImage ? postImage.getAttribute('src') || '' : '');
  if (!title) return emptyResult('详情页解析失败');

  const category = textOf(document.querySelector('.post-meta .cats .cat a'));
  const makerParagraphs = Array.from(document.querySelectorAll('.post-meta .cats p'));
  const makerParagraph = makerParagraphs.find(el => /Maker\s*:/i.test(el.textContent || ''));
  const maker = makerParagraph ? textOf(makerParagraph.querySelector('a')) : '';
  const tags = Array.from(document.querySelectorAll('.post-meta .tags a'))
    .map(textOf)
    .filter(Boolean);
  const views = textOf(document.querySelector('.dz_view .views'));

  let serverButtons = Array.from(document.querySelectorAll('.btnst .btn-server[data-link]'));
  if (!serverButtons.length) {
    serverButtons = Array.from(document.querySelectorAll('.video-wrap .btn-server[data-link]'));
  }
  if (!serverButtons.length) {
    serverButtons = Array.from(document.querySelectorAll('.btnst .btn-server, .video-wrap .btn-server'));
  }
  const encodedUrl = encodeURIComponent(url);
  const playItems = serverButtons.map((btn, index) => {
    const serverName = textOf(btn) || `线路${index + 1}`;
    return `${serverName}$${index}---${encodedUrl}`;
  });

  return {
    code: 1,
    msg: '数据列表',
    page: 1,
    pagecount: 1,
    limit: 1,
    total: 1,
    list: [{
      vod_id: id,
      vod_name: title,
      vod_pic: pic,
      vod_remarks: [category, views].filter(Boolean).join(' / '),
      vod_director: maker,
      vod_actor: tags.join(','),
      vod_content: postImage ? postImage.getAttribute('alt') || title : title,
      vod_play_from: 'SupJav',
      vod_play_url: playItems.join('#')
    }]
  };
}

async function playerContent(flag, id, vipFlags) {
  const separator = String(id || '').indexOf('---');
  const index = Math.max(0, parseInt(String(id || '').slice(0, separator), 10) || 0);
  let detailUrl = separator >= 0 ? String(id).slice(separator + 3) : '';
  try { detailUrl = decodeURIComponent(detailUrl); } catch (e) {}
  if (!/^https?:\/\//i.test(detailUrl)) {
    const detailId = normalizeDetailId(detailUrl);
    detailUrl = detailId ? `${baseUrl}/${detailId}` : baseUrl + '/';
  }

  await ensureHumanVerified(detailUrl);

  return {
    type: 'sniff',
    url: detailUrl,
    // .mp4 会优先命中详情页广告；真实线路使用 HLS 或 Streamtape 下载接口。
    keyword: '.m3u8|streamtape.com/get_video|tapecontent.net',
    script: `
      (function(){
        var idx = ${index};
        var attempts = 0;
        var timer = setInterval(function(){
          attempts++;
          try {
            var btns = document.querySelectorAll('.btnst .btn-server[data-link]');
            if (!btns.length) btns = document.querySelectorAll('.video-wrap .btn-server[data-link]');
            if (!btns.length) {
              btns = document.querySelectorAll('.btnst .btn-server, .video-wrap .btn-server');
            }
            var target = btns[idx] || btns[0];
            if (target) {
              target.click();
              if (document.querySelector('#video')) {
                clearInterval(timer);
                return;
              }
            }
            var firstPlay = document.querySelector('#vserver');
            if (firstPlay && idx === 0) {
              firstPlay.click();
              if (document.querySelector('#video')) {
                clearInterval(timer);
                return;
              }
            }
          } catch (e) {}
          if (attempts >= 20) clearInterval(timer);
        }, 250);
        setTimeout(function(){
          try { clearInterval(timer); } catch (e) {}
        }, 6000);
      })();
    `,
    timeout: 35,
    headers: {
      'Referer': detailUrl
    }
  };
}

async function searchContent(key, quick, pg) {
  const page = Math.max(1, parseInt(pg, 10) || 1);
  const pagePath = page === 1 ? '/' : `/page/${page}/`;
  const url = `${baseUrl}${pagePath}?s=${encodeURIComponent(key || '')}`;
  await ensureHumanVerified(url);
  const document = await Java.wvOpen(url);
  const videos = parseVideoList(document);
  return {
    code: 1,
    msg: '数据列表',
    list: videos,
    page,
    pagecount: videos.length ? page + 1 : page,
    limit: 24,
    total: videos.length
  };
}

async function action(actionStr) {
  return { list: [] };
}

/* ---------------- 工具函数 ---------------- */
function parseVideoList(document) {
  const posts = document.querySelectorAll('.post');
  return Array.from(posts).map(post => {
    const titleLink = post.querySelector('h3 a');
    const vod_name = (titleLink?.getAttribute('title') || titleLink?.textContent || '').trim();
    const vod_id = normalizeDetailId(titleLink?.getAttribute('href') || '');
    const img = post.querySelector('img');
    const rawPic = img?.getAttribute('data-original') || img?.getAttribute('src') || '';
    const vod_pic = fixUrl(document, rawPic);
    const meta = post.querySelector('.meta');
    let vod_remarks = '';
    if (meta) {
      const metaText = meta.textContent || '';
      const viewsMatch = metaText.match(/([\d,]+)\s*Views/i);
      if (viewsMatch) vod_remarks = `${viewsMatch[1]}次浏览`;
      else {
        const chineseMatch = metaText.match(/([\d,]+)\s*次浏览/);
        vod_remarks = chineseMatch ? `${chineseMatch[1]}次浏览` : '';
      }
    }
    return { vod_id, vod_name, vod_pic, vod_remarks };
  }).filter(item => item.vod_id && item.vod_name);
}

function normalizeDetailId(value) {
  let id = String(value || '').trim();
  if (!id) return '';
  try { id = decodeURIComponent(id); } catch (e) {}

  try {
    if (/^https?:\/\//i.test(id)) id = new URL(id).pathname;
  } catch (e) {}

  id = id.split('?')[0].split('#')[0].replace(/\/+$/, '');
  id = id.slice(id.lastIndexOf('/') + 1);
  if (/^\d+$/.test(id)) id += '.html';
  return id;
}

function fixUrl(document, value) {
  if (!value) return '';
  try {
    if (document && document.fixUrl) return document.fixUrl(value);
    return new URL(value, baseUrl + '/').href;
  } catch (e) {
    return value;
  }
}

function textOf(element) {
  return element ? (element.textContent || '').trim() : '';
}

function isChallengeDocument(document) {
  const html = (document && (document.content ||
    (document.documentElement && document.documentElement.outerHTML))) || '';
  return containsAny(html, HUMAN_CHALLENGE_MARKERS);
}

function emptyResult(message) {
  return {
    code: 1,
    msg: message || '数据列表',
    page: 1,
    pagecount: 1,
    limit: 0,
    total: 0,
    list: []
  };
}

const spider = { init, homeContent, homeVideoContent, categoryContent, detailContent, searchContent, playerContent, action };
spider;
