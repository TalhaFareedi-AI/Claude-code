# Chatbot Harness and Platform Plan

Oct 14, 2026 · @Talha

## 1. Start here

**Clear meaning:** You are building two things. The **harness** is the manager code around the AI. The **platform** is the website, accounts, credit wallet and payments.

Think of the AI model as a very smart student. The harness is the teacher who gives it the right question, the right tools and a time limit, then checks its work.

### The 8 big ideas

1. **Cheap brain for easy work, strong brain for hard work.** A router picks the model. This alone cuts AI cost by about two thirds (section 8).
2. **Charts run in the user's browser.** The AI writes a small chart recipe once. Moving a slider after that costs 0 tokens (section 5).
3. **Big jobs: plan first, show the cost, then run.** Like Cursor: a to-do list, step-by-step work, then a check (section 3).
4. **Count every token of every AI call.** Save each call like a line on a bank statement (section 8).
5. **Sell credits, not tokens.** Each credit has a fixed AI cost limit, so every sale keeps a profit (section 9).
6. **Let the user pick the mode and the brain.** Think Again, Overthink, Council, Two Brains, Think Team and more, on Chinese or Western models through OpenRouter. The price shows first and caps stop runaway loops (sections 3 and 8).
7. **Skills on demand.** Developer mode opens a recipe card only when the task needs it, so it stays cheap (section 13).
8. **See every step.** The screen shows the plan, the tools and the files live, in a private folder for each user (section 14).

### What I assumed

- You use OpenRouter, one API key for many AI models. Prices here are what OpenRouter, Anthropic and Google showed on 14 Oct 2026 (see Sources). They change often, so the app reads them live.
- Chinese-lab models (DeepSeek, Qwen, Kimi, GLM, MiniMax) sit next to Western ones. The user picks, and a privacy label shows which route runs (section 11).
- Users are students, teachers and self-learners.
- Money is in US dollars. If you sell in Korea, use won with the same math.
- Numbers marked "example" teach the method. Replace them with your real numbers after launch.

### Word list

| Word | Simple meaning | Everyday example |
| --- | --- | --- |
| Model (LLM) | The AI brain that reads and writes text | A very smart student |
| Token | A small piece of a word. 100 English words is about 130 to 175 tokens | "playing" = "play" + "ing" |
| Input tokens | Everything you send to the AI | The question paper |
| Output tokens | Everything the AI writes back. On Claude it costs 5 times more than input | The answer sheet |
| Context window | The most tokens the AI can read at once | The size of a desk |
| Harness | Your code that controls the AI: what it reads, which tools, when to stop | Manager + rules + toolbox |
| Agent | An AI that works in steps and uses tools by itself | A worker with a to-do list |
| Tool | A function your code runs when the AI asks for it | Calculator, camera, printer |
| Prompt | The instruction text you send | A work order |
| Prompt chaining | The output of one prompt becomes the input of the next | A factory assembly line |
| Cache | A saved copy of repeated text, so it costs less next time | A photocopy instead of rewriting |
| JSON | A fixed text format that code can read | A filled-in form |
| Credit | Your platform's coin | An arcade token |
| Ledger | A list of every credit added or used | A bank statement |
| Margin | The share of money left after all costs | Your profit share |
| OpenRouter | One website and one API key that reaches hundreds of AI models | A food court: one counter, many kitchens |
| Mode | A ready-made way of thinking that the user picks with a tap | The gears of a bicycle |
| Reasoning tokens | The scrap-paper tokens a model writes before its answer. Paid like output | Rough work on an exam sheet |
| Skill | A folder with a SKILL.md recipe that the AI opens only when needed | A recipe card in a drawer |
| MCP | A standard plug that lets an AI app use outside tools | A USB port for tools |

Sections: 2 Big picture · 3 Harness · 4 Smart thinking · 5 Interactive charts · 6 Images, docs, PPT · 7 Teaching mode · 8 Tokens · 9 Credits and pricing · 10 Tech stack · 11 Safety · 12 Roadmap · 13 Developer mode and GitHub kit · 14 The screen, files and tools · 15 The whole plan on one page · 16 The agent team · 17 Fast, clean front end

## 2. The big picture

**Clear meaning:** Every message takes the same path: gateway, router, then the cheap path or the planner, then checker, teacher layer and meter.

&#91;embedded content: harness architecture · 14 parts, all AI calls via OpenRouter\]

Only hard jobs reach the planner and the tools. Every path ends at the meter, so no AI call goes uncounted. The dashed box is OpenRouter, the one door every AI call goes through. The mode picker lets the user choose a mode and a brain before the router runs.

The same system as a restaurant:

| Restaurant | Your platform | Its job |
| --- | --- | --- |
| Customer | User | Asks for something |
| Waiter | Chat app | Takes the order, brings the food |
| Head chef | Planner | Turns a big order into steps |
| Cooks | Tools | Chart, image, PPT, document, calculator |
| Taste tester | Checker | Stops bad food leaving the kitchen |
| Recipe book | Prompt library | Same good recipe every time |
| Notes on the customer | Memory | "No spicy food", "likes cricket" |
| Cashier | Meter + wallet | Counts what was used and charges for it |

## 3. The harness: how one message is handled

**Clear meaning:** The harness runs the same checklist for every message, so the bot is fast on easy questions and careful on hard ones.

### The journey of one message

1. **Receive.** The user sends text, a file, or clicks a button.
2. **Wallet check.** Does the user have enough credits? For big jobs, hold the estimated credits first (section 9).
3. **Build the desk.** Collect what the AI should read: rules, user profile, a short summary of old chat, the last few messages, matching notes (section 4).
4. **Route.** A small, cheap model (or a simple rule) labels the message and picks a mode.
5. **Plan (big jobs only).** The planner writes a to-do list and shows it to the user.
6. **Do the steps.** Each step calls a model or a tool. The result of one step feeds the next.
7. **Check.** Code tests what it can (math, chart recipe, file opens). A cheap model checks the rest. At most 2 fix attempts.
8. **Teacher layer.** Rewrite in simple words, add an everyday analogy, add 2 or 3 "next step" buttons.
9. **Bill.** Add up tokens and tool costs, turn them into credits, write them to the ledger.
10. **Learn.** Update the user's profile in the background: level, interests, weak topics.

### What the router sends back (example)

```json
{
  "mode": "normal",
  "intent": "teach",
  "needs": ["chart"],
  "make_plan": false,
  "auto_image": false,
  "est_credits": 8
}
```

- **mode:** Fast, Normal or Deep, or the mode the user already picked in the mode picker (below).
- **intent:** what the user wants: teach, solve, make\_ppt, make\_doc or chat.
- **needs:** which tools to get ready.
- **make\_plan:** true only for multi-step jobs.
- **auto\_image:** true only if the image rules allow it (section 6).
- **est\_credits:** the cost you show before big jobs.

Use plain rules before the AI router whenever you can. Example: the user clicked "Make PPT", so the intent is make\_ppt and no AI call is needed. Rules cost nothing.

### Three thinking modes (like Cursor)

| Mode | Model (example) | Thinking | Max steps | Typical credits |
| --- | --- | --- | --- | --- |
| Fast | Claude Haiku 5.5 | Off | 1 | 1 |
| Normal | Claude Sonnet 5.5 | Small | 3 | 5 to 10 |
| Deep | Claude Opus 5.5 | Large | 8 | About 120, shown before it starts |

"Thinking" means the model writes rough work before the final answer, like a student using scrap paper. More scrap paper helps on hard problems, but every token on it is paid as output. So each mode gets a thinking budget: the most scrap paper it may use. Most model APIs let you set this.

The models in this table are only defaults. The mode picker at the end of this section lets the user choose the mode and the brain, and the router keeps that choice.

### The agent loop: think, do, check

It works like a map app. It plans a route, drives one step, looks where it is, and re-routes if something went wrong.

```python
plan = planner.make_plan(goal)              # to-do list, shown to the user
for step in plan.steps[:MAX_STEPS]:          # never more than 8 steps
    if meter.task_credits() > task.max_credits:
        return ask_user("This needs more credits. Continue?")
    result = run(step)                       # one AI call or one tool
    if not checker.ok(result):
        result = fix(step, result)           # at most 2 tries
    plan.update(step, result)                # re-plan if needed
answer = teacher.simplify(plan.results, user.profile)
wallet.settle(task)                          # charge the real cost
```

Three safety stops: a step limit, a credit limit per task, and a time limit (for example 3 minutes). When one is reached, the agent stops and asks the user.

### Thinking on its own, with a spending limit

The AI is like a trusted employee with a company card. It can buy small things alone. Big things need a "yes" from the boss.

| What the AI wants to do | Can it do it alone? |
| --- | --- |
| Think, plan, use the calculator, write a chart recipe or a diagram | Yes, these are cheap |
| Make an image or search the web | Yes, if it fits the user's auto-spend limit (default 20 credits per task) |
| Start a big job: PPT, document, Deep task | Show the plan and the estimate, ask once |
| Anything above the user's limit | Always ask |

It can also suggest the next move by itself, as free buttons: "Show a graph", "Quiz me", "Explain simpler".

### Mode picker: more ways to think (web and app)

**Clear meaning:** A mode is a ready-made way of thinking. The user picks one with a tap, like choosing a gear on a bicycle. Fast, Normal and Deep are the first three gears. Seven more are added here, and every mode shows its price before it starts.

| Mode | What happens | Steps | Brain |
| --- | --- | --- | --- |
| Fast | One quick answer, no scrap paper | 1 | Quick |
| Normal | One answer with a little thinking | 1 | Quick or Smart |
| Deep | Plan, do the steps, check (the loop above) | Up to 8 | Smart or Genius |
| Think Again | Write, get marked by a critic, rewrite. Repeat up to 5 times | 2 to 11 | A writer and a critic (can differ) |
| Overthink | Several long-thinking tries, then a judge picks the best | 4 to 6 | One Genius brain |
| Council | 3 to 5 different brains answer alone, then a judge merges them and shows where they disagree | 4 to 6 | The user picks the members |
| Two Brains | One brain thinks and writes short notes, a second brain reads them and writes the answer | 2 | A thinker and an answerer, both picked by the user |
| Think Team | 2 to 5 brains think about the same question and write notes, one answerer reads all the notes and writes the reply | 3 to 6 | The user picks the thinkers and the answerer |
| Research | Plan search questions, search the web, read, answer with links | 3 to 8 | Smart |
| Developer | The Deep loop plus skills for design, code, research and prompts (section 13) | 4 to 10 | A coding brain |

Three tiers of brains: **Quick** is cheap and fast (routing, simple answers, critics). **Smart** is a good all-rounder (the default for most work). **Genius** is the strongest and most expensive (Overthink, judges, hard Deep tasks). Real models and prices for each tier are in section 8.

### How Think Again, Overthink and Council work

Everyday picture first:

- **Think Again** is a student who writes an essay, a teacher marks it, and the student rewrites it.
- **Overthink** is three students solving one hard question on separate sheets, then a teacher compares the sheets.
- **Council** is asking three different teachers, then one person writes a summary and notes where the teachers disagreed.

&#91;embedded content: thinking modes · 5 flows, 1 loop\]

Read each row from left to right. Think Again goes round a loop until the answer is good enough. Overthink and Council run their tries at the same time, then a judge decides. Two Brains hands short notes from a thinker to an answerer, and Think Team does the same with up to 5 thinkers.

Think Again as a loop. This is the "think again and again" mode:

```python
answer = write(question)                           # round 0: the first draft
for r in range(1, max_rounds + 1):                 # default 2 rounds, the user can raise it to 5
    if meter.task_credits() + next_round_cost > task.max_credits:
        break                                      # stop 1: money
    review = critic(question, answer)              # {"score": 1 to 10, "problems": [...]}
    if review.score >= 8:
        break                                      # stop 2: good enough
    answer = rewrite(question, answer, review.problems)
return answer                                      # stop 3: no rounds left
```

Overthink and Council use the same kind of stops, but their tries run side by side, not in a loop:

```python
# Overthink: one question, several long-thinking tries, one judge
tries = run_parallel(n=3, model=user.thinker, effort="high", max_tokens=8000)
final = judge(question, [t.answer for t in tries])   # the judge reads the answers, not the scrap paper

# Council: different brains answer alone, one judge merges
answers = run_parallel(models=user.council, effort="medium")
final = judge(question, answers)                     # lists agreement and disagreement, then merges
```

