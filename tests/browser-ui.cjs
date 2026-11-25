const { chromium } = require('playwright');
const fs = require('fs');
const path=require('path'),http=require('http');
const root=path.resolve(__dirname,'..');
const out=path.join(root,'build/ui');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const server=http.createServer((req,res)=>{res.setHeader('Content-Type','text/html; charset=utf-8');res.end(fs.readFileSync(path.join(root,'index.html')))});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const origin='http://127.0.0.1:'+server.address().port+'/';
 const browser=await chromium.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 const results=[];
 for(const width of [320,360,393,768,1440]){
  const context=await browser.newContext({viewport:{width,height:900},locale:'ru-RU',permissions:['clipboard-read','clipboard-write']});
  const page=await context.newPage();const errors=[],network=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{const u=route.request().url();if(u.startsWith(origin)||u.startsWith('data:'))return route.continue();network.push(u);return route.abort()});
  await page.goto(origin,{waitUntil:'networkidle'});
  try {
  const result={width,errors,initialRanks:await page.locator('#rank .rankingRow').count(),initialOperations:await page.locator('#feed .operationRow').count()};
  await page.locator('#holdersMore').click();result.expandedRanks=await page.locator('#rank .rankingRow').count();
  await page.locator('#holdersMore').click();result.collapsedRanks=await page.locator('#rank .rankingRow').count();
  await page.locator('#more').click();result.expandedOperations=await page.locator('#feed .operationRow').count();await page.locator('#more').click();
  await page.locator('#badgeFilterToggle').click();result.filtersOpen=await page.locator('#badgeFilterPanel').isVisible();await page.locator('#badgeFilterToggle').click();
  if(!await page.locator('#en').isVisible()||!await page.locator('#ru').isVisible())throw Error('Hidden language choice');
  await page.locator('#en').click();result.language=await page.locator('html').getAttribute('lang');
  await page.locator('#views button').nth(1).click();await page.locator('#sellerPeriods button').nth(2).click();result.sellers30=await page.locator('#rank .rankingRow').count();
  await page.locator('#views button').nth(2).click();result.services=await page.locator('#rank .rankingRow').count();
  await page.locator('#views button').nth(0).click();
  await page.locator('#currency button').nth(1).click();result.usdCap=await page.locator('#lastPrice').innerText();
  await page.locator('#currency button').nth(0).click();
  for(let i=0;i<await page.locator('#periods button').count();i++){await page.locator('#periods button').nth(i).click();if((await page.locator('#plot').innerHTML()).includes('NaN'))throw Error('NaN chart')}
  await page.locator('#periods button').nth(1).click();
  await page.locator('#plot svg[tabindex]').click();await page.locator('#plot svg[tabindex]').press('ArrowLeft');
  await page.locator('#copy').click();result.clipboard=await page.evaluate(()=>navigator.clipboard.readText());
  await page.locator('#ru').click();
  Object.assign(result,await page.evaluate(()=>({documentWidth:document.documentElement.scrollWidth,innerWidth,overflow:[...document.querySelectorAll('body *')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.right>innerWidth+1}).slice(0,12).map(e=>({tag:e.tagName,id:e.id,class:e.className})),externalRenderingResources:[...document.querySelectorAll('script[src],img[src],link[href]')].map(e=>e.src||e.href).filter(u=>/^https?:/.test(u)),invalidAnchors:[...document.querySelectorAll('a[href^="#"]')].filter(a=>!document.getElementById(a.hash.slice(1))).map(a=>a.hash),emptyButtons:[...document.querySelectorAll('button')].filter(b=>!b.textContent.trim()&&!b.getAttribute('aria-label')).map(b=>b.id),brokenImages:[...document.images].filter(i=>!i.complete||!i.naturalWidth).map(i=>i.alt),chartPaths:document.querySelectorAll('#plot svg path').length})));
  await page.evaluate(()=>scrollTo(0,0));
  if(width===393||width===1440)await page.screenshot({path:path.join(out,`joystick-${width}.png`),fullPage:true});
  results.push(result);await context.close();
  } catch(error) {
   await page.screenshot({path:path.join(out,`failure-${width}.png`),fullPage:true});
   fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify({width,error:error.stack},null,2));
   throw error;
  }
 }
 fs.writeFileSync(path.join(out,'ui-checks.json'),JSON.stringify(results,null,2));
 console.log(JSON.stringify(results,null,2));await browser.close();server.close();
 // Document width detects real horizontal scrolling; clipped decorative children
 // may extend outside their cards and are retained only as diagnostics above.
 if(results.some(r=>r.errors.length||r.documentWidth>r.innerWidth||r.externalRenderingResources.length||r.invalidAnchors.length||r.emptyButtons.length||r.brokenImages.length||r.initialRanks!==10||r.expandedRanks!==20||r.initialOperations!==10||r.expandedOperations<20))process.exit(1);
})();
