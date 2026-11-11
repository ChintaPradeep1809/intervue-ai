# Demo credentials (local development only)

`python -m app.seed` creates these accounts. They exist only in your local database. Never reuse
these passwords and never seed a production database with them.

| Role | Email | Password | Lands on |
|---|---|---|---|
| Super admin | `admin@intervue.local` | `Admin@12345` | `/admin` (command center) |
| Organization admin (Sunrise Institute of Technology) | `college@intervue.local` | `College@12345` | `/organization` |
| Candidate (resume pre-uploaded) | `candidate@intervue.local` | `Candidate@12345` | `/dashboard` |

Also seeded:

- 10 fictional students (`*@student.example.edu`, password `Student@1000`–`Student@1009`) with completed
  interviews. They were produced by running the real engine, evaluator and report pipeline on scripted
  answers of varying quality.
- Invite link for the campus template: http://localhost:3000/invite/sunrise-campus-2026
- 7 platform templates (AWS Data Engineer — 2 Years, Python Developer, Software Engineer, AI Engineer,
  Forward Deployed Engineer, Data Analyst, DevOps Engineer), the question bank and 4 plans.

No account is needed for the demo: open http://localhost:3000/demo.

Reset everything with `cd apps/api && python -m app.seed --reset`.