- `run_parallel` starts all tries at once, so the user waits for the slowest one, not for the sum.
- More thinking is not always better. On an easy question it only costs money, so the router may suggest Fast and say why.
- A different brain as critic or judge gives a second opinion. The same brain may repeat its own mistake.
- Research follows the pattern of GPT Researcher and STORM: a planner writes search questions, helpers search and read, a writer joins the findings with links (section 13).

### Two Brains: one thinks, another answers

**Clear meaning:** In Two Brains, one model does the hard thinking and writes short notes. A second model reads the notes and writes the reply the user sees. You can mix labs: Qwen thinks and DeepSeek answers, or GPT thinks and Claude answers.

Everyday picture: a clever friend works out a maths problem on scrap paper and hands you a few notes. A good teacher reads the notes and explains it in simple words. Two people, each doing what they do best.

How it runs:

1. The thinker brain reads the question and the user's context, thinks as long as its cap allows, and writes short working notes: the plan, key facts, the steps and the result it reached.
2. The harness keeps only the notes (about 1,000 tokens), not the whole scrap paper.
3. The answerer brain reads the question plus the notes and writes the final reply in the user's style: simple words, an analogy, next-step buttons.
4. Optional: a critic brain checks the reply, like Think Again.

Mixes to offer (examples; model names and tiers as in section 8):

| Mix | Thinker | Answerer | Why |
| --- | --- | --- | --- |
| Cross-lab, low price | Qwen3.8 Max (0902) | DeepSeek V4 Pro 0813 | Both Chinese labs, low prices |
| Best of both | GPT-6.1 Sol Pro | Claude Sonnet 5.5 | One lab's thinking, another lab's writing |
| Cheap thinker, strong writer | DeepSeek V4 Pro 0813 | Claude Opus 5.5 | Low thinking bill, polished answer |

Rules that make it work:

- Pass notes, not raw scrap paper. Some models hide their scrap paper or show only a summary. So tell the thinker to write the notes as its normal answer, in a fixed JSON shape, capped at about 1,000 tokens.
- The answerer treats the notes as help, not orders. It may disagree and fix a mistake. It shows the notes only if the user asks "show your thinking".
- The two steps run in a line, so the user waits for both. Show "Thinking with Qwen..." while the thinker works, then stream the answer.
- The question goes to both hosts, so the privacy label and the private route switch must cover both brains (section 11).
- If the thinker runs out of max\_tokens and the notes come back empty, retry once at lower effort, or let one brain do both steps.

Role slots work for any chain. A mode is a list of roles, and every role has a brain slot. Two Brains has think and answer. Think Again has writer and critic. Council has members and a judge. Deep and Developer can have planner, worker and checker. The picker shows "Advanced: choose a brain for each role", and the defaults work if the user ignores it. This is how one agentic chain can use a different brain at every step.

One Two Brains row (example):

```json
{
  "id": "two_brains",
  "name": "Two Brains",
  "steps": ["think", "answer"],
  "slots": {"think": "moonshotai/kimi-k3", "answer": "deepseek/deepseek-v4-pro-0813"},
  "reasoning": {"think": {"effort": "high"}, "answer": {"effort": "none"}},
  "max_tokens": {"think": 8000, "answer": 1500},
  "notes_max_tokens": 1000,
  "max_credits": 60,
  "plans": ["student", "pro", "school"]
}
```

- slots is one brain per role. Copy each model's exact name from OpenRouter's list.
- reasoning and max\_tokens are set per role, so the thinker can think hard while the answerer does not think at all.
- Credits for this mode are in section 9, step 2b.

### Think Team: many thinkers, one answerer

**Clear meaning:** In Think Team, the user picks 2 to 5 models to think about the same question. One more model reads every set of notes and writes the single reply. It is Two Brains with a team of thinkers.

Everyday picture: three friends each work out the same problem on their own paper. One teacher reads all three sets of notes, sees where they agree or differ, and explains the best answer.

How it differs from Council: Council members write full answers and a judge merges them. Think Team thinkers write only short notes, and the answerer writes the one reply the user sees, so the user reads one clean answer, not three.

How it runs:

1. The harness sends the same question and context to every thinker at the same time.
2. Each thinker writes short notes (about 500 tokens): its plan, key facts, steps and result.
3. The answerer reads every set of notes, each labelled with the thinker's name. It compares them, trusts the best reasoning, and says so when the thinkers disagree.
4. The answerer writes one reply in the user's style: simple words, an analogy, next-step buttons.

Rules that keep it safe:

- Mix labs. Thinkers from different labs make different mistakes, so the answerer can spot them.
- Run the thinkers in parallel, so the user waits for the slowest one, not for the sum.
- If one thinker fails, carry on with the rest. If fewer than 2 are left, fall back to Two Brains.
- Cap the notes, about 500 tokens each, so the answerer's input stays small.
- Give Think Team a daily limit and a credit cap, like Overthink and Council. The price is the sum of all thinkers plus the answerer, shown before it starts.
- The question goes to every host, so the privacy label and the private route switch must cover every brain in the team (section 11).

In the settings row, think becomes a list:

```json
{
  "id": "think_team",
  "name": "Think Team",
  "steps": ["think", "answer"],
  "slots": {"think": ["moonshotai/kimi-k3", "deepseek/deepseek-v4-pro-0813", "anthropic/claude-haiku-5.5"], "answer": "anthropic/claude-sonnet-5.5"},
  "min_thinkers": 2,
  "max_thinkers": 5,
  "notes_max_tokens": 500,
  "max_credits": 80,
  "plans": ["pro", "school"]
}
```

### Pick the brain: Chinese models or others

**Clear meaning:** The mode decides how the AI works. The brain (the model) decides who does the work. The user can choose both, and the price is shown before the start.

| Control | What the user sees | Default |
| --- | --- | --- |
| Mode | The 10 modes above | Normal |
| Brain | A list grouped as Quick, Smart, Genius. Each row shows the lab (Chinese or Western), "thinks: yes or no" and a price level. Chains show one list per role | Chosen by you |
| Effort | Chips: Auto, Off, Low, Medium, High, Max (see the effort section below) | Auto |
| Rounds or tries | A slider from 1 to 5 | 2 rounds, 3 tries |
| Cost cap | A slider in credits | 20 credits, the auto-spend limit |
| Estimate | "Up to 35 credits; the unused part comes back" | Updates on every change |
| Private route | A switch that allows only hosts that do not keep or train on prompts (section 11) | On for School accounts |

- Chinese-lab brains you can offer: DeepSeek, Qwen (Alibaba), Kimi (Moonshot), GLM (Z.ai) and MiniMax. Others: Claude, GPT and Gemini. All sit behind one OpenRouter key.
- The list comes live from OpenRouter (section 10). Your own table adds the tier, the lab tag and an on/off switch, so a new model appears only after you approve it.
- Show "thinks: yes" only when OpenRouter's model list says the model supports thinking, and send the thinking setting only to those models.
- A cheap input price does not mean cheap thinking, because thinking is paid as output. Kimi K3 costs $0.70 in and $15 out per million tokens. Claude Sonnet 5.5 costs $2 in and $10 out. For Overthink, Kimi K3 looks cheaper but costs more (section 9).

### Effort: how hard to think (Low, Medium, High)

**Clear meaning:** Effort is a dial for how much scrap paper a brain may use before it answers. Low is a quick think. High is a long think. More effort costs more and takes longer, and it only helps on hard questions.

Everyday picture: an exam. Low is a glance, then write. Medium is a few lines of rough work. High is a full page of rough work before the answer.

| The user picks | Sent to OpenRouter as | Share of max\_tokens for thinking | Good for |
| --- | --- | --- | --- |
| Auto | The router chooses one of the rows below | Varies | Default. It shows its choice |
| Off | effort: "none" | 0 | Greetings, rewrites, simple facts |
| Low | effort: "low" | About 20% | Questions with 1 or 2 steps |
| Medium | effort: "medium" | About 50% | Most homework, charts, short plans |
| High | effort: "high" | About 80% | Hard maths, code, plans with many parts |
| Max | effort: "xhigh" | About 95% | The hardest jobs. Pro plan only |

