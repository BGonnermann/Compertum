# Solo quant system build preparation

A supervised solo quant system needs a defined trading problem, usable data, a reproducible research pipeline, protected evaluation, and reliable paper execution. Machine learning and a mathematician worker can contribute throughout that pipeline when their claims have explicit tests.

Status: draft preparation brief, dated 8 October 2026. This is a proposed starting scope and input checklist; implementation decisions remain open. It uses the current discussion and public research.

The proposed first milestone is an end-to-end paper-trading system controlled through a terminal. Trading profitability is a separate result to establish through fresh evidence.

## Confirmed inputs and remaining details

| Input | Confirmed | Remaining detail |
| --- | --- | --- |
| Purpose | Supervised solo quant research and trading system | Personal-capital scope is proposed; benchmark and success criteria need definition |
| Market | Stocks | Initial stock watchlist and whether to include ETF benchmarks |
| Horizon | Daily, weekly, and monthly candidates | Compare predefined horizons under fixed evaluation rules |
| Machine | Windows 11, Ryzen 7 7700X, RTX 5070 Ti, 64 GB DDR5, 1 TB storage | Free space, GPU driver/framework compatibility, and desktop availability |
| Budget | Around $300 monthly, answering the monthly-budget question | Account for existing subscriptions and worker API charges within the ceiling |
| Broker | Alpaca brokerage | Confirm paper account, order permissions, and reconciliation behavior during integration |
| Data | Alpaca is the initial source | Basic-plan entitlement, sample extraction, feed, adjustments, timestamps, and historical coverage need verification |
| AI | Local and hosted models | Choose endpoints and models through bounded capability and cost checks |
| Repository | New repository | Name and hosting; private version control is proposed |
| Supervision | Human terminal monitoring is part of the requested design | Operating hours and alert route |
| Future live constraints | Live capital and loss limits have not been supplied | Set these before any live phase; the first milestone uses paper execution |
| Research priorities | ML and a mathematician worker requested | Proposed first tasks are return/risk prediction and covariance-estimator review |

Account names, provider names, and access status are sufficient for planning. Credentials belong in a local secret store or deployment secret manager.

Before data integration, extract a small representative Alpaca sample and document its feed, schema, adjustment and timestamp rules. Verify coverage for the selected symbols. Before paper integration, confirm paper permissions and order/status behavior. The operating ceiling is around $300 per month; check actual costs and existing subscriptions before paid service choices.

## Proposed initial scope

Stocks, daily/weekly/monthly candidates, native Windows, Alpaca, mixed local and hosted AI, a new repository, and the monthly budget are user-supplied constraints. Proposed first-version choices are a small fixed stock watchlist, daily source data, paper execution, long-only unlevered positions, a simple benchmark, and terminal controls. Those design choices remain proposals.

The first version should already include one bounded ML experiment and one mathematician review through the same evaluation pipeline. AVO-style research and DREAM-style replay can be added after the pipeline produces reliable records.

Keep live allocation at zero during the initial build. The future live milestone requires separately specified constraints and authorization.

## Architecture options

| Approach | Structure | Tradeoff |
| --- | --- | --- |
| Small modular system, proposed starting approach | One repository; persisted task and experiment records; isolated research processes; separate execution gateway and independent watchdog | Keeps ownership inspectable while retaining process isolation |
| Distributed research platform | Multiple services, shared queues, independently scaled workers, more infrastructure | Useful when measured workload or availability needs justify additional deployment and recovery complexity |
| Broad discovery laboratory first | Many autonomous hypotheses and evolving search policies before completing execution | Emphasizes exploration but delays operational evidence and expands the evaluation problem |

Worker titles describe responsibilities. Several roles may use the same underlying model with different tools and permissions. Every task does not need its own continuously running model.

