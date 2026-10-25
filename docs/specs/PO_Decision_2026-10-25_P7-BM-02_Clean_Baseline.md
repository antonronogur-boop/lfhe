<!-- PO decision received 2026-10-25 17:19 (Europe/Budapest). Stored verbatim (SD-12). -->

PRODUCT OWNER DECISION — P7-BM-02 CLEAN BASELINE
Status: FINAL / APPROVED
A P7-BM-02 hibamentes alapverziója az alábbi tartalommal kerüljön rögzítésre.
SOURCE CLAIMS
Claim A
Source attribution: the Northland air force
The Northland air force reported that four tanker aircraft arrived at Fort Aster.
Claim D
Source attribution: a Northland defence ministry spokesman
A Northland defence ministry spokesman denied that any tanker aircraft arrived at Fort Aster.
The two claims are explicitly contradictory.
Neither claim is to be treated as established ground truth.
CLEAN REPORT BASELINE
Statement 1 — Reported fact / contested
The Northland air force reported that four tanker aircraft arrived at Fort Aster.
Requirements:

* attribution must remain exactly tied to the Northland air force;
* this is a reported claim, not an independently established fact;
* `contested = true`.

Statement 2 — Contradictory reported fact
A Northland defence ministry spokesman denied that any tanker aircraft arrived at Fort Aster.
Requirements:

* attribution must remain exactly tied to the Northland defence ministry spokesman;
* the statement must remain explicitly visible as the contradiction to Statement 1;
* `contested = true`.

Statement 3 — Key Judgement
With no evidentiary basis in the available benchmark record to privilege either official statement, there is a roughly even chance that tanker aircraft arrived at Fort Aster.
Required analytical metadata:

* likelihood: `ROUGHLY_EVEN_CHANCE`;
* analytic confidence: `LOW`;
* `contested = true`.

This statement is intentionally limited to the disputed arrival.
It does not infer:

* expansion of capability;
* operational intent;
* duration of deployment;
* readiness;
* force posture;
* future activity.

Statement 4 — Warning / analytical boundary
The reported arrival remains contested, and no further conclusion about the aircraft is supported by the available claims.
This warning introduces no new factual claim.
It defines the analytical boundary of the available evidence.
CLEAN-BASELINE ACCEPTANCE
This baseline is accepted as internally consistent because:

1. all source attribution matches the underlying claims;
2. the two contradictory official statements remain explicitly separated;
3. neither source claim is promoted to established fact;
4. the Key Judgement acknowledges the contradiction;
5. the Key Judgement uses approved likelihood terminology;
6. analytic confidence is LOW;
7. disputed status is explicit;
8. no unsupported capability, intent, duration or force-development inference is introduced;
9. the warning introduces no additional evidence;
10. the report does not contain information absent from the benchmark evidence envelope.

IMPLEMENTATION DIRECTION
Replace the P7-BM-02 clean baseline with the text above.
Then regenerate the 18 benchmark cases using the previously approved error classes.
The seeded-error cases may modify only the feature required to introduce the intended benchmark defect.
Do not introduce unrelated differences between cases.
The three clean cases must preserve the approved baseline without additional semantic changes.
No further Product Owner review of the clean baseline is required if the text above is stored verbatim.
After implementation and green regression:
run:

* branch: `main`
* model: `claude-sonnet-5-5`
* sampling: `provider_fixed`
* scope: `benchmark_02_only`

The resulting P7-BM-02 real-provider evidence may be used to evaluate:

* semantic recall;
* critical misses;
* false-positive behaviour;
* precision;
* clean-case behaviour;
* CG7 criterion 19.

DEV operational pilot cycles remain on HOLD until the P7-BM-02 result has been evaluated.
P7-BM-02 CLEAN BASELINE — APPROVED.

A workflow pedig futtatás alatt
