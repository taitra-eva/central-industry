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
  const entries = (data.items || []).filter(x => {
    if (!x.discovered_at) return false;
    return Utilities.formatDate(new Date(x.discovered_at), TZ, 'yyyy-MM-dd') === today;
  }).slice(0, 40);
  const esc = s => String(s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const rows = entries.map(x => {
    const url = HOME_URL + 'article.html?id=' + encodeURIComponent(x.id);
    const categories = (x.industries || []).join('、');
    return '<li style="margin:0 0 14px"><a href="' + esc(url) + '">' + esc(x.title_zh || x.title) + '</a><div style="font-size:12px;color:#65758a">' + esc(categories + '｜' + x.region + '｜' + x.source) + '</div>' + (x.summary_status==='verified'&&x.summary_zh?'<div>'+esc(x.summary_zh)+'</div>':'') + '</li>';
  }).join('');
  const title = '【中部產業情報日報】' + today + '｜新增 ' + entries.length + ' 則';
  const html = '<div style="font-family:Arial,sans-serif;max-width:760px"><h2>中部產業情報日報｜' + today + '</h2><p>最新新聞已更新。點選標題即可進入站內文章頁；如摘要尚未完成，頁面會明確標示。</p>' +
    (entries.length?'<ol>'+rows+'</ol>':'<p>今日尚無新增新聞，請由網站瀏覽已收錄資料。</p>')+
    '<p><a href="'+ HOME_URL +'">前往中部產業情報中心</a></p><p style="color:#65758a">公開新聞索引不等於已完成 AI 分析。完整新聞以原始媒體為準。</p></div>';
  if (MailApp.getRemainingDailyQuota() < 1) throw Error('今日寄信配額不足');
  MailApp.sendEmail({to:RECIPIENT,subject:title,body:'中部產業情報日報 '+today+'\n'+HOME_URL,htmlBody:html});
  props.setProperty('lastDigestDate', today);
}

function setupDailyDigestTrigger() {
  ScriptApp.getProjectTriggers().filter(t => t.getHandlerFunction()==='sendDailyIndustryDigest').forEach(ScriptApp.deleteTrigger);
  ScriptApp.newTrigger('sendDailyIndustryDigest').timeBased().everyMinutes(30).create();
}
