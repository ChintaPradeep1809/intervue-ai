import { brand } from "@intervue/config";
import {
  BarChart3,
  Brain,
  Building2,
  Check,
  Code2,
  FileText,
  GraduationCap,
  LayoutTemplate,
  Mic,
  MonitorUp,
  Network,
  ShieldCheck,
  UserRound,
} from "lucide-react";

import { InterviewPreview } from "@/components/interview/interview-preview";
import { MarketingFooter, MarketingHeader } from "@/components/layout/marketing";
import { LinkButton } from "@/components/shared/primitives";

const STEPS = [
  { title: "Share your target", body: "Upload your resume and paste a job description — or pick a role like AWS Data Engineer." },
  { title: "Get a tailored plan", body: "The interviewer builds a round-by-round plan weighted to the skills the role actually needs." },
  { title: "Interview out loud", body: "Answer by voice. The interviewer listens, asks adaptive follow-ups and runs coding rounds." },
  { title: "Improve with evidence", body: "Your report quotes what you said and wrote, scores nine categories and gives a practice plan." },
];

const FEATURES = [
  { icon: Brain, title: "Technical interviews", body: "Role-specific questions across SQL, Python, PySpark, AWS, system design and more, with difficulty that adapts to your answers." },
  { icon: Code2, title: "Live coding", body: "Monaco editor with Python, JavaScript, TypeScript and SQL. Code runs in an isolated sandbox with hidden tests." },
  { icon: Mic, title: "Voice interviewer", body: "Speak naturally. Answers are transcribed, follow-ups are spoken back, and you can interrupt at any time." },
  { icon: FileText, title: "Resume & JD personalisation", body: "Questions reference only skills that actually appear on your resume, and prioritise the job's requirements." },
  { icon: Network, title: "System design canvas", body: "Sketch an architecture with real components and connections while you explain your trade-offs." },
  { icon: BarChart3, title: "Evidence-based evaluation", body: "Every score links to verbatim quotes, code or test results. Evidence that can't be verified is discarded." },
];

const AUDIENCES = [
  {
    id: "candidates",
    icon: UserRound,
    title: "For candidates",
    points: ["Practise realistic, role-specific interviews", "See exactly what you missed and why", "Track progress across attempts"],
  },
  {
    id: "colleges",
    icon: GraduationCap,
    title: "For colleges & institutes",
    points: ["Run placement assessments with one invite link", "Cohort dashboards: average scores, weakest skills", "Export results to CSV for placement cells"],
  },
  {
    id: "companies",
    icon: Building2,
    title: "For companies",
    points: ["Consistent first-round technical screens", "Structured, evidence-backed assessments for recruiters", "Humans make the decision — the AI assists"],
  },
];

const PRICING = [
  { name: "Free", price: "₹0", period: "forever", features: ["3 practice interviews / month", "Voice interviewer", "Evidence-based report"], cta: "Start free", href: "/auth/register" },
  { name: "Candidate Pro", price: "₹999", period: "per month", features: ["30 interviews / month", "All roles & coding rounds", "System design canvas", "Progress history"], cta: "Choose Pro", href: "/auth/register", highlight: true },
  { name: "College", price: "₹24,999", period: "per month", features: ["500 interviews / month", "Templates & invite links", "Cohort dashboard & CSV export", "Knowledge base"], cta: "Set up your college", href: "/auth/register?type=organization" },
  { name: "Enterprise", price: "Custom", period: "", features: ["Custom volume & question banks", "SSO and audit exports", "Dedicated support"], cta: "Contact us", href: `mailto:${brand.supportEmail}` },
];

const FAQ = [
  { q: "Is this a replacement for human interviewers?", a: "No. It is a practice and first-round assessment tool. Reports are designed to be reviewed by a person, and the platform never makes hiring decisions on its own." },
  { q: "What do you record?", a: "We store the text transcript, your code and the scores. We don't record audio or video. Screen snapshots are only taken while you are sharing your screen, after explicit consent, and you can stop sharing at any time." },
  { q: "Which browsers support the voice interviewer?", a: "Voice works best in Chrome and Edge. In other browsers you can type your answers — everything else works the same." },
  { q: "How is my code run?", a: "In an isolated sandbox with no network access and strict CPU, memory and time limits — never on our application servers." },
  { q: "Can organisations add their own questions and guidelines?", a: "Yes. Organisations create interview templates and can upload guidelines or role descriptions that shape the interview." },
];