| Component | Owns | Boundary |
| --- | --- | --- |
| Terminal controls and coordinator | Run, pause, resume, status, task queue, budgets | Controls workflows; retains state outside model context |
| Data service | Versioned raw data, adjustment metadata, availability times, feature inputs | Defines what information was available at each decision |
| Research and ML workers | Literature, hypotheses, candidate models and features | Propose candidates in isolated workspaces |
| Mathematician worker | Definitions, derivations, counterexamples, mathematical hypotheses | Produces inspectable claims; cannot approve them |
| Experiment runner | Actual execution, metrics, logs, resource receipts | Produces artifacts from recorded code and data |
| Protected evaluator | Fixed timing rules, comparison criteria, holdouts, selection controls | Workers cannot rewrite its criteria or access protected final feedback |
| Independent audit | Reruns, raw-artifact inspection, evidence status | Distinguishes passed, failed, and unverified checks |
| Strategy and model registry | Versions and evidence required for promotion | Research status does not imply permission to trade |
| Execution and risk gateway | Authorized version, position rules, order identity, account reconciliation | Sole route to broker actions |
| Watchdog and reporting | Independent health checks, alerts, reports, recoverable records | Detects missing heartbeats and unexplained account state |

Data, model, and code artifacts should have stable identifiers and content hashes. Each candidate records its hypothesis, parent version, dataset, feature timing, parameters, seed, environment, budget, result, and rejection or promotion reason. All attempts belong in the trial history.

Use separate candidate workspaces and a single owner for mutable broker state. Research workloads should have limits that preserve capacity for execution and monitoring.

### Proposed candidate path

A worker submits a hypothesis and candidate. The runner executes it. Protected validation checks the result. An independent audit inspects the evidence. Accepted candidates become reviewable paper candidates. Owner-approved versions reach the paper execution gateway.

Failed and unverified candidates remain recorded. A repeated attempt must explain what changed. A research task may finish with no accepted candidate.

Pause research, pause new orders, cancel outstanding orders, and close positions are distinct controls. Broker confirmation is needed before reporting the effect of an account action. Stopping an algorithm can leave holdings intact. [QuantConnect algorithm control](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/algorithm-control).

## Setup-specific recommendations

Use one native-Windows project with a persistent coordinator, isolated research tasks, a separate execution gateway, and an independent watchdog. The CPU and RAM are a reasonable starting point for daily-bar research and modest forecasting models. This is an engineering assessment, not a performance benchmark. Keep local LLM inference and model training under resource limits; initially run one GPU-heavy job at a time and reserve capacity for control and monitoring. One terabyte is total storage, not confirmed free space. Set retention limits and keep a recoverable backup elsewhere.

The same daily dataset can support proposed holding targets of 1, 5, and 21 trading sessions. Treat these as separate predeclared experiments, with overlapping-label controls and all variants counted. Choose based on fresh, cost-aware evidence. Automatic switching between horizons would be a further strategy requiring its own evaluation. A monthly series supplies relatively few time observations, even across years; more symbols do not make all observations independent.

For the first paper workflow, finish data collection after the session, record the signal's actual availability, and model execution in a later tradable session. Do not grant a strategy the same closing price used to calculate its completed daily signal. Confirm market calendars, daylight-saving behavior, final-bar timing, and next-session order handling in the execution specification.

### Alpaca data findings

Alpaca's current Trading API documentation lists Basic equity data as free, with history since 2016 and 200 historical API calls per minute. Basic real-time data is IEX only. Its FAQ says historical SIP queries are available without a paid subscription when the requested end time is at least 15 minutes old. Algo Trader Plus is listed at $99 per month. Thus the free plan is a reasonable first candidate for after-close research; actual account entitlement and symbol coverage still require a small authenticated extraction. Explicitly select and record the feed. IEX-only volume and prices can differ from the consolidated SIP feed.

