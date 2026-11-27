// 기능 시험 화면(selftest.html) 시험: 어사이드가 할 수 있는 일을 화면이 스스로 채점하는지
//  사용: node aside/test/sim/e2e-selftest.mjs [화면을 찍어 둘 폴더]
import { start, checker } from "./env.mjs";
const { ok, done } = checker(), SHOT = process.argv[2];
const E = await start();
const p = await E.ctx.newPage(); const errs = []; p.on("pageerror", (e) => errs.push(e.message));
let dialogs = 0; p.on("dialog", (d) => { dialogs++; d.accept(); });
await p.goto("https://mfgkorea.github.io/order.html/aside/selftest.html");
await p.waitForTimeout(1500);
const r = (k) => p.evaluate((id) => { const e = document.getElementById("r-" + id); return [e.dataset.r, e.textContent]; }, k);
ok((await r("sheet"))[0] === "1" && (await r("clock"))[0] === "1", "스스로 확인: 시트 연결 · 시계(한국 시간) 됨 · " + (await r("clock"))[1]);
ok((await r("eval"))[0] === "" && (await r("script"))[0] === "", "하기 전에는 '대기'");
await p.evaluate(await p.evaluate(() => document.getElementById("snip").value)); await p.waitForTimeout(800);
ok((await r("eval"))[0] === "1" && (await r("script"))[0] === "1", "코드를 실행하면 1·2번이 '됨'");
const src = await p.evaluate(() => document.getElementById("src").textContent);
ok(src.split("\n").length === 61 && !/[가-힣]{2,}(점|매장)/.test(src), "옮겨 넣을 표는 지어낸 61줄");
await p.fill("#dst", src); ok((await r("paste"))[0] === "1", "그대로 옮기면 '됨'");
await p.fill("#dst", src.replace(/\t/g, "    ")); ok((await r("paste"))[0] === "1", "탭이 빈칸 여러 개로 바뀌어도 같은 것으로");
const lines = src.split("\n"); lines[7] = lines[7].replace(/\d(?=\D*$)/, (d) => String((+d + 1) % 10)); lines.splice(30, 1);
await p.fill("#dst", lines.join("\n")); const pr = await r("paste");
ok(pr[0] === "0" && /^2줄 틀림/.test(pr[1]), "숫자 하나를 틀리고 한 줄을 빼면 '2줄 틀림' · " + pr[1]);
await p.fill("#dst", src);
await p.click("#dlg"); ok(dialogs === 1 && (await r("dialog"))[0] === "1", "확인 창을 누르면 '됨'");
await p.click("#bm"); ok(dialogs === 2 && (await r("bookmark"))[0] === "", "북마크 단추를 화면에서 그냥 누르면 안내만 (채점 안 함)");
await p.evaluate(() => { location.href = document.getElementById("bm").href; }); await p.waitForTimeout(300);
ok((await r("bookmark"))[0] === "1", "북마크로 실행하면 '됨'");
const sum = await p.evaluate(() => [document.getElementById("sum").textContent, document.getElementById("line").textContent]);
ok(/됨 7 \/ 8/.test(sum[0]) && /eval=1 script=1 bookmark=1 paste=1\(61줄 중 0줄 틀림\) dialog=1/.test(sum[1]) && /timer=-/.test(sum[1]), "결과 한 줄 · " + sum[0] + " · " + sum[1]);
await p.click("#save"); await p.waitForTimeout(600);
const saved = E.data().asideSelftest;
ok(saved && saved.ok === 7 && saved.n === 8 && /eval=1/.test(saved.line), "[결과를 시트에 남기기] → asideSelftest 한 줄");
ok(!errs.length, "화면 오류 없음" + (errs.length ? " · " + errs[0] : ""));
if (SHOT) { await p.setViewportSize({ width: 900, height: 1300 }); await p.screenshot({ path: SHOT + "/selftest.png", fullPage: true }); const m = await E.ctx.newPage(); await m.setViewportSize({ width: 390, height: 844 }); await m.goto("https://mfgkorea.github.io/order.html/aside/selftest.html"); await m.waitForTimeout(1200); await m.screenshot({ path: SHOT + "/selftest-390.png", fullPage: true }); const w = await m.evaluate(() => document.documentElement.scrollWidth); console.log("390px 가로 넘침:", w > 390 ? w : "없음"); }
await E.stop();
process.exit(done("기능 시험 화면 시험") ? 1 : 0);
