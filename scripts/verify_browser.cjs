/* Integration check: three isolated browser contexts, real server, real model. */
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");
(async () => {
  const browser = await chromium.launch({
    channel: process.env.MAYA_BROWSER || "msedge",
    headless: true,
  });
  const origin = process.env.MAYA_TEST_URL || "http://127.0.0.1:8003";
  const contexts = await Promise.all([
    browser.newContext({ viewport: { width: 390, height: 844 } }),
    browser.newContext({ viewport: { width: 1440, height: 1000 } }),
    browser.newContext({ viewport: { width: 390, height: 844 } }),
  ]);
  const [customer, judge, recipient] = await Promise.all(
    contexts.map((c) => c.newPage()),
  );
  const errors = [];
  for (const p of [customer, judge, recipient]) {
    p.on("pageerror", (e) => errors.push(e.message));
    p.on("response", (r) => {
      if (r.status() >= 400)
        console.log("HTTP", r.status(), new URL(r.url()).pathname);
    });
  }
  fs.mkdirSync("reports/screenshots", { recursive: true });
  try {
    await customer.goto(origin + "/app/");
    await customer.locator("#sandbox").click();
    await customer.locator("#recipient").selectOption("1");
    await customer.locator("#amount").fill("100.00");
    await customer.locator("#pair").click();
    await customer.locator("#pair-dialog").waitFor({ state: "visible" });
    const code = await customer.locator("#pair-code").innerText();
    await customer.locator("#close-dialog").click();
    await judge.goto(origin + "/demo/");
    await judge.locator("#code").fill(code);
    await judge.locator("#pair-form button").click();
    await judge.locator("#dashboard").waitFor({ state: "visible" });
    await customer.locator("#recipient-pair").click();
    await customer.locator("#pair-dialog").waitFor({ state: "visible" });
    const recipientCode = await customer.locator("#pair-code").innerText();
    await customer.locator("#close-dialog").click();
    await recipient.goto(origin + "/recipient/");
    await recipient.locator("#code").fill(recipientCode);
    await recipient.locator("#pair-form button").click();
    await recipient.locator("#dashboard").waitFor({ state: "visible" });
    await customer.locator("#payment-form button[type=submit]").click();
    await customer.locator("#send").waitFor({ timeout: 20000 });
    await customer.screenshot({
      path: "reports/screenshots/customer-review.png",
      fullPage: true,
    });
    await customer.locator("#send").click();
    await customer
      .locator("h1")
      .filter({ hasText: "Dummy payment completed" })
      .waitFor();
    await judge
      .getByText("Confirmed sandbox transfer", { exact: true })
      .waitFor({ timeout: 15000 });
    await recipient
      .locator("#dashboard")
      .getByText("Confirmed", { exact: true })
      .waitFor({ timeout: 15000 });
    await customer.screenshot({
      path: "reports/screenshots/customer-receipt.png",
      fullPage: true,
    });
    await judge.screenshot({
      path: "reports/screenshots/judge-live.png",
      fullPage: true,
    });
    await recipient.screenshot({
      path: "reports/screenshots/recipient-receipt.png",
      fullPage: true,
    });
    if (
      await customer.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      )
    )
      throw Error("Customer horizontal overflow");
    await customer.locator("[data-nav=home]").click();
    await customer.locator("#check").click();
    const canary = "PRIVATE-CANARY-BROWSER-179284";
    let leaked = false;
    customer.on("request", (r) => {
      if ((r.postData() || "").includes(canary)) leaked = true;
    });
    await customer.locator("#message").fill("Approve to receive your refund");
    await customer.locator("#analyse").click();
    await customer.locator("#check-result .card").waitFor();
    await customer.locator("#message").fill(canary);
    await customer.locator("#analyse").click();
    await customer.locator("#check-result .card").waitFor();
    if (leaked) throw Error("Raw text escaped the browser");
    await customer.locator("[data-nav=settings]").click();
    await customer.locator("#revoke").click();
    await judge.locator("#refresh").click();
    await judge.locator("#error").waitFor({ state: "visible" });
    if (errors.length) throw Error("Browser errors: " + errors.join("; "));
    fs.writeFileSync(
      "reports/browser.json",
      JSON.stringify(
        {
          passed: true,
          origin,
          checks: [
            "three isolated contexts",
            "live observation",
            "ledger-backed recipient receipt",
            "raw-text network canary",
            "revocation",
            "390px overflow",
          ],
          errors,
        },
        null,
        2,
      ),
    );
    console.log(
      "Browser integration passed. Screenshots in reports/screenshots.",
    );
  } catch (e) {
    for (const [i, p] of [customer, judge, recipient].entries()) {
      await p
        .screenshot({
          path: `reports/screenshots/failure-${i}.png`,
          fullPage: true,
        })
        .catch(() => {});
      console.log(
        "Page",
        i,
        await p
          .locator("body")
          .innerText()
          .catch(() => ""),
      );
    }
    console.log("Errors", errors);
    throw e;
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
