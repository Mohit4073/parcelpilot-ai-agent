# AI Tool Usage

I used **Claude** (by Anthropic) as my AI coding assistant for this whole project. I worked with it step by step — building and testing one piece at a time — rather than asking it to generate the entire system at once.

**How I actually used it:**

- **Planning first.** Before writing any code, I went through the assessment with Claude to decide what to build (I chose the internal support chatbot), what tools it needed, and how to handle documents that disagree with each other.

- **Building one piece at a time.** Claude wrote each part of the code — the data loading, the search tool, the calculation logic, the AI agent itself, the backend API, and the frontend chat interface — one file at a time. I ran and tested each piece myself before moving to the next one.

- **Fixing real bugs as they came up.** As I tested things, I ran into real errors — things like a data formatting bug that crashed the AI, an issue where old actions kept reappearing under new messages, a server crash from running out of memory during deployment, a Google AI model name that stopped working, and a deployment error that looked like a permissions issue but was actually something else. I pasted the actual error messages to Claude each time, and it helped me figure out and fix the real cause.

- **Testing against the real data, not made-up examples.** I ran the chatbot against the actual PDFs and spreadsheet provided, and shared the real results back. This caught genuine mistakes — for example, my dashboard initially failed to flag a real urgent ticket as high-priority, because the code was looking for different wording than what was actually in the ticket. I only caught this by checking against the real data.

- **Help with deployment.** Step-by-step help getting the project onto GitHub, and deployed live using Render (backend) and Vercel (frontend), including fixing deployment-specific issues that don't show up when testing locally.

- **Writing this documentation.** This note, the Architecture Note, the Product Note, and the README were all drafted by Claude, based on the real decisions and real bugs from building the project — I reviewed them and they reflect what was actually built.

All the actual decisions — what to build, what trade-offs to make, what to prioritize — were mine. Claude's role was to help me write the code, debug real problems, and think through options along the way.