The shares are from [OpenRouter's reasoning page](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens), 14 Oct 2026. They are a ceiling, not a promise: on an easy question a model may think much less.

What each level can cost, as a worked example:

- Input: Claude Sonnet 5.5, max\_tokens = 8,000, output price $10 per million tokens. Thinking is paid as output.
- Step: thinking ceiling = 8,000 × share. Low: 1,600 tokens, $0.016, × 1.055 ÷ 0.003 = 5.6, so 6 credits. Medium: 4,000 tokens, $0.04, 14.1, so 15 credits. High: 6,400 tokens, $0.064, 22.5, so 23 credits. Max: 7,600 tokens, $0.076, 26.7, so 27 credits.
- Output: the scrap paper alone can cost from 6 to 27 credits, before the answer is counted. The answer is billed on top.

Thinking tokens come out of max\_tokens, so a high effort leaves less room for the answer. At High only 1,600 tokens are left for the reply, and at Max only 400, so the answer may be cut short or come back empty. Raise max\_tokens when you raise effort. At Max with max\_tokens = 16,000 the ceiling is 15,200 tokens, which is 54 credits.

Rules:

- Defaults per mode (example): Fast off, Normal low, Deep medium. Think Again: writer medium, critic low. Overthink: each try high. Council: members medium, judge low. Two Brains: thinker high, answerer off. Think Team: thinkers medium, answerer off.
- Plan limits (example): Free can use Off and Low. Student can go up to High. Pro can use Max.
- Show effort beside the credit estimate. When the user moves the dial, the estimate changes at once.
- Send effort only to models that support it. Some models take a token budget instead of a level (Claude, Gemini and some Qwen models). For those, send max\_tokens inside reasoning, set to the share times max\_tokens. Never send both.
- Auto saves money: the router picks Low or Off for easy questions (section 8, trick 1).

### One picker for web and app

The website and the phone app both ask your server for the list of modes and the list of models. Add a mode or hide a model once, and both update at the same moment, with no app-store release.

One mode is one database row (example):

```json
{
  "id": "think_again",
  "name": "Think Again",
  "steps": ["write", "critic", "rewrite"],
  "default_brains": {"write": "deepseek/deepseek-v4-pro-0813", "critic": "anthropic/claude-haiku-5.5"},
  "reasoning": {"effort": "medium"},
  "default_rounds": 2,
  "max_rounds": 5,
  "stop_score": 8,
  "max_tokens_per_call": 4000,
  "max_credits": 80,
  "plans": ["student", "pro", "school"]
}
```

- `steps` are the roles in the loop. `default_brains` are the starting picks, written the way OpenRouter writes model names (lab/name).
- `reasoning` is how hard to think. OpenRouter takes either `effort` (none, minimal, low, medium, high, xhigh or max) or a token budget called `max_tokens`, never both. Each model supports one or both.
- `max_rounds`, `stop_score` and `max_credits` are the three stops. `plans` says who may use the mode.

### Stop loops from burning credits

- Hold the maximum credits first, charge the real cost, release the rest (section 9).
- Thinking can use up the whole `max_tokens` and leave an empty answer, and you still pay. Set `max_tokens` high enough and check `finish_reason`. If it says `length` with no text, retry once at a lower effort and tell the user.
- Give Overthink and Council a daily limit per user (example: 5 a day on Pro).
- Show the running cost after every round, plus a "Stop here" button that keeps the best answer so far.

## 4. Smart thinking: analogies, prompt chains, memory

**Clear meaning:** Good teaching comes from three habits: compare new ideas to familiar things, split big jobs into small prompts, and remember who the user is.

### Analogy engine (4 steps)

1. **Find the core idea** in one sentence: "electric current is a flow pushed by a pressure".
2. **Pick a familiar world.** Prefer the user's interests from memory (cooking, cricket, games). If none fits, use a classic one.
3. **Map each part** in a small table.
4. **Say where it breaks,** so the learner is not misled.

Example of what the AI should produce:

| Electricity | Water pipe |
| --- | --- |
| Voltage (the push) | Water pressure |
| Current (the flow) | How much water flows each second |
| Resistance | A narrow part of the pipe |
| Where it breaks | An open pipe spills water. An open switch just stops the flow. |

Keep analogies that users rate well in an **analogy library**. Reusing a proven one costs almost nothing.

### Prompt chaining: the backend writes its own prompts

A chain works like a factory line: each worker does one small job well and passes it on. Example request: "Make a 10-slide PPT on photosynthesis".

1. **Outline prompt** gives 10 slide titles.
2. **Slide prompt,** once per slide, gives bullets, speaker notes and a picture idea.
3. **Image-prompt writer** (cheap model) turns each picture idea into a detailed prompt for the image model. Your backend writes this prompt itself; the user never sees it.
4. **Image model** makes the pictures.
5. **Plain code, no AI,** builds the .pptx file.
6. **Checker** finds text that is too long or a missing picture.

Rules that keep chains reliable:

- Every step answers in JSON with a fixed shape, called a schema, so code can read it.
- Prompts live in a prompt library with version numbers (v1, v2), not inside your code.
- Before changing a prompt, run it on your fixed test questions and compare scores (section 11).

### Memory and personalization

The profile is a small card about the user. Keep it under about 200 tokens.

```json
{
  "level": "beginner",
  "interests": ["cricket", "cooking"],
  "language": "English",
  "likes": "short answers, step-by-step math",
  "weak_topics": ["fractions"],
  "goal": "pass physics exam"
}
```

- **How it fills:** a short form at sign-up, then a cheap model updates it after each chat.
- **How it is used:** it picks the analogy world, the depth, the language and the examples.
- **Privacy:** the user can see, edit and delete it.

### Context budget: what goes on the AI's desk

The AI reads a desk of limited size. Your harness decides what goes on it, with a token budget for each part.

| Part | Max tokens (example) | Note |
| --- | --- | --- |
| Rules + tool list | 3,000 | Same for everyone, so it is cached and cheap |
| User profile | 200 | The card above |
| Summary of old chat | 500 | Rewritten every few turns |
| Last 4 to 6 messages | 3,000 | Kept word for word |
| Notes or file parts | 3,000 | Only the parts that match the question |
| Tool results | 2,000 | Trimmed before sending |
| **Total** | **about 11,700** |  |

"Notes or file parts" works like an open-book exam: search the user's notes and put only the matching pages on the desk. This is called RAG (retrieval). When the desk is nearly full, summarize the oldest part. This is called compaction.

## 5. Interactive charts and graphs (like Claude)

**Clear meaning:** The AI writes a small chart recipe once. The user's browser draws it with hover labels and sliders, and redraws it instantly when an input changes, with no new AI call.

### How it works

1. The AI writes a **chart recipe** in JSON (about 1,000 to 1,500 tokens).
2. Your backend checks the recipe: the right shape, and the formula gives real numbers at the lowest, default and highest input.
3. The browser reads the recipe, draws the input boxes and sliders, then draws the chart with a chart library.
4. Hovering a point shows its values. The chart library does this for free.
5. When the user moves a slider, the browser recalculates every point and redraws. No server call, 0 tokens.
6. An optional "Explain what changed" button calls the cheap model (1 credit).

### Example recipe: savings growth

```json
{
  "chart": "line",
  "title": "How savings grow",
  "inputs": [
    {"id": "P", "label": "Start money ($)", "type": "number", "value": 1000},
    {"id": "r", "label": "Interest % per year", "type": "slider", "min": 0, "max": 20, "step": 0.5, "value": 5},
    {"id": "n", "label": "Years", "type": "slider", "min": 1, "max": 40, "value": 10}
  ],
  "x": {"label": "Year", "from": 0, "to": "n"},
  "lines": [{"name": "Money", "formula": "P * (1 + r/100)^x"}]
}
```

The formula in the recipe, written as math:

```latex
\text{money} = P \times \left(1 + \frac{r}{100}\right)^{x}
```

What it means, step by step:

- **Input:** P = 1,000 (start money), r = 5 (percent per year), x = 2 (years).
- **Step:** each year the money is multiplied by (1 + 5 ÷ 100) = 1.05. The small x on top means "do it x times". Two years: 1,000 × 1.05 × 1.05.
- **Output:** 1,102.50 dollars after 2 years.

### Two levels of interactivity

|  | Level A: chart recipe | Level B: mini-app |
| --- | --- | --- |
| What the AI writes | A small JSON recipe | A small web page (HTML + JavaScript) |
| Tokens per chart | About 1,000 to 1,500 | About 3,000 to 8,000 |
| Safety | Very safe: no AI code runs | Must run inside a locked box |
| Good for | Line, bar and pie charts, sliders, comparisons | Simulations, physics, sorting animations, games |
| When to build | First (Phase 1) | Later (Phase 3) |

The locked box is a **sandboxed iframe**: a mini web page on a separate domain. Code inside it can play, but it cannot read your site, the user's login, or the internet.

### Tools to use

- **Chart library:** Apache ECharts or Plotly.js. Hover, zoom and legends are built in.
- **Formula calculator:** math.js. It reads math formulas without running real code.
- **Never** run AI-written formulas with JavaScript eval(). Eval runs any code, including harmful code.
- **Reuse:** the same recipe can go into PPT and documents as a picture or a real chart (section 6).

## 6. Images, diagrams, documents and PPT

**Clear meaning:** Use the cheapest picture that does the job: drawn diagrams for labeled ideas, image models only for real-looking pictures, and fixed templates for files.

### When to make an image

| Situation | What to make |
| --- | --- |
| The user asks for an image | Image model. Show the credits first for premium quality |
| A labeled idea: circuit, water cycle, flowchart | An SVG or Mermaid diagram written by the AI: cheap, exact labels, editable |
| A visual topic in teaching mode, within the auto-spend limit and the daily cap | 1 image, made automatically |
| Anything else | No image |

**SVG** is a picture described in text (lines, boxes, words), so a text model can draw it. **Mermaid** is a short text language that turns into flowcharts.

### Image flow

1. The answer step suggests a picture idea.
2. A cheap model writes the detailed image prompt.
3. A safety check reads the prompt.
4. The image model makes the picture.
5. Your code saves it to file storage and shows it.

Image prices for one 1024 × 1024 picture ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), 14 Oct 2026):

| Model | Price per image | Use it for |
| --- | --- | --- |
| Nano Banana 2.1 | $0.0336 | Default pictures |
| Nano Banana Pro | $0.134 | Premium option |

Batch mode costs half for both, but it is slow. Use it for background jobs only.

### Documents (Word and PDF)

1. Outline prompt gives the headings.
2. Section prompts, one per section, write the text. Each one sees the outline.
3. Charts (from the same chart recipe) and images go where the text marks them.
4. Code turns the text into a Word file (python-docx or Pandoc) or a PDF (an HTML page printed by a headless browser, which is a browser with no screen running on your server).
5. Checker: no empty section, no broken image.

### PPT slides

The AI never writes the PPT file itself. It writes slide data in JSON, and your code builds the file from your own design templates.

```json
{
  "title": "How plants make food",
  "bullets": ["Leaves catch sunlight", "Roots bring water", "Air gives carbon dioxide", "Result: sugar and oxygen"],
  "visual": {"type": "image", "prompt": "simple cartoon leaf with sun and water arrows"},
  "notes": "Ask: where does the plant get water?"
}
```

- At most 5 bullets per slide, at most 12 words each.
- Charts become real, editable PPT charts.
- Start with 2 or 3 templates made by a designer.
- Build with python-pptx (Python) or PptxGenJS (JavaScript).
- For the preview, LibreOffice turns the file into page images.
- Show the credit estimate before starting (section 9).

## 7. Teaching mode

**Clear meaning:** Teaching mode makes the bot act like a patient tutor: it matches the learner's level, explains in small steps, then checks understanding.

| Feature | What the user sees | How you build it |
| --- | --- | --- |
| Level match | Answers fit beginner, medium or advanced | Profile level + the router reads the question |
| Explain simpler | A button that re-explains in easier words | The cheap model rewrites the last answer |
| Step-by-step math | Input → Step → Output for every calculation | A rule in the teaching prompt + the calculator tool |
| Analogy | A familiar comparison with a small mapping table | The analogy engine (section 4) |
| Check question | One quick question after each explanation | An extra JSON field in the same answer call |
| Quiz and flashcards | Clickable quiz cards | The AI writes quiz JSON; your app draws it |
| Interactive explainer | A graph with sliders | The chart recipe (section 5) |
| Mistake memory | Later review of weak topics | weak\_topics in the profile |
| Teacher tools | Lesson plan, worksheet, class slides | The document and PPT chains (section 6) |

Two rules make it trustworthy:

- **No mental math.** The AI never does long math in its head. It calls a calculator or code tool, so numbers are exact.
- **Next-step buttons.** After each answer, show 2 or 3 buttons such as "Show a graph", "Quiz me", "Explain simpler". The AI suggests them inside the same call, so they cost almost nothing.

## 8. Tokens: prices, counting and saving

**Clear meaning:** Tokens are your biggest cost, so count every one and use four tricks that cut the bill by more than half: routing, caching, summarizing and browser-side charts.

### Current prices (per 1 million tokens, 14 Oct 2026)

| Model | Job in your platform | Input | Output | Cached input |
| --- | --- | --- | --- | --- |
| Claude Haiku 5.5 | Router, Fast answers, checks, summaries | $0.10 | $0.50 | $0.01 |
| Claude Sonnet 5.5 | Normal teaching, charts, documents, slides | $2 | $10 | $0.10 |
| Claude Opus 5.5 | Deep mode | $4 | $20 | $0.20 |
| Claude Fable 5.1 | Only the hardest jobs (optional) | $10 | $50 | $0.25 |

Source: [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing). Haiku 5.5 has this price for prompts up to 100,000 tokens; above that it costs 5 times more. Batch mode is half price for jobs that can wait. Web search costs $10 per 1,000 searches.

### OpenRouter: one door to many models

**Clear meaning:** OpenRouter is like a food court. You pay at one counter and can order from many kitchens: Claude, GPT, Gemini, DeepSeek, Qwen, Kimi, GLM and more. Your code talks to one API with one key.

