# Product Note — ParcelPilot Internal AI Support Assistant

## Which extra problem I chose, and how I solved it

I chose **Problem 1: Proactive Issue Detection** — I added a second "Dashboard" tab next to the chat, so support staff don't have to ask a question to find out something needs attention.

It shows three things, pulled from the same ticket data the chatbot already uses:
- **Tickets that are already late** (past their promised response time) — and it correctly checks each customer's *own* contract terms, not just the generic policy, when deciding what "late" means.
- **Tickets that are close to being late**, so the team can act before it becomes a real problem.
- **Groups of tickets that share the same underlying bug** — for example, if two different tickets are both actually caused by the same known upload issue, they're grouped together instead of looking like two separate problems.

I used simple, rule-based logic here (checking time elapsed, matching keywords to known issues) instead of a machine-learning model. With this small amount of ticket data, simple rules are more accurate, easier to explain to a support manager, and easier to verify are actually correct. A machine-learning approach would need a lot more data to be trustworthy, and here it would just add complexity without adding real value.

I didn't build **Problem 2 (Trust and Reliability)** as a separate add-on feature — because it isn't really a bonus feature, it's something the whole chatbot needed to get right just to meet the basic requirements. Things like "don't trust outdated documents," "a signed contract can override the general policy," and "don't trust old wrong ticket answers" are baked into the core system, not bolted on afterward. That part is explained in the Architecture Note.

## What else I'd build next for ParcelPilot, in order of priority

1. **A permanent record of everything the system has done.** Right now, if the server restarts, all chat history and confirmed actions disappear. In a real support tool, you'd want a permanent, searchable log of every action taken — who approved it, when, and why — both to build trust in the system and for basic accountability.

2. **Connect the "action" tool to a real system.** Right now, "escalating a ticket" just creates a fake record. The natural next step is connecting it to ParcelPilot's actual ticketing system, so a confirmed escalation creates a real, working ticket.

3. **A simple way for staff to say "this answer was wrong."** A thumbs-up/thumbs-down button on each chatbot answer, saved along with the question and which documents it used, would be the fastest way to find out where the system is actually struggling once real people start using it — much better than guessing from a handful of test questions.

4. **A customer-facing version of the chatbot.** The assessment allowed building just one version, and I focused on making the internal one solid rather than splitting time across two shallower ones. A customer version would reuse most of the same tools, but with much stricter rules — a customer shouldn't even be able to *ask* about another company's account, not just be blocked when they try.

5. **Smarter alerts on the dashboard** — like noticing a sudden spike in similar complaints over the last few hours, not just a static count. This becomes genuinely useful once there's a lot more ticket data to work with; not worth over-building for the small amount of data in this assessment.

## What I left out on purpose

- **Real login/security.** Right now you just pick a name from a list — there's no password or real authentication. This is explicitly allowed by the assessment as a shortcut.
- **A second, customer-facing chatbot.** Only one was required; I put my effort into making the internal one solid.
- **A permanent database for chat history.** Everything is stored in memory for simplicity — a known and intentional trade-off, explained in the Architecture Note.
- **Automated tests.** Given the limited time, I focused on manually testing the system against real, tricky examples from the actual data (the contract conflicts, the wrong old ticket, the known-issue matching) instead of writing a formal test suite. In a real production project, tests would be one of the first things I'd add.

## One number I'd track to know if this is actually useful

**How often the chatbot gives a fully correct answer without a human needing to step in and fix or redo it — measured separately for different question types** (like fee/contract questions, credit calculations, and known-issue questions).

The key thing I'd watch for isn't just "did it answer" — it's whether it's **confidently wrong** versus **appropriately cautious**. If the system escalates a genuinely unclear situation instead of guessing, that's a success, not a failure. So really I'd track two related numbers: how often it's right when it does answer directly, and how often it escalates something it actually could have safely answered — because being too cautious has a cost too, just a much smaller one than being confidently wrong.