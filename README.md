# backlog-crew

A crew of AI agents that turns a GitHub backlog into pull requests, for any repository.
It runs on Amazon Bedrock AgentCore Runtime, is built with Strands Agents, and reaches
GitHub through AgentCore Gateway (MCP).

```
product spec ─┐
              ├─► planner ──► issues labeled `proposed`
code ─────────┘                    │  a human reviews and relabels → `agent-ready`
                                   ▼
              GitHub Action in the target repo
                                   ▼
                             orchestrator ── developer (one per area)   writes code
                                   │         integration_check          read-only
                                   │         reviewer                   read-only
                                   ▼
               branch backlog-crew/issue-N → pull request → a human merges
```

The crew knows nothing about your project until you describe it in a
**`.backlog-crew.yaml`** file in your repo. One deployment can serve many repositories.

## The agents

| Agent | What it does |
|---|---|
| **planner** | Compares your product spec with the code and open issues, and creates up to N issues labeled `proposed`. It never approves its own issues. |
| **orchestrator** | Takes one `agent-ready` issue, briefs the developers, runs the checks, and opens a PR with `Closes #N`. After `MAX_REVIEW_ROUNDS` failed rounds it comments on the issue and stops. |
| **developer** | One per area in your config. Reads the whole repo, writes only inside its area, and runs that area's test command before finishing. |
| **integration_check** | Only if you configure `integration_checks`. Checks both sides of an interface between areas agree (API paths, fields, types). |
| **reviewer** | Reviews the full diff for bugs, security gaps, failing tests and your rules. Returns APPROVE or CHANGES. |

The specialists report only to the orchestrator and never talk to each other. Agents can't
push, merge, change labels or run arbitrary shell commands: they get file tools and an
allowlisted command runner, and only the orchestrator's code commits and pushes.

---

## Using the crew on a GitHub repository

Do steps 1–2 once, when you deploy the crew. Do steps 3–7 for every repository you add.

### 1. Deploy the crew (once)

**You need:** an AWS account with Bedrock and AgentCore in your region, the AWS CLI v2, `uv`,
the CDK CLI (`npm i -g aws-cdk`) and Docker.

**a. Log in to AWS.** Use an AWS CLI profile that can create IAM roles, ECR, Secrets
Manager and AgentCore resources. For SSO profiles:

```bash
aws sso login --profile <aws-profile>
aws sts get-caller-identity --profile <aws-profile>   # check it's the account you expect
```

**b. Fill in your deploy settings.**

```bash
cp deploy.env.example deploy.env
```