| What OpenRouter does | What you do about it |
| --- | --- |
| Inference has [no markup](https://openrouter.ai/docs/faq): you pay each model's listed price | Use the listed price as your AI cost |
| Buying credits costs [5.5% by card](https://openrouter.ai/docs/faq) (minimum $0.80), or 5% by crypto | Add 5.5% to every cost (a factor of 1.055, section 9). Buy $15 or more at a time |
| With `usage: {include: true}`, each reply carries `usage.cost`, [the real charge](https://openrouter.ai/docs/use-cases/usage-accounting) | Bill from this number. Make one test call and check that it matches tokens × listed price |
| Thinking tokens ([reasoning tokens](https://openrouter.ai/docs/use-cases/reasoning-tokens)) are billed as output | Set `max_tokens` and a cost cap on every thinking mode |
| A [`models` list](https://openrouter.ai/blog/insights/model-routing/) is a fallback chain: if a model fails or is limited, the next one runs | You pay only for the model that ran. Save its name from the reply |
| [Privacy settings](https://openrouter.ai/docs/features/zdr) `data_collection: "deny"` and `zdr: true` limit which hosts may see prompts | Set them per plan (section 11) |
| Some models [cache automatically](https://openrouter.ai/docs/features/prompt-caching) (DeepSeek, OpenAI, Gemini, Grok, Moonshot, Groq). Claude needs `cache_control` marks | Savings differ by brain. Read `cached_tokens` in the reply |
| `:free` models allow [50 requests a day](https://openrouter.ai/docs/faq) (1,000 after you buy at least 10 credits) | Demos only, never for paying users |
| Token counts use each model's own tokenizer | One model's count does not match another's. Trust the reply, not your own estimate |

The fee, step by step:

- Input: you buy $10 of OpenRouter credits by card.
- Step: 5.5% of $10 is $0.55, but the minimum fee is $0.80, so the fee is $0.80.
- Output: you pay $10.80, which is 8%. At $100 the fee is $5.50 and you pay $105.50, which is 5.5%. Buy big, buy less often.

### Model menu (examples, 14 Oct 2026)

Prices are per 1 million tokens, as each lab page on OpenRouter showed them today. They change often and some include sales (DeepSeek V4.1 Flash showed 85% off), so never put them in code. The picker reads them live (section 10). The tiers are my suggestion: test them on your own questions (section 11).

| Tier | Model | Lab | Input | Output | Thinking |
| --- | --- | --- | --- | --- | --- |
| Quick | [DeepSeek V4.1 Flash](https://openrouter.ai/deepseek) | DeepSeek (China) | $0.0438 | $0.1752 | Not stated |
| Quick | [Qwen3.8 Flash](https://openrouter.ai/qwen) | Alibaba (China) | $0.15 | $0.47 | Yes |
| Quick | [Claude Haiku 5.5](https://openrouter.ai/anthropic) | Anthropic (US) | $0.10 | $0.50 | Yes, adaptive |
| Smart | [DeepSeek V4 Pro 0813](https://openrouter.ai/deepseek) | DeepSeek (China) | $0.2495 | $0.7484 | Not stated |
| Smart | [MiniMax M3](https://openrouter.ai/minimax) | MiniMax (China) | $0.23 | $0.96 | Not stated |
| Smart | [Qwen3.8 Max (0902)](https://openrouter.ai/qwen) | Alibaba (China) | $2 | $6 | Yes, on by default |
| Smart | [Claude Sonnet 5.5](https://openrouter.ai/anthropic) | Anthropic (US) | $2 | $10 | Yes, always on |
| Smart | [Gemini 4 Argon](https://openrouter.ai/google) | Google (US) | $2 | $10 | Yes, a reasoning model |
| Smart | [GPT-6.1 Sol Pro](https://openrouter.ai/openai) | OpenAI (US) | $2 | $10 | Yes, pro reasoning mode |
| Genius | [Kimi K3](https://openrouter.ai/moonshotai) | Moonshot AI (China) | $0.70 | $15 | Yes |
| Genius | [GLM 5.3 Prime](https://openrouter.ai/z-ai) | Z.ai (China) | $2.80 | $8.80 | Yes, always on |
| Genius | [Qwen3.8 Max Prime](https://openrouter.ai/qwen) | Alibaba (China) | $4 | $12 | Yes, effort adjustable |
| Genius | [Claude Opus 5.5](https://openrouter.ai/anthropic) | Anthropic (US) | $4 | $20 | Yes, adaptive |
| Genius | [Claude Fable 5.1](https://openrouter.ai/anthropic) | Anthropic (US) | $10 | $50 | Not stated |

- Look at the Output column first. Thinking modes spend mostly output tokens.
- Claude prices on OpenRouter are the same as the Claude table above.
- Pictures: Gemini image models are on OpenRouter too. [Nano Banana 2.1](https://openrouter.ai/google) is listed at $1.50 in and $30 out per million tokens, so a 1K picture still costs about $0.0336 (section 6). Ask with `modalities: ["image", "text"]` and the picture comes back as base64 data in `images` ([image docs](https://openrouter.ai/docs/features/multimodal/image-generation)).
- Web search: [Exa costs $0.007 a search, Parallel and Perplexity $0.005](https://openrouter.ai/docs/web-search).

### What uses tokens

- **Input:** rules, tool list, profile, chat history, files, tool results, and the user's message.
- **Output:** the answer, plus the thinking tokens, which are paid like output.
- **Cached input:** text sent again exactly the same. The first send costs 25% extra; every repeat within 5 minutes costs only 5% of normal on Sonnet 5.5 and Opus 5.5.
- **Hidden eaters:** resending the whole chat every turn, long tool results, and agent loops that resend the desk at every step, and thinking modes (Think Again, Overthink, Council) that run one question many times.

### The snowball problem

Each turn, the whole chat history is sent again, so the cost of one message keeps growing.

&#91;embedded content: example model · 500 history tokens per round, 20 rounds, last 4 rounds + a 300-token summary\]

The grey line keeps climbing; the blue line goes flat after round 4.

- **Input:** each round (one question + one answer) adds about 500 tokens of history. The chat has 20 rounds.
- **Step, no fix:** round 1 sends 500, round 2 sends 1,000, and so on to round 20, which sends 10,000. Total = 500 × (1 + 2 + ... + 20) = 500 × 210 = 105,000 tokens. Quick trick: 1 + 2 + ... + 20 = 20 × 21 ÷ 2 = 210.
- **Step, with fix:** keep the last 4 rounds word for word (2,000) plus a 300-token summary of older rounds. Rounds 1 to 4 send 5,000 in total. Rounds 5 to 20 send 2,300 each: 16 × 2,300 = 36,800. Total = 41,800 tokens.
- **Output:** 60% fewer history tokens. On Sonnet 5.5 that is $0.21 versus $0.084 for one long chat.

Caching also helps: if the user replies within 5 minutes, the old history is read from the cache at 5% of the price. The summary protects you when the cache has expired, and it keeps the AI focused.

### How to count tokens exactly

1. **Before the call, estimate.** Use the provider's token-counting endpoint, or a quick estimate in your code. Use it to hold credits and to show "about X credits".
2. **After the call, read the truth.** Every reply has a `usage` part with the real numbers: prompt\_tokens, completion\_tokens, cached\_tokens, reasoning\_tokens and cost (these are OpenRouter's names; send usage: {include: true} to get them). Bill from these numbers only.
3. **Save one row per AI call or tool use** in a usage table:

| Field | Example |
| --- | --- |
| user\_id, task\_id, step\_no | u\_42, t\_901, 3 |
| model | anthropic/claude-sonnet-5.5 |
| input / cached / output tokens | 3,000 / 3,000 / 700 |
| reasoning tokens | 450 (already counted inside output) |
| tool units | 1 image, 0 searches |
| cost\_usd (from usage.cost) | 0.0133 |
| credits\_charged | 5 |

### The 4 tricks that save the most

**1. Model routing:** easy messages go to the cheap model.

- **Input:** 1,000 messages a day, 700 of them easy. A Normal answer on Sonnet 5.5 costs $0.0133. A Fast answer on Haiku 5.5 costs $0.00065. The router check costs $0.000125 per message.
- **Step:** all on Sonnet = 1,000 × $0.0133 = $13.30. Routed = 700 × $0.00065 + 300 × $0.0133 + 1,000 × $0.000125 = $0.455 + $3.99 + $0.125 = $4.57.
- **Output:** about 66% cheaper, $13.30 down to $4.57 a day.

**2. Prompt caching:** the fixed rules are cheap after the first use.

- **Input:** rules + tool list = 3,000 tokens, sent with 1,000 Sonnet messages a day.
- **Step:** 3,000 × 1,000 = 3 million tokens a day. Without cache: 3 million × $2 per million = $6.00. With cache: 3 million × $0.10 per million = $0.30.
- **Output:** you save $5.70 a day, about $171 a month.

**3. Summarize old chat:** the snowball fix above, 60% fewer history tokens.

**4. Browser-side charts:** every slider move costs 0 tokens (section 5).

Smaller tricks: cap the answer length per mode, trim tool results before sending them back, use batch mode (half price) for background jobs like "make a full course", and reuse saved answers for common questions that are not personal.

## 9. Credits and pricing strategy

**Clear meaning:** Sell credits at 1 cent each and let 1 credit cover at most 0.3 cents of AI cost. Then 70% of every sale is left for payment fees, servers and profit.

Credits are like arcade tokens. Users buy tokens with money, and every game costs some tokens. You hide confusing token prices behind one simple coin.

### Step 1: decide what 1 credit is worth

- **Input:** you sell credits at $0.01 each ($10 = 1,000 credits). You want AI cost to be at most 30% of the price.
- **Step:** $0.01 × 30% = $0.003.
- **Output:** 1 credit may cover up to $0.003 of AI cost.

The rule for every action:

```latex
\text{credits} = \left\lceil \frac{\text{AI cost in dollars} \times 1.055}{0.003} \right\rceil
```

The ⌈ ⌉ brackets mean "round up to the next whole number". Always round up, never down. The 1.055 adds the 5.5% fee OpenRouter takes when you buy credits (section 8). Keep it in a settings table, so you can change it if your fee changes.

### Step 2: price each action

Worked example, one Normal answer:

- **Input:** Sonnet 5.5. 3,000 new input tokens at $2 per million, 3,000 cached tokens at $0.10 per million, 700 output tokens at $10 per million.
- **Step:** 3,000 × 2 ÷ 1,000,000 = $0.006. 3,000 × 0.10 ÷ 1,000,000 = $0.0003. 700 × 10 ÷ 1,000,000 = $0.007. Total = $0.0133. Add the 5.5% OpenRouter fee: $0.0133 × 1.055 = $0.01403. Then $0.01403 ÷ $0.003 = 4.7.
- **Output:** round up, so 5 credits.

All actions, using the same math with the fee (token sizes are examples; replace them with your real averages after launch):

| Action | What it uses | AI cost | Credits |
| --- | --- | --- | --- |
| Fast answer | Haiku 5.5: 4,000 in, 500 out | $0.00065 | 1 (the minimum) |
| Normal answer | Sonnet 5.5: 6,000 in (half cached), 700 out | $0.0133 | 5 |
| Interactive chart | Sonnet 5.5: 6,000 in (half cached), 1,500 out | $0.0213 | 8 |
| Slider move | The browser only | $0 | 0 |
| Image, standard | Haiku writes the prompt + Nano Banana 2.1 | $0.0339 | 12 |
| Image, premium | Haiku writes the prompt + Nano Banana Pro | $0.1343 | 48 |
| Web search add-on | 1 search + 5,000 tokens of results on Sonnet | $0.02 | 8 |
| Document, 5 sections | 6 Sonnet calls + 1 Haiku check | $0.073 | 26 |
| PPT, 10 slides, 3 images | 11 Sonnet calls + 3 images + 1 Haiku check | $0.226 | 80 |
| Deep task, 6 steps | Opus 5.5 per step: 12,000 in (8,000 cached), 2,000 out | $0.346 | 122, shown as "about 120" |

What Pro's 2,000 credits buy: about 400 Normal answers, or 25 PPTs, or 16 Deep tasks, or 57 Think Again runs, or 20 Overthink runs (both on Sonnet 5.5).

Price by value too. If a 10-slide PPT saves a teacher an hour, 80 credits ($0.80) is a great deal for them. You may charge more than the cost math says, as long as users see the price first.

### Step 2b: price the thinking modes (any brain)

**Clear meaning:** The same mode costs very different credits on different brains. The picker shows the number before the user starts, using the live price list.

Worked example: Think Again with the default (a first draft, then 2 fix rounds), on two brains.

- Input: the draft uses 3,000 tokens in and 1,500 out. Each fix round has a critic (4,500 in, 400 out) and a rewrite (5,000 in, 1,500 out). Total in = 3,000 + 2 × (4,500 + 5,000) = 22,000. Total out = 1,500 + 2 × (400 + 1,500) = 5,300. Thinking tokens are already inside the out numbers.
- Step on DeepSeek V4 Pro 0813 ($0.2495 in, $0.7484 out per million): 22,000 × 0.2495 ÷ 1,000,000 = $0.00549. 5,300 × 0.7484 ÷ 1,000,000 = $0.00397. Total $0.00946. Add the 5.5% fee: × 1.055 = $0.00998. Divide by $0.003: 3.3.
- Step on Claude Sonnet 5.5 ($2 in, $10 out per million): 22,000 × 2 ÷ 1,000,000 = $0.044. 5,300 × 10 ÷ 1,000,000 = $0.053. Total $0.097. × 1.055 = $0.1023. Divide by $0.003: 34.1.
- Output: round up. DeepSeek V4 Pro costs 4 credits. Sonnet 5.5 costs 35 credits.

The same steps for every mode and brain (no cache, which is the safe estimate):

| Mode and token plan | DeepSeek V4 Pro 0813 | Kimi K3 | Claude Sonnet 5.5 | Claude Opus 5.5 |
| --- | --- | --- | --- | --- |
| Normal answer: 3,000 in, 700 out | 1 | 5 | 5 | 10 |
| Think Again, draft + 2 rounds: 22,000 in, 5,300 out | 4 | 34 | 35 | 69 |
| Overthink, 3 tries + judge: 18,000 in, 24,800 out | 9 | 136 | 100 | 200 |

Overthink plan: each of 3 tries uses 3,000 in and 8,000 out (6,000 thinking + 2,000 answer). The judge reads 9,000 in and writes 800 out.

- Council: members DeepSeek V4 Pro 0813, Qwen3.8 Max (0902) and Claude Haiku 5.5 (each 3,000 in, 1,500 out), judge Claude Sonnet 5.5 (7,500 in, 1,200 out). Total $0.0449, × 1.055 ÷ 0.003 = 15.8, so 16 credits. An all-cheap council (DeepSeek V4 Pro, MiniMax M3, Qwen3.8 Flash, judge Haiku 5.5) costs 3 credits.
- Research: 4 searches at $0.007 each, then the brain reads 12,000 tokens and writes 1,500. DeepSeek V4 Pro costs 12 credits, Sonnet 5.5 costs 24. On cheap brains the searches cost more than the thinking.
- Two Brains: the thinker uses 3,000 in and 7,000 out (6,000 scrap paper and 1,000 notes). The answerer reads 4,000 (the question plus the notes) and writes 700. Qwen3.8 Max (0902) thinks and DeepSeek V4 Pro answers: $0.0495, × 1.055 ÷ 0.003 = 17.4, so 18 credits. GPT-6.1 Sol Pro thinks and Claude Sonnet 5.5 answers: $0.091, × 1.055 ÷ 0.003 = 32.002, so 33 credits. DeepSeek V4 Pro thinks and Claude Opus 5.5 answers: 13 credits, against 52 for Opus doing all of it alone. The thinker is most of the bill, because thinking is paid as output, so a cheap thinker with a strong answerer saves the most.
- Think Team: 3 thinkers, each 3,000 in and 3,000 out (500 of that is notes). The answerer reads 4,500 (the question plus 3 sets of notes) and writes 700. Qwen3.8 Max (0902), DeepSeek V4 Pro and Claude Haiku 5.5 think, Claude Sonnet 5.5 answers: $0.0448, × 1.055 ÷ 0.003 = 15.75, so 16 credits. GPT-6.1 Sol Pro, Qwen3.8 Max and Kimi K3 think, Sonnet 5.5 answers: $0.1231, so 44 credits. The same cheap team with Claude Opus 5.5 answering: 22 credits. A team of cheap thinkers can cost less than one strong brain thinking alone.

What to learn from the table:

- The same mode can cost 20 times more on another brain (Overthink: 9 against 200). So the estimate must be live, never typed in by hand.
- Chinese does not always mean cheap. Kimi K3 has a low input price, but its $15 output price makes Overthink cost 136 credits against 100 on Sonnet 5.5.
- Hold the maximum, settle the real cost. Think Again on Sonnet 5.5 holds 35 credits. If the critic is happy after the first look, only the draft and one critic call ran: 7,500 in and 1,900 out = $0.034, × 1.055 ÷ 0.003 = 11.96, so 12 credits. The other 23 go back to the wallet.
- Free plan check: one Think Again round on Qwen3.8 Flash (12,500 in, 3,400 out) costs $0.0035, × 1.055 ÷ 0.003 = 1.22, so 2 credits. Quick brains keep the Free plan safe.

### Step 3: fixed price or metered?

| Type | Rule | Why |
| --- | --- | --- |
| Small actions: Fast, Normal, chart, image | Fixed credits | Users like a price they can predict |
| Big jobs: Deep, PPT, document, Think Again, Overthink, Council, Two Brains, Think Team, Research | Show an estimate and a maximum, then charge the real cost | Big jobs vary a lot in size |
| Every action | Hard token caps per mode | No single request can cost far more than its price |

Once a month, compare each action's real average cost with its price. If cost is above credits × $0.003, raise the price or tighten the caps.

### Step 4: plans (example)

| Plan | Price | Credits | What it unlocks |
| --- | --- | --- | --- |
| Free | $0 | 100 a month | Fast, Normal and one Think Again round on Quick brains, 2 charts a day, no images, no Overthink or Council |
| Student | $8 a month | 800 a month | All modes on Quick and Smart brains, standard images |
| Pro | $20 a month | 2,000 a month | Everything: Genius brains, Overthink, Council, premium images, PPT and document export |
| School | $12 per student a month | 1,000 per student, shared pool | Teacher dashboard, class limits, only the brains the teacher allows |
| Top-up | $10 once | 800, valid 12 months | For anyone who runs out |

Top-ups cost more per credit than plans (1.25 cents versus 1 cent). This nudges people to subscribe.

### Step 5: wallet rules

1. **A ledger, not a balance box.** Every change is a new row: +2,000 plan, -5 answer, +35 released hold. Balance = the sum of the rows. Never overwrite a number.
2. **Hold, then settle,** like a hotel holding money on your card:
   - **Input:** balance 200. The user starts a PPT (maximum 120) and a Deep task (maximum 150) at the same time.
   - **Step:** hold 120 for the PPT, so 80 is free. The Deep task needs 150, more than 80, so ask the user to wait or top up. The PPT finishes at a real cost of 85: take 85, release 35.
   - **Output:** balance = 200 - 85 = 115. It never goes below zero.
3. Show "used 5 credits" after every answer, and the balance always.
4. Show the estimate and the maximum before every big job.
5. Refund automatically when your system fails.
6. Option: refresh plan credits weekly (about 500 a week instead of 2,000 a month), so one heavy day cannot empty a whole month. Cursor uses this idea.
7. A daily spending cap per user, and a fair-use limit on anything called "unlimited".
8. Check your country's consumer law on refunds and credit expiry before launch.

### Step 6: profit check (Pro plan, example)

- **Input:** Pro = $20 for 2,000 credits. AI cost is at most $0.003 per credit. Payment fee about $1. Servers and storage about $1 per user. A typical user spends 60% of the credits (example).
- **Step:** worst case, all 2,000 used: AI = 2,000 × $0.003 = $6, so profit = $20 - $6 - $1 - $1 = $12. Typical case, 1,200 used: AI = $3.60, so profit = $20 - $3.60 - $1 - $1 = $14.40.
- **Output:** you keep 60% even when a user spends everything, and about 72% for a typical user.

Free users cost at most 100 × $0.003 = $0.30 a month each, so 1,000 free users cost at most $300 a month. Treat it as marketing. Real costs are often lower, because rounding up means a Fast answer really uses only about 0.2 credits of AI cost.

The OpenRouter fee is already inside the 30% cap, so these profit numbers hold on every brain. Only the credits change. On a cheap brain the 1-credit minimum even makes the margin higher.

### How others charge (October 2026)

| Product | How it works | Idea to copy |
| --- | --- | --- |
| [Lovable](https://lovable.dev/pricing) | Each message costs credits by the work done: a small style change is 0.5, a landing page with 3 images is 1.7 | Price by work done, and show each message's cost |
| [Cursor](https://cursor.com/pricing) | A usage pool that refreshes weekly; when it runs out, buy top-offs or wait | Weekly refresh, top-ups, spending caps |
| [ChatGPT Business](https://openai.com/business/pricing/) | "Unlimited" chat with abuse guardrails; Enterprise can buy credit-based or token-based pricing | Even unlimited needs a fair-use limit |

## 10. Tech stack and database

**Clear meaning:** Use popular, proven tools: a React website, a Python backend, PostgreSQL for money and memory, and a job queue for long tasks.

| Part | Choice (example) | Why |
| --- | --- | --- |
| Website | Next.js (React) | Popular, good for chat apps |
| Live text | Server-Sent Events (SSE) | A one-way live pipe that shows the answer while it is written |
| Charts | Apache ECharts or Plotly.js | Hover, zoom and legends built in |
| Formulas | math.js | Reads math formulas without running code |
| Backend | Python + FastAPI | Best AI, PPT and Word libraries |
| Model gateway | OpenRouter plus a thin wrapper of your own | One key reaches DeepSeek, Qwen, Kimi, GLM, Claude, GPT and Gemini. Your wrapper adds caps, logging and wallet checks |
| Long jobs | A job queue: Redis + workers (Temporal later) | PPT and Deep tasks run in the background and survive restarts |
| Database | PostgreSQL + pgvector | Users, ledger, usage; pgvector finds text with similar meaning (notes, memory) |
| Fast counters | Redis | Live balance and rate limits |
| Files | S3 or Cloudflare R2 | Images, PPT and PDF files |
| Office files | python-pptx, python-docx | Real PPT and Word files |
| Previews | LibreOffice (headless) | Turns PPT pages into images |
| Diagrams | Mermaid and SVG | Cheap, exact labels |
| Mini-app box | Sandboxed iframe on a separate domain | Runs AI-written code safely |
| Code runner | A container sandbox, or the AI provider's code tool | Exact math |
| AI logs | Langfuse (open source) | Shows every step with its tokens and cost |
| Payments | Stripe or Paddle; Toss Payments in Korea | Check which one works for your country |
| Skills and tools | SKILL.md folders + MCP servers | Developer mode loads recipes and tools only when needed (section 13) |

### Database tables

| Table | What it stores |
| --- | --- |
| users | Account, plan, country |
| profiles | The memory card (section 4) |
| conversations, messages | Chat history and summaries |
| tasks | One row per job: mode, status, estimate, maximum |
| usage\_events | One row per AI call or tool use (section 8) |
| credit\_ledger | Every + and - of credits, with a reason |
| credit\_holds | Credits held for running jobs |
| model\_prices | Price of each model, copied every night from OpenRouter's model list, with a start date |
| action\_prices | Credits per action: Fast = 1, Normal = 5, and so on |
| artifacts | Chart recipes, images, documents, PPT files |
| prompts | Prompt text with version numbers |
| eval\_results | Scores from your test questions |
| modes | One row per mode: steps, default brains, caps, and which plans may use it (section 3) |
| model\_catalog | Your labels per model: tier (Quick, Smart, Genius), lab (Chinese or Western), private route yes or no, on or off |
| skills | Name, short description, file path and version of each skill (section 13) |
| run\_events | Every event of a run (plan, step, tool, file, cost), so a reload replays the screen (section 14) |
| workspace\_files | Each file in a user's workspace: user, task, path, kind, size, version, delete date (section 14) |

Keep prices in tables, not in code. When a provider changes its prices, you add one row and change no code.

### One OpenRouter call (example)

**Clear meaning:** Every AI step in the harness is one web request like this. Each setting is either a safety rail or a bill counter.

```json
{
  "model": "deepseek/deepseek-v4-pro-0813",
  "models": ["moonshotai/kimi-k3", "anthropic/claude-sonnet-5.5"],
  "messages": [{"role": "user", "content": "..."}],
  "max_tokens": 8000,
  "reasoning": {"effort": "high"},
  "usage": {"include": true},
  "provider": {"data_collection": "deny", "require_parameters": true}
}
```

- `model` is the first choice. `models` lists backups in order, used when the first one fails, is limited, or cannot fit the prompt. You pay only for the one that ran.
- `max_tokens` is the hard cap on the reply, thinking included.
- `reasoning` says how hard to think (section 3). Send it only to models that support it.
- `usage.include` asks for the real cost in the reply.
- `data_collection: "deny"` allows only hosts that do not collect or train on your data. `require_parameters: true` allows only hosts that support everything in the request, such as JSON answers and tools (section 4).
- After the reply, save the model that really ran, `usage.cost`, the token counts, `cached_tokens`, `reasoning_tokens` and `finish_reason` (section 8).

Let the price table fill itself. Each night, read OpenRouter's model list (`GET /api/v1/models`). Every model comes with its prices in dollars per token (so "0.0000025" means $2.50 per million), the settings it supports, and what it can read and write (text, images). Store a new `model_prices` row only when a price changed, and raise an alarm when a price jumps by a lot (example: more than 20%), because sales end without notice.

## 11. Safety and quality

**Clear meaning:** Safety and testing are part of the harness, because bad answers lose users and abuse loses money.

### Safety checklist

- [ ] Check user messages and AI answers with a safety filter. Be strictest with images.
- [ ] If people under 18 use it, add stricter filters and follow the child privacy laws of each country you sell in.
- [ ] Treat text from web pages and uploaded files as data, never as orders. Hidden text like "ignore your rules" is called prompt injection.
- [ ] Run AI-written code only in a sandbox. Never use eval().
- [ ] Set rate limits per minute, daily caps per user, and email or phone checks to stop fake free accounts.
- [ ] Let users see, edit and delete their memory.

### Quality checklist

- [ ] Keep a fixed set of about 100 test questions: math, science, PPT requests, and tricky ones.
- [ ] Run them before every prompt or model change. Score each answer: correct, simple, cost.
- [ ] Track thumbs up and down on every answer.
- [ ] Review 20 random conversations a week, only where your privacy policy allows it.

### Model, data and skills checklist

- [ ] Send `provider.data_collection: "deny"` on every request. Add `zdr: true` (zero data retention) for School accounts. [OpenRouter explains both](https://openrouter.ai/docs/features/zdr).
- [ ] Show a privacy label in the model picker. Some hosts may keep prompts or train on them. A private route can cost more: [OpenRouter's June 2026 post](https://openrouter.ai/blog/insights/the-open-weight-models-that-matter-june-2026/) says Western hosts that do not train on your data cost about 2 times the first-party price for DeepSeek V4 Flash.
- [ ] Keep OpenRouter prompt logging off. By default it [does not store prompts or answers](https://openrouter.ai/docs/faq), and switching it on only earns a 1% discount.
- [ ] Tell users that web search sits outside the privacy setting. OpenRouter says zero data retention covers model hosts only, not search tools.
- [ ] Never put `:free` models in front of paying users. They have low daily limits.
- [ ] Treat every skill, MCP server and prompt from GitHub as untrusted. Read the files, pin a version, and run tools inside a sandbox. A SKILL.md can hide orders for the AI (prompt injection).
- [ ] Check each repo's license before you copy code into a product you sell (section 13).
- [ ] Test every loop mode with worst-case questions. Confirm the three stops (rounds, credits, time) really stop it.
- [ ] If you serve schools or children, check your country's rules on sending student data to other countries, because a model's host may be abroad.

## 12. Build roadmap and numbers to watch

**Clear meaning:** Build the money system, the OpenRouter gateway, a first mode picker and the chart engine first, because they make you different and keep you profitable. Add Deep mode, the thinking loops, images and files next. Developer mode and Research come after that.

&#91;embedded content: roadmap · 5 phases, 2 gates, rough guess\]

Each phase ends with something you can use or sell. Do not start the next phase until its gate numbers are met.

### Numbers to watch (starting targets, example)

| Number | Simple meaning | Target |
| --- | --- | --- |
| Gross margin | Money left after AI, payment and server costs | Above 60% |
| AI cost per paying user | Your AI bill for one user in a month | Below 30% of their plan price |
| Small-model share | Messages answered by the cheap model | Above 60% |
| Cache hit rate | Input tokens read from the cache | Above 50% |
| Task success | Jobs finished with no retry or thumbs down | Above 85% |
| Understood rate | Thumbs up on explanations | Above 80% |
| Free to paid | Free users who start paying | 3 to 5% |
| Ledger mismatches | Credits charged that do not match usage rows | 0 |
| Loop stops by cap | Think Again or Overthink jobs that hit their credit cap before finishing | Below 5% |
| Price drift | Models whose live price differs from your table for more than a day | 0 |

## 13. Developer mode, skills and the GitHub kit

**Clear meaning:** Developer mode makes your chatbot work like a helper for builders. It researches, plans a design, writes better prompts and helps with code. It does this with skills (small recipe cards) and tools. This section also lists famous GitHub projects you can learn from while you build.

How I read "jam-packed development system chatbot": a chatbot packed with developer power, plus a kit of proven GitHub tools to build it faster. So this section has two parts: Developer mode inside your product, and a GitHub kit for you, the builder.

### Skills: recipe cards the AI opens only when needed

A skill is a folder with one file called SKILL.md. The file starts with a short header (a name and one line saying when to use it), then the steps. The AI always sees the one-line headers. It opens a full recipe only when the task matches. Here is a skill you could write yourself:

```markdown
---
name: architect
description: Plans a software system before any code is written. Use when the user asks how to design, structure or scale an app.
---
1. Ask for the goal, the users and the limits (money, team, deadline) if they are missing.
2. Write a one-page plan: the parts, the data, the risks.
3. Draw the parts as a Mermaid diagram.
4. Give 3 options with cost and risk, then recommend one.
5. End with the next 3 small steps.
```

Why open recipes only when needed? Example numbers:

- Input: 30 skills. A full recipe is about 1,500 tokens. A header is about 50 tokens.
- Step: load everything = 30 × 1,500 = 45,000 tokens on every message. Load all headers plus one recipe = 30 × 50 + 1,500 = 3,000 tokens.
- Output: 15 times fewer tokens. At Sonnet 5.5's input price ($2 per million) that is $0.006 instead of $0.09 per call.

### Built-in skills for Developer mode (start with these 7)

| Skill | What it does | Brain |
| --- | --- | --- |
| Architect | Plans the system first: parts, data, risks, options, a diagram | Smart or Genius |
| Researcher | Searches, reads, compares and answers with links | Smart |
| Prompt Smith | Turns a rough idea into a clear prompt plus 5 test cases | Smart |
| Coder | Writes and edits code in small steps and runs tests in a sandbox | A coding brain |
| Reviewer | Finds bugs, security holes and missing tests | Genius |
| Explainer | Explains code or math with an analogy and a mini quiz (section 4) | Quick or Smart |
| Chart Maker | Writes a chart recipe so the user can play with sliders (section 5) | Smart |

Coding brains seen on OpenRouter today (price per million tokens): [Kimi K2.7 Code](https://openrouter.ai/moonshotai) ($0.6712 in, $3.35 out, always thinks) and [Qwen3 Coder Next](https://openrouter.ai/qwen) ($0.12 in, $0.80 out, no thinking). The Smart and Genius brains in section 8 also work.

### Tools: MCP servers

MCP (Model Context Protocol) is a standard plug for tools, like USB for tools. A small program called an MCP server offers tools such as "fetch a web page" or "read a file". Your harness connects to it, shows its tool list to the AI, and runs a tool when the AI asks. The official [reference servers](https://github.com/modelcontextprotocol/servers) include Fetch, Filesystem, Git, Memory, Sequential Thinking and Time.

- Run code and file tools in a locked box: a container with no secrets, no open internet and a short time limit.
- Start with read-only tools (Fetch, Memory). Add Filesystem and Git later, in a separate folder per user.
- Meter every tool call like any AI call (section 8).

### The GitHub kit (checked 14 Oct 2026)

Stars and licenses are what each repo page showed today. Open the LICENSE file before you copy anything into a product you sell.

**Skills and tools**

| Repo | Stars | License | Use it for |
| --- | --- | --- | --- |
| [anthropics/skills](https://github.com/anthropics/skills) | 180.3k | Mixed: many skills Apache 2.0, but the docx, pdf, pptx and xlsx skills are source-available, not open source | Copy the SKILL.md format from its spec and template folders. Read the skills for ideas |
| [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | 90.0k | Apache 2.0 for new code, MIT for older | Ready tool servers: Fetch, Filesystem, Git, Memory, Sequential Thinking, Time |
| [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) | 95.2k | MIT | A big list of community tool servers. Search it before you build a tool |
| [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) | 55.6k | Not shown on the page | A list of skills, agents, plugins and developer tools. Browse it for skill ideas |

**Prompting**

| Repo | Stars | License | Use it for |
| --- | --- | --- | --- |
| [anthropics/prompt-eng-interactive-tutorial](https://github.com/anthropics/prompt-eng-interactive-tutorial) | 38.6k | Not shown on the page | A 9-chapter course from basic prompts to complex ones, plus an appendix on chaining, tools and search. Do it once with your own questions |
| [dair-ai/Prompt-Engineering-Guide](https://github.com/dair-ai/Prompt-Engineering-Guide) | 77.4k | MIT | Guides, papers and lessons on prompting, context and agents |
| [f/prompts.chat](https://github.com/f/prompts.chat) | 172.9k | MIT code, CC0 prompts | A library of ready prompts (once called Awesome ChatGPT Prompts). CC0 means public domain, so you can seed your prompt library with them |
| [stanfordnlp/dspy](https://github.com/stanfordnlp/dspy) | 36.7k | MIT | "Programming, not prompting": code tunes the prompts against your test questions. Use it in Phase 4 |
| [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) | 24.2k | MIT | Tests prompts and agents on a fixed question set and probes for attacks. Use it for your 100 test questions (section 11) |

**Architecture and agents**

| Repo | Stars | License | Use it for |
| --- | --- | --- | --- |
| [humanlayer/12-factor-agents](https://github.com/humanlayer/12-factor-agents) | 26.6k | Apache 2.0 code, CC BY-SA 4.0 text | 12 rules for agents that run in production. Read this first (the table below maps it to your plan) |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | 43.0k | MIT | A low-level kit for stateful agents. A good model for your agent loop |
| [openai/openai-agents-python](https://github.com/openai/openai-agents-python) | 28.6k | MIT | A light multi-agent kit that also works with other labs' models |
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | 59.4k | MIT | Teams of role-playing agents (a researcher, a writer, a reviewer). An idea source for Council |
| [Shubhamsaboo/awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps) | 139.9k | Apache 2.0 | 100+ working agent and RAG app examples to read and copy from |

Seven of the 12 rules, matched to your plan:

| 12-factor rule | Where it lives in your plan |
| --- | --- |
| Own your prompts | The prompt library with version numbers (section 4) |
| Own your context window | The context budget table (section 4) |
| Own your control flow | The agent loop and its three stops (section 3) |
| Contact humans with tool calls | Ask before big or costly jobs (section 3) |
| Compact errors into the context window | The checker and its 2 fix tries (section 3) |
| Unify execution state and business state | The tasks table and the ledger (section 10) |
| Small, focused agents | One skill, one job (this section) |

**Research agents**

| Repo | Stars | License | Use it for |
| --- | --- | --- | --- |
| [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) | 29.5k | Apache 2.0 | A planner writes research questions, helpers gather facts for each, a publisher writes the report. Copy this pattern for Research mode |
| [stanford-oval/storm](https://github.com/stanford-oval/storm) | 31.6k | MIT | Researches, builds an outline, then writes a long report with citations. Co-STORM adds a human to the loop |
| [langchain-ai/open\_deep\_research](https://github.com/langchain-ai/open_deep_research) | 12.7k | MIT | The owner archived it on 21 Aug 2026, so it is read-only. Learn from it, do not build on it |

**Coding agents**

| Repo | Stars | License | Use it for |
| --- | --- | --- | --- |
| [Aider-AI/aider](https://github.com/Aider-AI/aider) | 49.5k | Apache 2.0 | AI pair programming in the terminal. Try it before you design Developer mode |
| [cline/cline](https://github.com/cline/cline) | 67.6k | Apache 2.0 | An autonomous coding agent for the editor and the command line. It lists OpenRouter as a provider |
| [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | 90.8k | MIT | An open coding agent that takes whole tasks. Use it as a model of the Deep loop for code |

**Platform parts**

| Repo | Stars | License | Use it for |
| --- | --- | --- | --- |
| [langfuse/langfuse](https://github.com/langfuse/langfuse) | 32.4k | MIT, except the ee folders | Logs every AI step with tokens and cost. Can be self-hosted. Your AI log tool |
| [danny-avila/LibreChat](https://github.com/danny-avila/LibreChat) | 43.6k | MIT | A full chat app that lists OpenRouter among its providers. A shortcut start, or a UI to learn from |
| [open-webui/open-webui](https://github.com/open-webui/open-webui) | 154.1k | Its own license: covered parts must keep the "Open WebUI" branding | A popular chat UI. Read the license before using it in a product you sell |
| [BerriAI/litellm](https://github.com/BerriAI/litellm) | 53.8k | Not named on the page | A gateway to 100+ providers. You do not need it while you use OpenRouter. Keep it as a backup plan |
| [OpenRouterTeam/ai-sdk-provider](https://github.com/OpenRouterTeam/ai-sdk-provider) | 683 | Apache 2.0 | Connects OpenRouter to the Vercel AI SDK. Handy for the Next.js side. It is published by the OpenRouterTeam organization |
| [apache/echarts](https://github.com/apache/echarts) | 67.0k | Apache 2.0 | The chart engine (section 5) |
| [josdejong/mathjs](https://github.com/josdejong/mathjs) | 15.1k | Apache 2.0 | The formula calculator (section 5) |

### How to use the kit: 5 steps

1. Read 12-factor-agents in one sitting. Tick the rules your harness already follows.
2. Do the Anthropic prompt tutorial with your real use cases. Save the best prompts in your prompt library.
3. Write your first 3 skills by hand in SKILL.md format: Architect, Researcher, Prompt Smith. Keep each under 1,500 tokens.
4. Plug in two tool servers only, Fetch and Memory, inside a sandbox.
5. Add promptfoo with your 100 test questions, and Langfuse for logs, before you invite users.

License watch-list (not legal advice):

- anthropics/skills: the document skills are source-available, not open source. Build your own PPT and Word makers (section 6).
- open-webui: the branding rule makes it a poor base for a white-label product.
- langfuse: the ee folders have their own terms.
- litellm and awesome-claude-code: the page did not name the license. Open the LICENSE file.
- open\_deep\_research: archived, so no more fixes.

## 14. The screen: live steps, files, tools and your workspace

**Clear meaning:** The user should always see what the AI is doing, like watching a helper work. A short plan appears, ticks show up as steps finish, files land on the side, and the credits used are always visible. Claude and Manus feel like this. Nothing happens in secret.

&#91;embedded content: chat screen · sidebar, run card, files panel\]

Read it from the middle out. The run card shows the plan, the running tool and the cost. The box under it is where the user picks the mode, brains, effort, tools and skills. The right panel holds the files. On a phone, the sides become sheets.

### What each area does

| Area | What the user sees | On a phone |
| --- | --- | --- |
| Sidebar | Chats, projects, My files, skills, plan and credits | A slide-in menu |
| Run card | The plan as a checklist, the running tool, a thinking summary, credits used, a Stop button | Shrinks to one line: Step 3 of 5. Tap to open |
| Composer (the box at the bottom) | Text, file drop, chips for mode, effort, brains, tools and skills, and the estimate | The chips collapse into one Settings sheet. The estimate stays visible |
| Files panel | Every file this task made, a preview, Open and Download, and the folder name | A full-screen sheet, opened from a "Files (2)" chip |

### The kinds of step the user sees

| Step | What the user sees | Example |
| --- | --- | --- |
| Plan | A checklist of 3 to 8 plain steps | Read your notes, search the web, build the slides, check, export |
| Thinking | A closed block that opens to a short summary | "Thought for 12 s" |
| Tool | A card with the tool name, what it is doing and what it cost | "PPT builder: slide 4 of 10, 2 credits so far" |
| File made | A file card with Open and Download | photosynthesis.pptx, 10 slides |
| Check | A tick, or a note on what was fixed | "No empty slide" |
| Ask | A question with buttons | "This needs about 80 credits. Continue?" |
| Error | A calm card with Retry and Skip | "The image failed. Credits refunded." |
| Done | The answer, the credits used, next-step buttons | "Used 76 credits" |

### How the server feeds the screen

The server sends a stream of small events through the same live pipe as the chat text (Server-Sent Events, section 10). The screen only draws events and keeps no secret state, so a reload or a phone shows the same steps.

| Event | Sent when | The screen does |
| --- | --- | --- |
| run\_start | The task begins | Shows the run card |
| plan | The planner finishes the to-do list | Draws the checklist |
| step\_start, step\_done | A step begins or ends | Moves the dot and ticks it |
| thinking | A thinking summary is ready | Adds the closed "Thought for 12 s" block |
| tool\_start, tool\_result | A tool runs and returns | Shows the tool card, then its result and cost |
| file\_created | A file lands in the out folder | Adds a file card and opens the preview |
| text | The answer streams | Types the words live |
| cost | After every step | Updates "Used 34 credits, at most 80" |
| ask | The plan needs a yes, or more credits | Shows a question card with buttons |
| error | A step fails | Shows a calm card with Retry and Skip |
| run\_done | Everything is finished | Shows the answer, the credits used and next-step buttons |

Two events as they travel (example):

```json
{"seq": 14, "type": "tool_start", "step": 3, "tool": "ppt_builder", "title": "Building slide 4 of 10"}
{"seq": 15, "type": "cost", "used": 34, "max": 80}
```

- Step titles are plain words, at most 8 of them. The planner writes a title for every step.
- Raw tool input and output sit in a "Details" fold, not in the main view.
- Save every event in a run\_events table (run, number, type, data, time). A reload plays them back.
- Stop keeps the files already made, then settles the credits (hold, then settle, section 9).
- Show a thinking summary, not the raw scrap paper. OpenRouter returns thinking text for some models and hides it for others, and Claude's comes back as a summary by default.

### Tools, MCP and skills on the screen

| Control | What the user does | Rule |
| --- | --- | --- |
| Tools menu | Turns tool groups on or off for this chat: Chart, Image, Documents, PPT, Web search, and each MCP server | Built-in tools start on. MCP servers start off |
| Add an MCP server | Pastes a server address, or picks one from your list | Pro and School only. School uses the teacher's list. Every server runs behind your own gateway, inside the sandbox |
| Permission card | Allow once, Always allow, or Deny | Required for tools that spend credits, write outside the task folder or reach the internet |
| Tool card | Sees the tool, its server, what it is doing and what it cost | Shown for every call, so no tool runs in secret |
| Skills menu | Turns skills on or off, and sees "Used: Architect" when one ran | Skills open only when needed (section 13) |

The [MCP tools spec](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) says there should always be a person who can deny a tool call. Apps should show which tools the AI can use, show a clear sign when a tool runs, and ask before sensitive actions. They should also show tool inputs before the call, set time-outs and log every call. Treat a server's tool descriptions as untrusted unless you trust the server.

### Documents and PPT: how Manus does it, and what to copy

Manus gives each task its own isolated virtual computer, called a sandbox. Files the task makes are kept there. An idle sandbox goes to sleep, and it is recycled after 7 days for Free users and 21 days for Pro users. When the user comes back, Manus restores the finished files, uploads and slide decks, but not the scratch files. The user can open "View all files in this task" ([Manus sandbox post](https://manus.im/blog/manus-sandbox)). Its engineers also share their lessons ([Manus context post](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)).

| Manus idea | What it means | Your version |
| --- | --- | --- |
| One sandbox per task | Each job has its own computer, so jobs cannot disturb each other | One container per task, with only that task's folder inside |
| Files are memory | Big text goes to a file, and the prompt keeps only the path or web address | Save search results and drafts as files, and keep only the path in the prompt. It cuts input tokens |
| A todo.md plan | The agent rewrites its to-do list after each step, so the plan stays fresh in the model's recent attention | The plan file is the same checklist the run card shows |
| Keep errors in view | A failed step stays in the history, so the model does not repeat it | Leave failed results in the context, and show a calm error card |
| A stable prompt start | If the start of the prompt never changes, the cache works. Their example: cached input cost 10 times less on Claude Sonnet | Keep the rules first, never change them mid-task, and only add to the history (section 8) |
| Restore only what matters | Finished files and uploads come back, scratch files do not | Keep the out and inputs folders, delete the work folder |

Manus reports about 100 input tokens for every 1 output token, and about 50 tool calls per task. That is why it saves file paths, not whole pages, and why the cache matters so much.

The steps for a document or a PPT on your screen:

1. The plan card lists: outline, write sections, add charts and images, build the file, check, export.
2. The harness writes the outline as JSON in the work folder, and the plan in todo.md.
3. Each section call reads only the outline and its own notes, not the whole chat (section 4).
4. Code builds the file in the out folder (python-docx or python-pptx, section 6). LibreOffice makes the preview pictures.
5. The Files panel shows a card with Open and Download as soon as the file exists.
6. A change such as "make slide 3 simpler" edits the JSON and rebuilds the file as version 2. Old versions stay until the retention time ends.

### Your workspace: one folder per user, one per task

**Clear meaning:** Every task gets a private folder that belongs to one user. The screen shows it with the user's name, for example "Sam's workspace", but the folder itself is named with the user's id.

```
workspaces/
  u_42/                          shown as "Sam's workspace"
    t_901_photosynthesis-ppt/
      todo.md                    the plan, rewritten after every step
      inputs/notes.pdf           what the user uploaded
      work/slide-data.json       drafts and scratch files
      out/photosynthesis.pptx    finished files, shown as file cards
      out/photosynthesis.pdf
      run-events.log             the events of the run
```

| Rule | Why |
| --- | --- |
| Name folders with the user id, and show the name on screen | Names repeat, change and can hold slashes |
| Check every path before use: it must end inside the user's own folder | Stops ../ tricks (path traversal) that reach other users' files |
| Task folders are temporary | The work folder is deleted when the task ends. The out and inputs folders stay for a set time, for example 7 days on Free and 21 days on Pro, like Manus. "Save to library" keeps a file longer and counts toward the storage limit |
| A storage limit per plan | Stops abuse and caps your storage bill. The numbers are your choice |
| Download links are signed and expire | A link cannot be guessed or reused for days. Example: 15 minutes |
| Scan every upload and every made file | Never show unknown file types inline, and never run uploaded programs |
| Code runs in a sandbox | A container with only this task's folder, no secrets and no open internet (section 13) |
| "Delete my files" is a real button | It removes the folders and the database rows, for privacy laws |

Keep the out files in S3 or R2 (section 10) and the work folder on the sandbox disk. A workspace\_files table lists each file: user, task, path, kind, size, version and delete date.

### Tools and skills references for this screen

| Need | Repo | Stars | License | Use it for |
| --- | --- | --- | --- | --- |
| Chat screen parts | [assistant-ui/assistant-ui](https://github.com/assistant-ui/assistant-ui) | 11.4k | MIT | Thread, composer, attachments, tool-call screens and approvals in React |
| Chat hooks and streaming | [vercel/ai](https://github.com/vercel/ai) | 26.7k | Not named on the page | useChat and streamed tool states. Pair it with the OpenRouter provider in section 13 |
| An open Manus-style agent to learn from | [FoundationAgents/OpenManus](https://github.com/FoundationAgents/OpenManus) | 58.1k | MIT | A general agent with browser tools and MCP. Its README calls the multi-agent flow unstable |
| An agent platform with sandboxes | [kortix-ai/suna](https://github.com/kortix-ai/suna) | About 20k | Unclear: the page says both open source and source-available | Each session runs in a disposable Linux sandbox, with skills and MCP connectors. Read the LICENSE first |

Stars and licenses are what each page showed on 14 Oct 2026. The skills, MCP servers, prompting and research repos are in section 13.

## 15. The whole plan on one page

**Clear meaning:** This is the short version of everything. Read this page first. Open the numbered section only when you want the details.

Think of the contents card on a house plan: one line for each room, and a number that tells you which page to open.

| Piece | The decision | Where |
| --- | --- | --- |
| Product | A chatbot sold by credits, for study and work, with a smart manager (the harness) around the AI | 1, 9 |
| Gateway | Every AI call goes through OpenRouter: one key, many brains | 3, 8 |
| Path of a message | Message in, wallet check, router, mode, tools, checker, teacher layer, meter, answer | 2 |
| Modes | 10 modes: Fast, Normal, Deep, Think Again, Overthink, Council, Two Brains, Think Team, Research, Developer | 3, 4 |
| Brains | The user picks a brain per mode, or per role. Tiers are Quick, Smart, Genius, tagged Chinese or Western | 3 |
| Effort | Auto, Off, Low, Medium, High, Max. Free gets Off and Low, Student up to High, Pro up to Max | 3 |
| Teaching | Simple words first, then an everyday example, then math. A memory card keeps the user's level | 4, 7 |
| Charts | The AI writes a chart recipe once, the browser draws it, and a slider move costs 0 tokens | 5 |
| Files | Images, Word, PDF and PPT are built in a per-user workspace folder and shown as file cards with Open and Download | 6, 14 |
| Screen | Claude-style chat: plan checklist, live tool cards, thinking summary, credits used, files panel, and sheets on a phone | 14 |
| Tools and skills | MCP servers and skill recipe cards. The user can allow or deny each one. A GitHub starter kit is listed | 13, 14 |
| Agents | Understand + Enhance, 1 to 3 planners and a plan judge, 0 to 4 architects, 1 to 5 researchers, builder, checker, finisher. Plain code is the boss. Every agent's brain, effort, count and cap can be changed, with Fast, Balanced and Full team presets | 16 |
| Research | OpenRouter's web search tool on any brain (Exa, Parallel or the lab's own search), or Perplexity Sonar models for quick facts and long reports | 16 |
| Front end | Fast first load, live streaming, resume after a network drop, no double charges, one clean composer with 3 chips | 17 |
| Money | credits = ceil(AI cost in dollars x 1.055 / 0.003). Hold credits first, then settle. Pro profit about 60% worst case, 72% typical | 8, 9 |
| Safety | Credit caps, upload scans, a sandbox, path checks, signed expiring links, and untrusted skills and servers | 11, 14 |
| Build order | Setup, MVP, Create, Grow, Optimize, with 2 gates | 12 |

### Decisions only you can make

- **Country and payments.** In Korea, Toss Payments is the likely choice. Other countries need other payment options.
- **Default brains.** Which brain is the default per mode, and which labs the School plan may use.
- **Plans.** The price and the credits of each plan.
- **Free plan.** How generous it is. A small free gift is a cost, so set a limit.
- **File retention.** How many days files stay, per plan. The 7 and 21 days in this plan are examples.
- **Product name.**

### Next 5 steps

1. Make one real OpenRouter call. Compare usage.cost with tokens times price. This proves your money math.
2. Build the screen shell with the run card, driven by fake events, so you can watch it move.
3. Build the wallet ledger with hold and settle.
4. Add Fast and Normal, with the mode, brain and effort pickers reading the live model list.
5. Add the chart recipe engine, then pass Gate A (margin above 60% and zero ledger mismatches).

## 16. The agent team: understand, plan, research, build, finish

**Clear meaning:** An agent is one AI helper with one job. For every big task the harness runs a small team of them. Plain code is the boss: it starts each agent, runs some at the same time, and stops at the credit cap. The user sees a card for every agent on the run card (section 14) and can change every setting.

Everyday picture: building a house. One person listens to what you want (understand) and writes it as a clear order (enhance). A few planners draw plans and a lead picks the best (plan judge). Architects draw the rooms, researchers check prices and rules, builders build, an inspector checks, and a site manager walks through everything before handing you the keys (finisher).

&#91;embedded content: agent team · 9 agents, plain code is the boss\]

Read it from top to bottom. Dashed boxes are optional. Boxes on one row run at the same time, so 3 planners take about as long as 1.

### The agents

| Agent | Its one job | Hands on | Default brain (example) | Default |
| --- | --- | --- | --- | --- |
| Understander | Reads the message, memory and files. Finds the goal, the user's level, what is missing, and whether research or files are needed | A task card (JSON) | Claude Haiku 5.5 | Always on |
| Prompt enhancer | Rewrites the task as a clear prompt for the next agent. After the answer, writes 2 or 3 next-step prompts as buttons | A better prompt, next-step buttons | Same call as the Understander | On. The user can see and edit the better prompt |
| Planner (1 to 3) | Writes the step list, with a goal and a check for each step | A plan | DeepSeek V4 Pro | 1 planner on Deep and up |
| Plan judge | Merges the plans into one. Asks the user to approve when plan mode is Ask me | The final plan (todo.md) | Claude Haiku 5.5 | On with 2 or more planners |
| Architect (0 to 4) | Designs the structure before building: UI, data, slides or document, code | A short blueprint | Claude Sonnet 5.5 | Off. On for Developer, documents and PPT |
| Researcher (1 to 5) | Searches the web and reads sources for its part of the plan | Notes with links | See research below | 1, or 3 in Research mode |
| Builder | Does each step with tools: chart, image, document, PPT, code | Results and files | The mode's main brain | Always on |
| Checker | Tests each step: math, chart recipe, links, empty slides | Pass, or what to fix | Claude Haiku 5.5 | Always on |
| Finisher | Ticks every plan item, joins the parts, applies the teaching style, adds sources and credits used | The final answer and files | The mode's main brain | Always on |

Understand and Enhance are one call on a fast brain. Example: Haiku 5.5 reads 2,000 tokens and writes 400, which costs $0.0004, under 1 credit, so fold it into the run price.

### Planning mode on every step

**Clear meaning:** The plan shows before work starts, and every step has its own small goal and check.

- **Plan mode:** Off (just answer), Auto (plan only big tasks, the default), or Ask me (show the plan and wait for Approve or Edit).
- **Planning depth:** Light (one plan at the start), Normal (re-plan after a failed step), or Deep (re-plan after every step, like Manus rewriting todo.md).
- **Planners:** 1, 2 or 3, each with its own brain and effort. More planners catch more mistakes but cost more.
- **Step card:** goal, agent, brain, effort, status, time and credits.

Worked example, a plan from 2 planners:

- **Input:** Planner A (DeepSeek V4 Pro) and Planner B (Qwen3.8 Max) each read 3,000 tokens and write 1,200. The plan judge (Haiku 5.5) reads 3,000 and writes 600.
- **Step:** DeepSeek costs $0.0016, Qwen $0.0132, the judge $0.0006. The sum is $0.0154. Times 1.055 (OpenRouter fee), divided by $0.003 per credit = 5.4.
- **Output:** round up to 6 credits for the plan.

### Architects: pick only the ones you need

- **UI architect:** screens, parts and states.
- **Data architect:** tables, fields and APIs.
- **Slide or document architect:** outline, sections, and the chart or picture for each part.
- **Code architect:** files, modules and tests.

Each writes a short blueprint (under 1,500 tokens) into the work folder. The builder reads only the blueprint it needs, so prompts stay small (files are memory, section 14).

### Research: OpenRouter search or Perplexity

**Clear meaning:** Any brain on OpenRouter can search the web through one tool. Perplexity's Sonar models search by themselves. Pick the cheaper one that is good enough for each job.

- Ask for search with the web search server tool: add {"type": "openrouter:web\_search"} to tools. The brain decides when and how often to search. OpenRouter marks the older web plugin and the :online suffix as deprecated, so do not build on them.
- Engine auto uses the lab's own search for Claude, GPT, Gemini, Grok and Perplexity models. Other brains, such as DeepSeek, Qwen and Kimi, use an outside engine: Exa, Parallel or Perplexity.
- Limits: max\_uses caps searches per call, max\_total\_results caps results, and max\_tool\_calls caps all tool steps (default and maximum 30). Only Anthropic receives max\_uses natively, so also count searches in your own code.
- Sources come back as url\_citation items with a link and a title. Show them as numbered source chips.

| Job | Use | Price on OpenRouter (15 Oct 2026) |
| --- | --- | --- |
| Quick fact with a link | perplexity/sonar | $1 in, $1 out per million tokens |
| Research with a Chinese brain | That brain + the search tool, engine Exa or Parallel | Exa $0.007 a search, Parallel $0.001 to $0.005 |
| Research with Claude, GPT or Gemini | That brain + its own search | The lab's price, Claude $10 per 1,000 searches |
| Any brain, Perplexity engine | The search tool, engine perplexity | $0.005 a search |
| Hard multi-step question | perplexity/sonar-pro-search | $3 in, $15 out, plus $18 per 1,000 requests |
| Long report | perplexity/sonar-deep-research | $2 in, $8 out, $3 per million reasoning tokens, $5 per 1,000 searches |

Research team: 1 to 5 researchers run at the same time. Each takes a different sub-question from the plan and can use a different brain or engine. The Finisher keeps only facts with links and marks where sources disagree.

Worked example, a 3-researcher team:

- **Input:** each researcher makes 2 searches, reads 6,000 tokens (search pages count as input) and writes 800. R1 is DeepSeek V4 Pro with Exa. R2 is Qwen3.8 Flash with the Perplexity engine. R3 is Claude Sonnet 5.5 with its own search. The writer (Sonnet 5.5) reads 4,000 and writes 1,500.
- **Step:** R1 $0.0021 + $0.014 search = $0.0161. R2 $0.0013 + $0.010 = $0.0113. R3 $0.020 + $0.020 = $0.040. Writer $0.023. The sum is $0.0904. Times 1.055, divided by $0.003 = 31.8.
- **Output:** 32 credits. With DeepSeek in place of Claude for R3: 24 credits.

A Sonar Deep Research report with 20 searches, 20,000 reasoning tokens and 6,000 output tokens costs about $0.21, which is 75 credits. The number of searches changes per question, so always set a credit cap.

### Customize everything, but keep it simple

- One Team chip in the composer opens the team panel. The defaults work if the user never opens it.
- Presets: **Fast** (no planner, no research), **Balanced** (1 planner, 1 researcher), **Full team** (3 planners, architects, 3 researchers, Deep planning).
- For each agent: on or off, brain, effort, count and credit cap.
- Save the settings as a team profile and pick a profile per chat. School admins can lock profiles.
- The estimate updates as settings change, and the hold covers the maximum (section 9).

One team profile (example; copy each model's exact name from OpenRouter's list):

```json
{"name": "Full team", "plan_mode": "ask", "plan_depth": "deep",
 "understand": {"model": "anthropic/claude-haiku-5.5"},
 "planners": {"count": 3, "models": ["deepseek/deepseek-v4-pro-0813", "qwen/qwen3.8-max", "anthropic/claude-sonnet-5.5"], "effort": "medium"},
 "architects": ["ui", "data"],
 "researchers": {"count": 3, "engine": "auto", "max_searches_each": 2},
 "checker": {"model": "anthropic/claude-haiku-5.5"},
 "max_credits": 150}
```

### Speed rules for the team

- Skip the team by plain rules: a greeting or a short question goes straight to Fast.
- Run agents that do not depend on each other at the same time: planners, architects and researchers.
- Use small, fast brains for small jobs: understand, judge and check.
- Send each agent's status to the screen the moment it starts.
- Give each agent a time limit (example: 60 seconds), then switch to the next brain in its fallback list.
- Keep the start of every prompt the same, so the cache works (section 8).

## 17. A fast, reliable and clean front end

**Clear meaning:** The screen should open at once, never freeze, never lose work and never charge twice. It shows only what matters, and the hard parts hide behind one tap.

Everyday picture: a good shop counter. It is clean, the service is quick, and you get a receipt for everything.

| Goal | How |
| --- | --- |
| Fast first load | A Next.js shell served from a CDN. The chart engine, PPT preview, code view and team panel load only when opened (code splitting). Keep the first-load script small (example budget: 200 KB compressed) |
| Fast feel | Show the user's message and an Understanding card at once (optimistic UI). Stream words and steps as they arrive |
| Smooth long chats | Draw only the messages on screen (a virtual list). Heavy work, like chart data and file reading, runs in a Web Worker so typing never lags |
| Never lose a run | The job runs on the server queue, not in the browser, so closing the tab does not stop it. Every event has a number. After a network drop the browser reconnects with the last number it got (the SSE Last-Event-ID header) and receives only what it missed |
| Never charge twice | Every send and payment carries an idempotency key (a unique id), so a retry does not run or charge again |
| Calm errors | Retries with waits that grow, fallback brains, an offline banner, and a Retry card instead of a blank screen |
| Full transparency | Every agent card shows brain, effort, status, time and credits. Sources are chips. Raw inputs and outputs sit in Details |
| Clean | One composer with 3 chips: Mode, Team and Tools. Advanced settings live in one sheet. The same layout on web and app |
| Watch it | Error tracking (Sentry), speed numbers from real users, and browser tests (Playwright) for send, stop, reconnect and download |

Speed targets (examples; measure them with real users):

- The message appears on screen in under 100 ms.
- The first words of a Fast answer arrive in under 1.5 seconds.
- The plan card of a Deep task shows in under 4 seconds.
- After a network drop, the screen reconnects in under 2 seconds with no lost steps.

## Sources

All pages opened on 14 Oct 2026.

- [Claude API pricing](https://platform.claude.com/docs/en/about-claude/pricing): model prices, prompt caching, batch discount, web search price, token counting, usage fields.
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing): image prices for Nano Banana 2.1 and Nano Banana Pro.
- [Cursor pricing](https://cursor.com/pricing): weekly usage refresh, top-offs, spending caps.
- [Lovable pricing](https://lovable.dev/pricing): credits by work done, cost shown per message.
- [OpenAI business pricing](https://openai.com/business/pricing/): unlimited with abuse guardrails; credit-based and token-based Enterprise pricing.

OpenRouter and GitHub pages, opened on 14 Oct 2026:

- [OpenRouter FAQ](https://openrouter.ai/docs/faq): no markup on inference, the 5.5% credit fee, rate limits, default logging.
- [Reasoning tokens](https://openrouter.ai/docs/use-cases/reasoning-tokens): effort levels, thinking billed as output.
- [Usage accounting](https://openrouter.ai/docs/use-cases/usage-accounting): the cost field and token details.
- [Provider routing](https://openrouter.ai/docs/features/provider-routing): data collection, required parameters, host fallbacks.
- [Model routing](https://openrouter.ai/blog/insights/model-routing/): the models fallback list and how it is billed.
- [Zero data retention](https://openrouter.ai/docs/features/zdr): the per-request privacy setting and its limits.
- [Prompt caching](https://openrouter.ai/docs/features/prompt-caching): which models cache by themselves.
- [Models API](https://openrouter.ai/docs/guides/overview/models): price units and fields.
- [Image generation](https://openrouter.ai/docs/features/multimodal/image-generation) and [web search](https://openrouter.ai/docs/web-search): how to ask, and engine prices.
- [The Open Weight Models that Matter: June 2026](https://openrouter.ai/blog/insights/the-open-weight-models-that-matter-june-2026/): the privacy price gap for DeepSeek.
- Lab pages with model prices: [DeepSeek](https://openrouter.ai/deepseek), [Qwen](https://openrouter.ai/qwen), [Moonshot AI](https://openrouter.ai/moonshotai), [Z.ai](https://openrouter.ai/z-ai), [MiniMax](https://openrouter.ai/minimax), [Anthropic](https://openrouter.ai/anthropic), [OpenAI](https://openrouter.ai/openai), [Google](https://openrouter.ai/google).
- GitHub: every repo page linked in sections 13 and 14, for stars, license and description.

* [Manus sandbox post](https://manus.im/blog/manus-sandbox): the per-task sandbox, sleep and recycle times, which files come back (section 14).
* [Manus context post](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus): files as memory, todo.md, keeping errors, cache-friendly prompts (section 14).
* [MCP tools spec](https://modelcontextprotocol.io/specification/2025-06-18/server/tools): a person who can deny, visible tool use, untrusted descriptions (section 14).

- [OpenRouter web search tool](https://openrouter.ai/docs/guides/features/server-tools/web-search): the openrouter:web\_search tool, engines, limits, which labs search natively, and that the web plugin and :online are deprecated (section 16).
- [Perplexity on OpenRouter](https://openrouter.ai/perplexity): Sonar model names and prices (section 16).
