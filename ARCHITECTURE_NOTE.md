# Architecture Note — ParcelPilot Internal AI Support Assistant

## How the agent works

The system is built around **one AI agent** (Google Gemini), not several agents working together. The agent can call different "tools" (like looking up an order, or searching a policy document) as many times as it needs to, in whatever order makes sense, before giving a final answer.

For example, if someone asks "Can Northstar cancel this order for free?", the agent might:
1. Look up the order
2. Find out which account it belongs to
3. Search that account's contract
4. Check the standard policy too
5. Compare the two and decide which one applies
6. Give a final answer explaining why

Nobody tells it these exact steps — it figures out what to look up on its own, based on the question.

The agent is given two main rules to follow:
- **Which source to trust first** if two documents disagree (a signed customer contract wins over the general policy, which wins over product docs; old support tickets are never trusted as "the rule").
- **How to judge ticket severity** (P1, P2, P3), based on the definitions in the policy document.

Everything else — like calculating an actual fee or credit amount — is **not** left up to the AI's judgment. That's handled by real code instead (explained below), so the numbers are always exact and consistent.

## The three tools the agent can use

**1. Document search**
Searches the 6 policy/contract/product PDFs to find relevant text. Each document is tagged behind the scenes with things like: is this document current or outdated? Which specific customer does this contract belong to? This means:
- Outdated documents are automatically skipped, unless someone specifically asks about old policy.
- One customer's contract can never accidentally show up when answering a question about a different customer.

**2. Looking up data and doing calculations**
Instead of letting the AI freely query the spreadsheet however it wants, it can only use a fixed set of specific functions — like "get this order's details" or "calculate the cancellation fee for this order." The actual fee/credit rules (like "₹250 fee if cancelled after 30 minutes" or "Northstar never pays a cancellation fee") are written directly into the code. This means the AI never has to do date math or money math in its head — it just calls the right function and reads the answer back.

**3. Taking action (like escalating a ticket)**
This is a two-step process:
- Step 1: the AI can *draft* an action (like "escalate this ticket") — this shows up as a card in the chat for the person to review.
- Step 2: nothing actually happens until the person clicks "Confirm."

The AI has no way to skip step 2 — even if it wanted to, there's no code path for it to confirm its own action. Only a real button click from a real person can do that.

## How documents and data are handled

- **Documents**: the 6 PDFs are read, cleaned up (some had messy formatting), split into sections, and stored in a searchable database along with tags about how trustworthy/current each one is.
- **Spreadsheet data**: loaded into memory when the server starts, with dates properly parsed. All "how much time has passed" calculations use the fixed snapshot time given in the spreadsheet (not the real current time), since this is test data, not live data.

## How the system decides which source to trust

This was the main challenge in the assessment, and it's handled in two ways:

1. **Before the AI even sees anything**: outdated documents and other customers' contracts are filtered out automatically, so they usually don't even reach the AI in the first place.
2. **When the AI is reasoning**: if it does see two sources that disagree (e.g., a contract and the general policy), it's instructed to point out the disagreement and clearly say which one wins and why.

I tested this directly: I asked about two different customers cancelling similar orders. One customer's contract said "no fee, ever" — the system correctly said no fee. The other customer's contract said "just follow the normal policy" — the system correctly charged the standard fee. Same type of question, opposite correct answers, which shows it's actually reading the contracts rather than guessing based on "big customer = free."

I also tested that it won't trust bad information from old support tickets — one old ticket incorrectly said a certain limit was 3,000, but the real current limit is 5,000, and the system correctly went with the real number and explained that old tickets aren't reliable.

Finally, if information needed to answer a question is missing or unclear (like whether a delay was really the carrier's fault), the system is told not to guess — it says so, rather than promising something it can't confirm.

## Key trade-offs I made, and why

- **Chat history is stored in memory, not a database.** Simpler to build, and fine for a demo — but it means restarting the server clears all active conversations. I noted this as a known limitation rather than hiding it.
- **The dashboard uses simple rules, not machine learning.** With this small amount of ticket data, simple rules (like "is this ticket's response time already overdue?") are easier to trust and verify than a machine-learning model would be, and a proper ML approach wouldn't have enough data to actually be more accurate.
- **One AI agent, not multiple agents working together.** Simpler and easier to debug for a project this size, at the cost of not showing off more complex multi-agent coordination.
- **Free hosting plans** were used for both the frontend and backend. The trade-off is that the backend "falls asleep" after being unused for a while, so the very first request after a quiet period can take 30-50 seconds — documented clearly so it doesn't look broken.