var rule = {
    title: '溏心次元',
    host: 'https://txcy-online.buzz/',
    url: '/index.php/vodtype/fyclass-fypage/',
    homeUrl: '/banshu/',
    searchUrl: '/vodsearch/**----------fypage---/',
    searchable: 2,
    quickSearch: 1,
    filterable: 1,
    limit: 30,
    编码: 'utf-8',
    timeout: 5000,
    headers: {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 13; M2102J2SC Build/TKQ1.221114.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/139.0.7258.3 Mobile Safari/537.36',
    },
    class_name: '麻豆原创&代理节目&节目企划&国产片商&MD系列&导演系列&MDS系列&MDX系列&MDXS系列&MDL系列&MMZ系列&MAD系列&MDWP系列&MSD系列&MDM恋爱咖啡&MDUS系列&MXJ系列&MKY系列&MAN系列&MCY系列&MDAG系列&MDHT系列&BLX系列&MPG系列&兔子先生&果冻传媒&皇家华人&吴梦梦无套系列&PsychoPorn色控&蜜桃影像传媒&天美传媒&91制片厂&MSM性梦者&叮叮映画&涩会&豚豚创媒&爱妃传媒&辣椒原创&O-STAR&肉肉传媒&渡边传媒&葵心娱乐&红斯灯影像&麻麻传媒&蝌蚪传媒&PussyHunter&桃花源&大鸟十八&疯拍系列&KISS糖果屋&小鹏奇啪行&30天解密麻豆&突袭女优计划&女神羞羞研究所&小哥哥艾理&情趣K歌房&淫欲游戏王&麻豆不回家&女优淫娃培训营&狼人插&女优擂台摔角狂热&恋爱巴士&男女优生死斗&情人劫密室逃脱&换妻&你好同学&禁欲小屋&鲍鱼的胜利&性爱自修室&春游记&心动的性号&情趣大富翁&寻宝吧女神&男优练习生&女神体育祭&麻豆高校&野外露初&乌鸦传媒&精东影业&SWAG&星空无限传媒&大象传媒&大象传媒&MINI传媒&糖心&葫芦影业&天马传媒&CCAV成人头条&性视界传媒&SA国际传媒&香蕉传媒&91茄子&EDmosaic&国产精品',
    class_url: '1&2&3&32&4&5&6&7&8&46&50&53&58&64&74&78&79&87&89&96&100&101&115&116&10&11&12&13&14&15&45&52&65&71&72&75&76&80&81&91&95&97&103&104&105&106&108&17&18&19&20&22&23&24&27&31&40&41&54&55&61&66&67&68&69&77&84&88&92&93&94&99&102&110&111&112&33&34&36&47&48&59&62&73&82&83&90&109&113&114&117&118&39',
    play_parse: true,
    lazy: $js.toString(() => {
        input = {
            parse: 1,
            url: input,
            js: 'document.querySelector("#playleft iframe").contentWindow.document.querySelector("#start").click();'
        };
    }),
    double: true,
    lazy: $js.toString(() => {
        let html = JSON.parse(request(input).match(/r player_.*?=(.*?)</)[1]);
        let url = html.url;
        if (html.encrypt == '1') {
            url = unescape(url)
        } else if (html.encrypt == '2') {
            url = unescape(base64Decode(url))
        }
        if (/\.m3u8|\.mp4/.test(url)) {
            input = {
                jx: 0,
                url: url,
                parse: 0
            }
        } else {
            input
        }
    }),
    tab_rename: {
        '道长在线': '溏心次元在线'
    },
    推荐: '.row;.mb20;h2&&Text;img&&src;span small:eq(1)&&Text;a&&href',
    一级: '.row-m-space8&&.mb20;h2&&Text;img&&src;span small:eq(1)&&Text;a&&href',
    二级: '*',
    搜索: '*',
}