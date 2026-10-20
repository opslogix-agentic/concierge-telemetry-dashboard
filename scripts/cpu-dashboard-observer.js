// Run inside an authorized, signed-in Playwright session. No private API calls or saved cookies.
// Results are rounded UI observations, not exact native-timestamp pairs.
global.startCpuDashboardSampling = async function (context, target, output, durationMs = 24 * 60 * 60 * 1000, onSample = null) {
    const fs = process.getBuiltinModule('fs');
    const path = process.getBuiltinModule('path');
    fs.mkdirSync(path.dirname(output), { recursive: true, mode: 0o700 });
    const observer = await context.newPage();
    const stopAt = Date.now() + durationMs;
    let busy = false;
    let runs = 0;
    const append = row => fs.appendFileSync(output, JSON.stringify(row) + '\n', { mode: 0o600 });
    const sample = async () => {
        if (busy || observer.isClosed()) return;
        busy = true;
        try {
            await observer.goto(target.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
            if (/login|saml|sso/i.test(observer.url())) throw new Error('Dashboard sign-in required; no credentials will be entered automatically');
            const graph = observer.locator('svg').filter({ has: observer.locator('text').filter({ hasText: 'Load average (%)' }) });
            await graph.waitFor({ state: 'visible', timeout: 45000 });
            const body = await observer.locator('body').innerText();
            if (!body.includes(target.serial)) throw new Error('Selected dashboard serial does not match requested device');
            const points = await graph.locator('rect[stroke="red"]').evaluateAll(nodes => nodes.slice(-15).map(n => {
                const b = n.getBoundingClientRect(); return { x: b.x + b.width / 2, y: b.y + 40 };
            }));
            if (!points.length) throw new Error('CPU chart hover regions unavailable; review UI selectors');
            const observations = [];
            for (const point of points) {
                await observer.mouse.move(point.x, point.y);
                await observer.waitForTimeout(150);
                const text = await observer.locator('body').innerText();
                const section = text.slice(text.indexOf('System Resources'), text.indexOf('Memory'));
                const match = section.match(/Load average \(%\)\s+(\d{2}:\d{2})\s+(\d+(?:\.\d+)?)%/);
                if (match) observations.push({ displayed_time: match[1], displayed_percent: Number(match[2]) });
            }
            if (!observations.length) throw new Error('CPU tooltips could not be read');
            append({ captured_at: new Date().toISOString(), serial: target.serial, model: target.model,
                timezone: await observer.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone),
                observations, precision: 'UI rounds timestamps to minutes and percentages; require unique API-minute match before analysis' });
            runs++;
            if (onSample) await onSample();
        } catch (error) {
            append({ captured_at: new Date().toISOString(), serial: target.serial, error: error.message.split('\n')[0] });
        } finally { busy = false; }
    };
    await sample();
    const timer = setInterval(async () => {
        if (Date.now() >= stopAt || observer.isClosed()) { clearInterval(timer); return; }
        await sample();
    }, 5 * 60 * 1000);
    return { observer, timer, stopAt: new Date(stopAt).toISOString(), getRuns: () => runs, sample };
};
