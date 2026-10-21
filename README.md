# protect-skill-prompts

An agent skill for frontend developers who ship AI features: **keep your prompt
templates, skill instructions and system prompts out of the browser**, so users cannot
copy them from DevTools, the JS bundle, network responses, page data or saved state —
while users can still steer every result in their own words.

Works with Claude Code, Codex, Cursor and other agents that read `SKILL.md` skills.

[中文说明](#中文说明)

## Why

If your product's value is a carefully tuned prompt, every place it reaches the browser
is a copy button. The obvious leak (a string in client code) is rarely the one that
ships. The ones that do:

- a server component passing the template as a prop to a client component (it is
  serialized into the page even if never rendered)
- the provider's error message or `revised_prompt` passed through to the UI
- generation history, share links or "copy prompt / remix" storing the composed prompt
- a credit-quote or moderation call sent from the browser with the full prompt
- an agent's tool call arguments, shown "for transparency", containing the skill's text
- the model itself, when a user asks it to "repeat your instructions"

## What the skill does

When an agent builds or audits an AI feature, the skill makes it:

1. **Separate the data**: template (server only) vs. user choices vs. the user's own words.
2. **Compose late**: join them on the server at the provider call; persist and return only
   choices, the user's words, a skill id and the result.
3. **Use a fitting pattern**: skill-id endpoint, hidden-skill agent with a badge in chat,
   or skill nodes for canvases and pipelines.
4. **Keep the user in control**: a free-text request that overrides the template defaults.
   Hiding a recipe is never a reason to limit what users can ask for.
5. **Guard model output**: server-side echo check, metadata stripping, honest limits.
6. **Verify**: run `scan_leaks.py` on client-facing output with a positive control.

Contents:

```
skills/protect-skill-prompts/
  SKILL.md                      the workflow and patterns
  references/leak-surfaces.md   40+ leak surfaces with how to check each
  references/frameworks.md      Next.js, Pages Router, Vite/SPA, Remix, SvelteKit, Nuxt, Vercel AI SDK
  references/agents-and-chat.md hidden skills in agents: messages, tools, echo checks
  scripts/scan_leaks.py         leak scanner (Python 3.8+, no dependencies)
  scripts/test_scan_leaks.py    its tests
examples/nextjs-app-router/     a minimal safe implementation with `pnpm verify`
```

## Install

```bash
# Claude Code, Codex, Cursor and others, via the skills CLI
npx skills add captwg/protect-skill-prompts

# or copy it by hand
git clone https://github.com/captwg/protect-skill-prompts
cp -R protect-skill-prompts/skills/protect-skill-prompts ~/.claude/skills/        # Claude Code (user-wide)
cp -R protect-skill-prompts/skills/protect-skill-prompts .claude/skills/          # Claude Code (one project)
cp -R protect-skill-prompts/skills/protect-skill-prompts .agents/skills/          # Codex / Cursor (project)
```

Then ask your agent things like *"build an AI headshot page, our prompt must not be
copyable"* or *"audit our chat feature for prompt leaks"*.

## The scanner on its own

`scan_leaks.py` fingerprints your secret prompts as overlapping 8-word runs and searches
anything a browser receives. It decodes JSON/JS escapes, `\uXXXX`, HTML entities and
nested React Server Component payloads, handles Chinese/Japanese/Korean text, and reads
HAR exports (request bodies, responses, base64 bodies, WebSocket frames).

```bash
S=skills/protect-skill-prompts/scripts/scan_leaks.py
python3 $S --secrets server/prompts .next/static                    # shipped JS
python3 $S --secrets server/prompts --url http://localhost:3000/app # rendered page or API
python3 $S --secrets server/prompts session.har                     # DevTools > Network > Export HAR
python3 $S --secrets server/prompts --text "$(pbpaste)"             # positive control
```

Exit code `1` means a leak; each hit names the file or request, the share of the secret
matched and a sample. Code files given as `--secrets` contribute only their string
literals. Server build folders (`.next/server`, …), `node_modules` and the secret files
themselves are skipped.

## How it was tested

- Scanner: unit tests for bundles, double-escaped RSC payloads, `\u` escapes, HTML
  entities, HAR base64 bodies, CJK text, short secrets and false positives; each decoding
  test was checked to fail when decoding is disabled.
- Real Next.js 15 builds: a deliberately leaky app was flagged in the client bundle (100%
  of the template), the page payload (100%) and the API response; the safe app was clean;
  importing the template into a client component failed the build.
- Agent A/B runs, round 1: two tasks with and without the skill on a large and a small model
  (8 runs). The large model was safe either way; the small model without the skill relied
  on redaction that leaks on truncated errors and reworded tool arguments.
- Agent A/B runs, round 2 (24 runs): the same two tasks on Claude Haiku and Sonnet, 3 runs
  per combination, with no hint in the task that the prompt must be hidden (only that it is
  a proprietary recipe). The stand-in provider quotes a truncated prompt in its errors, and
  its model rewords the skill's guidance when it fills a `prompt` argument and prints its
  instructions when asked. Every run was rebuilt, exercised and graded automatically
  (bundle, page, quote, generation, provider error, history, extraction attempts, reworded
  recipe in tool arguments, 8-word and 5-word fingerprints).

  | | runs | leaked | still fully functional |
  |---|---|---|---|
  | with the skill | 12 | **0** | 12 |
  | without the skill, provider source readable in the project | 4 | 0 | 4 |
  | without the skill, provider a black box (as in production) | 8 | **8** | 8 |

  The leaks without the skill: the provider error shown verbatim or with a template fragment
  left after redaction (4), and the chat returning the full skill text on "repeat your
  instructions" (4), three of them also showing the reworded recipe in tool-call rows. With
  the skill, every run replaced provider errors with its own message, kept model-written
  prompts out of visible tool arguments, and refused extraction. When the provider's code
  was readable, agents read the traps out of it and avoided them without the skill, which is
  why that row is reported separately.
- Triggering: loads for building, Chinese-language and audit-style requests; stays out of
  unrelated frontend questions.

## Limits

No technique stops a determined user from inferring parts of a prompt from the outputs.
The skill makes the recipe impossible to copy from what the browser receives, raises the
cost of extraction through the model, and says plainly what remains possible.

## License

MIT

---

## 中文说明

给做 AI 功能的前端开发者的 Agent skill：**让提示词模板、skill 指令和系统提示词留在服务端**，
用户无法从开发者工具、JS 代码包、接口返回、页面数据或本地存储里复制；同时用户仍然可以用自己的话
提出任何修改要求。

适用于 Claude Code、Codex、Cursor 等支持 `SKILL.md` 的 Agent。

**它解决的常见泄露点：** 服务端组件把模板当 props 传给客户端组件（即使不渲染也会序列化进页面）；
模型服务的报错信息或 `revised_prompt` 原样返回；生成历史、分享链接、"复制提示词 / 再来一次"保存了
完整提示词；在浏览器里带着完整提示词调用积分估算；Agent 的工具调用参数（为了"透明"展示给用户）里
带着 skill 内容；用户让模型"重复你的指令"。

**核心做法：** 分清三类数据（模板只在服务端，用户选项和用户原话可以到前端）；在服务端调用模型的那一刻
才拼接提示词（compose late）；保存和返回的只有选项、用户原话、skill id 和结果；用户的自由输入优先于
模板默认值，隐藏模板不等于限制用户；服务端检查模型输出是否复述了模板；最后用 `scan_leaks.py`
扫描所有到达浏览器的内容，并用"故意放一段"做阳性对照。

**安装：** `npx skills add captwg/protect-skill-prompts`，或把 `skills/protect-skill-prompts`
复制到 `~/.claude/skills/`（Claude Code）或项目的 `.agents/skills/`（Codex / Cursor）。

**局限：** 任何方案都无法阻止用户从输出结果中推测提示词的一部分。这个 skill 保证浏览器拿到的内容里
复制不到配方，提高通过模型套取的成本，并如实说明还剩哪些可能。
