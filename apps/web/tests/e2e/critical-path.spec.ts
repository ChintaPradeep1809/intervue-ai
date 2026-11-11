import path from "node:path";

import { expect, type Page, test } from "@playwright/test";

const RESUME = path.resolve("tests/e2e/fixtures/resume.docx");

async function answerUntilDone(page: Page) {
  const box = page.getByLabel("Type your answer");
  for (let i = 0; i < 40; i++) {
    if (await page.getByRole("button", { name: "View report" }).isVisible()) return;
    if (await box.isEnabled().catch(() => false)) {
      await box.fill(
        "I would use a window function with row_number partitioned by the key because it is a single pass; the trade-off is memory versus latency, for example on 500 GB per day.",
      );
      await page.getByRole("button", { name: "Send answer" }).click();
    }
    await page.waitForTimeout(700);
  }
}

test("candidate: register → onboarding → plan → consent → interview → report", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;
  await page.goto("/auth/register");
  await page.getByLabel("Full name").fill("Ravi Kumar");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("Password!123");
  await page.getByRole("button", { name: "Create account" }).click();

  // Step 1 — profile
  await expect(page.getByRole("heading", { name: "Tell us about you" })).toBeVisible();
  await page.getByLabel("Years of experience").fill("2");
  await page.getByLabel("Target role").selectOption("aws_data_engineer");
  await page.getByRole("button", { name: /Continue/ }).click();

  // Step 2 — resume
  await page.getByLabel("Drop your resume here").setInputFiles(RESUME);
  await expect(page.getByText(/Detected: .*PySpark/)).toBeVisible();
  await page.getByRole("button", { name: "Continue", exact: false }).click();

  // Step 3 — job description
  await page.getByRole("tab", { name: "Paste JD" }).click();
  await page.getByLabel("Job description").fill("Data Engineer: SQL, PySpark, AWS Glue, Kafka and Redshift. Build reliable batch and streaming pipelines.");
  await page.getByRole("button", { name: /Continue/ }).click();

  // Step 4 — preferences
  await page.getByRole("button", { name: "30 minutes" }).click();
  await page.getByRole("button", { name: "Technical", exact: true }).click();
  await page.getByRole("button", { name: /Generate my plan/ }).click();

  // Step 5 — plan
  await expect(page.getByRole("heading", { name: "Your interview plan" })).toBeVisible();
  await expect(page.getByText("Skills being tested")).toBeVisible();
  await expect(page.getByText(/Apache Kafka/)).toBeVisible(); // JD requirement missing from the resume
  await page.getByRole("button", { name: /Confirm plan/ }).click();

  // Setup — consent; type answers instead of speaking in CI
  await expect(page.getByRole("heading", { name: "System check" })).toBeVisible();
  await page.getByRole("checkbox", { name: /AI processing/ }).click();
  await page.getByRole("checkbox", { name: /Data storage/ }).click();
  await page.getByRole("checkbox", { name: /Use my microphone/ }).click();
  await page.getByRole("button", { name: "Enter interview room" }).click();

  // Room
  await page.getByRole("button", { name: "Start interview" }).click();
  await expect(page.getByText(/Tell me|walk me through/i).first()).toBeVisible();
  await answerUntilDone(page);
  await page.getByRole("button", { name: "View report" }).click();

  await expect(page.getByText("Evaluation by category")).toBeVisible();
  await expect(page.getByRole("img", { name: /Overall: \d+ out of 100/ })).toBeVisible();
  await expect(page.getByText("Question-by-question analysis")).toBeVisible();
});

test("college admin: dashboard, candidates and templates", async ({ page }) => {
  await page.goto("/auth/login");
  await page.getByLabel("Email").fill("college@intervue.local");
  await page.getByLabel("Password").fill("College@12345");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Sunrise Institute of Technology" })).toBeVisible();
  await expect(page.getByText("Interviews completed")).toBeVisible();
  await page.getByRole("navigation", { name: "App" }).getByRole("link", { name: "Candidates" }).click();
  await expect(page.getByRole("link", { name: "Aarav Mehta" })).toBeVisible();
  await page.getByRole("navigation", { name: "App" }).getByRole("link", { name: "Templates & links" }).click();
  await expect(page.getByText("Campus Placement — Data Engineering 2026", { exact: true })).toBeVisible();
});
