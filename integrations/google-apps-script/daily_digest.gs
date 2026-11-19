/**
 * 中部產業情報中心：免費 Google Apps Script 每日電子報
 * 由帳號擁有者自行建立 Apps Script，並授權 MailApp 寄信。
 * 不需要 GitHub token、API Key 或第三方付費郵件服務。
 */
const NEWS_URL = 'https://taitra-eva.github.io/central-industry/data/news.json';
const HOME_URL = 'https://taitra-eva.github.io/central-industry/';
const RECIPIENT = 'taitra.eva@gmail.com';
const TZ = 'Asia/Taipei';

function sendDailyIndustryDigest() {
  const now = new Date();
  const today = Utilities.formatDate(now, TZ, 'yyyy-MM-dd');
  const hour = Number(Utilities.formatDate(now, TZ, 'H'));
  // Trigger every 30 minutes. Wait until the 09:00 harvest and page have been published.
  if (hour < 9 || hour > 18) return;
  const props = PropertiesService.getScriptProperties();
  if (props.getProperty('lastDigestDate') === today) return;
  const response = UrlFetchApp.fetch(NEWS_URL + '?t=' + Date.now(), {muteHttpExceptions: true});
  if (response.getResponseCode() !== 200) throw Error('新聞 JSON 尚未發布: HTTP ' + response.getResponseCode());
  const data = JSON.parse(response.getContentText('UTF-8'));
  if (!data.updated_at || data.status === 'pending') throw Error('新聞資料尚未完成');
  const updatedDay = Utilities.formatDate(new Date(data.updated_at), TZ, 'yyyy-MM-dd');
  if (updatedDay !== today) return; // never send stale edition
  const allNew = (data.items || []).filter(x => {
    if (!x.discovered_at) return false;
    return Utilities.formatDate(new Date(x.discovered_at), TZ, 'yyyy-MM-dd') === today;
  });
  const industries = ['機械','自行車','汽配','手工具','無人載具及機器人'];
  const esc = s => String(s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  // Deduplicate across sectors. Show up to 5 highlights per industry, but do not email the full article list.
  const displayed = new Set();
  const sections = industries.map(industry => {
    const sectorItems = allNew.filter(x => (x.industries || []).includes(industry));
    const selected = sectorItems.filter(x => !displayed.has(x.id)).slice(0, 5);
    selected.forEach(x => displayed.add(x.id));
    const lis = selected.map(x => {
      const url = HOME_URL + 'article.html?id=' + encodeURIComponent(x.id);
      const title = esc(x.title_zh || x.title);
      const summary = (x.summary_zh && ['verified','source_excerpt_translated'].includes(x.summary_status))
        ? '<div style="font-size:13px;color:#57463a;line-height:1.6;margin-top:4px">' + esc(x.summary_zh) + '</div>'
        : '<div style="font-size:12px;color:#8a7a70">中文摘要尚未完成，點進頁面可查看原文來源</div>';
      return '<li style="margin:0 0 14px"><a style="color:#91511f;text-decoration:none;font-weight:bold" href="' + esc(url) + '">' + title + '</a>' +
        '<div style="font-size:12px;color:#867668">' + esc((x.region||'') + '｜' + (x.source||'')) + '</div>' + summary + '</li>';
    }).join('');
    return '<section style="margin:22px 0"><h3 style="border-left:4px solid #b46c38;padding-left:10px;color:#704023">' + esc(industry) +
      ' <small style="font-weight:normal;color:#807165">(' + sectorItems.length + ' 則)</small></h3>' +
      (lis ? '<ol style="padding-left:24px">' + lis + '</ol>' : '<p style="color:#85766b">本次沒有新收錄新聞</p>') + '</section>';
  }).join('');
  const title = '【中部產業情報日報】' + today + '｜五大產業新增 ' + allNew.length + ' 則';
  const html = '<div style="font-family:Arial,\"Noto Sans TC\",sans-serif;max-width:720px;margin:auto;color:#3c3029">' +
    '<div style="background:#744020;color:white;padding:24px;border-radius:12px 12px 0 0"><h2 style="margin:0">中部產業情報日報</h2><div style="color:#f2dac3;margin-top:6px">' + today + '｜五大產業觀察</div></div>' +
    '<div style="background:#fffaf5;padding:22px;border:1px solid #eddfd0"><p>今日新收錄 <b>' + allNew.length +
    '</b> 則，以下每個產業最多精選 5 則。點新聞可進入站內頁面，查看已取得的中文重點與原文資訊。</p>' +
    sections + '<p style="text-align:center;margin-top:24px"><a style="background:#945226;color:white;padding:11px 18px;text-decoration:none;border-radius:7px" href="' + HOME_URL + '">查看網站全部新聞</a></p>' +
    '<p style="color:#8b7a70;font-size:12px">尚未取得足夠原文的文章不會編造中文摘要；本報告僅供情報參考。</p></div></div>';
  if (MailApp.getRemainingDailyQuota() < 1) throw Error('今日寄信配額不足');
  MailApp.sendEmail({to:RECIPIENT,subject:title,body:'中部產業情報日報 '+today+'\n'+HOME_URL,htmlBody:html});
  props.setProperty('lastDigestDate', today);
}

function setupDailyDigestTrigger() {
  ScriptApp.getProjectTriggers().filter(t => t.getHandlerFunction()==='sendDailyIndustryDigest').forEach(ScriptApp.deleteTrigger);
  ScriptApp.newTrigger('sendDailyIndustryDigest').timeBased().everyMinutes(30).create();
}
