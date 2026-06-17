# Update log — compressed main, this round's main result

Base: `WINE2026_compressed_main_latex_pkg/main.tex` (the version *without* this round's
result, 30 pp). After the edits below: **32 pp in the current `tectonic` build**, compiles with **0 errors and 0 undefined
references** (verified locally with `llncs.cls`; microtype font-expansion disabled only for the
local check — your `tectonic` build of `main.tex` is unaffected). This file is self-contained and
replaces any earlier changelog.

Post-review tweak: the Appendix G/SFBFP opening now says the main unconditional polynomial-time
result is Theorem `thm:mixedinP` for arbitrary drift, with Theorem `cor:inP` as the
nonnegative-drift special case.

Second positioning tweak: after `thm:mixedinP`, the main text now distinguishes three regimes
explicitly. Linear bipartite clearing is exact `P` (new `Corollary \label{cor:linearP}` from
`lem:nonneg` + `thm:mixedinP`); separable monotone nonlinear/AMM clearing remains a `CLS` upper
bound via Tarski/grid rounding, with `P` vs. `CLS`-hardness left open beyond affine maps; and
non-bipartite linear clearing remains the PPAD-hard side. The abstract, intro, Table 1, the
balanced circuit corollary, Appendix G's path-viewpoint wording, and related work were updated to
avoid selling generic "least fixed point in P" as the novelty. The related-work paragraph now
separates the paper from Besting--Hoefer--Huth's conservation/payment-network algorithms: their
setting computes extremal fixed points in generalized Eisenberg--Noe payment networks, while this
paper's boundary is the DeFi sign structure under price-impact feedback.

Slimming pass for the 13-page main-body limit: the main text now keeps the load-bearing chain
`lem:lfpsub -> lem:fromabove -> lem:activation -> thm:mixedinP -> cor:linearP` with complete
proofs. The `g>=0` reachability/cascade special case (`lem:floor`, `thm:term`, `cor:inP`) remains
stated in the main text to preserve orientation and numbering, but its proofs are moved to
Appendix `app:nonneg-special`. The small-impact contraction proof and the two-sector
nonnegative-drift economic characterization are also in the appendix. The compiled paper has 13
main-text pages before references; references begin on page 14.

Follow-up page-fit fix: the redundant complexity table was replaced by a compact in-text complexity
map. This moves the end of the main text fully onto page 13; the bibliography starts on page 14 in
the `tectonic --keep-logs` build.

## Headline addition: mixed-sign SFBFP is in P

**Where:** end of `\subsection` "Polynomial Time for Subtraction-Free Clearing" (`sec:nonnegdrift`). The
open `\begin{remark}[mixed-sign frontier]` (`rem:mixedsign`) was replaced by:

- a one-sentence standard fact (Kleene): for a continuous isotone self-map of a box, the iterates
  from `0` increase to the least fixed point — this pins down "least" wherever the two lemmas use
  it (per your review note);
- **`Lemma \label{lem:fromabove}`** (from-above cascade): an autonomous block `T_A` with
  `B_AA >= 0`, *arbitrary* `g_A`, whose least fixed point `zeta` is **strictly positive**, has a
  unique fixed point computed in `<= |A|` rounds by starting all-clamped (`C=A`) and repairing
  downward. Starting from the top keeps `C ⊇ U_A`, giving `zhat_I - zeta_I = (I-B_II)^{-1}
  B_IC (u_C - zeta_C) >= 0`, i.e. `zhat_I >= zeta_I > 0`; this **replaces the `g>=0` Neumann
  positivity step** of `thm:term`. `thm:term` is now literally the `g>=0` special case;
- **`Lemma \label{lem:activation}`** (monotone activation): activate floored coordinates with
  positive drive, re-solve the active block by `lem:fromabove`, repeat. Stays `<= z*`, keeps every
  active block all-positive, runs `<= |S|` steps;