Sources checked 7 October 2026 Eastern: [Alpaca market-data plans](https://docs.alpaca.markets/us/docs/about-market-data-api) and [market-data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq).

### Proposed monthly spending ceilings

| Category | Initial ceiling |
| --- | ---: |
| Hosted AI subscriptions and worker API use | $200 |
| Market data | $0 initially, using the verified free entitlement |
| Backup and essential services | $25 |
| Reserve for power, extra research, or a justified data upgrade | $75 |
| Total | $300 |

These are proposed allocations, not provider quotes or committed spending. Existing AI subscriptions count toward the AI ceiling. Start below the ceiling and retain unused funds. A paid data upgrade would require reallocating the budget rather than silently adding cost.

The initial terminal workflow runs during supervised sessions. A daily strategy does not itself ensure reliable execution while the desktop is asleep or offline. Specify awake hours, restart/reconciliation behavior, and unattended monitoring before scheduling routine paper orders.

## Machine learning research design

First choose the prediction target and the decision it supports. Forecasting return, ranking assets, estimating volatility, and forecasting liquidity are different tasks. A model score does not specify a portfolio or an executable order.

For each target, define the asset universe, forecast horizon, decision time, feature availability, label completion time, execution timing, and benchmark. Features must use only information available at the decision. Preprocessing is fitted on training data and then applied to later observations.

A useful first risk experiment could compare a simple rolling volatility estimate with a regularized forecast. A return-ranking experiment requires a suitable universe and enough history. The final choice depends on data availability and the owner's research priority.

| Stage | Candidate methods | Evidence needed to advance |
| --- | --- | --- |
| Baselines | Constant forecasts, simple rolling estimates, transparent trading rules | Reproducible data and timing; correct benchmark |
| Regularized models | Ridge, elastic net, logistic regression for a defined classification target | Incremental performance under the same evaluation contract |
| Nonlinear models | Shallow trees and bounded boosting experiments | Improvements that survive fresh periods and costs |
| More complex models | Compact neural models, ensembles, state or regime models | Enough effective data and a measured advantage over simpler candidates |
| Autonomous search | Bounded feature/model search and later policy replay | Complete trial accounting and selection-aware evaluation |

Public financial ML research supplies a reason to test nonlinear models. Gu, Kelly, and Xiu found useful nonlinear interactions in their asset-pricing study. That result does not choose a winning model for a different market, horizon, or execution policy. [NBER paper](https://www.nber.org/papers/w25398).

Keep two scorecards. The predictive scorecard measures error, calibration, or ranking against a baseline. The trading scorecard measures net performance, drawdown, exposure, turnover, and implementation costs. A prediction improvement must be tested through a fixed portfolio decision rule.

The main controls are chronological outer evaluation, training-only inner tuning, protected final evaluation, and a complete record of every searched variant. Same-time cross-sectional observations belong in the same time split. If outcome intervals overlap, remove training observations whose labels reach into evaluation and choose any gap from the actual timing rules. A generic row gap alone does not establish leakage safety. [TimeSeriesSplit documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).

Repeated feedback from a holdout can make it part of development. Limit its exposure and reserve fresh evidence. Record model, feature, and strategy variants together with failures. Selection-aware statistics such as the Deflated Sharpe Ratio supplement chronological evidence under their assumptions. [Generic holdout paper](https://arxiv.org/abs/1809.05596) and [Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf).

Retraining creates a challenger version. It does not silently replace the active model. Log the features actually served, monitor freshness and delayed-label performance, and validate training/serving agreement. Google's ML guidance emphasizes simple initial models and independently tested infrastructure. [Rules of ML](https://developers.google.com/machine-learning/guides/rules-of-ml).

## Mathematics worth implementing

Renaissance publicly describes work using data science, statistics, and applied mathematics to develop market models and trading algorithms. That supports a research direction, not access to its proprietary methods. The methods below are public quantitative tools. [Renaissance research scientist role](https://www.rentec.com/Careers.action?jobs=true&selectedPosition=researchScientist).

| Method family | Practical question | Initial use |
| --- | --- | --- |
| Probability and statistical inference | Could an apparent effect arise from noise or repeated selection? | Uncertainty, baselines, negative controls, trial accounting |
| Time series and filtering | Does earlier information help forecast later outcomes? | Autoregressive baselines, rolling estimates, later state-space models |
| Regularized statistical learning | Which features contribute under controlled complexity? | Ridge or elastic-net comparisons and feature ablations |
| Covariance and factor methods | Which exposures share risk? | Shrinkage estimates and portfolio risk measurement |
| Constrained optimization | How should forecasts, risk, and trading cost affect positions? | Transparent allocation with explicit constraints |
| Information and dependence measures | Does a candidate feature add information beyond existing inputs? | Bounded redundancy tests, conditional comparisons, and negative controls |
| Numerical analysis | Can a calculation become faster without changing its result? | Equivalent implementations and performance tests |

Start with claims small enough to verify. A useful algorithmic improvement or better estimator can be valuable without inventing an entirely new mathematical field.

### Four starter equations

These are illustrative public foundations. Their assumptions and parameter choices become part of the experiment contract.

**Autoregressive baseline**

```text
r[t+1] = a + sum(j=0 to p-1, phi[j+1] * r[t-j]) + epsilon[t+1]
```

Here r is a return measured at a fixed horizon, p is an integer at least one, and the parameters are fitted using training data. This tests whether past returns add forecasting information. For the stationary AR model, the roots of 1 - phi[1]*z - ... - phi[p]*z^p must lie outside the unit circle. Residual assumptions must also be specified. [Autoregressive models](https://otexts.com/fpp3/AR.html).

**Elastic-net prediction**

```text
choose a, beta to minimize:
  (1 / (2*T)) * sum(t=1 to T, (y[t] - a - x[t]^T beta)^2)
  + lambda1 * ||beta||1
  + (lambda2 / 2) * ||beta||2^2
```

The training target y is a precisely timed future outcome, for example y[t] = r[t+1]; x[t] contains only features available at the decision time. The penalties are nonnegative. Fit standardization on each training fold and tune penalties using chronological validation inside the development data. This controls fitted complexity, with no immunity to leakage or selection bias. [Regularized generalized linear models](https://www.jstatsoft.org/article/view/v033i01).

**Illustrative covariance shrinkage**

```text
Sigma_hat = (1 - delta) * S + delta * diagonal(S)
0 < delta <= 1
```

S is a positive-semidefinite training-sample covariance of simple asset returns at a common horizon. This particular diagonal target is a proposed transparent baseline, not a claim to reproduce a firm's estimator. Validate delta within development data. Positive diagonal entries in S and positive delta make this combination positive definite. Exclude zero-variance assets or specify and validate a variance floor; do not silently invert a singular estimate.

**Illustrative allocation objective**

```text
choose weights w to maximize:
  (1 - sum(w)) * r_cash + mu_hat^T w
  - (lambda / 2) * w^T Sigma_hat w
  - gamma * ||w - w_previous||1

subject to:
  sum(w) <= 1
  0 <= w[i] <= the approved nonnegative asset limit
```

mu_hat contains expected simple returns, Sigma_hat contains return covariances, and r_cash is the assumed cash return, all at the same horizon. lambda is positive and gamma is nonnegative. The return terms include the remaining cash; the quadratic term penalizes estimated risk; the final term is an assumed turnover-cost proxy. w_previous means current pretrade weights after market drift, not the previous target weights. This objective can choose no risky exposure. Specify all units, feasible position caps, financing assumptions, and trade thresholds consistently. The notation ^T means transpose; ||v||1 is the sum of absolute entries, and ||v||2^2 is the sum of squared entries. Actual fees and execution costs require separate modelling.

The objective expresses a decision rule under estimated inputs. It does not prove future profit or replace hard position and operational limits.

## Mathematician worker design

The worker receives a bounded problem, a baseline, explicit assumptions, a resource budget, and acceptance criteria. It may consult literature, derive equations, propose algorithms, seek counterexamples, and submit an implementation candidate with tests.

Example task: compare a proposed covariance estimator against the current estimator while preserving mathematical validity, then measure whether it improves later-period portfolio risk estimates or reduces allocation instability under the same constraints.

Each submission must contain:

- The precise claim, definitions, domains, units, and assumptions.

- Whether it is established mathematics, a reformulation, a conjecture, or a proposed empirical method.

- Relevant prior literature and how the proposed contribution differs.

- A derivation or proof attempt, worked examples, and limiting cases.

- Counterexample searches and numerical or symbolic checks.

- An implementation candidate, reproducible tests, and a falsifiable experiment.

- Evidence status and unresolved conditions.

Mathematical validation and financial validation are separate. A correct identity may have no forecasting value. A profitable-looking sample result may have no valid proof or future economic value.

Symbolic checks must preserve assumptions. For example, simplifying the square root of x squared requires attention to the domain and sign of x. SymPy's assumptions documentation makes this dependence explicit. A tool returning unknown leaves the claim unverified. [SymPy assumptions](https://docs.sympy.org/latest/guides/assumptions.html).

For appropriate claims, a formal proof checker can verify the formal statement under its declared assumptions. Numerical tests support computational checks but do not prove a universal theorem. A second AI review supplies critique, not mathematical certification.

Algorithm-discovery systems such as AlphaEvolve have produced verified improvements on bounded mathematical and computational problems using execution feedback. That motivates a measured discovery worker; it is not evidence that such a worker will discover tradable alpha. [AlphaEvolve paper](https://arxiv.org/abs/2506.13131).

The worker has no live credentials, no write access to protected holdouts or acceptance rules, and no authority to deploy or approve its own claims. Candidate code runs with bounded resources in an isolated workspace.

## Audits and failure tests

| Scenario | Required evidence |
| --- | --- |
| A worker reports success without a completed run | Audit remains unverified; candidate cannot advance |
| A feature uses future publication or label information | Timing checks reject the candidate |
| A covariance proposal produces invalid risk estimates | Mathematical checks reject it before allocation |
| A researcher repeatedly probes final evaluation | Access and trial records reveal the violation; fresh evaluation is required |
| Two workers retry the same task | Candidate identity prevents duplicate promotion; separate workspaces preserve artifacts |
| An order request times out | Reconcile broker order state before deciding whether to retry |
| The program restarts with existing holdings or orders | Recover documented state and reconcile against broker records |
| Data is stale or unavailable | Apply the predefined restriction on new decisions/orders and alert the owner |
| Research exhausts its budget | Stop the task and retain partial evidence |
| The trading process or monitor stops | Independent watchdog detects the missing heartbeat |
| A release changes results unexpectedly | Compare versions, retain evidence, and execute the tested recovery procedure |
| No candidate meets acceptance criteria | Report no accepted candidate without relaxing the criteria |

Broker events, simulated fills, cash, holdings, open orders, splits, dividends, and any financing costs need explicit accounting. Paper execution tests operational behavior but cannot fully establish real fill quality. [QuantConnect reconciliation](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/reconciliation).

Security, backups, deployment reproducibility, data permissions, bookkeeping, and the owner's incident instructions are operating requirements. Numerical live limits and any accounting or legal arrangements remain decisions to specify.

## Build sequence and completion criteria

| Stage | Deliverable | Evidence of completion |
| --- | --- | --- |
| 1. Scope and contracts | Confirmed market, timing, budgets, data semantics, and component ownership | Written decisions with testable acceptance criteria |
| 2. Research pipeline | Versioned data, baseline, chronological evaluator, records, terminal controls | Independent rerun reproduces the recorded result |
| 3. ML and mathematics | One bounded ML comparison and one inspected mathematical contribution | Both traverse the same protected validation and audit path |
| 4. Paper operation | Execution gateway, risk policy, broker reconciliation, watchdog | Traceable orders and reports; tested pause, restart, timeout, and stale-data behavior |
| 5. Controlled autonomy | Budgeted research and repair tasks; verified candidate promotion | Preserved failures, bounded retries, protected criteria, and owner-reviewable changes |
| 6. Search improvement | AVO-inspired coding search; optional DREAM-style replay | Measured benefit against a simpler loop under an equal budget, including fresh runs |
| 7. Later live consideration | Approved constraints, operating readiness, forward evidence | Separate readiness review and explicit authorization |

The first end-to-end milestone is a terminal-controlled paper workflow that takes a documented dataset through a baseline experiment, an ML comparison, a mathematician review, protected evaluation, independent auditing, and paper execution. Each result links to its code, data, parameters, environment, and complete trial history.

AVO contributes ideas for persistent autonomous coding and supervisory intervention. DREAM-RSI contributes replay of recorded discovery trees to improve exploration policies while leaving the coding agent unchanged. As checked on 7 October 2026, DREAM's official repository lists its full codebase and reproduction scripts as being prepared. A fresh-run comparison is needed to establish the value of any borrowed mechanisms here. [NVIDIA AVO architecture](https://developer.nvidia.com/blog/nvidia-avo-reaches-100-on-arc-agi-3-demonstrating-a-frontier-level-general-purpose-architecture-for-long-horizon-autonomous-agents/) and [Dream-RSI official repository](https://github.com/zhengkid/Dream-RSI).

## Decisions needed next

The supplied setup is sufficient to narrow the preparation. Next settle the watchlist, first ML target, benchmark, desktop availability, and research budgets. Verify Alpaca data entitlement and paper behavior during integration. Repository name/hosting and alert route are still open. Live capital and risk limits belong to the later live specification. The written implementation specification remains a separate design step.