Set `AWS_PROFILE`, `AWS_REGION` (or leave it empty to use the profile's region),
`ALLOWED_REPOS` and `MODEL_ID`. `deploy.env` is git-ignored: your account, region and repo
names stay out of this repo. To see the model ids your region offers:

```bash
aws bedrock list-inference-profiles --profile <aws-profile> \
  --query "inferenceProfileSummaries[?contains(inferenceProfileId,'claude')].inferenceProfileId"
```

Prefer a `global.` or regional (`us.`, `eu.`, `apac.`, `au.`) inference profile over a bare
model id.

**c. Create the GitHub token** as described in
[Choosing the crew's GitHub identity](#choosing-the-crews-github-identity), then store it:

```bash
scripts/put-github-token.sh   # prompts for the token; input is hidden, nothing is saved locally
```

Run it again whenever you rotate the token. Nothing needs redeploying.

**d. Let Docker build arm64 images** (AgentCore runs linux/arm64). On an Apple Silicon Mac
this already works. On an x86 machine or WSL, install QEMU emulation once:

```bash
docker run --privileged --rm tonistiigi/binfmt --install arm64
```

**e. Deploy.**

```bash
scripts/deploy.sh diff   # optional: preview the changes
scripts/deploy.sh
```

The script checks your login, the token secret and Docker. It bootstraps CDK the first time,
builds and pushes the image, and creates the Gateway, Identity provider and Runtime. The first
deploy takes 10–20 minutes, mostly the emulated image build. It ends by printing
`RuntimeArn` and `GatewayUrl`, which are also saved to the git-ignored `cdk-outputs.json`.

Run `scripts/deploy.sh` again after changing code, `deploy.env` or the Dockerfile. To remove
everything, run `cdk destroy --profile <aws-profile>`. The token secret stays; delete it
separately if you want.

### Choosing the crew's GitHub identity

GitHub has no "service accounts". The crew needs a token, and whoever owns that token is who
the commits, PRs and comments appear to come from. Pick one of these:

| Option | Good for | Trade-off |
|---|---|---|
| **Fine-grained PAT from your own account** | Getting started on your own repos | PRs show as opened by you, so you can't approve them yourself (matters if you protect `main` with required reviews). |
| **Machine user** (a second GitHub account, e.g. `yourname-bot`) **+ its PAT** (recommended) | Real use: the bot opens PRs and you review them | One more account to manage. GitHub allows one free machine account per person. |
| **GitHub App** | Teams and many repos | Not supported yet: App tokens expire every hour, and the Gateway holds a static token. Planned. |

**Setting up a machine user:**

1. Sign out (or use a private window) and create the account, e.g. `yourname-bot`, with its
   own email. Turn on 2FA.
2. Give it access to each target repo. For a personal repo, go to **Settings → Collaborators →
   Add people**, choose **Write**, and accept the invite as the bot. For an organization, add
   the bot as a member with Write on the repos.
3. Create its token, signed in as the bot (see below).

**Creating the token** (signed in as whichever account will act):

- **Fine-grained token**: **Settings → Developer settings → Personal access tokens →
  Fine-grained tokens → Generate new token**.
  - Resource owner: the account or organization that owns the repos.
  - Repository access: **Only select repositories**, then pick the target repos.
  - Repository permissions: **Contents**, **Issues** and **Pull requests** set to
    *Read and write*. *Metadata: Read* is added automatically. Leave **Workflows** off, so the
    crew can't change your CI.
  - Expiration: up to a year. Put a reminder in your calendar to rotate it with
    `scripts/put-github-token.sh`.
  - Organizations may need to approve fine-grained tokens first (**Org settings → Personal
    access tokens**).
- **Classic token, only if a fine-grained one can't reach the repo.** A fine-grained token
  only covers repos owned by one resource owner where the account is the owner or an org
  member. For a bot that is just a *collaborator* on someone else's personal repo, use a
  classic token with the `repo` scope instead. It's broader, so keep that bot's access to the
  minimum.

### 2. Check GitHub is reachable (once)

```bash
set -a; source deploy.env; set +a
GATEWAY_URL=<GatewayUrl> uv run python scripts/list_gateway_tools.py
```

You should see a list of `github___...` tools. If you get a 401, see
[Known gaps](#known-gaps-to-check-on-first-deploy).

### 3. Allow the repository

Add the repo to `ALLOWED_REPOS` in `deploy.env` and run `scripts/deploy.sh`. Also give the
GitHub token access to it: add it to the fine-grained token's repository list, or add the bot
as a collaborator.

### 4. Describe the project

Copy [`templates/backlog-crew.yaml`](templates/backlog-crew.yaml) to the root of the target
repo as **`.backlog-crew.yaml`** and fill it in. Every field is explained in the file:

| Field | Required | What it's for |
|---|---|---|
| `project.name`, `project.description` | name | What the product is and what's in or out of scope right now. Every agent sees this. |
| `spec` | no | Path to the product spec (default `docs/product-spec.md`). |
| `areas.<name>.path` | yes | A folder one developer agent owns. Use `.` for a single-area repo. |
| `areas.<name>.description` | no | The stack and what lives there. |
| `areas.<name>.test` | no | The command the developer must pass, run inside `path`. Its first word becomes an allowed command. |
| `areas.<name>.rules` | no | Conventions the developer follows and the reviewer checks. |
| `integration_checks` | no | Groups of areas whose interfaces must agree, e.g. `[[api, web]]`. |
| `review.rules` | no | Extra checks for every change. |
| `planner.max_issues` | no | Most issues per planner run (default 5). |

The more specific the rules, the better the output: a rule you leave out is a rule the agents
won't follow. Changes apply on the next run; no redeploy needed.

### 5. Write the product spec

Add the spec at the path in `spec`. Describe what the product must do, as features and
acceptance criteria. The planner compares this with the code; without it, the planner creates
no issues. You can skip this if you'll only write issues by hand.

### 6. Create the labels

In the target repo, create the labels **`proposed`** (the planner's suggestions) and
**`agent-ready`** (approved for the crew).

### 7. Add the trigger

Copy [`examples/agent-ready-trigger.yml`](examples/agent-ready-trigger.yml) to the target repo
as `.github/workflows/backlog-crew.yml`. Under **Settings → Secrets and variables →
Actions**, add the variable `BACKLOG_CREW_AWS_REGION` (your region) and two secrets:

- `BACKLOG_CREW_AWS_ROLE_ARN`: an AWS role trusted for this repo via GitHub OIDC, allowed to
  call `bedrock-agentcore:InvokeAgentRuntime` on the runtime.
- `BACKLOG_CREW_RUNTIME_ARN`: the `RuntimeArn` output.

### Day to day

1. **Plan:** run `RUNTIME_ARN=... scripts/invoke.sh plan acme/shop`, or on a schedule.
   Review the new `proposed` issues; edit, close or relabel them.
2. **Build:** add `agent-ready` to an issue, either a planner issue or one you wrote. The
   Action starts the crew, and a PR from `backlog-crew/issue-N` appears when it's done.
3. **Merge:** review the PR like any other. If the crew gets stuck, it comments on the
   issue explaining why.

You can also start a run by hand: `scripts/invoke.sh run acme/shop 42`.

---

## Config files

| File | Where | In git? | What it holds |
|---|---|---|---|
| `deploy.env` | this repo | **no** (copy from `deploy.env.example`) | AWS profile and region, allowed repos, model id, token secret name |
| `.env` | this repo | **no** (copy from `.env.example`) | Settings for running the crew locally |
| `cdk-outputs.json` | this repo | **no** (written by `scripts/deploy.sh`) | `RuntimeArn` and `GatewayUrl` from the last deploy |
| `cdk.json` | this repo | yes | Generic CDK defaults; overridden by `deploy.env` |
| `.backlog-crew.yaml` | **each target repo** | yes, in that repo | The project description, areas, rules and spec path (template in `templates/`) |
| GitHub token | AWS Secrets Manager | never | Written by `scripts/put-github-token.sh` |

## How it fits together

| Piece | Role |
|---|---|
| AgentCore Runtime | Runs `backlog_crew.app` from `runtime/Dockerfile` (arm64). The image has the toolchains the agents use to build and test. |
| AgentCore Gateway | MCP endpoint (AWS_IAM auth, SigV4-signed by the runtime role) with GitHub's MCP server as target `github`, for issues, comments and PRs. |
| AgentCore Identity | API-key provider `backlog-crew-github-token`, backed by the Secrets Manager secret. Used by the gateway and for `git clone`/`push`. |
| Bedrock | Claude via Strands `BedrockModel`. Override per agent with `MODEL_ID_<AGENT>`, e.g. `MODEL_ID_REVIEWER`. |

Code changes don't go through MCP: each run makes a real shallow `git clone` in the
container so the agents can run tests.

**Toolchains.** The image has Java 21, Node 22, Python 3.12, Go and make. If a repo's
`test` command needs something else (Rust, .NET, PHP...), add it to `runtime/Dockerfile`
and redeploy.

```
src/backlog_crew/
  app.py               entrypoint: {"mode":"plan","repo":...} | {"mode":"run","repo":...,"issue":N}
  config.py            deployment settings (env vars)
  project.py           loads and validates .backlog-crew.yaml
  auth.py              GitHub token from Identity; SigV4 auth for the gateway
  agents/prompts.py    project-agnostic prompts
  agents/planner.py, orchestrator.py, specialists.py
  tools/github.py      gateway MCP client and per-agent tool allowlists
  tools/workspace.py   git checkout, file tools, guarded command runner
infra/                 CDK (Python): image, Identity provider, Gateway + target, Runtime, IAM
templates/             backlog-crew.yaml, the project config template
examples/              GitHub Action for target repos
scripts/               deploy.sh, put-github-token.sh, invoke.sh, run_local.sh, list_gateway_tools.py
```

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
```

To run locally: copy `.env.example` to `.env`, fill in `ALLOWED_REPOS`, `GATEWAY_URL` and
`GITHUB_TOKEN`, run `scripts/run_local.sh`, then:

```bash
curl -s localhost:8080/invocations -H 'content-type: application/json' \
  -d '{"mode":"plan","repo":"acme/shop"}'
```

Invocations return at once; the work runs in the background. Results show up on GitHub, and
progress and errors (such as a missing or invalid `.backlog-crew.yaml`) show up in the logs.

## Known gaps to check on first deploy

- **Gateway → GitHub auth.** The gateway sends the token as `Authorization: Bearer <token>`.
  If `list_gateway_tools.py` returns 401, check `credential_prefix` in
  `infra/stacks/crew_stack.py`.
- **GitHub MCP tool names** change between server releases. The allowlists in
  `tools/github.py` include old and new spellings; trim them to what `list_gateway_tools.py`
  prints.
- **Config errors are only logged.** If `.backlog-crew.yaml` is missing or invalid, the run
  stops and the reason is in CloudWatch, not on the issue.
- **`test` commands are trusted.** Whatever a repo's config puts there, the agents may run, so
  only allow repos whose config you control.
- **Session length.** A runtime session lasts up to 8 hours. Keep issues to size S or M.
- **No deploy agent.** Infrastructure and deployment changes stay with humans.