- **`Theorem \label{thm:mixedinP}`** (mixed-sign SFBFP is in P): `O(|S|^2)` exact rational solves +
  exact M-matrix tests (`thm:mmatrix`) for arbitrary drift;
- a positive `\begin{remark}` (reusing the label `rem:mixedsign`) stating the case is settled, that
  `cor:inP`/`prop:nonnegdrift` are the special case, and that termination of the *one-pass
  symmetric* cascade remains only a method-level curiosity (the activation algorithm sidesteps it).

The new items compile as **Lemma 5, Lemma 6, Theorem 3**.

## Consistency edits (so nothing still calls the case open)

1. **Abstract** — "isolating a mixed-sign pivoting question" -> activation removes the drift-sign
   restriction, P for all drift.
2. **Intro** (after the monotonicity paragraph) — "leaves mixed-sign drift as a precise pivoting
   open problem" -> "then extends it to arbitrary drift by a monotone activation argument".
3. **Table 1** complexity cell — "P under small impact or nonnegative-drift SFBFP" -> "P under small
   impact, or large-impact SFBFP (all drift)".
4. **`sec:nonnegdrift` intro** — "sharpen the CLS upper bound in the nonnegative-drift regime" ->
   "in the large-impact regime, first for nonnegative drift and then ... for arbitrary drift".
5. **Economic-scope remark** (after `prop:nonnegdrift`) — cross-reference changed from
   `Remark rem:mixedsign` to `Theorem thm:mixedinP`.
6. **Related work** — paragraph title "Related work and open case." -> "Related work."; closing
   sentence "The open case is mixed-sign SFBFP ... remains open" -> "Mixed-sign SFBFP is in P
   (Theorem thm:mixedinP) ...".
7. **Appendix** (orbit-following section) — paragraph title "Open problem." -> "Complexity of the
   mixed-sign case (settled)."; body rewritten to a settled statement citing `thm:mixedinP`.
8. **Appendix summary table** — "sign-balanced + mixed-sign drift & open" -> "sign-balanced +
   arbitrary drift & P (Theorem thm:mixedinP)".
9. **Appendix method-level lines** — credit both `cor:inP` (nonneg) and `thm:mixedinP` (arbitrary)
   for bypassing the ramping-timing problem; disclaimer now mentions both main P theorems.

A full-text sweep for `remains open / open frontier / open case / Open problem /
nonnegative-drift SFBFP / pivoting question` returns nothing outside the new positive content.

## On your must-fix point (1), the `p^0_k <= M_k` condition

In **this** compressed base it is **already present and correct**: `prop:nonnegdrift` lists
`p^0_k <= M_k (k in R)` explicitly among its conditions, and its proof in `app:zmatrix` says the
displayed inequalities *are exactly* the nonnegativity of the drift entries — there is no bogus
"because `p_k in [0,M_k]`" justification here. So nothing was changed for (1). (That regression was
in the earlier `Strengthened_CLS` draft, not in this one.)

## Verification (for your confidence; not written into the paper)

`thm:mixedinP` is backed by ~2686 exact/high-precision instances with **0 failures**: 2177 vs the
exact oracle at `n<=7` (incl. 4 direct at `n=8` with both floors and caps), 120 near-critical
(`rho~1`) exact, 385 vs high-precision Kleene at `n<=16` (worst error 2.66e-15); every proof step
asserted at runtime. Code: `open_problem_explorer/twolevel.py` + `test_twolevel*.py`; proof note:
`open_problem_explorer/mixedsign_inP_proof.md`. (These are not in the zip; available on request.)

## Caveats before submitting

- This is now the paper's central claim. Please give `thm:mixedinP` / `lem:fromabove` /
  `lem:activation` a line-by-line read at the standard you hold `thm:term` to. The verification is
  evidence, not a referee.
- Beyond the consistency edits above, the hardness side, the other appendices, and the bibliography
  were **not** re-audited this round.
- The preview PDF was compiled with microtype expansion disabled (local toolchain limitation only);
  it is visually identical to your `tectonic` build of `main.tex`.