export default function LandingPage() {
  return (
    <div className="flex min-h-full flex-col">
      <MarketingHeader />
      <main id="main" className="flex-1">
        {/* Hero */}
        <section className="relative overflow-hidden border-b">
          <div className="bg-grid pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_at_top,black_30%,transparent_70%)]" />
          <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:py-24">
            <div className="space-y-6">
              <span className="inline-flex items-center gap-2 rounded-full border bg-background px-3 py-1 text-xs text-muted-foreground">
                <span className="size-1.5 rounded-full bg-success" /> Voice, coding and system design in one interview room
              </span>
              <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl">Practice. Interview. Improve.</h1>
              <p className="max-w-xl text-lg text-muted-foreground">{brand.description}</p>
              <div className="flex flex-wrap gap-3">
                <LinkButton href="/auth/register" size="lg" className="h-11 px-5 text-[15px]">
                  Start AI Interview
                </LinkButton>
                <LinkButton href="/demo" size="lg" variant="outline" className="h-11 px-5 text-[15px]">
                  Try a Demo
                </LinkButton>
              </div>
              <p className="text-xs text-muted-foreground">No sign-up needed for the demo · Works in Chrome and Edge · Type answers in any browser</p>
            </div>
            <InterviewPreview />
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-20 sm:px-6">
          <h2 className="text-3xl font-semibold">How it works</h2>
          <p className="mt-2 max-w-2xl text-muted-foreground">From resume to a personalised preparation plan in one sitting.</p>
          <ol className="mt-10 grid gap-6 md:grid-cols-4">
            {STEPS.map((s, i) => (
              <li key={s.title} className="relative rounded-xl border bg-card p-5">
                <span className="grid size-8 place-items-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">{i + 1}</span>
                <h3 className="mt-4 font-medium">{s.title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{s.body}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* Features */}
        <section id="features" className="scroll-mt-20 border-y bg-muted/40">
          <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
            <h2 className="text-3xl font-semibold">Built like a real interview</h2>
            <p className="mt-2 max-w-2xl text-muted-foreground">An explicit interview plan, adaptive follow-ups, and structured evaluation — not a chatbot.</p>
            <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map((f) => (
                <div key={f.title} className="rounded-xl border bg-card p-6 transition-shadow hover:shadow-sm">
                  <f.icon className="size-5 text-primary" />
                  <h3 className="mt-4 font-medium">{f.title}</h3>
                  <p className="mt-1.5 text-sm text-muted-foreground">{f.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Audiences */}
        <section className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
          <div className="grid gap-5 md:grid-cols-3">
            {AUDIENCES.map((a) => (
              <div key={a.id} id={a.id} className="scroll-mt-20 rounded-xl border p-6">
                <a.icon className="size-5 text-primary" />
                <h3 className="mt-4 text-lg font-medium">{a.title}</h3>
                <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
                  {a.points.map((p) => (
                    <li key={p} className="flex gap-2">
                      <Check className="mt-0.5 size-4 shrink-0 text-success" />
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <div id="privacy" className="mt-10 grid gap-6 rounded-xl border bg-card p-6 md:grid-cols-3">
            <div className="flex gap-3">
              <ShieldCheck className="size-5 shrink-0 text-primary" />
              <p className="text-sm text-muted-foreground"><span className="font-medium text-foreground">Consent first.</span> Microphone, screen sharing and AI analysis each need explicit consent. Nothing is recorded silently.</p>
            </div>
            <div className="flex gap-3">
              <MonitorUp className="size-5 shrink-0 text-primary" />
              <p className="text-sm text-muted-foreground"><span className="font-medium text-foreground">Snapshots, not streams.</span> Only compressed screenshots are taken, and only while you share.</p>
            </div>
            <div className="flex gap-3">
              <LayoutTemplate className="size-5 shrink-0 text-primary" />
              <p className="text-sm text-muted-foreground"><span className="font-medium text-foreground">You control your data.</span> Delete an interview or your whole account at any time.</p>
            </div>
          </div>
        </section>

        {/* Pricing */}
        <section id="pricing" className="scroll-mt-20 border-y bg-muted/40">
          <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
            <h2 className="text-3xl font-semibold">Pricing</h2>
            <p className="mt-2 text-muted-foreground">Indicative launch pricing. Payments are not enabled yet — every account starts on Free.</p>
            <div className="mt-10 grid gap-5 md:grid-cols-2 lg:grid-cols-4">
              {PRICING.map((p) => (
                <div key={p.name} className={`flex flex-col rounded-xl border bg-card p-6 ${p.highlight ? "ring-2 ring-primary" : ""}`}>
                  <p className="font-medium">{p.name}</p>
                  <p className="mt-3 text-3xl font-semibold">
                    {p.price} <span className="text-sm font-normal text-muted-foreground">{p.period}</span>
                  </p>
                  <ul className="mt-5 flex-1 space-y-2 text-sm text-muted-foreground">
                    {p.features.map((f) => (
                      <li key={f} className="flex gap-2">
                        <Check className="mt-0.5 size-4 shrink-0 text-success" />
                        {f}
                      </li>
                    ))}
                  </ul>
                  <LinkButton href={p.href} variant={p.highlight ? "default" : "outline"} className="mt-6 h-9">
                    {p.cta}
                  </LinkButton>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="mx-auto max-w-3xl scroll-mt-20 px-4 py-20 sm:px-6">
          <h2 className="text-3xl font-semibold">Frequently asked questions</h2>
          <div className="mt-8 divide-y rounded-xl border">
            {FAQ.map((f) => (
              <details key={f.q} className="group p-5 [&_summary::-webkit-details-marker]:hidden">
                <summary className="flex cursor-pointer items-center justify-between gap-4 font-medium">
                  {f.q}
                  <span className="text-muted-foreground transition-transform group-open:rotate-45">+</span>
                </summary>
                <p className="mt-3 text-sm text-muted-foreground">{f.a}</p>
              </details>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="mx-auto max-w-6xl px-4 pb-20 sm:px-6">
          <div className="flex flex-col items-start justify-between gap-6 rounded-2xl bg-studio p-10 text-studio-foreground md:flex-row md:items-center">
            <div>
              <h2 className="text-2xl font-semibold">Your next interview starts with practice.</h2>
              <p className="mt-2 text-studio-foreground/70">Try the AWS Data Engineer demo in under ten minutes — no account required.</p>
            </div>
            <div className="flex gap-3">
              <LinkButton href="/demo" variant="secondary" className="h-10 px-4">Try a Demo</LinkButton>
              <LinkButton href="/auth/register" className="h-10 px-4">Start AI Interview</LinkButton>
            </div>
          </div>
        </section>
      </main>
      <MarketingFooter />
    </div>
  );
}
